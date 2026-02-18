import argparse
import base64
import csv
import json
import os
import time

from config import load_config, merge_config
from datasets import append_derived_features, append_labels, ensure_dataset_dir
from features import (
    analyze_readme,
    detect_ai_artifacts,
    detect_ci,
    detect_scripts,
    detect_tests,
    extract_features,
)
from github_client import GitHubClient, now_iso as now_iso_api
from github_scraper import GitHubScraper, now_iso as now_iso_html
from outputs import (
    create_run_dir,
    write_batch_summary,
    write_profiles_jsonl,
    write_scores_csv,
    write_top_report,
)
from scoring import score_candidate
from schemas import validate_profile


def main():
    parser = argparse.ArgumentParser(
        description="GitHub-based Candidate Screening & Ranking MVP"
    )
    parser.add_argument("--candidates", default="candidates.csv")
    parser.add_argument("--job", default="job.md")
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--store-full-resume", action="store_true")
    args = parser.parse_args()

    result = run_pipeline(
        args.candidates,
        args.job,
        args.config,
        store_full_resume=args.store_full_resume,
    )
    print("Run complete")
    print(f"Profiles: {result['profiles_path']}")
    print(f"Scores: {result['scores_path']}")
    print(f"Report: {result['report_path']}")


def run_pipeline(
    candidates_path,
    job_path,
    config_path,
    store_full_resume=False,
    config_overrides=None,
):
    config = load_config(config_path)
    config = merge_config(config, config_overrides)
    if store_full_resume:
        config["resume_samples"]["store_full_text"] = True

    candidates = load_candidates(candidates_path)
    job_keywords = load_job_keywords(job_path)

    github_config = config.get("github", {})
    token = os.environ.get(github_config.get("token_env", "GITHUB_TOKEN"))
    timeout = int(github_config.get("request_timeout_sec", 20))
    max_repos = int(github_config.get("per_handle_max_repos", 12))
    cache_ttl_hours = int(github_config.get("cache_ttl_hours", 24))

    if token:
        client = GitHubClient(token=token, timeout=timeout)
        scraper = None
    else:
        client = None
        scraper = GitHubScraper(timeout=timeout)

    profiles = []
    resume_rows = []
    label_rows = []
    batch_summaries = []

    activity_window_days = config.get("activity", {}).get("window_days", 90)

    processing_config = config.get("processing", {})
    batch_size = int(processing_config.get("batch_size", 20))
    deviation_threshold = float(processing_config.get("batch_deviation_threshold", 0.2))
    if batch_size <= 0:
        batch_size = max(1, len(candidates))

    for batch_index, batch in enumerate(_chunked(candidates, batch_size), start=1):
        batch_profiles = []
        for candidate in batch:
            handle = candidate.get("handle")
            if not handle:
                continue
            github_data = get_github_data(
                handle,
                client=client,
                scraper=scraper,
                cache_ttl_hours=cache_ttl_hours,
                max_repos=max_repos,
                activity_window_days=activity_window_days,
            )
            features = extract_features(github_data, activity_window_days=activity_window_days)
            scores = score_candidate(features, config.get("scoring", {}).get("weights", {}))
            job_fit = derive_job_fit(job_keywords, github_data, features)

            display_id = _candidate_display_id(candidate)
            profile = {
                "candidate_id": display_id,
                "candidate_name": candidate.get("candidate_name"),
                "source_file": candidate.get("source_file"),
                "handle": handle,
                "batch_id": batch_index,
                "job_fit": job_fit,
                "evidence": {
                    "top_repos": features.get("top_repos"),
                    "languages": features.get("languages"),
                    "readme_with_install": features.get("readme_with_install"),
                    "ci_present": features.get("has_ci"),
                    "tests_present": features.get("has_tests"),
                    "activity_summary": _activity_summary(features),
                },
                "scores": scores,
                "score_rationale": build_rationale(features, scores),
            }
            valid, _ = validate_profile(profile)
            if not valid:
                continue
            profiles.append(profile)
            batch_profiles.append(profile)

            dataset_payload = build_resume_dataset_payload(candidate, config)
            if dataset_payload:
                resume_rows.append(dataset_payload["derived"])
                if dataset_payload.get("label"):
                    label_rows.append(dataset_payload["label"])

        batch_summaries.append(
            _batch_summary(batch_profiles, batch_index, deviation_threshold)
        )

    run_dir = create_run_dir()
    profiles_path = write_profiles_jsonl(run_dir, profiles)
    scores_path = write_scores_csv(run_dir, profiles)
    report_path = write_top_report(
        run_dir, profiles, int(config.get("output", {}).get("top_n", 10))
    )
    batch_path = write_batch_summary(run_dir, batch_summaries)

    if config.get("resume_samples", {}).get("enable_storage"):
        dataset_dir = ensure_dataset_dir()
        if label_rows:
            append_labels(dataset_dir, label_rows)
        if resume_rows:
            append_derived_features(dataset_dir, resume_rows)

    return {
        "run_dir": run_dir,
        "profiles_path": profiles_path,
        "scores_path": scores_path,
        "report_path": report_path,
        "batch_summary_path": batch_path,
    }


def load_candidates(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for idx, row in enumerate(reader, start=1):
            handle = (
                row.get("handle")
                or row.get("github")
                or row.get("github_handle")
                or row.get("github_username")
            )
            candidate_id = row.get("candidate_id") or f"c{idx:03d}"
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "handle": (handle or "").strip().lstrip("@"),
                    "candidate_name": row.get("candidate_name") or row.get("name"),
                    "source_file": row.get("source_file"),
                    "resume_summary": row.get("resume_summary"),
                    "extracted_skills": row.get("extracted_skills"),
                    "labels": row.get("labels"),
                    "reviewer_note": row.get("reviewer_note"),
                    "resume_full_text": row.get("resume_full_text"),
                }
            )
    return rows


def load_job_keywords(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().lower()
    tokens = set()
    for token in text.split():
        token = token.strip(" ,.;:()[]{}\n\t\r\"")
        if len(token) >= 3:
            tokens.add(token)
    return tokens


def get_github_data(
    handle,
    client,
    scraper,
    cache_ttl_hours,
    max_repos,
    activity_window_days,
):
    cache_path = os.path.join("cache", "github", f"{handle}.json")
    cached = _read_cache(cache_path, cache_ttl_hours)
    if cached:
        return cached

    if client:
        data = _collect_from_api(handle, client, max_repos, activity_window_days)
    else:
        data = _collect_from_html(handle, scraper, max_repos)

    if data:
        _write_cache(cache_path, data)
    return data or {"handle": handle, "repos": [], "activity": {}}


def _read_cache(path, ttl_hours):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fetched_at = data.get("fetched_at")
        if not fetched_at:
            return data
        fetched_ts = _parse_iso(fetched_at)
        if fetched_ts is None:
            return data
        if time.time() - fetched_ts <= ttl_hours * 3600:
            return data
    except Exception:
        return None
    return None


def _write_cache(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, sort_keys=True)


def _collect_from_api(handle, client, max_repos, activity_window_days):
    user = client.get_user(handle) or {}
    repos_raw = client.get_repos(handle) or []
    repos_raw = sorted(
        repos_raw,
        key=lambda r: r.get("updated_at") or "",
        reverse=True,
    )[:max_repos]

    repos = []
    for repo in repos_raw:
        name = repo.get("name")
        if not name:
            continue
        owner = repo.get("owner", {}).get("login") or handle
        readme_data = client.get_readme(owner, name)
        readme_text = None
        if readme_data and readme_data.get("content"):
            try:
                readme_text = base64.b64decode(readme_data.get("content")).decode(
                    "utf-8", errors="ignore"
                )
            except Exception:
                readme_text = None
        readme_flags = analyze_readme(readme_text)

        contents = client.get_contents(owner, name, "")
        file_names = []
        if isinstance(contents, list):
            file_names = [item.get("path") for item in contents if item.get("path")]
        workflows = client.get_workflows(owner, name)
        workflow_names = []
        if workflows and isinstance(workflows.get("workflows"), list):
            workflow_names = [wf.get("path") for wf in workflows.get("workflows") if wf]
        combined_files = file_names + workflow_names

        repo_entry = {
            "name": name,
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language"),
            "updated_at": repo.get("updated_at"),
            "has_readme": readme_flags.get("has_readme"),
            "readme_has_install": readme_flags.get("readme_has_install"),
            "readme_has_run": readme_flags.get("readme_has_run"),
            "readme_has_test": readme_flags.get("readme_has_test"),
            "has_tests": detect_tests(combined_files),
            "has_ci": detect_ci(combined_files),
            "has_scripts": detect_scripts(combined_files),
            "has_agents": detect_ai_artifacts(combined_files, readme_text),
            "topics": repo.get("topics") or [],
        }
        repos.append(repo_entry)

    activity = _collect_activity(handle, client, activity_window_days)
    return {
        "handle": handle,
        "fetched_at": now_iso_api(),
        "source": "rest",
        "profile": {
            "name": user.get("name"),
            "company": user.get("company"),
            "bio": user.get("bio"),
            "public_repos": user.get("public_repos"),
            "followers": user.get("followers"),
        },
        "repos": repos,
        "activity": activity,
    }


def _collect_activity(handle, client, window_days):
    events = client.get_events(handle) or []
    now = time.time()
    window_seconds = window_days * 86400
    weekly_buckets = [0] * (window_days // 7 + 1)
    recent_commits = 0
    recent_prs = 0
    recent_issues = 0
    small_prs = 0

    for event in events:
        created_at = event.get("created_at")
        created_ts = _parse_iso(created_at) if created_at else None
        if not created_ts:
            continue
        if now - created_ts > window_seconds:
            continue
        week_index = int((now - created_ts) // (7 * 86400))
        if 0 <= week_index < len(weekly_buckets):
            weekly_buckets[week_index] += 1

        event_type = event.get("type")
        payload = event.get("payload", {})
        if event_type == "PushEvent":
            recent_commits += len(payload.get("commits") or [])
        elif event_type == "PullRequestEvent":
            recent_prs += 1
            pr = payload.get("pull_request") or {}
            additions = pr.get("additions")
            deletions = pr.get("deletions")
            if additions is not None and deletions is not None:
                if (additions + deletions) <= 200:
                    small_prs += 1
        elif event_type == "IssuesEvent":
            recent_issues += 1

    small_pr_ratio = (small_prs / recent_prs) if recent_prs else 0

    return {
        "recent_commits": recent_commits,
        "recent_prs": recent_prs,
        "recent_issues": recent_issues,
        "small_pr_ratio": round(small_pr_ratio, 3),
        "issue_pr_link_ratio": 0,
        "weekly_activity": weekly_buckets,
    }


def _collect_from_html(handle, scraper, max_repos):
    if not scraper:
        return None
    user = scraper.get_user(handle) or {}
    repos = scraper.get_repos(handle, max_repos=max_repos)
    return {
        "handle": handle,
        "fetched_at": now_iso_html(),
        "source": "html",
        "profile": {
            "name": user.get("name"),
            "company": None,
            "bio": user.get("bio"),
            "public_repos": None,
            "followers": None,
        },
        "repos": repos,
        "activity": {
            "recent_commits": 0,
            "recent_prs": 0,
            "recent_issues": 0,
            "small_pr_ratio": 0,
            "issue_pr_link_ratio": 0,
            "weekly_activity": [],
        },
    }


def derive_job_fit(job_keywords, github_data, features):
    if not job_keywords:
        return []
    terms = set()
    for language in features.get("languages", []):
        terms.add(language.lower())
    for repo in github_data.get("repos", []):
        for topic in repo.get("topics") or []:
            terms.add(topic.lower())
    return sorted([word for word in job_keywords if word in terms])


def build_rationale(features, scores):
    rationale = []

    if scores.get("EngineeringScore", 0) > 0:
        eng_bits = []
        if features.get("has_ci"):
            eng_bits.append("CI")
        if features.get("has_tests"):
            eng_bits.append("tests")
        if features.get("readme_with_install"):
            eng_bits.append("README install/run")
        if features.get("recent_commits"):
            eng_bits.append("recent commits")
        rationale.append(
            "Engineering: " + (", ".join(eng_bits) if eng_bits else "evidence present")
        )
    else:
        rationale.append("Engineering: insufficient evidence")

    if scores.get("ImpactScore", 0) > 0:
        rationale.append("Impact: stars/forks or meaningful PR activity")
    else:
        rationale.append("Impact: insufficient evidence")

    if scores.get("ActivityScore", 0) > 0:
        rationale.append("Activity: recent commits/PRs/issues")
    else:
        rationale.append("Activity: insufficient evidence")

    if scores.get("AIProductivityScore", 0) > 0:
        rationale.append("AIProductivity: automation signals or doc clarity")
    else:
        rationale.append("AIProductivity: insufficient evidence")

    return rationale


def build_resume_dataset_payload(candidate, config):
    if not config.get("resume_samples", {}).get("enable_storage"):
        return None
    derived = {
        "candidate_id": candidate.get("candidate_id"),
        "resume_summary": candidate.get("resume_summary"),
        "extracted_skills": _split_list(candidate.get("extracted_skills")),
        "labels": _split_list(candidate.get("labels")),
        "reviewer_note": candidate.get("reviewer_note"),
        "resume_full_text": None,
    }
    if config.get("resume_samples", {}).get("store_full_text"):
        derived["resume_full_text"] = candidate.get("resume_full_text")
    label = None
    if candidate.get("labels"):
        label = {
            "candidate_id": candidate.get("candidate_id"),
            "label": candidate.get("labels"),
            "reviewer_note": candidate.get("reviewer_note"),
        }
    return {"derived": derived, "label": label}


def _split_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).split("|") if item.strip()]


def _activity_summary(features):
    return (
        f"{features.get('recent_commits', 0)} commits, "
        f"{features.get('recent_prs', 0)} PRs, "
        f"{features.get('recent_issues', 0)} issues "
        f"({features.get('activity_window_days', 90)}d)"
    )


def _parse_iso(value):
    if not value:
        return None
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


if __name__ == "__main__":
    main()
def _candidate_display_id(candidate):
    if candidate.get("candidate_name"):
        return candidate.get("candidate_name")
    if candidate.get("source_file"):
        return os.path.splitext(candidate.get("source_file"))[0]
    if candidate.get("handle"):
        return candidate.get("handle")
    return candidate.get("candidate_id")


def _chunked(items, size):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def _batch_summary(profiles, batch_id, deviation_threshold):
    scores = [p.get("scores", {}) for p in profiles]
    totals = [s.get("TotalScore", 0) for s in scores]
    avg_total = _avg(totals)
    deviation_flag = False
    if totals and avg_total > 0:
        deviation = max(totals) - min(totals)
        deviation_flag = (deviation / avg_total) > deviation_threshold
    return {
        "batch_id": batch_id,
        "count": len(profiles),
        "avg_total": avg_total,
        "avg_engineering": _avg([s.get("EngineeringScore", 0) for s in scores]),
        "avg_impact": _avg([s.get("ImpactScore", 0) for s in scores]),
        "avg_activity": _avg([s.get("ActivityScore", 0) for s in scores]),
        "avg_ai_productivity": _avg([s.get("AIProductivityScore", 0) for s in scores]),
        "deviation_flag": deviation_flag,
        "deviation_threshold": deviation_threshold,
    }


def _avg(values):
    if not values:
        return 0
    return round(sum(values) / len(values), 2)

import csv
import json
import os
import time


def create_run_dir(base_dir="runs"):
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    run_dir = os.path.join(base_dir, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def write_profiles_jsonl(run_dir, profiles):
    path = os.path.join(run_dir, "profiles.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for profile in profiles:
            f.write(json.dumps(profile, ensure_ascii=True) + "\n")
    return path


def write_scores_csv(run_dir, profiles):
    path = os.path.join(run_dir, "scores.csv")
    fieldnames = [
        "candidate_id",
        "candidate_name",
        "source_file",
        "handle",
        "EngineeringScore",
        "ImpactScore",
        "ActivityScore",
        "AIProductivityScore",
        "TotalScore",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for profile in profiles:
            scores = profile.get("scores", {})
            writer.writerow(
                {
                    "candidate_id": profile.get("candidate_id"),
                    "candidate_name": profile.get("candidate_name"),
                    "source_file": profile.get("source_file"),
                    "handle": profile.get("handle"),
                    "EngineeringScore": scores.get("EngineeringScore"),
                    "ImpactScore": scores.get("ImpactScore"),
                    "ActivityScore": scores.get("ActivityScore"),
                    "AIProductivityScore": scores.get("AIProductivityScore"),
                    "TotalScore": scores.get("TotalScore"),
                }
            )
    return path


def write_top_report(run_dir, profiles, top_n):
    path = os.path.join(run_dir, "top_report.md")
    sorted_profiles = sorted(
        profiles, key=lambda p: p.get("scores", {}).get("TotalScore", 0), reverse=True
    )
    top_profiles = sorted_profiles[:top_n]
    lines = ["# Top Candidates", "", f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}", ""]
    for idx, profile in enumerate(top_profiles, start=1):
        scores = profile.get("scores", {})
        evidence = profile.get("evidence", {})
        lines.append(f"## {idx}. {profile.get('candidate_id')} ({profile.get('handle')})")
        lines.append(f"- TotalScore: {scores.get('TotalScore')}")
        lines.append(
            "- Subscores: "
            f"Engineering {scores.get('EngineeringScore')}, "
            f"Impact {scores.get('ImpactScore')}, "
            f"Activity {scores.get('ActivityScore')}, "
            f"AIProductivity {scores.get('AIProductivityScore')}"
        )
        lines.append(f"- Top repos: {', '.join(evidence.get('top_repos', [])) or 'unknown'}")
        lines.append(
            f"- Evidence: CI {evidence.get('ci_present')}, Tests {evidence.get('tests_present')}, README install {evidence.get('readme_with_install')}"
        )
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def write_batch_summary(run_dir, summaries):
    path = os.path.join(run_dir, "batch_summary.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for summary in summaries:
            f.write(json.dumps(summary, ensure_ascii=True) + "\n")
    return path

import re


def extract_features(github_data, activity_window_days=90):
    repos = github_data.get("repos", [])
    languages = []
    top_repos = []
    total_stars = 0
    total_forks = 0
    has_ci = False
    has_tests = False
    has_readme = False
    readme_with_install = False
    automation_signals = 0
    ai_artifact_bonus = 0

    for repo in repos:
        name = repo.get("name")
        if name:
            top_repos.append(name)
        language = repo.get("language")
        if language:
            languages.append(language)
        total_stars += int(repo.get("stars") or 0)
        total_forks += int(repo.get("forks") or 0)
        if repo.get("has_ci"):
            has_ci = True
            automation_signals += 1
        if repo.get("has_tests"):
            has_tests = True
        if repo.get("has_readme"):
            has_readme = True
            if repo.get("readme_has_install"):
                readme_with_install = True
        if repo.get("has_scripts"):
            automation_signals += 1
        if repo.get("has_agents"):
            ai_artifact_bonus = 1

    activity = github_data.get("activity", {})
    recent_commits = int(activity.get("recent_commits") or 0)
    recent_prs = int(activity.get("recent_prs") or 0)
    recent_issues = int(activity.get("recent_issues") or 0)
    small_pr_ratio = float(activity.get("small_pr_ratio") or 0)
    issue_pr_link_ratio = float(activity.get("issue_pr_link_ratio") or 0)
    weekly_activity = activity.get("weekly_activity") or []

    return {
        "top_repos": top_repos[:8],
        "languages": _uniq(languages),
        "total_stars": total_stars,
        "total_forks": total_forks,
        "has_ci": has_ci,
        "has_tests": has_tests,
        "has_readme": has_readme,
        "readme_with_install": readme_with_install,
        "automation_signals": automation_signals,
        "recent_commits": recent_commits,
        "recent_prs": recent_prs,
        "recent_issues": recent_issues,
        "small_pr_ratio": small_pr_ratio,
        "issue_pr_link_ratio": issue_pr_link_ratio,
        "weekly_activity": weekly_activity,
        "ai_artifact_bonus": ai_artifact_bonus,
        "activity_window_days": activity_window_days,
    }


def analyze_readme(text):
    if not text:
        return {
            "has_readme": False,
            "readme_has_install": False,
            "readme_has_run": False,
            "readme_has_test": False,
        }
    lowered = text.lower()
    has_install = _match_any(lowered, ["install", "setup", "getting started"])
    has_run = _match_any(lowered, ["usage", "run", "quickstart"])
    has_test = _match_any(lowered, ["test", "pytest", "npm test", "go test"])
    return {
        "has_readme": True,
        "readme_has_install": has_install,
        "readme_has_run": has_run,
        "readme_has_test": has_test,
    }


def detect_tests(files):
    if not files:
        return False
    patterns = [r"test", r"tests", r"spec", r"pytest", r"unittest", r"go test"]
    for name in files:
        lowered = name.lower()
        if any(re.search(pat, lowered) for pat in patterns):
            return True
    return False


def detect_ci(files):
    if not files:
        return False
    for name in files:
        lowered = name.lower()
        if ".github/workflows" in lowered:
            return True
        if "circleci" in lowered or "travis" in lowered or "github/workflows" in lowered:
            return True
    return False


def detect_scripts(files):
    if not files:
        return False
    for name in files:
        lowered = name.lower()
        if "makefile" in lowered or "scripts/" in lowered:
            return True
    return False


def detect_ai_artifacts(files, readme_text):
    if files:
        for name in files:
            lowered = name.lower()
            if "prompts" in lowered or "agents" in lowered:
                return True
    if readme_text and re.search(r"ai|prompt|agent", readme_text, re.I):
        return True
    return False


def _uniq(items):
    seen = set()
    output = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _match_any(text, keywords):
    return any(keyword in text for keyword in keywords)

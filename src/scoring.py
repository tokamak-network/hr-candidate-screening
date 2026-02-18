def score_candidate(features, weights):
    eng = _score_engineering(features)
    impact = _score_impact(features)
    activity = _score_activity(features)
    ai_prod = _score_ai_productivity(features)
    total = eng + impact + activity + ai_prod
    return {
        "EngineeringScore": eng,
        "ImpactScore": impact,
        "ActivityScore": activity,
        "AIProductivityScore": ai_prod,
        "TotalScore": min(100, total),
    }


def _score_engineering(f):
    score = 0
    if f.get("has_ci"):
        score += 10
    if f.get("has_tests"):
        score += 10
    # Language diversity: 1 lang=4, 2=8(same as before), 3+=10
    lang_count = len(f.get("languages", []))
    score += _cap(lang_count * 4, 10)
    if f.get("readme_with_install"):
        score += 6
    # Activity bonus: halved divisor for more sensitivity
    activity_points = _cap((f.get("recent_commits", 0) + f.get("recent_prs", 0)) // 5, 6)
    score += activity_points
    # Job fit bonus: reward tech stack alignment with JD
    score += _cap(f.get("job_fit_count", 0) * 2, 6)
    return _cap(score, 40)


def _score_impact(f):
    score = 0
    stars = f.get("total_stars", 0)
    forks = f.get("total_forks", 0)
    # Halved threshold: 1pt per 5 stars (was per 10)
    score += _cap(stars // 5, 12)
    # Lowered fork threshold: 1pt per 3 forks (was per 5)
    score += _cap(forks // 3, 6)
    if f.get("recent_prs", 0) > 3:
        score += 6
    return _cap(score, 30)


def _score_activity(f):
    score = 0
    total_activity = f.get("recent_commits", 0) + f.get("recent_prs", 0) + f.get("recent_issues", 0)
    # Lowered threshold: 1pt per 3 events (was per 5)
    score += _cap(total_activity // 3, 10)
    weekly = f.get("weekly_activity", [])
    if weekly:
        active_weeks = sum(1 for v in weekly if v > 0)
        score += _cap(active_weeks // 2, 5)
    return _cap(score, 15)


def _score_ai_productivity(f):
    score = 0
    score += _cap(f.get("automation_signals", 0) * 3, 7)
    score += _cap(int(f.get("small_pr_ratio", 0) * 4), 4)
    if f.get("readme_with_install"):
        score += 3
    if f.get("ai_artifact_bonus"):
        score += 1
    return _cap(score, 15)


def _cap(value, limit):
    return min(limit, int(value))

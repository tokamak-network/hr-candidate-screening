PROFILE_FIELDS = [
    "candidate_id",
    "handle",
    "job_fit",
    "evidence",
    "scores",
    "score_rationale",
]

SCORE_FIELDS = [
    "EngineeringScore",
    "ImpactScore",
    "ActivityScore",
    "AIProductivityScore",
    "TotalScore",
]


def validate_profile(profile):
    missing = [key for key in PROFILE_FIELDS if key not in profile]
    if missing:
        return False, f"missing fields: {', '.join(missing)}"
    scores = profile.get("scores", {})
    missing_scores = [key for key in SCORE_FIELDS if key not in scores]
    if missing_scores:
        return False, f"missing score fields: {', '.join(missing_scores)}"
    return True, "ok"

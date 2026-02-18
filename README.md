# GitHub Candidate Screening & Ranking MVP

Deterministic CLI that scores candidates using GitHub repository evidence, emphasizing AI-enabled productivity signals.

## Quick start

1) Prepare inputs:
- `candidates.csv`
- `job.md`
- `config.yml`

2) Run:

```bash
python src/cli.py --candidates candidates.csv --job job.md --config config.yml
```

3) Outputs:
- `runs/<timestamp>/profiles.jsonl`
- `runs/<timestamp>/scores.csv`
- `runs/<timestamp>/top_report.md`

## Config example

```yaml
github:
  token_env: GITHUB_TOKEN
  cache_ttl_hours: 24
  per_handle_max_repos: 12
  request_timeout_sec: 20
scoring:
  weights:
    engineering: 40
    impact: 30
    activity: 15
    ai_productivity: 15
activity:
  window_days: 90
resume_samples:
  enable_storage: true
  store_full_text: false
output:
  top_n: 10
```

## Scoring overview (0-100)

- EngineeringScore (0-40)
  - CI/workflows, tests, language breadth, README install/run/test, recent code activity
- ImpactScore (0-30)
  - stars/forks and contribution breadth
- ActivityScore (0-15)
  - recent commits/PRs/issues and weekly consistency
- AIProductivityScore (0-15)
  - automation footprint, iteration velocity, doc-to-code clarity, optional AI artifact bonus (never a penalty)

## GitHub data collection

- Uses GitHub REST API when `GITHUB_TOKEN` is set.
- Falls back to public HTML scraping when token is absent.
- Caches raw data in `cache/github/<handle>.json` to avoid rate limits.

## Resume sample storage (privacy)

- Stores only derived/summary features by default.
- Full resume text is not stored unless `store_full_text: true` or `--store-full-resume` is passed.

Outputs:
- `datasets/resume_samples/labels.csv`
- `datasets/resume_samples/derived_features.jsonl`

## Inputs

`candidates.csv` minimal columns:

```
candidate_id,handle
c001,octocat
```

Optional columns:
- `resume_summary`
- `extracted_skills` (pipe-delimited: `Python|CI/CD`)
- `labels`
- `reviewer_note`
- `resume_full_text`

`job.md` is freeform text used to match keywords to repo languages/topics.
- Updated by Jaden (2026-02-18)

# Agent Guide

This repo is a small Python CLI app for GitHub-based candidate screening and ranking.
It is designed to be deterministic and evidence-based.

## Project Summary

- Entry point: `src/cli.py`
- Core modules:
  - `src/github_client.py` (REST API)
  - `src/github_scraper.py` (HTML fallback)
  - `src/features.py` (feature extraction)
  - `src/scoring.py` (deterministic scoring)
  - `src/outputs.py` (run outputs)
  - `src/datasets.py` (resume-derived datasets)
  - `src/config.py` (config loading and defaults)
  - `src/schemas.py` (light validation)

## Build / Lint / Test

There is no formal build, lint, or test harness in this repo yet.
Use the following commands based on intent:

- Run CLI (default):
  - `python3 src/cli.py --candidates candidates.csv --job job.md --config config.yml`
- Run CLI with resume full text enabled:
  - `python3 src/cli.py --candidates candidates.csv --job job.md --config config.yml --store-full-resume`

If you add tooling, document it here. Suggested conventions:

- Lint (suggested):
  - `python3 -m ruff check src`
- Format (suggested):
  - `python3 -m ruff format src`
- Type check (suggested):
  - `python3 -m mypy src`
- Tests (suggested):
  - `python3 -m pytest`

### Single Test Execution

No test suite is defined yet. If tests are added with pytest:
- Run a single test file: `python3 -m pytest tests/test_file.py`
- Run a single test function: `python3 -m pytest tests/test_file.py -k test_name`

## Repo Rules (Cursor / Copilot)

No Cursor rules in `.cursor/rules/` or `.cursorrules`.
No Copilot rules in `.github/copilot-instructions.md`.
If any are added later, update this section.

## Code Style Guidelines

### General

- Keep behavior deterministic. Avoid randomness and nondeterministic ordering.
- Prefer explicit data structures and fixed schemas.
- Avoid free-form model chatter in outputs.
- Maintain ASCII in files unless the file already uses non-ASCII.

### Imports

- Use standard library imports only where possible.
- One import per line; group by standard library then local modules.
- Avoid unused imports; keep imports near the top of the file.

### Formatting

- Use 4 spaces for indentation.
- Keep lines reasonably short (<= 100 chars when possible).
- Use double quotes for strings to match existing code style.
- Prefer f-strings for formatting.

### Types

- This repo does not use type hints consistently.
- Add typing only if it improves clarity and does not add heavy overhead.

### Naming

- Functions: `snake_case`.
- Variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Files/modules: `snake_case`.

### Error Handling

- Fail soft where external I/O is involved (GitHub API, HTML fetch).
- Catch network and JSON errors and return `None` or empty structures.
- Avoid raising exceptions for expected missing data.

### Data and Privacy

- Only store derived resume features by default.
- Full resume text is stored only when `store_full_text` is enabled.
- Never infer demographic attributes or use school/age/gender in scoring.

### GitHub Data Collection

- Prefer REST API when `GITHUB_TOKEN` is available.
- Use HTML scraping only as fallback.
- Cache GitHub data in `cache/github/<handle>.json` with TTL.
- Avoid adding heavy scraping logic; keep selectors minimal.

### Scoring

- Scores are deterministic and capped by defined limits.
- AI artifact detection is an optional bonus and never a penalty.
- If evidence is missing, do not infer; treat as unknown.

### Outputs

- Output paths are under `runs/<timestamp>/`.
- `profiles.jsonl` uses one JSON per line.
- `scores.csv` is deterministic and stable field order.
- `top_report.md` is concise and evidence-based.

### Prompts

- Prompts are stored in `prompts/`.
- Worker must cite evidence strictly from collected GitHub data.
- Reviewer checks schema compliance, evidence grounding, and fairness.

## Suggested Maintenance Notes

- If you add dependencies, document them in README.
- If you add tests, update this file with exact commands.
- Keep cache, runs, and datasets out of version control if needed.

## Implementation Map

- CLI flow: parse inputs -> load config -> fetch/cache GitHub data ->
  extract features -> score -> write outputs -> optional dataset append.
- Feature extraction lives in `src/features.py`.
- Score calculation lives in `src/scoring.py`.
- Output formatting lives in `src/outputs.py`.

## Safe Defaults

- Activity window is 90 days by default.
- Missing GitHub data yields zero or unknown signals, not penalties.
- No secrets should be committed; `GITHUB_TOKEN` should be in env only.

## Non-Goals

- No ML training or model-based scoring in the current MVP.
- No advanced analytics beyond explicit GitHub evidence.

import json
import re
import time
import urllib.request


class GitHubScraper:
    def __init__(self, timeout=20):
        self.timeout = timeout

    def get_user(self, handle):
        html = self._fetch(f"https://github.com/{handle}")
        if not html:
            return None
        name = _extract_first(html, r"<span class=\"p-name vcard-fullname[^>]*\">(.*?)</span>")
        bio = _extract_first(html, r"<div class=\"p-note[^>]*\">(.*?)</div>")
        return {
            "name": _clean_text(name),
            "bio": _clean_text(bio),
        }

    def get_repos(self, handle, max_repos=12):
        html = self._fetch(f"https://github.com/{handle}?tab=repositories")
        if not html:
            return []
        repo_blocks = re.findall(r"<li[^>]*itemprop=\"owns\"[^>]*>(.*?)</li>", html, re.S)
        repos = []
        for block in repo_blocks[: max_repos * 2]:
            name = _extract_first(block, r"itemprop=\"name codeRepository\"[^>]*>\s*([^<]+)")
            if not name:
                continue
            stars = _extract_first(block, r"aria-label=\"(\d+) users starred this repository\"")
            forks = _extract_first(block, r"aria-label=\"(\d+) users forked this repository\"")
            language = _extract_first(block, r"itemprop=\"programmingLanguage\">([^<]+)<")
            updated = _extract_first(block, r"datetime=\"([^\"]+)\"")
            repos.append(
                {
                    "name": _clean_text(name),
                    "stars": int(stars) if stars else 0,
                    "forks": int(forks) if forks else 0,
                    "language": _clean_text(language),
                    "updated_at": updated or None,
                    "has_readme": None,
                    "has_tests": None,
                    "has_ci": None,
                    "topics": [],
                }
            )
            if len(repos) >= max_repos:
                break
        return repos

    def get_repo_details(self, handle, repo_name):
        """Scrape an individual repo page for CI signals, topics, and README snippet."""
        html = self._fetch(f"https://github.com/{handle}/{repo_name}")
        if not html:
            return {"file_hints": [], "topics": [], "readme_text": None}

        # Topics
        topics = re.findall(
            r'data-ga-click="Topic, repository page"[^>]*>([^<]+)<', html
        )
        topics = [t.strip() for t in topics if t.strip()]

        # File hints: look for filenames listed in the repo tree
        file_hints = re.findall(
            r'class="[^"]*js-navigation-open[^"]*"[^>]*>([^<]+)<', html
        )
        file_hints = [f.strip() for f in file_hints if f.strip()]

        # Also check for .github/workflows badge pattern
        if re.search(r'\.github/workflows', html, re.I):
            file_hints.append(".github/workflows/ci.yml")
        if re.search(r'travis-ci|circleci|github.*actions', html, re.I):
            file_hints.append(".github/workflows/ci.yml")

        # README: grab first ~2000 chars of rendered README
        readme_match = re.search(
            r'<article[^>]*class="[^"]*markdown-body[^"]*"[^>]*>(.*?)</article>',
            html, re.S
        )
        readme_text = None
        if readme_match:
            raw = readme_match.group(1)
            readme_text = re.sub(r'<[^>]+>', ' ', raw)[:2000]

        return {"file_hints": file_hints, "topics": topics, "readme_text": readme_text}

    def get_activity(self, handle, window_days=90):
        """Parse the GitHub contributions page for recent activity."""
        html = self._fetch(f"https://github.com/users/{handle}/contributions")
        recent_commits = 0
        weekly_activity = []
        if html:
            # Try to extract total contributions mentioned on page
            total_match = re.search(r'([\d,]+)\s+contributions?\s+in the last year', html)
            if total_match:
                # Use the yearly total as a proxy; scale to window_days/365
                yearly = int(total_match.group(1).replace(",", ""))
                recent_commits = int(yearly * window_days / 365)

            # Parse per-day tooltips: "N contributions on Month Dayth."
            # These cover the last year; take the most recent window_days entries
            tooltips = re.findall(
                r'<tool-tip[^>]*>(\d+) contributions? on ([^<]+?)\.',
                html
            )
            if tooltips:
                daily_counts = [int(t[0]) for t in tooltips]
                # Tooltips appear oldest→newest; take last window_days days
                daily = daily_counts[-window_days:] if len(daily_counts) >= window_days else daily_counts
                recent_commits = sum(daily)
                # Bucket into weeks (index 0 = most recent week)
                bucket = []
                for v in reversed(daily):
                    bucket.append(v)
                    if len(bucket) == 7:
                        weekly_activity.append(sum(bucket))
                        bucket = []
                if bucket:
                    weekly_activity.append(sum(bucket))

        return {
            "recent_commits": recent_commits,
            "recent_prs": 0,
            "recent_issues": 0,
            "small_pr_ratio": 0,
            "issue_pr_link_ratio": 0,
            "weekly_activity": weekly_activity,
        }

    def _fetch(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except Exception:
            return None


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _extract_first(text, pattern):
    match = re.search(pattern, text, re.S)
    if match:
        return match.group(1)
    return None


def _clean_text(value):
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip()


def to_json(data):
    return json.dumps(data, ensure_ascii=True, sort_keys=True)

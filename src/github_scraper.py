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

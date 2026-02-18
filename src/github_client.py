import json
import time
import urllib.error
import urllib.parse
import urllib.request


class GitHubClient:
    def __init__(self, token=None, timeout=20):
        self.token = token
        self.timeout = timeout

    def get_user(self, handle):
        return self._get_json(f"https://api.github.com/users/{handle}")

    def get_repos(self, handle, per_page=100):
        url = (
            f"https://api.github.com/users/{handle}/repos?"
            f"per_page={per_page}&sort=updated"
        )
        return self._get_json(url) or []

    def get_events(self, handle, per_page=100):
        url = f"https://api.github.com/users/{handle}/events/public?per_page={per_page}"
        return self._get_json(url) or []

    def get_readme(self, owner, repo):
        url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        return self._get_json(url)

    def get_contents(self, owner, repo, path=""):
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        return self._get_json(url)

    def get_workflows(self, owner, repo):
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows"
        return self._get_json(url)

    def _get_json(self, url):
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError:
            return None
        except urllib.error.URLError:
            return None
        except json.JSONDecodeError:
            return None


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

"""Your GitHub repositories: a new star, fork, or issue/PR is announced.

sources.github: {"enabled": true, "repos": ["you/project"], "minutes": 10}. It reads the
public numbers from the GitHub API without logging in (60 requests an hour, plenty for a
few repos every 10 minutes). The first check of a repo only notes its numbers; later
checks announce what went up. A private repo needs GITHUB_TOKEN in the environment.
"""

import json
import os
import urllib.request

from .. import config, paths
from ..events import Event
from ..log import log

STATE = os.path.join(paths.HOME, "github.json")
COUNTS = (("stargazers_count", "新的 star"), ("forks_count", "新的 fork"), ("open_issues_count", "新的 Issue 或 PR"))


def fetch(repo):
    headers = {"accept": "application/vnd.github+json", "user-agent": "bobao"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def changes(repo, data, seen):
    """Events for the numbers that went up since `seen` (updated in place)."""
    out, before = [], seen.get(repo)
    now = {k: data.get(k, 0) for k, _ in COUNTS}
    seen[repo] = now
    if before is None:
        return out
    for k, title in COUNTS:
        if now[k] > before.get(k, now[k]):
            out.append(Event("github", repo, title, fields={"仓库": repo.split("/")[-1], "数量": str(now[k])}, bot=True))
    return out


def check(cfg, handle, get=fetch):
    seen = config.read_json(STATE, {}) or {}
    for repo in cfg["sources"]["github"].get("repos", []):
        try:
            evs = changes(repo, get(repo), seen)
        except Exception as e:
            log(f"读取 GitHub {repo} 失败：{e}")
            continue
        for ev in evs:
            handle(ev)
    with open(STATE, "w") as f:
        json.dump(seen, f)

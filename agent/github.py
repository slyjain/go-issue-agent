from __future__ import annotations

import json 
import urllib.request

from agent.types import Issue

_API = "https://api.github.com"

def fetch_issue(repo: str, number: int) -> Issue:
    url = f"{_API}/repos/{repo}/issues/{number}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return Issue(
        number=data["number"],
        title=data["title"],
        body=data.get("body") or "",
        labels=[l["name"] for l in data.get("labels", [])],
        url=data["html_url"],
    )


def fetch_pr_diff(repo: str, pr_number: int) -> str:
    url = f"{_API}/repos/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github.v3.diff"}
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode()

def fetch_pr_metadata(repo: str, pr_number: int) -> dict:
    url = f"{_API}/repos/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return {
        "title": data["title"],
        "body": data.get("body") or "",
        "base_sha": data["base"]["sha"],
        "head_sha": data["head"]["sha"],
        "merged": data.get("merged", False),
    }

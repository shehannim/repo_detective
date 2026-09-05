"""
github.py — Fetch GitHub issue data for repo-detective.

Supports:
  - Unauthenticated requests (60 req/hr rate limit)
  - GITHUB_TOKEN env var for 5000 req/hr

Returns a GitHubIssue dataclass with title, body, labels, and metadata.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

import httpx

_GH_API = "https://api.github.com"
_TIMEOUT = 10.0


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: List[str]
    state: str
    html_url: str
    repo_url: str          # HTTPS clone URL of the repo
    author: str


def _auth_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _repo_url_from_api(repo_full: str) -> str:
    """Return the HTTPS clone URL for a repo full name (owner/repo)."""
    return f"https://github.com/{repo_full}.git"


def parse_repo_full_name(repo_url: str) -> str:
    """
    Extract 'owner/repo' from a GitHub URL.
    Accepts: https://github.com/owner/repo[.git][/...]
    """
    repo_url = repo_url.strip().rstrip("/")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {repo_url!r}")
    return f"{parts[0]}/{parts[1]}"


def fetch_issue(repo_url: str, issue_number: int) -> GitHubIssue:
    """
    Fetch a single GitHub issue by number.
    Raises httpx.HTTPStatusError on 4xx/5xx.
    """
    repo_full = parse_repo_full_name(repo_url)
    url = f"{_GH_API}/repos/{repo_full}/issues/{issue_number}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **_auth_headers(),
    }

    resp = httpx.get(url, headers=headers, timeout=_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()

    clone_url = f"https://github.com/{repo_full}"

    return GitHubIssue(
        number=data["number"],
        title=data["title"],
        body=data.get("body") or "",
        labels=[lbl["name"] for lbl in data.get("labels", [])],
        state=data["state"],
        html_url=data["html_url"],
        repo_url=clone_url,
        author=data.get("user", {}).get("login", "unknown"),
    )


def issue_to_question(issue: GitHubIssue) -> str:
    """
    Synthesise a natural-language search query from an issue.
    Strips GitHub checklist noise and excessive whitespace.
    """
    # Remove markdown checklist items (- [x] / - [ ])
    body = re.sub(r"- \[[ xX]\] .*", "", issue.body)
    # Collapse blank lines
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    # Trim to 2000 chars so search tokenisation stays fast
    if len(body) > 2000:
        body = body[:2000] + "\n…[truncated]"

    parts = [f"Issue #{issue.number}: {issue.title}"]
    if issue.labels:
        parts.append(f"Labels: {', '.join(issue.labels)}")
    if body:
        parts.append(body)
    return "\n\n".join(parts)

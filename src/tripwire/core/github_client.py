"""Thin httpx wrapper around the GitHub REST API.

Used by `tripwire init` (v0.7.6 item A) to auto-create the
project-tracking repo and resolve auth without shelling out to the
`gh` CLI. Keeping this self-contained means `gh` stays an optional
prerequisite (only needed for v0.7.5's draft PRs).

The wrapper is intentionally narrow: only the four operations init
needs (`repo_exists`, `create_repo`, `resolve_token`, plus
`_authenticated_owner` to decide between the user / orgs endpoints).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

GITHUB_API = "https://api.github.com"

# Path is module-level so tests can monkeypatch it without touching
# the real user's gh config.
_GH_HOSTS_PATH = Path.home() / ".config" / "gh" / "hosts.yml"


class GitHubAuthError(RuntimeError):
    """Raised when the GitHub API returns 401/403 — token missing or
    insufficient. Distinct from generic HTTP errors so the init flow
    can show a precise "set GITHUB_TOKEN / GH_TOKEN" message."""


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def repo_exists(owner: str, repo: str, *, token: str) -> bool:
    """Return True if the repo exists on GitHub, False if 404.

    Raises `GitHubAuthError` on 401/403 so the caller can fail-fast
    with a clear "set GITHUB_TOKEN" error rather than silently
    treating an auth failure as "repo doesn't exist".
    """
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=_headers(token),
        timeout=10.0,
    )
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    if response.status_code in (401, 403):
        raise GitHubAuthError(
            f"GitHub API returned {response.status_code} checking "
            f"{owner}/{repo}. The token may be missing or lacks repo scope."
        )
    response.raise_for_status()
    return False  # unreachable; raise_for_status() raises


def create_repo(
    owner: str,
    repo: str,
    *,
    private: bool,
    description: str,
    token: str,
) -> dict[str, Any]:
    """Create a new GitHub repo under `owner` and return the API response.

    Picks the user vs org endpoint by comparing `owner` to the
    authenticated user's login. Org-owned creates require admin on the
    org; that error surfaces as a 403 / `GitHubAuthError`.
    """
    auth_owner = _authenticated_owner(token)
    if auth_owner is not None and owner == auth_owner:
        url = f"{GITHUB_API}/user/repos"
    else:
        url = f"{GITHUB_API}/orgs/{owner}/repos"

    response = httpx.post(
        url,
        headers=_headers(token),
        json={
            "name": repo,
            "private": private,
            "auto_init": False,
            "description": description,
        },
        timeout=15.0,
    )
    if response.status_code in (401, 403):
        raise GitHubAuthError(
            f"GitHub API returned {response.status_code} creating "
            f"{owner}/{repo}. Check that the token has `repo` scope and "
            f"(for org repos) admin access on `{owner}`."
        )
    response.raise_for_status()
    return response.json()


def resolve_token() -> str | None:
    """Resolve a GitHub token, in priority order.

    1. ``GITHUB_TOKEN`` env var.
    2. ``GH_TOKEN`` env var.
    3. ``oauth_token`` field in ``~/.config/gh/hosts.yml`` (`gh auth login`
       writes this; reading it is a UX win even though we don't shell
       out to `gh`).

    Returns None if every source misses or `hosts.yml` is malformed.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    token = os.environ.get("GH_TOKEN")
    if token:
        return token
    return _read_token_from_gh_hosts()


def _read_token_from_gh_hosts() -> str | None:
    """Best-effort read of `oauth_token` from ~/.config/gh/hosts.yml.

    Defensive: schema can vary across `gh` versions, so any parse error
    or unexpected shape returns None and lets the caller fall through
    to the "set GITHUB_TOKEN" error.
    """
    if not _GH_HOSTS_PATH.is_file():
        return None
    try:
        data = yaml.safe_load(_GH_HOSTS_PATH.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    host = data.get("github.com")
    if not isinstance(host, dict):
        return None
    token = host.get("oauth_token")
    return token if isinstance(token, str) and token else None


def _authenticated_owner(token: str) -> str | None:
    """Return the `login` of the authenticated user, or None on failure.

    Used by `create_repo` to pick the user vs org endpoint. Failure
    here just falls back to the org endpoint, which itself will
    report a clear error if the owner is wrong.
    """
    try:
        response = httpx.get(
            f"{GITHUB_API}/user",
            headers=_headers(token),
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    payload = response.json()
    login = payload.get("login")
    return login if isinstance(login, str) else None

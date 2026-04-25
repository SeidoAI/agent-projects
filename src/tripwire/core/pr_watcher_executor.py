"""Side-effect executor for the PR watcher.

Splits the watcher's policy from its side effects: the watcher
returns :class:`WatcherAction` records, this module turns them into
session.yaml writebacks, plan.md follow-up injections, GH PR
comments, and ``tripwire session pause / spawn --resume`` invocations.

The httpx call to the GitHub comments endpoint lives in this module
(rather than the watcher) so the watcher stays a pure function of
its inputs and tests don't have to mock out network just to exercise
the policy.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from tripwire.core.pr_watcher import (
    CommentOnPR,
    InjectFollowUp,
    ReengageAgent,
    TransitionStatus,
    WatcherAction,
)
from tripwire.core.session_store import load_session, save_session

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


_FOLLOW_UP_SEPARATOR = "\n\n<!-- watcher:tripwire={tid} ts={ts} -->\n"


def post_pr_comment(repo: str, pr_number: int, body: str, *, token: str) -> None:
    """POST a comment on the supplied PR via the GitHub Issues API.

    The Issues comments endpoint accepts a PR number transparently
    (PRs are issues with extra fields). Used over the Reviews API
    because review comments require commit/file refs we don't carry.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = httpx.post(
        f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
        headers=headers,
        json={"body": body},
        timeout=15.0,
    )
    response.raise_for_status()


def fetch_pr_state(repo_tuple: tuple[str, str], pr_number: int, *, token: str | None):
    """Fetch a PR's state via the GitHub PRs API.

    Wrapped here (rather than in :mod:`pr_watcher`) so the watcher
    stays a pure function with an injectable fetcher.
    """
    from tripwire.core.pr_watcher import PRState

    owner, repo = repo_tuple
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers=headers,
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    return PRState(
        number=payload["number"],
        state=payload["state"],
        merged=bool(payload.get("merged")),
        head_branch=payload.get("head", {}).get("ref", ""),
        title=payload.get("title", ""),
        url=payload.get("html_url", ""),
    )


def fetch_pr_files(
    repo_tuple: tuple[str, str], pr_number: int, *, token: str | None
) -> list[dict[str, Any]]:
    """Fetch a PR's file list via the GitHub PRs API."""
    owner, repo = repo_tuple
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        response = httpx.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=15.0,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list) or not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


class WatcherActionExecutor:
    """Apply :class:`WatcherAction` records to disk + GitHub + the agent."""

    def __init__(self, project_dir: Path, token: str | None) -> None:
        self.project_dir = project_dir
        self.token = token

    def execute(self, action: WatcherAction) -> None:
        if isinstance(action, TransitionStatus):
            self._do_transition(action)
        elif isinstance(action, InjectFollowUp):
            self._do_inject(action)
        elif isinstance(action, CommentOnPR):
            self._do_comment(action)
        elif isinstance(action, ReengageAgent):
            self._do_reengage(action)
        else:  # pragma: no cover
            logger.warning("WatcherActionExecutor: unknown action %r", action)

    # --- handlers -------------------------------------------------------

    def _do_transition(self, action: TransitionStatus) -> None:
        try:
            session = load_session(self.project_dir, action.session_id)
        except FileNotFoundError:
            logger.warning(
                "watcher: cannot transition '%s' — session file not found",
                action.session_id,
            )
            return
        session.status = action.new_status
        session.updated_at = datetime.now(tz=timezone.utc)
        save_session(self.project_dir, session)

    def _do_inject(self, action: InjectFollowUp) -> None:
        plan_path = self.project_dir / "sessions" / action.session_id / "plan.md"
        if not plan_path.exists():
            logger.warning(
                "watcher: plan.md missing for session '%s'", action.session_id
            )
            return
        existing = plan_path.read_text(encoding="utf-8")
        marker = f"watcher:tripwire={action.tripwire_id}"
        if marker in existing:
            return
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sep = _FOLLOW_UP_SEPARATOR.format(tid=action.tripwire_id, ts=ts)
        plan_path.write_text(
            existing.rstrip() + sep + action.message.rstrip() + "\n",
            encoding="utf-8",
        )

    def _do_comment(self, action: CommentOnPR) -> None:
        if self.token is None:
            logger.warning(
                "watcher: skipping CommentOnPR (no token) for %s#%d",
                action.repo,
                action.pr_number,
            )
            return
        try:
            post_pr_comment(
                action.repo,
                action.pr_number,
                action.body,
                token=self.token,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "watcher: failed to post comment on %s#%d: %s",
                action.repo,
                action.pr_number,
                exc,
            )

    def _do_reengage(self, action: ReengageAgent) -> None:
        # Pause first, then spawn --resume. Subprocess to keep this
        # decoupled from the running daemon — the spawned agent is
        # then owned by its own process group.
        for argv in (
            [
                "tripwire",
                "session",
                "pause",
                action.session_id,
                "--project-dir",
                str(self.project_dir),
            ],
            [
                "tripwire",
                "session",
                "spawn",
                action.session_id,
                "--resume",
                "--project-dir",
                str(self.project_dir),
            ],
        ):
            try:
                subprocess.run(argv, check=False, timeout=120)
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                logger.warning("watcher: re-engage step %r failed: %s", argv, exc)


__all__ = [
    "WatcherActionExecutor",
    "fetch_pr_files",
    "fetch_pr_state",
    "post_pr_comment",
]

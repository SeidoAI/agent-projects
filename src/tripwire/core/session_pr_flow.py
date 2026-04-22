"""Dual-PR orchestration for tripwire session complete.

Iterates session.runtime_state.worktrees, commits+pushes when
appropriate, opens a PR per repo, cross-links the sibling PR URLs,
and applies the session's merge_policy. Partial-failure-safe:
re-running detects existing PRs on the same branch and skips to
cross-linking.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tripwire.models.session import AgentSession


class PrFlowError(Exception):
    """Raised when the PR flow cannot proceed cleanly (e.g. dirty
    worktree with commit_on_complete='manual')."""


@dataclass
class PrFlowResult:
    pr_urls: list[str] = field(default_factory=list)
    skipped_repos: list[str] = field(default_factory=list)
    committed_repos: list[str] = field(default_factory=list)


def _run_git(
    args: list[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _is_dirty(worktree: Path) -> bool:
    r = _run_git(["status", "--porcelain"], cwd=worktree, check=False)
    return bool(r.stdout.strip())


def _branch_has_new_commits(worktree: Path, base: str) -> bool:
    r = _run_git(
        ["rev-list", "--count", f"{base}..HEAD"],
        cwd=worktree, check=False,
    )
    if r.returncode != 0:
        return False
    try:
        return int(r.stdout.strip()) > 0
    except ValueError:
        return False


def _find_existing_pr(repo: str, branch: str) -> str | None:
    r = subprocess.run(
        [
            "gh", "pr", "list", "--repo", repo,
            "--head", branch, "--json", "url",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return None
    try:
        items = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not items:
        return None
    return items[0].get("url")


def _render_commit_message(session: AgentSession, repo: str) -> str:
    return (
        f"chore(tripwire): session {session.id} — {repo}\n\n"
        f"Automated commit by tripwire session complete."
    )


def _render_pr_title(session: AgentSession, repo: str) -> str:
    return f"feat({session.id}): {session.name} [{repo}]"


def _render_pr_body(
    session: AgentSession, repo: str, sibling_urls: list[str]
) -> str:
    lines = [
        f"Session: `{session.id}`",
        f"Name: {session.name}",
        f"Issues: {', '.join(session.issues) or '—'}",
        "",
        "Automated by `tripwire session complete`.",
    ]
    if sibling_urls:
        lines += ["", "## Sibling PRs"]
        lines += [f"- {u}" for u in sibling_urls]
    return "\n".join(lines)


def run_pr_flow(
    *,
    session: AgentSession,
    project_dir: Path,
    skip_push: bool = False,
) -> PrFlowResult:
    """For each worktree with new commits vs base_branch, create or
    reuse a PR. Caller is responsible for invoking this only when
    session_complete's gates have passed.
    """
    result = PrFlowResult()

    base_branch_by_repo = {rb.repo: rb.base_branch for rb in session.repos}

    for wt in session.runtime_state.worktrees:
        wt_path = Path(wt.worktree_path)
        repo = wt.repo
        branch = wt.branch
        base = base_branch_by_repo.get(repo, "main")

        if _is_dirty(wt_path):
            if session.commit_on_complete == "auto":
                _run_git(["add", "-A"], cwd=wt_path)
                _run_git(
                    [
                        "-c", "user.name=tripwire",
                        "-c", "user.email=tripwire@local",
                        "commit", "-m", _render_commit_message(session, repo),
                    ],
                    cwd=wt_path,
                )
                result.committed_repos.append(repo)
            else:
                raise PrFlowError(
                    f"Worktree {wt_path} has uncommitted changes and "
                    f"session.commit_on_complete is 'manual'. "
                    f"Commit or discard, then rerun."
                )

        if not _branch_has_new_commits(wt_path, base):
            result.skipped_repos.append(repo)
            continue

        if not skip_push:
            _run_git(["push", "origin", branch], cwd=wt_path)

        existing_url = _find_existing_pr(repo, branch)
        if existing_url is None:
            pr_create = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--repo", repo,
                    "--base", base,
                    "--head", branch,
                    "--title", _render_pr_title(session, repo),
                    "--body", _render_pr_body(
                        session, repo, sibling_urls=[]
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            url = (pr_create.stdout or "").strip().splitlines()[-1]
        else:
            url = existing_url

        result.pr_urls.append(url)

    # Second pass: cross-link sibling URLs into each PR body.
    if len(result.pr_urls) > 1:
        for i, url in enumerate(result.pr_urls):
            siblings = [u for j, u in enumerate(result.pr_urls) if j != i]
            new_body = _render_pr_body(
                session=session,
                repo="",
                sibling_urls=siblings,
            )
            subprocess.run(
                ["gh", "pr", "edit", url, "--body", new_body],
                check=False,
            )

    # Merge policy
    policy = session.merge_policy
    if policy == "auto_merge_on_green":
        for url in result.pr_urls:
            subprocess.run(
                ["gh", "pr", "merge", "--auto", "--squash", url],
                check=False,
            )
    elif policy == "auto_merge_immediate":
        for url in result.pr_urls:
            subprocess.run(
                ["gh", "pr", "merge", "--squash", url],
                check=False,
            )
    # await_review: no-op

    return result

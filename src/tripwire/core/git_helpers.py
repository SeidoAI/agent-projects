"""Git helper functions for worktree and branch operations."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def branch_exists(repo_path: Path, branch_name: str) -> bool:
    """Check whether a branch exists in the given repo."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "rev-parse",
            "--verify",
            f"refs/heads/{branch_name}",
        ],
        capture_output=True,
    )
    return result.returncode == 0


def local_branches_with_prefix(repo_dir: Path, prefix: str) -> list[str]:
    """Return local branch names matching ``refs/heads/<prefix>``.

    Empty list on any failure (not a git repo, no matching branches,
    git not installed). Read-only — never mutates the repo. Used by
    the no-orphan-proj-branches lint and any other read-only branch
    discovery; the §3 ("validators are passive") + §9 ("CLI codifies
    repetitive procedure") promise requires this kind of subprocess
    plumbing to live in helpers, not inline in validator code.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "for-each-ref",
            "--format=%(refname:short)",
            f"refs/heads/{prefix}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def branch_commit_count_ahead(repo_dir: Path, branch: str, base: str) -> int | None:
    """Return commits in ``branch`` not in ``base`` (read-only).

    ``None`` on any failure — caller decides what "we can't tell" means.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "rev-list",
            f"{base}..{branch}",
            "--count",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return None


def worktree_path_for_session(clone_path: Path, session_slug: str) -> Path:
    """Compute the worktree path for a session.

    Convention: ``<repo-parent>/worktree-<repo-name>-<session-slug>/``
    The ``worktree-`` prefix mirrors the project/workspace prefix convention
    so a glance at any directory tells you what it is.
    """
    clone_resolved = clone_path.resolve()
    return clone_resolved.parent / f"worktree-{clone_resolved.name}-{session_slug}"


def worktree_add(
    clone_path: Path,
    wt_path: Path,
    branch: str,
    base_ref: str,
) -> None:
    """Create a git worktree with a new branch."""
    subprocess.run(
        [
            "git",
            "-C",
            str(clone_path),
            "worktree",
            "add",
            str(wt_path),
            "-b",
            branch,
            base_ref,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_attach(clone_path: Path, wt_path: Path, branch: str) -> None:
    """Attach an existing local branch as a new worktree at ``wt_path``.

    Unlike :func:`worktree_add`, this does NOT create a new branch — the
    branch must already exist in ``clone_path``. Used by ``--resume``
    recreation (v0.12.1) when ``tripwire session complete`` removed the
    worktree but left the local branch behind, so the resumed session
    picks up where the agent left off.
    """
    subprocess.run(
        [
            "git",
            "-C",
            str(clone_path),
            "worktree",
            "add",
            str(wt_path),
            branch,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_remove(clone_path: Path, wt_path: Path) -> None:
    """Remove a git worktree. No-op if it doesn't exist."""
    if not wt_path.exists():
        return
    subprocess.run(
        ["git", "-C", str(clone_path), "worktree", "remove", "--force", str(wt_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_prune(clone_path: Path) -> None:
    """Prune stale worktree references."""
    subprocess.run(
        ["git", "-C", str(clone_path), "worktree", "prune"],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_list(clone_path: Path) -> list[Path]:
    """List all worktree paths for a repo."""
    result = subprocess.run(
        ["git", "-C", str(clone_path), "worktree", "list", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]))
    return paths


def worktree_is_dirty(wt_path: Path) -> bool:
    """Check if a worktree has uncommitted changes."""
    result = subprocess.run(
        ["git", "-C", str(wt_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


class MainTreeUnavailable(RuntimeError):
    """Raised when `origin/main` can't be read.

    Either the directory isn't a git repo, no `origin` remote exists,
    or `origin/main` isn't a known ref. Distinct from the "main is
    empty" case (an empty repo would still return zero paths cleanly).
    """


def list_paths_on_main(repo_dir: Path) -> set[str]:
    """Return every file path tracked on ``origin/main`` of ``repo_dir``.

    Used by the ``done_implies_issue_artifacts_on_main`` validator rule. One
    `git ls-tree -r --name-only origin/main` call covers the whole repo
    — way cheaper than ``git show origin/main:<path>`` per artifact.

    The caller is expected to call ``git fetch origin`` before this if
    they want a fresh view; we deliberately don't fetch from inside the
    validator (network on every `tripwire validate` call would be
    unfriendly).

    Raises :class:`MainTreeUnavailable` if origin/main isn't readable.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-tree", "-r", "--name-only", "origin/main"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MainTreeUnavailable(
            (result.stderr or "git ls-tree origin/main failed").strip()
        )
    return {line for line in result.stdout.splitlines() if line}


class RebaseConflict(RuntimeError):
    """Raised when a rebase produces conflicts that the helper can't auto-resolve.

    The caller is expected to surface the message to the user (PM or
    agent) and roll back any in-progress state mutation. The conflicting
    rebase is left aborted (`git rebase --abort` is run before raising)
    so the worktree returns to a clean state on the original branch tip.
    """


def fetch_origin(repo_path: Path) -> None:
    """`git fetch origin` for the repo at `repo_path`.

    Quiet, no-prune. Used before a rebase to ensure the remote-tracking
    branch is current. Raises ``subprocess.CalledProcessError`` if the
    fetch itself fails (network, auth, no remote, etc.) — callers
    should treat that as a transition-blocking error.
    """
    subprocess.run(
        ["git", "-C", str(repo_path), "fetch", "origin", "--quiet"],
        check=True,
        capture_output=True,
        text=True,
    )


def rebase_branch_onto(worktree_path: Path, upstream: str) -> None:
    """Rebase the current branch in ``worktree_path`` onto ``upstream``.

    On success: the worktree's HEAD now sits on top of ``upstream``.
    On conflict: the rebase is aborted (so the worktree is restored to
    its pre-rebase HEAD) and ``RebaseConflict`` is raised, carrying the
    conflict summary in its message. Callers should surface this to the
    user and roll back any pre-rebase state mutations.

    Used by ``session_transition_cmd`` on transitions to ``in_review`` to
    keep PT branches up-to-date with main, closing the multi-session-
    wave staleness trap (kb-pivot wave 1 incident).
    """
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "rebase", upstream],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    # Conflict or other rebase failure — abort cleanly and surface.
    subprocess.run(
        ["git", "-C", str(worktree_path), "rebase", "--abort"],
        check=False,
        capture_output=True,
        text=True,
    )
    detail = (result.stderr or result.stdout or "rebase failed").strip()
    raise RebaseConflict(
        f"`git rebase {upstream}` failed in {worktree_path}:\n{detail}"
    )


def commit_and_push_file(
    repo_path: Path,
    file_path: Path,
    message: str,
) -> str | None:
    """Stage, commit, and push a single file inside ``repo_path``.

    Returns the new commit SHA, or ``None`` when ``file_path`` has no
    diff vs HEAD (nothing to commit). Commit failures raise
    ``subprocess.CalledProcessError`` so the caller sees pre-commit
    hook rejections — those are real problems that need surfacing.
    Push failures (no upstream, auth, network) log a WARNING with the
    local SHA and return normally; the commit is durable on disk and
    can be pushed by hand.

    Used post-spawn to land ``runtime_state.claude_session_id`` on the
    PT branch so PR squash-merge preserves it. Without this commit the
    runtime field lives only as an uncommitted edit in the main checkout
    and gets wiped the next time main pulls.
    """
    # ``git status --porcelain`` covers both tracked diffs AND untracked
    # files; ``git diff HEAD`` misses the latter, which would silently
    # no-op every fresh ``session.yaml`` write.
    status = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--porcelain", "--", str(file_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        return None

    subprocess.run(
        ["git", "-C", str(repo_path), "add", "--", str(file_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", message, "--", str(file_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    sha_result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    sha = sha_result.stdout.strip()

    push_result = subprocess.run(
        ["git", "-C", str(repo_path), "push"],
        capture_output=True,
        text=True,
    )
    if push_result.returncode != 0:
        log.warning(
            "git_helpers.commit_and_push_file: committed %s in %s as %s "
            "but push failed: %s. Push manually with "
            "`git -C %s push`.",
            file_path.name,
            repo_path,
            sha,
            (push_result.stderr or push_result.stdout).strip(),
            repo_path,
        )

    return sha

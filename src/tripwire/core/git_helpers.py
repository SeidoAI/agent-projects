"""Git helper functions for worktree and branch operations."""

from __future__ import annotations

import subprocess
from pathlib import Path


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


def worktree_path_for_session(clone_path: Path, session_slug: str) -> Path:
    """Compute the worktree path for a session.

    Convention: ``<repo-parent>/<repo-name>-wt-<session-slug>/``
    """
    clone_resolved = clone_path.resolve()
    return clone_resolved.parent / f"{clone_resolved.name}-wt-{session_slug}"


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

    Used by the ``done_implies_artifacts_on_main`` validator rule. One
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

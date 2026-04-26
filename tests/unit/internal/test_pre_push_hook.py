"""Tests for the pre-push hook installed at session-spawn time.

The hook lives at ``<worktree>/.git/hooks/pre-push`` and gates
``git push`` on the existence of a substantive ack marker for the
self-review tripwire on this session. Two opt-outs:

  * Per-call: ``tripwire session complete --no-tripwires`` writes an
    audit-log entry that the hook treats as bypass.
  * Per-project: ``tripwires.enabled: false`` in project.yaml — the
    hook checks the project config and short-circuits.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import yaml

from tripwire.runtimes.prep import install_pre_push_hook


def _project(project_dir: Path, *, enabled: bool = True) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    body: dict = {
        "name": "fixture",
        "key_prefix": "FIX",
        "base_branch": "main",
        "next_issue_number": 1,
        "next_session_number": 1,
        "phase": "scoping",
        "tripwires": {"enabled": enabled},
    }
    (project_dir / "project.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")


def _git_init(worktree: Path) -> None:
    worktree.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main", str(worktree)],
        check=True,
        capture_output=True,
    )


def test_install_writes_executable_hook(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    worktree = tmp_path / "wt"
    _project(project_dir)
    _git_init(worktree)

    install_pre_push_hook(
        worktree=worktree,
        project_dir=project_dir,
        session_id="fixture-1",
    )

    hook = worktree / ".git" / "hooks" / "pre-push"
    assert hook.is_file()
    mode = hook.stat().st_mode
    assert mode & stat.S_IXUSR, "hook should be executable"
    body = hook.read_text(encoding="utf-8")
    assert "fixture-1" in body
    assert "tripwires" in body.lower() or "tripwire" in body.lower()


def test_install_skipped_when_tripwires_disabled(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    worktree = tmp_path / "wt"
    _project(project_dir, enabled=False)
    _git_init(worktree)

    install_pre_push_hook(
        worktree=worktree,
        project_dir=project_dir,
        session_id="fixture-1",
    )

    hook = worktree / ".git" / "hooks" / "pre-push"
    assert not hook.exists()


def _run_hook(worktree: Path) -> subprocess.CompletedProcess:
    """Invoke the installed pre-push hook directly with empty stdin
    (the hook contract: stdin is `<local-ref> <local-sha> <remote-ref>
    <remote-sha>` lines; empty stdin = no refs to push)."""
    hook = worktree / ".git" / "hooks" / "pre-push"
    return subprocess.run(
        [str(hook), "origin", "<remote-url>"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        env={**os.environ},
        input="",
    )


def test_hook_blocks_without_ack(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    worktree = tmp_path / "wt"
    _project(project_dir)
    _git_init(worktree)
    install_pre_push_hook(
        worktree=worktree,
        project_dir=project_dir,
        session_id="fixture-1",
    )

    proc = _run_hook(worktree)
    assert proc.returncode != 0
    assert "tripwire" in proc.stderr.lower() or "ack" in proc.stderr.lower()


def test_hook_passes_with_substantive_ack(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    worktree = tmp_path / "wt"
    _project(project_dir)
    _git_init(worktree)
    install_pre_push_hook(
        worktree=worktree,
        project_dir=project_dir,
        session_id="fixture-1",
    )

    marker = (
        project_dir / ".tripwire" / "acks" / "self-review-fixture-1.json"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "tripwire_id": "self-review",
                "session_id": "fixture-1",
                "fix_commits": ["abc123"],
                "declared_no_findings": False,
            }
        ),
        encoding="utf-8",
    )

    proc = _run_hook(worktree)
    assert proc.returncode == 0, proc.stderr


def test_hook_passes_with_bypass_audit_entry(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    worktree = tmp_path / "wt"
    _project(project_dir)
    _git_init(worktree)
    install_pre_push_hook(
        worktree=worktree,
        project_dir=project_dir,
        session_id="fixture-1",
    )

    audit_dir = project_dir / ".tripwire" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "tripwire_bypass.log").write_text(
        "2026-04-26T00:00:00+00:00\tsession.complete\tfixture-1\t--no-tripwires\n",
        encoding="utf-8",
    )

    proc = _run_hook(worktree)
    assert proc.returncode == 0, proc.stderr


def test_hook_skipped_when_project_disabled_via_existing_install(
    tmp_path: Path,
) -> None:
    """If a project flips `tripwires.enabled: false` AFTER spawn, the
    already-installed hook still short-circuits because it re-reads the
    project config at run time."""
    project_dir = tmp_path / "proj"
    worktree = tmp_path / "wt"
    _project(project_dir)
    _git_init(worktree)
    install_pre_push_hook(
        worktree=worktree,
        project_dir=project_dir,
        session_id="fixture-1",
    )
    # Flip the flag post-install.
    _project(project_dir, enabled=False)

    proc = _run_hook(worktree)
    assert proc.returncode == 0, proc.stderr

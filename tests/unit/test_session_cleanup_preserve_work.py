"""Tests for PM-handoff #6 D2 — ``tripwire session cleanup --preserve-work``.

The default ``cleanup`` path rips out worktrees + plan.md + artifacts;
``--preserve-work`` is the escape hatch when an operator wants to free
a stuck runtime *without* losing in-progress work. Spec:

- Do NOT delete the session's worktree directories.
- Do NOT delete ``plan.md`` or ``artifacts/``.
- DO kill any runtime processes.
- DO clean up ``.tripwire/locks/*.lock`` for this session.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        cwd=path,
        check=True,
    )


def _add_worktree(clone: Path, name: str, branch: str) -> Path:
    wt = clone.parent / name
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", "-b", branch, str(wt)],
        check=True,
    )
    return wt


def _configure_project_repos(project_dir: Path, slug: str, local: Path) -> None:
    current = yaml.safe_load((project_dir / "project.yaml").read_text(encoding="utf-8"))
    current["repos"] = {slug: {"local": str(local)}}
    (project_dir / "project.yaml").write_text(yaml.safe_dump(current))


class TestCleanupPreserveWork:
    def test_preserve_work_keeps_worktree_on_disk(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        """The whole point of the flag — the worktree directory must
        survive. Compare against the default-cleanup test in
        test_session_cleanup_orphans.py where the same scenario removes
        the worktree."""
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        wt = _add_worktree(clone, "code-wt-s1", "feat/s1")
        assert wt.is_dir()

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            plan=True,
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(clone),
                        "worktree_path": str(wt),
                        "branch": "feat/s1",
                    }
                ]
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "cleanup",
                "s1",
                "--preserve-work",
                "--project-dir",
                str(tmp_path_project),
            ],
        )

        assert result.exit_code == 0, result.output
        # Worktree must still be on disk.
        assert wt.is_dir(), "worktree should survive --preserve-work"
        # Output should call out preservation explicitly so operators
        # don't get confused about why nothing got removed.
        assert "Preserved work" in result.output

    def test_preserve_work_keeps_plan_md_and_artifacts(
        self, tmp_path_project, save_test_session
    ):
        """``plan.md`` and ``artifacts/`` under the session's
        per-issue/session directory must survive."""
        from tripwire.core import paths

        save_test_session(tmp_path_project, "s1", status="completed", plan=True)

        plan = paths.session_plan_path(tmp_path_project, "s1")
        assert plan.is_file()
        artifacts_dir = paths.session_artifacts_dir(tmp_path_project, "s1")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        side_artifact = artifacts_dir / "self-review.md"
        side_artifact.write_text("# self-review\nin progress\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "cleanup",
                "s1",
                "--preserve-work",
                "--project-dir",
                str(tmp_path_project),
            ],
        )

        assert result.exit_code == 0, result.output
        assert plan.is_file(), "plan.md must survive --preserve-work"
        assert side_artifact.is_file(), "artifacts/ must survive --preserve-work"

    def test_preserve_work_clears_session_locks(
        self, tmp_path_project, save_test_session
    ):
        """``.tripwire/locks/<sid>.lock`` (and ``*-<sid>.lock``) must
        be removed — the runtime process is dead, so the lock is stale
        by definition."""
        save_test_session(tmp_path_project, "s1", status="completed", plan=True)

        locks_dir = tmp_path_project / ".tripwire" / "locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        own_lock = locks_dir / "s1.lock"
        own_lock.write_text("pid=12345\n", encoding="utf-8")
        gated_lock = locks_dir / "spawn-s1.lock"
        gated_lock.write_text("pid=12346\n", encoding="utf-8")
        # An unrelated session's lock — must NOT be touched.
        other_lock = locks_dir / "other.lock"
        other_lock.write_text("pid=99999\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "cleanup",
                "s1",
                "--preserve-work",
                "--project-dir",
                str(tmp_path_project),
            ],
        )

        assert result.exit_code == 0, result.output
        assert not own_lock.exists()
        assert not gated_lock.exists()
        assert other_lock.exists(), "must not touch other sessions' locks"
        # Output reports lock count.
        assert "2 lock(s) cleared" in result.output

    def test_preserve_work_lock_dir_missing_is_noop(
        self, tmp_path_project, save_test_session
    ):
        """No ``.tripwire/locks/`` directory exists yet — must not
        crash; reports zero locks cleared."""
        save_test_session(tmp_path_project, "s1", status="completed", plan=True)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "cleanup",
                "s1",
                "--preserve-work",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "0 lock(s) cleared" in result.output

    def test_default_cleanup_still_removes_worktree(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        """Regression guard — the historic full-cleanup path is
        unchanged. Without ``--preserve-work`` the worktree is
        removed."""
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        wt = _add_worktree(clone, "code-wt-s1", "feat/s1")

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            plan=True,
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(clone),
                        "worktree_path": str(wt),
                        "branch": "feat/s1",
                    }
                ]
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        # Default path strips the worktree — preserve-work would have
        # left it.
        assert not wt.exists()
        assert "Preserved work" not in result.output

    def test_preserve_work_help_flag_visible(self):
        """`tripwire session cleanup --help` advertises the flag so
        operators discover it."""
        runner = CliRunner()
        result = runner.invoke(session_cmd, ["cleanup", "--help"])
        assert result.exit_code == 0
        assert "--preserve-work" in result.output

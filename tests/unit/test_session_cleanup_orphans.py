"""Tests for I6 — `tripwire session cleanup` scans clones for
orphan worktrees that aren't recorded in runtime_state.

Before I6, cleanup iterated only `session.runtime_state.worktrees`.
Any worktree on disk matching the tripwire naming convention
(``<clone-name>-wt-<session-id>``) that wasn't in runtime_state —
e.g. from an interrupted spawn, or from a pre-I5 dry-run — was
left behind. PMs had to ``git worktree remove`` by hand.

After I6, cleanup also scans each known clone's parent directory
for orphan worktrees matching the session's naming suffix and
removes them (respecting --force for dirty ones).
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
    """Overwrite tmp_path_project's project.yaml so it includes the
    repo registry entry pointing at our test clone."""
    current = yaml.safe_load((project_dir / "project.yaml").read_text(encoding="utf-8"))
    current["repos"] = {slug: {"local": str(local)}}
    (project_dir / "project.yaml").write_text(yaml.safe_dump(current))


class TestOrphanWorktreeScan:
    def test_cleanup_removes_orphan_matching_session_id(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        # Orphan worktree with the tripwire-shape name, NOT recorded
        # in runtime_state.
        orphan = _add_worktree(clone, "code-wt-s1", "feat/s1")
        assert orphan.is_dir()

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            # NOTE: empty runtime_state — orphan was never recorded.
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert "Removed orphan" in result.output
        assert str(orphan) in result.output
        assert not orphan.exists()

    def test_cleanup_leaves_other_sessions_orphans(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        """Cleaning session A must not remove session B's orphan
        worktree — suffix match is per-session-id."""
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        orphan_a = _add_worktree(clone, "code-wt-session-a", "feat/a")
        orphan_b = _add_worktree(clone, "code-wt-session-b", "feat/b")

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(tmp_path_project, "session-a", status="completed")
        save_test_session(tmp_path_project, "session-b", status="completed")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "session-a", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert not orphan_a.exists()
        assert orphan_b.exists()

    def test_cleanup_skips_dirty_orphan_without_force(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        orphan = _add_worktree(clone, "code-wt-s1", "feat/s1")
        # Make it dirty — uncommitted file.
        (orphan / "dirty.txt").write_text("uncommitted\n")

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(tmp_path_project, "s1", status="completed")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert "Skipping orphan" in result.output
        assert "uncommitted changes" in result.output
        assert orphan.exists()  # preserved

    def test_cleanup_force_removes_dirty_orphan(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        orphan = _add_worktree(clone, "code-wt-s1", "feat/s1")
        (orphan / "dirty.txt").write_text("uncommitted\n")

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(tmp_path_project, "s1", status="completed")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "cleanup",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--force",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Removed orphan" in result.output
        assert not orphan.exists()

    def test_cleanup_does_not_touch_non_matching_dirs(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        """A sibling directory that doesn't match `*-wt-<session-id>`
        must not be touched — regression guard on the glob pattern."""
        clone = tmp_path / "code"
        clone.mkdir()
        _init_repo(clone)
        _add_worktree(clone, "code-wt-s1", "feat/s1")

        # An unrelated sibling directory (not a worktree at all).
        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        (unrelated / "marker.txt").write_text("dont touch me")

        _configure_project_repos(tmp_path_project, "SeidoAI/code", clone)
        save_test_session(tmp_path_project, "s1", status="completed")

        runner = CliRunner()
        runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert unrelated.is_dir()
        assert (unrelated / "marker.txt").read_text() == "dont touch me"

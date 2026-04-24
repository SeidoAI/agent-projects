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

    def test_orphan_scan_finds_project_tracking_worktree_not_in_runtime_state(
        self, tmp_path_project, save_test_session
    ):
        """v0.7.4: a project-tracking worktree that leaked — interrupted
        spawn, pre-runtime_state crash — lives at
        ``<project_dir>.parent/<project_dir>.name-wt-<sid>``. It's NOT
        under any registered code-repo clone, so the pre-v0.7.4
        orphan scan (which only iterated ``proj.repos.items()``) would
        have missed it. This test proves ``project_dir`` is now
        included as a scan root."""
        _init_repo(tmp_path_project)
        # Orphan project-tracking worktree: sibling of project_dir,
        # name matches the v0.7.4 convention, NOT in runtime_state.
        orphan = _add_worktree(
            tmp_path_project,
            f"{tmp_path_project.name}-wt-s1",
            "proj/s1",
        )
        assert orphan.is_dir()

        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            # Empty runtime_state — orphan was never recorded.
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

    def test_cleanup_removes_both_code_and_project_tracking_worktrees(
        self, tmp_path, tmp_path_project
    ):
        """v0.7.4: a session may own BOTH a code worktree and a
        project-tracking worktree (recorded in runtime_state). Cleanup
        must iterate both and remove them together — not stop after
        the first."""
        from tripwire.core.session_store import save_session
        from tripwire.models import AgentSession
        from tripwire.models.session import RuntimeState, WorktreeEntry

        code_clone = tmp_path / "code"
        code_clone.mkdir()
        _init_repo(code_clone)
        code_wt = _add_worktree(code_clone, "code-wt-s1", "feat/s1")

        # Project-tracking repo worktree — different clone entirely.
        proj_clone = tmp_path / "proj-tracking"
        proj_clone.mkdir()
        _init_repo(proj_clone)
        proj_wt = _add_worktree(proj_clone, "proj-tracking-wt-s1", "proj/s1")

        _configure_project_repos(tmp_path_project, "SeidoAI/code", code_clone)

        # Persist a session whose runtime_state records both worktrees.
        save_session(
            tmp_path_project,
            AgentSession.model_validate(
                {
                    "id": "s1",
                    "name": "Test session",
                    "agent": "backend-coder",
                    "issues": [],
                    "repos": [],
                    "status": "completed",
                    "runtime_state": RuntimeState(
                        worktrees=[
                            WorktreeEntry(
                                repo="SeidoAI/code",
                                clone_path=str(code_clone),
                                worktree_path=str(code_wt),
                                branch="feat/s1",
                            ),
                            WorktreeEntry(
                                repo="proj-tracking",
                                clone_path=str(proj_clone),
                                worktree_path=str(proj_wt),
                                branch="proj/s1",
                            ),
                        ]
                    ).model_dump(),
                }
            ),
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        # Content assertion: BOTH worktrees are gone from disk.
        assert not code_wt.exists(), f"{code_wt} should have been removed"
        assert not proj_wt.exists(), f"{proj_wt} should have been removed"

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

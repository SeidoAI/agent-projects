"""Tests for `tripwire migrate templates` — v0.10.0 layout migration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.main import cli

runner = CliRunner()


def _make_flat_layout_project(root: Path) -> Path:
    """Build a pre-v0.10.0 flat-layout project at *root*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        "name: flat\nkey_prefix: FLT\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    for d in (
        "agents",
        "enums",
        "issue_templates",
        "session_templates",
        "comment_templates",
        "orchestration",
    ):
        (root / d).mkdir()
        (root / d / "marker.yaml").write_text(f"# flat {d}\n", encoding="utf-8")
    return root


def _git_init(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=project,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial flat layout"],
        cwd=project,
        check=True,
    )


class TestMigrateTemplates:
    def test_dry_run_makes_no_changes(self, tmp_path: Path):
        project = _make_flat_layout_project(tmp_path / "proj")
        result = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(project), "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "would move: agents/" in result.output
        assert "dry run" in result.output
        # Nothing actually moved.
        assert (project / "agents").is_dir()
        assert not (project / "templates" / "agents").exists()

    def test_non_git_project_uses_shutil_move(self, tmp_path: Path):
        project = _make_flat_layout_project(tmp_path / "proj")
        result = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        # Each flat-layout dir gone, canonical present with the marker file.
        for src, dest in (
            ("agents", "templates/agents"),
            ("enums", "templates/enums"),
            ("issue_templates", "templates/issues"),
            ("session_templates", "templates/sessions"),
            ("comment_templates", "templates/comments"),
            ("orchestration", "templates/orchestration"),
        ):
            assert not (project / src).exists(), f"{src}/ should be moved"
            assert (project / dest / "marker.yaml").is_file(), (
                f"{dest}/marker.yaml should exist"
            )

    def test_git_repo_uses_git_mv(self, tmp_path: Path):
        project = _make_flat_layout_project(tmp_path / "proj")
        _git_init(project)
        result = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        # Git tracks the rename. `git status -s` shows R lines.
        status = subprocess.run(
            ["git", "status", "-s"],
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
        )
        # Some renames may show as A+D depending on git version + similarity
        # threshold; either way, the canonical path is staged and the
        # flat-layout one is gone.
        assert "templates/agents/marker.yaml" in status.stdout

    def test_idempotent_second_run_is_noop(self, tmp_path: Path):
        project = _make_flat_layout_project(tmp_path / "proj")
        first = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(project)]
        )
        assert first.exit_code == 0
        second = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(project)]
        )
        assert second.exit_code == 0
        assert "Nothing to migrate" in second.output or "Skipped" in second.output

    def test_collision_with_canonical_dir_aborts(self, tmp_path: Path):
        project = _make_flat_layout_project(tmp_path / "proj")
        # Pre-create the canonical dir alongside the flat-layout one.
        (project / "templates").mkdir()
        (project / "templates" / "agents").mkdir(parents=True)
        (project / "templates" / "agents" / "preexisting.yaml").write_text(
            "# foreign\n"
        )
        result = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(project)]
        )
        assert result.exit_code != 0
        assert "destination already exists" in result.output

    def test_non_project_dir_aborts(self, tmp_path: Path):
        not_a_project = tmp_path / "random"
        not_a_project.mkdir()
        result = runner.invoke(
            cli, ["migrate", "templates", "--project-dir", str(not_a_project)]
        )
        assert result.exit_code != 0
        assert "doesn't look like a tripwire project" in result.output

    def test_help_lists_migrations(self):
        result = runner.invoke(cli, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "templates" in result.output

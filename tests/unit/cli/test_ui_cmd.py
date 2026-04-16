"""Tests for keel.cli.ui — the `keel ui` subcommand."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from keel.cli.main import cli

runner = CliRunner()


class TestUiHelp:
    def test_help_shows_all_flags(self):
        result = runner.invoke(cli, ["ui", "--help"])
        assert result.exit_code == 0
        assert "--project-dir" in result.output
        assert "--port" in result.output
        assert "--no-browser" in result.output
        assert "--dev" in result.output


class TestGracefulDegradation:
    def test_missing_fastapi_prints_helpful_message(self):
        with patch(
            "builtins.__import__",
            side_effect=_make_import_blocker("fastapi"),
        ):
            result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 1
        assert "full keel install" in result.output
        assert "pip install keel" in result.output

    def test_missing_uvicorn_prints_helpful_message(self):
        with patch(
            "builtins.__import__",
            side_effect=_make_import_blocker("uvicorn"),
        ):
            result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 1
        assert "full keel install" in result.output


class TestNoProjects:
    def test_no_projects_found_prints_hint(self, tmp_path: Path):
        with patch(
            "keel.ui.services.project_service.discover_projects",
            return_value=[],
        ):
            result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 1
        assert "No projects found" in result.output
        assert "keel init" in result.output


class TestStubBehaviour:
    def test_project_dir_flag_exits_cleanly(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        result = runner.invoke(cli, ["ui", "--project-dir", str(proj)])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output

    def test_port_flag_accepted(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        result = runner.invoke(
            cli, ["ui", "--project-dir", str(proj), "--port", "9999"]
        )
        assert result.exit_code == 0

    def test_no_browser_and_dev_flags_accepted(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        result = runner.invoke(
            cli,
            ["ui", "--project-dir", str(proj), "--no-browser", "--dev"],
        )
        assert result.exit_code == 0


def _make_import_blocker(blocked_module: str):
    """Return a side_effect function that blocks one module's import."""
    _real_import = builtins.__import__

    def _blocker(name, *args, **kwargs):
        if name == "keel.ui.server":
            exc = ModuleNotFoundError(
                f"No module named '{blocked_module}'"
            )
            exc.name = blocked_module
            raise exc
        return _real_import(name, *args, **kwargs)

    return _blocker

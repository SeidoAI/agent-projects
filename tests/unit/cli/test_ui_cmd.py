"""Tests for tripwire.cli.ui — the `tripwire ui` subcommand."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tripwire.cli.main import cli

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_project_index():
    """Clear the project_service module-level cache between tests.

    Without this, an earlier test's `_project_index` / `_pinned` / cache
    leaks into the next, causing assertions about discovered project_dirs
    to see stale entries.
    """
    from tripwire.ui.services.project_service import reload_project_index

    reload_project_index()
    yield
    reload_project_index()


@pytest.fixture(autouse=True)
def _stub_check_port():
    """Default the single-instance probe to "port is free" for every test.

    Without this, tests that don't explicitly care about the probe still
    hit whatever's actually on port 8000 of the host running the suite,
    which is non-hermetic. Tests that *do* care override the mock with
    their own ``patch("tripwire.cli.ui._check_port", ...)``; tests that
    exercise the probe itself live in test_ui_check_port.py (no stub).
    """
    with patch(
        "tripwire.cli.ui._check_port",
        return_value=("free", "http://127.0.0.1:8000"),
    ):
        yield


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
        assert "full tripwire install" in result.output
        assert "pip install tripwire-pm" in result.output

    def test_missing_uvicorn_prints_helpful_message(self):
        with patch(
            "builtins.__import__",
            side_effect=_make_import_blocker("uvicorn"),
        ):
            result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 1
        assert "full tripwire install" in result.output


class TestNoProjects:
    def test_no_projects_found_prints_hint_and_continues(
        self, tmp_path: Path, monkeypatch
    ):
        # The UI launches even with zero projects so the user sees the
        # empty state in the browser and can act from there. Exiting at
        # the CLI would leave them with nothing actionable in the
        # terminal. We patch start_server to short-circuit the actual
        # uvicorn run; the assertion is "we got past the empty-list
        # gate and reached server launch."
        monkeypatch.chdir(tmp_path)
        with (
            patch(
                "tripwire.ui.services.project_service.discover_projects",
                return_value=[],
            ),
            patch("tripwire.ui.server.start_server") as start_server,
        ):
            result = runner.invoke(cli, ["ui", "--no-browser"])
        assert result.exit_code == 0, result.output
        assert "No projects discovered" in result.output
        # Server still launched, with an empty project list.
        assert start_server.called
        kwargs = start_server.call_args.kwargs
        assert kwargs["project_dirs"] == []


class TestCwdAutodetect:
    """Running `tripwire ui` from inside a project picks that project."""

    def test_cwd_with_project_yaml_is_used(self, tmp_path: Path, monkeypatch):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        monkeypatch.chdir(proj)
        with patch(
            "tripwire.ui.services.project_service.discover_projects",
            return_value=[],
        ):
            with patch("tripwire.ui.server.start_server") as mock_start:
                result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["project_dirs"] == [proj.resolve()]

    def test_cwd_subdir_walks_up_to_project_root(self, tmp_path: Path, monkeypatch):
        proj = tmp_path / "proj"
        (proj / "issues" / "KUI-1").mkdir(parents=True)
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        monkeypatch.chdir(proj / "issues" / "KUI-1")
        with patch(
            "tripwire.ui.services.project_service.discover_projects",
            return_value=[],
        ):
            with patch("tripwire.ui.server.start_server") as mock_start:
                result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["project_dirs"] == [proj.resolve()]

    def test_explicit_project_dir_overrides_cwd(self, tmp_path: Path, monkeypatch):
        cwd_proj = tmp_path / "cwd_proj"
        cwd_proj.mkdir()
        (cwd_proj / "project.yaml").write_text(
            "name: cwd\nkey_prefix: CWD\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        explicit = tmp_path / "explicit"
        explicit.mkdir()
        (explicit / "project.yaml").write_text(
            "name: exp\nkey_prefix: EXP\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        monkeypatch.chdir(cwd_proj)
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui", "--project-dir", str(explicit)])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["project_dirs"] == [explicit.resolve()]


class TestServerLaunch:
    """Verify that the CLI wires through to ``start_server`` correctly."""

    def test_project_dir_flag_calls_start_server(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui", "--project-dir", str(proj)])
        assert result.exit_code == 0
        mock_start.assert_called_once()
        kwargs = mock_start.call_args.kwargs
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8000
        assert kwargs["dev_mode"] is False
        assert kwargs["open_browser"] is True

    def test_port_flag_forwarded(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(
                cli, ["ui", "--project-dir", str(proj), "--port", "9999"]
            )
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["port"] == 9999

    def test_no_browser_and_dev_flags_forwarded(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(
                cli,
                ["ui", "--project-dir", str(proj), "--no-browser", "--dev"],
            )
        assert result.exit_code == 0
        kwargs = mock_start.call_args.kwargs
        assert kwargs["dev_mode"] is True
        assert kwargs["open_browser"] is False


class TestPinBehavior:
    """v0.10.0: only `--project-dir` should pin discovery.

    Bare `tripwire ui` from inside a project (or anywhere with
    `project_roots` configured) should keep wider discovery active so
    the project switcher can list every known project.
    """

    def test_project_dir_pins(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui", "--project-dir", str(proj)])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["pin"] is True

    def test_bare_ui_from_project_dir_does_not_pin(
        self, tmp_path: Path, monkeypatch
    ):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        monkeypatch.chdir(proj)
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["pin"] is False

    def test_bare_ui_from_subdir_does_not_pin(
        self, tmp_path: Path, monkeypatch
    ):
        proj = tmp_path / "proj"
        (proj / "issues" / "KUI-1").mkdir(parents=True)
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        monkeypatch.chdir(proj / "issues" / "KUI-1")
        with patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["pin"] is False

    def test_wide_discovery_does_not_pin(self, tmp_path: Path, monkeypatch):
        """When discover_projects returns hits but cwd has no project."""
        from tripwire.ui.services.project_service import ProjectSummary

        sentinel = tmp_path / "discovered"
        sentinel.mkdir()
        (sentinel / "project.yaml").write_text(
            "name: dis\nkey_prefix: DIS\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch(
            "tripwire.ui.services.project_service.discover_projects",
            return_value=[
                ProjectSummary(
                    id="abc",
                    name="dis",
                    key_prefix="DIS",
                    dir=str(sentinel),
                    phase="scoping",
                    issue_count=0,
                    node_count=0,
                    session_count=0,
                )
            ],
        ):
            with patch("tripwire.ui.server.start_server") as mock_start:
                result = runner.invoke(cli, ["ui"])
        assert result.exit_code == 0
        assert mock_start.call_args.kwargs["pin"] is False
        # And project_dirs reflects the discovered project, not cwd.
        assert mock_start.call_args.kwargs["project_dirs"] == [Path(str(sentinel))]


class TestSeedProjectIndexPin:
    """seed_project_index(pin=) controls whether discovery widens later."""

    def test_pin_true_blocks_wider_discovery(self, tmp_path: Path):
        from tripwire.ui.config import UserConfig
        from tripwire.ui.services.project_service import (
            discover_projects,
            reload_project_index,
            seed_project_index,
        )

        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )

        try:
            seed_project_index([proj], pin=True)
            # discover_projects with empty config still pinned to seed.
            results = discover_projects(UserConfig())
            assert {Path(s.dir).resolve() for s in results} == {proj.resolve()}
        finally:
            reload_project_index()

    def test_pin_false_allows_wider_discovery(self, tmp_path: Path, monkeypatch):
        from tripwire.ui.config import UserConfig
        from tripwire.ui.services.project_service import (
            discover_projects,
            reload_project_index,
            seed_project_index,
        )

        proj_a = tmp_path / "a"
        proj_a.mkdir()
        (proj_a / "project.yaml").write_text(
            "name: a\nkey_prefix: A\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        proj_b = tmp_path / "b"
        proj_b.mkdir()
        (proj_b / "project.yaml").write_text(
            "name: b\nkey_prefix: B\nnext_issue_number: 1\nnext_session_number: 1\n"
        )

        # cwd = an empty dir; project_roots covers both projects.
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)

        try:
            seed_project_index([proj_a], pin=False)
            results = discover_projects(UserConfig(project_roots=[tmp_path]))
            dirs = {Path(s.dir).resolve() for s in results}
            assert proj_a.resolve() in dirs
            assert proj_b.resolve() in dirs
        finally:
            reload_project_index()


class TestSingleInstanceProbe:
    """Before binding, `tripwire ui` probes /api/health to detect a
    second invocation of itself on the same port."""

    def test_reuse_existing_tripwire_instance(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch(
            "tripwire.cli.ui._check_port",
            return_value=("reuse", "http://127.0.0.1:8000"),
        ), patch("tripwire.cli.ui.webbrowser.open") as mock_open, patch(
            "tripwire.ui.server.start_server"
        ) as mock_start:
            result = runner.invoke(cli, ["ui", "--project-dir", str(proj)])
        assert result.exit_code == 0
        assert "already running" in result.output
        assert "http://127.0.0.1:8000" in result.output
        mock_start.assert_not_called()
        mock_open.assert_called_once_with("http://127.0.0.1:8000")

    def test_reuse_no_browser_skips_open(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch(
            "tripwire.cli.ui._check_port",
            return_value=("reuse", "http://127.0.0.1:8000"),
        ), patch("tripwire.cli.ui.webbrowser.open") as mock_open, patch(
            "tripwire.ui.server.start_server"
        ):
            result = runner.invoke(
                cli, ["ui", "--project-dir", str(proj), "--no-browser"]
            )
        assert result.exit_code == 0
        mock_open.assert_not_called()

    def test_conflict_exits_with_error(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch(
            "tripwire.cli.ui._check_port",
            return_value=("conflict", "http://127.0.0.1:8000"),
        ), patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui", "--project-dir", str(proj)])
        assert result.exit_code == 1
        assert "in use by another service" in result.output
        mock_start.assert_not_called()

    def test_free_port_proceeds_to_bind(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch(
            "tripwire.cli.ui._check_port",
            return_value=("free", "http://127.0.0.1:8000"),
        ), patch("tripwire.ui.server.start_server") as mock_start:
            result = runner.invoke(cli, ["ui", "--project-dir", str(proj)])
        assert result.exit_code == 0
        mock_start.assert_called_once()

    def test_dev_mode_skips_probe(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        with patch("tripwire.cli.ui._check_port") as mock_probe, patch(
            "tripwire.ui.server.start_server"
        ) as mock_start:
            result = runner.invoke(
                cli, ["ui", "--project-dir", str(proj), "--dev"]
            )
        assert result.exit_code == 0
        mock_probe.assert_not_called()
        mock_start.assert_called_once()


def _make_import_blocker(blocked_module: str):
    """Return a side_effect function that blocks one module's import."""
    _real_import = builtins.__import__

    def _blocker(name, *args, **kwargs):
        if name == "tripwire.ui.server":
            exc = ModuleNotFoundError(f"No module named '{blocked_module}'")
            exc.name = blocked_module
            raise exc
        return _real_import(name, *args, **kwargs)

    return _blocker

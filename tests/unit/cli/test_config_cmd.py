"""Tests for tripwire.cli.config — the `tripwire config` subcommand."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli

runner = CliRunner()


@pytest.fixture(autouse=True)
def _redirect_default_config(tmp_path: Path, monkeypatch):
    """Point ~/.tripwire/config.yaml at a tmp file for the duration of each test.

    v0.13.1: ``_default_config_path()`` is now a function that reads
    ``TRIPWIRE_CONFIG_DIR`` lazily, so we redirect via env-var override
    (the same path real production deployments use) rather than patching
    a module constant.
    """
    monkeypatch.setenv("TRIPWIRE_CONFIG_DIR", str(tmp_path))
    yield tmp_path / "config.yaml"


class TestShow:
    def test_show_empty_config_prints_defaults(self, _redirect_default_config: Path):
        result = runner.invoke(cli, ["project", "config", "show"])
        assert result.exit_code == 0
        assert "port: 8000" in result.output
        assert "open_browser: true" in result.output

    def test_show_includes_path_header(self, _redirect_default_config: Path):
        result = runner.invoke(cli, ["project", "config", "show"])
        assert result.exit_code == 0
        assert str(_redirect_default_config) in result.output


class TestSet:
    def test_set_project_roots_writes_to_disk(
        self, tmp_path: Path, _redirect_default_config: Path
    ):
        root_a = tmp_path / "a"
        root_a.mkdir()
        root_b = tmp_path / "b"
        root_b.mkdir()
        result = runner.invoke(
            cli, ["project", "config", "set", "project-roots", str(root_a), str(root_b)]
        )
        assert result.exit_code == 0, result.output
        on_disk = yaml.safe_load(_redirect_default_config.read_text())
        assert on_disk["project_roots"] == [str(root_a), str(root_b)]

    def test_set_workspace_roots_writes_to_disk(
        self, tmp_path: Path, _redirect_default_config: Path
    ):
        root = tmp_path / "ws"
        root.mkdir()
        result = runner.invoke(
            cli, ["project", "config", "set", "workspace-roots", str(root)]
        )
        assert result.exit_code == 0, result.output
        on_disk = yaml.safe_load(_redirect_default_config.read_text())
        assert on_disk["workspace_roots"] == [str(root)]

    def test_set_overwrites_previous_value(
        self, tmp_path: Path, _redirect_default_config: Path
    ):
        first = tmp_path / "first"
        first.mkdir()
        second = tmp_path / "second"
        second.mkdir()
        runner.invoke(cli, ["project", "config", "set", "project-roots", str(first)])
        result = runner.invoke(
            cli, ["project", "config", "set", "project-roots", str(second)]
        )
        assert result.exit_code == 0
        on_disk = yaml.safe_load(_redirect_default_config.read_text())
        assert on_disk["project_roots"] == [str(second)]

    def test_set_warns_on_nonexistent_path(
        self, tmp_path: Path, _redirect_default_config: Path
    ):
        ghost = tmp_path / "does-not-exist"
        result = runner.invoke(
            cli, ["project", "config", "set", "project-roots", str(ghost)]
        )
        # Persisted anyway — warn but don't fail; user may be configuring
        # ahead of mounting the volume / cloning the repo.
        assert result.exit_code == 0
        assert "does not exist" in result.output

    def test_set_doesnt_pollute_with_defaults(
        self, tmp_path: Path, _redirect_default_config: Path
    ):
        """v0.10.0 review fix: setting one field should not write every
        other field's default into the YAML. Hand-crafted minimal
        configs ought to stay minimal after CLI use.
        """
        root = tmp_path / "r"
        root.mkdir()
        result = runner.invoke(
            cli, ["project", "config", "set", "project-roots", str(root)]
        )
        assert result.exit_code == 0
        on_disk = yaml.safe_load(_redirect_default_config.read_text())
        # Only project_roots should be persisted — port/open_browser/
        # workspace_roots are defaults, omitted.
        assert on_disk == {"project_roots": [str(root)]}
        assert "port" not in on_disk
        assert "open_browser" not in on_disk
        assert "workspace_roots" not in on_disk

    def test_show_round_trips_set(self, tmp_path: Path, _redirect_default_config: Path):
        root = tmp_path / "r"
        root.mkdir()
        runner.invoke(cli, ["project", "config", "set", "project-roots", str(root)])
        show = runner.invoke(cli, ["project", "config", "show"])
        assert show.exit_code == 0
        assert str(root) in show.output


class TestAdd:
    def test_add_project_root_appends(
        self, tmp_path: Path, _redirect_default_config: Path
    ):
        first = tmp_path / "first"
        first.mkdir()
        second = tmp_path / "second"
        second.mkdir()
        runner.invoke(cli, ["project", "config", "set", "project-roots", str(first)])
        result = runner.invoke(
            cli, ["project", "config", "add", "project-root", str(second)]
        )
        assert result.exit_code == 0
        on_disk = yaml.safe_load(_redirect_default_config.read_text())
        assert on_disk["project_roots"] == [str(first), str(second)]

    def test_add_is_idempotent(self, tmp_path: Path, _redirect_default_config: Path):
        root = tmp_path / "r"
        root.mkdir()
        runner.invoke(cli, ["project", "config", "add", "project-root", str(root)])
        result = runner.invoke(
            cli, ["project", "config", "add", "project-root", str(root)]
        )
        assert result.exit_code == 0
        assert "already in" in result.output
        on_disk = yaml.safe_load(_redirect_default_config.read_text())
        assert on_disk["project_roots"] == [str(root)]


class TestPath:
    def test_path_prints_default_location(self, _redirect_default_config: Path):
        result = runner.invoke(cli, ["project", "config", "path"])
        assert result.exit_code == 0
        assert str(_redirect_default_config) in result.output


class TestSavedConfigIsRoundTrippable:
    """`save_user_config(load_user_config(p), p)` must be a no-op."""

    def test_default_config_round_trips(self, tmp_path: Path):
        from tripwire.ui.config import (
            UserConfig,
            load_user_config,
            save_user_config,
        )

        target = tmp_path / "config.yaml"
        save_user_config(UserConfig(), target)
        loaded = load_user_config(target)
        assert loaded == UserConfig()

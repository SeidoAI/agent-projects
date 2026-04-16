"""Tests for keel.ui.config — UserConfig model + load_user_config()."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from keel.ui.config import UserConfig, load_user_config


class TestUserConfigDefaults:
    def test_defaults(self):
        cfg = UserConfig()
        assert cfg.project_roots == []
        assert cfg.default_project is None
        assert cfg.port == 8000
        assert cfg.open_browser is True


class TestLoadUserConfig:
    def test_missing_file_returns_defaults(self, tmp_path: Path):
        cfg = load_user_config(tmp_path / "nonexistent.yaml")
        assert cfg == UserConfig()

    def test_empty_file_returns_defaults(self, tmp_path: Path):
        f = tmp_path / "config.yaml"
        f.write_text("", encoding="utf-8")
        cfg = load_user_config(f)
        assert cfg == UserConfig()

    def test_valid_config_parsed(self, tmp_path: Path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "project_roots:\n"
            f"  - {tmp_path}\n"
            f"default_project: {tmp_path}\n"
            "port: 9000\n"
            "open_browser: false\n",
            encoding="utf-8",
        )
        cfg = load_user_config(f)
        assert cfg.port == 9000
        assert cfg.open_browser is False
        assert cfg.default_project == tmp_path
        assert tmp_path in cfg.project_roots

    def test_tilde_expanded_in_paths(self, tmp_path: Path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "project_roots:\n"
            "  - ~/some/path\n"
            "default_project: ~/other/path\n",
            encoding="utf-8",
        )
        cfg = load_user_config(f)
        home = Path.home()
        assert cfg.project_roots[0] == home / "some" / "path"
        assert cfg.default_project == home / "other" / "path"

    def test_invalid_yaml_returns_defaults_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        f = tmp_path / "config.yaml"
        f.write_text(":\n  - :\n  bad: [yaml", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="keel.ui.config"):
            cfg = load_user_config(f)
        assert cfg == UserConfig()
        assert "Invalid YAML" in caplog.text

    def test_invalid_port_returns_defaults_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        f = tmp_path / "config.yaml"
        f.write_text("port: abc\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="keel.ui.config"):
            cfg = load_user_config(f)
        assert cfg == UserConfig()
        assert "Invalid config" in caplog.text

    def test_port_out_of_range_returns_defaults(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        f = tmp_path / "config.yaml"
        f.write_text("port: 99999\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="keel.ui.config"):
            cfg = load_user_config(f)
        assert cfg == UserConfig()
        assert "Invalid config" in caplog.text

    def test_nonexistent_project_root_kept_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        missing = tmp_path / "does-not-exist"
        f = tmp_path / "config.yaml"
        f.write_text(f"project_roots:\n  - {missing}\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="keel.ui.config"):
            cfg = load_user_config(f)
        assert missing in cfg.project_roots
        assert "project root does not exist" in caplog.text

    def test_non_mapping_yaml_returns_defaults(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        f = tmp_path / "config.yaml"
        f.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="keel.ui.config"):
            cfg = load_user_config(f)
        assert cfg == UserConfig()
        assert "Expected a YAML mapping" in caplog.text

    def test_default_path_resolves_to_home(self):
        """load_user_config(None) should target ~/.keel/config.yaml."""
        # We just verify it doesn't crash — the file likely doesn't exist
        cfg = load_user_config()
        assert isinstance(cfg, UserConfig)

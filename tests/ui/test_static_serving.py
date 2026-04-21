"""Tests for static file serving — dev mode, prod mode, missing statics."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tripwire.ui.server import create_app


class TestDevMode:
    def test_no_static_mount(self):
        app = create_app(dev_mode=True)
        client = TestClient(app)
        # In dev mode, / should not serve statics — it should 404
        # (only /api/* routes are available)
        r = client.get("/")
        assert r.status_code == 404

    def test_info_log_emitted(self, caplog):
        with caplog.at_level(logging.INFO, logger="tripwire.ui.server"):
            create_app(dev_mode=True)
        assert any("Dev mode" in m for m in caplog.messages)


class TestProdModeWithBundle:
    def test_index_html_served_at_root(self, tmp_path: Path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text(
            "<html><body>tripwire</body></html>", encoding="utf-8"
        )

        with patch("tripwire.ui.server.importlib.resources.files") as mock_files:
            mock_files.return_value = tmp_path
            app = create_app(dev_mode=False)

        client = TestClient(app)
        r = client.get("/")
        assert r.status_code == 200
        assert "tripwire" in r.text

    def test_unknown_path_returns_index_html(self, tmp_path: Path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text(
            "<html><body>spa-fallback</body></html>", encoding="utf-8"
        )

        with patch("tripwire.ui.server.importlib.resources.files") as mock_files:
            mock_files.return_value = tmp_path
            app = create_app(dev_mode=False)

        client = TestClient(app)
        r = client.get("/some/unknown/path")
        assert r.status_code == 200
        assert "spa-fallback" in r.text

    def test_api_routes_not_intercepted(self, tmp_path: Path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("<html></html>", encoding="utf-8")

        with patch("tripwire.ui.server.importlib.resources.files") as mock_files:
            mock_files.return_value = tmp_path
            app = create_app(dev_mode=False)

        client = TestClient(app)
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestProdModeWithoutBundle:
    def test_warning_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tripwire.ui.server"):
            create_app(dev_mode=False)
        assert any("Frontend statics not found" in m for m in caplog.messages)

    def test_api_still_works(self):
        app = create_app(dev_mode=False)
        client = TestClient(app)
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

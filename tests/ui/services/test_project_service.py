"""Tests for keel.ui.services.project_service — discovery, caching, index."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from keel.ui.config import UserConfig
from keel.ui.services.project_service import (
    _project_id,
    discover_projects,
    get_project_dir,
    reload_project_index,
)


def _make_project(
    root: Path,
    name: str = "test",
    key_prefix: str = "TST",
    *,
    issues: int = 0,
    nodes: int = 0,
    sessions: int = 0,
) -> Path:
    """Create a minimal keel project directory under *root*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        f"name: {name}\nkey_prefix: {key_prefix}\n"
        "next_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions"):
        (root / sub).mkdir(exist_ok=True)

    for i in range(issues):
        issue_dir = root / "issues" / f"TST-{i + 1}"
        issue_dir.mkdir()
        (issue_dir / "issue.yaml").write_text(
            f"---\nid: TST-{i + 1}\ntitle: Issue {i + 1}\nstatus: todo\n"
            "priority: medium\nexecutor: ai\nverifier: required\nkind: feat\n---\n"
            "## Context\ntest\n",
            encoding="utf-8",
        )

    for i in range(nodes):
        (root / "nodes" / f"node-{i}.yaml").write_text(
            f"id: node-{i}\ntype: model\nname: Node {i}\nstatus: active\n",
            encoding="utf-8",
        )

    for i in range(sessions):
        (root / "sessions" / f"s{i}").mkdir()

    return root


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset module-level cache before each test."""
    reload_project_index()
    yield
    reload_project_index()


class TestDiscoverProjects:
    def test_empty_config_no_projects(self, tmp_path: Path):
        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            # Make CWD point to tmp_path (no project.yaml there)
            mock_path_cls.cwd.return_value = tmp_path
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            # Restore Path behaviour for everything else
            mock_path_cls.side_effect = Path
            cfg = UserConfig(project_roots=[])
            result = discover_projects(cfg)
        assert result == []

    def test_project_in_cwd(self, tmp_path: Path):
        proj = _make_project(tmp_path / "myproj")
        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            result = discover_projects(UserConfig())
        assert len(result) == 1
        assert result[0].name == "test"

    def test_multiple_projects_in_configured_root(self, tmp_path: Path):
        root = tmp_path / "projects"
        _make_project(root / "alpha", name="alpha", key_prefix="A")
        _make_project(root / "beta", name="beta", key_prefix="B")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = tmp_path / "empty"
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig(project_roots=[root])
            result = discover_projects(cfg)

        names = {s.name for s in result}
        assert "alpha" in names
        assert "beta" in names

    def test_hidden_dirs_pruned(self, tmp_path: Path):
        root = tmp_path / "projects"
        root.mkdir()
        _make_project(root / ".hidden" / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = tmp_path / "empty"
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig(project_roots=[root])
            result = discover_projects(cfg)

        assert len(result) == 0

    def test_build_dirs_pruned(self, tmp_path: Path):
        root = tmp_path / "projects"
        root.mkdir()
        _make_project(root / "node_modules" / "proj")
        _make_project(root / ".git" / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = tmp_path / "empty"
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig(project_roots=[root])
            result = discover_projects(cfg)

        assert len(result) == 0

    def test_deduplication_by_resolved_path(self, tmp_path: Path):
        proj = _make_project(tmp_path / "real")
        link = tmp_path / "link"
        link.symlink_to(proj)

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig(project_roots=[tmp_path])
            result = discover_projects(cfg)

        assert len(result) == 1

    def test_unreadable_project_yaml_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        proj = tmp_path / "bad"
        proj.mkdir()
        (proj / "project.yaml").write_text("not: valid: yaml: [", encoding="utf-8")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = tmp_path / "empty"
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            with caplog.at_level(
                logging.WARNING, logger="keel.ui.services.project_service"
            ):
                cfg = UserConfig(project_roots=[tmp_path])
                result = discover_projects(cfg)

        assert len(result) == 0
        assert "Skipping" in caplog.text

    def test_deterministic_ids(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj")
        id1 = _project_id(proj.resolve())
        id2 = _project_id(proj.resolve())
        assert id1 == id2
        assert len(id1) == 12

    def test_counts(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj", issues=3, nodes=2, sessions=1)

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            result = discover_projects(UserConfig())

        assert len(result) == 1
        assert result[0].issue_count == 3
        assert result[0].node_count == 2
        assert result[0].session_count == 1


class TestCache:
    def test_cache_hit(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig()
            r1 = discover_projects(cfg)
            r2 = discover_projects(cfg)

        assert r1 is r2  # same object — cache hit

    def test_reload_clears_cache(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig()
            r1 = discover_projects(cfg)
            reload_project_index()
            r2 = discover_projects(cfg)

        assert r1 is not r2  # different objects — cache was cleared

    def test_cache_expires(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            cfg = UserConfig()
            r1 = discover_projects(cfg)

            with patch("keel.ui.services.project_service.time") as mock_time:
                mock_time.monotonic.return_value = time.monotonic() + 61
                r2 = discover_projects(cfg)

        assert r1 is not r2


class TestProjectIndex:
    def test_get_project_dir_after_discovery(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            results = discover_projects(UserConfig())

        pid = results[0].id
        assert get_project_dir(pid) == proj.resolve()

    def test_get_project_dir_bad_id(self, tmp_path: Path):
        assert get_project_dir("nonexistent") is None

    def test_index_cleared_on_reload(self, tmp_path: Path):
        proj = _make_project(tmp_path / "proj")

        with patch("keel.ui.services.project_service.Path") as mock_path_cls:
            mock_path_cls.cwd.return_value = proj
            mock_path_cls.home.return_value = tmp_path / "fakehome"
            mock_path_cls.side_effect = Path
            results = discover_projects(UserConfig())

        pid = results[0].id
        reload_project_index()
        assert get_project_dir(pid) is None

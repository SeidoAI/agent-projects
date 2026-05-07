"""Unit tests for tripwire.ui.services.workspace_service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from tripwire.core.workspace_store import add_project, save_workspace
from tripwire.models.workspace import Workspace, WorkspaceProjectEntry
from tripwire.ui.config import UserConfig
from tripwire.ui.services.workspace_service import (
    discover_workspaces,
    get_workspace_dir,
    get_workspace_id_for_project,
    list_workspaces,
    reload_workspace_index,
)


@pytest.fixture(autouse=True)
def _reset_workspace_index():
    """Clear the workspace_service module-level cache between tests."""
    reload_workspace_index()
    yield
    reload_workspace_index()


def _make_workspace(
    workspace_dir: Path, *, slug: str = "seido", name: str = "Seido"
) -> Path:
    """Write a valid workspace.yaml under *workspace_dir* and return it."""
    workspace_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)
    ws = Workspace(
        uuid=uuid4(),
        name=name,
        slug=slug,
        description=f"{name} fixture workspace",
        schema_version=1,
        tripwire_version="0.6.0",
        created_at=now,
        updated_at=now,
    )
    save_workspace(workspace_dir, ws)
    return workspace_dir


class TestDiscoverWorkspaces:
    def test_empty_config_returns_empty(self):
        assert discover_workspaces(UserConfig()) == []

    def test_finds_workspace_at_depth_1(self, tmp_path: Path):
        ws_dir = _make_workspace(tmp_path / "ws-a")
        results = discover_workspaces(UserConfig(workspace_roots=[ws_dir.parent]))
        slugs = [s.slug for s in results]
        assert slugs == ["seido"]
        assert results[0].dir == str(ws_dir.resolve())

    def test_finds_workspace_at_depth_0(self, tmp_path: Path):
        """Pointing workspace_roots directly at a workspace dir works."""
        ws_dir = _make_workspace(tmp_path / "ws")
        results = discover_workspaces(UserConfig(workspace_roots=[ws_dir]))
        assert [s.slug for s in results] == ["seido"]

    def test_skips_non_workspace_dirs(self, tmp_path: Path):
        """Sibling dirs without workspace.yaml are ignored, not errors."""
        _make_workspace(tmp_path / "real")
        (tmp_path / "decoy").mkdir()
        (tmp_path / "decoy" / "README.md").write_text("not a workspace")
        results = discover_workspaces(UserConfig(workspace_roots=[tmp_path]))
        assert {s.slug for s in results} == {"seido"}

    def test_lists_member_project_slugs(self, tmp_path: Path):
        ws_dir = _make_workspace(tmp_path / "ws")
        add_project(
            ws_dir,
            WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kbp"),
        )
        add_project(
            ws_dir,
            WorkspaceProjectEntry(slug="gui", name="graph-ui", path="../gui"),
        )
        results = discover_workspaces(UserConfig(workspace_roots=[ws_dir]))
        assert results[0].project_slugs == ["kbp", "gui"]

    def test_dedups_across_overlapping_roots(self, tmp_path: Path):
        ws_dir = _make_workspace(tmp_path / "ws")
        results = discover_workspaces(
            UserConfig(workspace_roots=[ws_dir, ws_dir.parent])
        )
        # Same workspace surfaced via two roots must not appear twice.
        assert len(results) == 1

    def test_caches_results_for_60s(self, tmp_path: Path):
        _make_workspace(tmp_path / "ws-a")
        config = UserConfig(workspace_roots=[tmp_path])
        first = discover_workspaces(config)
        # Add a second workspace AFTER the first call.
        _make_workspace(tmp_path / "ws-b", slug="other", name="Other")
        # Cache hit: second workspace not seen.
        second = discover_workspaces(config)
        assert {s.slug for s in second} == {s.slug for s in first}
        # Force rescan picks up the new workspace.
        reload_workspace_index()
        third = discover_workspaces(config)
        assert {s.slug for s in third} == {"seido", "other"}

    def test_id_stable_across_calls(self, tmp_path: Path):
        ws_dir = _make_workspace(tmp_path / "ws")
        config = UserConfig(workspace_roots=[ws_dir])
        first = discover_workspaces(config)
        reload_workspace_index()
        second = discover_workspaces(config)
        assert first[0].id == second[0].id


class TestListAndGetDir:
    def test_get_workspace_dir_returns_known(self, tmp_path: Path, monkeypatch):
        ws_dir = _make_workspace(tmp_path / "ws")
        config = UserConfig(workspace_roots=[ws_dir])
        # Populate the index via discovery.
        from tripwire.ui import config as config_mod

        monkeypatch.setattr(config_mod, "load_user_config", lambda: config)
        from tripwire.ui.services import workspace_service as ws_svc

        monkeypatch.setattr(ws_svc, "load_user_config", lambda: config)
        summaries = list_workspaces()
        assert len(summaries) == 1
        ws_id = summaries[0].id
        assert get_workspace_dir(ws_id) == ws_dir.resolve()

    def test_get_workspace_dir_unknown_returns_none(self):
        assert get_workspace_dir("does-not-exist") is None


class TestGetWorkspaceIdForProject:
    def test_resolves_pointer_to_registered_workspace(
        self, tmp_path: Path, monkeypatch
    ):
        ws_dir = _make_workspace(tmp_path / "workspaces" / "seido")
        proj_dir = tmp_path / "projects" / "kbp"
        proj_dir.mkdir(parents=True)
        # Register the workspace so the gate in
        # `get_workspace_id_for_project` recognises it.
        cfg = UserConfig(workspace_roots=[ws_dir.parent])
        from tripwire.ui.services import workspace_service as ws_svc

        monkeypatch.setattr(ws_svc, "load_user_config", lambda: cfg)
        ws_id = get_workspace_id_for_project(proj_dir, "../../workspaces/seido")
        assert ws_id is not None
        assert len(ws_id) == 12  # blake2s-6 hex

    def test_id_matches_discover_id(self, tmp_path: Path, monkeypatch):
        ws_dir = _make_workspace(tmp_path / "workspaces" / "seido")
        proj_dir = tmp_path / "projects" / "kbp"
        proj_dir.mkdir(parents=True)
        cfg = UserConfig(workspace_roots=[ws_dir.parent])
        from tripwire.ui.services import workspace_service as ws_svc

        monkeypatch.setattr(ws_svc, "load_user_config", lambda: cfg)
        from_pointer = get_workspace_id_for_project(proj_dir, "../../workspaces/seido")
        from_discovery = discover_workspaces(cfg)[0].id
        assert from_pointer == from_discovery

    def test_broken_pointer_returns_none(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        assert get_workspace_id_for_project(proj_dir, "../missing-ws") is None

    def test_pointer_to_non_workspace_dir_returns_none(self, tmp_path: Path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        decoy = tmp_path / "decoy"
        decoy.mkdir()
        (decoy / "README.md").write_text("not a workspace")
        assert get_workspace_id_for_project(proj_dir, "../decoy") is None

    def test_pointer_to_unregistered_workspace_returns_none(
        self, tmp_path: Path, monkeypatch
    ):
        """v0.10.0 fix: a project whose workspace.path points at a real
        workspace.yaml but the workspace itself isn't under any
        registered ``workspace_roots`` must NOT surface a workspace_id.

        Without this gate, the picker dropdown renders an "Unknown
        workspace" group with no way for the user to recover (the name
        only resolves via ``GET /api/workspaces``, which only returns
        registered workspaces).
        """
        # Make the workspace exist on disk but DON'T register it.
        _make_workspace(tmp_path / "elsewhere" / "seido")
        proj_dir = tmp_path / "projects" / "kbp"
        proj_dir.mkdir(parents=True)
        empty_cfg = UserConfig(workspace_roots=[])
        from tripwire.ui.services import workspace_service as ws_svc

        monkeypatch.setattr(ws_svc, "load_user_config", lambda: empty_cfg)
        ws_id = get_workspace_id_for_project(proj_dir, "../../elsewhere/seido")
        assert ws_id is None

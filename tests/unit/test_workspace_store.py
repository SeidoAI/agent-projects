"""workspace_store: CRUD on workspace.yaml."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tripwire.core.workspace_store import (
    add_project,
    load_workspace,
    remove_project,
    save_workspace,
    update_project_pull_state,
    update_project_push_state,
    workspace_exists,
)
from tripwire.models.workspace import Workspace, WorkspaceProjectEntry


def _fresh_ws() -> Workspace:
    now = datetime.now(tz=timezone.utc)
    return Workspace(
        uuid=uuid4(),
        name="Seido",
        slug="seido",
        description="",
        schema_version=1,
        tripwire_version="0.6.0",
        created_at=now,
        updated_at=now,
    )


def test_exists_false_for_empty_dir(tmp_path):
    assert workspace_exists(tmp_path) is False


def test_save_then_load_roundtrip(tmp_path):
    (tmp_path / "nodes").mkdir()
    ws = _fresh_ws()
    save_workspace(tmp_path, ws)
    loaded = load_workspace(tmp_path)
    assert loaded.slug == "seido"


def test_add_project(tmp_path):
    (tmp_path / "nodes").mkdir()
    save_workspace(tmp_path, _fresh_ws())
    add_project(
        tmp_path,
        WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kb-pivot"),
    )
    ws = load_workspace(tmp_path)
    assert len(ws.projects) == 1
    assert ws.projects[0].slug == "kbp"


def test_add_duplicate_slug_rejected(tmp_path):
    (tmp_path / "nodes").mkdir()
    save_workspace(tmp_path, _fresh_ws())
    add_project(
        tmp_path,
        WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kb-pivot"),
    )
    with pytest.raises(ValueError, match="already registered"):
        add_project(
            tmp_path,
            WorkspaceProjectEntry(slug="kbp", name="other", path="../other"),
        )


def test_remove_project(tmp_path):
    (tmp_path / "nodes").mkdir()
    save_workspace(tmp_path, _fresh_ws())
    add_project(
        tmp_path,
        WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kb-pivot"),
    )
    remove_project(tmp_path, slug="kbp")
    ws = load_workspace(tmp_path)
    assert ws.projects == []


def test_update_pull_state(tmp_path):
    (tmp_path / "nodes").mkdir()
    save_workspace(tmp_path, _fresh_ws())
    add_project(
        tmp_path,
        WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kb-pivot"),
    )
    update_project_pull_state(
        tmp_path,
        slug="kbp",
        sha="abc123",
        at=datetime.now(tz=timezone.utc),
    )
    ws = load_workspace(tmp_path)
    assert ws.projects[0].last_pulled_sha == "abc123"


def test_update_push_state(tmp_path):
    (tmp_path / "nodes").mkdir()
    save_workspace(tmp_path, _fresh_ws())
    add_project(
        tmp_path,
        WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kb-pivot"),
    )
    update_project_push_state(
        tmp_path,
        slug="kbp",
        sha="def456",
        at=datetime.now(tz=timezone.utc),
    )
    ws = load_workspace(tmp_path)
    assert ws.projects[0].last_pushed_sha == "def456"

"""Workspace + WorkspaceProjectEntry Pydantic models (v0.6b)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from keel.models.workspace import Workspace, WorkspaceProjectEntry


def _now():
    return datetime.now(tz=timezone.utc)


def _minimal_workspace(**kwargs):
    defaults = dict(
        uuid=uuid4(),
        name="Seido",
        slug="seido",
        description="",
        schema_version=1,
        keel_version="0.6.0",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(kwargs)
    return Workspace(**defaults)


def test_minimal_workspace():
    ws = _minimal_workspace()
    assert ws.projects == []


def test_duplicate_project_slugs_rejected():
    with pytest.raises(ValidationError):
        _minimal_workspace(
            projects=[
                WorkspaceProjectEntry(slug="kbp", name="kb-pivot", path="../kb-pivot"),
                WorkspaceProjectEntry(slug="kbp", name="other", path="../other"),
            ]
        )


def test_project_entry_tracks_last_sync():
    entry = WorkspaceProjectEntry(
        slug="kbp",
        name="kb-pivot",
        path="../kb-pivot",
        last_pulled_sha="a3f2b1c",
        last_pulled_at=_now(),
        last_pushed_sha="a3f2b1c",
        last_pushed_at=_now(),
    )
    assert entry.last_pulled_sha == "a3f2b1c"


def test_unknown_schema_version_rejected():
    with pytest.raises(ValidationError):
        _minimal_workspace(schema_version=99)

"""ProjectConfig.workspace field (v0.6b)."""

import pytest
from pydantic import ValidationError

from keel.models.project import ProjectConfig, ProjectWorkspacePointer


def _project_fields():
    return {
        "name": "test",
        "key_prefix": "TST",
        "next_issue_number": 1,
        "next_session_number": 1,
    }


def test_workspace_field_optional():
    p = ProjectConfig(**_project_fields())
    assert p.workspace is None


def test_workspace_path_accepts_relative():
    p = ProjectConfig(
        **_project_fields(),
        workspace=ProjectWorkspacePointer(path="../seido-workspace"),
    )
    assert p.workspace is not None
    assert p.workspace.path == "../seido-workspace"


def test_workspace_rejects_empty_pointer():
    with pytest.raises(ValidationError):
        ProjectWorkspacePointer()

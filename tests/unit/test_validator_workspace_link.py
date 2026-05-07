"""Validator rule for bidirectional workspace<->project link consistency."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from tripwire.core.validator._types import ValidationContext
from tripwire.core.validator.checks.workspace_link import check_workspace_link
from tripwire.core.workspace_store import save_workspace
from tripwire.models.project import ProjectConfig, ProjectWorkspacePointer
from tripwire.models.workspace import Workspace, WorkspaceProjectEntry


def _project_config(workspace_path: str | None = None) -> ProjectConfig:
    return ProjectConfig.model_validate(
        {
            "name": "alpha",
            "key_prefix": "ALP",
            "next_issue_number": 1,
            "next_session_number": 1,
            "workspace": (
                {"path": workspace_path} if workspace_path is not None else None
            ),
        }
    )


def _save_workspace(
    ws_dir: Path,
    *,
    slug: str = "ws",
    projects: list[WorkspaceProjectEntry] | None = None,
) -> None:
    now = datetime.now(tz=timezone.utc)
    ws_dir.mkdir(parents=True, exist_ok=True)
    save_workspace(
        ws_dir,
        Workspace(
            uuid=uuid4(),
            name=slug,
            slug=slug,
            description="",
            schema_version=1,
            tripwire_version="0.6.0",
            created_at=now,
            updated_at=now,
            projects=projects or [],
        ),
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    p = tmp_path / "alpha"
    p.mkdir()
    return p


def test_no_workspace_pointer_is_noop(project_dir: Path) -> None:
    """A project without `workspace.path` produces no findings."""
    ctx = ValidationContext(project_dir=project_dir, project_config=_project_config())
    assert check_workspace_link(ctx) == []


def test_pointer_to_missing_directory_dangling(project_dir: Path) -> None:
    ctx = ValidationContext(
        project_dir=project_dir,
        project_config=_project_config(workspace_path="../does-not-exist"),
    )
    findings = check_workspace_link(ctx)
    assert len(findings) == 1
    assert findings[0].code == "workspace/pointer_dangling"
    assert findings[0].severity == "error"


def test_pointer_to_dir_without_workspace_yaml(
    project_dir: Path, tmp_path: Path
) -> None:
    bare = tmp_path / "bare-dir"
    bare.mkdir()
    ctx = ValidationContext(
        project_dir=project_dir,
        project_config=_project_config(workspace_path="../bare-dir"),
    )
    findings = check_workspace_link(ctx)
    assert len(findings) == 1
    assert findings[0].code == "workspace/pointer_dangling"


def test_workspace_does_not_list_back_reference(
    project_dir: Path, tmp_path: Path
) -> None:
    ws = tmp_path / "ws-x"
    _save_workspace(ws, slug="wsx", projects=[])
    ctx = ValidationContext(
        project_dir=project_dir,
        project_config=_project_config(workspace_path="../ws-x"),
    )
    findings = check_workspace_link(ctx)
    assert len(findings) == 1
    assert findings[0].code == "workspace/back_reference_missing"
    assert findings[0].severity == "error"
    assert "list this project" in findings[0].message


def test_happy_path_relative_back_reference(project_dir: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws-y"
    _save_workspace(
        ws,
        slug="wsy",
        projects=[WorkspaceProjectEntry(slug="alp", name="alpha", path="../alpha")],
    )
    ctx = ValidationContext(
        project_dir=project_dir,
        project_config=_project_config(workspace_path="../ws-y"),
    )
    assert check_workspace_link(ctx) == []


def test_happy_path_absolute_back_reference(project_dir: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws-z"
    _save_workspace(
        ws,
        slug="wsz",
        projects=[
            WorkspaceProjectEntry(
                slug="alp", name="alpha", path=str(project_dir.resolve())
            )
        ],
    )
    ctx = ValidationContext(
        project_dir=project_dir,
        project_config=_project_config(workspace_path="../ws-z"),
    )
    assert check_workspace_link(ctx) == []


def test_workspace_yaml_load_error_is_surfaced(
    project_dir: Path, tmp_path: Path
) -> None:
    ws = tmp_path / "ws-broken"
    ws.mkdir()
    # Hand-write an invalid workspace.yaml.
    (ws / "workspace.yaml").write_text("not: [a, valid, mapping", encoding="utf-8")
    ctx = ValidationContext(
        project_dir=project_dir,
        project_config=_project_config(workspace_path="../ws-broken"),
    )
    findings = check_workspace_link(ctx)
    assert len(findings) == 1
    assert findings[0].code == "workspace/load_error"


def test_check_is_registered_in_all_checks() -> None:
    """Wire-up regression: the new check must run in the canonical pipeline."""
    from tripwire.core.validator.checks import (
        ALL_CHECKS,
        WORKSPACE_CHECKS,
    )

    assert check_workspace_link in ALL_CHECKS
    assert WORKSPACE_CHECKS == [check_workspace_link]


def test_pointer_object_form_pydantic_construct(
    project_dir: Path, tmp_path: Path
) -> None:
    """Sanity: ProjectConfig.workspace accepts the v0.6b object form."""
    ws = tmp_path / "ws-q"
    _save_workspace(
        ws,
        slug="wsq",
        projects=[WorkspaceProjectEntry(slug="alp", name="alpha", path="../alpha")],
    )
    config = ProjectConfig(
        name="alpha",
        key_prefix="ALP",
        next_issue_number=1,
        next_session_number=1,
        workspace=ProjectWorkspacePointer(path="../ws-q"),
    )
    ctx = ValidationContext(project_dir=project_dir, project_config=config)
    assert check_workspace_link(ctx) == []

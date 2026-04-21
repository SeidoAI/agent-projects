"""Tests for tripwire.ui.services.artifact_service (KUI-22)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tripwire.ui.services.artifact_service import (
    ApprovalSidecar,
    ArtifactContent,
    ArtifactManifest,
    ArtifactSpec,
    ArtifactStatus,
    approve_artifact,
    get_manifest,
    get_session_artifact,
    list_session_artifacts,
    reject_artifact,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _write_manifest(project_dir: Path, artifacts: list[dict[str, Any]]) -> None:
    path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"artifacts": artifacts}, sort_keys=False))


def _session_dir(project_dir: Path, session_id: str) -> Path:
    sdir = project_dir / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


@pytest.fixture
def project_with_manifest(tmp_path_project: Path) -> Path:
    """Writes a realistic manifest covering a gated + ungated artifact."""
    _write_manifest(
        tmp_path_project,
        [
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "planning",
                "produced_by": "pm",
                "owned_by": "pm",
                "required": True,
                "approval_gate": True,
            },
            {
                "name": "task-checklist",
                "file": "task-checklist.md",
                "template": "task-checklist.md.j2",
                "produced_at": "executing",
                "produced_by": "backend-coder",
                "owned_by": "backend-coder",
                "required": True,
                "approval_gate": False,
            },
        ],
    )
    return tmp_path_project


# ---------------------------------------------------------------------------
# get_manifest
# ---------------------------------------------------------------------------


class TestGetManifest:
    def test_parses_full_field_set(self, project_with_manifest: Path):
        manifest = get_manifest(project_with_manifest)
        assert isinstance(manifest, ArtifactManifest)
        assert len(manifest.artifacts) == 2
        plan = manifest.artifacts[0]
        assert plan.name == "plan"
        assert plan.file == "plan.md"
        assert plan.template == "plan.md.j2"
        assert plan.produced_at == "planning"
        assert plan.produced_by == "pm"
        assert plan.owned_by == "pm"
        assert plan.required is True
        assert plan.approval_gate is True

    def test_returns_empty_when_manifest_missing(self, tmp_path: Path):
        """Missing manifest file → empty manifest, not an error."""
        project = tmp_path / "p"
        project.mkdir()
        (project / "project.yaml").write_text(
            "name: t\nkey_prefix: T\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        assert get_manifest(project).artifacts == []

    def test_returns_empty_on_malformed_manifest(self, tmp_path_project: Path):
        path = tmp_path_project / "templates" / "artifacts" / "manifest.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not: valid: yaml: here :::")
        assert get_manifest(tmp_path_project).artifacts == []

    def test_owned_by_defaults_to_produced_by(self, tmp_path_project: Path):
        _write_manifest(
            tmp_path_project,
            [
                {
                    "name": "plan",
                    "file": "plan.md",
                    "template": "plan.md.j2",
                    "produced_at": "planning",
                    "produced_by": "pm",
                    # no owned_by
                }
            ],
        )
        spec = get_manifest(tmp_path_project).artifacts[0]
        assert spec.owned_by == "pm"


# ---------------------------------------------------------------------------
# list_session_artifacts
# ---------------------------------------------------------------------------


class TestListSessionArtifacts:
    def test_reports_missing_artifacts(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        statuses = list_session_artifacts(project_with_manifest, "s1")
        names = {s.spec.name: s for s in statuses}
        assert set(names) == {"plan", "task-checklist"}
        assert all(s.present is False for s in statuses)
        assert all(s.size_bytes is None for s in statuses)
        assert all(s.last_modified is None for s in statuses)

    def test_detects_present_artifact_at_root(self, project_with_manifest: Path):
        sdir = _session_dir(project_with_manifest, "s1")
        (sdir / "plan.md").write_text("# plan\n", encoding="utf-8")

        statuses = list_session_artifacts(project_with_manifest, "s1")
        plan = next(s for s in statuses if s.spec.name == "plan")
        assert plan.present is True
        assert plan.size_bytes == len("# plan\n")
        assert plan.last_modified is not None

    def test_detects_present_artifact_in_artifacts_subdir(
        self, project_with_manifest: Path
    ):
        sdir = _session_dir(project_with_manifest, "s1")
        adir = sdir / "artifacts"
        adir.mkdir()
        (adir / "task-checklist.md").write_text("- [ ] x\n", encoding="utf-8")

        statuses = list_session_artifacts(project_with_manifest, "s1")
        checklist = next(s for s in statuses if s.spec.name == "task-checklist")
        assert checklist.present is True

    def test_symlinked_artifact_not_treated_as_present(
        self, project_with_manifest: Path, tmp_path: Path
    ):
        sdir = _session_dir(project_with_manifest, "s1")
        real_target = tmp_path / "real.md"
        real_target.write_text("#\n", encoding="utf-8")
        link = sdir / "plan.md"
        link.symlink_to(real_target)

        statuses = list_session_artifacts(project_with_manifest, "s1")
        plan = next(s for s in statuses if s.spec.name == "plan")
        assert plan.present is False

    def test_reports_approval_sidecar_when_present(
        self, project_with_manifest: Path
    ):
        sdir = _session_dir(project_with_manifest, "s1")
        (sdir / "plan.md").write_text("# plan\n", encoding="utf-8")
        # Pre-write a sidecar and confirm the status picks it up.
        approve_artifact(project_with_manifest, "s1", "plan", feedback="lgtm")

        statuses = list_session_artifacts(project_with_manifest, "s1")
        plan = next(s for s in statuses if s.spec.name == "plan")
        assert plan.approval is not None
        assert plan.approval.approved is True
        assert plan.approval.feedback == "lgtm"

    def test_returns_empty_when_manifest_missing(self, tmp_path: Path):
        project = tmp_path / "p"
        project.mkdir()
        (project / "project.yaml").write_text(
            "name: t\nkey_prefix: T\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        (project / "sessions" / "s1").mkdir(parents=True)
        assert list_session_artifacts(project, "s1") == []


# ---------------------------------------------------------------------------
# get_session_artifact
# ---------------------------------------------------------------------------


class TestGetSessionArtifact:
    def test_returns_body_and_mtime(self, project_with_manifest: Path):
        sdir = _session_dir(project_with_manifest, "s1")
        (sdir / "plan.md").write_text("# plan content\n", encoding="utf-8")

        content = get_session_artifact(project_with_manifest, "s1", "plan")
        assert isinstance(content, ArtifactContent)
        assert content.name == "plan"
        assert content.body == "# plan content\n"
        assert content.file_path.endswith("plan.md")
        assert content.mtime is not None

    def test_missing_file_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(FileNotFoundError):
            get_session_artifact(project_with_manifest, "s1", "plan")

    def test_unknown_name_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(FileNotFoundError):
            get_session_artifact(project_with_manifest, "s1", "nonexistent")


# ---------------------------------------------------------------------------
# approve_artifact
# ---------------------------------------------------------------------------


class TestApproveArtifact:
    def test_writes_sidecar_at_session_root(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        status = approve_artifact(
            project_with_manifest, "s1", "plan", feedback="looks good"
        )
        sidecar = (
            project_with_manifest / "sessions" / "s1" / "plan.approval.yaml"
        )
        assert sidecar.is_file()
        raw = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert raw["approved"] is True
        assert raw["reviewer"] == "user"
        assert raw["feedback"] == "looks good"
        assert "reviewed_at" in raw
        # Returned status reflects the new sidecar.
        assert isinstance(status, ArtifactStatus)
        assert status.approval is not None
        assert status.approval.approved is True

    def test_accepts_missing_feedback(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        status = approve_artifact(project_with_manifest, "s1", "plan")
        assert status.approval is not None
        assert status.approval.approved is True
        assert status.approval.feedback is None

    def test_ungated_artifact_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(ValueError, match="no approval gate"):
            approve_artifact(project_with_manifest, "s1", "task-checklist")

    def test_unknown_artifact_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(ValueError, match="No manifest entry"):
            approve_artifact(project_with_manifest, "s1", "does-not-exist")


# ---------------------------------------------------------------------------
# reject_artifact
# ---------------------------------------------------------------------------


class TestRejectArtifact:
    def test_writes_sidecar_with_feedback(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        status = reject_artifact(
            project_with_manifest, "s1", "plan", feedback="needs rework"
        )
        sidecar = (
            project_with_manifest / "sessions" / "s1" / "plan.approval.yaml"
        )
        raw = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert raw["approved"] is False
        assert raw["feedback"] == "needs rework"
        assert status.approval is not None
        assert status.approval.approved is False

    def test_empty_feedback_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(ValueError, match="feedback"):
            reject_artifact(project_with_manifest, "s1", "plan", feedback="")

    def test_whitespace_feedback_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(ValueError, match="feedback"):
            reject_artifact(
                project_with_manifest, "s1", "plan", feedback="   \n\t  "
            )

    def test_ungated_artifact_raises(self, project_with_manifest: Path):
        _session_dir(project_with_manifest, "s1")
        with pytest.raises(ValueError, match="no approval gate"):
            reject_artifact(
                project_with_manifest, "s1", "task-checklist", feedback="x"
            )


# ---------------------------------------------------------------------------
# Atomic write behaviour
# ---------------------------------------------------------------------------


class TestAtomicSidecarWrite:
    def test_existing_sidecar_is_overwritten_cleanly(
        self, project_with_manifest: Path
    ):
        _session_dir(project_with_manifest, "s1")
        approve_artifact(project_with_manifest, "s1", "plan", feedback="first")
        reject_artifact(
            project_with_manifest, "s1", "plan", feedback="changed mind"
        )

        sidecar = (
            project_with_manifest / "sessions" / "s1" / "plan.approval.yaml"
        )
        raw = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert raw["approved"] is False
        assert raw["feedback"] == "changed mind"
        # No temp-file debris.
        sdir = project_with_manifest / "sessions" / "s1"
        assert sorted(p.name for p in sdir.iterdir()) == ["plan.approval.yaml"]


# ---------------------------------------------------------------------------
# DTO round-trips
# ---------------------------------------------------------------------------


class TestDtoRoundTrip:
    def test_artifact_spec_dto_stable(self):
        spec = ArtifactSpec(
            name="plan",
            file="plan.md",
            template="plan.md.j2",
            produced_at="planning",
            produced_by="pm",
            owned_by="pm",
            required=True,
            approval_gate=True,
        )
        data = spec.model_dump()
        assert ArtifactSpec.model_validate(data) == spec

    def test_sidecar_dto_stable(self):
        from datetime import datetime

        side = ApprovalSidecar(
            approved=True,
            reviewer="user",
            reviewed_at=datetime(2026, 4, 14, 12, 0, 0),
            feedback="ok",
        )
        data = side.model_dump(mode="json")
        assert ApprovalSidecar.model_validate(data) == side

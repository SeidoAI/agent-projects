"""ProjectConfig override fields added in v0.7b."""

import pytest
from pydantic import ValidationError

from tripwire.models.project import ArtifactManifestRequirements, ProjectConfig


def test_project_supports_artifact_overrides():
    p = ProjectConfig(
        name="test",
        key_prefix="TST",
        artifact_manifest_overrides=[
            {
                "name": "extra-doc",
                "file": "extra.md",
                "template": "extra.md.j2",
                "produced_at": "in_progress",
                "produced_by": "execution-agent",
            }
        ],
    )
    assert len(p.artifact_manifest_overrides) == 1
    assert p.artifact_manifest_overrides[0].name == "extra-doc"


def test_project_supports_issue_artifact_overrides():
    p = ProjectConfig(
        name="test",
        key_prefix="TST",
        issue_artifact_manifest_overrides=[
            {
                "name": "extra-issue-doc",
                "file": "extra.md",
                "template": "extra.md.j2",
                "produced_by": "execution-agent",
                "required_at_status": "in_review",
            }
        ],
    )
    assert len(p.issue_artifact_manifest_overrides) == 1


def test_overrides_default_to_empty_lists():
    p = ProjectConfig(name="test", key_prefix="TST")
    assert p.artifact_manifest_overrides == []
    assert p.issue_artifact_manifest_overrides == []


# ----------------------------------------------------------------------------
# v0.7.9 §A1 — artifact_manifest correctness contract
# ----------------------------------------------------------------------------


def test_artifact_manifest_has_spec_defaults():
    """Empty `artifact_manifest:` resolves to the spec §A1 defaults."""
    p = ProjectConfig(name="test", key_prefix="TST")
    assert p.artifact_manifest.session_required == [
        "task-checklist.md",
        "verification-checklist.md",
        "self-review.md",
        "pm-response.md",
        "insights.yaml",
    ]
    assert p.artifact_manifest.issue_required == ["developer.md", "verified.md"]


def test_artifact_manifest_accepts_explicit_spec_defaults():
    p = ProjectConfig(
        name="test",
        key_prefix="TST",
        artifact_manifest={
            "session_required": [
                "task-checklist.md",
                "verification-checklist.md",
                "self-review.md",
                "pm-response.md",
                "insights.yaml",
            ],
            "issue_required": ["developer.md", "verified.md"],
        },
    )
    assert "self-review.md" in p.artifact_manifest.session_required
    assert "verified.md" in p.artifact_manifest.issue_required


def test_artifact_manifest_accepts_project_specific_lists():
    p = ProjectConfig(
        name="test",
        key_prefix="TST",
        artifact_manifest={
            "session_required": ["only-this.md"],
            "issue_required": [],
        },
    )
    assert p.artifact_manifest.session_required == ["only-this.md"]
    assert p.artifact_manifest.issue_required == []


def test_artifact_manifest_rejects_unknown_keys():
    """`extra=forbid` on the requirements model — typos must fail fast."""
    with pytest.raises(ValidationError):
        ArtifactManifestRequirements.model_validate(
            {"session_required": [], "issue_required": [], "typo": "nope"}
        )


def test_artifact_manifest_rejects_non_list_values():
    with pytest.raises(ValidationError):
        ArtifactManifestRequirements.model_validate(
            {"session_required": "not-a-list", "issue_required": []}
        )

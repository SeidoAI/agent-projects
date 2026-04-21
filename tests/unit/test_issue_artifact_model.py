"""IssueArtifactEntry + IssueArtifactManifest models."""

import pytest
from pydantic import ValidationError

from tripwire.models.issue_artifacts import IssueArtifactEntry, IssueArtifactManifest


def test_issue_artifact_entry_minimal():
    entry = IssueArtifactEntry(
        name="developer",
        file="developer.md",
        template="developer.md.j2",
        produced_by="execution-agent",
        required_at_status="in_review",
    )
    assert entry.owned_by == "execution-agent"  # defaults from produced_by
    assert entry.required is True


def test_issue_artifact_entry_keeps_explicit_owned_by():
    entry = IssueArtifactEntry(
        name="developer",
        file="developer.md",
        template="developer.md.j2",
        produced_by="execution-agent",
        owned_by="verification-agent",
        required_at_status="in_review",
    )
    assert entry.owned_by == "verification-agent"


def test_issue_artifact_manifest_loads():
    manifest = IssueArtifactManifest(
        artifacts=[
            {
                "name": "developer",
                "file": "developer.md",
                "template": "developer.md.j2",
                "produced_by": "execution-agent",
                "required_at_status": "in_review",
            }
        ]
    )
    assert len(manifest.artifacts) == 1
    assert manifest.artifacts[0].name == "developer"


def test_issue_artifact_entry_rejects_unknown_field():
    with pytest.raises(ValidationError):
        IssueArtifactEntry(
            name="x",
            file="x.md",
            template="x.md.j2",
            produced_by="execution-agent",
            required_at_status="in_review",
            bogus="nope",
        )

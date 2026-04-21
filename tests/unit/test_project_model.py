"""ProjectConfig override fields added in v0.7b."""

from tripwire.models.project import ProjectConfig


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

"""Issue artifact store: shipped manifest + overrides + status ordering."""

from pathlib import Path

import yaml

from tripwire.core.issue_artifact_store import (
    load_issue_artifact_manifest,
    status_at_or_past,
)


def test_load_default_manifest(tmp_path_project: Path):
    manifest = load_issue_artifact_manifest(tmp_path_project)
    names = {e.name for e in manifest.artifacts}
    assert names == {"developer", "verified"}

    developer = next(e for e in manifest.artifacts if e.name == "developer")
    assert developer.required_at_status == "in_review"
    assert developer.produced_by == "execution-agent"

    verified = next(e for e in manifest.artifacts if e.name == "verified")
    assert verified.required_at_status == "verified"


def test_status_at_or_past_default_order():
    assert status_at_or_past("in_review", "in_review") is True
    assert status_at_or_past("verified", "in_review") is True
    assert status_at_or_past("executing", "in_review") is False
    assert status_at_or_past("completed", "verified") is True
    assert status_at_or_past("planned", "queued") is False


def test_status_at_or_past_unknown_returns_false():
    assert status_at_or_past("qa", "in_review") is False
    assert status_at_or_past("in_review", "qa") is False


def test_status_at_or_past_session_status_default_order():
    """v0.11.1: helper accepts enum_name='session_status' for session-side
    callers. Both default lifecycle enums share the canonical order today."""
    assert (
        status_at_or_past("completed", "in_review", enum_name="session_status") is True
    )
    assert (
        status_at_or_past("in_review", "completed", enum_name="session_status") is False
    )
    assert (
        status_at_or_past("executing", "completed", enum_name="session_status") is False
    )
    assert status_at_or_past("verified", "verified", enum_name="session_status") is True


def test_status_at_or_past_side_states_short_circuit():
    """v0.12: side states (paused/abandoned/failed/deferred) are off-lifecycle.

    Real-world bug: a project whose session_status.yaml lists `paused` after
    `completed` would have `status_at_or_past("paused", "completed")` return
    True (because index-of-paused > index-of-completed) — incorrectly
    demanding completed-state artifacts from a paused session. The
    short-circuit fixes this regardless of enum ordering.
    """
    thresholds = (
        "planned",
        "queued",
        "executing",
        "in_review",
        "verified",
        "completed",
    )
    for side in ("paused", "abandoned", "failed", "deferred"):
        for threshold in thresholds:
            assert status_at_or_past(side, threshold) is False, (
                f"side state {side!r} unexpectedly past threshold {threshold!r}"
            )
            assert (
                status_at_or_past(side, threshold, enum_name="session_status") is False
            ), (
                f"side state {side!r} unexpectedly past threshold {threshold!r} "
                "(session_status)"
            )


def test_project_override_appends(tmp_path_project: Path):
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["issue_artifact_manifest_overrides"] = [
        {
            "name": "security-audit",
            "file": "security-audit.md",
            "template": "security-audit.md.j2",
            "produced_by": "execution-agent",
            "required_at_status": "completed",
        }
    ]
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    manifest = load_issue_artifact_manifest(tmp_path_project)
    names = {e.name for e in manifest.artifacts}
    assert "security-audit" in names


def test_project_override_replaces_by_name(tmp_path_project: Path):
    """Overrides replace shipped entries with the same name."""
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["issue_artifact_manifest_overrides"] = [
        {
            "name": "developer",
            "file": "dev-notes.md",
            "template": "dev-notes.md.j2",
            "produced_by": "execution-agent",
            "required_at_status": "in_review",
        }
    ]
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    manifest = load_issue_artifact_manifest(tmp_path_project)
    developer = next(e for e in manifest.artifacts if e.name == "developer")
    assert developer.file == "dev-notes.md"

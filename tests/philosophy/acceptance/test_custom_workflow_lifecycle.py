"""A custom workflow declared only in YAML can be created and moved.

Philosophy §9 ("Specs declare, validate enforces, agents execute, CLI
codifies") makes a load-bearing promise:

    *"Agents extend tripwire by editing YAML. No Python knowledge needed."*

This test is the executable proof of that promise. A new workflow
declared entirely in ``workflow.yaml`` — with no source-tree edits, no
new Python class, no registry registration — must produce a working
workflow you can:

  1. validate (the loader accepts the declaration)
  2. instantiate (an instance file at the declared ``storage_path`` loads)
  3. transition (``execute_transition`` flips the status field and persists)

If any of these fail, the framework has silently regressed on §9 and
the philosophy doc is fiction.
"""

from __future__ import annotations

from tests.philosophy.conftest import write_instance_file, write_workflow_yaml
from tripwire.core.workflow.instance_io import load_instance
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.transitions import execute_transition

RELEASE_TRACKING_WORKFLOW = {
    "release-tracking": {
        "actor": "pm-agent",
        "trigger": "release.declare",
        "brief-description": "Track a release from drafting to publication.",
        "instance": {
            "storage_path": "instances/releases/{instance_id}/release.yaml",
            "status_field": "status",
            "status_enum": ["drafting", "ready_to_publish", "published"],
            "required_fields": ["id", "status", "name"],
            "instance_id_field": "id",
        },
        "statuses": [
            {"id": "drafting"},
            {"id": "ready_to_publish"},
            {"id": "published", "terminal": True},
        ],
        "routes": [
            {
                "id": "drafting-to-ready",
                "actor": "pm-agent",
                "from": "drafting",
                "to": "ready_to_publish",
                "kind": "forward",
            },
            {
                "id": "ready-to-published",
                "actor": "pm-agent",
                "from": "ready_to_publish",
                "to": "published",
                "kind": "forward",
            },
        ],
    }
}


def test_yaml_only_workflow_can_be_loaded(minimal_project):
    """§9: the loader accepts a workflow declared with no Python support."""
    write_workflow_yaml(minimal_project, RELEASE_TRACKING_WORKFLOW)

    spec = load_workflows(minimal_project)
    assert "release-tracking" in spec.workflows, (
        "philosophy §9 regressed: a YAML-declared workflow did not load. "
        "Adding a workflow MUST be possible by editing workflow.yaml alone."
    )
    workflow = spec.workflows["release-tracking"]
    assert workflow.instance is not None
    assert workflow.instance.status_enum == [
        "drafting",
        "ready_to_publish",
        "published",
    ]


def test_yaml_only_workflow_can_be_instantiated(minimal_project):
    """§9: an instance file at the declared ``storage_path`` loads cleanly."""
    write_workflow_yaml(minimal_project, RELEASE_TRACKING_WORKFLOW)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="v1.0",
        data={"id": "v1.0", "status": "drafting", "name": "First release"},
    )

    instance = load_instance(minimal_project, "release-tracking", "v1.0")
    assert instance["status"] == "drafting"
    assert instance["name"] == "First release"


def test_yaml_only_workflow_can_be_transitioned(minimal_project):
    """§9: ``tripwire transition`` moves the instance through its declared
    statuses. The status field on disk reflects the new value.

    This is the headline claim of the validate-driven-workflows thesis:
    the agent declares structure in YAML, and the framework executes
    transitions against that declaration alone — no per-workflow class.
    """
    write_workflow_yaml(minimal_project, RELEASE_TRACKING_WORKFLOW)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="v1.0",
        data={"id": "v1.0", "status": "drafting", "name": "First release"},
    )

    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="v1.0",
        target_status="ready_to_publish",
    )
    assert result.ok, (
        f"first transition failed: reason={result.reason!r} "
        f"message={result.message!r}. philosophy §9 promises YAML-only "
        f"workflows transition without Python support."
    )

    on_disk = load_instance(minimal_project, "release-tracking", "v1.0")
    assert on_disk["status"] == "ready_to_publish"

    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="v1.0",
        target_status="published",
    )
    assert result.ok, f"second transition failed: {result.message!r}"

    on_disk = load_instance(minimal_project, "release-tracking", "v1.0")
    assert on_disk["status"] == "published"


def test_yaml_only_workflow_rejects_illegal_transition(minimal_project):
    """§9: the executor enforces declared routes — illegal transitions are
    rejected with a structured reason, not silently allowed.

    This is the *enforce* half of "specs declare, validate enforces".
    Without it, a YAML declaration would be advisory, not authoritative.
    """
    write_workflow_yaml(minimal_project, RELEASE_TRACKING_WORKFLOW)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="v1.0",
        data={"id": "v1.0", "status": "drafting", "name": "First release"},
    )

    # drafting → published is NOT a declared route (must go via ready_to_publish).
    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="v1.0",
        target_status="published",
    )
    assert not result.ok, (
        "philosophy §9 regressed: an illegal transition was accepted. "
        "Declared routes are authoritative; the executor MUST reject "
        "moves that aren't in workflow.yaml."
    )
    assert result.reason, "rejection must carry a structured reason"

    on_disk = load_instance(minimal_project, "release-tracking", "v1.0")
    assert on_disk["status"] == "drafting", (
        "rejected transition must leave the instance unchanged"
    )

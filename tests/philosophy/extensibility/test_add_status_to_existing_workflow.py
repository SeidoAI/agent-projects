"""Workflows can be evolved without breaking existing instances.

Philosophy §9 promises:

    *"Agents extend tripwire by editing YAML. ... New workflows declare
    YAML; new invariants are validators. Three orthogonal extension
    points."*

For that promise to hold, **existing** instances must survive *changes*
to their workflow declaration. Specifically:

  - Adding a new status leaves existing routes legal and existing
    instances valid.
  - Adding a new route between existing statuses does not invalidate
    transitions that already happened.
  - Adding a new validator to a workflow doesn't retroactively reject
    instances that pre-date it (it produces *findings* the agent
    addresses next time).

If those evolutions break things, agents have to either edit Python
(violating §9) or keep workflows immutable (violating the "extend
via YAML" promise).
"""

from __future__ import annotations

import copy

from tests.philosophy.conftest import write_instance_file, write_workflow_yaml
from tripwire.core.workflow.instance_io import load_instance
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.transitions import execute_transition

# Baseline workflow used across the tests: 2 statuses, 1 route.
BASELINE_WORKFLOW: dict = {
    "release-tracking": {
        "actor": "pm-agent",
        "trigger": "release.declare",
        "instance": {
            "storage_path": "instances/releases/{instance_id}/release.yaml",
            "status_field": "status",
            "status_enum": ["drafting", "published"],
            "required_fields": ["id", "status"],
            "instance_id_field": "id",
        },
        "statuses": [
            {"id": "drafting"},
            {"id": "published", "terminal": True},
        ],
        "routes": [
            {
                "id": "drafting-to-published",
                "actor": "pm-agent",
                "from": "drafting",
                "to": "published",
                "kind": "forward",
            }
        ],
    }
}


def test_adding_a_status_does_not_invalidate_existing_instances(minimal_project):
    """Add ``ready_to_publish`` between ``drafting`` and ``published``.

    An instance already at ``drafting`` should still load, and a
    ``drafting → published`` transition (via the preserved direct route)
    should still pass.
    """
    write_workflow_yaml(minimal_project, BASELINE_WORKFLOW)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="v1.0",
        data={"id": "v1.0", "status": "drafting"},
    )

    # Evolve: insert a new status + a new route. Keep the original
    # direct route too, so we can prove the EXISTING route remains
    # legal after evolution.
    evolved = copy.deepcopy(BASELINE_WORKFLOW)
    evolved["release-tracking"]["instance"]["status_enum"] = [
        "drafting",
        "ready_to_publish",
        "published",
    ]
    evolved["release-tracking"]["statuses"] = [
        {"id": "drafting"},
        {"id": "ready_to_publish"},
        {"id": "published", "terminal": True},
    ]
    # Both new edges: drafting → ready_to_publish AND ready_to_publish →
    # published. Skipping the second would leave ready_to_publish as a
    # trap status, and the workflow validator (correctly) rejects that.
    evolved["release-tracking"]["routes"].extend(
        [
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
        ]
    )
    write_workflow_yaml(minimal_project, evolved)

    # Existing instance still loads cleanly.
    instance = load_instance(minimal_project, "release-tracking", "v1.0")
    assert instance["status"] == "drafting", (
        "philosophy §9 regressed: adding a status invalidated an existing "
        "instance. Workflow evolution MUST be backwards-compatible for "
        "instances at unchanged statuses."
    )

    # Pre-existing route still passes.
    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="v1.0",
        target_status="published",
    )
    assert result.ok, (
        f"adding a new status broke a previously-legal route: "
        f"reason={result.reason!r} message={result.message!r}"
    )


def test_adding_a_route_keeps_old_routes_legal(minimal_project):
    """Adding ``drafting → ready_to_publish`` while keeping
    ``drafting → published`` leaves the second route legal.

    Sanity check: route additions are additive, not replacements.
    """
    # Start with the evolved shape from the previous test as baseline
    # (3 statuses, 1 route: drafting → published).
    workflow = {
        "release-tracking": {
            "actor": "pm-agent",
            "trigger": "release.declare",
            "instance": {
                "storage_path": "instances/releases/{instance_id}/release.yaml",
                "status_field": "status",
                "status_enum": ["drafting", "ready_to_publish", "published"],
                "required_fields": ["id", "status"],
                "instance_id_field": "id",
            },
            "statuses": [
                {"id": "drafting"},
                {"id": "ready_to_publish"},
                {"id": "published", "terminal": True},
            ],
            "routes": [
                {
                    "id": "drafting-to-published",
                    "actor": "pm-agent",
                    "from": "drafting",
                    "to": "published",
                    "kind": "forward",
                }
            ],
        }
    }
    write_workflow_yaml(minimal_project, workflow)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="alpha",
        data={"id": "alpha", "status": "drafting"},
    )

    # Add new routes — drafting → ready_to_publish AND ready_to_publish
    # → published. The original direct route stays. ready_to_publish
    # needs an outbound or `workflow/trap_status` correctly rejects it.
    workflow["release-tracking"]["routes"].extend(
        [
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
        ]
    )
    write_workflow_yaml(minimal_project, workflow)

    # The new route works for a new instance.
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="beta",
        data={"id": "beta", "status": "drafting"},
    )
    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="beta",
        target_status="ready_to_publish",
    )
    assert result.ok, f"new route rejected: {result.message!r}"

    # The original route ALSO still works for an instance that wants it.
    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="alpha",
        target_status="published",
    )
    assert result.ok, (
        "philosophy §9 regressed: adding a parallel route broke the "
        "original route. Route evolution must be additive."
    )


def test_incomplete_evolution_is_rejected_by_validator(minimal_project):
    """§9: ``tripwire validate`` enforces invariants — adding a status
    without an outbound route (a "trap status") is caught and rejected.

    This is the second half of "specs declare, validate enforces". The
    declaration is YAML; the enforcement runs at transition time. An
    incomplete YAML evolution that would silently strand instances at
    a dead-end status MUST surface as a structured rejection.
    """
    write_workflow_yaml(minimal_project, BASELINE_WORKFLOW)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="v1.0",
        data={"id": "v1.0", "status": "drafting"},
    )

    # Add `ready_to_publish` WITHOUT an outbound route. Non-terminal +
    # no exit = trap. Validator must catch it.
    broken = copy.deepcopy(BASELINE_WORKFLOW)
    broken["release-tracking"]["instance"]["status_enum"] = [
        "drafting",
        "ready_to_publish",
        "published",
    ]
    broken["release-tracking"]["statuses"].insert(1, {"id": "ready_to_publish"})
    broken["release-tracking"]["routes"].append(
        {
            "id": "drafting-to-ready",
            "actor": "pm-agent",
            "from": "drafting",
            "to": "ready_to_publish",
            "kind": "forward",
        }
    )
    write_workflow_yaml(minimal_project, broken)

    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="v1.0",
        target_status="ready_to_publish",
    )
    assert not result.ok, (
        "philosophy §9 regressed: an incomplete workflow evolution "
        "(trap status, no outbound route) was accepted. `tripwire "
        "validate` MUST catch declarative drift; that's the whole "
        "point of validate-as-accountability-surface."
    )
    assert "trap_status" in (result.message or ""), (
        f"trap-status finding expected; got: {result.message!r}"
    )


def test_adding_a_workflow_does_not_affect_other_workflows(minimal_project):
    """Adding a second workflow to ``workflow.yaml`` doesn't disturb the
    first.

    The orthogonal-extension claim: new workflows declare YAML — they
    don't interact with existing ones. An instance of workflow A
    transitioning correctly before workflow B is declared should
    continue to transition correctly after.
    """
    write_workflow_yaml(minimal_project, BASELINE_WORKFLOW)
    write_instance_file(
        minimal_project,
        "instances/releases/{instance_id}/release.yaml",
        instance_id="v1.0",
        data={"id": "v1.0", "status": "drafting"},
    )

    # Add a completely unrelated workflow alongside release-tracking.
    extended = copy.deepcopy(BASELINE_WORKFLOW)
    extended["bug-triage"] = {
        "actor": "pm-agent",
        "trigger": "bug.report",
        "instance": {
            "storage_path": "instances/bugs/{instance_id}/bug.yaml",
            "status_field": "status",
            "status_enum": ["reported", "triaged"],
            "required_fields": ["id", "status"],
            "instance_id_field": "id",
        },
        "statuses": [
            {"id": "reported"},
            {"id": "triaged", "terminal": True},
        ],
        "routes": [
            {
                "id": "reported-to-triaged",
                "actor": "pm-agent",
                "from": "reported",
                "to": "triaged",
                "kind": "forward",
            }
        ],
    }
    write_workflow_yaml(minimal_project, extended)

    spec = load_workflows(minimal_project)
    assert {"release-tracking", "bug-triage"} <= spec.workflows.keys()

    # release-tracking still transitions.
    result = execute_transition(
        minimal_project,
        workflow_id="release-tracking",
        instance_id="v1.0",
        target_status="published",
    )
    assert result.ok, (
        "philosophy §9 regressed: declaring a second workflow disturbed "
        "the first. Workflows must be orthogonal extension points."
    )

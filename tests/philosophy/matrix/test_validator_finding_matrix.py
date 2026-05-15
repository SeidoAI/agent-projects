"""Behavioural matrix: each deviation type produces a specific rejection.

Philosophy §3 makes tripwires the agent's control-loop signal:

    *"Validators don't try to prevent the deviation — they catch it
    after. That asymmetry is the point. Tripwire only fires on
    deviation."*

For that signal to be useful, it has to be **stable**: an agent that
sees ``transition_not_reachable`` today must see the same code for
the same deviation tomorrow. If a refactor silently renames a
rejection reason or starts producing a different finding for the
same violation, every skill markdown that greps for the old name
breaks — quietly.

This matrix pins one row per deviation type. Adding a new declared
rejection reason MUST come with a row here. Renaming an existing one
breaks this test, surfacing the cost of the rename.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.philosophy.conftest import write_instance_file, write_workflow_yaml
from tripwire.core.workflow.transitions import (
    TransitionError,
    execute_transition,
)

# ----- workflow shapes used as setup ingredients -----------------------------

THREE_STATUS_LINEAR = {
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


# ----- scenarios -------------------------------------------------------------


def _scenario_unknown_workflow(project_dir):
    write_workflow_yaml(project_dir, THREE_STATUS_LINEAR)
    write_instance_file(
        project_dir,
        "instances/releases/{instance_id}/release.yaml",
        "v1.0",
        {"id": "v1.0", "status": "drafting"},
    )
    return {
        "workflow_id": "nonexistent-workflow",
        "instance_id": "v1.0",
        "target_status": "drafting",
    }


def _scenario_unknown_status(project_dir):
    write_workflow_yaml(project_dir, THREE_STATUS_LINEAR)
    write_instance_file(
        project_dir,
        "instances/releases/{instance_id}/release.yaml",
        "v1.0",
        {"id": "v1.0", "status": "drafting"},
    )
    return {
        "workflow_id": "release-tracking",
        "instance_id": "v1.0",
        "target_status": "made_up_status",
    }


def _scenario_illegal_transition(project_dir):
    """drafting → published is not a declared route (must go via ready_to_publish)."""
    write_workflow_yaml(project_dir, THREE_STATUS_LINEAR)
    write_instance_file(
        project_dir,
        "instances/releases/{instance_id}/release.yaml",
        "v1.0",
        {"id": "v1.0", "status": "drafting"},
    )
    return {
        "workflow_id": "release-tracking",
        "instance_id": "v1.0",
        "target_status": "published",
    }


def _scenario_missing_instance(project_dir):
    write_workflow_yaml(project_dir, THREE_STATUS_LINEAR)
    # …deliberately no instance file written.
    return {
        "workflow_id": "release-tracking",
        "instance_id": "nope",
        "target_status": "ready_to_publish",
    }


def _scenario_workflow_without_instance_block(project_dir):
    """Workflow declared without an ``instance:`` block — the executor
    can't materialise on-disk state and must surface that loud.
    """
    no_instance = {
        "release-tracking": {
            "actor": "pm-agent",
            "trigger": "release.declare",
            # …no `instance:` block.
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
    write_workflow_yaml(project_dir, no_instance)
    return {
        "workflow_id": "release-tracking",
        "instance_id": "anything",
        "target_status": "published",
    }


def _scenario_trap_status_workflow(project_dir):
    """A non-terminal status with an inbound route but no outbound is
    a "trap" — work that enters can't leave. The transition gate (via
    the workflow tripwire) catches it.

    Note the fixture shape: ``dead_end`` has an inbound (from
    ``drafting``) so it doesn't trip ``workflow/unreachable_status``,
    and ``published`` has its own inbound (from ``drafting``) so the
    terminal status is reachable. The ONLY remaining issue is
    ``dead_end`` having no outbound while being non-terminal — pure
    trap.
    """
    trap_workflow = {
        "release-tracking": {
            "actor": "pm-agent",
            "trigger": "release.declare",
            "instance": {
                "storage_path": "instances/releases/{instance_id}/release.yaml",
                "status_field": "status",
                "status_enum": ["drafting", "dead_end", "published"],
                "required_fields": ["id", "status"],
                "instance_id_field": "id",
            },
            "statuses": [
                {"id": "drafting"},
                {"id": "dead_end"},  # non-terminal, no outbound = trap
                {"id": "published", "terminal": True},
            ],
            "routes": [
                {
                    "id": "drafting-to-dead-end",
                    "actor": "pm-agent",
                    "from": "drafting",
                    "to": "dead_end",
                    "kind": "forward",
                },
                {
                    "id": "drafting-to-published",
                    "actor": "pm-agent",
                    "from": "drafting",
                    "to": "published",
                    "kind": "forward",
                },
            ],
        }
    }
    write_workflow_yaml(project_dir, trap_workflow)
    write_instance_file(
        project_dir,
        "instances/releases/{instance_id}/release.yaml",
        "v1.0",
        {"id": "v1.0", "status": "drafting"},
    )
    return {
        "workflow_id": "release-tracking",
        "instance_id": "v1.0",
        "target_status": "dead_end",
    }


# ----- the matrix ------------------------------------------------------------
#
# Each row: (scenario name, setup callable, expectation kind, expected match).
#
# `kind` is one of:
#   - "raises"   — execute_transition raises TransitionError; match against str(exc)
#   - "rejects"  — execute_transition returns TransitionResult(ok=False);
#                  match against `result.reason` (the agent-facing rejection code)
#
# The expected match is a substring — full strings are too brittle, but the
# substring chosen MUST be the load-bearing identifier the agent / skill
# markdown grep for. If a future refactor changes the substring, fix the skill
# markdown too.

MatrixRow = tuple[str, Callable, str, str]

MATRIX: list[MatrixRow] = [
    (
        "unknown workflow id",
        _scenario_unknown_workflow,
        "raises",
        "workflow",  # error mentions the workflow name
    ),
    (
        "unknown target status",
        _scenario_unknown_status,
        "raises",
        "unknown status",
    ),
    (
        "illegal transition (no declared route)",
        _scenario_illegal_transition,
        "rejects",
        "transition_not_reachable",
    ),
    (
        "missing instance file",
        _scenario_missing_instance,
        "raises",
        "not found",
    ),
    (
        "workflow without instance block",
        _scenario_workflow_without_instance_block,
        "raises",
        "instance",  # error mentions the missing instance shape
    ),
    (
        "trap status (non-terminal, no outbound)",
        _scenario_trap_status_workflow,
        "rejects",
        "trap_status",
    ),
]


@pytest.mark.parametrize(
    "scenario_name,setup,kind,expected",
    MATRIX,
    ids=[row[0] for row in MATRIX],
)
def test_validator_response_to_deviation(
    scenario_name, setup, kind, expected, minimal_project
):
    """For each declared deviation, the executor produces the documented
    response shape (raise vs. reject) and the documented identifier.

    A failure here means an agent looking up "what happens when X
    fails?" against the skill markdown will see one thing and the
    executor will do another. That's the exact drift this matrix is
    here to catch.
    """
    kwargs = setup(minimal_project)

    if kind == "raises":
        with pytest.raises(Exception) as exc_info:
            execute_transition(minimal_project, **kwargs)
        message = str(exc_info.value)
        # We accept both TransitionError (input errors) and
        # InstanceNotFoundError (instance file missing) — both are
        # exception-shaped responses, distinct from the rejection-
        # result shape. Matrix rows pick one or the other.
        assert isinstance(exc_info.value, (TransitionError, FileNotFoundError)), (
            f"unexpected exception type {type(exc_info.value).__name__} for "
            f"scenario {scenario_name!r}: {message}"
        )
        assert expected in message.lower(), (
            f"scenario {scenario_name!r} should raise with {expected!r} in "
            f"the message; got: {message!r}"
        )
    elif kind == "rejects":
        result = execute_transition(minimal_project, **kwargs)
        assert not result.ok, f"scenario {scenario_name!r} should reject; got ok=True"
        haystack = f"{result.reason or ''} {result.message or ''}".lower()
        assert expected in haystack, (
            f"scenario {scenario_name!r} should reject with {expected!r} "
            f"in reason/message; got reason={result.reason!r} "
            f"message={result.message!r}"
        )
    else:
        raise AssertionError(f"unknown matrix kind: {kind!r}")

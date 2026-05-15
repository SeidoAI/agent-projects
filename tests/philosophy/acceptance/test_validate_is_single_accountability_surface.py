"""``tripwire validate`` surfaces findings across every declared workflow.

Philosophy §9 says:

    *"`tripwire validate` enforces invariants. Always available. Reads
    every instance file, runs every declared validator, produces
    findings. Single accountability surface across every workflow."*

The headline claim is **single surface**: one invocation, every
finding. A project with multiple workflows isn't N validation passes
(one per workflow) — it's one pass that produces the union of
findings. Skill markdown can tell the agent "run `tripwire validate`"
without qualifying which workflow, and that one command is the whole
accountability story.

If a future refactor split validation into per-workflow commands, or
silently dropped findings from workflows the agent didn't explicitly
name, §9 dies and the agent has to learn N separate accountability
surfaces. This test pins the single-surface promise.
"""

from __future__ import annotations

from tests.philosophy.conftest import write_workflow_yaml
from tripwire.core.validator import validate_project

# Two workflows, each containing one deliberate structural violation.
# The point is not which violations specifically — it's that ONE
# validate() call surfaces BOTH workflows' problems.
TWO_BROKEN_WORKFLOWS = {
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
            # Violation: route's `to` references a status that doesn't
            # exist in this workflow. Should surface as
            # `workflow/cross_link_unknown_status` or similar.
            {
                "id": "drafting-to-missing",
                "actor": "pm-agent",
                "from": "drafting",
                "to": "nonexistent_status",
                "kind": "forward",
            }
        ],
    },
    "bug-triage": {
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
            # Violation: duplicate status id. Should surface as
            # `workflow/duplicate_status_id`.
            {"id": "reported"},
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
    },
}


def test_validate_surfaces_findings_from_every_declared_workflow(minimal_project):
    """Two workflows; both broken; one ``validate_project`` call;
    findings name both.

    The §9 promise is that an agent runs ``tripwire validate`` and
    sees the whole landscape. If the report names only one workflow's
    problems, the agent fixes that, re-runs, sees the second one, and
    discovers validate isn't actually a single surface — it's an
    iterative one.
    """
    write_workflow_yaml(minimal_project, TWO_BROKEN_WORKFLOWS)

    report = validate_project(minimal_project, validator_ids=["v_workflow_well_formed"])

    # Findings should mention both workflow names.
    finding_fields = [f.field or "" for f in report.findings]
    finding_messages = [f.message or "" for f in report.findings]
    blob = " ".join(finding_fields + finding_messages)

    assert "release-tracking" in blob, (
        "Philosophy §9 regressed: ONE validate() call did not surface\n"
        "findings from the `release-tracking` workflow. The 'single\n"
        "accountability surface' claim requires the report to span every\n"
        "declared workflow without re-running.\n"
        f"\nfindings: {[(f.code, f.field, f.message[:60]) for f in report.findings]}"
    )
    assert "bug-triage" in blob, (
        "Philosophy §9 regressed: ONE validate() call did not surface\n"
        "findings from the `bug-triage` workflow.\n"
        f"\nfindings: {[(f.code, f.field, f.message[:60]) for f in report.findings]}"
    )


def test_validate_runs_zero_validators_zero_findings(minimal_project):
    """Sanity / null case: a well-formed project with no workflows
    declared returns a clean report. The single surface still works
    when the surface is empty.

    This pins a side promise of §9: validate is *always* available —
    a project that hasn't declared workflows yet doesn't error, it
    just produces an empty (or near-empty) findings list. The
    accountability surface is a no-op, not a hard error.
    """
    # No workflow.yaml is written — the minimal_project fixture
    # produces just project.yaml + instances/ skeleton.
    report = validate_project(minimal_project, validator_ids=["v_workflow_well_formed"])
    # The check returns [] when workflow.yaml is absent (opt-in).
    assert all(f.code != "workflow/parse_error" for f in report.findings), (
        f"validate on a no-workflow project should not parse-error; got "
        f"{[f for f in report.findings if f.code == 'workflow/parse_error']}"
    )

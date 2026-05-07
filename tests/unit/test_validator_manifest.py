"""Validator rules for manifest ownership (v0.6a additions)."""


def test_validator_rejects_invalid_produced_by(tmp_project_manifest):
    """manifest_schema/produced_by_valid fires for unknown agent type."""
    from tripwire.core.validator import validate_project

    proj = tmp_project_manifest(
        artifacts=[
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "planning",
                "produced_by": "wizard",
                "owned_by": "pm",
                "required": True,
            },
        ]
    )
    result = validate_project(proj)
    assert any(f.code == "manifest_schema/produced_by_valid" for f in result.findings)


def test_validator_warns_on_phase_ownership_inconsistent(tmp_project_manifest):
    """manifest_schema/phase_ownership_consistent warns when PM owns an
    artifact PRODUCED by an agent during executing/in_review.

    v0.12: the rule's signal is "produced_by != owned_by during agent
    phase" — the v0.5 bug where PM was charged with files an agent
    actually wrote. PM-owned-and-PM-produced artifacts (e.g.
    pr-review.yaml at in_review) are deliberately PM work and don't
    fire the heuristic.
    """
    from tripwire.core.validator import validate_project

    proj = tmp_project_manifest(
        artifacts=[
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "executing",
                "produced_by": "execution-agent",
                "owned_by": "pm",
                "required": True,
            },
        ]
    )
    result = validate_project(proj)
    warnings = [
        f
        for f in result.findings
        if f.code == "manifest_schema/phase_ownership_consistent"
    ]
    assert len(warnings) == 1
    assert warnings[0].severity == "warning"


def test_phase_ownership_consistent_silent_when_pm_authors_and_owns(
    tmp_project_manifest,
):
    """v0.12: PM-authored AND PM-owned at executing/in_review is the
    canonical pr-review.yaml shape — must not trip the heuristic."""
    from tripwire.core.validator import validate_project

    proj = tmp_project_manifest(
        artifacts=[
            {
                "name": "pr-review",
                "file": "pr-review.yaml",
                "template": "pr-review.yaml.j2",
                "produced_at": "in_review",
                "produced_by": "pm",
                "owned_by": "pm",
                "required": True,
            },
        ]
    )
    result = validate_project(proj)
    warnings = [
        f
        for f in result.findings
        if f.code == "manifest_schema/phase_ownership_consistent"
    ]
    assert warnings == []

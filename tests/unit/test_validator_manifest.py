"""Validator rules for manifest ownership (v0.6a additions)."""


def test_validator_rejects_invalid_produced_by(tmp_project_manifest):
    """manifest_schema/produced_by_valid fires for unknown agent type."""
    from keel.core.validator import validate_project

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
    artifact produced during implementing phase."""
    from keel.core.validator import validate_project

    proj = tmp_project_manifest(
        artifacts=[
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "implementing",
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
    assert len(warnings) == 1
    assert warnings[0].severity == "warning"

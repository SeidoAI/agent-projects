"""Validator rules for handoff.yaml (v0.6a)."""

from pathlib import Path


def _write_session_yaml(project_dir: Path, session_id: str, status: str) -> None:
    sess = project_dir / "sessions" / session_id
    sess.mkdir(parents=True)
    (sess / "session.yaml").write_text(
        f"""---
uuid: 11111111-1111-1111-1111-111111111111
id: {session_id}
name: test
agent: pm
status: {status}
issues: []
repos: []
---
"""
    )


def test_handoff_schema_required_at_queued(tmp_project_manifest):
    """Session in queued without handoff.yaml raises error."""
    from tripwire.core.validator import validate_project

    project_dir = tmp_project_manifest([])
    _write_session_yaml(project_dir, "session-x", "queued")
    result = validate_project(project_dir)
    assert any(f.code == "handoff_schema/required_at_queued" for f in result.findings)


def test_handoff_schema_planned_does_not_require_handoff(tmp_project_manifest):
    """A session in `planned` status should NOT require handoff.yaml."""
    from tripwire.core.validator import validate_project

    project_dir = tmp_project_manifest([])
    _write_session_yaml(project_dir, "session-x", "planned")
    result = validate_project(project_dir)
    assert not any(
        f.code == "handoff_schema/required_at_queued" for f in result.findings
    )


def test_handoff_schema_branch_format(tmp_project_manifest):
    """An invalid branch in handoff.yaml surfaces as branch_format error."""
    from tripwire.core.validator import validate_project

    project_dir = tmp_project_manifest([])
    _write_session_yaml(project_dir, "session-x", "queued")
    handoff = project_dir / "sessions" / "session-x" / "handoff.yaml"
    handoff.write_text(
        """---
uuid: 22222222-2222-2222-2222-222222222222
session_id: session-x
handoff_at: 2026-04-15T00:00:00Z
handed_off_by: pm
branch: not-valid
---
"""
    )
    result = validate_project(project_dir)
    assert any(f.code == "handoff_schema/branch_format" for f in result.findings)


def test_handoff_schema_valid_handoff_no_findings(tmp_project_manifest):
    """A well-formed handoff.yaml produces no handoff-schema findings."""
    from tripwire.core.validator import validate_project

    project_dir = tmp_project_manifest([])
    _write_session_yaml(project_dir, "session-x", "queued")
    handoff = project_dir / "sessions" / "session-x" / "handoff.yaml"
    handoff.write_text(
        """---
uuid: 33333333-3333-3333-3333-333333333333
session_id: session-x
handoff_at: 2026-04-15T00:00:00Z
handed_off_by: pm
branch: feat/some-valid-slug
---
"""
    )
    result = validate_project(project_dir)
    handoff_findings = [
        f for f in result.findings if f.code.startswith("handoff_schema/")
    ]
    assert handoff_findings == []

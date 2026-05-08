"""Regression tests for PM handoff #5 (WS6).

The handoff named four gaps in the v0.12 lifecycle. v0.13 fixes
A/C/D as data-only YAML edits; Gap B (squash-merge orphan branch)
gets a follow-up dedicated side-effect handler. These tests exercise
the routes' existence and the executor's transition behavior — they
do NOT reach into the legacy direct-status-write callers (those are
tracked as WS4-residual cutover work).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture
def project_with_v013_workflow(tmp_path: Path):
    """Init a minimal project with the full v0.13 coding-session workflow."""
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    # Use the shipped v0.13 template directly so the regression test
    # sees the same routes a real project would have post-migration.
    template_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "tripwire"
        / "templates"
        / "workflow.yaml.j2"
    )
    (tmp_path / "workflow.yaml").write_text(
        template_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    sessions_dir = tmp_path / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    return tmp_path


def _save_session_at_status(project_dir: Path, status: str) -> None:
    """Write a session.yaml at the given status."""
    sessions_dir = project_dir / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "session.yaml").write_text(
        dedent(
            f"""\
            ---
            uuid: 11111111-1111-4111-8111-111111111111
            id: test-session
            name: Test session
            agent: backend-coder
            issues: []
            repos: []
            status: {status}
            created_at: 2026-04-30T00:00:00Z
            updated_at: 2026-04-30T00:00:00Z
            ---
            """
        ),
        encoding="utf-8",
    )


def test_gap_c_paused_to_queued_route_exists(
    project_with_v013_workflow: Path,
) -> None:
    """Gap C: the documented recovery `paused → queued` exists in v0.13."""
    from tripwire.core.workflow.loader import load_workflows

    spec = load_workflows(project_with_v013_workflow)
    routes = spec.workflows["coding-session"].routes
    edges = {(r.from_ref, r.to_ref) for r in routes}
    assert ("paused", "queued") in edges


def test_gap_d_paused_to_completed_route_exists(
    project_with_v013_workflow: Path,
) -> None:
    """Gap D: the `never mind, leave completed` reversal exists in v0.13."""
    from tripwire.core.workflow.loader import load_workflows

    spec = load_workflows(project_with_v013_workflow)
    routes = spec.workflows["coding-session"].routes
    edges = {(r.from_ref, r.to_ref) for r in routes}
    assert ("paused", "completed") in edges


def test_gap_a_reopen_route_preserves_claude_session_id(
    project_with_v013_workflow: Path,
) -> None:
    """Gap A: the `completed → paused` reopen route declares
    runtime_state.claude_session_id in preserve_fields, so the
    executor's preserve-and-re-assert pass guarantees the field
    survives the transition.
    """
    from tripwire.core.workflow.loader import load_workflows

    spec = load_workflows(project_with_v013_workflow)
    reopen_route = next(
        r
        for r in spec.workflows["coding-session"].routes
        if r.id == "completed-to-paused-reopen"
    )
    assert "runtime_state.claude_session_id" in reopen_route.preserve_fields
    assert "runtime_state.worktrees" in reopen_route.preserve_fields


def test_v013_template_has_no_recovery_path_findings(
    project_with_v013_workflow: Path,
) -> None:
    """The shipped v0.13 template should not produce a
    `workflow/no_recovery_path` finding — every off-path status
    (paused, failed) has a route back to an on-path status.
    """
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    spec = load_workflows(project_with_v013_workflow)
    findings = validate_workflow_spec(
        spec,
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/no_recovery_path" not in codes

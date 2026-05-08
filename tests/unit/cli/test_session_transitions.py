"""Drift-prevention tests for the session-transition declarations.

In v0.13 the legacy ``_ALLOWED_TRANSITIONS`` map was deleted; transitions
are now declared in ``workflow.yaml`` and read by the executor at runtime.
These tests assert the shipped template's coding-session workflow uses
only ``SessionStatus`` member values for status ids, and that the
``verified → completed`` happy-path edge is declared (regression for
the v0.9 ``verified → done`` drift bug that pre-dated the unification).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core.workflow.loader import parse_workflow_spec
from tripwire.models.enums import SessionStatus


def _shipped_coding_session():
    template = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "tripwire"
        / "templates"
        / "workflow.yaml.j2"
    )
    raw = yaml.safe_load(template.read_text(encoding="utf-8"))
    spec = parse_workflow_spec(raw)
    return spec.workflows["coding-session"]


def test_template_uses_only_session_status_member_values() -> None:
    """Every status id in the shipped template is a SessionStatus value."""
    valid = {s.value for s in SessionStatus}
    workflow = _shipped_coding_session()
    for status in workflow.statuses:
        assert status.id in valid, f"status id {status.id!r} not in SessionStatus"


def test_template_routes_only_reference_session_status_members() -> None:
    """Route ``from``/``to`` must be SessionStatus values or boundary ports."""
    valid = {s.value for s in SessionStatus}
    workflow = _shipped_coding_session()
    for route in workflow.routes:
        for end in (route.from_ref, route.to_ref):
            if end.startswith(("source:", "sink:")):
                continue
            assert end in valid, f"route endpoint {end!r} not in SessionStatus"


def test_verified_can_transition_to_completed_in_template() -> None:
    """Regression: verified→completed must be a declared route."""
    workflow = _shipped_coding_session()
    assert any(
        r.from_ref == "verified" and r.to_ref == "completed" for r in workflow.routes
    )


def test_no_route_targets_legacy_done_status_in_template() -> None:
    """Regression: verified→done was the legacy drift that caused v0.9's
    enum/transition mismatch. The template must not declare it."""
    workflow = _shipped_coding_session()
    assert not any(r.to_ref == "done" for r in workflow.routes)

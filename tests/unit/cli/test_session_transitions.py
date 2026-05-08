"""Drift-prevention tests for the session-transition map.

The map at `cli/session.py::_ALLOWED_TRANSITIONS` is hand-maintained.
It pre-existed the Python `SessionStatus` enum and a value drifted
(`verified → done`) because nothing checked map values against the enum.
These tests close that loop: every key and every value must be a
member of `SessionStatus`.
"""

from __future__ import annotations

from tripwire.cli.session import _ALLOWED_TRANSITIONS
from tripwire.models.enums import SessionStatus


def test_allowed_transitions_only_uses_valid_statuses() -> None:
    """Every source and target in the transition map is a SessionStatus member."""
    valid = {s.value for s in SessionStatus}
    for src, targets in _ALLOWED_TRANSITIONS.items():
        assert src in valid, f"transition source {src!r} not in SessionStatus"
        for t in targets:
            assert t in valid, f"transition target {t!r} not in SessionStatus"


def test_verified_can_transition_to_completed() -> None:
    """Regression: verified→completed must be allowed (was verified→done)."""
    assert "completed" in _ALLOWED_TRANSITIONS["verified"]


def test_verified_cannot_transition_to_done() -> None:
    """Regression: verified→done was the legacy value that drifted from the enum."""
    assert "done" not in _ALLOWED_TRANSITIONS["verified"]

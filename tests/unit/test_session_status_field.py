"""Tests for KUI-110 Phase 2.1 — `AgentSession.status` typed as `SessionStatus`.

The field used to be a plain `str`. Pydantic accepted any string at
load time, which let `status: done` (a value not in `SessionStatus`)
land on disk. With this change Pydantic rejects unknown statuses at
``model_validate`` time, raising ``ValidationError``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tripwire.models.enums import SessionStatus
from tripwire.models.session import AgentSession


_BASE = {
    "uuid": "00000000-0000-4000-8000-000000000000",
    "id": "test",
    "name": "Test session",
    "agent": "backend-coder",
    "issues": [],
    "repos": [],
}


def test_session_status_invalid_string_raises() -> None:
    """`status: nonsense_value` → ValidationError."""
    with pytest.raises(ValidationError):
        AgentSession.model_validate({**_BASE, "status": "nonsense_value"})


def test_session_status_legacy_done_rejected() -> None:
    """`status: done` is the exact value that motivated Phase 2.1.

    Should be rejected post-hardening (`completed` is the canonical
    terminal-success).
    """
    with pytest.raises(ValidationError):
        AgentSession.model_validate({**_BASE, "status": "done"})


def test_session_status_completed_accepted() -> None:
    """`status: completed` loads cleanly and is a SessionStatus instance."""
    sess = AgentSession.model_validate({**_BASE, "status": "completed"})
    assert sess.status == SessionStatus.COMPLETED
    assert isinstance(sess.status, SessionStatus)


def test_session_status_default_is_planned() -> None:
    """Omitting status defaults to SessionStatus.PLANNED."""
    sess = AgentSession.model_validate({**_BASE})
    assert sess.status == SessionStatus.PLANNED

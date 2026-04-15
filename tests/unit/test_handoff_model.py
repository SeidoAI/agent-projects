"""SessionHandoff model for sessions/<id>/handoff.yaml."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from keel.models.handoff import SessionHandoff, WorkspaceContext


def _now():
    return datetime.now(tz=timezone.utc)


class TestSessionHandoff:
    def test_minimal_valid(self):
        h = SessionHandoff(
            uuid=uuid4(),
            session_id="session-auth-42-setup",
            handoff_at=_now(),
            handed_off_by="pm",
            branch="feat/auth-42-setup",
        )
        assert h.branch == "feat/auth-42-setup"
        assert h.open_questions == []
        assert h.context_to_preserve == []
        assert h.last_verification_passed_at is None
        assert h.workspace_context is None

    def test_rejects_invalid_branch(self):
        with pytest.raises(ValidationError):
            SessionHandoff(
                uuid=uuid4(),
                session_id="session-x",
                handoff_at=_now(),
                handed_off_by="pm",
                branch="not-a-valid-branch",
            )

    def test_accepts_workspace_context(self):
        h = SessionHandoff(
            uuid=uuid4(),
            session_id="session-x",
            handoff_at=_now(),
            handed_off_by="pm",
            branch="feat/x",
            workspace_context=WorkspaceContext(
                workspace_nodes_touched=["auth-system"],
                workspace_sha_at_handoff="a3f2b1c",
                stale_nodes=[],
            ),
        )
        assert h.workspace_context is not None
        assert "auth-system" in h.workspace_context.workspace_nodes_touched

    def test_rejects_unknown_handed_off_by(self):
        with pytest.raises(ValidationError):
            SessionHandoff(
                uuid=uuid4(),
                session_id="session-x",
                handoff_at=_now(),
                handed_off_by="wizard",
                branch="feat/x",
            )

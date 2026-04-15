"""handoff_store: read/write sessions/<id>/handoff.yaml."""

from datetime import datetime, timezone
from uuid import uuid4

from keel.core.handoff_store import (
    handoff_exists,
    load_handoff,
    save_handoff,
)
from keel.core.paths import handoff_path
from keel.models.handoff import SessionHandoff


def _handoff(session_id: str) -> SessionHandoff:
    return SessionHandoff(
        uuid=uuid4(),
        session_id=session_id,
        handoff_at=datetime.now(tz=timezone.utc),
        handed_off_by="pm",
        branch="feat/some-work",
    )


def test_save_then_load_roundtrip(tmp_path):
    project_dir = tmp_path
    (project_dir / "sessions" / "session-x").mkdir(parents=True)
    h = _handoff("session-x")
    save_handoff(project_dir, h)

    loaded = load_handoff(project_dir, "session-x")
    assert loaded is not None
    assert loaded.session_id == "session-x"
    assert loaded.branch == "feat/some-work"


def test_exists_false_when_missing(tmp_path):
    (tmp_path / "sessions" / "session-x").mkdir(parents=True)
    assert handoff_exists(tmp_path, "session-x") is False


def test_exists_true_after_save(tmp_path):
    (tmp_path / "sessions" / "session-x").mkdir(parents=True)
    save_handoff(tmp_path, _handoff("session-x"))
    assert handoff_exists(tmp_path, "session-x") is True


def test_handoff_path_layout(tmp_path):
    p = handoff_path(tmp_path, "session-x")
    assert p == tmp_path / "sessions" / "session-x" / "handoff.yaml"


def test_load_missing_returns_none(tmp_path):
    (tmp_path / "sessions" / "session-x").mkdir(parents=True)
    assert load_handoff(tmp_path, "session-x") is None

"""Tests for `save_session` event emission (KUI-100).

When a session's `status` changes between save calls, `save_session`
must emit one `status_transition` event under the `status_transitions/`
subdir. The default `NullEmitter` keeps existing batch / unit-test
behaviour unchanged. See `docs/specs/2026-04-26-v08-handoff.md` §1.2.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tripwire.core.session_store import save_session
from tripwire.models.session import AgentSession


class _RecordingEmitter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def emit(self, kind: str, payload: Mapping[str, Any]) -> str:
        self.calls.append((kind, dict(payload)))
        return ""


def _make_session(sid: str, status: str = "planned") -> AgentSession:
    return AgentSession.model_validate(
        {
            "id": sid,
            "uuid": "00000000-0000-4000-a000-000000000001",
            "name": "fixture",
            "status": status,
            "agent": "backend-coder",
        }
    )


def test_save_session_no_emitter_is_a_no_op(tmp_path: Path) -> None:
    """No emitter passed → existing behaviour unchanged, never raises."""
    session = _make_session("s1")
    save_session(tmp_path, session)
    assert (tmp_path / "instances" / "sessions" / "s1" / "session.yaml").is_file()


def test_save_session_first_save_emits_no_transition(tmp_path: Path) -> None:
    """No prior session.yaml → no transition (nothing to compare against)."""
    emitter = _RecordingEmitter()
    session = _make_session("s1", status="planned")
    save_session(tmp_path, session, emitter=emitter)
    assert all(kind != "status_transitions" for kind, _ in emitter.calls)


def test_save_session_emits_on_status_change(tmp_path: Path) -> None:
    emitter = _RecordingEmitter()
    s1 = _make_session("s1", status="planned")
    save_session(tmp_path, s1, emitter=emitter)

    s2 = _make_session("s1", status="executing")
    save_session(tmp_path, s2, emitter=emitter)

    matching = [p for k, p in emitter.calls if k == "status_transitions"]
    assert len(matching) == 1
    payload = matching[0]
    for key in (
        "id",
        "kind",
        "fired_at",
        "session_id",
        "from_status",
        "to_status",
    ):
        assert key in payload, f"missing {key!r} in {payload}"
    assert payload["kind"] == "status_transition"
    assert payload["session_id"] == "s1"
    assert payload["from_status"] == "planned"
    assert payload["to_status"] == "executing"


def test_save_session_no_emit_when_status_unchanged(tmp_path: Path) -> None:
    emitter = _RecordingEmitter()
    s = _make_session("s1", status="executing")
    save_session(tmp_path, s, emitter=emitter)
    save_session(tmp_path, s, emitter=emitter)
    matching = [p for k, p in emitter.calls if k == "status_transitions"]
    assert matching == []

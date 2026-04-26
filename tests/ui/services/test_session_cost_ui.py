"""UI session service exposes per-session cost (KUI-96 §E2)."""

from __future__ import annotations

import json
from pathlib import Path

from tripwire.ui.services.session_service import get_session, list_sessions


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _assistant_event(model: str, usage: dict) -> dict:
    return {"type": "assistant", "message": {"model": model, "usage": usage}}


def test_list_sessions_includes_cost_usd(
    save_test_session, tmp_path_project: Path
) -> None:
    """``cost_usd`` lives on every summary so the UI grid can display it."""
    log = tmp_path_project / "sessions" / "s1" / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 1000, "output_tokens": 500}
            )
        ],
    )
    save_test_session(
        tmp_path_project, session_id="s1", runtime_state={"log_path": str(log)}
    )
    save_test_session(tmp_path_project, session_id="s2")

    summaries = list_sessions(tmp_path_project)
    by_id = {s.id: s for s in summaries}
    assert abs(by_id["s1"].cost_usd - 0.0525) < 1e-9
    assert by_id["s2"].cost_usd == 0.0


def test_get_session_includes_cost_usd(
    save_test_session, tmp_path_project: Path
) -> None:
    """The session detail view also surfaces ``cost_usd`` for real-time UX."""
    log = tmp_path_project / "sessions" / "s1" / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 1000, "output_tokens": 500}
            )
        ],
    )
    save_test_session(
        tmp_path_project, session_id="s1", runtime_state={"log_path": str(log)}
    )
    detail = get_session(tmp_path_project, "s1")
    assert abs(detail.cost_usd - 0.0525) < 1e-9

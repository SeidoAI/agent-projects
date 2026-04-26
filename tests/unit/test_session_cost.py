"""Tests for ``tripwire.core.session_cost`` (KUI-96 §E2).

The cost module must read a stream-json log produced by ``claude -p``
and return a :class:`CostBreakdown` summing each token category times
the appropriate model rate from ``data/anthropic_pricing.yaml``.

Coverage targets:
- per-token-type accumulation (input, output, cache_read, cache_write)
- per-event model dispatch (assistant events carry their own model)
- malformed lines / non-dict payloads / empty logs degrade gracefully
- unknown model names fall back to the ``default:`` rates
- ``compute_session_cost`` resolves a session-id → log path via
  the persisted ``runtime_state.log_path``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_log(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _assistant_event(model: str, usage: dict) -> dict:
    return {
        "type": "assistant",
        "message": {"model": model, "usage": usage},
    }


def test_compute_cost_from_log_sums_assistant_usage(tmp_path: Path) -> None:
    """Two assistant events with simple input/output tokens accumulate."""
    from tripwire.core.session_cost import compute_cost_from_log

    log = tmp_path / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 1000, "output_tokens": 500}
            ),
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 200, "output_tokens": 100}
            ),
        ],
    )
    result = compute_cost_from_log(log)
    # Opus rates: input 15.00 + output 75.00 per Mtok.
    expected_input = (1000 + 200) * 15.0 / 1_000_000
    expected_output = (500 + 100) * 75.0 / 1_000_000
    assert abs(result.input_usd - expected_input) < 1e-9
    assert abs(result.output_usd - expected_output) < 1e-9
    assert abs(result.total_usd - (expected_input + expected_output)) < 1e-9
    assert result.cache_read_usd == pytest.approx(0.0)
    assert result.cache_write_usd == pytest.approx(0.0)


def test_compute_cost_includes_cache_token_categories(tmp_path: Path) -> None:
    """``cache_creation_input_tokens`` + ``cache_read_input_tokens`` price separately."""
    from tripwire.core.session_cost import compute_cost_from_log

    log = tmp_path / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7",
                {
                    "input_tokens": 100,
                    "output_tokens": 100,
                    "cache_creation_input_tokens": 1000,
                    "cache_read_input_tokens": 10000,
                },
            ),
        ],
    )
    result = compute_cost_from_log(log)
    # Opus: cache_write 18.75, cache_read 1.50.
    assert result.cache_write_usd == pytest.approx(1000 * 18.75 / 1_000_000)
    assert result.cache_read_usd == pytest.approx(10000 * 1.50 / 1_000_000)
    assert result.input_usd == pytest.approx(100 * 15.0 / 1_000_000)
    assert result.output_usd == pytest.approx(100 * 75.0 / 1_000_000)
    assert result.total_usd == pytest.approx(
        result.input_usd
        + result.output_usd
        + result.cache_read_usd
        + result.cache_write_usd
    )


def test_compute_cost_dispatches_per_event_model(tmp_path: Path) -> None:
    """Each assistant event uses its own ``message.model`` for pricing."""
    from tripwire.core.session_cost import compute_cost_from_log

    log = tmp_path / "session.log"
    _write_log(
        log,
        [
            # Sonnet rates: input 3.00, output 15.00.
            _assistant_event(
                "claude-sonnet-4-6", {"input_tokens": 1000, "output_tokens": 1000}
            ),
            # Haiku rates: input 0.80, output 4.00.
            _assistant_event(
                "claude-haiku-4-5", {"input_tokens": 1000, "output_tokens": 1000}
            ),
        ],
    )
    result = compute_cost_from_log(log)
    expected = (1000 * 3.0 + 1000 * 15.0 + 1000 * 0.8 + 1000 * 4.0) / 1_000_000
    assert result.total_usd == pytest.approx(expected)


def test_compute_cost_unknown_model_uses_default(tmp_path: Path) -> None:
    """Models with no entry in ``models:`` fall back to ``default:``."""
    from tripwire.core.session_cost import compute_cost_from_log

    log = tmp_path / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "totally-unknown-model", {"input_tokens": 1000, "output_tokens": 0}
            )
        ],
    )
    result = compute_cost_from_log(log)
    # Default rates: input 15.00 (Anthropic-conservative).
    assert result.input_usd == pytest.approx(1000 * 15.0 / 1_000_000)


def test_compute_cost_skips_malformed_and_empty_lines(tmp_path: Path) -> None:
    """JSON-decode errors, non-dicts, and blank lines do not crash."""
    from tripwire.core.session_cost import compute_cost_from_log

    log = tmp_path / "session.log"
    log.write_text(
        "\n".join(
            [
                "",
                "not json at all",
                "[1, 2, 3]",  # JSON but not a dict
                json.dumps(_assistant_event("claude-opus-4-7", {"input_tokens": 100})),
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = compute_cost_from_log(log)
    assert result.input_usd == pytest.approx(100 * 15.0 / 1_000_000)


def test_compute_cost_falls_back_to_event_message_model_when_missing(
    tmp_path: Path,
) -> None:
    """``fallback_model`` arg is used only when the event has no model field."""
    from tripwire.core.session_cost import compute_cost_from_log

    log = tmp_path / "session.log"
    # Note: usage is present but model is missing — falls back to argument.
    _write_log(
        log,
        [
            {
                "type": "assistant",
                "message": {"usage": {"input_tokens": 1000, "output_tokens": 0}},
            }
        ],
    )
    # Force sonnet via fallback.
    result = compute_cost_from_log(log, fallback_model="claude-sonnet-4-6")
    assert result.input_usd == pytest.approx(1000 * 3.0 / 1_000_000)


def test_compute_cost_missing_log_returns_zero_breakdown(tmp_path: Path) -> None:
    """Calling on a non-existent log returns zeros; never raises."""
    from tripwire.core.session_cost import compute_cost_from_log

    result = compute_cost_from_log(tmp_path / "does-not-exist.log")
    assert result.total_usd == 0.0
    assert result.input_usd == 0.0
    assert result.output_usd == 0.0
    assert result.cache_read_usd == 0.0
    assert result.cache_write_usd == 0.0


def test_compute_session_cost_reads_log_from_runtime_state(tmp_path: Path) -> None:
    """``compute_session_cost`` resolves a session-id to its persisted log path."""
    from tripwire.core.session_cost import compute_session_cost
    from tripwire.core.session_store import save_session
    from tripwire.models.session import AgentSession, RuntimeState

    log = tmp_path / "logs" / "demo.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 1000, "output_tokens": 0}
            )
        ],
    )

    project_dir = tmp_path / "proj"
    (project_dir / "sessions" / "demo").mkdir(parents=True, exist_ok=True)
    session = AgentSession(
        id="demo",
        name="demo",
        agent="backend-coder",
        runtime_state=RuntimeState(log_path=str(log)),
    )
    save_session(project_dir, session)

    result = compute_session_cost(project_dir, "demo")
    assert result.input_usd == pytest.approx(1000 * 15.0 / 1_000_000)


def test_compute_session_cost_no_log_path_returns_zero(tmp_path: Path) -> None:
    """A session with no recorded ``runtime_state.log_path`` yields zero."""
    from tripwire.core.session_cost import compute_session_cost
    from tripwire.core.session_store import save_session
    from tripwire.models.session import AgentSession

    project_dir = tmp_path / "proj"
    (project_dir / "sessions" / "demo").mkdir(parents=True, exist_ok=True)
    save_session(
        project_dir,
        AgentSession(id="demo", name="demo", agent="backend-coder"),
    )
    result = compute_session_cost(project_dir, "demo")
    assert result.total_usd == 0.0

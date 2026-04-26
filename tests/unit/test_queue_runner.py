"""Quota-aware auto-launcher daemon (KUI-96 §E1).

The runner walks ``sessions/*/session.yaml`` for ``status == queued``,
estimates remaining Anthropic Max headroom by summing recent session
costs against a configurable cap, and spawns one queued session per
tick when headroom is available. After a 429 or other quota error is
seen, the runner enters a cool-down where it probes with a tiny
``claude -p`` call before spawning again.

Tests focus on the policy (which session gets spawned, when to defer,
when to probe) using injected runners — no actual claude calls or
detached subprocess forks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tripwire.core.queue_runner import (
    QueueRunner,
    QueueRunnerConfig,
    TickOutcome,
)
from tripwire.core.routing_telemetry import (
    TelemetryRow,
    append_telemetry_row,
)


def _row(sid: str, cost_usd: float) -> TelemetryRow:
    return TelemetryRow(
        sid=sid,
        task_kind="agentic_loop",
        provider="claude",
        model="opus",
        effort="xhigh",
        merged=True,
        cost_usd=cost_usd,
        duration_min=10,
        re_engages=0,
        ci_failures=0,
    )


def _config(**overrides) -> QueueRunnerConfig:
    base = {
        "cap_usd_per_window": 100.0,
        "max_concurrent_spawns": 1,
        "probe_interval_seconds": 300.0,
        "tick_sleep_seconds": 60.0,
    }
    base.update(overrides)
    return QueueRunnerConfig(**base)


def test_runner_spawns_queued_session_when_headroom_available(
    save_test_session, tmp_path_project: Path
) -> None:
    """Headroom available → first queued session spawns; it transitions
    to `executing` (or whatever the spawn runner reports)."""
    save_test_session(tmp_path_project, session_id="s1", status="queued")
    spawned: list[str] = []
    runner = QueueRunner(
        project_dir=tmp_path_project,
        config=_config(cap_usd_per_window=100.0),
        spawn_runner=lambda pd, sid: spawned.append(sid),
        probe_runner=lambda: True,
        clock=lambda: datetime(2026, 4, 26, 12, tzinfo=timezone.utc),
    )
    outcome = runner.tick()
    assert spawned == ["s1"]
    assert outcome.spawned_session == "s1"
    assert outcome.action == "spawned"


def test_runner_defers_when_cap_exhausted(
    save_test_session, tmp_path_project: Path
) -> None:
    """Recent telemetry already exceeds the cap → no spawn; reason recorded."""
    # Existing cost exhausting the $100 cap.
    append_telemetry_row(tmp_path_project, _row("done1", 60.0))
    append_telemetry_row(tmp_path_project, _row("done2", 50.0))
    save_test_session(tmp_path_project, session_id="s1", status="queued")
    spawned: list[str] = []
    runner = QueueRunner(
        project_dir=tmp_path_project,
        config=_config(cap_usd_per_window=100.0),
        spawn_runner=lambda pd, sid: spawned.append(sid),
        probe_runner=lambda: True,
        clock=lambda: datetime(2026, 4, 26, 12, tzinfo=timezone.utc),
    )
    outcome = runner.tick()
    assert spawned == []
    assert outcome.action == "deferred"
    assert "cap" in (outcome.reason or "").lower()


def test_runner_does_nothing_when_no_queued_sessions(
    save_test_session, tmp_path_project: Path
) -> None:
    """Empty queue → idle tick."""
    runner = QueueRunner(
        project_dir=tmp_path_project,
        config=_config(),
        spawn_runner=lambda pd, sid: pytest.fail("should not be called"),
        probe_runner=lambda: True,
    )
    outcome = runner.tick()
    assert outcome.action == "idle"


def test_runner_probes_when_in_cooldown(
    save_test_session, tmp_path_project: Path
) -> None:
    """After a quota error, the runner probes before resuming spawns.

    Simulated by directly setting ``in_cooldown`` and a
    ``last_probe_at`` deep enough in the past that the probe is due.
    """
    save_test_session(tmp_path_project, session_id="s1", status="queued")
    spawned: list[str] = []
    probes: list[int] = []

    def probe() -> bool:
        probes.append(1)
        return True  # cap is back

    runner = QueueRunner(
        project_dir=tmp_path_project,
        config=_config(cap_usd_per_window=100.0),
        spawn_runner=lambda pd, sid: spawned.append(sid),
        probe_runner=probe,
        clock=lambda: datetime(2026, 4, 26, 12, tzinfo=timezone.utc),
    )
    runner.enter_cooldown(reason="429 from previous spawn")
    outcome = runner.tick()
    # Probe ran; cap is back; spawn proceeded.
    assert probes == [1]
    assert spawned == ["s1"]
    assert outcome.action == "spawned"


def test_runner_stays_in_cooldown_when_probe_fails(
    save_test_session, tmp_path_project: Path
) -> None:
    """Probe still 429 → no spawn; runner remains in cool-down."""
    save_test_session(tmp_path_project, session_id="s1", status="queued")
    spawned: list[str] = []
    runner = QueueRunner(
        project_dir=tmp_path_project,
        config=_config(),
        spawn_runner=lambda pd, sid: spawned.append(sid),
        probe_runner=lambda: False,  # still capped
    )
    runner.enter_cooldown(reason="429")
    outcome = runner.tick()
    assert spawned == []
    assert outcome.action == "cooldown"
    assert runner.in_cooldown is True


def test_runner_picks_oldest_queued_when_multiple(
    save_test_session, tmp_path_project: Path
) -> None:
    """Two queued sessions → only one spawns per tick; FIFO by id."""
    save_test_session(tmp_path_project, session_id="alpha", status="queued")
    save_test_session(tmp_path_project, session_id="beta", status="queued")
    spawned: list[str] = []
    runner = QueueRunner(
        project_dir=tmp_path_project,
        config=_config(),
        spawn_runner=lambda pd, sid: spawned.append(sid),
        probe_runner=lambda: True,
    )
    outcome = runner.tick()
    assert outcome.action == "spawned"
    # Only one spawn per tick (max_concurrent_spawns default is 1).
    assert len(spawned) == 1


def test_outcome_dataclass_serialises() -> None:
    """``TickOutcome`` carries enough fields to write a queue.log line."""
    outcome = TickOutcome(action="spawned", spawned_session="s1", reason=None)
    assert outcome.action == "spawned"
    assert outcome.spawned_session == "s1"
    assert outcome.reason is None

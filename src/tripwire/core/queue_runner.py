"""Quota-aware auto-launcher daemon (KUI-96 §E1).

Long-running policy loop. On every tick:

    1. List queued sessions.
    2. If we are in cool-down (a previous spawn observed a 429),
       probe with a tiny ``claude -p`` call. If the probe fails the
       cap is still exhausted; defer to the next tick. If it
       succeeds, exit cool-down and proceed.
    3. Estimate recent spend by summing the last N hours of cost
       from ``.routing_telemetry.jsonl``. If spend ≥ cap, defer.
    4. Otherwise, pick the oldest queued session and call the
       injected ``spawn_runner``. One spawn per tick — concurrency
       is bounded by the runtime caps anyway, and the simpler
       semantics make the daemon easier to reason about.

The daemon itself (``run_forever``) is a thin wrapper around
``tick`` that sleeps between iterations. ``tick`` is pure-policy
and synchronous so unit tests don't need threads or fake clocks
beyond a callable.

Cap-detection note: there is no public Anthropic API for remaining
weekly cap, so the heuristic combines (a) summing recent telemetry
and (b) probing on demand after a quota error. This is best-effort —
false positives degrade to "deferred and probe again next tick"
rather than crashing.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.process_helpers import is_alive
from tripwire.core.routing_telemetry import read_telemetry
from tripwire.core.session_store import list_sessions

logger = logging.getLogger(__name__)


# ---------- Daemon filesystem layout ------------------------------------


def queue_dir(project_dir: Path) -> Path:
    """``<project>/.tripwire/queue`` — pidfile + log live here."""
    return project_dir / ".tripwire" / "queue"


def pidfile_path(project_dir: Path) -> Path:
    return queue_dir(project_dir) / "queue.pid"


def logfile_path(project_dir: Path) -> Path:
    return queue_dir(project_dir) / "queue.log"


def write_pidfile(project_dir: Path, pid: int) -> None:
    pid_path = pidfile_path(project_dir)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(pid))


def remove_pidfile(project_dir: Path) -> None:
    try:
        pidfile_path(project_dir).unlink()
    except FileNotFoundError:
        pass


def is_queue_running(project_dir: Path) -> bool:
    """True iff a pidfile exists *and* its pid is still live."""
    pid_path = pidfile_path(project_dir)
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return False
    return is_alive(pid)


# ---------- Config + outcomes ---------------------------------------------


@dataclass
class QueueRunnerConfig:
    """Tunables for the queue runner. Defaults err on the conservative side."""

    cap_usd_per_window: float = 200.0
    """USD cap to compare recent spend against. Tune per Max plan."""

    max_concurrent_spawns: int = 1
    """How many sessions to spawn per tick. 1 keeps semantics simple."""

    probe_interval_seconds: float = 300.0
    """Sleep between probes while in cool-down."""

    tick_sleep_seconds: float = 60.0
    """Sleep between policy ticks when ``run_forever`` is in use."""


@dataclass
class TickOutcome:
    """One tick's decision, suitable for logging to ``queue.log``."""

    action: str  # "idle" | "spawned" | "deferred" | "cooldown"
    spawned_session: str | None = None
    reason: str | None = None
    recent_spend_usd: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------- Default runners (DI seams) -----------------------------------


def default_probe_runner() -> bool:
    """Send a tiny ``claude -p`` call; return True on success.

    Used to detect that a previous quota error has cleared. The
    ``--max-turns 1`` ensures a fast round-trip; failure is recorded
    as still-capped without distinguishing 429s from network errors
    (deferring is the same response either way).
    """
    if not shutil.which("claude"):
        logger.warning("queue_runner: claude CLI not on PATH; probe inconclusive")
        return False
    try:
        result = subprocess.run(
            ["claude", "-p", "ok", "--max-turns", "1"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("queue_runner: probe failed: %s", exc)
        return False
    return result.returncode == 0


def default_spawn_runner(project_dir: Path, session_id: str) -> None:
    """Invoke ``tripwire session spawn`` for ``session_id``."""
    cmd = [
        "tripwire",
        "session",
        "spawn",
        session_id,
        "--project-dir",
        str(project_dir),
    ]
    subprocess.run(cmd, check=True)


# ---------- Runner --------------------------------------------------------


class QueueRunner:
    """Stateful policy + tick loop. One per ``tripwire queue start``."""

    def __init__(
        self,
        *,
        project_dir: Path,
        config: QueueRunnerConfig,
        spawn_runner: Callable[[Path, str], None] = default_spawn_runner,
        probe_runner: Callable[[], bool] = default_probe_runner,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ) -> None:
        self.project_dir = project_dir
        self.config = config
        self.spawn_runner = spawn_runner
        self.probe_runner = probe_runner
        self.clock = clock

        self.in_cooldown = False
        self.cooldown_reason: str | None = None
        self.last_probe_at: datetime | None = None

    # --- public surface ---------------------------------------------------

    def enter_cooldown(self, *, reason: str) -> None:
        """Mark the runner as quota-throttled until a probe succeeds."""
        self.in_cooldown = True
        self.cooldown_reason = reason
        self.last_probe_at = None

    def tick(self) -> TickOutcome:
        """Run one policy iteration and return the decision."""
        queued = self._queued_sessions()

        if not queued:
            return TickOutcome(action="idle", reason="no queued sessions")

        if self.in_cooldown:
            return self._handle_cooldown(queued)

        spend = self._recent_spend_usd()
        if spend >= self.config.cap_usd_per_window:
            return TickOutcome(
                action="deferred",
                reason=(
                    f"recent spend ${spend:.2f} ≥ cap "
                    f"${self.config.cap_usd_per_window:.2f}"
                ),
                recent_spend_usd=spend,
            )

        return self._spawn_one(queued, recent_spend=spend)

    def run_forever(self, *, max_ticks: int | None = None) -> None:  # pragma: no cover
        """Loop ``tick`` with sleeps. Tested via the synchronous ``tick``.

        ``max_ticks`` is a test seam so a controller test can run a
        bounded number of iterations.
        """
        ticks = 0
        while True:
            outcome = self.tick()
            self._log_outcome(outcome)
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return
            time.sleep(self.config.tick_sleep_seconds)

    # --- internals --------------------------------------------------------

    def _queued_sessions(self) -> list[str]:
        sessions = list_sessions(self.project_dir)
        return sorted(s.id for s in sessions if s.status == "queued")

    def _recent_spend_usd(self) -> float:
        """Sum the cost column from telemetry rows. No time-window slicing
        in v0 — operators tune ``cap_usd_per_window`` against the
        full-history total. A future iteration could subset by
        timestamp once that field is added to the row schema.
        """
        rows = read_telemetry(self.project_dir)
        return sum(float(r.get("cost_usd") or 0.0) for r in rows)

    def _handle_cooldown(self, queued: list[str]) -> TickOutcome:
        now = self.clock()
        if (
            self.last_probe_at is None
            or (now - self.last_probe_at).total_seconds()
            >= self.config.probe_interval_seconds
        ):
            self.last_probe_at = now
            ok = self.probe_runner()
            if ok:
                self.in_cooldown = False
                self.cooldown_reason = None
                spend = self._recent_spend_usd()
                if spend >= self.config.cap_usd_per_window:
                    return TickOutcome(
                        action="deferred",
                        reason=(
                            "probe succeeded but recent spend "
                            f"${spend:.2f} still over cap"
                        ),
                        recent_spend_usd=spend,
                    )
                return self._spawn_one(queued, recent_spend=spend)
            return TickOutcome(
                action="cooldown",
                reason=f"probe failed; {self.cooldown_reason or 'still capped'}",
            )
        return TickOutcome(
            action="cooldown",
            reason="cooldown active; next probe pending",
        )

    def _spawn_one(self, queued: list[str], *, recent_spend: float) -> TickOutcome:
        sid = queued[0]
        try:
            self.spawn_runner(self.project_dir, sid)
        except subprocess.CalledProcessError as exc:
            self.enter_cooldown(reason=f"spawn returned {exc.returncode}")
            return TickOutcome(
                action="cooldown",
                reason=str(exc),
                recent_spend_usd=recent_spend,
            )
        except (OSError, RuntimeError) as exc:
            return TickOutcome(
                action="deferred",
                reason=f"spawn raised {type(exc).__name__}: {exc}",
                recent_spend_usd=recent_spend,
            )
        return TickOutcome(
            action="spawned",
            spawned_session=sid,
            recent_spend_usd=recent_spend,
        )

    def _log_outcome(self, outcome: TickOutcome) -> None:  # pragma: no cover
        logger.info(
            "queue_runner tick: action=%s session=%s reason=%s spend=%.2f",
            outcome.action,
            outcome.spawned_session,
            outcome.reason,
            outcome.recent_spend_usd,
        )


__all__ = [
    "QueueRunner",
    "QueueRunnerConfig",
    "TickOutcome",
    "default_probe_runner",
    "default_spawn_runner",
]

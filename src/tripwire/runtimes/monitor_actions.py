"""Side-effect executor for in-flight monitor actions.

The :class:`RuntimeMonitor` is pure-function — it emits
:class:`MonitorAction` records but never touches the filesystem,
sends signals, or mutates session state. :class:`ActionExecutor`
turns those records into the actual side effects.

Splitting the policy from the side effects lets each be tested in
isolation: the monitor's tripwire logic against fake events, the
executor's writeback semantics against a real ``session.yaml`` on
disk.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.process_helpers import send_sigcont, send_sigstop, send_sigterm
from tripwire.core.session_store import load_session, save_session
from tripwire.runtimes.monitor import (
    InjectFollowUp,
    LogWarning,
    MonitorAction,
    ResumeProcess,
    SigtermProcess,
    SuspendProcess,
    TransitionStatus,
)

# B4 — defensive cap on how long the agent may stay SIGSTOP'd. Even if
# external state never SIGCONTs the agent, after this many seconds the
# scheduled timer wakes it back up so the session isn't lost. 30 min
# is roughly an order of magnitude longer than the longest observed
# CI run on this repo (~3 min); shorter caps risk waking mid-poll.
_DEFENSIVE_RESUME_SECONDS = 30 * 60

logger = logging.getLogger(__name__)


_FOLLOW_UP_SEPARATOR = "\n\n<!-- monitor:tripwire={tid} ts={ts} -->\n"


class ActionExecutor:
    """Apply :class:`MonitorAction` records to the filesystem and process."""

    def __init__(
        self,
        project_dir: Path,
        session_id: str,
        *,
        monitor_log_path: Path | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.session_id = session_id
        self.monitor_log_path = monitor_log_path

    def execute(self, action: MonitorAction) -> None:
        if isinstance(action, SigtermProcess):
            self._do_sigterm(action)
        elif isinstance(action, TransitionStatus):
            self._do_transition(action)
        elif isinstance(action, InjectFollowUp):
            self._do_inject(action)
        elif isinstance(action, LogWarning):
            self._do_warning(action)
        elif isinstance(action, SuspendProcess):
            self._do_suspend(action)
        elif isinstance(action, ResumeProcess):
            self._do_resume(action)
        else:  # pragma: no cover — exhaustive over the dataclass union
            logger.warning("ActionExecutor: unknown action type %r", action)

    # --- handlers -------------------------------------------------------

    def _do_sigterm(self, action: SigtermProcess) -> None:
        sent = send_sigterm(action.pid)
        outcome = f"sigterm/{action.tripwire_id} pid={action.pid} sent={sent}: {action.reason}"
        self._stamp_engagement(outcome)
        self._append_monitor_log(action.tripwire_id, action.reason)
        if not sent:
            logger.warning(
                "monitor: SIGTERM target pid %d not found (%s)",
                action.pid,
                action.tripwire_id,
            )

    def _do_transition(self, action: TransitionStatus) -> None:
        try:
            session = load_session(self.project_dir, self.session_id)
        except FileNotFoundError:
            logger.warning(
                "monitor: cannot transition '%s' — session file not found",
                self.session_id,
            )
            return
        previous = session.status
        session.status = action.new_status
        session.updated_at = datetime.now(tz=timezone.utc)
        save_session(self.project_dir, session)
        self._append_monitor_log(
            action.tripwire_id,
            f"status {previous} → {action.new_status}: {action.reason}",
        )

    def _do_inject(self, action: InjectFollowUp) -> None:
        if action.target != "plan.md":
            # Forward-compat: other targets (e.g. "next-message" buffer)
            # not implemented for v0.7.9.
            logger.info(
                "monitor: inject target %r not implemented; logging only",
                action.target,
            )
            self._append_monitor_log(action.tripwire_id, action.message)
            return
        plan_path = self.project_dir / "sessions" / self.session_id / "plan.md"
        if not plan_path.exists():
            logger.warning("monitor: plan.md missing for session '%s'", self.session_id)
            return
        existing = plan_path.read_text(encoding="utf-8")
        marker = f"monitor:tripwire={action.tripwire_id}"
        if marker in existing:
            # Idempotent — same tripwire id has already been injected.
            return
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sep = _FOLLOW_UP_SEPARATOR.format(tid=action.tripwire_id, ts=ts)
        new_text = existing.rstrip() + sep + action.message.rstrip() + "\n"
        plan_path.write_text(new_text, encoding="utf-8")
        self._append_monitor_log(action.tripwire_id, "follow-up injected into plan.md")

    def _do_warning(self, action: LogWarning) -> None:
        self._append_monitor_log(action.tripwire_id, action.message)

    def _do_suspend(self, action: SuspendProcess) -> None:
        sent = send_sigstop(action.pid)
        outcome = (
            f"sigstop/{action.tripwire_id} pid={action.pid} sent={sent}: "
            f"{action.reason}"
        )
        self._append_monitor_log(action.tripwire_id, outcome)
        if not sent:
            logger.warning(
                "monitor: SIGSTOP target pid %d not found (%s)",
                action.pid,
                action.tripwire_id,
            )
            return
        # Schedule a defensive SIGCONT — even if nothing else wakes
        # the agent, it can't be left frozen indefinitely.
        timer = threading.Timer(
            _DEFENSIVE_RESUME_SECONDS,
            self._defensive_resume,
            args=(action.pid, action.tripwire_id),
        )
        timer.daemon = True
        timer.start()

    def _do_resume(self, action: ResumeProcess) -> None:
        sent = send_sigcont(action.pid)
        outcome = (
            f"sigcont/{action.tripwire_id} pid={action.pid} sent={sent}: "
            f"{action.reason}"
        )
        self._append_monitor_log(action.tripwire_id, outcome)
        if not sent:
            logger.warning(
                "monitor: SIGCONT target pid %d not found (%s)",
                action.pid,
                action.tripwire_id,
            )

    def _defensive_resume(self, pid: int, source_tripwire_id: str) -> None:
        """Fallback SIGCONT path that fires after ``_DEFENSIVE_RESUME_SECONDS``.

        Runs on a daemon ``threading.Timer``. If the agent already
        exited (pid gone), ``send_sigcont`` is a no-op.
        """
        sent = send_sigcont(pid)
        self._append_monitor_log(
            "monitor/ci_wait_resume",
            (
                f"defensive sigcont pid={pid} sent={sent} "
                f"source={source_tripwire_id} after={_DEFENSIVE_RESUME_SECONDS}s"
            ),
        )

    # --- helpers --------------------------------------------------------

    def _stamp_engagement(self, outcome: str) -> None:
        try:
            session = load_session(self.project_dir, self.session_id)
        except FileNotFoundError:
            return
        if not session.engagements:
            return
        last = session.engagements[-1]
        if last.outcome is None:
            last.outcome = outcome
            last.ended_at = datetime.now(tz=timezone.utc)
            session.updated_at = datetime.now(tz=timezone.utc)
            save_session(self.project_dir, session)

    def _append_monitor_log(self, tripwire_id: str, message: str) -> None:
        if self.monitor_log_path is None:
            return
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        line = f"{ts} {tripwire_id} {message}\n"
        self.monitor_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.monitor_log_path.open("a", encoding="utf-8") as f:
            f.write(line)


__all__ = ["ActionExecutor"]

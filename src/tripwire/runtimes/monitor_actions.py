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

import json
import logging
import subprocess
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

# B4b — how often the GH-polling resume thread checks `gh pr view` for
# CI completion. Every 30s matches the agent's own polling cadence
# and keeps the rate-limit footprint minimal (max 60 calls/30min).
_GH_POLL_INTERVAL_SECONDS = 30

# B4b — per-call timeout on the `gh pr view` invocation. CI rollup is
# a small JSON payload; anything beyond this means gh / network
# trouble and we'd rather sleep+retry than hang the poll thread.
_GH_POLL_CALL_TIMEOUT = 30

logger = logging.getLogger(__name__)


_FOLLOW_UP_SEPARATOR = "\n\n<!-- monitor:tripwire={tid} ts={ts} -->\n"


def _all_checks_completed(payload: dict) -> bool:
    """True iff every entry in ``statusCheckRollup`` has reached a
    terminal status. Both SUCCESS and FAILURE wake the agent — the
    point of the wake-up is to let the agent observe the outcome,
    not to gate on a specific conclusion."""
    runs = payload.get("statusCheckRollup") or []
    if not runs:
        # An empty rollup means CI hasn't reported anything yet. We
        # don't know whether to wake; treat as still-pending.
        return False
    for run in runs:
        status = (run.get("status") or "").upper()
        # GitHub Actions reports COMPLETED with a conclusion; the
        # legacy commit-status API returns just a state — treat
        # SUCCESS / FAILURE / ERROR as terminal there too.
        if status in {"COMPLETED", "SUCCESS", "FAILURE", "ERROR"}:
            continue
        return False
    return True


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
        # B4b — per-suspended-pid event so the defensive Timer and the
        # GH-polling resume thread coordinate: whichever fires first
        # SIGCONTs the pid and sets the event; the loser sees the
        # event set and exits without re-SIGCONT'ing.
        self._resume_events: dict[int, threading.Event] = {}

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
        # v0.7.10 §3.A4 — flag cost-overrun on runtime_state so
        # `tripwire session list` can surface it.
        if action.tripwire_id == "monitor/cost_overrun":
            self._stamp_cost_overrun()
        self._append_monitor_log(action.tripwire_id, action.reason)
        if not sent:
            logger.warning(
                "monitor: SIGTERM target pid %d not found (%s)",
                action.pid,
                action.tripwire_id,
            )

    def _stamp_cost_overrun(self) -> None:
        try:
            session = load_session(self.project_dir, self.session_id)
        except FileNotFoundError:
            return
        if session.runtime_state.cost_overrun_at is not None:
            return  # idempotent — first crossing wins
        session.runtime_state.cost_overrun_at = datetime.now(tz=timezone.utc)
        session.updated_at = datetime.now(tz=timezone.utc)
        save_session(self.project_dir, session)

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
        # Shared coordinator: whichever resume path wins (poll thread
        # or defensive timer) sets this event so the other exits
        # without double-SIGCONT'ing.
        resume_event = self._resume_events.setdefault(action.pid, threading.Event())
        # Schedule a defensive SIGCONT — even if nothing else wakes
        # the agent, it can't be left frozen indefinitely.
        timer = threading.Timer(
            _DEFENSIVE_RESUME_SECONDS,
            self._defensive_resume,
            args=(action.pid, action.tripwire_id),
        )
        timer.daemon = True
        timer.start()
        # B4b — start the GH-polling resume thread when we know the PR
        # number AND the worktree to invoke `gh` from. Without either,
        # the defensive timer is the only path back.
        if action.pr_number is not None and action.code_worktree is not None:
            poller = threading.Thread(
                target=self._gh_poll_resume_loop,
                args=(
                    action.pid,
                    action.pr_number,
                    action.code_worktree,
                    resume_event,
                    action.tripwire_id,
                ),
                daemon=True,
                name=f"tw-ci-resume-{action.pid}",
            )
            poller.start()

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
        exited (pid gone), ``send_sigcont`` is a no-op. Always sets
        the per-pid resume event so any still-running poll thread
        exits without double-SIGCONT'ing.
        """
        resume_event = self._resume_events.get(pid)
        already_resumed = resume_event is not None and resume_event.is_set()
        if resume_event is not None:
            resume_event.set()
        if already_resumed:
            # Poll thread won the race; nothing left to do.
            return
        sent = send_sigcont(pid)
        self._append_monitor_log(
            "monitor/ci_wait_resume",
            (
                f"defensive sigcont pid={pid} sent={sent} "
                f"source={source_tripwire_id} after={_DEFENSIVE_RESUME_SECONDS}s"
            ),
        )

    # --- B4b: GH-polling resume ----------------------------------------

    def _gh_poll_once(
        self,
        *,
        pid: int,
        pr_number: int,
        code_worktree: Path,
        resume_event: threading.Event,
        source_tripwire_id: str,
    ) -> bool:
        """Single iteration of the GH-polling resume.

        Calls ``gh pr view <num> --json statusCheckRollup`` from the
        agent's code worktree, parses the rollup, and SIGCONTs when
        every check has ``status: COMPLETED``. Returns ``True`` iff
        SIGCONT fired on this iteration.

        Failure modes (timeouts, non-zero gh exit, malformed JSON,
        already-resumed-by-defensive-timer) all return ``False``
        without firing — the caller's loop sleeps and retries.
        """
        if resume_event.is_set():
            return False
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--json",
                    "statusCheckRollup",
                ],
                cwd=str(code_worktree),
                capture_output=True,
                text=True,
                timeout=_GH_POLL_CALL_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("monitor: gh poll subprocess error: %s", exc)
            return False
        if result.returncode != 0:
            logger.debug(
                "monitor: gh poll non-zero returncode %d (stderr=%r)",
                result.returncode,
                (result.stderr or "")[:200],
            )
            return False
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            logger.debug(
                "monitor: gh poll malformed JSON (stdout=%r)",
                (result.stdout or "")[:200],
            )
            return False
        if not _all_checks_completed(payload):
            return False
        # Race-check after the network call — a slow gh response could
        # have raced with the defensive timer.
        if resume_event.is_set():
            return False
        resume_event.set()
        sent = send_sigcont(pid)
        self._append_monitor_log(
            "monitor/ci_wait_resume",
            (
                f"gh-poll sigcont pid={pid} sent={sent} pr={pr_number} "
                f"source={source_tripwire_id}"
            ),
        )
        return True

    def _gh_poll_resume_loop(
        self,
        pid: int,
        pr_number: int,
        code_worktree: Path,
        resume_event: threading.Event,
        source_tripwire_id: str,
    ) -> None:
        """Daemon-thread driver: keep polling until SIGCONT fires or
        the resume event is set by the defensive timer."""
        while not resume_event.is_set():
            if self._gh_poll_once(
                pid=pid,
                pr_number=pr_number,
                code_worktree=code_worktree,
                resume_event=resume_event,
                source_tripwire_id=source_tripwire_id,
            ):
                return
            # Sleep on the event so a defensive-timer SIGCONT wakes
            # us immediately rather than waiting out the full
            # _GH_POLL_INTERVAL_SECONDS.
            if resume_event.wait(timeout=_GH_POLL_INTERVAL_SECONDS):
                return

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

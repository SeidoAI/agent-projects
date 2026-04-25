"""SubprocessRuntime — launches ``claude -p`` via Popen, streams output to a log.

The runtime is headless by design: claude runs to completion (opens
PR, exits) or stops early with a plain-text question in the log.
The human observes via ``tripwire session attach <id>`` (= tail -f
on the log file); there is no mid-run interactive channel.

This is the default runtime. ``-p`` mode sidesteps the workspace-
trust dialog, multi-line prompt quirks, and ready-probe fragility
that an interactive runtime would need to solve.
"""

from __future__ import annotations

import subprocess as _sp
import time
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.process_helpers import is_alive, send_sigterm
from tripwire.core.spawn_config import build_claude_args
from tripwire.models.session import AgentSession
from tripwire.runtimes.base import (
    AttachCommand,
    AttachExec,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
)
from tripwire.runtimes.monitor_runner import RunnerConfig, spawn_monitor_runner


def _render_log_path(prepped: PreppedSession) -> Path:
    """Render the ``log_path_template`` using the session's known fields."""
    template = prepped.spawn_defaults.invocation.log_path_template
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    raw = template.format(
        project_slug=prepped.project_slug,
        session_id=prepped.session_id,
        timestamp=ts,
    )
    return Path(raw).expanduser()


def _render_monitor_log_path(prepped: PreppedSession) -> Path:
    template = prepped.spawn_defaults.invocation.monitor_log_path_template
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    raw = template.format(
        project_slug=prepped.project_slug,
        session_id=prepped.session_id,
        timestamp=ts,
    )
    return Path(raw).expanduser()


def _build_runner_config(
    prepped: PreppedSession, agent_pid: int, agent_log_path: Path
) -> RunnerConfig:
    """Bundle everything the standalone monitor process needs to operate."""
    cfg_values = prepped.spawn_defaults.config
    # Code worktree is the agent's cwd; PT worktree is whichever entry
    # is NOT the code worktree (best-effort — None if not present).
    code_wt = prepped.code_worktree
    pt_wt: Path | None = None
    for wt in prepped.worktrees:
        wt_path = Path(wt.worktree_path)
        if wt_path != code_wt:
            pt_wt = wt_path
            break
    return RunnerConfig(
        session_id=prepped.session_id,
        pid=agent_pid,
        log_path=agent_log_path,
        code_worktree=code_wt,
        pt_worktree=pt_wt,
        project_dir=prepped.project_dir,
        max_budget_usd=float(cfg_values.max_budget_usd),
        monitor_log_path=_render_monitor_log_path(prepped),
        model_name=cfg_values.model,
        key_files=list(prepped.session.key_files),
        # Conservative default: required artifact for #9 is the
        # session's self-review.md committed under sessions/<sid>/.
        # Project-side artifact manifest (KUI-87) drives the broader
        # set; exposing it here would require a project-yaml load
        # we don't otherwise need at start time.
        required_artifacts=["self-review.md"],
        poll_interval=2.0,
    )


class SubprocessRuntime:
    name = "subprocess"

    def validate_environment(self) -> None:
        # claude-on-PATH is checked by the CLI layer before prep runs.
        return

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        argv = build_claude_args(
            prepped.spawn_defaults,
            prompt=prepped.prompt,
            interactive=False,
            system_append=prepped.system_append,
            session_id=prepped.session_id,
            claude_session_id=prepped.claude_session_id,
            resume=prepped.resume,
        )

        log_path = _render_log_path(prepped)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_path.open("a", encoding="utf-8")

        try:
            proc = _sp.Popen(
                argv,
                cwd=str(prepped.code_worktree),
                stdout=log_fh,
                stderr=_sp.STDOUT,
                start_new_session=True,
            )
        finally:
            log_fh.close()

        # v0.7.9 §A7 — fork the in-flight monitor so cost / quota /
        # push-loop tripwires fire even after the spawning CLI exits.
        # Failure to spawn the monitor is logged but does not abort
        # the agent launch (degraded mode > no-launch).
        if prepped.spawn_defaults.invocation.monitor:
            spawn_monitor_runner(
                cfg=_build_runner_config(prepped, proc.pid, log_path)
            )

        return RuntimeStartResult(
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
            pid=proc.pid,
            log_path=str(log_path),
        )

    def pause(self, session: AgentSession) -> None:
        pid = session.runtime_state.pid
        if not pid or not is_alive(pid):
            return
        send_sigterm(pid)
        # Poll until the process actually exits so the caller can set
        # status to 'paused' without lying about reality. Escalation to
        # SIGKILL is abandon's job, not pause's.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not is_alive(pid):
                return
            time.sleep(0.1)
        raise RuntimeError(
            f"SIGTERM not honoured within 2s for pid {pid} — "
            "escalate via 'tripwire session abandon'"
        )

    def abandon(self, session: AgentSession) -> None:
        pid = session.runtime_state.pid
        if not pid or not is_alive(pid):
            return
        send_sigterm(pid)
        # Give the process a moment to exit cleanly before escalating.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not is_alive(pid):
                return
            time.sleep(0.1)
        # Still alive — SIGKILL.
        import os
        import signal

        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def status(self, session: AgentSession) -> RuntimeStatus:
        pid = session.runtime_state.pid
        if not pid:
            return "unknown"
        return "running" if is_alive(pid) else "exited"

    def attach_command(self, session: AgentSession) -> AttachCommand:
        log_path = session.runtime_state.log_path
        if not log_path:
            return AttachInstruction(
                message=(
                    f"Session '{session.id}' has no log_path recorded. "
                    "The session was never spawned, or state was cleared "
                    "by 'tripwire session cleanup'."
                )
            )
        return AttachExec(argv=["tail", "-f", log_path])

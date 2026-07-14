"""SessionRuntime protocol and shared types.

Each runtime implementation (claude, codex, manual, future: container) owns
the lifecycle for one session: start, pause, abandon, status, attach.
The prep pipeline runs before ``start`` and is runtime-agnostic.

Subprocess-based runtimes (claude, codex) inherit from
:class:`BasePopenRuntime` which collects the verbatim-shared lifecycle
mechanics — log-path templating, monitor-runner spawn, SIGTERM-then-
SIGKILL pause/abandon, log-tail attach. Subclasses only customise
``name``, ``validate_environment``, and ``_build_argv``.
"""

from __future__ import annotations

import os
import signal
import subprocess as _sp
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from tripwire.core.process_helpers import is_alive, send_sigterm
from tripwire.models.session import AgentSession, WorktreeEntry
from tripwire.models.spawn import SpawnDefaults


@dataclass
class PreppedSession:
    """Output of the prep pipeline, consumed by a runtime's ``start``."""

    session_id: str
    session: AgentSession
    project_dir: Path
    code_worktree: Path
    worktrees: list[WorktreeEntry]
    claude_session_id: str
    prompt: str
    system_append: str
    project_slug: str
    spawn_defaults: SpawnDefaults
    resume: bool = False


@dataclass
class AttachExec:
    """Runtime wants `tripwire session attach` to execvp this argv."""

    argv: list[str]


@dataclass
class AttachInstruction:
    """Runtime has no process to attach to; print this message instead."""

    message: str


AttachCommand = AttachExec | AttachInstruction


RuntimeStatus = Literal["running", "exited", "unknown"]


@dataclass
class RuntimeStartResult:
    """What a runtime's ``start`` returns — fields the caller writes
    back onto ``session.runtime_state``."""

    claude_session_id: str
    worktrees: list[WorktreeEntry]
    started_at: str
    pid: int | None = None
    log_path: str | None = None


class SessionRuntime(Protocol):
    """Protocol for session execution runtimes."""

    name: str

    def validate_environment(self) -> None:
        """Raise with a user-facing message if this runtime can't run
        on this host (e.g. a required binary missing). Called at prep time BEFORE
        any filesystem mutation."""
        ...

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        """Launch the agent process. Returns state to persist on
        ``session.runtime_state``."""
        ...

    def pause(self, session: AgentSession) -> None: ...
    def abandon(self, session: AgentSession) -> None: ...
    def status(self, session: AgentSession) -> RuntimeStatus: ...
    def attach_command(self, session: AgentSession) -> AttachCommand: ...


# ----------------------------------------------------------------------------
# Shared mechanics for subprocess-based runtimes (claude, codex).
# ----------------------------------------------------------------------------


def _render_path_template(template: str, prepped: PreppedSession) -> Path:
    """Render a log-path template using session fields + a UTC timestamp."""
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    raw = template.format(
        project_slug=prepped.project_slug,
        session_id=prepped.session_id,
        timestamp=ts,
    )
    return Path(raw).expanduser()


class BasePopenRuntime(ABC):
    """Common lifecycle for subprocess-based runtimes.

    Subclasses provide ``name``, ``validate_environment`` (auth checks),
    and ``_build_argv`` (the runtime-specific command line). Everything
    else — Popen + log-fh handoff, monitor-runner fork, pause/abandon
    semantics, attach instructions — lives here.
    """

    name: str

    @abstractmethod
    def _build_argv(self, prepped: PreppedSession) -> list[str]:
        """Return the argv this runtime should execvp."""

    def validate_environment(self) -> None:
        # Subclasses override when the runtime needs an auth gate.
        return

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        argv = self._build_argv(prepped)

        log_path = _render_path_template(
            prepped.spawn_defaults.invocation.log_path_template, prepped
        )
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
        if prepped.spawn_defaults.invocation.monitor:
            from tripwire.core.runtime_config import load_resolved_runtime_config
            from tripwire.runtimes.monitor_runner import (
                RunnerConfig,
                spawn_monitor_runner,
            )

            cfg_values = prepped.spawn_defaults.config
            code_wt = prepped.code_worktree
            pt_wt: Path | None = None
            for wt in prepped.worktrees:
                wt_path = Path(wt.worktree_path)
                if wt_path != code_wt:
                    pt_wt = wt_path
                    break
            monitor_log_path = _render_path_template(
                prepped.spawn_defaults.invocation.monitor_log_path_template, prepped
            )
            # v0.14.0 — runtime tunables (stream_idle, max_runtime,
            # push_loop thresholds) live in
            # templates/runtime/defaults.yaml + project overrides.
            runtime = load_resolved_runtime_config(prepped.project_dir).monitor
            spawn_monitor_runner(
                cfg=RunnerConfig(
                    session_id=prepped.session_id,
                    pid=proc.pid,
                    log_path=log_path,
                    code_worktree=code_wt,
                    pt_worktree=pt_wt,
                    project_dir=prepped.project_dir,
                    max_budget_usd=float(cfg_values.max_budget_usd),
                    monitor_log_path=monitor_log_path,
                    stream_idle_threshold_seconds=runtime.stream_idle_threshold_seconds,
                    max_runtime_seconds=runtime.max_runtime_seconds,
                    push_loop_warn_threshold=runtime.push_loop.warn_threshold,
                    push_loop_terminate_threshold=runtime.push_loop.terminate_threshold,
                    model_name=cfg_values.model,
                    key_files=list(prepped.session.key_files),
                    required_artifacts=["self-review.md"],
                    poll_interval=2.0,
                )
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
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not is_alive(pid):
                return
            time.sleep(0.1)
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

"""CodexRuntime — launches OpenAI's ``codex exec --json`` via Popen.

Parallel adapter to :class:`ClaudeRuntime`: same ``SessionRuntime``
contract, same SIGTERM-then-SIGKILL pause/abandon semantics, same
log-tail attach mechanism. The differences are confined to:

  - the binary (``codex`` instead of ``claude``)
  - the argv shape (see :func:`tripwire.core.codex_args.build_codex_args`)
  - the auth gate (``OPENAI_API_KEY`` env var or a prior ``codex login``
    that wrote ``~/.codex/auth.json``)
  - the resume path (``codex exec resume <SESSION_ID>`` is a subcommand,
    not a flag)

The runtime delegates argv assembly to ``build_codex_args`` so the
flag mapper stays out of the lifecycle code; this file owns Popen,
log files, and signal handling only.
"""

from __future__ import annotations

import os
import subprocess as _sp
import time
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.process_helpers import is_alive, send_sigterm
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
    cfg_values = prepped.spawn_defaults.config
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
        required_artifacts=["self-review.md"],
        poll_interval=2.0,
    )


def _has_codex_auth() -> bool:
    """Detect whether the host can authenticate to the Codex API.

    Two paths: ``OPENAI_API_KEY`` env var, or a prior ``codex login`` that
    persisted credentials under ``~/.codex/auth.json``. Either is enough."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    home = os.environ.get("HOME")
    if not home:
        return False
    return (Path(home) / ".codex" / "auth.json").is_file()


class CodexRuntime:
    name = "codex"

    def validate_environment(self) -> None:
        # codex-on-PATH is checked by the CLI layer before prep runs;
        # auth is the runtime-specific gate.
        if not _has_codex_auth():
            raise RuntimeError(
                "Codex runtime requires authentication. Set OPENAI_API_KEY "
                "or run 'codex login --with-api-key' to persist credentials "
                "under ~/.codex/auth.json."
            )

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        # Imported here to avoid a cycle: codex_args lives under core/
        # and may eventually want to import from runtimes for shared
        # helpers (e.g. skill-inlining). Keeping the import local
        # sidesteps that risk.
        from tripwire.core.codex_args import build_codex_args

        argv = build_codex_args(
            prepped.spawn_defaults,
            prompt=prepped.prompt,
            interactive=False,
            system_append=prepped.system_append,
            session_id=prepped.session_id,
            codex_session_id=prepped.claude_session_id,
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

        if prepped.spawn_defaults.invocation.monitor:
            spawn_monitor_runner(cfg=_build_runner_config(prepped, proc.pid, log_path))

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

"""Long-lived monitor process runner.

Spawned by :class:`ClaudeRuntime` (and :class:`CodexRuntime`) as a detached subprocess so the
in-flight monitor outlives the CLI invocation that launched the
agent. Owns:

  - one :class:`RuntimeMonitor` (pure-function tripwire policy)
  - one :class:`MonitorThread` (tails the agent's stream-json log)
  - one :class:`ActionExecutor` (turns actions into side effects)

The runner polls ``cfg.pid`` every ``cfg.poll_interval`` seconds.
When the agent process dies (or the safety cap fires), it flushes
any remaining log lines, runs the on-process-exit tripwires, and
exits.

Invoked as ``python -m tripwire.runtimes.monitor_runner <ctx-json>``.
The ctx-json file is written by the runtime at spawn time and
contains everything the runner needs to operate independently of
the parent CLI.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tripwire.core.process_helpers import is_alive
from tripwire.runtimes.monitor import (
    InjectFollowUp,
    LogWarning,
    MonitorContext,
    MonitorThread,
    RuntimeMonitor,
    SigtermProcess,
    TransitionStatus,
)
from tripwire.runtimes.monitor_actions import ActionExecutor

STREAM_IDLE_TRIPWIRE_ID = "monitor/stream_idle"

logger = logging.getLogger(__name__)


@dataclass
class RunnerConfig:
    """Serialisable handoff between the runtime that spawns the agent
    and the standalone monitor process. JSON-encoded; paths are
    rendered as strings on disk and decoded back to :class:`Path`.
    """

    session_id: str
    pid: int
    log_path: Path
    code_worktree: Path
    pt_worktree: Path | None
    project_dir: Path
    max_budget_usd: float
    monitor_log_path: Path
    model_name: str = "claude-opus-4-7"
    key_files: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    poll_interval: float = 1.0
    # Stream-idle threshold: if the agent's log file has produced no
    # new events for this many seconds while the process is still
    # alive, the runner classifies it as a silent stream-idle death
    # (typically a wedged libuv loop after a SIGSTOP/SIGCONT cycle, or
    # a `claude -p` post-end_turn hang) and reaps it. 600s = 10 min,
    # well above any normal between-events gap during heavy tool use.
    stream_idle_threshold_seconds: float = 600.0


def write_runner_config(cfg: RunnerConfig, target: Path) -> None:
    payload = asdict(cfg)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_runner_config(source: Path) -> RunnerConfig:
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["log_path"] = Path(raw["log_path"])
    raw["code_worktree"] = Path(raw["code_worktree"])
    raw["pt_worktree"] = Path(raw["pt_worktree"]) if raw.get("pt_worktree") else None
    raw["project_dir"] = Path(raw["project_dir"])
    raw["monitor_log_path"] = Path(raw["monitor_log_path"])
    return RunnerConfig(**raw)


class MonitorRunner:
    """Owns the monitor + executor + log-tail thread for one agent."""

    def __init__(
        self,
        cfg: RunnerConfig,
        *,
        max_runtime_seconds: float = 6 * 60 * 60,  # 6h hard cap
    ) -> None:
        self.cfg = cfg
        self.max_runtime_seconds = max_runtime_seconds
        self.exit_reason: str | None = None
        self._executor = ActionExecutor(
            project_dir=cfg.project_dir,
            session_id=cfg.session_id,
            monitor_log_path=cfg.monitor_log_path,
        )
        self._monitor = RuntimeMonitor(
            MonitorContext(
                session_id=cfg.session_id,
                pid=cfg.pid,
                log_path=cfg.log_path,
                code_worktree=cfg.code_worktree,
                pt_worktree=cfg.pt_worktree,
                project_dir=cfg.project_dir,
                max_budget_usd=cfg.max_budget_usd,
                model_name=cfg.model_name,
                key_files=list(cfg.key_files),
                required_artifacts=list(cfg.required_artifacts),
            )
        )
        self._thread = MonitorThread(
            self._monitor,
            self._executor.execute,
            poll_interval=cfg.poll_interval,
        )

    def run(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + self.max_runtime_seconds
        try:
            while True:
                if not is_alive(self.cfg.pid):
                    self.exit_reason = "pid_dead"
                    return
                if time.monotonic() >= deadline:
                    self.exit_reason = "max_runtime"
                    return
                if self._is_stream_idle():
                    self._reap_stream_idle()
                    self.exit_reason = "stream_idle"
                    return
                time.sleep(self.cfg.poll_interval)
        finally:
            # Flush remaining lines + run on-exit tripwires + stop thread.
            self._thread.on_process_exit(exit_code=None)
            self._thread.stop()

    def _is_stream_idle(self) -> bool:
        """True when the agent's log has produced no events for longer
        than the configured threshold while the process is still alive.

        Symptom of a wedged libuv loop (post-SIGSTOP/SIGCONT) or a
        `claude -p` that didn't `_exit` after `result/end_turn`.
        Process is technically alive but doing no useful work.
        """
        if self.cfg.stream_idle_threshold_seconds <= 0:
            return False
        idle_for = time.monotonic() - self._thread.last_event_at
        return idle_for > self.cfg.stream_idle_threshold_seconds

    def _reap_stream_idle(self) -> None:
        """SIGTERM the wedged agent + flip session status to ``failed``
        + leave a follow-up note in the plan so the next ``--resume``
        spawn knows what happened."""
        idle_minutes = (time.monotonic() - self._thread.last_event_at) / 60.0
        reason = (
            f"agent log produced no events for ~{idle_minutes:.0f} min "
            f"while pid {self.cfg.pid} was still alive; "
            f"classified as silent stream-idle (likely a wedged libuv "
            f"loop after a SIGSTOP/SIGCONT cycle or a claude -p "
            f"post-end_turn hang)"
        )
        followup = (
            "## PM follow-up — silent stream-idle reaper\n\n"
            f"Previous engagement was reaped at {idle_minutes:.0f} min "
            "of stream silence. Your prior conversation is preserved; "
            "resume from where you left off. If you were in PR closeout, "
            "verify the closing comment + status transition landed before "
            "the silence began."
        )
        self._executor.execute(
            LogWarning(
                tripwire_id=STREAM_IDLE_TRIPWIRE_ID,
                message=reason,
            )
        )
        self._executor.execute(
            SigtermProcess(
                tripwire_id=STREAM_IDLE_TRIPWIRE_ID,
                pid=self.cfg.pid,
                reason=reason,
            )
        )
        self._executor.execute(
            TransitionStatus(
                tripwire_id=STREAM_IDLE_TRIPWIRE_ID,
                new_status="failed",
                reason=reason,
            )
        )
        self._executor.execute(
            InjectFollowUp(
                tripwire_id=STREAM_IDLE_TRIPWIRE_ID,
                message=followup,
                target="plan.md",
            )
        )


def spawn_monitor_runner(
    cfg: RunnerConfig,
    *,
    ctx_path: Path | None = None,
) -> int | None:
    """Fork a detached monitor process for the supplied agent.

    Writes ``cfg`` as JSON to ``ctx_path`` (defaulting to a sibling of
    the agent's log file) and spawns ``python -m
    tripwire.runtimes.monitor_runner <ctx-json>`` with
    ``start_new_session=True`` so the monitor outlives the CLI
    invocation. Returns the spawned monitor pid, or None on failure.
    """
    if ctx_path is None:
        ctx_path = cfg.log_path.with_suffix(".monitor-ctx.json")
    write_runner_config(cfg, ctx_path)
    cfg.monitor_log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = cfg.monitor_log_path.open("a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "tripwire.runtimes.monitor_runner", str(ctx_path)],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except (OSError, FileNotFoundError) as exc:
        logger.warning("monitor: failed to spawn runner subprocess: %s", exc)
        return None
    finally:
        log_fh.close()
    return proc.pid


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 1:
        print(
            "usage: python -m tripwire.runtimes.monitor_runner <ctx.json>",
            file=sys.stderr,
        )
        return 2
    ctx_path = Path(args[0])
    cfg = read_runner_config(ctx_path)
    runner = MonitorRunner(cfg)
    runner.run()
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess
    sys.exit(main())


__all__ = [
    "MonitorRunner",
    "RunnerConfig",
    "main",
    "read_runner_config",
    "spawn_monitor_runner",
    "write_runner_config",
]

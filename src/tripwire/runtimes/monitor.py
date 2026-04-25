"""In-flight runtime monitor (v0.7.9 §A7).

The monitor watches the stream-json log of a running ``claude -p``
process and emits :class:`MonitorAction` records when one of six
tripwires fires:

  #9   final-text "session complete" with required artifacts missing
  #10  ``gh pr create`` from code worktree but PT branch has no commits
  #11  commits diverge from ``session.key_files`` (warn-only)
  #12  cumulative session cost exceeds ``max_budget_usd`` — SIGTERMs
  #13  quota error in stream → auto-transition to ``failed``
  #14  >5/>10 consecutive failed ``git push`` attempts → warn / SIGTERM

Design notes
------------
- :class:`RuntimeMonitor` is pure-function over events for testability.
  It accumulates state internally (cost, push counter, final text)
  but never executes side effects — actions go to a sink the caller
  owns.
- :class:`MonitorThread` wraps the monitor in a daemon thread that
  tails the log file in append-only mode. It calls the monitor's
  ``process_event`` per JSON line and forwards each emitted action
  to the sink.
- Action *execution* (SIGTERM, status writeback, follow-up injection)
  lives in :mod:`tripwire.runtimes.monitor_actions` so tests can
  exercise the policy independently from the side effects.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------- Pricing ------------------------------------------------------


_PRICING_PATH = Path(__file__).parent.parent / "data" / "anthropic_pricing.yaml"


@dataclass(frozen=True)
class _ModelRates:
    input: float
    output: float
    cache_read: float
    cache_write: float


_pricing_cache: dict[str, _ModelRates] | None = None
_default_rates_cache: _ModelRates | None = None


def _load_pricing() -> tuple[dict[str, _ModelRates], _ModelRates]:
    """Read ``anthropic_pricing.yaml`` once and memoise."""
    global _pricing_cache, _default_rates_cache
    if _pricing_cache is not None and _default_rates_cache is not None:
        return _pricing_cache, _default_rates_cache
    raw = yaml.safe_load(_PRICING_PATH.read_text(encoding="utf-8"))
    models = {
        name: _ModelRates(**rates) for name, rates in (raw.get("models") or {}).items()
    }
    default = _ModelRates(**raw["default"])
    _pricing_cache = models
    _default_rates_cache = default
    return models, default


def _rate_for(model_name: str) -> _ModelRates:
    """Pick the longest-key prefix match for ``model_name``, else default."""
    models, default = _load_pricing()
    matches = [k for k in models if k in model_name]
    if not matches:
        return default
    best = max(matches, key=len)
    return models[best]


def _cost_for_usage(model_name: str, usage: dict[str, Any]) -> float:
    """Compute USD cost for a single ``usage`` payload."""
    rates = _rate_for(model_name)
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    crd = int(usage.get("cache_read_input_tokens") or 0)
    cwr = int(usage.get("cache_creation_input_tokens") or 0)
    return (
        inp * rates.input
        + out * rates.output
        + crd * rates.cache_read
        + cwr * rates.cache_write
    ) / 1_000_000


# ---------- Action types --------------------------------------------------


@dataclass
class LogWarning:
    tripwire_id: str
    message: str


@dataclass
class SigtermProcess:
    tripwire_id: str
    pid: int
    reason: str


@dataclass
class TransitionStatus:
    tripwire_id: str
    new_status: str
    reason: str


@dataclass
class InjectFollowUp:
    """Append a ``## PM follow-up`` block somewhere the next agent
    spawn will read it. ``target`` is one of:
      - ``"plan.md"`` — append to the session's plan file
      - ``"next-message"`` — buffer for the next ``--resume`` spawn
    """

    tripwire_id: str
    message: str
    target: str = "plan.md"


MonitorAction = LogWarning | SigtermProcess | TransitionStatus | InjectFollowUp


# ---------- Context -------------------------------------------------------


@dataclass
class MonitorContext:
    """Per-spawn read-only context handed to the monitor.

    The monitor doesn't fetch session state on its own — the caller
    populates everything it might need to evaluate a tripwire here.
    Keeps the monitor a pure function of (context, event-stream).
    """

    session_id: str
    pid: int
    log_path: Path
    code_worktree: Path
    pt_worktree: Path | None
    project_dir: Path
    max_budget_usd: float
    model_name: str = "claude-opus-4-7"
    key_files: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)


# ---------- Helpers used by tripwires -------------------------------------


def _pt_branch_has_commits(pt_worktree: Path) -> bool:
    """Return True if the PT worktree has any commits beyond ``origin/main``.

    Wrapped in a module-level function so tests can patch it without
    needing a real git repo on disk.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(pt_worktree),
                "rev-list",
                "--count",
                "HEAD",
                "^origin/main",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    if result.returncode != 0:
        return False
    return int((result.stdout or "0").strip() or "0") > 0


def _committed_paths_in_branch(worktree: Path) -> set[str]:
    """Return all file paths committed on the worktree's current branch."""
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree), "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.splitlines() if line}


def _commits_diff_files(worktree: Path) -> set[str]:
    """Return paths touched on the worktree's branch since ``origin/main``."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "diff",
                "--name-only",
                "origin/main...HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.splitlines() if line}


# ---------- Monitor -------------------------------------------------------


_QUOTA_PATTERNS = (
    "quota exceeded",
    "credit balance",
    "insufficient credit",
    "rate_limit_error",
    "billing",
)


_PUSH_FAILURE_PATTERNS = (
    "failed to push",
    "rejected (non-fast-forward)",
    "rejected (fetch first)",
    "remote rejected",
)


class RuntimeMonitor:
    """Pure-function monitor: events in, actions out.

    Stateful between calls (accumulates cost, tracks push failures,
    holds the most recent assistant text) but does not perform any
    side effects — :class:`MonitorThread` or the test harness owns
    the action sink.
    """

    def __init__(self, ctx: MonitorContext) -> None:
        self.ctx = ctx
        self.cumulative_cost_usd = 0.0
        self._cost_overrun_fired = False
        self._consecutive_failed_pushes = 0
        self._push_warning_fired = False
        self._push_sigterm_fired = False
        self._last_pending_push_id: str | None = None
        self._final_text = ""
        self._session_complete_text_seen = False
        self._quota_error_fired = False

    # --- public surface -------------------------------------------------

    def process_event(self, event: dict[str, Any]) -> list[MonitorAction]:
        actions: list[MonitorAction] = []
        kind = event.get("type")
        if kind == "assistant":
            self._handle_assistant(event, actions)
        elif kind == "user":
            self._handle_user(event, actions)
        elif kind == "result":
            self._handle_result(event, actions)
        return actions

    def on_process_exit(self, exit_code: int | None) -> list[MonitorAction]:
        """Run final-state checks (#9, #11) when the agent process exits."""
        actions: list[MonitorAction] = []
        self._check_session_complete_no_artifacts(actions)
        self._check_key_files_drift(actions)
        return actions

    # --- handlers -------------------------------------------------------

    def _handle_assistant(
        self, event: dict[str, Any], actions: list[MonitorAction]
    ) -> None:
        message = event.get("message") or {}
        # cost accumulation (#12)
        usage = message.get("usage") or {}
        if usage:
            model = message.get("model") or self.ctx.model_name
            self.cumulative_cost_usd += _cost_for_usage(model, usage)
            self._maybe_fire_cost_overrun(actions)
        # tool_use blocks: detect `gh pr create` and remember pending pushes
        content = message.get("content") or []
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                self._handle_tool_use(block, actions)
            elif btype == "text":
                text = block.get("text") or ""
                if isinstance(text, str) and text.strip():
                    self._final_text = text
                    self._check_session_complete_marker(text)

    def _handle_tool_use(
        self, block: dict[str, Any], actions: list[MonitorAction]
    ) -> None:
        name = block.get("name") or ""
        inp = block.get("input") or {}
        cmd = ""
        if name == "Bash" and isinstance(inp, dict):
            cmd = str(inp.get("command") or "")
        # #14 — track git pushes; remember the tool_use id so the
        # tool_result can be matched.
        if cmd and self._is_git_push(cmd):
            self._last_pending_push_id = block.get("id") or "<no-id>"
        # #10 — `gh pr create` from code worktree
        if cmd and self._is_pr_create(cmd):
            self._check_code_pr_no_pt(actions)

    def _handle_user(self, event: dict[str, Any], actions: list[MonitorAction]) -> None:
        message = event.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            # If we have a pending push tool_use_id, this result decides it.
            if self._last_pending_push_id is None:
                continue
            text = self._stringify_tool_result(block.get("content"))
            is_error = bool(block.get("is_error")) or self._looks_like_push_failure(
                text
            )
            if is_error:
                self._consecutive_failed_pushes += 1
                self._maybe_fire_push_loop(actions)
            else:
                # Successful push resets the streak.
                self._consecutive_failed_pushes = 0
                self._push_warning_fired = False
            self._last_pending_push_id = None

    def _handle_result(
        self, event: dict[str, Any], actions: list[MonitorAction]
    ) -> None:
        # #13 — quota / billing errors that surface in the result.
        text_blob = ""
        for key in ("result", "error", "message"):
            val = event.get(key)
            if isinstance(val, str):
                text_blob += " " + val
        text_lower = text_blob.lower()
        if event.get("is_error") or event.get("subtype") == "error":
            if any(pat in text_lower for pat in _QUOTA_PATTERNS):
                if not self._quota_error_fired:
                    self._quota_error_fired = True
                    actions.append(
                        TransitionStatus(
                            tripwire_id="monitor/quota_error",
                            new_status="failed",
                            reason=f"Quota / billing error in stream: {text_blob.strip()[:200]}",
                        )
                    )

    # --- tripwire firing logic -----------------------------------------

    def _maybe_fire_cost_overrun(self, actions: list[MonitorAction]) -> None:
        if self._cost_overrun_fired:
            return
        if self.cumulative_cost_usd < self.ctx.max_budget_usd:
            return
        self._cost_overrun_fired = True
        reason = (
            f"Cumulative session cost ${self.cumulative_cost_usd:.4f} "
            f"exceeds max_budget_usd ${self.ctx.max_budget_usd:.2f}"
        )
        actions.append(
            SigtermProcess(
                tripwire_id="monitor/cost_overrun",
                pid=self.ctx.pid,
                reason=reason,
            )
        )
        actions.append(
            TransitionStatus(
                tripwire_id="monitor/cost_overrun",
                new_status="paused",
                reason=reason,
            )
        )
        actions.append(
            InjectFollowUp(
                tripwire_id="monitor/cost_overrun",
                message=(
                    "## PM follow-up — cost overrun\n\n"
                    f"Session was halted by the runtime monitor: {reason}.\n"
                    "Review the work-to-date, decide whether to bump the "
                    "budget and resume, scope down, or abandon."
                ),
                target="plan.md",
            )
        )

    def _maybe_fire_push_loop(self, actions: list[MonitorAction]) -> None:
        n = self._consecutive_failed_pushes
        if n >= 10 and not self._push_sigterm_fired:
            self._push_sigterm_fired = True
            actions.append(
                SigtermProcess(
                    tripwire_id="monitor/push_loop",
                    pid=self.ctx.pid,
                    reason=f"{n} consecutive failed git push attempts — loop detected",
                )
            )
            return
        if n >= 5 and not self._push_warning_fired:
            self._push_warning_fired = True
            actions.append(
                LogWarning(
                    tripwire_id="monitor/push_loop",
                    message=(
                        f"{n} consecutive failed git push attempts. "
                        "Looks like the agent may be in a push loop."
                    ),
                )
            )

    def _check_code_pr_no_pt(self, actions: list[MonitorAction]) -> None:
        pt = self.ctx.pt_worktree
        if pt is None:
            return
        if _pt_branch_has_commits(pt):
            return
        actions.append(
            InjectFollowUp(
                tripwire_id="monitor/code_pr_no_pt",
                message=(
                    "## PM follow-up — code PR opened, project-tracking branch empty\n\n"
                    "The runtime detected a `gh pr create` from the code "
                    "worktree but the project-tracking worktree has no "
                    "commits beyond `origin/main`. Per the v0.7.9 exit "
                    "protocol, BOTH PRs must exist — author the PT-side "
                    "artifacts (developer.md, verified.md, self-review.md, "
                    "insights.yaml) and open the PT PR."
                ),
                target="plan.md",
            )
        )

    def _check_session_complete_marker(self, text: str) -> None:
        lowered = text.lower()
        if "session complete" in lowered or "session is complete" in lowered:
            self._session_complete_text_seen = True

    def _check_session_complete_no_artifacts(
        self, actions: list[MonitorAction]
    ) -> None:
        if not self._session_complete_text_seen:
            return
        if not self.ctx.required_artifacts:
            return
        committed = _committed_paths_in_branch(self.ctx.code_worktree)
        # An artifact counts as committed if any committed path ends with it.
        missing = [
            a
            for a in self.ctx.required_artifacts
            if not any(p.endswith(a) for p in committed)
        ]
        if not missing:
            return
        actions.append(
            InjectFollowUp(
                tripwire_id="monitor/session_complete_no_artifacts",
                message=(
                    "## PM follow-up — session declared complete without artifacts\n\n"
                    "The agent's final text contained 'session complete' but "
                    "the following required artifacts are not committed to "
                    f"the branch: {', '.join(missing)}. Author them before "
                    "exiting."
                ),
                target="plan.md",
            )
        )

    def _check_key_files_drift(self, actions: list[MonitorAction]) -> None:
        if not self.ctx.key_files:
            return
        touched = _commits_diff_files(self.ctx.code_worktree)
        if not touched:
            return
        allowed = set(self.ctx.key_files)
        drift = sorted(p for p in touched if p not in allowed)
        if not drift:
            return
        actions.append(
            LogWarning(
                tripwire_id="monitor/key_files_drift",
                message=(
                    "Commits touched files outside session.key_files: "
                    + ", ".join(drift)
                ),
            )
        )

    # --- low-level helpers ---------------------------------------------

    @staticmethod
    def _is_git_push(cmd: str) -> bool:
        cmd = cmd.strip()
        return "git push" in cmd or (cmd.startswith("git -C") and " push " in cmd)

    @staticmethod
    def _is_pr_create(cmd: str) -> bool:
        return "gh pr create" in cmd

    @staticmethod
    def _stringify_tool_result(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    txt = block.get("text") or block.get("content")
                    if isinstance(txt, str):
                        parts.append(txt)
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _looks_like_push_failure(text: str) -> bool:
        lowered = text.lower()
        return any(pat in lowered for pat in _PUSH_FAILURE_PATTERNS)


# ---------- Threaded log tail --------------------------------------------


class MonitorThread:
    """Daemon thread that tails ``ctx.log_path`` and feeds the monitor.

    Polls the file at ``poll_interval`` seconds, reads any new bytes,
    splits on newlines, and dispatches each parsed event to
    :meth:`RuntimeMonitor.process_event`. Each emitted action is
    forwarded to the supplied ``sink`` callable.
    """

    def __init__(
        self,
        monitor: RuntimeMonitor,
        sink: Callable[[MonitorAction], None],
        *,
        poll_interval: float = 0.5,
    ) -> None:
        self._monitor = monitor
        self._sink = sink
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._buffer = ""
        self._offset = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="tw-monitor"
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def on_process_exit(self, exit_code: int | None = None) -> None:
        """Flush any remaining lines, then dispatch ``on_process_exit`` actions."""
        self._read_once()
        for action in self._monitor.on_process_exit(exit_code):
            self._sink(action)

    def _run(self) -> None:
        log_path = self._monitor.ctx.log_path
        # Wait for the file to appear, but bail if asked to stop.
        while not self._stop.is_set() and not log_path.exists():
            if self._stop.wait(self._poll_interval):
                return
        while not self._stop.is_set():
            self._read_once()
            if self._stop.wait(self._poll_interval):
                return

    def _read_once(self) -> None:
        log_path = self._monitor.ctx.log_path
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._offset)
                chunk = f.read()
                self._offset = f.tell()
        except FileNotFoundError:
            return
        if not chunk:
            return
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("monitor: skipping malformed JSONL line: %r", line[:80])
                continue
            if not isinstance(event, dict):
                continue
            try:
                actions = self._monitor.process_event(event)
            except Exception:
                logger.exception("monitor: process_event raised on event %r", event)
                continue
            for action in actions:
                try:
                    self._sink(action)
                except Exception:
                    logger.exception("monitor: action sink raised on %r", action)


__all__ = [
    "InjectFollowUp",
    "LogWarning",
    "MonitorAction",
    "MonitorContext",
    "MonitorThread",
    "RuntimeMonitor",
    "SigtermProcess",
    "TransitionStatus",
]

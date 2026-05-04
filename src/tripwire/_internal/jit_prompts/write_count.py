"""Write-count JIT prompt — KUI-141 / B7.

Fires on ``session.complete`` when the count of file-edit tool
invocations in the session's claude stream-json log exceeds a
threshold (default 20). Forces a validation cadence: long runs of
edits without intervening validation accumulate drift.

Per-project override: if ``project.yaml.jit_prompts.extra`` carries an
entry with ``id: write-count`` and a ``params: {threshold: N}`` key,
that ``N`` overrides the default. The override does NOT affect the
manifest registration — the JIT prompt is registered once via the
built-in manifest; the ``extra`` entry is read solely for its params.

Per the v0.9 plan's stop-and-ask escape, this implementation does not
read ``validate.run`` events from the events log (the validate CLI
doesn't emit them yet). The threshold itself enforces validation
cadence; once acked, the JIT prompt stays silent for the session. See
``decisions.md`` D6 for the rationale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import yaml

from tripwire._internal.jit_prompts import JitPrompt, JitPromptContext

DEFAULT_WRITE_COUNT_THRESHOLD = 20

_WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})


_VARIATIONS: tuple[str, ...] = (
    """\
You've made more file edits in this session than the configured
write-count threshold without an intervening `tripwire validate`
run. The pattern this catches: long edit-only stretches accumulate
drift between code state and the validators' last clean run, and
late surprises become harder to attribute.

Run `tripwire validate` now. Walk the findings:

  - Each error → fix in this session, before completing.
  - Each warning → ack inline (commit message references it) or
    open a follow-up issue.

Re-run `session complete --ack` once the marker carries fix-commit
SHAs OR `declared_no_findings: true`.
""",
    """\
Stop. The write count for this session has crossed the threshold.
Validation cadence is the pattern this JIT prompt enforces: edit, run
validate, edit, run validate. Long edit stretches without validation
mean broken contracts can ride for hundreds of lines before anyone
notices.

Now:

  1. Run `tripwire validate` from the session worktree.
  2. Walk the findings — fix or ack each one.
  3. Commit the fix(es) and reference the SHAs in the ack marker.

Re-run with `--ack`. The marker is rejected if it lacks fix-commit
SHAs and does not declare `declared_no_findings: true`.
""",
    """\
The write-count JIT prompt is a smoke alarm for "I forgot to validate".
You've crossed the threshold. Don't argue with the alarm — run
validation.

Concretely:

  - `tripwire validate` from the session worktree.
  - For each error: fix it in a single commit; reference the SHA
    in the ack marker.
  - For each warning: either fix in-line OR file a follow-up issue
    AND note the deferral in `decisions.md`.

The threshold itself is configurable via
`project.yaml.jit_prompts.extra` for an `id: write-count` entry's
`params: {threshold: N}`; bump it if 20 is genuinely too low for
your project's idiom. Default exists for a reason.

Re-run `--ack` once the marker is substantive.
""",
)


class WriteCountJitPrompt(JitPrompt):
    """Block when file-edit count crosses the configured threshold."""

    id: ClassVar[str] = "write-count"
    fires_on: ClassVar[str] = "session.complete"
    blocks: ClassVar[bool] = True

    def fire(self, ctx: JitPromptContext) -> str:
        idx = ctx.variation_index(len(_VARIATIONS))
        return _VARIATIONS[idx]

    def is_acknowledged(self, ctx: JitPromptContext) -> bool:
        marker = ctx.ack_path(self.id)
        if not marker.is_file():
            return False
        return _marker_substantive(marker)

    def should_fire(self, ctx: JitPromptContext) -> bool:
        log_path = _session_log_path(ctx.project_dir, ctx.session_id)
        if log_path is None:
            return False
        threshold = _read_threshold(ctx.project_dir)
        return _count_writes(log_path) > threshold


def _count_writes(log_path: Path) -> int:
    """Count Edit/Write/NotebookEdit tool_use events in the claude log."""
    if not log_path.is_file():
        return 0
    count = 0
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            if block.get("name") in _WRITE_TOOLS:
                count += 1
    return count


def _read_threshold(project_dir: Path) -> int:
    """Resolve the threshold from project.yaml or fall back to default."""
    project_yaml = project_dir / "project.yaml"
    if not project_yaml.is_file():
        return DEFAULT_WRITE_COUNT_THRESHOLD
    try:
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return DEFAULT_WRITE_COUNT_THRESHOLD
    if not isinstance(data, dict):
        return DEFAULT_WRITE_COUNT_THRESHOLD
    jit_prompts = data.get("jit_prompts")
    if not isinstance(jit_prompts, dict):
        return DEFAULT_WRITE_COUNT_THRESHOLD
    extras = jit_prompts.get("extra") or []
    if not isinstance(extras, list):
        return DEFAULT_WRITE_COUNT_THRESHOLD
    for entry in extras:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") != WriteCountJitPrompt.id:
            continue
        params = entry.get("params") or {}
        if not isinstance(params, dict):
            continue
        threshold = params.get("threshold")
        if isinstance(threshold, int) and threshold > 0:
            return threshold
    return DEFAULT_WRITE_COUNT_THRESHOLD


def _session_log_path(project_dir: Path, session_id: str) -> Path | None:
    """Resolve runtime_state.log_path from session.yaml without typed loaders.

    Avoids importing the full session model so unit fixtures don't
    have to satisfy every required field.
    """
    syaml = project_dir / "sessions" / session_id / "session.yaml"
    if not syaml.is_file():
        return None
    try:
        text = syaml.read_text(encoding="utf-8")
    except OSError:
        return None
    payload_text = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            payload_text = parts[1]
    try:
        data = yaml.safe_load(payload_text) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    runtime = data.get("runtime_state") or {}
    if not isinstance(runtime, dict):
        return None
    raw = runtime.get("log_path")
    if not isinstance(raw, str) or not raw:
        return None
    return Path(raw).expanduser()


def _marker_substantive(marker_path: Path) -> bool:
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    commits = data.get("fix_commits")
    declared = data.get("declared_no_findings")
    has_commits = isinstance(commits, list) and any(
        isinstance(s, str) and s.strip() for s in commits
    )
    return bool(has_commits or declared is True)


__all__ = ["DEFAULT_WRITE_COUNT_THRESHOLD", "WriteCountJitPrompt"]

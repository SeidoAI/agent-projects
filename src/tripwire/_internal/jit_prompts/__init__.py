"""JIT prompt primitive: base class, context, and event orchestrator.

A JIT prompt is a lifecycle prompt delivered at the moment it is most useful
for instruction-following. Some prompts are withheld until they fire; others
reinforce known workflow requirements with recency bias. Blocking prompts
require acknowledgement via ``--ack``.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class JitPromptContext:
    """Context object passed to ``JitPrompt.fire`` / ``is_acknowledged``."""

    project_dir: Path
    session_id: str
    project_id: str

    def ack_path(self, jit_prompt_id: str) -> Path:
        """Marker file path for an ack from this context."""
        return (
            self.project_dir
            / ".tripwire"
            / "acks"
            / f"{jit_prompt_id}-{self.session_id}.json"
        )

    def variation_index(self, n_variations: int) -> int:
        """Deterministic variation pick from ``hash(project_id, session_id)``."""
        if n_variations <= 0:
            raise ValueError("n_variations must be positive")
        seed = f"{self.project_id}:{self.session_id}".encode()
        digest = hashlib.sha256(seed).digest()
        return int.from_bytes(digest[:8], "big") % n_variations


class JitPrompt(ABC):
    """Base class for JIT prompts."""

    id: ClassVar[str] = ""
    fires_on: ClassVar[str] = ""
    blocks: ClassVar[bool] = True

    def __init__(self) -> None:
        for attr in ("id", "fires_on"):
            if not getattr(self.__class__, attr, ""):
                raise TypeError(
                    f"{self.__class__.__name__} must set class attribute {attr!r}"
                )

    @abstractmethod
    def fire(self, ctx: JitPromptContext) -> str:
        """Return the prompt text to deliver to the agent."""

    @abstractmethod
    def is_acknowledged(self, ctx: JitPromptContext) -> bool:
        """Return True iff this JIT prompt has been acknowledged for ``ctx``."""

    def should_fire(self, ctx: JitPromptContext) -> bool:
        """Return True iff this JIT prompt's observed pattern is present."""
        return True


@dataclass
class JitPromptFireResult:
    """Outcome of :func:`fire_jit_prompt_event` for one lifecycle event."""

    blocked: bool = False
    escalated: bool = False
    prompts: list[str] = field(default_factory=list)
    fires: list[tuple[str, str]] = field(default_factory=list)


def fire_jit_prompt_event(
    *,
    project_dir: Path,
    event: str,
    session_id: str,
) -> JitPromptFireResult:
    """Orchestrate a lifecycle event through the JIT prompt registry."""
    from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry
    from tripwire.core.event_emitter import FileEmitter
    from tripwire.core.store import load_project

    registry = load_jit_prompt_registry(project_dir)
    if not registry:
        return JitPromptFireResult()

    jit_prompts = _workflow_declared_prompts(project_dir, registry.get(event, []))
    if not jit_prompts:
        return JitPromptFireResult()

    project = load_project(project_dir)
    opt_out = _opt_out_sessions(project)
    if session_id in opt_out:
        return JitPromptFireResult()

    project_id = project.name.lower().replace(" ", "-")
    ctx = JitPromptContext(
        project_dir=project_dir, session_id=session_id, project_id=project_id
    )

    emitter = FileEmitter(project_dir)
    result = JitPromptFireResult()

    for jit_prompt in jit_prompts:
        if jit_prompt.is_acknowledged(ctx):
            continue

        if not jit_prompt.should_fire(ctx):
            continue

        prior_fires = _count_prior_fires(project_dir, session_id, jit_prompt.id)
        prompt = jit_prompt.fire(ctx)

        escalated = prior_fires >= 2
        if escalated:
            display_prompt = (
                f"JIT prompt {jit_prompt.id!r} has fired {prior_fires + 1} "
                f"times on session {session_id!r} without acknowledgement. "
                f"Address the prompt and re-run the command with `--ack`. "
                f"The prompt was:\n\n{prompt}"
            )
            result.escalated = True
        else:
            display_prompt = prompt

        payload = _build_payload(
            jit_prompt_id=jit_prompt.id,
            session_id=session_id,
            event=event,
            blocks=jit_prompt.blocks,
            prompt=prompt,
            escalated=escalated,
        )
        event_path = emitter.emit("jit_prompt_firings", payload)
        result.fires.append((jit_prompt.id, event_path))
        result.prompts.append(display_prompt)
        _emit_workflow_event(
            project_dir=project_dir,
            jit_prompt=jit_prompt,
            session_id=session_id,
            event=event,
            escalated=escalated,
        )

        if jit_prompt.blocks:
            result.blocked = True

    return result


def _emit_workflow_event(
    *,
    project_dir: Path,
    jit_prompt: JitPrompt,
    session_id: str,
    event: str,
    escalated: bool,
) -> None:
    """Append ``jit_prompt.fired`` rows for workflow.yaml references."""
    from tripwire.core.workflow.registry import jit_prompt_status_refs

    refs = jit_prompt_status_refs(project_dir, jit_prompt.id)
    if not refs:
        return
    try:
        from tripwire.core.events.log import emit_event as _emit

        for workflow, status in refs:
            _emit(
                project_dir,
                workflow=workflow,
                instance=session_id,
                status=status,
                event="jit_prompt.fired",
                details={
                    "id": jit_prompt.id,
                    "fires_on": event,
                    "blocks": bool(jit_prompt.blocks),
                    "escalated": escalated,
                },
            )
    except Exception:
        # Best-effort workflow log; the `.tripwire/events/jit_prompt_firings`
        # write above remains the authoritative prompt-fire record.
        pass


def _workflow_declared_prompts(
    project_dir: Path, prompts: list[JitPrompt]
) -> list[JitPrompt]:
    """Filter event prompts to ids referenced by workflow.yaml.

    Projects without workflow.yaml retain the historical manifest
    behavior; projects with workflows only run configured prompt refs.
    """
    from tripwire.core.workflow.loader import load_workflows

    spec = load_workflows(project_dir)
    if not spec.workflows:
        return prompts
    declared: set[str] = set()
    for workflow in spec.workflows.values():
        for status in workflow.statuses:
            declared.update(status.jit_prompts)
    return [prompt for prompt in prompts if prompt.id in declared]


def _opt_out_sessions(project) -> set[str]:
    """Read ``project.yaml.jit_prompts.opt_out`` from the typed model."""
    from tripwire._internal.jit_prompts.loader import _read_jit_prompts_block

    cfg = _read_jit_prompts_block(project)
    opt_out = cfg.get("opt_out", []) if isinstance(cfg, dict) else []
    return {sid for sid in opt_out if isinstance(sid, str)}


def _count_prior_fires(project_dir: Path, session_id: str, jit_prompt_id: str) -> int:
    """Count prior fire events for ``(session_id, jit_prompt_id)`` on disk."""
    fire_dir = project_dir / ".tripwire" / "events" / "jit_prompt_firings" / session_id
    if not fire_dir.is_dir():
        return 0
    count = 0
    for entry in sorted(fire_dir.glob("*.json")):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("jit_prompt_id") == jit_prompt_id:
            count += 1
    return count


def _build_payload(
    *,
    jit_prompt_id: str,
    session_id: str,
    event: str,
    blocks: bool,
    prompt: str,
    escalated: bool,
) -> dict:
    """Build the JSON payload written to ``jit_prompt_firings``."""
    return {
        "kind": "jit_prompt_fire",
        "jit_prompt_id": jit_prompt_id,
        "session_id": session_id,
        "fired_at": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
        "blocks": blocks,
        "ack": None,
        "ack_at": None,
        "ack_marker_path": None,
        "fix_commits": [],
        "declared_no_findings": False,
        "escalated": escalated,
        "prompt_redacted": f"<<{jit_prompt_id} JIT prompt - content withheld>>",
        "prompt_revealed": prompt,
    }


__all__ = [
    "JitPrompt",
    "JitPromptContext",
    "JitPromptFireResult",
    "fire_jit_prompt_event",
]

"""JIT prompt primitive — base class, context, registry orchestrator.

A JIT prompt is a lifecycle prompt delivered at the moment it is most
useful for instruction-following. Some prompts are withheld until they
fire; others reinforce known workflow requirements with recency bias.
Blocking prompts require acknowledgement via ``--ack``.

Public surface (within this package):

- :class:`JitPrompt` — base class implementations subclass.
- :class:`JitPromptContext` — per-fire context object passed to
  ``fire()`` / ``is_acknowledged()``.
- :func:`fire_jit_prompt_event` — orchestrator the CLI calls when a
  lifecycle event happens. Loads the registry, runs each registered JIT
  prompt, emits ``jit_prompt_firings`` events, returns a
  :class:`JitPromptFireResult`.

The base class and orchestrator live here. Concrete JIT prompts (e.g.
``self_review``) live in sibling modules. The registry / loader logic
is in :mod:`tripwire._internal.jit_prompts.loader`.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class JitPromptContext:
    """Context object passed to ``JitPrompt.fire`` / ``is_acknowledged``.

    ``project_dir`` is the directory holding ``project.yaml``.
    ``project_id`` is the project's slug (used to seed variation choice).
    ``session_id`` is the session whose lifecycle event triggered the
    fire.
    """

    project_dir: Path
    session_id: str
    project_id: str

    def ack_path(self, jit_prompt_id: str) -> Path:
        """Marker file path for an ack from this context.

        Layout: ``<project_dir>/.tripwire/acks/<jit-prompt>-<sid>.json``.
        Caller is responsible for ``mkdir(parents=True, exist_ok=True)``
        before writing.
        """
        return (
            self.project_dir
            / ".tripwire"
            / "acks"
            / f"{jit_prompt_id}-{self.session_id}.json"
        )

    def variation_index(self, n_variations: int) -> int:
        """Deterministic variation pick from ``hash(project_id, session_id)``.

        Uses ``sha256`` rather than Python's built-in ``hash()`` so the
        choice is stable across processes (PYTHONHASHSEED randomises
        ``hash()`` per-interpreter).
        """
        if n_variations <= 0:
            raise ValueError("n_variations must be positive")
        seed = f"{self.project_id}:{self.session_id}".encode()
        digest = hashlib.sha256(seed).digest()
        return int.from_bytes(digest[:8], "big") % n_variations


class JitPrompt(ABC):
    """Base class for JIT prompts.

    Subclasses set ``id``, ``fires_on``, and ``blocks`` as class
    attributes and implement :meth:`fire` and :meth:`is_acknowledged`.
    The class attributes drive registry indexing and the loop-safety
    counter.
    """

    id: ClassVar[str] = ""
    fires_on: ClassVar[str] = ""
    blocks: ClassVar[bool] = True

    def __init__(self) -> None:
        # Concrete subclasses must set id and fires_on. ABC's
        # ``__abstractmethods__`` enforces that ``fire`` and
        # ``is_acknowledged`` are implemented; the class attribute
        # check has to live on instantiation because ``__init_subclass__``
        # runs before ABCMeta populates ``__abstractmethods__``.
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


@dataclass
class JitPromptFireResult:
    """Outcome of :func:`fire_jit_prompt_event` for a lifecycle event call.

    ``blocked`` is True when at least one ``blocks=True`` JIT prompt fired
    and was not acknowledged. The CLI uses this to decide between exit
    1 (block) and proceeding with the normal action.

    ``prompts`` are the per-JIT-prompt prompts to surface to the agent
    in fire order. ``escalated`` is True when the loop-safety counter
    tripped on at least one JIT prompt — the prompt mentions ``--ack``
    explicitly per spec §13.

    ``fires`` records (jit_prompt_id, event_path) pairs for audit and
    for the ``--ack`` writer to update later.
    """

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
    """Orchestrate a lifecycle event through the JIT prompt registry.

    Loads the registry, iterates JIT prompts registered to ``event``, and
    for each one:

    1. If already acknowledged → skip (return-no-block).
    2. Else, count prior fires for (jit_prompt_id, session_id) under
       ``.tripwire/events/jit_prompt_firings/<sid>/``. If this would be the third
       fire, emit a fire event AND set ``escalated=True`` with a prompt
       pointing the agent at ``--ack``.
    3. Else, call ``tw.fire(ctx)`` and emit a ``firings`` event with
       the redacted prompt + metadata.

    Returns a :class:`JitPromptFireResult`. The CLI is responsible for printing
    the prompts and exiting 1 when ``blocked=True``.
    """
    from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry
    from tripwire.core.event_emitter import FileEmitter
    from tripwire.core.store import load_project

    registry = load_jit_prompt_registry(project_dir)
    if not registry:
        return JitPromptFireResult()

    jit_prompts = registry.get(event, [])
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

        prior_fires = _count_prior_fires(project_dir, session_id, jit_prompt.id)
        prompt = jit_prompt.fire(ctx)

        if prior_fires >= 2:
            # Third (or later) fire on the same session escalates.
            escalation = (
                f"JIT prompt {jit_prompt.id!r} has fired {prior_fires + 1} times on session "
                f"{session_id!r} without acknowledgement. Address the prompt "
                f"and re-run the command with `--ack`. The prompt was:\n\n"
                f"{prompt}"
            )
            result.escalated = True
            payload = _build_payload(
                jit_prompt_id=jit_prompt.id,
                session_id=session_id,
                event=event,
                blocks=jit_prompt.blocks,
                prompt=prompt,
                escalated=True,
            )
            event_path = emitter.emit("jit_prompt_firings", payload)
            result.fires.append((jit_prompt.id, event_path))
            result.prompts.append(escalation)
        else:
            payload = _build_payload(
                jit_prompt_id=jit_prompt.id,
                session_id=session_id,
                event=event,
                blocks=jit_prompt.blocks,
                prompt=prompt,
                escalated=False,
            )
            event_path = emitter.emit("jit_prompt_firings", payload)
            result.fires.append((jit_prompt.id, event_path))
            result.prompts.append(prompt)

        if jit_prompt.blocks:
            result.blocked = True

    return result


def _opt_out_sessions(project) -> set[str]:
    """Read ``project.yaml.jit_prompts.opt_out`` from the typed model."""
    from tripwire._internal.jit_prompts.loader import _read_jit_prompts_block

    cfg = _read_jit_prompts_block(project)
    opt_out = cfg.get("opt_out", []) if isinstance(cfg, dict) else []
    return {sid for sid in opt_out if isinstance(sid, str)}


def _count_prior_fires(project_dir: Path, session_id: str, jit_prompt_id: str) -> int:
    """Count prior fire events for (session_id, jit_prompt_id) on disk."""
    fire_dir = project_dir / ".tripwire" / "events" / "jit_prompt_firings" / session_id
    if not fire_dir.is_dir():
        return 0
    count = 0
    import json

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
    """Build the JSON payload written to ``.tripwire/events/jit_prompt_firings/``.

    Schema per spec §1.2. ``prompt_revealed`` stays ``None`` on the
    fire-event itself; PM-mode reveals via the ``--reveal`` paths.
    The redacted placeholder records that *something* fired without
    leaking content.
    """
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
        "prompt_redacted": f"<<{jit_prompt_id} JIT prompt — content withheld>>",
        # `prompt_revealed` is populated only by PM-mode readers; agents
        # already received the prompt as the CLI return value, and the
        # event file is read by the UI which honours role-based
        # redaction. We persist it on disk so the PM `--reveal` flow
        # works without re-firing the JIT prompt.
        "prompt_revealed": prompt,
    }


__all__ = [
    "JitPrompt",
    "JitPromptContext",
    "JitPromptFireResult",
    "fire_jit_prompt_event",
]

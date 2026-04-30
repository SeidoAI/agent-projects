"""Tripwire primitive — base class, context, registry orchestrator.

A tripwire is a hidden prompt registered against a lifecycle event.
Invisible to the executing agent until the event fires; delivered as a
fresh CLI return value; blocks the lifecycle event until acknowledged
via ``--ack``.

Public surface (within this package):

- :class:`Tripwire` — base class implementations subclass.
- :class:`TripwireContext` — per-fire context object passed to
  ``fire()`` / ``is_acknowledged()``.
- :func:`fire_event` — orchestrator the CLI calls when a lifecycle
  event happens. Loads the registry, runs each registered tripwire,
  emits ``firings`` events, returns a :class:`FireResult`.

The base class and orchestrator live here. Concrete tripwires (e.g.
``self_review``) live in sibling modules. The registry / loader logic
is in :mod:`tripwire._internal.tripwires.loader`.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class TripwireContext:
    """Context object passed to ``Tripwire.fire`` / ``is_acknowledged``.

    ``project_dir`` is the directory holding ``project.yaml``.
    ``project_id`` is the project's slug (used to seed variation choice).
    ``session_id`` is the session whose lifecycle event triggered the
    fire.
    """

    project_dir: Path
    session_id: str
    project_id: str

    def ack_path(self, tripwire_id: str) -> Path:
        """Marker file path for an ack from this context.

        Layout: ``<project_dir>/.tripwire/acks/<tw>-<sid>.json``.
        Caller is responsible for ``mkdir(parents=True, exist_ok=True)``
        before writing.
        """
        return (
            self.project_dir
            / ".tripwire"
            / "acks"
            / f"{tripwire_id}-{self.session_id}.json"
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


class Tripwire(ABC):
    """Base class for tripwires.

    Subclasses set ``id``, ``fires_on``, and ``blocks`` as class
    attributes and implement :meth:`fire` and :meth:`is_acknowledged`.
    The class attributes drive registry indexing and the loop-safety
    counter.

    KUI-121: subclasses may also set ``at = (workflow_id, station_id)``
    to declare the workflow station the tripwire belongs to. The
    loader registers the mapping with
    :mod:`tripwire.core.workflow.registry` at instantiation time so
    the gate runner and drift detector can ask "what tripwires fire at
    station X?". Tripwires without ``at`` are treated as
    non-workflow-resident (legacy / not yet migrated).
    """

    id: ClassVar[str] = ""
    fires_on: ClassVar[str] = ""
    blocks: ClassVar[bool] = True
    # Optional — empty tuple means "not yet registered against a
    # station". Subclasses override to set the (workflow, station) pair.
    at: ClassVar[tuple[str, str] | tuple[()]] = ()

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
    def fire(self, ctx: TripwireContext) -> str:
        """Return the prompt text to deliver to the agent."""

    @abstractmethod
    def is_acknowledged(self, ctx: TripwireContext) -> bool:
        """Return True iff this tripwire has been acknowledged for ``ctx``."""

    def should_fire(self, ctx: TripwireContext) -> bool:
        """Return True iff this tripwire's observed pattern is present.

        Default ``True`` preserves the v0.8 always-fire behaviour
        (e.g. ``self-review``). Conditional tripwires (the v0.9
        deviation set) override this to stay silent when their
        pattern is absent — without this gate, every session.complete
        would surface five prompts regardless of relevance.
        """
        return True


@dataclass
class FireResult:
    """Outcome of :func:`fire_event` for a single lifecycle event call.

    ``blocked`` is True when at least one ``blocks=True`` tripwire fired
    and was not acknowledged. The CLI uses this to decide between exit
    1 (block) and proceeding with the normal action.

    ``prompts`` are the per-tripwire prompts to surface to the agent
    in fire order. ``escalated`` is True when the loop-safety counter
    tripped on at least one tripwire — the prompt mentions ``--ack``
    explicitly per spec §13.

    ``fires`` records (tripwire_id, event_path) pairs for audit and
    for the ``--ack`` writer to update later.
    """

    blocked: bool = False
    escalated: bool = False
    prompts: list[str] = field(default_factory=list)
    fires: list[tuple[str, str]] = field(default_factory=list)


def fire_event(
    *,
    project_dir: Path,
    event: str,
    session_id: str,
) -> FireResult:
    """Orchestrate a lifecycle event through the tripwire registry.

    Loads the registry, iterates tripwires registered to ``event``, and
    for each one:

    1. If already acknowledged → skip (return-no-block).
    2. Else, count prior fires for (tripwire_id, session_id) under
       ``.tripwire/events/firings/<sid>/``. If this would be the third
       fire, emit a fire event AND set ``escalated=True`` with a prompt
       pointing the agent at ``--ack``.
    3. Else, call ``tw.fire(ctx)`` and emit a ``firings`` event with
       the redacted prompt + metadata.

    Returns a :class:`FireResult`. The CLI is responsible for printing
    the prompts and exiting 1 when ``blocked=True``.
    """
    from tripwire._internal.tripwires.loader import load_registry
    from tripwire.core.event_emitter import FileEmitter
    from tripwire.core.store import load_project

    registry = load_registry(project_dir)
    if not registry:
        return FireResult()

    tripwires = registry.get(event, [])
    if not tripwires:
        return FireResult()

    project = load_project(project_dir)
    opt_out = _opt_out_sessions(project)
    if session_id in opt_out:
        return FireResult()

    project_id = project.name.lower().replace(" ", "-")
    ctx = TripwireContext(
        project_dir=project_dir, session_id=session_id, project_id=project_id
    )

    emitter = FileEmitter(project_dir)
    result = FireResult()

    for tw in tripwires:
        if tw.is_acknowledged(ctx):
            continue

        if not tw.should_fire(ctx):
            continue

        prior_fires = _count_prior_fires(project_dir, session_id, tw.id)
        prompt = tw.fire(ctx)

        escalated = prior_fires >= 2
        if escalated:
            # Third (or later) fire on the same session escalates.
            escalation = (
                f"Tripwire {tw.id!r} has fired {prior_fires + 1} times on session "
                f"{session_id!r} without acknowledgement. Address the prompt "
                f"and re-run the command with `--ack`. The prompt was:\n\n"
                f"{prompt}"
            )
            result.escalated = True
            display_prompt = escalation
        else:
            display_prompt = prompt
        payload = _build_payload(
            tripwire_id=tw.id,
            session_id=session_id,
            event=event,
            blocks=tw.blocks,
            prompt=prompt,
            escalated=escalated,
        )
        event_path = emitter.emit("firings", payload)
        result.fires.append((tw.id, event_path))
        result.prompts.append(display_prompt)
        # KUI-123: also append to the workflow events log when the
        # tripwire declares a station via `at = (...)`.
        _emit_workflow_event(
            project_dir=project_dir,
            tripwire=tw,
            session_id=session_id,
            event=event,
            escalated=escalated,
        )

        if tw.blocks:
            result.blocked = True

    return result


def _emit_workflow_event(
    *,
    project_dir: Path,
    tripwire: Tripwire,
    session_id: str,
    event: str,
    escalated: bool,
) -> None:
    """Append one ``tripwire.fired`` row to the workflow events log
    (KUI-123) when the tripwire declares an ``at = (workflow, station)``.

    Tripwires without ``at`` are silently skipped. Best-effort: emission
    failures don't sink the fire — the legacy `.tripwire/events/firings`
    channel above stays authoritative for the UI."""
    pair = getattr(tripwire.__class__, "at", ())
    if not isinstance(pair, tuple) or len(pair) != 2:
        return
    workflow, station = pair
    if not isinstance(workflow, str) or not isinstance(station, str):
        return
    try:
        from tripwire.core.events.log import emit_event as _emit

        _emit(
            project_dir,
            workflow=workflow,
            instance=session_id,
            station=station,
            event="tripwire.fired",
            details={
                "id": tripwire.id,
                "fires_on": event,
                "blocks": bool(tripwire.blocks),
                "escalated": escalated,
            },
        )
    except Exception:
        # Best-effort log; the legacy `.tripwire/events/firings` write
        # above is the authoritative record for the UI.
        pass


def _opt_out_sessions(project) -> set[str]:
    """Read ``project.yaml.tripwires.opt_out`` from the typed model."""
    from tripwire._internal.tripwires.loader import _read_tripwires_block

    cfg = _read_tripwires_block(project)
    opt_out = cfg.get("opt_out", []) if isinstance(cfg, dict) else []
    return {sid for sid in opt_out if isinstance(sid, str)}


def _count_prior_fires(project_dir: Path, session_id: str, tripwire_id: str) -> int:
    """Count prior fire events for (session_id, tripwire_id) on disk."""
    fire_dir = project_dir / ".tripwire" / "events" / "firings" / session_id
    if not fire_dir.is_dir():
        return 0
    count = 0
    import json

    for entry in sorted(fire_dir.glob("*.json")):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("tripwire_id") == tripwire_id:
            count += 1
    return count


def _build_payload(
    *,
    tripwire_id: str,
    session_id: str,
    event: str,
    blocks: bool,
    prompt: str,
    escalated: bool,
) -> dict:
    """Build the JSON payload written to ``.tripwire/events/firings/``.

    Schema per spec §1.2. ``prompt_revealed`` stays ``None`` on the
    fire-event itself; PM-mode reveals via the ``--reveal`` paths.
    The redacted placeholder records that *something* fired without
    leaking content.
    """
    return {
        "kind": "tripwire_fire",
        "tripwire_id": tripwire_id,
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
        "prompt_redacted": f"<<{tripwire_id} prompt — content withheld>>",
        # `prompt_revealed` is populated only by PM-mode readers; agents
        # already received the prompt as the CLI return value, and the
        # event file is read by the UI which honours role-based
        # redaction. We persist it on disk so the PM `--reveal` flow
        # works without re-firing the tripwire.
        "prompt_revealed": prompt,
    }


__all__ = ["FireResult", "Tripwire", "TripwireContext", "fire_event"]

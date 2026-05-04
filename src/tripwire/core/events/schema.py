"""Schema for the workflow events log (KUI-123).

One row per emitted event:

.. code-block:: json

    {
      "ts": "2026-04-30T15:00:00Z",
      "workflow": "coding-session",
      "instance": "v09-workflow-substrate",
      "status": "executing",
      "event": "validator.run",
      "details": { "id": "v_uuid_present", "outcome": "pass" }
    }

``ts`` is RFC-3339 UTC with a ``Z`` suffix (matches the rest of the
codebase's event-emission convention). ``instance`` is the session id
that contextualises the event — sessions are the canonical instance
of the ``coding-session`` workflow today; future workflows may use
other instance kinds (issue ids, PR numbers). ``details`` is a
free-form dict for event-kind-specific payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    """One row in the events log.

    Constructed by :func:`tripwire.core.events.log.emit_event`; consumers
    read these back via :func:`tripwire.core.events.log.read_events`.
    """

    ts: str
    workflow: str
    instance: str
    status: str
    event: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "workflow": self.workflow,
            "instance": self.instance,
            "status": self.status,
            "event": self.event,
            "details": dict(self.details),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> Event:
        return cls(
            ts=str(payload.get("ts", "")),
            workflow=str(payload.get("workflow", "")),
            instance=str(payload.get("instance", "")),
            status=str(payload.get("status", "")),
            event=str(payload.get("event", "")),
            details=dict(payload.get("details") or {}),
        )


# Conventional event-kind taxonomy. Subsystems are free to emit any
# kind they like — these are the well-known ones consumed by the drift
# detector (KUI-124).
EVENT_VALIDATOR_RUN = "validator.run"
EVENT_JIT_PROMPT_FIRED = "jit_prompt.fired"
EVENT_PROMPT_CHECK_INVOKED = "prompt_check.invoked"
EVENT_TRANSITION_REQUESTED = "transition.requested"
EVENT_TRANSITION_COMPLETED = "transition.completed"
EVENT_TRANSITION_REJECTED = "transition.rejected"


__all__ = [
    "EVENT_JIT_PROMPT_FIRED",
    "EVENT_PROMPT_CHECK_INVOKED",
    "EVENT_TRANSITION_COMPLETED",
    "EVENT_TRANSITION_REJECTED",
    "EVENT_TRANSITION_REQUESTED",
    "EVENT_VALIDATOR_RUN",
    "Event",
]

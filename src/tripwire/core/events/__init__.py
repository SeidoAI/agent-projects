"""Per-project workflow events log substrate (KUI-123).

The append-only events log lives at ``<project>/events/<UTC-date>.jsonl``
— one JSON record per line, schema
``{ts, workflow, instance, station, event, details}``.

Validators (KUI-120), tripwires (KUI-121), and transitions (KUI-159)
all emit through this surface via :func:`tripwire.core.events.log.emit_event`.
The drift detector (KUI-124) consumes via
:func:`tripwire.core.events.log.read_events`.

This is distinct from the legacy ``.tripwire/events/<kind>/<sid>/<n>.json``
fan-out written by :class:`tripwire.core.event_emitter.FileEmitter` —
the legacy channel is the per-session UI event surface; this is the
workflow-level audit log. Both coexist; v0.9 doesn't migrate the
legacy channel.
"""

from __future__ import annotations

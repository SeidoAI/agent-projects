"""Inline post-write hooks invoked by the workflow executor.

The executor is an atomic primitive — no side-effect registry, no
dispatch. ``execute_transition`` calls four best-effort hooks inline
after the status write: close engagement, audit, telemetry, reset
acks. External effects (sweep, rebase, kill, draft flips, PR close,
worktree remove, follow-up stub) live as standalone scripts under
``templates/side_effects/<entity>/<name>.py`` and are invoked by the
executor via subprocess. ``known_ids()`` enumerates side-effect ids
the schema may declare so the ``workflow/unknown_side_effect`` lint
can flag typos.

This package mirrors ``templates/side_effects/`` — one file per hook,
grouped by the entity the transition operates on. For now the only
entity sub-registry is ``session`` (the ``coding-session`` workflow);
v2 schema will add ``issue/``, ``pr/``, and ``code_review/`` as those
workflows get their own side_effects.

Aggregation pattern: this top-level ``__init__`` re-exports the public
hook callables (so existing import paths like
``from tripwire.core.workflow.post_write_hooks import close_active_engagement``
keep working unchanged) and aggregates ``known_ids()`` across every
entity sub-registry listed in :data:`_ENTITY_SUBREGISTRIES`. Adding a
new entity = adding one line to that tuple plus a new
``<entity>/__init__.py``. We deliberately avoid ``pkgutil.iter_modules``
here — explicit + grep-friendly beats magic at module-import time.
"""

from __future__ import annotations

from collections.abc import Callable

# Re-export the public hook callables from the session sub-registry so
# callers don't have to know about the entity layout. If/when other
# entity sub-registries grow callables that need to be re-exported,
# add them here.
from tripwire.core.workflow.post_write_hooks.session import (
    append_audit_record,
    append_telemetry_record,
    close_active_engagement,
    reset_acks_if_requested,
)
from tripwire.core.workflow.post_write_hooks.session import (
    known_ids as _session_known_ids,
)

# Entity sub-registries the parent aggregates. Each entry is a
# zero-arg callable returning ``set[str]`` of side-effect ids the
# entity's workflows may declare. Extend this tuple as new entity
# sub-registries land (``issue``, ``pr``, ``code_review``, …).
_ENTITY_SUBREGISTRIES: tuple[Callable[[], set[str]], ...] = (_session_known_ids,)


def known_ids() -> set[str]:
    """Return the union of side-effect ids across every entity sub-registry.

    Static; the executor does not dispatch by id anymore — used by the
    load-time ``workflow/unknown_side_effect`` lint to flag typos.
    """
    aggregated: set[str] = set()
    for ids in _ENTITY_SUBREGISTRIES:
        aggregated.update(ids())
    return aggregated


__all__ = [
    "append_audit_record",
    "append_telemetry_record",
    "close_active_engagement",
    "known_ids",
    "reset_acks_if_requested",
]

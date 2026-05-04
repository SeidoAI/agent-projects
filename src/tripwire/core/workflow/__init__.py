"""The workflow primitive — `workflow.yaml` schema, loader, registry.

A workflow is a typed lifecycle graph: statuses with declared
validators, JIT prompts, and prompt-checks; transitions between statuses
gated by the runtime; and an append-only events log substrate.

This module is the substrate for v0.9 — every other v0.9 session
(consumers UI, entity graph, validator/JIT prompt authoring, etc.) reads
the typed workflow tree exposed here.

Public surface:

- :func:`tripwire.core.workflow.loader.load_workflows` — read the
  per-project ``workflow.yaml`` and return a typed
  :class:`WorkflowSpec`.
- :class:`tripwire.core.workflow.schema.WorkflowSpec` (and friends) —
  the typed dataclass tree.
- :func:`tripwire.core.workflow.schema.validate_workflow_spec` —
  well-formedness validator surfaced through ``tripwire validate``.
- :mod:`tripwire.core.workflow.registry` — implementation catalogs for
  validator, JIT prompt, and prompt-check ids referenced by
  ``workflow.yaml``.

The architecture overlay
(``backlog-architecture.md``) locks every shape in this module:
per-project location, equality-only conditional syntax, multiple
workflows per file, terminal statuses.
"""

from __future__ import annotations

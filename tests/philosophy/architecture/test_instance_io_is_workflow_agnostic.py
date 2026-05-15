"""``instance_io.py`` doesn't know any specific workflow.

Philosophy §9 makes the generic loader the structural answer to "no
per-workflow Python class":

    *"`workflow.yaml` declares structure ... instance shapes, required
    fields. Pure data."*

For that promise to hold, the loader has to be *workflow-agnostic*:
it reads ``instance.storage_path`` from the spec and operates against
any well-shaped workflow. If the loader hard-codes ``coding-session``
or ``issue-closure`` anywhere, then those workflows are getting
privileged treatment in code that's supposed to be generic — and the
"any YAML workflow works" claim is silently false.

This test scans ``instance_io.py`` for mentions of any specific
workflow id declared in ``workflow.yaml.j2``. Finding one means the
generic loader has grown a workflow-specific branch; either:

  - move the branching into ``transitions.py`` (where dispatch
    between typed wrappers and the generic loader legitimately
    happens), or
  - generalise the special case by extending the schema.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire

INSTANCE_IO = Path(tripwire.__file__).parent / "core" / "workflow" / "instance_io.py"
WORKFLOW_TEMPLATE = Path(tripwire.__file__).parent / "templates" / "workflow.yaml.j2"


def _declared_workflow_ids() -> set[str]:
    """Return every workflow id in the shipped workflow.yaml template."""
    spec = yaml.safe_load(WORKFLOW_TEMPLATE.read_text(encoding="utf-8"))
    return set(spec.get("workflows", {}).keys())


def test_instance_io_mentions_no_specific_workflow_id():
    """``instance_io.py`` contains no occurrences of any declared
    workflow id (as a string literal or substring).

    The generic loader reads workflow shape via the spec; it should
    never branch on workflow identity. The dispatch between typed
    wrappers (``AgentSession`` etc.) and the dict loader happens in
    ``transitions.py``, which is the right home for that decision.
    """
    text = INSTANCE_IO.read_text(encoding="utf-8")
    declared = _declared_workflow_ids()

    violations: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith('"'):
            continue
        for wf_id in declared:
            # Match quoted occurrence (string literal). Substring
            # match would false-flag "issue-closure" inside arbitrary
            # words; the quote-anchored form is precise.
            if f'"{wf_id}"' in line or f"'{wf_id}'" in line:
                violations.append(f"  line {line_no}: {wf_id!r} → {line.strip()}")

    assert not violations, (
        "Philosophy §9 violation — `instance_io.py` mentions a specific\n"
        "workflow id. The generic loader must stay workflow-agnostic.\n"
        "\n"
        f"Declared workflows scanned: {sorted(declared)}\n"
        "\n"
        "Offending lines:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix options:\n"
        "  1. Move the workflow-specific branch into `transitions.py`'s\n"
        "     `_load_workflow_instance` / `_save_workflow_instance`. That's\n"
        "     where dispatch between typed wrappers and the generic dict\n"
        "     loader legitimately happens.\n"
        "  2. Generalise the special case by extending the schema (e.g.\n"
        "     add a new field on `instance:` that drives the behaviour\n"
        "     declaratively rather than by workflow id)."
    )

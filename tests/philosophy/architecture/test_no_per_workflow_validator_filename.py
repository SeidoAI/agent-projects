"""No validator file is named after a specific workflow.

Philosophy §9 promises three orthogonal extension points:

    *"New skills (slash commands) wrap CLI; new workflows declare
    YAML; new invariants are validators. Three orthogonal extension
    points."*

For validators to be orthogonal to workflows, they have to be
*reusable across workflows*. A file named ``coding_session.py`` or
``issue_closure.py`` in ``core/validator/checks/`` signals the
opposite: a validator built for one workflow, owned by that workflow,
and (almost certainly) too narrow to reuse elsewhere.

The naming convention §9 implies: validators should be named by
*concern* — ``identity.py``, ``references.py``, ``structure.py``,
``session_lifecycle.py`` (a lifecycle pattern, not a specific
workflow) — not by *workflow id*.

This fitness function pins that. The set of validator filenames is
disjoint from the (normalised) set of declared workflow ids. Adding
a workflow doesn't add a validator file; adding a validator file
doesn't presume a workflow.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire

VALIDATOR_ROOT = Path(tripwire.__file__).parent / "core" / "validator"
CHECKS_DIR = VALIDATOR_ROOT / "checks"
LINT_DIR = VALIDATOR_ROOT / "lint"
WORKFLOW_TEMPLATE = Path(tripwire.__file__).parent / "templates" / "workflow.yaml.j2"


def _declared_workflow_filename_forms() -> set[str]:
    """Return the workflow ids in filename form (``some-workflow`` →
    ``some_workflow.py``).
    """
    spec = yaml.safe_load(WORKFLOW_TEMPLATE.read_text(encoding="utf-8"))
    out: set[str] = set()
    for wf_id in spec.get("workflows", {}):
        out.add(wf_id.replace("-", "_") + ".py")
    return out


def _validator_filenames() -> set[str]:
    out: set[str] = set()
    for directory in (CHECKS_DIR, LINT_DIR):
        for path in directory.rglob("*.py"):
            if path.name.startswith("_"):
                continue
            out.add(path.name)
    return out


def test_no_validator_file_named_after_a_specific_workflow():
    """The set of validator filenames is disjoint from the
    (filename-form) set of declared workflow ids.

    A failure means someone created e.g. ``core/validator/checks/
    pr_lifecycle.py`` — implicitly saying "these checks belong to
    the pr-lifecycle workflow." Even if the checks are useful, the
    NAME couples the validator to a single workflow and breaks the
    §9 orthogonality claim. Rename by concern (e.g.
    ``pr_artifacts.py``, ``pr_merge_state.py``) so the validator's
    reusability is visible in its identity.
    """
    workflow_filenames = _declared_workflow_filename_forms()
    validator_filenames = _validator_filenames()

    overlap = workflow_filenames & validator_filenames
    assert not overlap, (
        "Philosophy §9 violation — validator file named after a specific\n"
        "workflow id. Validators must be orthogonal extension points; a\n"
        "name like that implicitly couples the validator to one workflow.\n"
        "\n"
        f"Overlap: {sorted(overlap)}\n"
        f"Declared workflows (filename form): {sorted(workflow_filenames)}\n"
        "\n"
        "Fix: rename the validator file by its CONCERN (what kind of\n"
        "thing it checks), not by workflow id. Examples in the existing\n"
        "tree: `identity.py`, `references.py`, `structure.py`,\n"
        "`session_lifecycle.py` (a lifecycle pattern is a concern;\n"
        "a workflow id is not)."
    )

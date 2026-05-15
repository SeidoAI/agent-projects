"""Each workflow's ``instance`` block is internally consistent.

Tripwire has a deliberate two-layer workflow model documented in
``docs/workflows/reference-only-workflows.md``:

  - **Executor-driven workflows** (``coding-session``, ``issue-closure``,
    ``phase-advancement``): ``execute_transition`` materialises and
    advances instances. ``status_enum`` and the ``statuses:`` block
    declare the same state machine from two angles, and they MUST
    agree.

  - **Reference-only workflows** (``pm-scoping``, ``pm-triage``, etc.):
    declared so ``tripwire validate`` can lint cross-links and shape,
    but no executor is wired up. ``status_enum`` is the external
    lifecycle the PM agent writes to instance files; ``statuses:`` is
    the process map for documentation and drift detection. They
    deliberately use different vocabularies. The flag
    ``instance.reference_only: true`` marks these.

  - **Singleton workflows** (``phase-advancement``): exactly one
    instance per project; ``storage_path`` is a literal path with no
    ``{instance_id}`` substitution. Marked with
    ``instance.singleton: true``.

The fitness function below codifies the consistency invariants that
apply to each shape, and **only** to that shape. The investigation
that surfaced this model is in the round-4 commit message; the
schema flags ``singleton`` / ``reference_only`` formalise it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire

WORKFLOW_TEMPLATE = Path(tripwire.__file__).parent / "templates" / "workflow.yaml.j2"


def _load_workflows() -> dict[str, dict]:
    spec = yaml.safe_load(WORKFLOW_TEMPLATE.read_text(encoding="utf-8"))
    return spec.get("workflows", {})


def _instance_block(workflow: dict) -> dict | None:
    inst = workflow.get("instance")
    return inst if isinstance(inst, dict) else None


def test_status_field_in_required_fields():
    """The instance's ``status_field`` is also listed in
    ``required_fields``. Applies to every workflow with an instance
    block; without it, an instance file could omit the status field
    and the executor / shape validator would crash.
    """
    violations: list[str] = []
    for wf_id, body in _load_workflows().items():
        inst = _instance_block(body)
        if inst is None:
            continue
        status_field = inst.get("status_field")
        required = inst.get("required_fields") or []
        if status_field and status_field not in required:
            violations.append(
                f"  {wf_id}: status_field={status_field!r} not in "
                f"required_fields={required!r}"
            )
    assert not violations, (
        "Schema sanity violation — status_field is not in required_fields.\n"
        "\n"
        "Offending workflows:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: add the status_field name to required_fields."
    )


def test_instance_id_field_in_required_fields_for_non_singleton_workflows():
    """For non-singleton workflows, ``instance_id_field`` is listed in
    ``required_fields``. Singleton workflows are exempt because
    ``instance_id_field`` doesn't appear in their literal storage_path
    — the field exists only as a label for the singleton instance.
    """
    violations: list[str] = []
    for wf_id, body in _load_workflows().items():
        inst = _instance_block(body)
        if inst is None:
            continue
        if inst.get("singleton", False):
            continue
        id_field = inst.get("instance_id_field", "id")
        required = inst.get("required_fields") or []
        if id_field not in required:
            violations.append(
                f"  {wf_id}: instance_id_field={id_field!r} not in "
                f"required_fields={required!r}"
            )
    assert not violations, (
        "Schema sanity violation — non-singleton workflow's\n"
        "instance_id_field is not in required_fields.\n"
        "\n"
        "Offending workflows:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: either add the field to required_fields, or — if the\n"
        "workflow really has one instance per project — set\n"
        "`instance.singleton: true`."
    )


def test_status_enum_matches_declared_statuses_for_executor_driven_workflows():
    """Executor-driven workflows (NOT marked ``reference_only``) MUST
    have ``instance.status_enum`` equal to the set of ``statuses[].id``.

    Both lists describe the SAME state machine — one for the route
    graph the executor walks, one for the instance-shape contract
    consumers depend on. A mismatch means an instance can carry a
    status the executor doesn't know how to transition (or vice
    versa).

    Reference-only workflows (``reference_only: true``) are exempt:
    they intentionally use ``status_enum`` for the external lifecycle
    and ``statuses:`` for the process map, with different vocabularies.
    See ``docs/workflows/reference-only-workflows.md``.
    """
    violations: list[str] = []
    for wf_id, body in _load_workflows().items():
        inst = _instance_block(body)
        if inst is None:
            continue
        if inst.get("reference_only", False):
            continue
        status_enum = set(inst.get("status_enum") or [])
        declared_statuses = {
            s["id"]
            for s in body.get("statuses") or []
            if isinstance(s, dict) and "id" in s
        }
        if status_enum != declared_statuses:
            only_in_enum = status_enum - declared_statuses
            only_in_statuses = declared_statuses - status_enum
            detail = []
            if only_in_enum:
                detail.append(
                    f"in status_enum but not statuses: {sorted(only_in_enum)}"
                )
            if only_in_statuses:
                detail.append(
                    f"in statuses but not status_enum: {sorted(only_in_statuses)}"
                )
            violations.append(f"  {wf_id}: {'; '.join(detail)}")

    assert not violations, (
        "Schema sanity violation — executor-driven workflow's\n"
        "status_enum drifts from its statuses block. Both must declare\n"
        "the same state machine; the executor uses the latter and the\n"
        "instance-shape validator uses the former.\n"
        "\n"
        "Offending workflows:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: align the two lists. If the workflow is actually\n"
        "agent-driven (no executor wiring), mark it\n"
        "`instance.reference_only: true` instead."
    )


def test_storage_path_has_instance_id_placeholder_for_non_singleton_workflows():
    """Non-singleton workflows MUST include ``{instance_id}`` in
    ``storage_path`` so each instance gets its own file. Singletons
    (``singleton: true``) are exempt; their storage_path is a literal.
    """
    violations: list[str] = []
    for wf_id, body in _load_workflows().items():
        inst = _instance_block(body)
        if inst is None:
            continue
        if inst.get("singleton", False):
            continue
        storage_path = inst.get("storage_path") or ""
        if "{instance_id}" not in storage_path:
            violations.append(f"  {wf_id}: storage_path={storage_path!r}")

    assert not violations, (
        "Schema sanity violation — non-singleton storage_path lacks\n"
        "`{instance_id}`. Without it every instance writes to the same\n"
        "file — catastrophic data loss in a single transition.\n"
        "\n"
        "Offending workflows:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: add `{instance_id}` to the storage_path template, OR — if\n"
        "the workflow really has one instance per project — set\n"
        "`instance.singleton: true`."
    )


def test_singleton_storage_path_is_literal():
    """Inverse of the above: ``singleton: true`` MUST mean
    ``storage_path`` has NO ``{instance_id}``. A singleton with the
    placeholder is a contradiction — the storage_path can't be both
    a single literal AND parameterised."""
    violations: list[str] = []
    for wf_id, body in _load_workflows().items():
        inst = _instance_block(body)
        if inst is None:
            continue
        if not inst.get("singleton", False):
            continue
        storage_path = inst.get("storage_path") or ""
        if "{instance_id}" in storage_path:
            violations.append(f"  {wf_id}: storage_path={storage_path!r}")

    assert not violations, (
        "Schema sanity violation — singleton workflow has `{instance_id}`\n"
        "in storage_path. A singleton has exactly one instance per\n"
        "project — the path is a literal.\n"
        "\n"
        "Offending workflows:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: remove `{instance_id}` from storage_path, OR remove the\n"
        "`singleton: true` flag if the workflow really has many instances."
    )

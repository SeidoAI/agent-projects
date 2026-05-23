"""Materialised workflow instances must conform to ``workflow.yaml`` ``instance:``."""

from __future__ import annotations

import yaml

from tripwire.core.parser import ParseError
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_instance_shape_conforms(ctx: ValidationContext) -> list[CheckResult]:
    """Every materialised instance must match its workflow's declared shape.

    For each workflow that declares an ``instance:`` block in
    ``workflow.yaml``, walk the disk via :func:`list_instances` and
    confirm that each instance file:

    - carries every entry in ``required_fields``
      (missing → ``instance/missing_required_field``);
    - carries a value at ``status_field`` that's in ``status_enum``
      (out-of-enum → ``instance/invalid_status_value``).

    Workflows without an ``instance:`` block are skipped silently;
    that gap is already reported by ``workflow/instance_missing``
    inside :func:`check_workflow_well_formed`. A workflow.yaml that
    fails to parse is also skipped silently — the parse error
    surfaces through ``v_workflow_well_formed``.
    """
    # Local imports keep the validator/workflow circular surface minimal.
    from tripwire.core.workflow.instance_io import (
        InstanceNotFoundError,
        list_instances,
        load_instance,
    )
    from tripwire.core.workflow.loader import load_workflows

    results: list[CheckResult] = []
    try:
        spec = load_workflows(ctx.project_dir)
    except yaml.YAMLError:
        # workflow.yaml parse errors are reported by
        # ``check_workflow_well_formed`` — no point double-reporting.
        return results

    for workflow_id, workflow in spec.workflows.items():
        shape = workflow.instance
        if shape is None:
            # Missing-block warning is owned by the workflow validator;
            # silently skip here to avoid double-reporting.
            continue
        try:
            instance_ids = list_instances(ctx.project_dir, workflow_id)
        except (LookupError, ValueError):
            # Resolution problems already surface via workflow lints.
            continue

        status_enum = set(shape.status_enum)
        for instance_id in instance_ids:
            try:
                data = load_instance(ctx.project_dir, workflow_id, instance_id)
            except InstanceNotFoundError:
                # Disappeared between list and load; nothing to assert.
                continue
            except (ValueError, ParseError):
                # Parse errors are reported by the entity loader
                # (e.g. ``session/parse_error``); skip silently here.
                continue

            rendered = ctx.project_dir / shape.storage_path.replace(
                "{instance_id}", instance_id
            )
            try:
                rel_path = str(rendered.relative_to(ctx.project_dir))
            except ValueError:
                rel_path = str(rendered)

            for required in shape.required_fields:
                if required not in data or data.get(required) in (None, ""):
                    results.append(
                        CheckResult(
                            code="instance/missing_required_field",
                            severity="error",
                            file=rel_path,
                            field=required,
                            message=(
                                f"workflow {workflow_id!r} instance "
                                f"{instance_id!r} is missing required field "
                                f"{required!r} declared on "
                                f"workflow.yaml `instance.required_fields`."
                            ),
                            fix_hint=(f"Add `{required}: <value>` to {rel_path}."),
                        )
                    )

            if status_enum:
                value = data.get(shape.status_field)
                if value is None or value not in status_enum:
                    results.append(
                        CheckResult(
                            code="instance/invalid_status_value",
                            severity="error",
                            file=rel_path,
                            field=shape.status_field,
                            message=(
                                f"workflow {workflow_id!r} instance "
                                f"{instance_id!r} has "
                                f"`{shape.status_field}: {value!r}` which "
                                f"is not in the declared status_enum "
                                f"{sorted(status_enum)}."
                            ),
                            fix_hint=(
                                f"Set `{shape.status_field}` to one of "
                                f"{sorted(status_enum)} in {rel_path}, or "
                                f"add the value to "
                                f"workflow.yaml `instance.status_enum`."
                            ),
                        )
                    )

    return results

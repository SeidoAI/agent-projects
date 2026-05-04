"""Workflow well-formedness check (KUI-119).

Runs the typed loader against ``<project>/workflow.yaml`` and routes
each :class:`WorkflowFinding` into the validator's standard
:class:`CheckResult` channel. Surfaces under ``tripwire validate``.

Reference checks resolve against implementation catalogs. The catalogs
only prove an id exists; ``workflow.yaml`` is the sole source of where
that id runs.
"""

from __future__ import annotations

import yaml

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.workflow.loader import WORKFLOW_FILENAME, load_workflows
from tripwire.core.workflow.schema import validate_workflow_spec


def check_workflow_well_formed(ctx: ValidationContext) -> list[CheckResult]:
    """Validate ``<project>/workflow.yaml`` shape and references.

    Returns an empty list when the file is absent — the workflow
    primitive is opt-in for projects that haven't run the init that
    plants it. Yaml parse failures surface as ``workflow/parse_error``.
    """
    out: list[CheckResult] = []
    try:
        spec = load_workflows(ctx.project_dir)
    except yaml.YAMLError as exc:
        out.append(
            CheckResult(
                code="workflow/parse_error",
                severity="error",
                file=WORKFLOW_FILENAME,
                message=f"workflow.yaml failed to parse: {exc}",
                fix_hint=(
                    "Check the YAML syntax against the schema in "
                    "docs/specs/2026-04-30-v09-workflow-substrate.md."
                ),
            )
        )
        return out

    findings = validate_workflow_spec(
        spec,
        known_tripwires=_known_tripwires(),
        known_heuristics=_known_heuristics(),
        known_jit_prompts=_known_jit_prompts(ctx.project_dir),
        known_prompt_checks=_known_prompt_checks(ctx.project_dir),
        known_commands=_known_commands(ctx.project_dir),
        known_skills=_known_skills(ctx.project_dir),
    )
    for finding in findings:
        out.append(
            CheckResult(
                code=finding.code,
                severity=finding.severity,
                file=WORKFLOW_FILENAME,
                message=finding.message,
                field=(
                    f"{finding.workflow}.{finding.status}"
                    if finding.status is not None
                    else finding.workflow
                ),
            )
        )
    return out


def _known_tripwires() -> set[str]:
    """Return implemented tripwire ids (hard-gate primitives)."""
    from tripwire.core.workflow.registry import known_validator_ids

    return known_validator_ids()


def _known_heuristics() -> set[str]:
    """Return implemented heuristic ids (soft warn-once primitives).

    Stage 1 ships an empty registry; the heuristics module lands in a
    follow-up commit. Returning an empty set means the spec validator
    skips the unknown-id check (matching the existing pattern for the
    other primitive sets).
    """
    return set()


def _known_jit_prompts(project_dir) -> set[str]:  # type: ignore[no-untyped-def]
    """Return implemented JIT prompt ids."""
    from tripwire.core.workflow.registry import known_jit_prompt_ids

    return known_jit_prompt_ids(project_dir)


def _known_prompt_checks(project_dir):  # type: ignore[no-untyped-def]
    """Return implemented prompt-check command ids."""
    from tripwire.core.workflow.registry import known_prompt_check_ids

    return known_prompt_check_ids(project_dir)


def _known_commands(project_dir):  # type: ignore[no-untyped-def]
    """Return implemented slash command ids."""
    from tripwire.core.workflow.registry import known_command_ids

    return known_command_ids(project_dir)


def _known_skills(project_dir):  # type: ignore[no-untyped-def]
    """Return implemented skill ids."""
    from tripwire.core.workflow.registry import known_skill_ids

    return known_skill_ids(project_dir)

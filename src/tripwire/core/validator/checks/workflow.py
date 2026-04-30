"""Workflow well-formedness check (KUI-119).

Runs the typed loader against ``<project>/workflow.yaml`` and routes
each :class:`WorkflowFinding` into the validator's standard
:class:`CheckResult` channel. Surfaces under ``tripwire validate``.

This first cut runs with empty ``known_validators`` /
``known_tripwires`` / ``known_prompt_checks`` sets — meaning the
ref-existence checks short-circuit. Subsequent v0.9 sessions tighten
the contract by populating those sets from the station registries
(KUI-120 validators, KUI-121 tripwires, KUI-122 prompt-checks). The
schema-shape checks (unknown_next_station, terminal_with_next, …)
fire today.
"""

from __future__ import annotations

import yaml

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.workflow.loader import WORKFLOW_FILENAME, load_workflows
from tripwire.core.workflow.registry import registers_at
from tripwire.core.workflow.schema import validate_workflow_spec


@registers_at("coding-session", "executing")
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
        known_validators=_known_validators(),
        known_tripwires=_known_tripwires(),
        known_prompt_checks=_known_prompt_checks(ctx.project_dir),
    )
    for finding in findings:
        out.append(
            CheckResult(
                code=finding.code,
                severity=finding.severity,
                file=WORKFLOW_FILENAME,
                message=finding.message,
                field=(
                    f"{finding.workflow}.{finding.station}"
                    if finding.station is not None
                    else finding.workflow
                ),
            )
        )
    return out


def _known_validators() -> set[str]:
    """Return the registry-declared validator ids.

    Populated by KUI-120 once each check declares its station via
    ``@registers_at``. Returns an empty set today, which the schema
    treats as "skip the ref-existence check".
    """
    from tripwire.core.workflow.registry import known_validator_ids

    return known_validator_ids()


def _known_tripwires() -> set[str]:
    """Return the registry-declared tripwire ids.

    Populated by KUI-121 once each Tripwire subclass declares its
    station via ``at = (...)``.

    KNOWN GAP (codex P2 on PR #73): the registry is populated as a
    side-effect of `_instantiate()` in tripwires/loader.py, which only
    runs when `load_registry(project_dir)` is called. `tripwire
    validate` does not call it, so this set is usually empty during
    workflow.yaml ref-checks — which silently disables the
    `workflow/unknown_tripwire` finding. Force-loading from this
    callsite would mutate global registry state in a way that leaks
    into the gate runtime in transitions.py (the same registry is
    used to enforce tripwires-at-stations during `tripwire
    transition`), turning workflow.yaml validation into an
    unintentional precondition for transition behaviour. Filed as
    follow-up: see post-completion-comments.md §Follow-ups
    "snapshot/restore tripwire registry for validate-time ref checks".
    """
    from tripwire.core.workflow.registry import known_tripwire_ids

    return known_tripwire_ids()


def _known_prompt_checks(project_dir):  # type: ignore[no-untyped-def]
    """Return the registry-declared prompt-check ids.

    Populated by KUI-122 once each PM-skill slash command declares
    ``fires_at:`` in its frontmatter.
    """
    from tripwire.core.workflow.registry import known_prompt_check_ids

    return known_prompt_check_ids(project_dir)

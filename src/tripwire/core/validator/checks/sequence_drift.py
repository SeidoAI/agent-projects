"""Identity invariant: ``project.yaml.next_issue_number`` stays ahead of max key."""

from __future__ import annotations

from tripwire.core.id_generator import parse_key
from tripwire.core.store import PROJECT_CONFIG_FILENAME
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_sequence_drift(ctx: ValidationContext) -> list[CheckResult]:
    """`project.yaml.next_issue_number` must be at least max(existing keys) + 1."""
    if ctx.project_config is None:
        return []
    max_n = 0
    for entity in ctx.issues:
        try:
            _, n = parse_key(entity.model.id)
        except ValueError:
            continue
        if n > max_n:
            max_n = n
    expected = max_n + 1
    if ctx.project_config.next_issue_number < expected:
        return [
            CheckResult(
                code="sequence/drift",
                severity="warning",
                file=PROJECT_CONFIG_FILENAME,
                field="next_issue_number",
                message=(
                    f"next_issue_number={ctx.project_config.next_issue_number} but "
                    f"max existing issue key is {max_n}. Counter should be >= {expected}."
                ),
                fix_hint=f"Run with --fix to bump next_issue_number to {expected}.",
            )
        ]
    return []

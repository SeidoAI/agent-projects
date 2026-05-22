"""Identity invariant: issue ids match the project's ``<key_prefix>-<N>``."""

from __future__ import annotations

from tripwire.core.id_generator import parse_key
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.issue import Issue


def check_id_format(ctx: ValidationContext) -> list[CheckResult]:
    """Issue IDs must match `<key_prefix>-<N>` from project.yaml.

    Node and session IDs are validated by the Pydantic model itself.
    """
    if ctx.project_config is None:
        return []
    expected_prefix = ctx.project_config.key_prefix
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        try:
            prefix, _n = parse_key(issue.id)
        except ValueError:
            results.append(
                CheckResult(
                    code="id/format",
                    severity="error",
                    file=entity.rel_path,
                    field="id",
                    message=f"Issue id {issue.id!r} is not in the form <PREFIX>-<N>.",
                )
            )
            continue
        if prefix != expected_prefix:
            results.append(
                CheckResult(
                    code="id/wrong_prefix",
                    severity="error",
                    file=entity.rel_path,
                    field="id",
                    message=(
                        f"Issue id {issue.id!r} has prefix {prefix!r} but the "
                        f"project's key_prefix is {expected_prefix!r}."
                    ),
                    fix_hint=f"Rename the id to {expected_prefix}-N to match project.yaml.",
                )
            )
    return results

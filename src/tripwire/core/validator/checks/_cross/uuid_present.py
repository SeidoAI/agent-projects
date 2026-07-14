"""Identity invariant: every loaded entity carries a ``uuid`` field."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext


def check_uuid_present(ctx: ValidationContext) -> list[CheckResult]:
    """Every loaded entity must carry a `uuid` field.

    The model's `default_factory=uuid.uuid4` ensures a UUID is always set on
    Pydantic instances; this check exists to catch the case where someone
    has hand-edited a YAML file and removed the field. We look at the raw
    frontmatter, not the model.
    """
    results: list[CheckResult] = []
    for bucket, kind in (
        (ctx.issues, "issue"),
        (ctx.nodes, "node"),
        (ctx.sessions, "session"),
        (ctx.comments, "comment"),
    ):
        for entity in bucket:
            if "uuid" not in entity.raw_frontmatter:
                results.append(
                    CheckResult(
                        code="uuid/missing",
                        severity="error",
                        file=entity.rel_path,
                        field="uuid",
                        message=f"{kind} has no `uuid` field in frontmatter.",
                        fix_hint="Run with --fix to auto-generate a uuid4.",
                    )
                )
    return results

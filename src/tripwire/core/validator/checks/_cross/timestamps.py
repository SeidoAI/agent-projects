"""Identity invariant: parseable ``created_at`` / ``updated_at`` on every entity."""

from __future__ import annotations

from datetime import datetime

from tripwire.core.validator._types import CheckResult, ValidationContext


def check_timestamps(ctx: ValidationContext) -> list[CheckResult]:
    """Every entity should have parseable created_at / updated_at where applicable."""
    results: list[CheckResult] = []
    for kind, bucket in (
        ("issue", ctx.issues),
        ("node", ctx.nodes),
        ("session", ctx.sessions),
    ):
        for entity in bucket:
            for field_name in ("created_at", "updated_at"):
                value = getattr(entity.model, field_name, None)
                if value is None:
                    results.append(
                        CheckResult(
                            code="timestamp/missing",
                            severity="warning",
                            file=entity.rel_path,
                            field=field_name,
                            message=f"{kind} has no {field_name}.",
                            fix_hint=f"Run with --fix to set {field_name} from file mtime.",
                        )
                    )
                elif not isinstance(value, datetime):
                    results.append(
                        CheckResult(
                            code="timestamp/invalid",
                            severity="error",
                            file=entity.rel_path,
                            field=field_name,
                            message=f"{kind} {field_name} is not a valid ISO datetime.",
                        )
                    )
    return results

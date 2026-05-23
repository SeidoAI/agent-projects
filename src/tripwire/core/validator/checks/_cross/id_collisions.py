"""Identity invariant: two files claiming the same id with different uuids."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, LoadedEntity, ValidationContext


def check_id_collisions(ctx: ValidationContext) -> list[CheckResult]:
    """Two entity files claiming the same id with different uuids → error."""
    results: list[CheckResult] = []
    for kind, bucket in (
        ("issue", ctx.issues),
        ("node", ctx.nodes),
        ("session", ctx.sessions),
    ):
        seen: dict[str, list[LoadedEntity]] = {}
        for entity in bucket:
            seen.setdefault(entity.model.id, []).append(entity)
        for entity_id, entities in seen.items():
            if len(entities) <= 1:
                continue
            unique_uuids = {str(e.model.uuid) for e in entities}
            if len(unique_uuids) == 1:
                # Same id and same uuid — duplicate file, weird but not a collision.
                continue
            files = ", ".join(e.rel_path for e in entities)
            results.append(
                CheckResult(
                    code="collision/id",
                    severity="error",
                    file=entities[0].rel_path,
                    field="id",
                    message=(
                        f"{kind} id {entity_id!r} is claimed by multiple files with "
                        f"different uuids: {files}"
                    ),
                    fix_hint="Run with --fix to rename one and rewrite local references.",
                )
            )
    return results

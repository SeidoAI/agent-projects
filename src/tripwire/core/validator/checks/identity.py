"""Identity invariants: uuid presence, id format, collisions, sequence drift, timestamps."""

from __future__ import annotations

from datetime import datetime

from tripwire.core.id_generator import parse_key
from tripwire.core.store import PROJECT_CONFIG_FILENAME
from tripwire.core.validator._types import CheckResult, LoadedEntity, ValidationContext
from tripwire.core.workflow.registry import registers_at
from tripwire.models.issue import Issue


@registers_at("coding-session", "executing")
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


@registers_at("coding-session", "executing")
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


@registers_at("coding-session", "executing")
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


@registers_at("coding-session", "executing")
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


@registers_at("coding-session", "executing")
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

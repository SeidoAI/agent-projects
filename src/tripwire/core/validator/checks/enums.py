"""Enum-value validity: every enum-typed field carries a value in the active enum."""

from __future__ import annotations

from typing import Any

from tripwire.core.enum_loader import EnumRegistry
from tripwire.core.validator._types import CheckResult, LoadedEntity, ValidationContext
from tripwire.models.comment import Comment
from tripwire.models.issue import Issue
from tripwire.models.node import ConceptNode
from tripwire.models.session import AgentSession


def _check_enum_field(
    entity: LoadedEntity,
    enum_name: str,
    field_name: str,
    value: Any,
    enums: EnumRegistry,
    code: str,
) -> CheckResult | None:
    if value is None:
        return None

    raw = str(value)
    if enums.is_valid(enum_name, raw):
        return None

    # v0.9.4: alias-aware fallback for issue_status / session_status. A
    # pre-v0.9.4 project still has its enum yaml at the legacy values
    # (backlog/todo/etc.), but the loaded model normalizes them to
    # canonical via StrEnum.__missing__. Without this fallback, every
    # issue/session in a pre-backfill project fails enum validation.
    # Compare BOTH directions: if the project enum accepts the legacy
    # alias of the canonical value (or vice versa), pass.
    if enum_name in ("issue_status", "session_status"):
        from tripwire.core.status_contract import (
            normalize_issue_status,
            normalize_session_status,
        )

        normalize = (
            normalize_issue_status
            if enum_name == "issue_status"
            else normalize_session_status
        )
        canonical = normalize(raw)

        # Direction 1: model emitted canonical, project enum has legacy.
        # Build the reverse alias map (canonical → legacy) from the
        # forward map and test if any legacy spelling of `canonical` is
        # in the project enum.
        from tripwire.core.status_contract import (
            ISSUE_ALIASES,
            SESSION_ALIASES,
        )

        aliases = ISSUE_ALIASES if enum_name == "issue_status" else SESSION_ALIASES
        legacy_for_canonical = {
            legacy for legacy, canon in aliases.items() if canon == canonical
        }
        if any(enums.is_valid(enum_name, legacy) for legacy in legacy_for_canonical):
            return None

        # Direction 2: model emitted legacy (raw == legacy), project enum
        # has canonical. enums.is_valid(canonical) handles this.
        if canonical != raw and enums.is_valid(enum_name, canonical):
            return None

    valid = ", ".join(enums.value_ids(enum_name)) or "(none)"
    return CheckResult(
        code=code,
        severity="error",
        file=entity.rel_path,
        field=field_name,
        message=f"{field_name}={value!r} not in active {enum_name} enum.",
        fix_hint=f"Valid values: {valid}",
    )


def check_enum_values(ctx: ValidationContext) -> list[CheckResult]:
    """Every enum-typed field on every entity must have a value in the active enum."""
    results: list[CheckResult] = []

    for entity in ctx.issues:
        issue: Issue = entity.model
        for enum_name, value in (
            ("issue_status", issue.status),
            ("priority", issue.priority),
            ("executor", issue.executor),
            ("verifier", issue.verifier),
        ):
            r = _check_enum_field(
                entity, enum_name, enum_name, value, ctx.enums, f"enum/{enum_name}"
            )
            if r:
                results.append(r)

    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for enum_name, value in (
            ("node_type", node.type),
            ("node_status", node.status),
        ):
            r = _check_enum_field(
                entity, enum_name, enum_name, value, ctx.enums, f"enum/{enum_name}"
            )
            if r:
                results.append(r)

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        r = _check_enum_field(
            entity,
            "session_status",
            "status",
            session.status,
            ctx.enums,
            "enum/session_status",
        )
        if r:
            results.append(r)
        if session.current_state is not None:
            r2 = _check_enum_field(
                entity,
                "agent_state",
                "current_state",
                session.current_state,
                ctx.enums,
                "enum/agent_state",
            )
            if r2:
                results.append(r2)

    for entity in ctx.comments:
        comment: Comment = entity.model
        r = _check_enum_field(
            entity,
            "comment_type",
            "type",
            comment.type,
            ctx.enums,
            "enum/comment_type",
        )
        if r:
            results.append(r)

    return results

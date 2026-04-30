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
    if not enums.is_valid(enum_name, str(value)):
        valid = ", ".join(enums.value_ids(enum_name)) or "(none)"
        return CheckResult(
            code=code,
            severity="error",
            file=entity.rel_path,
            field=field_name,
            message=f"{field_name}={value!r} not in active {enum_name} enum.",
            fix_hint=f"Valid values: {valid}",
        )
    return None


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

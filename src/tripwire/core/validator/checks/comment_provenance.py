"""Every comment carries author / type / created_at."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.comment import Comment


def check_comment_provenance(ctx: ValidationContext) -> list[CheckResult]:
    """Every comment has author/type/created_at; type is in the active enum."""
    results: list[CheckResult] = []
    for entity in ctx.comments:
        comment: Comment = entity.model
        if not comment.author:
            results.append(
                CheckResult(
                    code="comment/no_author",
                    severity="error",
                    file=entity.rel_path,
                    field="author",
                    message="Comment is missing required field `author`.",
                )
            )
        if not comment.type:
            results.append(
                CheckResult(
                    code="comment/no_type",
                    severity="error",
                    file=entity.rel_path,
                    field="type",
                    message="Comment is missing required field `type`.",
                )
            )
        if comment.created_at is None:
            results.append(
                CheckResult(
                    code="comment/no_created_at",
                    severity="error",
                    file=entity.rel_path,
                    field="created_at",
                    message="Comment is missing required field `created_at`.",
                )
            )
    return results

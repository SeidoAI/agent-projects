"""Project standards: ``<project>/standards.md`` exists when referenced."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_project_standards(ctx: ValidationContext) -> list[CheckResult]:
    """V0 standards check: just confirm `<project>/standards.md` exists if any
    file references it. Future versions will read project-defined rules.
    """
    standards_path = ctx.project_dir / paths.STANDARDS
    referenced = False
    for bucket in (ctx.issues, ctx.nodes, ctx.sessions):
        for entity in bucket:
            if paths.STANDARDS in entity.body:
                referenced = True
                break
        if referenced:
            break
    if referenced and not standards_path.exists():
        return [
            CheckResult(
                code="standards/missing",
                severity="warning",
                file=None,
                message=(
                    "An entity references standards.md, but standards.md is missing "
                    "from the project root."
                ),
            )
        ]
    return []

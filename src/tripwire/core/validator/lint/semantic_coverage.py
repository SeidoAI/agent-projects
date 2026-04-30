"""KUI-146 (D4) — issue acceptance criteria reference too few concept nodes.

For each active issue, count the ``[[node-id]]`` references inside
the ``## Acceptance criteria`` section. When the count falls below
the project-type threshold (default 1) — warn.

The rationale: AC items that don't link to the concept they're
asserting against silently lose context when the underlying spec
changes. Forcing at least one reference per issue is cheap insurance.

Threshold ``min_ac_node_refs`` is read from
:mod:`tripwire.core.validator.lint._thresholds` (overrideable via
``project.yaml.lint_config.semantic_coverage.min_ac_node_refs`` in D7).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from tripwire.core.graph.refs import extract_references
from tripwire.core.validator.lint._thresholds import get_threshold

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


_INACTIVE_ISSUE = {"done", "canceled"}

# Match the AC heading and capture text up to the next `## ` heading
# at the same level (or end of body).
_AC_SECTION = re.compile(
    r"##\s*Acceptance\s*criteria\s*\n(?P<body>.*?)(?=\n##\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if not ctx.issues:
        return []

    min_refs: int = get_threshold(
        ctx.project_config, "semantic_coverage", "min_ac_node_refs"
    ) or 1

    results: list[CheckResult] = []
    for entity in ctx.issues:
        status = str(getattr(entity.model, "status", ""))
        if status in _INACTIVE_ISSUE:
            continue
        section = _ac_section(entity.body or "")
        if section is None:
            # No AC section at all — covered by the body-structure check;
            # don't double-warn here.
            continue
        ref_count = len(extract_references(section))
        if ref_count >= min_refs:
            continue
        results.append(
            CheckResult(
                code="semantic_coverage/below_threshold",
                severity="warning",
                file=entity.rel_path,
                field="body",
                message=(
                    f"Issue {entity.model.id!r} acceptance criteria reference "
                    f"{ref_count} concept node(s); threshold is {min_refs}. "
                    f"Add a `[[node-id]]` link in the AC items so the "
                    f"requirement stays tied to its concept."
                ),
                fix_hint=(
                    "Edit the `## Acceptance criteria` section to reference "
                    "the concept node(s) the AC asserts against."
                ),
            )
        )
    return results


def _ac_section(body: str) -> str | None:
    """Extract the text inside ``## Acceptance criteria`` — None if absent."""
    match = _AC_SECTION.search(body)
    if match is None:
        return None
    return match.group("body")

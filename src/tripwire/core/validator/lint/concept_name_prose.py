"""KUI-145 (D3) — concept name appears as prose without ``[[node-id]]``.

Heuristic: when the human-readable name of a concept node appears in
≥N (default 2) issue bodies AS PROSE (case-folded substring match),
without those issues using a proper ``[[node-id]]`` reference, the
project is drifting back toward "names as identifiers". The lint
warns rather than errors — the heuristic has false positives and the
fix is a one-line edit.

Threshold ``min_issues`` is read from
:mod:`tripwire.core.validator.lint._thresholds` (overrideable via
``project.yaml.lint_config.concept_name_prose.min_issues`` in D7).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from tripwire.core.graph.refs import FENCE_PATTERN, extract_references
from tripwire.core.validator.lint._thresholds import get_threshold

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


# Match `[[anything]]` to strip references before scanning prose so the
# proper-ref text doesn't double-count as prose.
_REF_STRIP = re.compile(r"\[\[[^\]]+\]\]")


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if not ctx.nodes or not ctx.issues:
        return []

    min_issues = get_threshold(ctx.project_config, "concept_name_prose", "min_issues")
    if min_issues is None:
        min_issues = 2

    rel_by_id = {e.model.id: e.rel_path for e in ctx.nodes}
    results: list[CheckResult] = []

    for node_entity in ctx.nodes:
        node = node_entity.model
        name = (getattr(node, "name", "") or "").strip()
        # Skip very-short names — too generic, false-positive risk too high.
        if len(name) < 3:
            continue
        needle = name.casefold()

        prose_hits: list[str] = []
        for issue_entity in ctx.issues:
            body = issue_entity.body or ""
            refs = set(extract_references(body))
            if node.id in refs:
                # Issue uses the proper reference — prose match doesn't count.
                continue
            stripped = _strip_prose_text(body)
            if needle in stripped.casefold():
                prose_hits.append(issue_entity.model.id)

        if len(prose_hits) >= min_issues:
            results.append(
                CheckResult(
                    code="concept_name_prose/found",
                    severity="warning",
                    file=rel_by_id.get(node.id),
                    field="name",
                    message=(
                        f"Concept node {node.id!r} (name {name!r}) appears as "
                        f"prose in {len(prose_hits)} issue(s) without a "
                        f"`[[{node.id}]]` reference: "
                        f"{', '.join(sorted(prose_hits))}. Replace prose "
                        f"mentions with the link form so renames stay safe."
                    ),
                )
            )

    return results


def _strip_prose_text(body: str) -> str:
    """Return body text with [[refs]] removed and code fences excluded.

    The lint scans only prose — references are stripped so an issue
    that already uses ``[[auth-system]]`` doesn't ALSO count its
    rendered-text portion as a prose hit.
    """
    out_lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out_lines.append(_REF_STRIP.sub("", line))
    return "\n".join(out_lines)

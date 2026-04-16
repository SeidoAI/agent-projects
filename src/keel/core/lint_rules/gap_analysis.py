"""lint/gap_analysis_row_density — warn when gap-analysis.md rows per
issue ratio is too low (phase-range map style instead of per-deliverable).

The heuristic: phase-range maps (broad bucketing) typically have fewer
than 3 rows per concrete issue. A proper per-deliverable gap analysis
has many more. If the ratio is below threshold, the PM agent is likely
shortcutting the scoping workflow.
"""

from __future__ import annotations

from keel.core.linter import LintFinding, register_rule
from keel.core.store import list_issues

GAP_DOC = "docs/gap-analysis.md"
MIN_ROWS_PER_ISSUE = 3


@register_rule(
    stage="scoping", code="lint/gap_analysis_row_density", severity="warning"
)
def _check(ctx):
    path = ctx.project_dir / GAP_DOC
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    data_rows = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip header divider rows like |---|---|
        if set(stripped.replace("|", "").strip()) <= set("-: "):
            continue
        data_rows += 1
    # Subtract the header row (first table row).
    if data_rows > 0:
        data_rows -= 1

    issues = list(list_issues(ctx.project_dir))
    issue_count = len(issues)
    if issue_count == 0:
        return
    if data_rows < MIN_ROWS_PER_ISSUE * issue_count:
        yield LintFinding(
            code="lint/gap_analysis_row_density",
            severity="warning",
            message=(
                f"gap-analysis.md has {data_rows} rows for {issue_count} issues "
                f"({data_rows / issue_count:.1f} rows/issue, threshold "
                f"{MIN_ROWS_PER_ISSUE}). Phase-range maps don't replace "
                "per-deliverable analysis."
            ),
            file=GAP_DOC,
            fix_hint=(
                "Expand to per-deliverable rows (what each delivers, "
                "existing gap, acceptance criteria)."
            ),
        )

"""Issue body structure: required Markdown headings, acceptance checkbox, refs."""

from __future__ import annotations

from tripwire.core.graph.refs import extract_references
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.issue import Issue

# Required Markdown body sections. Concrete issues must include all of
# REQUIRED_ISSUE_BODY_HEADINGS; epics use the smaller REQUIRED_EPIC_BODY_HEADINGS.
REQUIRED_ISSUE_BODY_HEADINGS = (
    "Context",
    "Implements",
    "Repo scope",
    "Requirements",
    "Execution constraints",
    "Acceptance criteria",
    "Test plan",
    "Dependencies",
    "Definition of Done",
)
REQUIRED_EPIC_BODY_HEADINGS = (
    "Context",
    "Child issues",
    "Acceptance criteria",
)


def _is_epic(issue) -> bool:
    """Return True if the issue has a ``type/epic`` label."""
    return any(label == "type/epic" for label in getattr(issue, "labels", []))


def _section(body: str, heading: str) -> str | None:
    marker = f"## {heading}"
    if marker not in body:
        return None
    after = body.split(marker, 1)[1]
    next_heading = after.find("\n## ")
    if next_heading == -1:
        return after
    return after[:next_heading]


def check_issue_body_structure(ctx: ValidationContext) -> list[CheckResult]:
    """Required Markdown headings, acceptance checkbox, stop-and-ask, refs count.

    Epics (issues with ``type/epic`` label) have relaxed requirements:
    only Context, Child issues, and Acceptance criteria headings are
    required, and stop-and-ask guidance is not checked.
    """
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        body = issue.body
        epic = _is_epic(issue)
        required_headings = (
            REQUIRED_EPIC_BODY_HEADINGS if epic else REQUIRED_ISSUE_BODY_HEADINGS
        )

        for heading in required_headings:
            if f"## {heading}" not in body:
                results.append(
                    CheckResult(
                        code="body/missing_heading",
                        severity="warning",
                        file=entity.rel_path,
                        field="body",
                        message=f"Issue body is missing required heading `## {heading}`.",
                        fix_hint=f"Add a `## {heading}` section to the issue body.",
                    )
                )

        # Acceptance criteria checkbox
        accept_section = _section(body, "Acceptance criteria")
        if (
            accept_section is not None
            and "- [ ]" not in accept_section
            and "- [x]" not in accept_section
        ):
            results.append(
                CheckResult(
                    code="body/no_acceptance_checkbox",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message="Acceptance criteria section has no checkbox items.",
                )
            )

        # Stop-and-ask guidance — not required for epics (they are not
        # executed by agents, so ambiguity guidance is irrelevant).
        if (
            not epic
            and "stop and ask" not in body.lower()
            and "stop, ask" not in body.lower()
        ):
            results.append(
                CheckResult(
                    code="body/no_stop_and_ask",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message="Issue body is missing 'stop and ask' guidance for ambiguity.",
                )
            )

        # Node references — warning for both epics and concrete issues,
        # but epics are less likely to reference code-level nodes.
        if not extract_references(body):
            results.append(
                CheckResult(
                    code="body/no_references",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message=(
                        "Issue body has no [[references]] to concept nodes — "
                        "potential coherence gap."
                    ),
                    fix_hint=(
                        "Reference the relevant concept nodes (endpoints, models, contracts) "
                        "in the body using [[node-id]]."
                    ),
                )
            )

    return results

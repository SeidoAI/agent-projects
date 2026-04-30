"""Issue body structure, status transitions, handoff.yaml schema."""

from __future__ import annotations

from pydantic import ValidationError

from tripwire.core import paths
from tripwire.core.parser import ParseError, parse_frontmatter_body
from tripwire.core.reference_parser import extract_references
from tripwire.core.status import is_status_reachable
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.issue import Issue
from tripwire.models.session import AgentSession

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


def _section(body: str, heading: str) -> str | None:
    marker = f"## {heading}"
    if marker not in body:
        return None
    after = body.split(marker, 1)[1]
    next_heading = after.find("\n## ")
    if next_heading == -1:
        return after
    return after[:next_heading]


def check_status_transitions(ctx: ValidationContext) -> list[CheckResult]:
    """Every issue's status must be reachable from the project's start state."""
    if ctx.project_config is None:
        return []
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        if not is_status_reachable(ctx.project_config, issue.status):
            results.append(
                CheckResult(
                    code="status/unreachable",
                    severity="error",
                    file=entity.rel_path,
                    field="status",
                    message=(
                        f"Issue status {issue.status!r} is not reachable from "
                        f"the start state via project.yaml.status_transitions."
                    ),
                    fix_hint="Check status_transitions in project.yaml.",
                )
            )
    return results


def check_handoff_artifact(ctx: ValidationContext) -> list[CheckResult]:
    """v0.6a: sessions in ``queued`` state require a valid handoff.yaml.

    Three possible findings:
    - ``handoff_schema/required_at_queued`` — session queued but file missing.
    - ``handoff_schema/branch_format`` — handoff.yaml.branch violates
      the ``<type>/<slug>`` convention (extracted via raw YAML parse so
      malformed branches surface cleanly, not as generic schema errors).
    - ``handoff_schema/malformed`` — any other parse/schema failure.
    """
    results: list[CheckResult] = []

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        if session.status != "queued":
            continue

        handoff_file_rel = f"{paths.SESSIONS_DIR}/{session.id}/{paths.HANDOFF_FILENAME}"
        handoff_file = paths.handoff_path(ctx.project_dir, session.id)
        if not handoff_file.is_file():
            results.append(
                CheckResult(
                    code="handoff_schema/required_at_queued",
                    severity="error",
                    file=handoff_file_rel,
                    message=(
                        f"Session {session.id!r} is queued but handoff.yaml "
                        "is missing — launch requires a structured handoff "
                        "artifact."
                    ),
                    fix_hint=(
                        "Run `/pm-session-queue` which creates handoff.yaml, "
                        "or write sessions/<id>/handoff.yaml manually."
                    ),
                )
            )
            continue

        # Check branch format via raw YAML parse first so malformed branch
        # strings surface as handoff_schema/branch_format (the specific code
        # callers expect), not as a generic Pydantic ValidationError.
        try:
            text = handoff_file.read_text(encoding="utf-8")
            frontmatter, _body = parse_frontmatter_body(text)
        except (ParseError, OSError) as exc:
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=f"handoff.yaml failed to parse: {exc}",
                )
            )
            continue

        branch = frontmatter.get("branch") if isinstance(frontmatter, dict) else None
        if isinstance(branch, str):
            from tripwire.core.branch_naming import is_valid_branch_name

            if not is_valid_branch_name(branch, project_dir=ctx.project_dir):
                results.append(
                    CheckResult(
                        code="handoff_schema/branch_format",
                        severity="error",
                        file=handoff_file_rel,
                        field="branch",
                        message=(
                            f"handoff.yaml.branch {branch!r} does not match "
                            "the <type>/<slug> convention."
                        ),
                        fix_hint=(
                            "Run `tripwire session derive-branch <session-id>` "
                            "and copy its output."
                        ),
                    )
                )
                continue

        # Pydantic validation catches any other schema problems (missing
        # required fields, bad types). The branch validator inside
        # SessionHandoff raises the same branch-format error, but this
        # function already handled that code above, so any ValidationError
        # here is structural.
        try:
            from tripwire.core.handoff_store import load_handoff

            load_handoff(ctx.project_dir, session.id)
        except ValidationError as exc:
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=f"handoff.yaml schema validation failed: {exc}",
                )
            )
        except ValueError as exc:
            # branch format (caught again via SessionHandoff validator) or
            # unparseable YAML.
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=str(exc),
                )
            )

    return results

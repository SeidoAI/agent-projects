"""Issue body structure, status transitions, handoff.yaml schema."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from tripwire.core import paths
from tripwire.core.graph.refs import extract_references
from tripwire.core.parser import ParseError, parse_frontmatter_body
from tripwire.core.status import build_issue_transitions, is_status_reachable
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
    """Every issue's status must be reachable via the issue-closure workflow.

    v0.13.1 (B8): reachability is now derived from ``workflow.yaml``'s
    ``issue-closure`` workflow routes — the hand-rolled
    ``project.yaml.status_transitions`` table this used to consult was
    deleted.

    Projects without an ``issue-closure`` workflow get the
    "trivially reachable" fallback (every declared status counts), so
    the check is a no-op rather than failing every issue.
    """
    if ctx.project_config is None:
        return []
    transitions = build_issue_transitions(ctx.project_dir)
    declared = list(ctx.project_config.statuses)
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        if not is_status_reachable(
            transitions, issue.status, declared_statuses=declared
        ):
            results.append(
                CheckResult(
                    code="status/unreachable",
                    severity="error",
                    file=entity.rel_path,
                    field="status",
                    message=(
                        f"Issue status {issue.status!r} is not reachable from "
                        f"the start state via the issue-closure workflow "
                        f"routes in workflow.yaml."
                    ),
                    fix_hint=(
                        "Check the issue-closure workflow's `routes:` block "
                        "in workflow.yaml or fix the issue's status."
                    ),
                )
            )
    return results


def check_project_repos_present(ctx: ValidationContext) -> list[CheckResult]:
    """``project.yaml.repos`` must declare the project's own meta-repo
    (the "PT repo") as at least one entry (v0.10.0+).

    The dashboard distinguishes the PT repo (slug ending in
    ``/<project.name>`` OR with ``local`` matching the project dir)
    from generic code-output repos. Without a PT-repo entry the
    "project repo · …" affordance can't render. Mirror the JS predicate
    in ``web/src/features/dashboard/ProjectDashboard.tsx::isPtRepo``
    so the two surfaces agree.

    Validate-time check (not schema-time) — projects that load but
    lack a PT repo surface as a structured finding instead of
    crashing the whole validator with a Pydantic exception.
    """
    config = ctx.project_config
    if config is None:
        return []
    project_dir = ctx.project_dir.resolve()
    name = config.name
    repos = config.repos or {}

    for slug, entry in repos.items():
        # Match by local-path equality (entry.local == project.dir)
        # OR by slug suffix (slug.endswith('/' + name)). Either is
        # enough, mirroring the dashboard's `isPtRepo` predicate.
        local = entry.local if entry is not None else None
        if local is not None:
            try:
                if Path(local).expanduser().resolve() == project_dir:
                    return []
            except OSError:
                # An unresolvable path doesn't match — fall through
                # to the slug-suffix test. A separate check could
                # surface the dangling path; out of scope here.
                pass
        if slug.endswith("/" + name):
            return []

    return [
        CheckResult(
            code="project/repos_required",
            severity="error",
            file=paths.PROJECT_CONFIG,
            field="repos",
            message=(
                f"project.yaml.repos has no entry for the project's own "
                f"repo (slug ending in /{name}, or local matching the "
                "project dir); the v0.10.0 dashboard can't render the "
                "'project repo' affordance without it."
            ),
            fix_hint=(
                "Add an entry to project.yaml.repos that identifies the "
                "project's own meta-repo:\n"
                f"  repos:\n"
                f"    SeidoAI/project-{name}:\n"
                f"      local: <project-dir>"
            ),
        )
    ]


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


def check_instance_shape_conforms(ctx: ValidationContext) -> list[CheckResult]:
    """Every materialised instance must match its workflow's declared shape.

    For each workflow that declares an ``instance:`` block in
    ``workflow.yaml``, walk the disk via :func:`list_instances` and
    confirm that each instance file:

    - carries every entry in ``required_fields``
      (missing → ``instance/missing_required_field``);
    - carries a value at ``status_field`` that's in ``status_enum``
      (out-of-enum → ``instance/invalid_status_value``).

    Workflows without an ``instance:`` block are skipped silently;
    that gap is already reported by ``workflow/instance_missing``
    inside :func:`check_workflow_well_formed`. A workflow.yaml that
    fails to parse is also skipped silently — the parse error
    surfaces through ``v_workflow_well_formed``.
    """
    # Local imports keep the validator/workflow circular surface minimal.
    from tripwire.core.workflow.instance_io import (
        InstanceNotFoundError,
        list_instances,
        load_instance,
    )
    from tripwire.core.workflow.loader import load_workflows

    results: list[CheckResult] = []
    try:
        spec = load_workflows(ctx.project_dir)
    except yaml.YAMLError:
        # workflow.yaml parse errors are reported by
        # ``check_workflow_well_formed`` — no point double-reporting.
        return results

    for workflow_id, workflow in spec.workflows.items():
        shape = workflow.instance
        if shape is None:
            # Missing-block warning is owned by the workflow validator;
            # silently skip per the v0.13.1 design.
            continue
        try:
            instance_ids = list_instances(ctx.project_dir, workflow_id)
        except (LookupError, ValueError):
            # Resolution problems already surface via workflow lints.
            continue

        status_enum = set(shape.status_enum)
        for instance_id in instance_ids:
            try:
                data = load_instance(ctx.project_dir, workflow_id, instance_id)
            except InstanceNotFoundError:
                # Disappeared between list and load; nothing to assert.
                continue
            except (ValueError, ParseError):
                # Parse errors are reported by the entity loader
                # (e.g. ``session/parse_error``); skip silently here.
                continue

            rendered = ctx.project_dir / shape.storage_path.replace(
                "{instance_id}", instance_id
            )
            try:
                rel_path = str(rendered.relative_to(ctx.project_dir))
            except ValueError:
                rel_path = str(rendered)

            for required in shape.required_fields:
                if required not in data or data.get(required) in (None, ""):
                    results.append(
                        CheckResult(
                            code="instance/missing_required_field",
                            severity="error",
                            file=rel_path,
                            field=required,
                            message=(
                                f"workflow {workflow_id!r} instance "
                                f"{instance_id!r} is missing required field "
                                f"{required!r} declared on "
                                f"workflow.yaml `instance.required_fields`."
                            ),
                            fix_hint=(f"Add `{required}: <value>` to {rel_path}."),
                        )
                    )

            if status_enum:
                value = data.get(shape.status_field)
                if value is None or value not in status_enum:
                    results.append(
                        CheckResult(
                            code="instance/invalid_status_value",
                            severity="error",
                            file=rel_path,
                            field=shape.status_field,
                            message=(
                                f"workflow {workflow_id!r} instance "
                                f"{instance_id!r} has "
                                f"`{shape.status_field}: {value!r}` which "
                                f"is not in the declared status_enum "
                                f"{sorted(status_enum)}."
                            ),
                            fix_hint=(
                                f"Set `{shape.status_field}` to one of "
                                f"{sorted(status_enum)} in {rel_path}, or "
                                f"add the value to "
                                f"workflow.yaml `instance.status_enum`."
                            ),
                        )
                    )

    return results

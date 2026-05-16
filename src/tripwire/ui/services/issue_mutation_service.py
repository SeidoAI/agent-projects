"""Issue mutation service — status transitions and partial field patches.

The read side of issue access lives in
:mod:`tripwire.ui.services.issue_service`. This module is the write
counterpart used by the ``PATCH /api/projects/{pid}/issues/{key}`` and
``POST /.../issues/{key}/status`` routes.

Two public entry points:

- :func:`update_issue_status` validates the requested new status against
  the ``issue-closure`` workflow's routes in ``workflow.yaml`` and
  rejects any transition that isn't a declared edge.
- :func:`update_issue_fields` applies a partial
  :class:`IssuePatch` — only non-``None`` fields flow through to disk.
  Status transitions inside a patch still go through the same validator.
  Priority / label / agent changes are validated against the
  project's enums via :func:`tripwire.core.enum_loader.load_enum`.

Every successful mutation appends an entry to the project's audit log;
invalid transitions and bad enum values raise :class:`ValueError` so the
route can translate to 409 / 400.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tripwire.core.enum_loader import load_enum
from tripwire.core.locks import project_lock
from tripwire.core.status import build_issue_transitions
from tripwire.core.store import load_issue, load_project, save_issue
from tripwire.ui.services._audit import write_audit_entry
from tripwire.ui.services.issue_service import IssueDetail, get_issue

logger = logging.getLogger("tripwire.ui.services.issue_mutation_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class IssuePatch(BaseModel):
    """Partial update for an Issue.

    Every field is optional; only non-``None`` values are applied. The
    model forbids any field outside this allowlist, which is how we keep
    the immutable ``uuid`` / ``id`` / ``created_at`` triplet unreachable
    from the PATCH route.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    status: str | None = None
    priority: str | None = None
    labels: list[str] | None = None
    agent: str | None = None

    def set_fields(self) -> dict[str, object]:
        """Return the fields the caller actually set (excluding ``None``)."""
        return self.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _validate_transition(
    project_dir: Path, current_status: str, new_status: str
) -> None:
    """Raise ``ValueError`` if *new_status* isn't reachable from *current_status*.

    The allowed-next-states map is derived from the ``issue-closure``
    workflow's routes in ``workflow.yaml``. An empty allowlist for the
    current state means "no transitions out of this state" via the
    workflow and blocks every change.
    """
    transitions = build_issue_transitions(project_dir)
    allowed = set(transitions.get(current_status, []))

    if new_status == current_status:
        # No-op transition: skip allowlist.
        return
    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition from {current_status!r} to {new_status!r}. "
            f"Allowed next statuses: {sorted(allowed)}"
        )


def _validate_enum_value(
    project_dir: Path, enum_name: str, value: str, *, field_label: str
) -> None:
    """Raise ``ValueError`` if *value* is not in the named enum."""
    try:
        allowed = load_enum(project_dir, enum_name)
    except FileNotFoundError as exc:
        raise ValueError(
            f"Cannot validate {field_label}: enum {enum_name!r} is not defined "
            f"for this project."
        ) from exc
    if value not in allowed:
        raise ValueError(
            f"Invalid {field_label} value {value!r}. Allowed: {sorted(allowed)}"
        )


def _validate_labels(project_dir: Path, labels: list[str]) -> None:
    """Reject any label outside the union of all project label categories.

    A category with an empty allowlist is treated as "anything allowed in
    this category", matching the validator's semantics. If every category
    is empty we skip validation entirely.
    """
    config = load_project(project_dir)
    cats = config.label_categories
    all_lists = [cats.executor, cats.verifier, cats.domain, cats.agent]
    if all(not lst for lst in all_lists):
        return
    allowed: set[str] = set()
    has_closed_category = False
    for lst in all_lists:
        if lst:
            has_closed_category = True
            allowed.update(lst)
    if not has_closed_category:
        return
    for label in labels:
        if label in allowed:
            continue
        # Allow free-form labels under a category prefix whose list is
        # empty — the open-category rule above. We enforce closed-category
        # prefixes (e.g. ``type/`` when ``domain`` lists ``type/epic``)
        # only when the exact label isn't in the union.
        prefix = label.split("/", 1)[0] if "/" in label else label
        open_category_match = False
        for cat_name, lst in zip(
            ("executor", "verifier", "domain", "agent"), all_lists, strict=False
        ):
            if not lst and prefix == cat_name:
                open_category_match = True
                break
        if open_category_match:
            continue
        raise ValueError(f"Invalid label {label!r}. Allowed labels: {sorted(allowed)}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_issue_status(project_dir: Path, key: str, new_status: str) -> IssueDetail:
    """Transition an issue's ``status`` field, returning the fresh detail.

    v0.13.2 follow-up: the status flip routes through
    :func:`tripwire.core.workflow.transitions.execute_transition` so the
    issue-closure workflow's route checks + tripwires run as a single
    gate. The pre-fix path did ``issue.status = new_status; save_issue(...)`` directly — a single-writer violation that the
    AST fitness function now catches.

    The executor takes its own per-instance lock; the audit write
    happens here in addition to the executor's audit hook (which only
    fires for coding-session today) so the UI's mutation history stays
    parallel to other UI patches.

    Raises:
        FileNotFoundError: if the issue file is missing.
        ValueError: if the transition isn't allowed by the
            ``issue-closure`` workflow routes in ``workflow.yaml``.
    """
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    # The UI-level ``project_lock`` covers load → executor-call →
    # audit-write so a crash between the save (inside the executor)
    # and the UI audit never leaves a mutated-but-unaudited issue
    # for the UI's audit log. The executor takes its own per-
    # instance transition lock under a different name — no conflict
    # with the broader project_lock.
    with project_lock(project_dir):
        issue = load_issue(project_dir, key)
        old_status = str(issue.status)

        # Idempotent same-status patches: UIs frequently re-send the
        # current status as a no-op (optimistic-update retries, drag-
        # to-same-column). The pre-v0.13.2 ``_validate_transition``
        # short-circuited this; the executor rejects same-status as
        # ``transition_not_reachable``. Preserve the no-op semantics.
        if old_status == new_status:
            return get_issue(project_dir, key)

        try:
            result = execute_transition(
                project_dir,
                workflow_id="issue-closure",
                instance_id=key,
                target_status=new_status,
            )
        except TransitionError as exc:
            msg = f"Invalid transition from {old_status!r} to {new_status!r}: {exc}"
            # Include the allowed-next list so UI clients can show
            # the operator which moves are available from the
            # current status.
            allowed = sorted(build_issue_transitions(project_dir).get(old_status, []))
            if allowed:
                msg += f". Allowed next statuses: {allowed}"
            write_audit_entry(
                project_dir,
                "issue.update_status.rejected",
                before={"status": old_status},
                after={"status": new_status},
                result_summary=msg,
                extras={"issue_key": key},
            )
            raise ValueError(msg) from exc

        if not result.ok:
            detail = result.message or result.reason or "transition rejected"
            msg = f"Invalid transition from {old_status!r} to {new_status!r}: {detail}"
            allowed = sorted(build_issue_transitions(project_dir).get(old_status, []))
            if allowed:
                msg += f". Allowed next statuses: {allowed}"
            write_audit_entry(
                project_dir,
                "issue.update_status.rejected",
                before={"status": old_status},
                after={"status": new_status},
                result_summary=msg,
                extras={"issue_key": key},
            )
            raise ValueError(msg)

        # Re-load to grab the executor's stamps (current_status_instance,
        # updated_at) for the audit `after`.
        write_audit_entry(
            project_dir,
            "issue.update_status",
            before={"status": old_status},
            after={"status": new_status},
            result_summary=f"{key}: {old_status} → {new_status}",
            extras={"issue_key": key},
        )
    logger.info("issue.update_status: %s %s → %s", key, old_status, new_status)
    return get_issue(project_dir, key)


def update_issue_fields(project_dir: Path, key: str, patch: IssuePatch) -> IssueDetail:
    """Apply *patch* to an issue, returning the fresh detail.

    Only fields the client actually set are written. Status changes still
    go through :func:`_validate_transition`; priority / agent values are
    checked against the project's enums; labels are validated against the
    project's label categories.

    The whole load → validate → save → audit sequence holds
    :func:`tripwire.core.locks.project_lock` so concurrent patches on
    the same issue serialize cleanly.

    Raises:
        FileNotFoundError: if the issue file is missing.
        ValueError: on invalid status transition, enum value, or label.
    """
    fields = patch.set_fields()
    if not fields:
        # Nothing to do — return the current detail as a cheap no-op so
        # idempotent clients (retries, optimistic UIs) don't see a 500.
        return get_issue(project_dir, key)

    # v0.13.2 follow-up: if the patch includes a status change, route
    # that through the executor (sole writer of workflow instance
    # status). Other fields (priority / labels / agent) are
    # non-workflow metadata and go through the direct write path.
    if "status" in fields:
        new_status = fields.pop("status")
        update_issue_status(project_dir, key, str(new_status))
        if not fields:
            # Status was the only field; we're done.
            return get_issue(project_dir, key)

    with project_lock(project_dir):
        issue = load_issue(project_dir, key)

        if "priority" in fields:
            _validate_enum_value(
                project_dir,
                "priority",
                fields["priority"],
                field_label="priority",
            )
        if "agent" in fields and fields["agent"] is not None:
            _validate_enum_value(
                project_dir,
                "agent_type",
                fields["agent"],
                field_label="agent",
            )
        if "labels" in fields:
            _validate_labels(project_dir, fields["labels"])

        before = {k: getattr(issue, k) for k in fields}

        for name, value in fields.items():
            setattr(issue, name, value)
        issue.updated_at = datetime.now(tz=timezone.utc)
        save_issue(project_dir, issue)

        after = {k: fields[k] for k in fields}
        write_audit_entry(
            project_dir,
            "issue.update_fields",
            before=before,
            after=after,
            result_summary=f"{key}: patched {sorted(fields)}",
            extras={"issue_key": key},
        )
    logger.info("issue.update_fields: %s patched fields=%s", key, sorted(fields))
    return get_issue(project_dir, key)


__all__ = [
    "IssuePatch",
    "update_issue_fields",
    "update_issue_status",
]

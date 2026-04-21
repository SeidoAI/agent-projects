"""Issue mutation service — status transitions and partial field patches.

The read side of issue access lives in
:mod:`tripwire.ui.services.issue_service`. This module is the write
counterpart used by the ``PATCH /api/projects/{pid}/issues/{key}`` and
``POST /.../issues/{key}/status`` routes.

Two public entry points:

- :func:`update_issue_status` validates the requested new status against
  ``project.yaml.status_transitions[current_status]`` and rejects any
  transition that isn't in the allowed list.
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
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tripwire.core.enum_loader import load_enum
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

    Looks up the allowed next-states in ``project.yaml.status_transitions``.
    An empty allowlist for the current state means "no transitions out of
    this state" and blocks every change.
    """
    config = load_project(project_dir)
    allowed = config.status_transitions.get(current_status, [])
    if new_status == current_status:
        # A no-op "transition" to the same status is harmless; skip the
        # allowlist check so callers can re-PATCH without racing the
        # transition table.
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
            f"Invalid {field_label} value {value!r}. "
            f"Allowed: {sorted(allowed)}"
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
        raise ValueError(
            f"Invalid label {label!r}. Allowed labels: {sorted(allowed)}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_issue_status(
    project_dir: Path, key: str, new_status: str
) -> IssueDetail:
    """Transition an issue's ``status`` field, returning the fresh detail.

    Raises:
        FileNotFoundError: if the issue file is missing.
        ValueError: if the transition isn't allowed by
            ``project.yaml.status_transitions``.
    """
    issue = load_issue(project_dir, key)
    old_status = issue.status

    try:
        _validate_transition(project_dir, old_status, new_status)
    except ValueError:
        # Log the rejected attempt so the audit log can show what the
        # client tried to do — useful when diagnosing UI bugs that send
        # the wrong next-status.
        write_audit_entry(
            project_dir,
            "issue.update_status.rejected",
            before={"status": old_status},
            after={"status": new_status},
            result_summary=f"Invalid transition {old_status!r} → {new_status!r}",
            extras={"issue_key": key},
        )
        raise

    issue.status = new_status
    issue.updated_at = datetime.now()
    save_issue(project_dir, issue)

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


def update_issue_fields(
    project_dir: Path, key: str, patch: IssuePatch
) -> IssueDetail:
    """Apply *patch* to an issue, returning the fresh detail.

    Only fields the client actually set are written. Status changes still
    go through :func:`_validate_transition`; priority / agent values are
    checked against the project's enums; labels are validated against the
    project's label categories.

    Raises:
        FileNotFoundError: if the issue file is missing.
        ValueError: on invalid status transition, enum value, or label.
    """
    fields = patch.set_fields()
    if not fields:
        # Nothing to do — return the current detail as a cheap no-op so
        # idempotent clients (retries, optimistic UIs) don't see a 500.
        return get_issue(project_dir, key)

    issue = load_issue(project_dir, key)

    if "status" in fields:
        _validate_transition(project_dir, issue.status, fields["status"])
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
    issue.updated_at = datetime.now()
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

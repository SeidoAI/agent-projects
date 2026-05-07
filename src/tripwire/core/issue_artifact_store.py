"""Load per-issue artifact manifest, merge project overrides, status ordering.

The manifest declares which files every issue must have at which lifecycle
status. The shipped manifest lives at
`src/tripwire/templates/issue_artifacts/manifest.yaml`; a project can append
or replace entries via `project.yaml.issue_artifact_manifest_overrides`.

`status_at_or_past(current, threshold, project_dir)` answers: has the issue
reached the required gate? Uses the active `issue_status` enum's declaration
order as the canonical lifecycle.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core.enum_loader import load_enum
from tripwire.models.issue_artifacts import IssueArtifactEntry, IssueArtifactManifest

# Canonical lifecycle order for artifact-staging logic. The list
# represents progression through the issue lifecycle.
_DEFAULT_STATUS_ORDER: list[str] = [
    "planned",
    "queued",
    "executing",
    "in_review",
    "verified",
    "completed",
]


def _shipped_manifest_path() -> Path:
    import tripwire

    return (
        Path(tripwire.__file__).parent
        / "templates"
        / "issue_artifacts"
        / "manifest.yaml"
    )


def _load_project_overrides(project_dir: Path) -> list[dict]:
    """Read project.yaml.issue_artifact_manifest_overrides. Missing project → []."""
    project_yaml = project_dir / "project.yaml"
    if not project_yaml.is_file():
        return []
    try:
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    overrides = data.get("issue_artifact_manifest_overrides") or []
    return overrides if isinstance(overrides, list) else []


def load_issue_artifact_manifest(project_dir: Path) -> IssueArtifactManifest:
    """Load shipped manifest, merge project overrides, validate enum values."""
    shipped = yaml.safe_load(_shipped_manifest_path().read_text(encoding="utf-8")) or {}
    by_name: dict[str, dict] = {a["name"]: a for a in (shipped.get("artifacts") or [])}
    for override in _load_project_overrides(project_dir):
        if not isinstance(override, dict) or "name" not in override:
            continue
        by_name[override["name"]] = override

    entries = [IssueArtifactEntry.model_validate(a) for a in by_name.values()]

    allowed_statuses = set(load_enum(project_dir, "issue_status"))
    allowed_agents = set(load_enum(project_dir, "agent_type"))

    for entry in entries:
        if entry.required_at_status not in allowed_statuses:
            raise ValueError(
                f"Issue artifact {entry.name!r} required_at_status="
                f"{entry.required_at_status!r} not in issue_status enum: "
                f"{sorted(allowed_statuses)}"
            )
        if entry.produced_by not in allowed_agents:
            raise ValueError(
                f"Issue artifact {entry.name!r} produced_by="
                f"{entry.produced_by!r} not in agent_type enum: "
                f"{sorted(allowed_agents)}"
            )
        if entry.owned_by is not None and entry.owned_by not in allowed_agents:
            raise ValueError(
                f"Issue artifact {entry.name!r} owned_by="
                f"{entry.owned_by!r} not in agent_type enum: "
                f"{sorted(allowed_agents)}"
            )

    return IssueArtifactManifest(artifacts=entries)


def _status_ordering(
    project_dir: Path | None, enum_name: str = "issue_status"
) -> list[str]:
    """Canonical lifecycle order: enum's declared order for the project,
    falling back to the tripwire default if the project has no override.

    `enum_name` selects which lifecycle enum to read — `issue_status` for
    issue-side gating (default), `session_status` for session-side. The
    canonical default is the same for both today.
    """
    if project_dir is None:
        return list(_DEFAULT_STATUS_ORDER)
    try:
        values = load_enum(project_dir, enum_name)
    except FileNotFoundError:
        return list(_DEFAULT_STATUS_ORDER)
    return list(values) if values else list(_DEFAULT_STATUS_ORDER)


SIDE_STATES: frozenset[str] = frozenset({"paused", "abandoned", "failed", "deferred"})
"""Statuses that exist outside the linear lifecycle progression.

A session/issue in one of these states is in limbo — paused awaiting
human input, deferred, abandoned without success, or failed mid-run.
Artifact-presence and coherence gates that test "have we reached
status X yet?" should treat side states as "not reached" regardless of
where they happen to sit in the enum's declared order.

Without this, projects whose `session_status.yaml` declares
`paused`/`failed`/`abandoned` AFTER `completed` would have
`status_at_or_past("paused", "completed")` return True — incorrectly
demanding completed-state artifacts from a paused session.
"""


def status_at_or_past(
    current: str,
    threshold: str,
    project_dir: Path | None = None,
    enum_name: str = "issue_status",
) -> bool:
    """Is `current` at or past `threshold` in the enum's declared order?

    Returns False if either status isn't declared — the caller should treat
    unknown statuses as "not reached" rather than raise.

    `enum_name` selects which lifecycle enum to consult. Defaults to
    `issue_status` so existing issue-side callers continue to work
    unchanged; session-side callers should pass `enum_name="session_status"`.

    v0.12: short-circuits to False when `current` is in `SIDE_STATES`
    (paused/abandoned/failed/deferred). Side states are off-lifecycle;
    artifact gates do not apply while a session/issue sits in one. When
    the entity transitions back onto the lifecycle, the gates re-engage
    based on the new status.
    """
    if current in SIDE_STATES:
        return False
    order = _status_ordering(project_dir, enum_name=enum_name)
    try:
        return order.index(current) >= order.index(threshold)
    except ValueError:
        return False

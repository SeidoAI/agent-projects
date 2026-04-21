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


_DEFAULT_STATUS_ORDER: list[str] = [
    "backlog",
    "todo",
    "in_progress",
    "in_review",
    "verified",
    "done",
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
    shipped = yaml.safe_load(
        _shipped_manifest_path().read_text(encoding="utf-8")
    ) or {}
    by_name: dict[str, dict] = {
        a["name"]: a for a in (shipped.get("artifacts") or [])
    }
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


def _status_ordering(project_dir: Path | None) -> list[str]:
    """Canonical lifecycle order: enum's declared order for the project,
    falling back to the tripwire default if the project has no override."""
    if project_dir is None:
        return list(_DEFAULT_STATUS_ORDER)
    try:
        values = load_enum(project_dir, "issue_status")
    except FileNotFoundError:
        return list(_DEFAULT_STATUS_ORDER)
    return list(values) if values else list(_DEFAULT_STATUS_ORDER)


def status_at_or_past(
    current: str, threshold: str, project_dir: Path | None = None
) -> bool:
    """Is `current` at or past `threshold` in the enum's declared order?

    Returns False if either status isn't declared — the caller should treat
    unknown statuses as "not reached" rather than raise.
    """
    order = _status_ordering(project_dir)
    try:
        return order.index(current) >= order.index(threshold)
    except ValueError:
        return False

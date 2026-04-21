"""Orchestration read service — resolve active orchestration pattern.

Reads ``<project>/orchestration/<default_pattern>.yaml`` and exposes the
resolved pattern (plus optional session-level overrides) to the UI for
read-only display. This service does NOT interpret rule semantics —
rule execution belongs in ``tripwire.containers``.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from tripwire.core import paths
from tripwire.core.session_store import load_session
from tripwire.core.store import load_project

logger = logging.getLogger("tripwire.ui.services.orchestration_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class HookDescriptor(BaseModel):
    """One hook declared in an orchestration pattern. Empty placeholder in v1."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="allow")

    name: str | None = None
    path: str | None = None
    kind: str | None = None


class RuleDescriptor(BaseModel):
    """One rule declared in an orchestration pattern."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="allow")

    event: str | None = None
    condition: str | None = None
    action: str | None = None
    description: str | None = None


class OrchestrationPattern(BaseModel):
    """Resolved orchestration pattern for a project or session."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str
    source_path: str
    plan_approval_required: bool = False
    auto_merge_on_pass: bool = False
    hooks: list[HookDescriptor] = Field(default_factory=list)
    rules: list[RuleDescriptor] = Field(default_factory=list)
    overrides_applied: list[str] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pattern_file(project_dir: Path, pattern_name: str) -> Path:
    return project_dir / paths.ORCHESTRATION_DIR / f"{pattern_name}.yaml"


def _load_pattern_yaml(path: Path) -> dict[str, Any]:
    """Load a pattern YAML into a dict.

    Raises :class:`FileNotFoundError` on miss and :class:`ValueError`
    on any parse / schema issue.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Orchestration pattern not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"Orchestration pattern {path} must be a YAML mapping, got "
            f"{type(raw).__name__}"
        )
    return raw


def _shape_pattern(
    name: str,
    source_path: Path,
    data: dict[str, Any],
    *,
    overrides_applied: list[str] | None = None,
) -> OrchestrationPattern:
    """Build an OrchestrationPattern from a pre-merged dict."""
    hooks_raw = data.get("hooks", []) or []
    rules_raw = data.get("rules", []) or []

    # Surface list-typed fields even if YAML produced weird types — the
    # route should never 500 because a project typed `rules: null` by
    # accident.
    if not isinstance(hooks_raw, list):
        logger.warning(
            "orchestration: `hooks` in %s is not a list (%s); ignoring",
            source_path,
            type(hooks_raw).__name__,
        )
        hooks_raw = []
    if not isinstance(rules_raw, list):
        logger.warning(
            "orchestration: `rules` in %s is not a list (%s); ignoring",
            source_path,
            type(rules_raw).__name__,
        )
        rules_raw = []

    hooks = [
        HookDescriptor.model_validate(h if isinstance(h, dict) else {"name": str(h)})
        for h in hooks_raw
    ]
    rules = [
        RuleDescriptor.model_validate(r if isinstance(r, dict) else {"description": str(r)})
        for r in rules_raw
    ]

    return OrchestrationPattern(
        name=str(data.get("name", name)),
        source_path=str(source_path),
        plan_approval_required=bool(data.get("plan_approval_required", False)),
        auto_merge_on_pass=bool(data.get("auto_merge_on_pass", False)),
        hooks=hooks,
        rules=rules,
        overrides_applied=overrides_applied,
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Shallow-deep merge: top-level keys union, nested dicts union, lists replace.

    - If both sides have a dict at the same key: recurse.
    - Otherwise the override wins.
    """
    out = copy.deepcopy(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(out.get(key), dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _overridden_keys(
    base: dict[str, Any], override: dict[str, Any]
) -> list[str]:
    """Return keys whose resolved value differs from the base."""
    changed: list[str] = []
    for key in override:
        if base.get(key) != override[key]:
            changed.append(key)
    changed.sort()
    return changed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_active_pattern(project_dir: Path) -> OrchestrationPattern:
    """Return the project-wide orchestration pattern.

    Raises :class:`FileNotFoundError` if the configured pattern file is
    missing.
    """
    config = load_project(project_dir)
    pattern_name = config.orchestration.default_pattern
    path = _pattern_file(project_dir, pattern_name)

    data = _load_pattern_yaml(path)
    return _shape_pattern(pattern_name, path, data, overrides_applied=None)


def get_session_pattern(
    project_dir: Path, session_id: str
) -> OrchestrationPattern:
    """Return the effective pattern for *session_id*.

    Starts from the project's active pattern. If the session has an
    `orchestration.overrides` dict, deep-merges it on top and lists the
    top-level override keys in ``overrides_applied``. If the session
    picks a different pattern via `orchestration.pattern`, that replaces
    the base before overrides are applied.
    """
    config = load_project(project_dir)
    session = load_session(project_dir, session_id)

    # Which pattern to start from.
    pattern_name = config.orchestration.default_pattern
    if session.orchestration is not None and session.orchestration.pattern:
        pattern_name = session.orchestration.pattern

    base_path = _pattern_file(project_dir, pattern_name)
    base = _load_pattern_yaml(base_path)

    if session.orchestration is None or not session.orchestration.overrides:
        # Still return the pattern; overrides_applied is None (distinct from []).
        return _shape_pattern(pattern_name, base_path, base, overrides_applied=None)

    override = dict(session.orchestration.overrides)
    merged = _deep_merge(base, override)
    changed = _overridden_keys(base, merged)

    return _shape_pattern(
        pattern_name,
        base_path,
        merged,
        overrides_applied=changed,
    )


__all__ = [
    "HookDescriptor",
    "OrchestrationPattern",
    "RuleDescriptor",
    "get_active_pattern",
    "get_session_pattern",
]

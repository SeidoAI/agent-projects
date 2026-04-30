"""Per-lint thresholds with project-level override layering.

Defaults live in ``DEFAULT_THRESHOLDS`` (mutable dict — keep keys
stable). KUI-149 (D7) extends :func:`get_threshold` to honour
``project.yaml.lint_config`` overrides; the v0.9 default-only
implementation is the floor.

Project-type-aware defaults (e.g. node_ratio differs between
``library`` and ``product`` kinds) are layered on top of
``DEFAULT_THRESHOLDS`` via ``KIND_OVERRIDES``. The active project
``kind`` comes from ``project.yaml.metadata.kind`` and falls back
to ``"product"`` when absent.

Schema design (v1.0 forward-compat note): the config block is shaped
``{lint_name: {threshold_name: value}}`` so adding a new threshold
means a new sub-key, not a model migration. A ``_schema_version``
field is intentionally NOT added in v0.9; it lands when the v1.0
contract is published (TW1-4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tripwire.models.project import ProjectConfig


# Defaults: shape `{lint_name: {threshold_name: value}}`.
DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "concept_name_prose": {
        # Min number of issues that must use the node name as prose
        # (without a [[ref]]) before the lint warns.
        "min_issues": 2,
    },
    "semantic_coverage": {
        # Min `[[node-id]]` references in the AC section per active issue.
        "min_ac_node_refs": 1,
    },
    "mega_issue": {
        # Warn when an issue has >= this many child issues OR sessions.
        "max_children": 8,
        "max_sessions": 6,
    },
    "node_ratio": {
        # Warn when nodes-per-active-issue ratio falls outside this band.
        "min_ratio": 0.10,
        "max_ratio": 5.0,
    },
}


# Per-project-kind overrides on top of DEFAULT_THRESHOLDS. Missing kinds
# fall through to the defaults; missing keys inside a kind also fall
# through. Project-team can layer their own values via
# `project.yaml.lint_config` (KUI-149).
KIND_OVERRIDES: dict[str, dict[str, dict[str, Any]]] = {
    "library": {
        # Libraries tend to have fewer issues per concept node.
        "node_ratio": {"min_ratio": 0.5, "max_ratio": 10.0},
    },
    "framework": {
        "node_ratio": {"min_ratio": 0.5, "max_ratio": 10.0},
    },
}


def get_threshold(
    project_config: ProjectConfig | None,
    lint_name: str,
    threshold_name: str,
) -> Any:
    """Return the configured threshold or the package default.

    Layering (highest precedence first):
    1. ``project.yaml.lint_config[lint_name][threshold_name]`` (KUI-149).
    2. ``KIND_OVERRIDES[project.metadata.kind][lint_name][threshold_name]``.
    3. ``DEFAULT_THRESHOLDS[lint_name][threshold_name]``.
    """
    project_override = _project_override(
        project_config, lint_name, threshold_name
    )
    if project_override is not None:
        return project_override

    kind = _project_kind(project_config)
    kind_override = (
        KIND_OVERRIDES.get(kind, {}).get(lint_name, {}).get(threshold_name)
    )
    if kind_override is not None:
        return kind_override

    return DEFAULT_THRESHOLDS.get(lint_name, {}).get(threshold_name)


def _project_kind(project_config: ProjectConfig | None) -> str:
    """Resolve ``project.yaml.metadata.kind`` with a ``product`` fallback."""
    if project_config is None:
        return "product"
    metadata = getattr(project_config, "metadata", None) or {}
    kind = metadata.get("kind") if isinstance(metadata, dict) else None
    return kind if isinstance(kind, str) and kind else "product"


def _project_override(
    project_config: ProjectConfig | None,
    lint_name: str,
    threshold_name: str,
) -> Any:
    """Read the per-project override, or None when absent.

    Reads via ``model_dump`` so the typed and dict-shaped variants
    surface the same way. Missing or malformed entries surface as
    None — overrides are advisory, not gating.
    """
    if project_config is None:
        return None
    cfg = getattr(project_config, "lint_config", None)
    if cfg is None:
        return None
    if hasattr(cfg, "model_dump"):
        cfg = cfg.model_dump()
    if not isinstance(cfg, dict):
        return None
    block = cfg.get(lint_name)
    if not isinstance(block, dict):
        return None
    return block.get(threshold_name)


__all__ = [
    "DEFAULT_THRESHOLDS",
    "KIND_OVERRIDES",
    "get_threshold",
]

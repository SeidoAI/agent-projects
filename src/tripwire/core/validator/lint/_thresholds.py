"""Per-lint thresholds with project-level override layering.

v0.14.0 — package-shipped defaults moved to
``templates/lint/defaults.yaml``. The dicts ``DEFAULT_THRESHOLDS``
and ``KIND_OVERRIDES`` are populated at import time by reading that
file; the public API (and ``get_threshold``'s merge semantics)
unchanged. KUI-149 (D7) extends :func:`get_threshold` to honour
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

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from tripwire.models.project import ProjectConfig


def _shipped_defaults_path() -> Path:
    """Path to the package-shipped lint defaults YAML."""
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "lint" / "defaults.yaml"


def _load_shipped() -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, dict[str, Any]]]
]:
    """Load (DEFAULT_THRESHOLDS, KIND_OVERRIDES) from the shipped YAML.

    Read at import time; the public dict constants below are populated
    from the result. Failing here is a packaging bug — surfacing it as
    ImportError at module load is the right move (no silent fallback).
    """
    payload = yaml.safe_load(_shipped_defaults_path().read_text(encoding="utf-8")) or {}
    defaults = payload.get("default_thresholds") or {}
    overrides = payload.get("kind_overrides") or {}
    if not isinstance(defaults, dict) or not isinstance(overrides, dict):
        raise RuntimeError(
            "templates/lint/defaults.yaml: expected top-level keys "
            "`default_thresholds` and `kind_overrides` to be mappings."
        )
    return defaults, overrides


# Defaults: shape `{lint_name: {threshold_name: value}}`.
# Populated from `templates/lint/defaults.yaml` (v0.14.0); the module-
# level constant exposes the dict so existing callers continue to work.
DEFAULT_THRESHOLDS: dict[str, dict[str, Any]]

# Per-project-kind overrides on top of DEFAULT_THRESHOLDS. Missing kinds
# fall through to the defaults; missing keys inside a kind also fall
# through. Project-team can layer their own values via
# `project.yaml.lint_config` (KUI-149).
KIND_OVERRIDES: dict[str, dict[str, dict[str, Any]]]

DEFAULT_THRESHOLDS, KIND_OVERRIDES = _load_shipped()


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

    A project override that doesn't match the type of the package
    default (e.g. user wrote ``"8"`` instead of ``8``) is treated as
    absent and falls through to the next layer. Validator runs are
    advisory state — a config typo must not crash validate.
    """
    default = DEFAULT_THRESHOLDS.get(lint_name, {}).get(threshold_name)
    expected_type = _expected_type(default)

    project_override = _project_override(project_config, lint_name, threshold_name)
    if _matches_type(project_override, expected_type):
        return project_override

    kind = _project_kind(project_config)
    kind_override = KIND_OVERRIDES.get(kind, {}).get(lint_name, {}).get(threshold_name)
    if _matches_type(kind_override, expected_type):
        return kind_override

    return default


def _expected_type(default: Any) -> type | tuple[type, ...] | None:
    """Return the type a config override must match for `default`."""
    if default is None:
        return None
    if isinstance(default, bool):
        return bool
    if isinstance(default, int):
        # Accept int OR float for int defaults (e.g. `8` or `8.0`); reject
        # bool because bool is a subclass of int and would otherwise pass.
        return (int, float)
    if isinstance(default, float):
        return (int, float)
    return type(default)


def _matches_type(value: Any, expected: type | tuple[type, ...] | None) -> bool:
    """True iff `value` is non-None AND matches `expected` (with bool exclusion)."""
    if value is None:
        return False
    if expected is None:
        # Default is itself None — accept any non-None value verbatim.
        return True
    if isinstance(value, bool) and bool not in (
        expected if isinstance(expected, tuple) else (expected,)
    ):
        return False
    return isinstance(value, expected)


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

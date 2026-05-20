"""Runtime configuration resolver.

Loads daemon-wide tunables for the monitor, queue runner, and PR
watcher. Mirrors the precedence chain in
:mod:`tripwire.core.spawn_config` but with a simpler three-layer
hierarchy (no per-agent or per-session layer — runtime config is
daemon-wide, not per-instance):

1. shipped ``templates/runtime/defaults.yaml`` (framework floor)
2. ``<project>/.tripwire/runtime/defaults.yaml`` (project file override)
3. ``project.yaml.runtime`` (project inline override)

The final layer is validated against :class:`RuntimeDefaults`. Missing
required fields raise ``ValidationError`` rather than silently filling
from Python defaults — this is the "no hardcoded defaults in Python"
principle from v0.14.0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tripwire.models.runtime import RuntimeDefaults


def _shipped_path() -> Path:
    """Path to the shipped runtime defaults YAML."""
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "runtime" / "defaults.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``override`` onto ``base``. ``override`` wins per-key.

    Same shape as :func:`tripwire.core.spawn_config._deep_merge` — kept
    standalone here so runtime config doesn't depend on the spawn module.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_resolved_runtime_config(project_dir: Path) -> RuntimeDefaults:
    """Resolve runtime config. project.yaml.runtime > project-file > default."""
    base: dict[str, Any] = (
        yaml.safe_load(_shipped_path().read_text(encoding="utf-8")) or {}
    )

    # 2. Project file override
    file_override = project_dir / ".tripwire" / "runtime" / "defaults.yaml"
    if file_override.is_file():
        override = yaml.safe_load(file_override.read_text(encoding="utf-8")) or {}
        base = _deep_merge(base, override)

    # 3. project.yaml inline
    try:
        from tripwire.core.store import load_project

        project = load_project(project_dir)
    except Exception:
        project = None
    if project is not None:
        inline = getattr(project, "runtime", None)
        if isinstance(inline, dict) and inline:
            base = _deep_merge(base, inline)

    return RuntimeDefaults.model_validate(base)

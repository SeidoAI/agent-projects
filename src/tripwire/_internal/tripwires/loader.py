"""Registry loader for tripwires.

Loads built-in tripwires from ``manifest.yaml`` next to this module
and merges in any project-local extras declared in
``project.yaml.tripwires.extra``. Returns a dict keyed by lifecycle
event whose values are lists of instantiated tripwires.

The whole-project disable (``tripwires.enabled: false``) is enforced
here — a disabled project gets an empty registry, which fans out to a
no-op everywhere.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from tripwire._internal.tripwires import Tripwire

if TYPE_CHECKING:
    from tripwire.models.project import ProjectConfig


_MANIFEST_PATH = Path(__file__).parent / "manifest.yaml"


def load_registry(project_dir: Path) -> dict[str, list[Tripwire]]:
    """Build the per-event tripwire registry for a project.

    Returns ``{}`` when ``project.yaml.tripwires.enabled`` is False.
    Otherwise loads the bundled manifest and appends any project-local
    extras. Per-session opt-out is enforced at fire time, not here.
    """
    from tripwire.core.store import load_project

    project = load_project(project_dir)
    cfg = _read_tripwires_block(project)

    if cfg.get("enabled", True) is False:
        return {}

    registry: dict[str, list[Tripwire]] = {}
    builtin = _load_manifest(_MANIFEST_PATH)
    for event, entries in builtin.items():
        registry.setdefault(event, [])
        for entry in entries:
            tw = _instantiate(entry, project_dir=project_dir)
            registry[event].append(tw)

    extras = cfg.get("extra", []) or []
    for entry in extras:
        if not isinstance(entry, dict):
            continue
        event = entry.get("fires_on") or entry.get("event")
        if not isinstance(event, str):
            continue
        registry.setdefault(event, [])
        tw = _instantiate(entry, project_dir=project_dir)
        registry[event].append(tw)

    return registry


def _load_manifest(path: Path) -> dict[str, list[dict]]:
    """Parse the bundled manifest. Empty event keys map to empty lists."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, list[dict]] = {}
    for event, entries in raw.items():
        if entries is None:
            out[event] = []
            continue
        if not isinstance(entries, list):
            raise ValueError(
                f"manifest entry for {event!r} must be a list, got {type(entries)!r}"
            )
        out[event] = [e for e in entries if isinstance(e, dict)]
    return out


def _instantiate(entry: dict, *, project_dir: Path) -> Tripwire:
    """Resolve and instantiate one tripwire entry.

    ``entry`` may name a dotted Python path (``class:`` or ``cls:``) or
    point at a project-local Python file (``module:``). Local modules
    are loaded via ``importlib.util.spec_from_file_location`` and the
    declared ``id`` is used to find the class within the module.
    """
    cls_path = entry.get("class") or entry.get("cls")
    module_path = entry.get("module")

    if cls_path:
        module_name, _, class_name = cls_path.rpartition(".")
        if not module_name or not class_name:
            raise ValueError(f"invalid class path: {cls_path!r}")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
    elif module_path:
        # Project-local module: relative paths resolve against project_dir.
        path = Path(module_path)
        if not path.is_absolute():
            path = (project_dir / path).resolve()
        spec = importlib.util.spec_from_file_location(
            f"_tripwire_extra_{path.stem}", path
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load module from {path!r}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = _find_tripwire_class(module, entry.get("id"))
    else:
        raise ValueError(f"tripwire entry must declare `class` or `module`: {entry!r}")

    if not isinstance(cls, type) or not issubclass(cls, Tripwire):
        raise TypeError(f"{cls!r} is not a Tripwire subclass")

    instance = cls()
    return instance


def _find_tripwire_class(module: Any, declared_id: str | None) -> type[Tripwire]:
    """Find the (single) Tripwire subclass in a project-local module."""
    candidates = [
        v
        for v in vars(module).values()
        if isinstance(v, type) and issubclass(v, Tripwire) and v is not Tripwire
    ]
    if declared_id:
        for c in candidates:
            if getattr(c, "id", None) == declared_id:
                return c
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        f"could not resolve Tripwire class in {module!r} "
        f"(found {len(candidates)} candidate(s))"
    )


def _read_tripwires_block(project: ProjectConfig) -> dict:
    """Read the un-typed ``tripwires:`` block from ``project.yaml``.

    The :class:`ProjectConfig` model uses ``extra="forbid"``, so a new
    ``tripwires:`` field would have to be modelled to be readable via
    the typed surface. We instead added a tolerant typed
    ``ProjectTripwiresConfig`` field on the project model — see
    :mod:`tripwire.models.project`. This helper returns the field as a
    plain dict so ``fire_event`` and ``load_registry`` don't need to
    know the typed shape.
    """
    cfg = getattr(project, "tripwires", None)
    if cfg is None:
        return {}
    if hasattr(cfg, "model_dump"):
        return cfg.model_dump()
    if isinstance(cfg, dict):
        return cfg
    return {}

"""Registry loader for JIT prompts."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from tripwire._internal.jit_prompts import JitPrompt

if TYPE_CHECKING:
    from tripwire.models.project import ProjectConfig


_MANIFEST_PATH = Path(__file__).parent / "manifest.yaml"


def load_jit_prompt_registry(project_dir: Path) -> dict[str, list[JitPrompt]]:
    """Build the per-event JIT prompt registry for a project."""
    from tripwire.core.store import load_project

    project = load_project(project_dir)
    cfg = _read_jit_prompts_block(project)

    if cfg.get("enabled", True) is False:
        return {}

    registry: dict[str, list[JitPrompt]] = {}
    builtin = _load_manifest(_MANIFEST_PATH)
    for event, entries in builtin.items():
        registry.setdefault(event, [])
        for entry in entries:
            jit_prompt = _instantiate(entry, project_dir=project_dir)
            registry[event].append(jit_prompt)

    extras = cfg.get("extra", []) or []
    for entry in extras:
        if not isinstance(entry, dict):
            continue
        event = entry.get("fires_on") or entry.get("event")
        if not isinstance(event, str):
            continue
        registry.setdefault(event, [])
        jit_prompt = _instantiate(entry, project_dir=project_dir)
        registry[event].append(jit_prompt)

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


def _instantiate(entry: dict, *, project_dir: Path) -> JitPrompt:
    """Resolve and instantiate one JIT prompt entry."""
    cls_path = entry.get("class") or entry.get("cls")
    module_path = entry.get("module")

    if cls_path:
        module_name, _, class_name = cls_path.rpartition(".")
        if not module_name or not class_name:
            raise ValueError(f"invalid class path: {cls_path!r}")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
    elif module_path:
        path = Path(module_path)
        if not path.is_absolute():
            path = (project_dir / path).resolve()
        spec = importlib.util.spec_from_file_location(
            f"_jit_prompt_extra_{path.stem}", path
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load module from {path!r}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = _find_jit_prompt_class(module, entry.get("id"))
    else:
        raise ValueError(
            f"JIT prompt entry must declare `class` or `module`: {entry!r}"
        )

    if not isinstance(cls, type) or not issubclass(cls, JitPrompt):
        raise TypeError(f"{cls!r} is not a JitPrompt subclass")

    return cls()


def _find_jit_prompt_class(module: Any, declared_id: str | None) -> type[JitPrompt]:
    """Find the single JIT prompt subclass in a project-local module."""
    candidates = [
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, JitPrompt)
        and value is not JitPrompt
    ]
    if declared_id:
        for candidate in candidates:
            if getattr(candidate, "id", None) == declared_id:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        f"could not resolve JitPrompt class in {module!r} "
        f"(found {len(candidates)} candidate(s))"
    )


def _read_jit_prompts_block(project: ProjectConfig) -> dict:
    """Read the typed ``jit_prompts:`` block from ``project.yaml``."""
    cfg = getattr(project, "jit_prompts", None)
    if cfg is None:
        return {}
    if hasattr(cfg, "model_dump"):
        return cfg.model_dump()
    if isinstance(cfg, dict):
        return cfg
    return {}

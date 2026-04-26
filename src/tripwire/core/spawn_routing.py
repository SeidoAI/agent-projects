"""Resolve a session's ``task_kind`` to a ``(provider, model, effort)`` tuple.

The shipped routing table at ``src/tripwire/templates/spawn/routing.yaml``
maps a small set of named task kinds (e.g. ``lint_or_template_edit``,
``agentic_loop``) to a provider+model+effort tuple. A project may
override or add routes via
``<project_dir>/.tripwire/spawn/routing.yaml`` and may change the
``default:`` route name.

Why this exists: the v0.7.x batch ran every session on
``(opus, max)`` regardless of task complexity, blowing the weekly
quota. Routing lets a lint patch use ``(sonnet, low)`` while a gnarly
debug uses ``(opus, max)`` — same plan-driven workflow, right-sized
spend.

The session's resolution chain is:

1. ``session.spawn_config.task_kind`` picks a route name (the empty
   string falls back to ``default:`` from whichever file wins).
2. The project file's ``routes`` map deep-merges into the shipped
   ``routes`` map, with leaf-level replacement.
3. The project file's ``default:`` scalar (if present) replaces the
   shipped default.

Unknown ``task_kind`` (a non-empty string that resolves to no route)
raises :class:`UnknownTaskKindError`. Silent fallback hides typos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class UnknownTaskKindError(ValueError):
    """Raised when ``task_kind`` does not match any known route."""


@dataclass(frozen=True)
class RouteResolution:
    """Resolved route for a session's ``task_kind``."""

    task_kind: str
    provider: str
    model: str
    effort: str


def shipped_routing_path() -> Path:
    """Return the absolute path to the package's ``routing.yaml``."""
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "spawn" / "routing.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _merge_routes(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Combine the shipped + project routing tables.

    ``routes`` is merged key-by-key; a project entry replaces a shipped
    entry wholesale (we don't deep-merge inside an individual route to
    avoid leaving partially-defined entries). ``default`` from the
    override replaces the shipped scalar if present.
    """
    merged: dict[str, Any] = {
        "default": base.get("default", ""),
        "routes": dict(base.get("routes") or {}),
    }
    override_routes = override.get("routes") or {}
    if isinstance(override_routes, dict):
        for name, route in override_routes.items():
            if isinstance(route, dict):
                merged["routes"][name] = dict(route)
    if "default" in override and isinstance(override["default"], str):
        merged["default"] = override["default"]
    return merged


def _build_resolution(name: str, route: dict[str, Any]) -> RouteResolution:
    return RouteResolution(
        task_kind=name,
        provider=str(route.get("provider", "claude")),
        model=str(route.get("model", "")),
        effort=str(route.get("effort", "")),
    )


def resolve_route(task_kind: str, project_dir: Path) -> RouteResolution:
    """Return the ``(provider, model, effort)`` route for ``task_kind``.

    ``task_kind`` of ``""`` (or ``None``-equivalent empty) falls back
    to the resolved table's ``default:`` route name. A non-empty
    ``task_kind`` that does not match a known route raises
    :class:`UnknownTaskKindError`.
    """
    shipped = _load_yaml(shipped_routing_path())
    project = _load_yaml(project_dir / ".tripwire" / "spawn" / "routing.yaml")
    table = _merge_routes(shipped, project)

    routes = table.get("routes") or {}
    if not task_kind:
        default_name = table.get("default") or ""
        if not default_name or default_name not in routes:
            raise UnknownTaskKindError(
                f"routing.yaml has no usable default route "
                f"(default={default_name!r})"
            )
        return _build_resolution(default_name, routes[default_name])

    if task_kind not in routes:
        known = sorted(routes.keys())
        raise UnknownTaskKindError(
            f"task_kind {task_kind!r} not in routing table; "
            f"known routes: {', '.join(known)}"
        )
    return _build_resolution(task_kind, routes[task_kind])


__all__ = [
    "RouteResolution",
    "UnknownTaskKindError",
    "resolve_route",
    "shipped_routing_path",
]

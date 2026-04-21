"""Enum read service — list + get of project-level enum YAML files.

Surfaces the project's ``enums/*.yaml`` files in an API-friendly shape
for UI label + colour rendering. Supports both the structured
``values:`` form used by new projects and the legacy flat-list form
that early projects shipped.

Note: the ``tripwire.core.enum_loader`` dataclass uses ``EnumValue.id``,
but this service exposes ``EnumValue.value`` to match the API naming
convention. Callers that need the raw dataclass should import from the
core module directly; callers that need the API surface stay here.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from tripwire.core import paths

logger = logging.getLogger("tripwire.ui.services.enum_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class EnumValue(BaseModel):
    """One value within an enum — API shape.

    Uses ``value`` rather than ``id`` to match the route-level naming.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    value: str
    label: str
    color: str | None = None
    description: str | None = None


class EnumDescriptor(BaseModel):
    """A named enum with an ordered list of values."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str
    values: list[EnumValue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_label(value: str) -> str:
    """Canonical title-case label derived from an enum value."""
    return value.replace("_", " ").title()


def _coerce_value_entry(entry: object, source: Path) -> EnumValue | None:
    """Build an EnumValue from a single YAML entry.

    Returns ``None`` and logs a debug line when the entry is malformed —
    callers should skip malformed entries rather than crash.
    """
    if isinstance(entry, str):
        return EnumValue(value=entry, label=_default_label(entry), color=None)

    if not isinstance(entry, dict):
        logger.debug("enum_service: unexpected value entry in %s: %r", source, entry)
        return None

    # Structured form — accept `value` or legacy `id` as the key.
    raw_value = entry.get("value") or entry.get("id")
    if not raw_value:
        logger.debug(
            "enum_service: value entry missing id/value in %s: %r",
            source,
            entry,
        )
        return None

    value = str(raw_value)
    label = str(entry.get("label") or _default_label(value))
    color_raw = entry.get("color")
    color = str(color_raw) if color_raw is not None else None
    description_raw = entry.get("description")
    description = str(description_raw) if description_raw is not None else None

    # Log unknown fields at debug level — we don't silently eat typos.
    known = {"value", "id", "label", "color", "description"}
    for key in entry:
        if key not in known:
            logger.debug(
                "enum_service: unknown field %r in enum value %r at %s",
                key,
                value,
                source,
            )

    return EnumValue(value=value, label=label, color=color, description=description)


def _parse_enum_yaml(path: Path, name: str) -> EnumDescriptor:
    """Parse an enum YAML file into an :class:`EnumDescriptor`.

    Accepts:

    - **Flat list** — ``[todo, in_progress, done]`` at the top level.
    - **Structured** — ``{name?: ..., values: [{value|id, label?, color?,
      description?}, ...]}``.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if raw is None:
        return EnumDescriptor(name=name, values=[])

    # Flat list at the top-level — treat every item as a value.
    if isinstance(raw, list):
        values = [
            v for v in (_coerce_value_entry(e, path) for e in raw) if v is not None
        ]
        return EnumDescriptor(name=name, values=values)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Enum file {path} must be a YAML list or mapping, got {type(raw).__name__}"
        )

    # Structured form — require `values:` key OR accept top-level list under another key?
    # The spec says `values:`; anything else is a third format we don't invent.
    declared_name = str(raw.get("name", name))
    raw_values = raw.get("values", [])

    if not isinstance(raw_values, list):
        raise ValueError(
            f"Enum file {path} `values` must be a list, got {type(raw_values).__name__}"
        )

    values = [
        v for v in (_coerce_value_entry(e, path) for e in raw_values) if v is not None
    ]
    return EnumDescriptor(name=declared_name, values=values)


def _enums_dir(project_dir: Path) -> Path:
    return project_dir / paths.ENUMS_DIR


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_enums(project_dir: Path) -> dict[str, EnumDescriptor]:
    """Load every ``<project>/enums/*.yaml`` into a name → descriptor map.

    The map key is the filename stem (``issue_status.yaml`` → ``issue_status``).
    Files that fail to load are skipped with a warning log.
    """
    directory = _enums_dir(project_dir)
    if not directory.is_dir():
        return {}

    out: dict[str, EnumDescriptor] = {}
    for path in sorted(directory.glob("*.yaml")):
        name = path.stem
        try:
            out[name] = _parse_enum_yaml(path, name)
        except (yaml.YAMLError, ValueError) as exc:
            logger.warning("enum_service: skipping %s (%s)", path, exc)
    return out


def get_enum(project_dir: Path, name: str) -> EnumDescriptor:
    """Load a single enum by name.

    Raises :class:`FileNotFoundError` when the file is missing; routes
    translate to 404.
    """
    path = _enums_dir(project_dir) / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Enum not found: {path}")
    return _parse_enum_yaml(path, name)


__all__ = [
    "EnumDescriptor",
    "EnumValue",
    "get_enum",
    "list_enums",
]

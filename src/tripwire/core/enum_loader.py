"""Dynamic enum loading from `<project>/enums/`.

Enums are not hardcoded — they are YAML files in the project repo at
`<project>/enums/<name>.yaml`, copied from packaged defaults at
`templates/enums/` on `tripwire init`. After init, the project owns its
enums and can add states, rename labels, recolor for the UI, or remove states
it doesn't use.

This module loads the active enum YAMLs for a given project and returns a
structured representation. The validator (Step 3) uses the loaded enum to
check that every enum-typed field on every entity has a value present in
the active enum.

Field-type policy (post-KUI-110, v1 hardening): some Pydantic models now
use the upstream StrEnums directly as field types — notably
``AgentSession.status: SessionStatus`` — locking the upstream value set
at load time. The project-side YAML remains authoritative for labels,
colors, and any UI metadata, but the value set itself can no longer
drift from the upstream Python enum (drift raises ``ValidationError``
on load). Other entities (e.g. ``Issue``) keep the plain-``str`` field
type and rely on the validator's ``status_in_enum`` rules for
enforcement; for those, a project can still add a ``qa`` status
project-locally without the package having to know about it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tripwire.models.enums import DEFAULT_ENUMS

logger = logging.getLogger(__name__)

ENUMS_DIRNAME = "enums"


@dataclass(frozen=True)
class EnumValue:
    """One value within an enum (matches the YAML schema)."""

    id: str
    label: str
    color: str | None = None


@dataclass(frozen=True)
class LoadedEnum:
    """An enum as loaded from YAML (project) or built from a packaged StrEnum default."""

    name: str
    description: str | None
    values: tuple[EnumValue, ...]
    source: (
        str  # "project" if from <project>/enums/, "default" if from packaged defaults
    )

    def value_ids(self) -> tuple[str, ...]:
        return tuple(v.id for v in self.values)

    def is_valid(self, value: str) -> bool:
        return value in self.value_ids()


@dataclass
class EnumRegistry:
    """All enums active for one project, keyed by enum name (e.g. "issue_status")."""

    enums: dict[str, LoadedEnum] = field(default_factory=dict)

    def get(self, name: str) -> LoadedEnum | None:
        return self.enums.get(name)

    def is_valid(self, enum_name: str, value: str) -> bool:
        loaded = self.enums.get(enum_name)
        if loaded is None:
            return False
        return loaded.is_valid(value)

    def value_ids(self, enum_name: str) -> tuple[str, ...]:
        loaded = self.enums.get(enum_name)
        return loaded.value_ids() if loaded else ()


def _load_enum_yaml(path: Path, enum_name: str) -> LoadedEnum:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"Enum file {path} must be a YAML mapping, got {type(raw).__name__}"
        )
    values_raw = raw.get("values", [])
    if not isinstance(values_raw, list):
        raise ValueError(
            f"Enum file {path} `values` must be a list, got {type(values_raw).__name__}"
        )

    values: list[EnumValue] = []
    for entry in values_raw:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Enum file {path} value entry must be a mapping, got {type(entry).__name__}"
            )
        if "id" not in entry:
            raise ValueError(f"Enum file {path} value entry missing required `id`.")
        values.append(
            EnumValue(
                id=str(entry["id"]),
                label=str(entry.get("label", entry["id"])),
                color=entry.get("color"),
            )
        )

    return LoadedEnum(
        name=str(raw.get("name", enum_name)),
        description=raw.get("description"),
        values=tuple(values),
        source="project",
    )


def _package_template_enum_path(enum_name: str) -> Path:
    """Path to the enum YAML shipped inside the tripwire package."""
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "enums" / f"{enum_name}.yaml"


def _default_enum(enum_name: str) -> LoadedEnum | None:
    """Load the packaged default for an enum.

    Prefers the shipped YAML at `src/tripwire/templates/enums/<name>.yaml`
    (richer than StrEnum: carries labels, colors, descriptions). Falls back
    to the in-code StrEnum if no template ships.
    """
    pkg_path = _package_template_enum_path(enum_name)
    if pkg_path.is_file():
        loaded = _load_enum_yaml(pkg_path, enum_name)
        return LoadedEnum(
            name=loaded.name,
            description=loaded.description,
            values=loaded.values,
            source="default",
        )

    cls = DEFAULT_ENUMS.get(enum_name)
    if cls is None:
        return None
    values = tuple(
        EnumValue(id=member.value, label=member.value.replace("_", " ").title())
        for member in cls
    )
    return LoadedEnum(
        name=cls.__name__,
        description=cls.__doc__,
        values=values,
        source="default",
    )


def load_enum(project_dir: Path, enum_name: str) -> list[str]:
    """Load one enum's value IDs, preferring project override over packaged default.

    Lookup order:
      1. `<project_dir>/enums/<enum_name>.yaml` (project override)
      2. `src/tripwire/templates/enums/<enum_name>.yaml` (packaged default)
      3. `DEFAULT_ENUMS[enum_name]` (StrEnum fallback, for enums without a YAML
         template — e.g. legacy enums)

    Raises FileNotFoundError if none of the above exist.
    """
    project_path = project_dir / ENUMS_DIRNAME / f"{enum_name}.yaml"
    if project_path.is_file():
        return list(_load_enum_yaml(project_path, enum_name).value_ids())

    pkg_path = _package_template_enum_path(enum_name)
    if pkg_path.is_file():
        return list(_load_enum_yaml(pkg_path, enum_name).value_ids())

    default = _default_enum(enum_name)
    if default is not None:
        return list(default.value_ids())

    raise FileNotFoundError(
        f"No enum definition found for {enum_name!r} (looked in project override, "
        f"packaged template, and StrEnum defaults)."
    )


def load_enums(project_dir: Path) -> EnumRegistry:
    """Load all active enums for a project.

    For each known enum name, prefer `<project>/enums/<name>.yaml` if present;
    otherwise fall back to the packaged default StrEnum class. The registry
    returned can be queried for valid values without further IO.
    """
    registry = EnumRegistry()
    enums_dir = project_dir / ENUMS_DIRNAME

    for enum_name in DEFAULT_ENUMS:
        project_path = enums_dir / f"{enum_name}.yaml"
        if project_path.exists():
            registry.enums[enum_name] = _load_enum_yaml(project_path, enum_name)
            logger.debug(
                "enum_loader: loaded %s from project (%s)", enum_name, project_path
            )
        else:
            default = _default_enum(enum_name)
            if default is not None:
                registry.enums[enum_name] = default
                logger.debug("enum_loader: loaded %s from packaged default", enum_name)

    # Also load any project-defined enums that don't correspond to a packaged
    # default — projects can add new enums entirely.
    if enums_dir.is_dir():
        for path in sorted(enums_dir.glob("*.yaml")):
            enum_name = path.stem
            if enum_name in registry.enums:
                continue
            registry.enums[enum_name] = _load_enum_yaml(path, enum_name)
            logger.info(
                "enum_loader: loaded project-only enum %s from %s", enum_name, path
            )

    logger.info(
        "enum_loader: loaded %d enums for project at %s",
        len(registry.enums),
        project_dir,
    )
    return registry

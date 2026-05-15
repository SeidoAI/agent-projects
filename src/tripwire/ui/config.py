"""User-scoped configuration loader for ``~/.tripwire/config.yaml``.

Reads the YAML file into a pydantic ``UserConfig`` model. A missing file
returns defaults without error; invalid content logs a warning and falls
back to defaults.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger("tripwire.ui.config")


def _default_config_path() -> Path:
    """Return ``~/.tripwire/config.yaml`` (or ``$TRIPWIRE_CONFIG_DIR/config.yaml``
    when the env var is set).

    The override exists so tests can redirect the path to ``tmp_path``
    via ``monkeypatch.setenv``. Computed lazily so a test's ``setenv``
    is honoured even after this module is imported.
    """
    override = os.environ.get("TRIPWIRE_CONFIG_DIR")
    root = Path(override) if override else Path.home() / ".tripwire"
    return root / "config.yaml"


class UserConfig(BaseModel):
    """Schema for ``~/.tripwire/config.yaml``."""

    project_roots: list[Path] = Field(default_factory=list)
    workspace_roots: list[Path] = Field(default_factory=list)
    default_project: Path | None = None
    port: int = Field(default=8000, ge=1, le=65535)
    open_browser: bool = True

    @field_validator("project_roots", "workspace_roots", mode="before")
    @classmethod
    def _expand_roots(cls, v: object) -> object:
        if isinstance(v, list):
            return [Path(p).expanduser() for p in v]
        return v

    @field_validator("default_project", mode="before")
    @classmethod
    def _expand_default(cls, v: object) -> object:
        if v is not None:
            return Path(v).expanduser()
        return v


def load_user_config(path: Path | None = None) -> UserConfig:
    """Load user config from *path* (default ``~/.tripwire/config.yaml``).

    Returns ``UserConfig()`` with defaults when the file is missing or
    contains invalid content.
    """
    config_path = path if path is not None else _default_config_path()

    if not config_path.exists():
        return UserConfig()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in %s: %s", config_path, exc)
        return UserConfig()

    if raw is None:
        return UserConfig()

    if not isinstance(raw, dict):
        logger.warning(
            "Expected a YAML mapping in %s, got %s", config_path, type(raw).__name__
        )
        return UserConfig()

    try:
        config = UserConfig.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Invalid config in %s: %s", config_path, exc)
        return UserConfig()

    for root in config.project_roots:
        if not root.exists():
            logger.warning("project root does not exist: %s", root)
    for root in config.workspace_roots:
        if not root.exists():
            logger.warning("workspace root does not exist: %s", root)

    return config


def save_user_config(config: UserConfig, path: Path | None = None) -> Path:
    """Write *config* to *path* (default ``~/.tripwire/config.yaml``).

    Creates the parent directory if needed. Returns the path written to.

    Uses ``exclude_defaults=True`` so a hand-crafted minimal config (just
    ``project_roots: [...]``) doesn't bloat with default-valued fields
    (``port: 8000``, ``open_browser: true``, ``workspace_roots: []``)
    on every CLI write. Round-trips cleanly because ``load_user_config``
    re-applies defaults at read time.
    """
    config_path = path if path is not None else _default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    config_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return config_path

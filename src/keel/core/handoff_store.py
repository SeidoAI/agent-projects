"""Read/write handoff.yaml files.

Mirrors the pattern of session_store.py. Frontmatter-only YAML;
body is ignored.
"""

from __future__ import annotations

from pathlib import Path

from keel.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from keel.core.paths import handoff_path
from keel.models.handoff import SessionHandoff


def handoff_exists(project_dir: Path, session_id: str) -> bool:
    return handoff_path(project_dir, session_id).is_file()


def load_handoff(project_dir: Path, session_id: str) -> SessionHandoff | None:
    path = handoff_path(project_dir, session_id)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, _body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    return SessionHandoff.model_validate(frontmatter)


def save_handoff(project_dir: Path, handoff: SessionHandoff) -> None:
    path = handoff_path(project_dir, handoff.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = handoff.model_dump(mode="json", exclude_none=True)
    text = serialize_frontmatter_body(data, "")
    path.write_text(text, encoding="utf-8")

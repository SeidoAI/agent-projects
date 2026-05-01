"""File-based CRUD for concept nodes.

Concept nodes live at `<project>/nodes/<id>.yaml`. The filename matches
the node id (slug), and the file format is YAML frontmatter + optional
Markdown body — the same format as issues, parsed via `core/parser.py`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tripwire.core import paths
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from tripwire.models.node import ConceptNode

# Backwards-compatible alias — prefer importing from `tripwire.core.paths`.
NODES_DIRNAME = paths.NODES_DIR


def node_path(project_dir: Path, node_id: str) -> Path:
    return paths.node_path(project_dir, node_id)


def load_node(project_dir: Path, node_id: str) -> ConceptNode:
    """Load `<project_dir>/nodes/<node_id>.yaml` into a ConceptNode."""
    path = node_path(project_dir, node_id)
    if not path.exists():
        raise FileNotFoundError(f"Concept node file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    return ConceptNode.model_validate({**frontmatter, "body": body})


def save_node(
    project_dir: Path, node: ConceptNode, *, update_cache: bool = True
) -> None:
    """Serialise a ConceptNode to `<project_dir>/nodes/<id>.yaml`.

    Sets `updated_at` to now if it is unset. If `update_cache` is True
    (the default), invalidates the graph cache for this file. Batch
    writers can pass `update_cache=False` and invalidate once at the end.
    """
    if node.updated_at is None:
        node.updated_at = datetime.now()

    path = node_path(project_dir, node.id)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = node.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    # KUI-126 / A1: omit `version` when it equals the default (1). This
    # implements the v0.9 "no migration step" semantics — existing
    # files don't sprout the field until a real contract bump.
    if data.get("version") == 1:
        data.pop("version", None)
    text = serialize_frontmatter_body(data, node.body)
    path.write_text(text, encoding="utf-8")

    if update_cache:
        from tripwire.core.graph.cache import update_cache_for_file

        update_cache_for_file(project_dir, str(path.relative_to(project_dir)))


def list_nodes(project_dir: Path) -> list[ConceptNode]:
    """Load every node file under `<project_dir>/nodes/`."""
    nodes_dir = paths.nodes_dir(project_dir)
    if not nodes_dir.is_dir():
        return []
    nodes: list[ConceptNode] = []
    for path in sorted(nodes_dir.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter_body(text)
        nodes.append(ConceptNode.model_validate({**frontmatter, "body": body}))
    return nodes


def node_exists(project_dir: Path, node_id: str) -> bool:
    return node_path(project_dir, node_id).exists()


def delete_node(project_dir: Path, node_id: str) -> None:
    """Delete a concept node file. No-op if the file does not exist."""
    path = node_path(project_dir, node_id)
    if path.exists():
        path.unlink()

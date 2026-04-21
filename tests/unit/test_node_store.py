"""Unit tests for `core/node_store.py` (ConceptNode CRUD)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.node_store import (
    delete_node,
    list_nodes,
    load_node,
    node_exists,
    save_node,
)
from tripwire.models import ConceptNode, NodeSource


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "nodes").mkdir(parents=True)
    return tmp_path


def make_node(node_id: str = "user-model") -> ConceptNode:
    return ConceptNode(
        id=node_id,
        type="model",
        name="User",
        description="The user model",
        source=NodeSource(
            repo="SeidoAI/web-app-backend",
            path="src/models/user.py",
            lines=(12, 45),
            branch="test",
            content_hash="sha256:abc",
        ),
        related=["auth-endpoint"],
        tags=["auth"],
        body="## Description\n\nThe user model holds [[auth-endpoint]] credentials.\n",
    )


class TestNodeStore:
    def test_save_and_load_node(self, project_dir: Path) -> None:
        node = make_node()
        save_node(project_dir, node)
        loaded = load_node(project_dir, "user-model")

        assert loaded.uuid == node.uuid
        assert loaded.id == "user-model"
        assert loaded.source is not None
        assert loaded.source.lines == (12, 45)
        assert loaded.related == ["auth-endpoint"]
        assert "[[auth-endpoint]]" in loaded.body

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        save_node(tmp_path, make_node())
        assert (tmp_path / "nodes" / "user-model.yaml").exists()

    def test_load_missing_node_raises(self, project_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_node(project_dir, "nope")

    def test_save_sets_updated_at_if_unset(self, project_dir: Path) -> None:
        node = make_node()
        assert node.updated_at is None
        save_node(project_dir, node)
        assert node.updated_at is not None

    def test_list_nodes_empty(self, project_dir: Path) -> None:
        assert list_nodes(project_dir) == []

    def test_list_nodes_returns_all(self, project_dir: Path) -> None:
        save_node(project_dir, make_node("user-model"))
        save_node(project_dir, make_node("auth-endpoint"))
        save_node(project_dir, make_node("config-jwt"))
        loaded = list_nodes(project_dir)
        assert len(loaded) == 3
        assert {n.id for n in loaded} == {"user-model", "auth-endpoint", "config-jwt"}

    def test_node_exists(self, project_dir: Path) -> None:
        assert not node_exists(project_dir, "user-model")
        save_node(project_dir, make_node())
        assert node_exists(project_dir, "user-model")

    def test_delete_node(self, project_dir: Path) -> None:
        save_node(project_dir, make_node())
        assert node_exists(project_dir, "user-model")
        delete_node(project_dir, "user-model")
        assert not node_exists(project_dir, "user-model")

    def test_delete_nonexistent_is_noop(self, project_dir: Path) -> None:
        # Should not raise
        delete_node(project_dir, "nope")

    def test_uuid_first_in_yaml(self, project_dir: Path) -> None:
        save_node(project_dir, make_node())
        raw = (project_dir / "nodes" / "user-model.yaml").read_text()
        assert raw.startswith("---\nuuid:")

    def test_node_without_source_round_trip(self, project_dir: Path) -> None:
        # A `planned` node has no source.
        planned = ConceptNode(
            id="refresh-endpoint",
            type="endpoint",
            name="POST /auth/refresh",
            status="planned",
        )
        save_node(project_dir, planned)
        loaded = load_node(project_dir, "refresh-endpoint")
        assert loaded.source is None
        assert loaded.status == "planned"

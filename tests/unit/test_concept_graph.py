"""Unit tests for `core/graph/concept.py`."""

from __future__ import annotations

from pathlib import Path

from tripwire.core.graph.cache import full_rebuild
from tripwire.core.graph.concept import (
    build_full_graph,
    orphan_issues,
    orphan_nodes,
)
from tripwire.core.node_store import save_node
from tripwire.core.store import save_issue, save_project
from tripwire.models import (
    ConceptNode,
    Issue,
    ProjectConfig,
    RepoEntry,
)


def setup_project(tmp_path: Path) -> Path:
    save_project(
        tmp_path,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"SeidoAI/x": RepoEntry()},
        ),
    )
    return tmp_path


def make_issue_file(project_dir: Path, key: str, body: str = "", **kw: object) -> None:
    save_issue(
        project_dir,
        Issue(
            id=key,
            title=f"Test {key}",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body=body,
            **kw,  # type: ignore[arg-type]
        ),
    )


def make_node_file(project_dir: Path, node_id: str, **kw: object) -> None:
    save_node(
        project_dir,
        ConceptNode(
            id=node_id,
            type=kw.get("node_type", "model"),  # type: ignore[arg-type]
            name=kw.get("name", node_id),  # type: ignore[arg-type]
            status="active",
            related=kw.get("related", []),  # type: ignore[arg-type]
        ),
    )


class TestBuildFullGraph:
    def test_empty_project(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        full_rebuild(tmp_path)
        result = build_full_graph(tmp_path)
        assert result.nodes == []
        assert result.edges == []
        assert result.orphans == []

    def test_issue_and_node(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        make_node_file(tmp_path, "user-model")
        make_issue_file(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        full_rebuild(tmp_path)

        result = build_full_graph(tmp_path)
        node_ids = {n.id for n in result.nodes}
        assert node_ids == {"TST-1", "user-model"}

        kinds = {n.id: n.kind for n in result.nodes}
        assert kinds["TST-1"] == "issue"
        assert kinds["user-model"] == "node"

        # Edge from TST-1 to user-model
        ref_edges = [e for e in result.edges if e.type == "references"]
        assert any(e.from_id == "TST-1" and e.to_id == "user-model" for e in ref_edges)

    def test_orphan_detection(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        make_node_file(tmp_path, "orphan-node")
        make_issue_file(tmp_path, "TST-1", body="## Context\nno refs\n")
        full_rebuild(tmp_path)

        result = build_full_graph(tmp_path)
        # Both have no edges, so both are orphans
        assert "orphan-node" in result.orphans
        assert "TST-1" in result.orphans

    def test_fallback_scan_without_cache(self, tmp_path: Path) -> None:
        """If no cache exists, build_full_graph should still work via scan fallback."""
        setup_project(tmp_path)
        make_node_file(tmp_path, "user-model")
        make_issue_file(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        # Note: no full_rebuild call

        result = build_full_graph(tmp_path)
        node_ids = {n.id for n in result.nodes}
        assert node_ids == {"TST-1", "user-model"}

    def test_node_metadata_from_cache(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        make_node_file(
            tmp_path,
            "user-model",
            node_type="model",
            name="User (Firestore)",
        )
        full_rebuild(tmp_path)

        result = build_full_graph(tmp_path)
        user_model = next(n for n in result.nodes if n.id == "user-model")
        assert user_model.type == "model"
        assert user_model.label == "User (Firestore)"
        assert user_model.status == "active"


class TestOrphanHelpers:
    def test_orphan_nodes_only(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        make_node_file(tmp_path, "orphan-node")
        make_node_file(tmp_path, "connected-node")
        make_issue_file(tmp_path, "TST-1", body="## Context\n[[connected-node]]\n")
        full_rebuild(tmp_path)

        orphans = orphan_nodes(tmp_path)
        assert orphans == ["orphan-node"]

    def test_orphan_issues_only(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        make_node_file(tmp_path, "user-model")
        make_issue_file(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        make_issue_file(tmp_path, "TST-2", body="## Context\nNo refs.\n")
        full_rebuild(tmp_path)

        orphans = orphan_issues(tmp_path)
        assert orphans == ["TST-2"]

"""Unit tests for `core/graph_cache.py`.

Covers:
- load_index / save_index round-trip
- Full rebuild on a fresh project
- Incremental update for: new file, modified file, deleted file
- Derived table correctness (by_name, by_type, referenced_by, blocks)
- ensure_fresh dispatches full vs incremental correctly
- Equivalence: full rebuild vs incremental updates produce the same cache
- Cache invalidation on version mismatch
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from tripwire.core.graph_cache import (
    CACHE_VERSION,
    INDEX_REL_PATH,
    ensure_fresh,
    full_rebuild,
    load_index,
    save_index,
    update_cache_for_file,
)
from tripwire.core.node_store import save_node
from tripwire.core.store import save_issue, save_project
from tripwire.models import (
    ConceptNode,
    Issue,
    NodeSource,
    ProjectConfig,
    RepoEntry,
)
from tripwire.models.graph import GraphIndex

# ============================================================================
# Helpers
# ============================================================================


def make_project(tmp_path: Path) -> Path:
    """Minimal project with one repo registered."""
    save_project(
        tmp_path,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"SeidoAI/test-repo": RepoEntry()},
            next_issue_number=1,
        ),
    )
    return tmp_path


def make_issue(
    project_dir: Path,
    key: str,
    *,
    blocked_by: list[str] | None = None,
    body: str | None = None,
    parent: str | None = None,
) -> None:
    issue = Issue(
        id=key,
        title=f"Test {key}",
        status="todo",
        priority="medium",
        executor="ai",
        verifier="required",
        blocked_by=blocked_by or [],
        parent=parent,
        body=body or f"Body for {key}.\n",
    )
    # These tests exercise the graph cache's own dispatcher logic
    # (ensure_fresh, full_rebuild). Skip the automatic cache invalidation
    # on save so the tests see the pre-invalidation state.
    save_issue(project_dir, issue, update_cache=False)


def make_node(
    project_dir: Path,
    node_id: str,
    *,
    node_type: str = "model",
    related: list[str] | None = None,
    name: str | None = None,
) -> None:
    node = ConceptNode(
        id=node_id,
        type=node_type,
        name=name or node_id.replace("-", " ").title(),
        status="active",
        related=related or [],
        source=NodeSource(
            repo="SeidoAI/test-repo",
            path=f"src/{node_id}.py",
            lines=(1, 10),
            content_hash="sha256:abc",
        ),
    )
    save_node(project_dir, node, update_cache=False)


# ============================================================================
# Load / save
# ============================================================================


class TestLoadSave:
    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_index(tmp_path) is None

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        cache = GraphIndex(version=CACHE_VERSION)
        save_index(tmp_path, cache)
        loaded = load_index(tmp_path)
        assert loaded is not None
        assert loaded.version == CACHE_VERSION

    def test_save_uses_from_to_aliases(self, tmp_path: Path) -> None:
        """GraphEdge in the YAML should use `from`/`to` keys, not `from_id`/`to_id`."""
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1", blocked_by=["TST-2"])
        make_issue(tmp_path, "TST-2")
        full_rebuild(tmp_path)
        raw = yaml.safe_load((tmp_path / INDEX_REL_PATH).read_text())
        edges = raw.get("edges", [])
        assert edges, "Expected at least one edge after full rebuild"
        for edge in edges:
            assert "from" in edge
            assert "to" in edge
            assert "from_id" not in edge
            assert "to_id" not in edge

    def test_version_mismatch_treated_as_missing(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        # Write a v1 cache
        (tmp_path / "graph").mkdir(exist_ok=True)
        (tmp_path / INDEX_REL_PATH).write_text(
            yaml.safe_dump({"version": 1, "files": {}})
        )
        assert load_index(tmp_path) is None

    def test_corrupt_yaml_treated_as_missing(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        (tmp_path / "graph").mkdir(exist_ok=True)
        (tmp_path / INDEX_REL_PATH).write_text("not: : : valid:\n")
        assert load_index(tmp_path) is None


# ============================================================================
# Full rebuild
# ============================================================================


class TestFullRebuild:
    def test_empty_project(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        cache = full_rebuild(tmp_path)
        assert cache.version == CACHE_VERSION
        assert cache.files == {}
        assert cache.edges == []
        assert cache.last_full_rebuild is not None

    def test_issues_and_nodes(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model")
        make_node(tmp_path, "auth-endpoint", node_type="endpoint")
        make_issue(
            tmp_path,
            "TST-1",
            body="## Context\nuses [[user-model]] and [[auth-endpoint]]\n",
        )
        cache = full_rebuild(tmp_path)

        assert len(cache.files) == 3
        assert "issues/TST-1/issue.yaml" in cache.files
        assert "nodes/user-model.yaml" in cache.files
        assert "nodes/auth-endpoint.yaml" in cache.files

        # Edges: TST-1 → user-model, TST-1 → auth-endpoint (both `references`)
        ref_edges = [e for e in cache.edges if e.type == "references"]
        assert len(ref_edges) == 2
        targets = {e.to_id for e in ref_edges}
        assert targets == {"user-model", "auth-endpoint"}

    def test_by_type_populated(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model", node_type="model")
        make_node(tmp_path, "business-model", node_type="model")
        make_node(tmp_path, "auth-endpoint", node_type="endpoint")
        cache = full_rebuild(tmp_path)

        assert sorted(cache.by_type["model"]) == ["business-model", "user-model"]
        assert cache.by_type["endpoint"] == ["auth-endpoint"]

    def test_by_name_populated(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model", name="User (Firestore)")
        cache = full_rebuild(tmp_path)
        assert cache.by_name["User (Firestore)"] == "user-model"

    def test_referenced_by_populated(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model")
        make_issue(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        make_issue(tmp_path, "TST-2", body="## Context\n[[user-model]]\n")
        cache = full_rebuild(tmp_path)
        assert sorted(cache.referenced_by["user-model"]) == ["TST-1", "TST-2"]

    def test_blocks_computed_from_blocked_by(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        make_issue(tmp_path, "TST-2", blocked_by=["TST-1"])
        make_issue(tmp_path, "TST-3", blocked_by=["TST-1"])
        cache = full_rebuild(tmp_path)
        tst1_fp = cache.files["issues/TST-1/issue.yaml"]
        assert sorted(tst1_fp.blocks) == ["TST-2", "TST-3"]

    def test_related_edges(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "node-a", related=["node-b"])
        make_node(tmp_path, "node-b", related=["node-a"])
        cache = full_rebuild(tmp_path)
        related_edges = [e for e in cache.edges if e.type == "related"]
        assert len(related_edges) == 2  # a→b and b→a


# ============================================================================
# Incremental update
# ============================================================================


class TestIncrementalUpdate:
    def test_add_new_issue(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        full_rebuild(tmp_path)

        make_node(tmp_path, "user-model")
        make_issue(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")

        update_cache_for_file(tmp_path, "nodes/user-model.yaml")
        update_cache_for_file(tmp_path, "issues/TST-1/issue.yaml")

        cache = load_index(tmp_path)
        assert cache is not None
        assert "issues/TST-1/issue.yaml" in cache.files
        assert "nodes/user-model.yaml" in cache.files
        ref_edges = [e for e in cache.edges if e.type == "references"]
        assert len(ref_edges) == 1

    def test_modify_issue_removes_old_edges(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "node-a")
        make_node(tmp_path, "node-b")
        make_issue(tmp_path, "TST-1", body="## Context\n[[node-a]]\n")
        full_rebuild(tmp_path)

        # Rewrite the issue to point at node-b instead of node-a
        make_issue(tmp_path, "TST-1", body="## Context\n[[node-b]]\n")
        update_cache_for_file(tmp_path, "issues/TST-1/issue.yaml")

        cache = load_index(tmp_path)
        assert cache is not None
        ref_targets = {
            e.to_id
            for e in cache.edges
            if e.type == "references" and e.from_id == "TST-1"
        }
        assert ref_targets == {"node-b"}

    def test_delete_issue(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model")
        make_issue(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        full_rebuild(tmp_path)

        (tmp_path / "issues" / "TST-1" / "issue.yaml").unlink()
        result = update_cache_for_file(tmp_path, "issues/TST-1/issue.yaml")
        assert result is True

        cache = load_index(tmp_path)
        assert cache is not None
        assert "issues/TST-1/issue.yaml" not in cache.files
        # No edges should remain for the deleted issue.
        assert not any(e.from_id == "TST-1" for e in cache.edges)

    def test_delete_removes_from_referenced_by(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model")
        make_issue(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        make_issue(tmp_path, "TST-2", body="## Context\n[[user-model]]\n")
        full_rebuild(tmp_path)

        (tmp_path / "issues" / "TST-1" / "issue.yaml").unlink()
        update_cache_for_file(tmp_path, "issues/TST-1/issue.yaml")

        cache = load_index(tmp_path)
        assert cache is not None
        assert cache.referenced_by.get("user-model") == ["TST-2"]

    def test_update_unrelated_file_is_noop(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        full_rebuild(tmp_path)
        # Files outside issues/ and nodes/ should be ignored entirely.
        assert update_cache_for_file(tmp_path, "docs/README.md") is False

    def test_blocks_updates_incrementally(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        make_issue(tmp_path, "TST-2", blocked_by=["TST-1"])
        full_rebuild(tmp_path)

        # Modify TST-2 to no longer be blocked by TST-1
        make_issue(tmp_path, "TST-2", blocked_by=[])
        update_cache_for_file(tmp_path, "issues/TST-2/issue.yaml")

        cache = load_index(tmp_path)
        assert cache is not None
        assert cache.files["issues/TST-1/issue.yaml"].blocks == []


# ============================================================================
# ensure_fresh
# ============================================================================


class TestEnsureFresh:
    def test_first_call_does_full_rebuild(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        result = ensure_fresh(tmp_path)
        assert result is True
        cache = load_index(tmp_path)
        assert cache is not None
        assert cache.last_full_rebuild is not None

    def test_second_call_noop_when_nothing_changed(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        ensure_fresh(tmp_path)
        second = ensure_fresh(tmp_path)
        assert second is False

    def test_detects_new_file(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        ensure_fresh(tmp_path)

        make_issue(tmp_path, "TST-2")
        # Bump mtime a hair so the check picks it up on fast filesystems
        time.sleep(0.01)
        result = ensure_fresh(tmp_path)
        assert result is True
        cache = load_index(tmp_path)
        assert cache is not None
        assert "issues/TST-2/issue.yaml" in cache.files

    def test_detects_modified_file(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_node(tmp_path, "user-model")
        make_issue(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        ensure_fresh(tmp_path)

        # Modify the issue with a different reference. Force a later mtime
        # to avoid fast-filesystem races.
        time.sleep(0.01)
        make_node(tmp_path, "other-model")
        make_issue(tmp_path, "TST-1", body="## Context\n[[other-model]]\n")
        ensure_fresh(tmp_path)

        cache = load_index(tmp_path)
        assert cache is not None
        ref_targets = {
            e.to_id
            for e in cache.edges
            if e.from_id == "TST-1" and e.type == "references"
        }
        assert ref_targets == {"other-model"}

    def test_detects_deleted_file(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        ensure_fresh(tmp_path)

        (tmp_path / "issues" / "TST-1" / "issue.yaml").unlink()
        result = ensure_fresh(tmp_path)
        assert result is True
        cache = load_index(tmp_path)
        assert cache is not None
        assert "issues/TST-1/issue.yaml" not in cache.files

    def test_rebuild_on_missing_cache(self, tmp_path: Path) -> None:
        make_project(tmp_path)
        make_issue(tmp_path, "TST-1")
        ensure_fresh(tmp_path)
        # Delete the cache file
        (tmp_path / INDEX_REL_PATH).unlink()
        result = ensure_fresh(tmp_path)
        assert result is True
        assert load_index(tmp_path) is not None


# ============================================================================
# Equivalence: incremental path and full-rebuild path produce the same cache
# ============================================================================


class TestEquivalence:
    def test_incremental_matches_full_rebuild(self, tmp_path: Path) -> None:
        """Build up a project via incremental updates, then do a full rebuild,
        and confirm the two produce equivalent caches (same edges, same
        derived tables). This is the most important correctness property of
        the incremental update path."""
        make_project(tmp_path)

        # Build up project files in an arbitrary order.
        make_node(tmp_path, "user-model")
        make_node(tmp_path, "auth-endpoint", node_type="endpoint")
        make_node(tmp_path, "node-a", related=["node-b"])
        make_node(tmp_path, "node-b", related=["node-a"])
        make_issue(tmp_path, "TST-1", body="## Context\n[[user-model]]\n")
        make_issue(
            tmp_path,
            "TST-2",
            body="## Context\n[[auth-endpoint]]\n",
            blocked_by=["TST-1"],
        )
        make_issue(tmp_path, "TST-3", parent="TST-1")

        # Incremental path: update each file one by one
        for rel in [
            "nodes/user-model.yaml",
            "nodes/auth-endpoint.yaml",
            "nodes/node-a.yaml",
            "nodes/node-b.yaml",
            "issues/TST-1/issue.yaml",
            "issues/TST-2/issue.yaml",
            "issues/TST-3/issue.yaml",
        ]:
            update_cache_for_file(tmp_path, rel)

        incremental_cache = load_index(tmp_path)
        assert incremental_cache is not None

        # Full rebuild path
        full_cache = full_rebuild(tmp_path)

        # Compare the two caches — files, edges (as sets), and derived tables.
        assert set(incremental_cache.files.keys()) == set(full_cache.files.keys())

        def _edge_tuple(e: object) -> tuple:
            return (e.from_id, e.to_id, e.type, e.source_file)  # type: ignore[attr-defined]

        inc_edges = {_edge_tuple(e) for e in incremental_cache.edges}
        full_edges = {_edge_tuple(e) for e in full_cache.edges}
        assert inc_edges == full_edges

        assert incremental_cache.by_name == full_cache.by_name
        assert {k: sorted(v) for k, v in incremental_cache.by_type.items()} == {
            k: sorted(v) for k, v in full_cache.by_type.items()
        }
        assert {k: sorted(v) for k, v in incremental_cache.referenced_by.items()} == {
            k: sorted(v) for k, v in full_cache.referenced_by.items()
        }

        # Blocks lists should also match.
        for rel in incremental_cache.files:
            inc_blocks = sorted(incremental_cache.files[rel].blocks)
            full_blocks = sorted(full_cache.files[rel].blocks)
            assert inc_blocks == full_blocks, f"Blocks mismatch for {rel}"

"""Tests for tripwire.ui.services.node_service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripwire.ui.services.node_service import (
    FreshnessReport,
    NodeDetail,
    NodeSummary,
    ReverseRefsResult,
    check_all_freshness,
    get_node,
    list_nodes,
    reverse_refs,
)

# ---------------------------------------------------------------------------
# list_nodes
# ---------------------------------------------------------------------------


class TestListNodes:
    def test_empty_when_no_nodes(self, tmp_path_project: Path):
        assert list_nodes(tmp_path_project) == []

    def test_returns_all_by_default(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "alpha", type="model")
        save_test_node(tmp_path_project, "beta", type="decision")

        result = list_nodes(tmp_path_project)
        assert {n.id for n in result} == {"alpha", "beta"}
        assert all(isinstance(n, NodeSummary) for n in result)

    def test_filter_by_type(self, tmp_path_project: Path, save_test_node):
        save_test_node(tmp_path_project, "alpha", type="model")
        save_test_node(tmp_path_project, "beta", type="decision")

        result = list_nodes(tmp_path_project, node_type="decision")
        assert [n.id for n in result] == ["beta"]

    def test_filter_by_status(self, tmp_path_project: Path, save_test_node):
        save_test_node(tmp_path_project, "alpha", status="active")
        save_test_node(tmp_path_project, "beta", status="deprecated")

        result = list_nodes(tmp_path_project, status="deprecated")
        assert [n.id for n in result] == ["beta"]

    def test_ref_count_from_cache(
        self, tmp_path_project: Path, save_test_node, save_test_issue
    ):
        save_test_node(tmp_path_project, "user-model")
        # Default save_test_issue body contains [[user-model]]
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2")

        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)

        by_id = {n.id: n for n in list_nodes(tmp_path_project)}
        assert by_id["user-model"].ref_count == 2

    def test_ref_count_zero_when_no_cache(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "alpha")
        result = list_nodes(tmp_path_project)
        assert result[0].ref_count == 0

    def test_stale_filter_true(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "alpha")
        save_test_node(tmp_path_project, "beta")

        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)
        cache = graph_cache.load_index(tmp_path_project)
        assert cache is not None
        cache.stale_nodes = ["alpha"]
        graph_cache.save_index(tmp_path_project, cache)

        result = list_nodes(tmp_path_project, stale=True)
        assert [n.id for n in result] == ["alpha"]

    def test_stale_filter_false_excludes_stale(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "alpha")
        save_test_node(tmp_path_project, "beta")

        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)
        cache = graph_cache.load_index(tmp_path_project)
        assert cache is not None
        cache.stale_nodes = ["alpha"]
        graph_cache.save_index(tmp_path_project, cache)

        result = list_nodes(tmp_path_project, stale=False)
        assert [n.id for n in result] == ["beta"]


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


class TestGetNode:
    def test_returns_detail(self, tmp_path_project: Path, save_test_node):
        save_test_node(
            tmp_path_project,
            "user-model",
            description="The user model",
            tags=["auth"],
            related=["other-node"],
        )

        detail = get_node(tmp_path_project, "user-model")
        assert isinstance(detail, NodeDetail)
        assert detail.id == "user-model"
        assert detail.description == "The user model"
        assert detail.tags == ["auth"]
        assert detail.related == ["other-node"]
        assert detail.is_stale is False
        assert detail.source is None

    def test_returns_source_when_present(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(
            tmp_path_project,
            "user-model",
            source={
                "repo": "SeidoAI/web",
                "path": "src/user.py",
                "lines": (1, 10),
                "branch": "main",
                "content_hash": "sha256:abc",
            },
        )
        detail = get_node(tmp_path_project, "user-model")
        assert detail.source is not None
        assert detail.source.repo == "SeidoAI/web"
        assert detail.source.path == "src/user.py"
        assert detail.source.lines == (1, 10)

    def test_is_stale_from_cache(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "alpha")

        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)
        cache = graph_cache.load_index(tmp_path_project)
        assert cache is not None
        cache.stale_nodes = ["alpha"]
        graph_cache.save_index(tmp_path_project, cache)

        detail = get_node(tmp_path_project, "alpha")
        assert detail.is_stale is True

    def test_raises_on_invalid_slug(self, tmp_path_project: Path):
        with pytest.raises(ValueError, match="Invalid node id"):
            get_node(tmp_path_project, "Not-A-Slug")

    def test_raises_on_missing(self, tmp_path_project: Path):
        with pytest.raises(FileNotFoundError):
            get_node(tmp_path_project, "ghost")

    def test_round_trips_via_json(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(
            tmp_path_project,
            "user-model",
            source={
                "repo": "SeidoAI/web",
                "path": "src/user.py",
                "branch": "main",
            },
        )
        detail = get_node(tmp_path_project, "user-model")
        rebuilt = NodeDetail.model_validate(json.loads(detail.model_dump_json()))
        assert rebuilt == detail


# ---------------------------------------------------------------------------
# check_all_freshness
# ---------------------------------------------------------------------------


class TestCheckAllFreshness:
    def test_empty_project(self, tmp_path_project: Path):
        report = check_all_freshness(tmp_path_project)
        assert isinstance(report, FreshnessReport)
        assert report.nodes == []

    def test_source_missing_when_file_absent(
        self, tmp_path_project: Path, save_test_node, monkeypatch
    ):
        save_test_node(
            tmp_path_project,
            "user-model",
            source={
                "repo": "SeidoAI/web",
                "path": "src/user.py",
                "branch": "main",
            },
        )
        # Force the gh subprocess not to be found so fetch returns None.
        import tripwire.core.freshness as freshness_mod

        def _raise_missing(*a, **kw):
            raise FileNotFoundError("gh not found")

        monkeypatch.setattr(freshness_mod.subprocess, "run", _raise_missing)

        report = check_all_freshness(tmp_path_project)
        assert len(report.nodes) == 1
        assert report.nodes[0].id == "user-model"
        assert report.nodes[0].status == "source_missing"

    def test_current_when_hash_matches(
        self, tmp_path: Path, save_test_node, monkeypatch
    ):
        # Build a project whose project.yaml declares a repo with a local path
        # pointing at a tmp directory we control.
        repo_local = tmp_path / "local_repo"
        repo_local.mkdir()
        (repo_local / "file.py").write_text("hello\n", encoding="utf-8")

        from tripwire.core.freshness import hash_content

        h = hash_content("hello\n")

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(
            "name: p\nkey_prefix: P\nnext_issue_number: 1\nnext_session_number: 1\n"
            "repos:\n  SeidoAI/web:\n    local: " + str(repo_local) + "\n",
            encoding="utf-8",
        )
        for sub in ("issues", "nodes", "sessions"):
            (project_dir / sub).mkdir()

        save_test_node(
            project_dir,
            "user-model",
            source={
                "repo": "SeidoAI/web",
                "path": "file.py",
                "content_hash": h,
            },
        )

        report = check_all_freshness(project_dir)
        assert any(
            e.id == "user-model" and e.status == "current" for e in report.nodes
        )

    def test_skips_nodes_without_source(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "planned-node")
        report = check_all_freshness(tmp_path_project)
        assert report.nodes == []


# ---------------------------------------------------------------------------
# reverse_refs
# ---------------------------------------------------------------------------


class TestReverseRefs:
    def test_reads_from_cache(
        self, tmp_path_project: Path, save_test_node, save_test_issue
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)

        result = reverse_refs(tmp_path_project, "user-model")
        assert isinstance(result, ReverseRefsResult)
        assert result.node_id == "user-model"
        assert any(
            r.id == "TST-1" and r.kind == "issue" for r in result.referrers
        )

    def test_rebuilds_cache_lazily_when_absent(
        self, tmp_path_project: Path, save_test_node, save_test_issue
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        # Ensure no cache exists before the call.
        from tripwire.core import paths

        cache_path = paths.graph_cache_path(tmp_path_project)
        assert not cache_path.exists()

        # Per KUI-16 execution constraint, reverse_refs triggers one
        # rebuild of the missing cache. Verify the referrer is found AND
        # the cache file now exists on disk.
        result = reverse_refs(tmp_path_project, "user-model")
        assert any(r.id == "TST-1" for r in result.referrers)
        assert cache_path.exists()

    def test_falls_back_to_scan_when_rebuild_fails(
        self,
        tmp_path_project: Path,
        save_test_node,
        save_test_issue,
        monkeypatch,
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        # Monkeypatch ensure_fresh to raise — simulates a cache rebuild
        # that fails (lock timeout, disk IO error, etc). The service
        # should log and fall back to a filesystem scan.
        import tripwire.ui.services.node_service as svc
        from tripwire.core import graph_cache as gc

        def _boom(*a, **kw):
            raise OSError("simulated lock failure")

        monkeypatch.setattr(svc.graph_cache, "ensure_fresh", _boom)
        # Also assert the top-level load returns None so the fallback
        # actually fires.
        monkeypatch.setattr(svc.graph_cache, "load_index", lambda *a, **kw: None)

        result = reverse_refs(tmp_path_project, "user-model")
        assert any(r.id == "TST-1" for r in result.referrers)
        # Avoid lint complaint about unused import in tighter test.
        assert gc is svc.graph_cache

    def test_detects_node_to_node_referrer(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "target")
        save_test_node(
            tmp_path_project,
            "referrer",
            body="## Body\nSee [[target]] here.\n",
        )

        result = reverse_refs(tmp_path_project, "target")
        assert any(r.id == "referrer" and r.kind == "node" for r in result.referrers)

    def test_raises_on_invalid_slug(self, tmp_path_project: Path):
        with pytest.raises(ValueError):
            reverse_refs(tmp_path_project, "Not-A-Slug")

    def test_empty_referrers_for_unreferenced_node(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "lonely")
        result = reverse_refs(tmp_path_project, "lonely")
        assert result.referrers == []

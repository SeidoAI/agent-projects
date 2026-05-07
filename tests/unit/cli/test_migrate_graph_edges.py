"""Tests for `tripwire migrate graph-edges` — pre-v0.9 edge-type rewrite."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli
from tripwire.core import paths

runner = CliRunner()


def _make_project(root: Path) -> Path:
    """Build a minimal tripwire project skeleton at *root*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        "name: edge-mig\nkey_prefix: EM\n"
        "next_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    (root / "nodes").mkdir()
    return root


def _write_cache(project: Path, edges: list[dict]) -> Path:
    cache = project / paths.GRAPH_CACHE
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "files": {},
                "edges": edges,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return cache


def _read_edges(project: Path) -> list[dict]:
    cache = project / paths.GRAPH_CACHE
    data = yaml.safe_load(cache.read_text(encoding="utf-8"))
    return list(data.get("edges") or [])


class TestMigrateGraphEdges:
    def test_rewrites_legacy_strings(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        _write_cache(
            project,
            [
                {"from": "EM-1", "to": "user-model", "type": "references"},
                {"from": "EM-1", "to": "EM-2", "type": "blocked_by"},
                {"from": "n1", "to": "n2", "type": "related"},
                {"from": "EM-3", "to": "REQ-1", "type": "implements"},
            ],
        )

        result = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert "Rewrote 3 edge(s)" in result.output

        edges = _read_edges(project)
        types = [e["type"] for e in edges]
        # `references` → `refs`, `blocked_by` → `depends_on`,
        # `related` → `refs`, `implements` is already canonical.
        assert types == ["refs", "depends_on", "refs", "implements"]

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        _write_cache(
            project,
            [
                {"from": "EM-1", "to": "user-model", "type": "references"},
                {"from": "EM-1", "to": "EM-2", "type": "blocked_by"},
            ],
        )

        first = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(project)]
        )
        assert first.exit_code == 0, first.output
        assert "Rewrote 2 edge(s)" in first.output

        second = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(project)]
        )
        assert second.exit_code == 0, second.output
        assert "already canonical" in second.output
        assert "Rewrote" not in second.output

    def test_missing_cache_is_noop(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        # No cache file written.
        result = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        assert "nothing to migrate" in result.output.lower()
        # Still no cache afterward.
        assert not (project / paths.GRAPH_CACHE).exists()

    def test_dry_run_makes_no_changes(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        cache = _write_cache(
            project,
            [
                {"from": "EM-1", "to": "user-model", "type": "references"},
            ],
        )
        before = cache.read_text(encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "migrate",
                "graph-edges",
                "--project-dir",
                str(project),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "[dry-run]" in result.output
        # File untouched.
        assert cache.read_text(encoding="utf-8") == before

    def test_unknown_kinds_pass_through(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path / "p")
        _write_cache(
            project,
            [
                {"from": "EM-1", "to": "EM-2", "type": "future_kind"},
                {"from": "EM-1", "to": "user-model", "type": "references"},
            ],
        )

        result = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        edges = _read_edges(project)
        types = [e["type"] for e in edges]
        # Unknown kind survives untouched; legacy still rewritten.
        assert types == ["future_kind", "refs"]

    def test_rejects_non_project_dir(self, tmp_path: Path) -> None:
        # No project.yaml at the root.
        bare = tmp_path / "bare"
        bare.mkdir()
        result = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(bare)]
        )
        assert result.exit_code != 0
        assert "doesn't look like a tripwire project" in result.output

    def test_parent_kind_is_canonical(self, tmp_path: Path) -> None:
        """`parent` is canonical post-rip; the migration must leave it alone."""
        project = _make_project(tmp_path / "p")
        _write_cache(
            project,
            [
                {"from": "EM-2", "to": "EM-1", "type": "parent"},
            ],
        )

        result = runner.invoke(
            cli, ["migrate", "graph-edges", "--project-dir", str(project)]
        )
        assert result.exit_code == 0, result.output
        edges = _read_edges(project)
        assert edges[0]["type"] == "parent"

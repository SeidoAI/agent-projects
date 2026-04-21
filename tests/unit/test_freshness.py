"""Unit tests for `core/freshness.py`.

Network-dependent tests (GitHub API) are not exercised here — those go in
integration tests once `gh` is reliably available in the test env. The
local-clone path is fully covered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.freshness import (
    HASH_PREFIX,
    _read_local,
    _slice_lines,
    check_all_nodes,
    check_node_freshness,
    fetch_content,
    hash_content,
)
from tripwire.models import (
    ConceptNode,
    NodeSource,
    ProjectConfig,
    RepoEntry,
)
from tripwire.models.graph import FreshnessStatus


class TestHashContent:
    def test_string_hash(self) -> None:
        h = hash_content("hello")
        assert h.startswith(HASH_PREFIX)
        # Known SHA-256 of "hello"
        assert h == (
            "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )

    def test_bytes_hash(self) -> None:
        h = hash_content(b"hello")
        assert h == hash_content("hello")

    def test_empty_hash(self) -> None:
        # SHA-256 of the empty string
        assert hash_content("") == (
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_hash_is_stable(self) -> None:
        assert hash_content("foo") == hash_content("foo")
        assert hash_content("foo") != hash_content("bar")


class TestSliceLines:
    def test_basic_slice(self) -> None:
        text = "one\ntwo\nthree\nfour\nfive\n"
        assert _slice_lines(text, (2, 4)) == "two\nthree\nfour"

    def test_single_line_range(self) -> None:
        text = "a\nb\nc\n"
        assert _slice_lines(text, (2, 2)) == "b"

    def test_full_file_range(self) -> None:
        text = "a\nb\nc"
        assert _slice_lines(text, (1, 3)) == "a\nb\nc"

    def test_invalid_range_raises(self) -> None:
        with pytest.raises(ValueError):
            _slice_lines("a\nb\n", (0, 2))
        with pytest.raises(ValueError):
            _slice_lines("a\nb\n", (3, 1))


class TestReadLocal:
    def test_read_whole_file(self, tmp_path: Path) -> None:
        f = tmp_path / "x.py"
        f.write_text("line one\nline two\nline three\n", encoding="utf-8")
        assert _read_local(f, None) == "line one\nline two\nline three\n"

    def test_read_line_range(self, tmp_path: Path) -> None:
        f = tmp_path / "x.py"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
        assert _read_local(f, (2, 4)) == "b\nc\nd"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert _read_local(tmp_path / "nope.py", None) is None


class TestFetchContent:
    def test_local_clone_path(self, tmp_path: Path) -> None:
        # Set up a fake local clone with a file at src/api/auth.py
        clone_dir = tmp_path / "clone"
        (clone_dir / "src" / "api").mkdir(parents=True)
        target = clone_dir / "src" / "api" / "auth.py"
        target.write_text("def login(): pass\n", encoding="utf-8")

        project = ProjectConfig(
            name="t",
            key_prefix="T",
            repos={"SeidoAI/web-app-backend": RepoEntry(local=str(clone_dir))},
        )
        source = NodeSource(
            repo="SeidoAI/web-app-backend",
            path="src/api/auth.py",
        )
        assert fetch_content(source, project) == "def login(): pass\n"

    def test_local_clone_with_line_range(self, tmp_path: Path) -> None:
        clone_dir = tmp_path / "clone"
        (clone_dir / "src").mkdir(parents=True)
        target = clone_dir / "src" / "x.py"
        target.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

        project = ProjectConfig(
            name="t",
            key_prefix="T",
            repos={"SeidoAI/web-app-backend": RepoEntry(local=str(clone_dir))},
        )
        source = NodeSource(
            repo="SeidoAI/web-app-backend",
            path="src/x.py",
            lines=(2, 4),
        )
        assert fetch_content(source, project) == "two\nthree\nfour"

    def test_no_local_no_gh_returns_none(self, tmp_path: Path) -> None:
        # No local clone configured and no `gh` available — should return None
        # gracefully (the test env may or may not have `gh`, but the source
        # repo doesn't exist on GitHub).
        project = ProjectConfig(name="t", key_prefix="T")
        source = NodeSource(
            repo="non-existent-org-12345/non-existent-repo",
            path="x.py",
        )
        result = fetch_content(source, project)
        assert result is None


class TestCheckNodeFreshness:
    def _make_project_with_clone(
        self, tmp_path: Path, content: str
    ) -> tuple[Path, ProjectConfig]:
        clone_dir = tmp_path / "clone"
        (clone_dir / "src" / "api").mkdir(parents=True)
        (clone_dir / "src" / "api" / "auth.py").write_text(content, encoding="utf-8")
        project = ProjectConfig(
            name="t",
            key_prefix="T",
            repos={"SeidoAI/web-app-backend": RepoEntry(local=str(clone_dir))},
        )
        return clone_dir, project

    def test_no_source_status(self) -> None:
        node = ConceptNode(id="planned-x", type="endpoint", name="x", status="planned")
        result = check_node_freshness(node, ProjectConfig(name="t", key_prefix="T"))
        assert result.status == FreshnessStatus.NO_SOURCE

    def test_fresh_status(self, tmp_path: Path) -> None:
        content = "def login(): pass\n"
        _, project = self._make_project_with_clone(tmp_path, content)
        node = ConceptNode(
            id="auth-endpoint",
            type="endpoint",
            name="x",
            source=NodeSource(
                repo="SeidoAI/web-app-backend",
                path="src/api/auth.py",
                content_hash=hash_content(content),
            ),
        )
        result = check_node_freshness(node, project)
        assert result.status == FreshnessStatus.FRESH

    def test_stale_status_when_hash_differs(self, tmp_path: Path) -> None:
        _, project = self._make_project_with_clone(tmp_path, "def new_login(): pass\n")
        node = ConceptNode(
            id="auth-endpoint",
            type="endpoint",
            name="x",
            source=NodeSource(
                repo="SeidoAI/web-app-backend",
                path="src/api/auth.py",
                content_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
            ),
        )
        result = check_node_freshness(node, project)
        assert result.status == FreshnessStatus.STALE

    def test_source_missing_status(self, tmp_path: Path) -> None:
        # Local clone exists but the file inside is missing.
        clone_dir = tmp_path / "clone"
        clone_dir.mkdir()
        project = ProjectConfig(
            name="t",
            key_prefix="T",
            repos={"SeidoAI/web-app-backend": RepoEntry(local=str(clone_dir))},
        )
        node = ConceptNode(
            id="auth-endpoint",
            type="endpoint",
            name="x",
            source=NodeSource(
                repo="SeidoAI/web-app-backend",
                path="src/api/auth.py",
            ),
        )
        result = check_node_freshness(node, project)
        # Without `gh` configured for this fake repo, fetch returns None.
        # This may resolve to either SOURCE_MISSING (no fallback) or STALE
        # (if `gh` happens to error out cleanly). Accept SOURCE_MISSING.
        assert result.status == FreshnessStatus.SOURCE_MISSING

    def test_no_stored_hash_treated_as_stale(self, tmp_path: Path) -> None:
        content = "def login(): pass\n"
        _, project = self._make_project_with_clone(tmp_path, content)
        node = ConceptNode(
            id="auth-endpoint",
            type="endpoint",
            name="x",
            source=NodeSource(
                repo="SeidoAI/web-app-backend",
                path="src/api/auth.py",
                content_hash=None,
            ),
        )
        result = check_node_freshness(node, project)
        assert result.status == FreshnessStatus.STALE
        assert result.current_hash is not None


class TestCheckAllNodes:
    def test_skips_non_active_nodes(self, tmp_path: Path) -> None:
        clone_dir = tmp_path / "clone"
        (clone_dir / "src").mkdir(parents=True)
        (clone_dir / "src" / "x.py").write_text("a\n", encoding="utf-8")
        project = ProjectConfig(
            name="t",
            key_prefix="T",
            repos={"x/y": RepoEntry(local=str(clone_dir))},
        )
        nodes = [
            ConceptNode(
                id="planned-thing",
                type="endpoint",
                name="x",
                status="planned",
                source=NodeSource(repo="x/y", path="src/x.py"),
            ),
            ConceptNode(
                id="active-without-source",
                type="endpoint",
                name="x",
                status="active",
            ),
            ConceptNode(
                id="active-with-source",
                type="endpoint",
                name="x",
                status="active",
                source=NodeSource(
                    repo="x/y",
                    path="src/x.py",
                    content_hash=hash_content("a\n"),
                ),
            ),
        ]
        results = check_all_nodes(nodes, project)
        # Only the third node was checked.
        assert len(results) == 1
        assert results[0].node_id == "active-with-source"
        assert results[0].status == FreshnessStatus.FRESH

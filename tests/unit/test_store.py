"""Unit tests for `core/store.py` (Issue, ProjectConfig, Comment CRUD)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from tripwire.core.store import (
    ProjectNotFoundError,
    issue_exists,
    list_issues,
    load_comments,
    load_issue,
    load_project,
    save_comment,
    save_issue,
    save_project,
)
from tripwire.models import Comment, Issue, ProjectConfig, RepoEntry


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal project.yaml + empty issues directory."""
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "test",
                "key_prefix": "TST",
                "next_issue_number": 1,
                "next_session_number": 1,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "issues").mkdir()
    return tmp_path


# ----------------------------------------------------------------------------
# ProjectConfig
# ----------------------------------------------------------------------------


class TestProject:
    def test_load_project(self, project_dir: Path) -> None:
        config = load_project(project_dir)
        assert config.name == "test"
        assert config.key_prefix == "TST"

    def test_load_missing_project_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectNotFoundError):
            load_project(tmp_path)

    def test_save_and_reload(self, project_dir: Path) -> None:
        config = load_project(project_dir)
        config.repos["SeidoAI/web-app-backend"] = RepoEntry(local="~/Code/x")
        save_project(project_dir, config)
        reloaded = load_project(project_dir)
        assert "SeidoAI/web-app-backend" in reloaded.repos
        assert reloaded.repos["SeidoAI/web-app-backend"].local == "~/Code/x"

    def test_save_full_project_config_round_trip(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="seido",
            key_prefix="SEI",
            base_branch="main",
            statuses=["backlog", "todo", "done"],
            status_transitions={
                "backlog": ["todo"],
                "todo": ["done"],
                "done": [],
            },
            repos={"SeidoAI/x": RepoEntry(local="~/x")},
            next_issue_number=5,
        )
        save_project(tmp_path, config)
        reloaded = load_project(tmp_path)
        assert reloaded.name == "seido"
        assert reloaded.next_issue_number == 5
        assert reloaded.status_transitions["todo"] == ["done"]


# ----------------------------------------------------------------------------
# Issues
# ----------------------------------------------------------------------------


class TestIssueStore:
    def test_save_and_load_issue(self, project_dir: Path) -> None:
        issue = Issue(
            id="TST-1",
            title="Test issue",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body="## Context\n\nSome context with [[ref]].\n",
        )
        save_issue(project_dir, issue)
        loaded = load_issue(project_dir, "TST-1")

        assert loaded.uuid == issue.uuid
        assert loaded.id == "TST-1"
        assert loaded.title == "Test issue"
        assert "[[ref]]" in loaded.body

    def test_save_creates_issues_directory(self, tmp_path: Path) -> None:
        # Even without an existing issues/ directory, save should create it.
        issue = Issue(
            id="TST-1",
            title="t",
            status="todo",
            priority="low",
            executor="ai",
            verifier="none",
        )
        save_issue(tmp_path, issue)
        assert (tmp_path / "issues" / "TST-1" / "issue.yaml").exists()

    def test_load_missing_issue_raises(self, project_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_issue(project_dir, "TST-999")

    def test_save_sets_updated_at_if_unset(self, project_dir: Path) -> None:
        issue = Issue(
            id="TST-1",
            title="t",
            status="todo",
            priority="low",
            executor="ai",
            verifier="none",
        )
        assert issue.updated_at is None
        save_issue(project_dir, issue)
        assert issue.updated_at is not None

    def test_list_issues_empty(self, project_dir: Path) -> None:
        assert list_issues(project_dir) == []

    def test_list_issues_returns_all(self, project_dir: Path) -> None:
        for n in (1, 2, 3):
            save_issue(
                project_dir,
                Issue(
                    id=f"TST-{n}",
                    title=f"Issue {n}",
                    status="todo",
                    priority="low",
                    executor="ai",
                    verifier="none",
                ),
            )
        loaded = list_issues(project_dir)
        assert len(loaded) == 3
        assert {i.id for i in loaded} == {"TST-1", "TST-2", "TST-3"}

    def test_issue_exists(self, project_dir: Path) -> None:
        assert not issue_exists(project_dir, "TST-1")
        save_issue(
            project_dir,
            Issue(
                id="TST-1",
                title="t",
                status="todo",
                priority="low",
                executor="ai",
                verifier="none",
            ),
        )
        assert issue_exists(project_dir, "TST-1")

    def test_uuid_round_trip_through_yaml(self, project_dir: Path) -> None:
        original = Issue(
            id="TST-1",
            title="t",
            status="todo",
            priority="low",
            executor="ai",
            verifier="none",
            body="body",
        )
        original_uuid = original.uuid
        save_issue(project_dir, original)
        # Read the raw YAML to confirm uuid is the first frontmatter field.
        raw = (project_dir / "issues" / "TST-1" / "issue.yaml").read_text()
        assert raw.startswith("---\nuuid:")
        loaded = load_issue(project_dir, "TST-1")
        assert loaded.uuid == original_uuid


# ----------------------------------------------------------------------------
# Comments
# ----------------------------------------------------------------------------


class TestCommentStore:
    def test_save_and_load_comments(self, project_dir: Path) -> None:
        c1 = Comment(
            issue_key="TST-1",
            author="claude",
            type="status_change",
            created_at=datetime(2026, 4, 7, 10),
            body="started work",
        )
        c2 = Comment(
            issue_key="TST-1",
            author="maia",
            type="question",
            created_at=datetime(2026, 4, 7, 11),
            body="question?",
        )
        save_comment(project_dir, c1, "001-start.yaml")
        save_comment(project_dir, c2, "002-question.yaml")

        loaded = load_comments(project_dir, "TST-1")
        assert len(loaded) == 2
        # Sorted by filename → 001 first, then 002
        assert loaded[0].author == "claude"
        assert loaded[1].author == "maia"

    def test_load_comments_for_unknown_issue(self, project_dir: Path) -> None:
        assert load_comments(project_dir, "TST-999") == []


# ============================================================================
# Cache invalidation on save (Phase 2.2 of v0.5 architectural refactor)
# ============================================================================


class TestCacheInvalidationOnSave:
    """save_issue and save_node (default update_cache=True) must leave
    the graph cache consistent with what's on disk."""

    def test_save_issue_updates_graph_cache(self, project_dir: Path) -> None:
        from tripwire.core.graph_cache import load_index

        issue = Issue(
            id="TST-42",
            title="Cache me",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body="Body.\n",
        )
        save_issue(project_dir, issue)

        cache = load_index(project_dir)
        assert cache is not None, "save_issue should have created the cache"
        assert "issues/TST-42/issue.yaml" in cache.files

    def test_save_issue_with_update_cache_false_does_not_touch_cache(
        self, project_dir: Path
    ) -> None:
        from tripwire.core.graph_cache import load_index

        issue = Issue(
            id="TST-99",
            title="No cache",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body="Body.\n",
        )
        save_issue(project_dir, issue, update_cache=False)

        cache = load_index(project_dir)
        # Either no cache file at all, or the cache doesn't include TST-99.
        if cache is not None:
            assert "issues/TST-99/issue.yaml" not in cache.files

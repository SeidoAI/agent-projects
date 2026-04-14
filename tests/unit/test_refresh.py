"""Unit tests for `keel refresh`."""

from __future__ import annotations

from pathlib import Path

import yaml

from keel.core.graph_cache import ensure_fresh, load_index


def write_project_yaml(project_dir: Path) -> None:
    config = {
        "name": "test-project",
        "key_prefix": "TST",
        "base_branch": "main",
        "repos": {},
        "statuses": ["backlog", "todo", "in_progress", "done"],
        "status_transitions": {
            "backlog": ["todo"],
            "todo": ["in_progress"],
            "in_progress": ["done"],
            "done": [],
        },
        "next_issue_number": 1,
        "next_session_number": 1,
    }
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )


class TestRefreshCommand:
    def test_fresh_cache_is_noop(self, tmp_path: Path) -> None:
        write_project_yaml(tmp_path)
        (tmp_path / "issues").mkdir()
        (tmp_path / "nodes").mkdir(parents=True)

        # First call builds
        assert ensure_fresh(tmp_path) is True
        # Second call is a no-op
        assert ensure_fresh(tmp_path) is False

    def test_stale_cache_rebuilds(self, tmp_path: Path) -> None:
        write_project_yaml(tmp_path)
        (tmp_path / "issues").mkdir()
        (tmp_path / "nodes").mkdir(parents=True)

        ensure_fresh(tmp_path)
        idx = load_index(tmp_path)
        assert idx is not None

        # Add an issue file — makes cache stale
        import uuid

        from keel.core.parser import serialize_frontmatter_body

        fm = {
            "uuid": str(uuid.uuid4()),
            "id": "TST-1",
            "title": "Test issue",
            "status": "todo",
            "priority": "medium",
            "executor": "ai",
            "verifier": "required",
            "created_at": "2026-04-10T10:00:00",
            "updated_at": "2026-04-10T10:00:00",
        }
        body = "## Context\nTest.\n"
        idir = tmp_path / "issues" / "TST-1"
        idir.mkdir(parents=True, exist_ok=True)
        (idir / "issue.yaml").write_text(
            serialize_frontmatter_body(fm, body), encoding="utf-8"
        )

        # Now cache is stale — should rebuild
        assert ensure_fresh(tmp_path) is True

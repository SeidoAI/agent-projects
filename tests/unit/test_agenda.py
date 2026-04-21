"""Unit tests for `tripwire agenda`."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import yaml

from tripwire.cli.agenda import _collect_agenda
from tripwire.core.parser import serialize_frontmatter_body


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


def write_issue(project_dir: Path, key: str, **overrides: object) -> None:
    idir = project_dir / "issues" / key
    idir.mkdir(parents=True, exist_ok=True)
    fm = {
        "uuid": str(uuid.uuid4()),
        "id": key,
        "title": f"Test {key}",
        "status": "todo",
        "priority": "medium",
        "executor": "ai",
        "verifier": "required",
        "created_at": "2026-04-10T10:00:00",
        "updated_at": "2026-04-10T10:00:00",
    }
    fm.update(overrides)
    body = "## Context\nTest.\n\n## Acceptance criteria\n- [ ] ok\n"
    (idir / "issue.yaml").write_text(
        serialize_frontmatter_body(fm, body), encoding="utf-8"
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write_project_yaml(tmp_path)
    (tmp_path / "issues").mkdir()
    (tmp_path / "nodes").mkdir(parents=True)
    return tmp_path


class TestAgendaCollection:
    def test_empty_project(self, project: Path) -> None:
        result = _collect_agenda(project, "status", None)
        assert result.total_issues == 0
        assert result.groups == []

    def test_groups_by_status(self, project: Path) -> None:
        write_issue(project, "TST-1", status="todo")
        write_issue(project, "TST-2", status="todo")
        write_issue(project, "TST-3", status="in_progress")
        result = _collect_agenda(project, "status", None)
        assert result.total_issues == 3
        assert len(result.groups) == 2
        group_keys = {g.key for g in result.groups}
        assert group_keys == {"todo", "in_progress"}

    def test_groups_by_executor(self, project: Path) -> None:
        write_issue(project, "TST-1", executor="ai")
        write_issue(project, "TST-2", executor="human")
        result = _collect_agenda(project, "executor", None)
        group_keys = {g.key for g in result.groups}
        assert group_keys == {"ai", "human"}

    def test_filter(self, project: Path) -> None:
        write_issue(project, "TST-1", status="todo")
        write_issue(project, "TST-2", status="in_progress")
        result = _collect_agenda(project, "status", "status:todo")
        assert result.total_issues == 1
        assert result.groups[0].key == "todo"
        assert len(result.groups[0].items) == 1

    def test_blocked_detection(self, project: Path) -> None:
        write_issue(project, "TST-1", status="todo")
        write_issue(project, "TST-2", status="todo", blocked_by=["TST-1"])
        result = _collect_agenda(project, "status", None)
        assert result.blocked_count == 1
        blocked_items = [
            item for g in result.groups for item in g.items if item.is_blocked
        ]
        assert len(blocked_items) == 1
        assert blocked_items[0].id == "TST-2"

    def test_json_serializable(self, project: Path) -> None:
        write_issue(project, "TST-1")
        result = _collect_agenda(project, "status", None)
        from dataclasses import asdict

        out = json.loads(json.dumps(asdict(result)))
        assert out["project_name"] == "test-project"
        assert out["total_issues"] == 1
        assert isinstance(out["groups"], list)

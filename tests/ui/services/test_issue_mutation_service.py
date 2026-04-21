"""Tests for tripwire.ui.services.issue_mutation_service (KUI-24)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from tripwire.core.store import load_issue
from tripwire.ui.services._audit import audit_log_path
from tripwire.ui.services.issue_mutation_service import (
    IssuePatch,
    update_issue_fields,
    update_issue_status,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _redirect_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Send audit writes into tmp_path rather than the real ~/.tripwire."""
    monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "audit-logs"))


@pytest.fixture
def project_with_transitions(tmp_path_project: Path):
    """Overlay a project.yaml with a realistic status_transitions map."""
    data: dict[str, Any] = {
        "name": "tmp",
        "key_prefix": "TMP",
        "next_issue_number": 1,
        "next_session_number": 1,
        "statuses": ["todo", "in_progress", "in_review", "done"],
        "status_transitions": {
            "todo": ["in_progress"],
            "in_progress": ["in_review", "todo"],
            "in_review": ["done", "in_progress"],
            "done": [],
        },
        "label_categories": {
            "executor": [],
            "verifier": [],
            "domain": ["domain/backend", "domain/frontend"],
            "agent": [],
        },
    }
    (tmp_path_project / "project.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    return tmp_path_project


# ---------------------------------------------------------------------------
# update_issue_status
# ---------------------------------------------------------------------------


class TestUpdateIssueStatus:
    def test_valid_transition_updates_status(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")

        result = update_issue_status(project_with_transitions, "TMP-1", "in_progress")

        assert result.id == "TMP-1"
        assert result.status == "in_progress"
        # Confirmed on disk too.
        reloaded = load_issue(project_with_transitions, "TMP-1")
        assert reloaded.status == "in_progress"

    def test_invalid_transition_raises(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        with pytest.raises(ValueError, match="Invalid transition"):
            update_issue_status(project_with_transitions, "TMP-1", "done")

    def test_invalid_transition_mentions_allowed_list(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        with pytest.raises(ValueError, match="in_progress"):
            update_issue_status(project_with_transitions, "TMP-1", "done")

    def test_no_op_same_status_succeeds(
        self, project_with_transitions, save_test_issue
    ):
        """PATCHing to the same status is idempotent, not an error."""
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        result = update_issue_status(project_with_transitions, "TMP-1", "todo")
        assert result.status == "todo"

    def test_transition_from_terminal_status_raises(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="done")
        with pytest.raises(ValueError, match="Invalid transition"):
            update_issue_status(project_with_transitions, "TMP-1", "in_progress")

    def test_updates_updated_at_timestamp(
        self, project_with_transitions, save_test_issue
    ):
        from datetime import datetime

        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        before = load_issue(project_with_transitions, "TMP-1").updated_at

        update_issue_status(project_with_transitions, "TMP-1", "in_progress")

        after = load_issue(project_with_transitions, "TMP-1").updated_at
        assert after is not None
        assert isinstance(after, datetime)
        if before is not None:
            assert after >= before

    def test_preserves_body(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        original_body = load_issue(project_with_transitions, "TMP-1").body

        update_issue_status(project_with_transitions, "TMP-1", "in_progress")

        assert load_issue(project_with_transitions, "TMP-1").body == original_body

    def test_missing_issue_raises_file_not_found(
        self, project_with_transitions
    ):
        with pytest.raises(FileNotFoundError):
            update_issue_status(project_with_transitions, "TMP-404", "in_progress")

    def test_audit_log_entry_written_on_success(
        self, project_with_transitions, save_test_issue, tmp_path: Path
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        update_issue_status(project_with_transitions, "TMP-1", "in_progress")

        log_path = audit_log_path(project_with_transitions)
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "issue.update_status"
        assert record["before_state_snippet"] == {"status": "todo"}
        assert record["after_state_snippet"] == {"status": "in_progress"}
        assert record["extras"]["issue_key"] == "TMP-1"

    def test_audit_log_entry_written_on_rejection(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        with pytest.raises(ValueError):
            update_issue_status(project_with_transitions, "TMP-1", "done")

        log_path = audit_log_path(project_with_transitions)
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "issue.update_status.rejected"

    def test_file_not_written_on_invalid_transition(
        self, project_with_transitions, save_test_issue
    ):
        """Transition check rejects before the save — status stays on todo."""
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        with pytest.raises(ValueError):
            update_issue_status(project_with_transitions, "TMP-1", "done")
        assert load_issue(project_with_transitions, "TMP-1").status == "todo"


# ---------------------------------------------------------------------------
# update_issue_fields
# ---------------------------------------------------------------------------


class TestUpdateIssueFields:
    def test_partial_patch_only_changes_set_fields(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(
            project_with_transitions,
            "TMP-1",
            status="todo",
            priority="medium",
            labels=["domain/backend"],
        )

        patch = IssuePatch(priority="high")
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)

        # priority changed; status/labels untouched.
        assert result.priority == "high"
        assert result.status == "todo"
        assert result.labels == ["domain/backend"]

    def test_empty_patch_is_noop(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        patch = IssuePatch()
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.status == "todo"
        # No audit entry should be written for a literal no-op.
        assert not audit_log_path(project_with_transitions).exists()

    def test_status_patch_goes_through_transition_check(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        patch = IssuePatch(status="done")
        with pytest.raises(ValueError, match="Invalid transition"):
            update_issue_fields(project_with_transitions, "TMP-1", patch)

    def test_status_patch_valid_transition_succeeds(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="todo")
        patch = IssuePatch(status="in_progress")
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.status == "in_progress"

    def test_invalid_priority_enum_raises(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(priority="extreme")
        with pytest.raises(ValueError, match="priority"):
            update_issue_fields(project_with_transitions, "TMP-1", patch)

    def test_invalid_label_raises(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(labels=["domain/nonexistent"])
        with pytest.raises(ValueError, match="label"):
            update_issue_fields(project_with_transitions, "TMP-1", patch)

    def test_valid_label_succeeds(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(labels=["domain/backend"])
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.labels == ["domain/backend"]

    def test_immutable_field_rejected_at_dto_validation(self):
        """IssuePatch forbids extra fields, protecting uuid/id/created_at."""
        with pytest.raises(ValidationError):
            IssuePatch.model_validate(
                {"uuid": "00000000-0000-0000-0000-000000000000"}
            )
        with pytest.raises(ValidationError):
            IssuePatch.model_validate({"id": "OTHER-1"})
        with pytest.raises(ValidationError):
            IssuePatch.model_validate({"created_at": "2020-01-01"})

    def test_multi_field_patch(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(
            project_with_transitions, "TMP-1", status="todo", priority="medium"
        )
        patch = IssuePatch(status="in_progress", priority="high")
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.status == "in_progress"
        assert result.priority == "high"

    def test_audit_entry_on_success(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", priority="medium")
        patch = IssuePatch(priority="high")
        update_issue_fields(project_with_transitions, "TMP-1", patch)

        log_path = audit_log_path(project_with_transitions)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "issue.update_fields"
        assert record["before_state_snippet"] == {"priority": "medium"}
        assert record["after_state_snippet"] == {"priority": "high"}

    def test_updates_updated_at(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(priority="high")
        update_issue_fields(project_with_transitions, "TMP-1", patch)
        reloaded = load_issue(project_with_transitions, "TMP-1")
        assert reloaded.updated_at is not None

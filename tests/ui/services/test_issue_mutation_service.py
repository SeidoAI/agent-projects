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
    """Overlay project.yaml + workflow.yaml so the issue-closure routes
    drive the realistic queued → executing → in_review → completed flow
    this module exercises.

    v0.13.1 (B8): the legacy ``project.yaml.status_transitions`` block
    no longer exists; the workflow.yaml's ``issue-closure`` routes are
    the source of truth. This fixture writes both so the mutation
    service can resolve transitions via the workflow.
    """
    data: dict[str, Any] = {
        "name": "tmp",
        "key_prefix": "TMP",
        "next_issue_number": 1,
        "next_session_number": 1,
        "statuses": ["queued", "executing", "in_review", "completed"],
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
    # Workflow with only the routes this module's tests exercise.
    _routes = [
        ("queued", "executing"),
        ("executing", "in_review"),
        ("executing", "queued"),
        ("in_review", "completed"),
        ("in_review", "executing"),
    ]
    routes_yaml = "".join(
        f"      - id: issue-{f}-to-{t}\n"
        f"        actor: pm-agent\n"
        f"        from: {f}\n"
        f"        to: {t}\n"
        f"        kind: forward\n"
        for f, t in _routes
    )
    (tmp_path_project / "workflow.yaml").write_text(
        "workflow_schema_version: 1\n"
        "workflows:\n"
        "  issue-closure:\n"
        "    actor: pm-agent\n"
        "    trigger: command.pm-issue-close\n"
        "    instance:\n"
        "      storage_path: instances/issues/{instance_id}/issue.yaml\n"
        "      status_field: status\n"
        "      status_enum: [queued, executing, in_review, completed]\n"
        "    statuses:\n"
        "      - id: queued\n"
        "      - id: executing\n"
        "      - id: in_review\n"
        "      - id: completed\n"
        "        terminal: true\n"
        "    routes:\n" + routes_yaml,
        encoding="utf-8",
    )
    return tmp_path_project


# ---------------------------------------------------------------------------
# update_issue_status
# ---------------------------------------------------------------------------


class TestUpdateIssueStatus:
    def test_valid_transition_updates_status(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")

        result = update_issue_status(project_with_transitions, "TMP-1", "executing")

        assert result.id == "TMP-1"
        assert result.status == "executing"
        # Confirmed on disk too.
        reloaded = load_issue(project_with_transitions, "TMP-1")
        assert reloaded.status == "executing"

    def test_invalid_transition_raises(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        with pytest.raises(ValueError, match="Invalid transition"):
            update_issue_status(project_with_transitions, "TMP-1", "completed")

    def test_invalid_transition_mentions_allowed_list(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        with pytest.raises(ValueError, match="executing"):
            update_issue_status(project_with_transitions, "TMP-1", "completed")

    def test_no_op_same_status_succeeds(
        self, project_with_transitions, save_test_issue
    ):
        """PATCHing to the same status is idempotent, not an error."""
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        result = update_issue_status(project_with_transitions, "TMP-1", "queued")
        assert result.status == "queued"

    def test_no_op_same_status_writes_audit_and_bumps_updated_at(
        self, project_with_transitions, save_test_issue
    ):
        """Regression test for codex-MED on the v0.13.2 same-status
        short-circuit.

        Before the fix, an idempotent same-status patch returned the
        cached detail without writing an audit row or bumping
        ``updated_at`` — the PM's request disappeared without trace.
        That's a regression vs. the pre-v0.13.2 path, which always
        recorded the acknowledgement.
        """
        from datetime import datetime, timedelta, timezone

        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        before_updated_at = load_issue(project_with_transitions, "TMP-1").updated_at

        update_issue_status(project_with_transitions, "TMP-1", "queued")

        # updated_at advanced past the seeded value.
        after_updated_at = load_issue(project_with_transitions, "TMP-1").updated_at
        assert after_updated_at is not None
        assert after_updated_at != before_updated_at
        assert datetime.now(tz=timezone.utc) - after_updated_at < timedelta(minutes=1)

        # Audit row written with the distinct ``no_op`` action so
        # operators can filter same-status acks from real transitions.
        log_path = audit_log_path(project_with_transitions)
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "issue.update_status.no_op"
        assert record["before_state_snippet"] == {"status": "queued"}
        assert record["after_state_snippet"] == {"status": "queued"}
        assert record["extras"]["issue_key"] == "TMP-1"

    def test_transition_from_terminal_status_raises(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="completed")
        with pytest.raises(ValueError, match="Invalid transition"):
            update_issue_status(project_with_transitions, "TMP-1", "executing")

    def test_updates_updated_at_timestamp(
        self, project_with_transitions, save_test_issue
    ):
        from datetime import datetime, timedelta, timezone

        save_test_issue(project_with_transitions, "TMP-1", status="queued")

        update_issue_status(project_with_transitions, "TMP-1", "executing")

        after = load_issue(project_with_transitions, "TMP-1").updated_at
        assert after is not None
        assert isinstance(after, datetime)
        # Post-fix-#6: mutation writes tz-aware UTC timestamps.
        assert after.tzinfo is not None
        # And the stamp is recent (within the last minute of real time).
        assert datetime.now(tz=timezone.utc) - after < timedelta(minutes=1)

    def test_preserves_body(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        original_body = load_issue(project_with_transitions, "TMP-1").body

        update_issue_status(project_with_transitions, "TMP-1", "executing")

        assert load_issue(project_with_transitions, "TMP-1").body == original_body

    def test_missing_issue_raises_file_not_found(self, project_with_transitions):
        with pytest.raises(FileNotFoundError):
            update_issue_status(project_with_transitions, "TMP-404", "executing")

    def test_audit_log_entry_written_on_success(
        self, project_with_transitions, save_test_issue, tmp_path: Path
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        update_issue_status(project_with_transitions, "TMP-1", "executing")

        log_path = audit_log_path(project_with_transitions)
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "issue.update_status"
        assert record["before_state_snippet"] == {"status": "queued"}
        assert record["after_state_snippet"] == {"status": "executing"}
        assert record["extras"]["issue_key"] == "TMP-1"

    def test_audit_log_entry_written_on_rejection(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        with pytest.raises(ValueError):
            update_issue_status(project_with_transitions, "TMP-1", "completed")

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
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        with pytest.raises(ValueError):
            update_issue_status(project_with_transitions, "TMP-1", "completed")
        assert load_issue(project_with_transitions, "TMP-1").status == "queued"

    def test_executor_call_and_audit_happen_inside_project_lock(
        self,
        project_with_transitions,
        save_test_issue,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """v0.13.2 follow-up: the executor call (which now does the
        actual save) and the UI audit write both happen INSIDE the
        ``project_lock`` so concurrent callers can't race and a crash
        between executor-return and audit-write never leaves a mutated-
        but-unaudited issue (from the UI audit log's perspective).

        Trace order: lock-enter → executor → audit → lock-release.
        The executor's own per-instance transition lock is a separate
        lock (different path name) so it nests cleanly inside
        ``project_lock``.
        """
        save_test_issue(project_with_transitions, "TMP-1", status="queued")

        events: list[str] = []

        import contextlib

        from tripwire.core.workflow import transitions as exec_mod
        from tripwire.ui.services import issue_mutation_service as svc

        original_lock = svc.project_lock
        original_execute = exec_mod.execute_transition
        original_audit = svc.write_audit_entry

        def _traced_lock(project_dir):
            @contextlib.contextmanager
            def _wrap():
                events.append("lock_acquired")
                with original_lock(project_dir):
                    yield
                events.append("lock_released")

            return _wrap()

        def _traced_execute(*a, **kw):
            events.append("execute_transition")
            return original_execute(*a, **kw)

        def _traced_audit(*a, **kw):
            events.append("audit")
            return original_audit(*a, **kw)

        monkeypatch.setattr(svc, "project_lock", _traced_lock)
        monkeypatch.setattr(exec_mod, "execute_transition", _traced_execute)
        monkeypatch.setattr(svc, "write_audit_entry", _traced_audit)

        update_issue_status(project_with_transitions, "TMP-1", "executing")

        # Order: acquired < execute_transition < audit < released.
        assert events[0] == "lock_acquired"
        assert events[-1] == "lock_released"
        exec_idx = events.index("execute_transition")
        audit_idx = events.index("audit")
        release_idx = events.index("lock_released")
        assert exec_idx < audit_idx < release_idx

    def test_updated_at_is_tz_aware_utc(
        self, project_with_transitions, save_test_issue
    ):
        """Post-fix #6: updated_at is tz-aware UTC on every successful write."""
        save_test_issue(project_with_transitions, "TMP-1", status="queued")

        update_issue_status(project_with_transitions, "TMP-1", "executing")

        reloaded = load_issue(project_with_transitions, "TMP-1")
        assert reloaded.updated_at is not None
        assert reloaded.updated_at.tzinfo is not None


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
            status="queued",
            priority="medium",
            labels=["domain/backend"],
        )

        patch = IssuePatch(priority="high")
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)

        # priority changed; status/labels untouched.
        assert result.priority == "high"
        assert result.status == "queued"
        assert result.labels == ["domain/backend"]

    def test_empty_patch_is_noop(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        patch = IssuePatch()
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.status == "queued"
        # No audit entry should be written for a literal no-op.
        assert not audit_log_path(project_with_transitions).exists()

    def test_status_patch_goes_through_transition_check(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        patch = IssuePatch(status="completed")
        with pytest.raises(ValueError, match="Invalid transition"):
            update_issue_fields(project_with_transitions, "TMP-1", patch)

    def test_status_patch_valid_transition_succeeds(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1", status="queued")
        patch = IssuePatch(status="executing")
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.status == "executing"

    def test_invalid_priority_enum_raises(
        self, project_with_transitions, save_test_issue
    ):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(priority="extreme")
        with pytest.raises(ValueError, match="priority"):
            update_issue_fields(project_with_transitions, "TMP-1", patch)

    def test_invalid_label_raises(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(labels=["domain/nonexistent"])
        with pytest.raises(ValueError, match="label"):
            update_issue_fields(project_with_transitions, "TMP-1", patch)

    def test_valid_label_succeeds(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(labels=["domain/backend"])
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.labels == ["domain/backend"]

    def test_immutable_field_rejected_at_dto_validation(self):
        """IssuePatch forbids extra fields, protecting uuid/id/created_at."""
        with pytest.raises(ValidationError):
            IssuePatch.model_validate({"uuid": "00000000-0000-4000-8000-000000000000"})
        with pytest.raises(ValidationError):
            IssuePatch.model_validate({"id": "OTHER-1"})
        with pytest.raises(ValidationError):
            IssuePatch.model_validate({"created_at": "2020-01-01"})

    def test_multi_field_patch(self, project_with_transitions, save_test_issue):
        save_test_issue(
            project_with_transitions, "TMP-1", status="queued", priority="medium"
        )
        patch = IssuePatch(status="executing", priority="high")
        result = update_issue_fields(project_with_transitions, "TMP-1", patch)
        assert result.status == "executing"
        assert result.priority == "high"

    def test_audit_entry_on_success(self, project_with_transitions, save_test_issue):
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

    def test_updates_updated_at(self, project_with_transitions, save_test_issue):
        save_test_issue(project_with_transitions, "TMP-1")
        patch = IssuePatch(priority="high")
        update_issue_fields(project_with_transitions, "TMP-1", patch)
        reloaded = load_issue(project_with_transitions, "TMP-1")
        assert reloaded.updated_at is not None

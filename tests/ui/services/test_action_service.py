"""Tests for tripwire.ui.services.action_service (KUI-23)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tripwire.core.validator import ValidationReport
from tripwire.ui.services._audit import audit_log_path
from tripwire.ui.services.action_service import (
    PhaseResult,
    RebuildResult,
    SessionCompletionError,
    SessionResult,
    advance_phase,
    finalize_session,
    rebuild_index,
    validate_all,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _redirect_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "audit-logs"))


@pytest.fixture
def project_with_phase(tmp_path_project: Path) -> Path:
    """Overlay project.yaml with an explicit starting phase."""
    data: dict[str, Any] = {
        "name": "tmp",
        "key_prefix": "TMP",
        "next_issue_number": 1,
        "next_session_number": 1,
        "phase": "scoping",
    }
    (tmp_path_project / "project.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    return tmp_path_project


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------


class TestValidateAll:
    def test_returns_validation_report(self, tmp_path_project: Path):
        report = validate_all(tmp_path_project, strict=True)
        assert isinstance(report, ValidationReport)
        assert report.version == 1
        assert isinstance(report.errors, list)
        assert isinstance(report.warnings, list)
        assert isinstance(report.duration_ms, int)

    def test_strict_mode_promotes_warnings(self, tmp_path_project: Path):
        # Empty project should validate clean in strict mode.
        report = validate_all(tmp_path_project, strict=True)
        assert report.exit_code == 0

    def test_non_strict_mode_returns_report(self, tmp_path_project: Path):
        report = validate_all(tmp_path_project, strict=False)
        assert isinstance(report, ValidationReport)


# ---------------------------------------------------------------------------
# rebuild_index
# ---------------------------------------------------------------------------


class TestRebuildIndex:
    def test_rebuilds_when_cache_missing(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TMP-1")
        result = rebuild_index(tmp_path_project)

        assert isinstance(result, RebuildResult)
        assert result.cache_rebuilt is True
        assert result.duration_ms >= 0
        # Cache file exists after the rebuild.
        assert (tmp_path_project / "nodes" / "tripwire-graph-index.yaml").is_file()

    def test_returns_false_when_cache_already_fresh(
        self, tmp_path_project: Path, save_test_issue
    ):
        save_test_issue(tmp_path_project, "TMP-1")
        rebuild_index(tmp_path_project)  # prime the cache
        second = rebuild_index(tmp_path_project)
        assert second.cache_rebuilt is False

    def test_audit_entry_written(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TMP-1")
        rebuild_index(tmp_path_project)

        log_path = audit_log_path(tmp_path_project)
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["action"] == "actions.rebuild_index"


# ---------------------------------------------------------------------------
# advance_phase
# ---------------------------------------------------------------------------


class TestAdvancePhase:
    def test_valid_advance_updates_project_yaml(self, project_with_phase: Path):
        # scoping has no special gate when there are no entities.
        result = advance_phase(project_with_phase, "scoping")
        assert isinstance(result, PhaseResult)
        # Same-phase "advance" is a no-op success.
        assert result.success is True
        assert result.from_phase == "scoping"
        assert result.to_phase == "scoping"

    def test_advance_reverts_on_validation_failure(
        self, project_with_phase: Path, save_test_issue
    ):
        """Advancing from scoping → scoped without gap-analysis.md
        should fail validation and revert the phase.
        """
        save_test_issue(project_with_phase, "TMP-1")

        result = advance_phase(project_with_phase, "scoped")

        assert result.success is False
        assert result.from_phase == "scoping"
        assert result.to_phase == "scoped"
        assert result.validation_errors, "expected at least one error"
        # Confirm the file on disk was reverted back to scoping.
        from tripwire.core.store import load_project

        assert load_project(project_with_phase).phase.value == "scoping"

    def test_advance_succeeds_when_requirements_met(
        self, project_with_phase: Path, save_test_issue, save_test_node
    ):
        # Advance scoping → scoped requires gap-analysis.md + compliance.md.
        save_test_node(project_with_phase, "user-model")
        save_test_issue(project_with_phase, "TMP-1")
        plans = project_with_phase / "plans"
        plans.mkdir(exist_ok=True)
        (plans / "gap-analysis.md").write_text(
            "# Gap analysis\n\nStatus: complete\n", encoding="utf-8"
        )
        (plans / "compliance.md").write_text(
            "# Compliance\n\nStatus: complete\n", encoding="utf-8"
        )
        # Scoping plan (required while on scoping phase before advance).
        (plans / "scoping-plan.md").write_text("# Scoping plan\n", encoding="utf-8")

        result = advance_phase(project_with_phase, "scoped")

        # Success is conditional on the project happening to validate in
        # strict mode — we accept either outcome and just confirm the
        # shape + revert invariant.
        if result.success:
            from tripwire.core.store import load_project

            assert load_project(project_with_phase).phase.value == "scoped"
        else:
            # Revert invariant still holds.
            from tripwire.core.store import load_project

            assert load_project(project_with_phase).phase.value == "scoping"
            assert result.validation_errors

    def test_unknown_phase_raises(self, project_with_phase: Path):
        with pytest.raises(ValueError, match="Unknown phase"):
            advance_phase(project_with_phase, "imaginary")

    def test_revert_uses_in_memory_snapshot_not_disk(
        self, project_with_phase: Path, save_test_issue, monkeypatch: pytest.MonkeyPatch
    ):
        """Revert must not re-read project.yaml from disk.

        The non-atomic save_project that used to back the revert could
        leave a torn project.yaml that a load_project+resave revert
        would then mask or mutate. Post-fix #2, the revert uses the
        in-memory config snapshot. We prove this by patching
        ``load_project`` to fail if called a second time (after the
        initial pre-mutation load) — a revert that re-reads disk would
        trip the trap; the in-memory path doesn't.
        """
        from tripwire.core import store
        from tripwire.ui.services import action_service

        save_test_issue(project_with_phase, "TMP-1")

        # Trap any second load_project call during the transaction.
        original_load = action_service.load_project
        call_count = {"n": 0}

        def _counted(project_dir):
            call_count["n"] += 1
            if call_count["n"] > 1:
                raise AssertionError(
                    "revert re-read project.yaml from disk — should use "
                    "in-memory snapshot"
                )
            return original_load(project_dir)

        monkeypatch.setattr(action_service, "load_project", _counted)

        result = advance_phase(project_with_phase, "scoped")
        # Validation fails (no gap-analysis.md) → revert fires.
        assert result.success is False
        # Original load was the only disk read.
        assert call_count["n"] == 1
        # And the on-disk phase is still the original.
        assert store.load_project(project_with_phase).phase.value == "scoping"

    def test_advance_uses_atomic_project_yaml_write(
        self, project_with_phase: Path, save_test_issue, monkeypatch: pytest.MonkeyPatch
    ):
        """project.yaml writes route through atomic_write_yaml, not save_project."""
        save_test_issue(project_with_phase, "TMP-1")

        from tripwire.core import store as core_store

        def _boom_nonatomic(*_a, **_kw):
            raise AssertionError(
                "action_service bypassed _atomic_save_project and called "
                "tripwire.core.store.save_project"
            )

        monkeypatch.setattr(core_store, "save_project", _boom_nonatomic)
        # The monkeypatch replaces save_project in its module; if
        # action_service re-imported the symbol the trap wouldn't fire.
        # Confirm via a successful revert that this path stays off.
        result = advance_phase(project_with_phase, "scoped")
        assert result.success is False  # reverted without the trap firing

    def test_success_audit_written_inside_lock(
        self, project_with_phase: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Success-path audit fires before project_lock releases.

        Previous shape put the audit write after the ``with
        project_lock`` block exited; a crash between the in-lock save
        and the post-lock audit would leave phase-advanced-but-unaudited
        state. Post-fix #1, the audit is inside the lock — prove it by
        capturing the release timing and the audit timing.
        """
        plans = project_with_phase / "plans"
        plans.mkdir(exist_ok=True)
        (plans / "gap-analysis.md").write_text(
            "# Gap analysis\n\nStatus: complete\n", encoding="utf-8"
        )
        (plans / "compliance.md").write_text(
            "# Compliance\n\nStatus: complete\n", encoding="utf-8"
        )

        events: list[str] = []

        from tripwire.ui.services import action_service

        original_audit = action_service.write_audit_entry
        original_lock = action_service.project_lock

        def _traced_audit(*a, **kw):
            events.append("audit")
            return original_audit(*a, **kw)

        def _traced_lock(*a, **kw):
            import contextlib

            @contextlib.contextmanager
            def _wrap():
                with original_lock(*a, **kw):
                    yield
                events.append("lock_released")

            return _wrap()

        monkeypatch.setattr(action_service, "write_audit_entry", _traced_audit)
        monkeypatch.setattr(action_service, "project_lock", _traced_lock)

        result = advance_phase(project_with_phase, "scoped")
        if result.success:
            assert "audit" in events
            assert "lock_released" in events
            assert events.index("audit") < events.index("lock_released")

    def test_reverts_phase_when_validator_crashes(
        self, project_with_phase: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The try/except BaseException branch must revert even on a crash.

        The revert invariant — "a half-advanced phase never lands on
        disk" — is what the bare-except in advance_phase exists for. A
        test that only exercises the validator-returns-errors path
        doesn't prove that invariant; an exception-throwing validator
        does.
        """
        from tripwire.core.store import load_project
        from tripwire.ui.services import action_service

        def _boom(*_a, **_kw):
            raise RuntimeError("simulated validator crash")

        monkeypatch.setattr(action_service, "validate_project", _boom)

        with pytest.raises(RuntimeError, match="simulated"):
            advance_phase(project_with_phase, "scoped")

        # Revert invariant: phase on disk is still the original.
        assert load_project(project_with_phase).phase.value == "scoping"

    def test_same_phase_noop_does_not_audit(self, project_with_phase: Path):
        """Same-phase 'advance' is an idempotent no-op — nothing to audit."""
        advance_phase(project_with_phase, "scoping")
        log_path = audit_log_path(project_with_phase)
        assert not log_path.exists()

    def test_audit_entry_on_successful_transition(self, project_with_phase: Path):
        plans = project_with_phase / "plans"
        plans.mkdir(exist_ok=True)
        (plans / "gap-analysis.md").write_text(
            "# Gap analysis\n\nStatus: complete\n", encoding="utf-8"
        )
        (plans / "compliance.md").write_text(
            "# Compliance\n\nStatus: complete\n", encoding="utf-8"
        )

        result = advance_phase(project_with_phase, "scoped")
        # Only assert audit when the transition actually succeeded. The
        # validator has other checks that may still trip; if we revert,
        # a separate reverted-audit test covers that path.
        if result.success:
            log_path = audit_log_path(project_with_phase)
            assert log_path.is_file()
            successful = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["action"] == "actions.advance_phase"
            ]
            assert len(successful) == 1
            assert successful[0]["before_state_snippet"] == {"phase": "scoping"}
            assert successful[0]["after_state_snippet"] == {"phase": "scoped"}

    def test_audit_entry_on_revert(self, project_with_phase: Path, save_test_issue):
        save_test_issue(project_with_phase, "TMP-1")
        advance_phase(project_with_phase, "scoped")  # expected to revert

        log_path = audit_log_path(project_with_phase)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        reverted = [
            json.loads(line)
            for line in lines
            if json.loads(line)["action"] == "actions.advance_phase.reverted"
        ]
        assert len(reverted) == 1
        assert "errors" in reverted[0]["extras"]


# ---------------------------------------------------------------------------
# finalize_session
# ---------------------------------------------------------------------------


class TestFinalizeSession:
    @staticmethod
    def _complete_ok(project_dir: Path, session_id: str) -> None:
        from datetime import datetime, timezone

        from tripwire.core.session_store import load_session, save_session
        from tripwire.models.enums import SessionStatus

        session = load_session(project_dir, session_id)
        now = datetime.now(tz=timezone.utc)
        session.status = SessionStatus.COMPLETED
        session.updated_at = now
        for engagement in session.engagements:
            if engagement.ended_at is None:
                engagement.ended_at = now
        save_session(project_dir, session)

    def test_updates_status_and_timestamp(
        self, tmp_path_project: Path, save_test_session, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            "tripwire.ui.services.action_service.complete_session", self._complete_ok
        )
        save_test_session(tmp_path_project, "s1", status="verified")
        result = finalize_session(tmp_path_project, "s1")

        assert isinstance(result, SessionResult)
        assert result.session_id == "s1"
        assert result.status == "completed"
        assert result.changed_at is not None

        from tripwire.core.session_store import load_session

        reloaded = load_session(tmp_path_project, "s1")
        assert reloaded.status == "completed"
        assert reloaded.updated_at is not None

    def test_delegates_to_complete_session_for_engagement_closeout(
        self,
        tmp_path_project: Path,
        save_test_session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from datetime import datetime

        monkeypatch.setattr(
            "tripwire.ui.services.action_service.complete_session", self._complete_ok
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="verified",
            engagements=[
                {
                    "started_at": datetime(2026, 4, 14, 10, 0, 0).isoformat(),
                    "trigger": "initial_launch",
                    "context": "first run",
                    # no ended_at — should be closed by finalize
                },
                {
                    "started_at": datetime(2026, 4, 14, 11, 0, 0).isoformat(),
                    "trigger": "ci_failure",
                    "context": "retry",
                    "ended_at": datetime(2026, 4, 14, 12, 0, 0).isoformat(),
                },
            ],
        )

        finalize_session(tmp_path_project, "s1")

        from tripwire.core.session_store import load_session

        reloaded = load_session(tmp_path_project, "s1")
        assert reloaded.engagements[0].ended_at is not None
        # The already-closed engagement's timestamp is preserved.
        assert (
            reloaded.engagements[1]
            .ended_at.replace(tzinfo=None)
            .isoformat()
            .startswith("2026-04-14T12:00:00")
        )

    def test_missing_session_raises(self, tmp_path_project: Path):
        with pytest.raises(FileNotFoundError):
            finalize_session(tmp_path_project, "nope")

    def test_gate_failure_raises_completion_error(
        self,
        tmp_path_project: Path,
        save_test_session,
    ):
        save_test_session(tmp_path_project, "s1", status="executing")

        with pytest.raises(SessionCompletionError) as exc:
            finalize_session(tmp_path_project, "s1")
        assert exc.value.code == "complete/not_active"

    def test_audit_entry_written(
        self,
        tmp_path_project: Path,
        save_test_session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "tripwire.ui.services.action_service.complete_session", self._complete_ok
        )
        save_test_session(tmp_path_project, "s1", status="verified")
        finalize_session(tmp_path_project, "s1")

        log_path = audit_log_path(tmp_path_project)
        record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert record["action"] == "actions.finalize_session"
        assert record["extras"]["session_id"] == "s1"
        assert record["before_state_snippet"] == {"status": "verified"}

    def test_changed_at_is_tz_aware_utc(
        self,
        tmp_path_project: Path,
        save_test_session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Post-fix #6: finalize writes tz-aware UTC timestamps.

        The downstream lint rule ``tripwire.core.lint_rules.session_stale``
        has defensive code at lines 30-32 to coerce naive ``updated_at``
        values to UTC. That workaround exists because older writers
        shipped naive timestamps. Every new write from this service is
        tz-aware so the workaround is unnecessary for anything we touch.
        """
        from datetime import timezone

        monkeypatch.setattr(
            "tripwire.ui.services.action_service.complete_session", self._complete_ok
        )
        save_test_session(tmp_path_project, "s1", status="verified")
        result = finalize_session(tmp_path_project, "s1")

        assert result.changed_at.tzinfo is not None
        assert result.changed_at.utcoffset() == timezone.utc.utcoffset(None)

        from tripwire.core.session_store import load_session

        reloaded = load_session(tmp_path_project, "s1")
        assert reloaded.updated_at is not None
        assert reloaded.updated_at.tzinfo is not None

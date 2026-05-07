"""Layer-3 coherence validator: session.status vs. referenced issue statuses.

See src/tripwire/core/validator.py:check_session_issue_coherence.
"""

from pathlib import Path

from tripwire.core.validator import (
    _COHERENCE_MATRIX,
    _SESSION_STATUS_TO_PHASE,
    validate_project,
)


def test_matrix_shape_matches_spec_5_phases():
    """Matrix is keyed by canonical (v0.9.4) phases — no extras."""
    expected_phases = {"planned", "executing", "in_review", "verified", "completed"}
    assert set(_COHERENCE_MATRIX.keys()) == expected_phases


def test_matrix_rows_cover_all_issue_statuses():
    """Every phase row must list every canonical issue status."""
    expected_issue_statuses = {
        "planned",
        "queued",
        "executing",
        "in_review",
        "verified",
        "completed",
    }
    for phase, row in _COHERENCE_MATRIX.items():
        missing = expected_issue_statuses - set(row.keys())
        assert not missing, f"matrix row {phase!r} missing: {missing}"


def test_session_status_to_phase_maps_all_in_lifecycle_statuses():
    """v0.9.4: queued/executing collapse to executing-phase; completed → completed."""
    assert _SESSION_STATUS_TO_PHASE["planned"] == "planned"
    assert _SESSION_STATUS_TO_PHASE["queued"] == "executing"
    assert _SESSION_STATUS_TO_PHASE["executing"] == "executing"
    assert _SESSION_STATUS_TO_PHASE["in_review"] == "in_review"
    assert _SESSION_STATUS_TO_PHASE["verified"] == "verified"
    assert _SESSION_STATUS_TO_PHASE["completed"] == "completed"
    # Off-lifecycle statuses deliberately absent (failed/paused/abandoned).
    assert "failed" not in _SESSION_STATUS_TO_PHASE
    assert "paused" not in _SESSION_STATUS_TO_PHASE
    assert "abandoned" not in _SESSION_STATUS_TO_PHASE
    # Pruned dead aliases — no longer in the canonical SessionStatus enum.
    assert "active" not in _SESSION_STATUS_TO_PHASE
    assert "re_engaged" not in _SESSION_STATUS_TO_PHASE


def test_issue_behind_session_is_error(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    """Session in_review + issue still queued → error (session is past the issue)."""
    save_test_issue(tmp_path_project, "TMP-1", status="queued")
    save_test_session(
        tmp_path_project,
        "session-one",
        issues=["TMP-1"],
        status="in_review",
    )

    report = validate_project(tmp_path_project)
    codes = [f.code for f in report.findings]
    assert "coherence/issue_status_lags_session" in codes
    lags = [
        f for f in report.findings if f.code == "coherence/issue_status_lags_session"
    ]
    assert lags[0].severity == "error"


def test_issue_ahead_of_session_is_warning(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    """Session executing + issue already completed → warning (issue ran ahead)."""
    save_test_issue(tmp_path_project, "TMP-1", status="completed")
    save_test_session(
        tmp_path_project,
        "session-one",
        issues=["TMP-1"],
        status="executing",
    )

    report = validate_project(tmp_path_project)
    codes = [f.code for f in report.findings]
    assert "coherence/issue_status_ahead_of_session" in codes
    ahead = [
        f
        for f in report.findings
        if f.code == "coherence/issue_status_ahead_of_session"
    ]
    assert ahead[0].severity == "warning"


def test_coherence_passes_when_aligned(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    """Session executing + issue executing → no coherence finding."""
    save_test_issue(tmp_path_project, "TMP-1", status="executing")
    save_test_session(
        tmp_path_project,
        "session-one",
        issues=["TMP-1"],
        status="executing",
    )

    report = validate_project(tmp_path_project)
    codes = [f.code for f in report.findings]
    assert "coherence/issue_status_lags_session" not in codes
    assert "coherence/issue_status_ahead_of_session" not in codes


def test_coherence_skips_off_lifecycle_statuses(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    """Session.status == 'failed' is not in the matrix → no finding emitted."""
    save_test_issue(tmp_path_project, "TMP-1", status="queued")
    save_test_session(
        tmp_path_project,
        "session-one",
        issues=["TMP-1"],
        status="failed",
    )

    report = validate_project(tmp_path_project)
    codes = [f.code for f in report.findings]
    assert "coherence/issue_status_lags_session" not in codes
    assert "coherence/issue_status_ahead_of_session" not in codes


def test_planned_session_with_in_progress_issue_warns_ahead(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    """Regression for KUI-158 §A1: planned sessions must run the coherence rule.

    Pre-fix, ``_SESSION_STATUS_TO_PHASE`` keyed on ``"planning"`` while
    ``SessionStatus.PLANNED = "planned"``, so the lookup missed and the
    rule silently skipped every planned session. Asserts the rule now
    fires ``ahead_warn`` when an issue is past the session's planning
    phase.
    """
    save_test_issue(tmp_path_project, "TMP-1", status="executing")
    save_test_session(
        tmp_path_project,
        "session-one",
        issues=["TMP-1"],
        status="planned",
    )

    report = validate_project(tmp_path_project)
    codes = [f.code for f in report.findings]
    assert "coherence/issue_status_ahead_of_session" in codes
    ahead = [
        f
        for f in report.findings
        if f.code == "coherence/issue_status_ahead_of_session"
    ]
    assert ahead[0].severity == "warning"

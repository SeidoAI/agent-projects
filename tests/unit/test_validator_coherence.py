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
    """Matrix is keyed by spec §6.4's 5 phases — no extras."""
    expected_phases = {"planning", "in_progress", "in_review", "verified", "done"}
    assert set(_COHERENCE_MATRIX.keys()) == expected_phases


def test_matrix_rows_cover_all_issue_statuses():
    """Every phase row must list every known issue status."""
    expected_issue_statuses = {
        "backlog",
        "todo",
        "in_progress",
        "in_review",
        "verified",
        "done",
    }
    for phase, row in _COHERENCE_MATRIX.items():
        missing = expected_issue_statuses - set(row.keys())
        assert not missing, f"matrix row {phase!r} missing: {missing}"


def test_session_status_to_phase_maps_all_in_lifecycle_statuses():
    """Working states (queued/executing/active) collapse to in_progress; completed → done."""
    assert _SESSION_STATUS_TO_PHASE["planning"] == "planning"
    assert _SESSION_STATUS_TO_PHASE["queued"] == "in_progress"
    assert _SESSION_STATUS_TO_PHASE["executing"] == "in_progress"
    assert _SESSION_STATUS_TO_PHASE["active"] == "in_progress"
    assert _SESSION_STATUS_TO_PHASE["in_review"] == "in_review"
    assert _SESSION_STATUS_TO_PHASE["verified"] == "verified"
    assert _SESSION_STATUS_TO_PHASE["completed"] == "done"
    # Off-lifecycle statuses deliberately absent.
    assert "failed" not in _SESSION_STATUS_TO_PHASE
    assert "paused" not in _SESSION_STATUS_TO_PHASE
    assert "abandoned" not in _SESSION_STATUS_TO_PHASE
    assert "re_engaged" not in _SESSION_STATUS_TO_PHASE


def test_issue_behind_session_is_error(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    """Session in_review + issue still todo → error (session is past the issue)."""
    save_test_issue(tmp_path_project, "TMP-1", status="todo")
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
    """Session in_progress + issue already done → warning (issue ran ahead)."""
    save_test_issue(tmp_path_project, "TMP-1", status="done")
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
    """Session executing + issue in_progress → no coherence finding."""
    save_test_issue(tmp_path_project, "TMP-1", status="in_progress")
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
    save_test_issue(tmp_path_project, "TMP-1", status="todo")
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

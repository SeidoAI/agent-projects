"""session_complete gate logic."""

from pathlib import Path

import pytest

from tripwire.core.session_complete import CompleteError, complete_session


def test_complete_refuses_non_completable_status(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1", status="planned")
    with pytest.raises(CompleteError) as exc:
        complete_session(tmp_path_project, "s1", dry_run=True)
    assert exc.value.code == "complete/not_active"


def test_complete_refuses_without_artifacts(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    with pytest.raises(CompleteError) as exc:
        complete_session(
            tmp_path_project,
            "s1",
            dry_run=True,
            skip_pr_merge_check=True,
        )
    assert exc.value.code == "complete/missing_artifacts"


def test_complete_dry_run_passes_when_artifacts_present(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    result = complete_session(
        tmp_path_project,
        "s1",
        dry_run=True,
        skip_pr_merge_check=True,
    )
    assert result.session_id == "s1"


def test_complete_closes_issues_and_transitions_session(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    result = complete_session(
        tmp_path_project,
        "s1",
        skip_pr_merge_check=True,
        skip_worktree_cleanup=True,
    )
    assert "TMP-1" in result.issues_closed

    from tripwire.core.session_store import load_session
    from tripwire.core.store import load_issue

    issue = load_issue(tmp_path_project, "TMP-1")
    assert issue.status == "done"
    session = load_session(tmp_path_project, "s1")
    assert session.status == "done"


def test_complete_force_bypasses_gates(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="planned")
    result = complete_session(
        tmp_path_project,
        "s1",
        force=True,
        dry_run=True,
        skip_pr_merge_check=True,
        skip_artifact_check=True,
    )
    assert result.session_id == "s1"

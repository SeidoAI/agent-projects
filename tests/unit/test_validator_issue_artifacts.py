"""Validator check_issue_artifact_presence — enforces developer/verified files."""

from pathlib import Path

from tripwire.core.validator import validate_project


def test_issue_at_in_review_missing_developer_errors(
    tmp_path_project: Path, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    # No developer.md written.

    report = validate_project(tmp_path_project)
    missing = [
        f
        for f in report.findings
        if f.code == "issue_artifact/missing" and "developer.md" in f.message
    ]
    assert missing, "expected issue_artifact/missing for developer.md"
    assert missing[0].severity == "error"


def test_issue_at_verified_missing_verified_errors(
    tmp_path_project: Path, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="verified")
    # Write developer.md so only verified.md is missing.
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )

    report = validate_project(tmp_path_project)
    missing = [
        f
        for f in report.findings
        if f.code == "issue_artifact/missing" and "verified.md" in f.message
    ]
    assert missing, "expected issue_artifact/missing for verified.md"


def test_issue_at_todo_no_artifacts_required(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, "TMP-1", status="todo")
    report = validate_project(tmp_path_project)
    codes = [f.code for f in report.findings]
    assert "issue_artifact/missing" not in codes


def test_issue_at_in_review_with_developer_present_passes(
    tmp_path_project: Path, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    report = validate_project(tmp_path_project)
    # verified.md isn't required at in_review — only at verified.
    dev_missing = [
        f
        for f in report.findings
        if f.code == "issue_artifact/missing" and "developer.md" in f.message
    ]
    assert not dev_missing


def test_issue_at_done_requires_both(tmp_path_project: Path, save_test_issue):
    """Status `done` is past `in_review` and `verified`, so both are required."""
    save_test_issue(tmp_path_project, "TMP-1", status="done")
    report = validate_project(tmp_path_project)
    messages = [
        f.message for f in report.findings if f.code == "issue_artifact/missing"
    ]
    assert any("developer.md" in m for m in messages)
    assert any("verified.md" in m for m in messages)

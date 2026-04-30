"""KUI-147 (D5) — mega_issue lint.

Warns when an issue accretes too many children (sub-issues whose
``parent`` field points at it) OR too many sessions implementing it,
suggesting it ought to be broken down. Thresholds come from
``_thresholds.DEFAULT_THRESHOLDS['mega_issue']``.
"""

from pathlib import Path

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import mega_issue


def test_warns_when_children_exceed_threshold(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, key="TMP-1")
    # Default max_children=8, so 9 children fires.
    for n in range(9):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 2}", parent="TMP-1")

    ctx = load_context(tmp_path_project)
    results = mega_issue.check(ctx)
    codes = [r.code for r in results]
    assert "mega_issue/too_many_children" in codes


def test_no_warning_at_threshold(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, key="TMP-1")
    for n in range(8):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 2}", parent="TMP-1")

    ctx = load_context(tmp_path_project)
    assert mega_issue.check(ctx) == []


def test_warns_when_sessions_exceed_threshold(
    tmp_path_project: Path, save_test_issue, save_test_session
):
    save_test_issue(tmp_path_project, key="TMP-1")
    # Default max_sessions=6, so 7 sessions fires.
    for n in range(7):
        save_test_session(
            tmp_path_project,
            session_id=f"s-{n}",
            issues=["TMP-1"],
        )

    ctx = load_context(tmp_path_project)
    results = mega_issue.check(ctx)
    assert any(r.code == "mega_issue/too_many_sessions" for r in results)


def test_no_warning_when_issue_has_no_children(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, key="TMP-1")
    ctx = load_context(tmp_path_project)
    assert mega_issue.check(ctx) == []

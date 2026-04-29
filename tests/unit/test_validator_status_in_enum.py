"""Tests for the upstream-enum status check rules (KUI-110 Phase 2.4).

These rules are the belt-and-suspenders layer that catches statuses
which slipped past Pydantic (e.g. hand-edited YAML on disk) and which
would have validated against a drifted project-side enum YAML. They
assert the upstream Python enum (`SessionStatus`, `IssueStatus`) is the
floor, regardless of how the project's enum YAML has been customised.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.validator import validate_project
from tests.unit.test_validator import (  # type: ignore[import-not-found]
    write_issue,
    write_project_yaml,
    write_session,
)


def test_session_with_invalid_status_flagged(tmp_path: Path) -> None:
    """A session with status not in SessionStatus → status/invalid_enum error."""
    write_project_yaml(tmp_path)
    write_session(tmp_path, "good-sess", status="executing")
    write_session(tmp_path, "bad-sess", status="nonsense_value")

    report = validate_project(tmp_path, strict=True, fix=False)

    codes = [r.code for r in report.errors]
    assert "status/invalid_enum" in codes, (
        f"expected 'status/invalid_enum' in errors, got codes={codes}"
    )
    matches = [r for r in report.errors if r.code == "status/invalid_enum"]
    files = [m.file for m in matches]
    assert any("bad-sess" in (f or "") for f in files), (
        f"expected error on bad-sess, got files={files}"
    )
    assert not any("good-sess" in (f or "") for f in files), (
        f"good-sess should not be flagged, got files={files}"
    )


def test_session_with_legacy_done_status_flagged(tmp_path: Path) -> None:
    """`status: done` is the exact failure mode that motivated this rule."""
    write_project_yaml(tmp_path)
    # Bypass Pydantic by hand-writing the YAML — uses write_session directly.
    write_session(tmp_path, "legacy-done", status="done")

    report = validate_project(tmp_path, strict=True, fix=False)

    codes_for_legacy = [
        r.code for r in report.errors if "legacy-done" in (r.file or "")
    ]
    assert "status/invalid_enum" in codes_for_legacy


def test_issue_with_invalid_status_flagged(tmp_path: Path) -> None:
    """An issue with status not in IssueStatus → status/invalid_enum error."""
    write_project_yaml(tmp_path)
    write_issue(tmp_path, "TST-1", status="todo")
    write_issue(tmp_path, "TST-2", status="ghost_state")

    report = validate_project(tmp_path, strict=True, fix=False)

    matches = [r for r in report.errors if r.code == "status/invalid_enum"]
    flagged_files = [m.file for m in matches]
    assert any("TST-2" in (f or "") for f in flagged_files), (
        f"expected error on TST-2, got files={flagged_files}"
    )
    assert not any("TST-1" in (f or "") for f in flagged_files)


def test_valid_status_no_error(tmp_path: Path) -> None:
    """Sessions and issues at upstream-canonical statuses pass clean."""
    write_project_yaml(tmp_path)
    write_session(tmp_path, "ok-sess", status="completed")
    write_issue(tmp_path, "TST-3", status="done")  # done IS valid for issues

    report = validate_project(tmp_path, strict=True, fix=False)

    invalid_enum_errors = [r for r in report.errors if r.code == "status/invalid_enum"]
    assert invalid_enum_errors == [], (
        f"expected no status/invalid_enum errors, got "
        f"{[(r.file, r.message) for r in invalid_enum_errors]}"
    )

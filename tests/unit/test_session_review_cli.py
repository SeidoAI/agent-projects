"""tripwire session review CLI."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _stub_gh(*_args, **_kwargs):
    """Stub `subprocess.run` for all review-time gh/git calls — no network."""

    class _Result:
        returncode = 1
        stdout = ""

    return _Result()


def test_review_empty_session(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="in_review")
    runner = CliRunner()
    with patch("tripwire.cli.session.subprocess.run", side_effect=_stub_gh):
        result = runner.invoke(
            session_cmd,
            [
                "review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--no-write-verified",
                "--no-post-pr-comments",
            ],
        )
    # No issues → clean verdict → exit 0
    assert result.exit_code == 0, result.output
    assert "Session Review: s1" in result.output
    assert "approved" in result.output


def test_review_with_issue_writes_verified(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    save_test_session(tmp_path_project, "s1", status="in_review", issues=["TMP-1"])
    runner = CliRunner()
    with patch("tripwire.cli.session.subprocess.run", side_effect=_stub_gh):
        result = runner.invoke(
            session_cmd,
            [
                "review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--no-post-pr-comments",
            ],
        )
    assert result.exit_code in (
        0,
        1,
    ), result.output  # may emit notes due to zero PR files
    verified = tmp_path_project / "issues" / "TMP-1" / "verified.md"
    assert verified.is_file()
    text = verified.read_text(encoding="utf-8")
    assert "Verified by" in text


def test_review_writes_review_json(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="in_review")
    runner = CliRunner()
    with patch("tripwire.cli.session.subprocess.run", side_effect=_stub_gh):
        result = runner.invoke(
            session_cmd,
            [
                "review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--no-write-verified",
                "--no-post-pr-comments",
            ],
        )
    # Exit 0 when no issues / no PR files — report is "approved".
    assert result.exit_code == 0, result.output
    review_path = tmp_path_project / "sessions" / "s1" / "review.json"
    assert review_path.is_file()
    import json as _json

    data = _json.loads(review_path.read_text(encoding="utf-8"))
    assert data["session_id"] == "s1"
    assert data["verdict"] in {"approved", "approved_with_notes", "rejected"}
    assert "exit_code" in data
    assert "timestamp" in data


def test_review_verified_md_rendered_from_template(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    save_test_session(tmp_path_project, "s1", status="in_review", issues=["TMP-1"])
    runner = CliRunner()
    with patch("tripwire.cli.session.subprocess.run", side_effect=_stub_gh):
        result = runner.invoke(
            session_cmd,
            [
                "review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--no-post-pr-comments",
            ],
        )
    assert result.exit_code in (0, 1), result.output
    verified = tmp_path_project / "issues" / "TMP-1" / "verified.md"
    assert verified.is_file()
    text = verified.read_text(encoding="utf-8")
    # Header from the template.
    assert "# Verification notes — TMP-1" in text
    # Field labels from the template (not the hand-crafted inline content).
    assert "**Verified by**:" in text
    assert "**Verified at**:" in text
    assert "**Verdict**:" in text
    # Section headings from the template.
    assert "## Deviations found" in text
    assert "## Follow-up issues created" in text


def test_review_json_output(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="in_review")
    runner = CliRunner()
    with patch("tripwire.cli.session.subprocess.run", side_effect=_stub_gh):
        result = runner.invoke(
            session_cmd,
            [
                "review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--format",
                "json",
                "--no-write-verified",
                "--no-post-pr-comments",
            ],
        )
    import json as _json

    data = _json.loads(result.output)
    assert data["session_id"] == "s1"
    assert "verdict" in data

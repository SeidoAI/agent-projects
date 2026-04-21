"""tripwire issue CLI — artifact list/init/verify."""

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.issue import issue_cmd


def test_issue_artifact_list_shows_missing(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")

    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        ["artifact", "list", "TMP-1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "developer.md" in result.output
    assert "MISSING" in result.output


def test_issue_artifact_list_json(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        [
            "artifact",
            "list",
            "TMP-1",
            "--project-dir",
            str(tmp_path_project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    import json

    rows = json.loads(result.output)
    names = {r["name"] for r in rows}
    assert "developer" in names


def test_issue_artifact_init_writes_file(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        [
            "artifact",
            "init",
            "TMP-1",
            "developer",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path_project / "issues" / "TMP-1" / "developer.md").is_file()


def test_issue_artifact_init_refuses_overwrite(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# existing\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        [
            "artifact",
            "init",
            "TMP-1",
            "developer",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code != 0
    assert (
        "already exists" in result.output
        or "already exists" in (result.stderr_bytes or b"").decode()
    )


def test_issue_artifact_init_unknown_artifact(tmp_path_project: Path, save_test_issue):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        [
            "artifact",
            "init",
            "TMP-1",
            "nonesuch",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code != 0


def test_issue_artifact_verify_exits_1_when_missing(
    tmp_path_project: Path, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        [
            "artifact",
            "verify",
            "TMP-1",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 1
    assert "MISSING" in result.output


def test_issue_artifact_verify_passes_when_present(
    tmp_path_project: Path, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    runner = CliRunner()
    result = runner.invoke(
        issue_cmd,
        [
            "artifact",
            "verify",
            "TMP-1",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0

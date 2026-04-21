"""tripwire session monitor CLI."""

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def test_monitor_empty_project(tmp_path_project: Path):
    runner = CliRunner()
    result = runner.invoke(
        session_cmd, ["monitor", "--project-dir", str(tmp_path_project)]
    )
    assert result.exit_code == 0
    assert (
        "no executing sessions" in result.output.lower()
        or "no sessions" in result.output.lower()
    )


def test_monitor_specific_session(tmp_path_project: Path, save_test_session):
    save_test_session(
        tmp_path_project,
        "s1",
        status="executing",
        runtime_state={"claude_session_id": "sid"},
    )
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["monitor", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "s1" in result.output


def test_monitor_json_format(tmp_path_project: Path, save_test_session):
    save_test_session(
        tmp_path_project,
        "s1",
        status="executing",
        runtime_state={"claude_session_id": "sid"},
    )
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "monitor",
            "s1",
            "--project-dir",
            str(tmp_path_project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    import json

    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["session_id"] == "s1"


def test_monitor_defaults_to_executing_only(tmp_path_project: Path, save_test_session):
    save_test_session(
        tmp_path_project,
        "s1",
        status="executing",
        runtime_state={"claude_session_id": "sid"},
    )
    save_test_session(tmp_path_project, "s2", status="planned")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd, ["monitor", "--project-dir", str(tmp_path_project)]
    )
    assert result.exit_code == 0
    assert "s1" in result.output
    assert "s2" not in result.output

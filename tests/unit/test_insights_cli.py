"""tripwire session insights CLI — list / apply / reject."""

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.insights_store import load_insights, save_insights
from tripwire.models.insights import InsightsFile, NodeProposal


def test_insights_list_prints_proposals(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1")
    save_insights(
        tmp_path_project,
        "s1",
        InsightsFile(
            proposals=[
                NodeProposal(
                    kind="new_node",
                    id="pg-tuning",
                    name="PG Tuning",
                    body="body",
                    rationale="useful",
                )
            ]
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["insights", "list", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "pg-tuning" in result.output


def test_insights_list_empty(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["insights", "list", "s1", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0
    assert "No insight proposals" in result.output


def test_insights_apply_new_node_writes_file(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1")
    save_insights(
        tmp_path_project,
        "s1",
        InsightsFile(
            proposals=[
                NodeProposal(
                    kind="new_node",
                    id="pg-tuning",
                    name="PG Tuning",
                    body="tuning notes",
                    rationale="useful",
                )
            ]
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "insights",
            "apply",
            "s1",
            "--proposal",
            "pg-tuning",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path_project / "nodes" / "pg-tuning.yaml").is_file()

    # Applied proposal removed from insights.yaml
    remaining = load_insights(tmp_path_project, "s1")
    assert remaining.proposals == []


def test_insights_apply_update_node_appends_delta(
    tmp_path_project: Path, save_test_session, save_test_node
):
    save_test_session(tmp_path_project, "s1")
    save_test_node(
        tmp_path_project,
        "auth-system",
        body="Original description.\n",
    )
    save_insights(
        tmp_path_project,
        "s1",
        InsightsFile(
            proposals=[
                NodeProposal(
                    kind="update_node",
                    id="auth-system",
                    delta="added refresh token rotation",
                    rationale="security gap",
                )
            ]
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "insights",
            "apply",
            "s1",
            "--proposal",
            "auth-system",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output

    node_text = (tmp_path_project / "nodes" / "auth-system.yaml").read_text(
        encoding="utf-8"
    )
    assert "Original description" in node_text
    assert "added refresh token rotation" in node_text
    assert "## Updated" in node_text


def test_insights_reject_records_rejection(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1")
    save_insights(
        tmp_path_project,
        "s1",
        InsightsFile(
            proposals=[
                NodeProposal(
                    kind="new_node",
                    id="meh-node",
                    name="Meh",
                    body="x",
                    rationale="too vague",
                )
            ]
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "insights",
            "reject",
            "s1",
            "--proposal",
            "meh-node",
            "--reason",
            "redundant with existing node",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output

    # Proposal removed from insights.yaml
    remaining = load_insights(tmp_path_project, "s1")
    assert remaining.proposals == []

    # Rejection recorded
    rej_path = tmp_path_project / "sessions" / "s1" / "insights.rejected.yaml"
    assert rej_path.is_file()
    assert "meh-node" in rej_path.read_text(encoding="utf-8")


def test_insights_apply_unknown_proposal(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "insights",
            "apply",
            "s1",
            "--proposal",
            "does-not-exist",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code != 0


def test_insights_apply_update_without_existing_node(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1")
    save_insights(
        tmp_path_project,
        "s1",
        InsightsFile(
            proposals=[
                NodeProposal(
                    kind="update_node",
                    id="nonexistent-node",
                    delta="x",
                    rationale="y",
                )
            ]
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "insights",
            "apply",
            "s1",
            "--proposal",
            "nonexistent-node",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code != 0

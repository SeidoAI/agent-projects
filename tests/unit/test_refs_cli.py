"""keel refs check: ref-integrity subcommand.

v0.6a: refs check already existed from v0.5 refactor, but now exits
non-zero on integrity errors (dangling refs, stale nodes).
"""

from click.testing import CliRunner

from keel.cli.refs import refs_cmd


def test_refs_check_exits_zero_on_clean_project(tmp_path_project):
    runner = CliRunner()
    result = runner.invoke(refs_cmd, ["check", "--project-dir", str(tmp_path_project)])
    assert result.exit_code == 0, result.output


def test_refs_check_reports_broken_ref(save_test_issue, tmp_path_project):
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        kind="feat",
        title="One",
        blocked_by=[],
        body="## Context\nReferences [[nonexistent-node]].\n",
    )
    runner = CliRunner()
    result = runner.invoke(
        refs_cmd,
        ["check", "--project-dir", str(tmp_path_project), "--format", "json"],
    )
    import json as _json

    assert result.exit_code != 0, result.output
    payload = _json.loads(result.output)
    assert any(d["ref"] == "nonexistent-node" for d in payload["dangling"]), payload

"""Spawn refuses to launch when any strict tripwire fires (§A6).

Asserts the no-bypass guarantee end-to-end: session spawn calls
strict_check before mutating the filesystem; any error-severity result
exits non-zero with the error code in output. There is no flag that
opts out.
"""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


class TestSpawnCallsStrictCheckFirst:
    def test_spawn_rejects_session_with_no_repos(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        save_test_issue(tmp_path_project, key="TMP-1")
        save_test_session(
            tmp_path_project,
            "s-no-repos",
            issues=["TMP-1"],
            repos=[],
            status="queued",
            plan=True,
        )
        write_handoff_yaml(tmp_path_project, "s-no-repos")

        with patch("shutil.which", return_value="/usr/bin/claude"):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s-no-repos", "--project-dir", str(tmp_path_project)],
            )
        assert result.exit_code != 0
        # Error code must appear so PMs know exactly what fired.
        assert "check/no_repos" in result.output

    def test_spawn_rejects_placeholder_plan(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        save_test_issue(tmp_path_project, key="TMP-1")
        save_test_session(
            tmp_path_project,
            "s-placeholder",
            issues=["TMP-1"],
            repos=[{"repo": "example/code", "base_branch": "main"}],
            status="queued",
        )
        write_handoff_yaml(tmp_path_project, "s-placeholder")
        # Write a scaffold-only plan.md.
        (tmp_path_project / "sessions" / "s-placeholder" / "plan.md").write_text(
            "# Plan — <session-id>\n\n## Goal\nWhat is this session trying "
            "to achieve, in one paragraph?\n",
            encoding="utf-8",
        )

        with patch("shutil.which", return_value="/usr/bin/claude"):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s-placeholder", "--project-dir", str(tmp_path_project)],
            )
        assert result.exit_code != 0
        assert "check/plan_unfilled" in result.output

    def test_no_bypass_flag_exists(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["spawn", "--help"]
        )
        assert result.exit_code == 0
        # Per §A4: no --force, no --skip-* on spawn.
        assert "--force" not in result.output
        assert "--skip-" not in result.output
        assert "--bypass" not in result.output


class TestSessionCheckReportsStrictResults:
    def test_check_command_surfaces_error_codes(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        save_test_issue(tmp_path_project, key="TMP-1")
        save_test_session(
            tmp_path_project,
            "s-check",
            issues=["TMP-1"],
            repos=[],
            status="planned",
            plan=True,
        )
        write_handoff_yaml(tmp_path_project, "s-check")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["check", "s-check", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "check/no_repos" in result.output

    def test_check_json_includes_strict_results(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        import json

        save_test_issue(tmp_path_project, key="TMP-1")
        save_test_session(
            tmp_path_project,
            "s-check-json",
            issues=["TMP-1"],
            repos=[],
            status="planned",
            plan=True,
        )
        write_handoff_yaml(tmp_path_project, "s-check-json")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "check",
                "s-check-json",
                "--project-dir",
                str(tmp_path_project),
                "--format",
                "json",
            ],
        )
        # Even when strict checks fail, the JSON body should be parseable.
        payload = json.loads(result.output)
        assert "strict_checks" in payload
        codes = [c["error_code"] for c in payload["strict_checks"]]
        assert "check/no_repos" in codes

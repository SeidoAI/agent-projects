"""Tests for `tripwire session show <sid>` artifact summary (v0.7.9 §A2).

The plain `show` output (text format) appends a brief summary
showing whether self-review.md and pm-response.yaml are committed to
the session directory. ``--full`` expands them inline. The intent is
to keep the default output readable while signalling presence.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _write_files(project_dir: Path, sid: str) -> None:
    sdir = project_dir / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "self-review.md").write_text(
        "## Lens 1: AC\n- something\n", encoding="utf-8"
    )
    (sdir / "pm-response.yaml").write_text(
        "items:\n"
        '  - quote_excerpt: "something"\n'
        "    decision: accepted\n",
        encoding="utf-8",
    )


class TestSessionShowReviewSummary:
    def test_default_shows_collapsed_summary_when_files_present(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _write_files(tmp_path_project, "s1")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["show", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        # Existence indicators appear; full content does NOT.
        assert "self-review.md" in result.output
        assert "pm-response.yaml" in result.output
        # The actual bullet from self-review.md must NOT appear in
        # collapsed output.
        assert "- something" not in result.output

    def test_default_signals_missing_files(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        # No artifacts on disk.
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["show", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        # Both files mentioned, with a missing marker.
        out = result.output
        assert "self-review.md" in out
        assert "pm-response.yaml" in out
        assert "missing" in out.lower()

    def test_full_flag_expands_file_contents(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _write_files(tmp_path_project, "s1")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "show",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--full",
            ],
        )
        assert result.exit_code == 0, result.output
        # With --full, the literal bullet from self-review must appear.
        assert "- something" in result.output
        # And the pm-response decision should be visible.
        assert "decision: accepted" in result.output

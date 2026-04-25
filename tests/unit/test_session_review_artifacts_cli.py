"""CLI tests for `tripwire session review-artifacts <sid>`.

Renders self-review.md + pm-response.yaml side-by-side, marks
unaddressed self-review items, supports `--format human` (default) and
`--format json`. See decisions.md for why this is a sibling subcommand
rather than the existing `session review`.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _write_self_review(project_dir: Path, sid: str, body: str) -> None:
    sdir = project_dir / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "self-review.md").write_text(body, encoding="utf-8")


def _write_pm_response(project_dir: Path, sid: str, body: str) -> None:
    sdir = project_dir / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "pm-response.yaml").write_text(body, encoding="utf-8")


class TestSessionReviewArtifactsHuman:
    def test_renders_pairs_in_human_format(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _write_self_review(
            tmp_path_project,
            "s1",
            "## Lens 1: AC\n- alpha point\n- beta point\n",
        )
        _write_pm_response(
            tmp_path_project,
            "s1",
            "items:\n"
            '  - quote_excerpt: "alpha"\n'
            "    decision: accepted\n"
            '  - quote_excerpt: "beta"\n'
            "    decision: deferred\n"
            "    follow_up: KUI-91\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "review-artifacts",
                "s1",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "alpha point" in result.output
        assert "beta point" in result.output
        assert "accepted" in result.output
        assert "deferred" in result.output

    def test_marks_unaddressed_items(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _write_self_review(
            tmp_path_project,
            "s1",
            "## Lens 1: AC\n- covered item\n- orphan item\n",
        )
        _write_pm_response(
            tmp_path_project,
            "s1",
            "items:\n"
            '  - quote_excerpt: "covered"\n'
            "    decision: accepted\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "review-artifacts",
                "s1",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "orphan item" in result.output
        # Some explicit "unaddressed" / "no response" marker — robust to
        # phrasing tweaks but must signal the gap.
        assert "unaddressed" in result.output.lower()

    def test_missing_self_review_emits_clear_hint(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        # No artifacts written.
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "review-artifacts",
                "s1",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        # Command shouldn't crash — emit a clear hint.
        assert result.exit_code == 0, result.output
        assert "self-review.md" in result.output
        assert "missing" in result.output.lower()


class TestSessionReviewArtifactsJson:
    def test_json_format_returns_structured_pairs_and_unaddressed(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _write_self_review(
            tmp_path_project,
            "s1",
            "## Lens 1: AC\n- mypy thing\n- README thing\n",
        )
        _write_pm_response(
            tmp_path_project,
            "s1",
            "items:\n"
            '  - quote_excerpt: "mypy"\n'
            "    decision: accepted\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "review-artifacts",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["session_id"] == "s1"
        assert data["self_review_present"] is True
        assert data["pm_response_present"] is True
        assert len(data["pairs"]) == 2
        assert any(p["pm_response"] is None for p in data["pairs"])
        assert len(data["unaddressed"]) == 1
        assert data["unaddressed"][0]["text"] == "README thing"

"""``tripwire pr status`` CLI (KUI-152).

Reads the most recent ``pm_review.completed`` event for a session and
renders a human-readable status summary — verdict + per-check
pass/fail. Read-only, no mutations.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner


def _scaffold(tmp_path: Path) -> Path:
    """Minimal project + an emitted pm_review.completed event."""
    from tripwire.core.events.log import emit_event

    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\n"
        "statuses: [planned]\nstatus_transitions:\n  planned: []\n"
        "repos: {}\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                stations:
                  - id: planned
                    next: queued
                  - id: queued
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    sd = tmp_path / "sessions" / "demo"
    sd.mkdir(parents=True)
    (sd / "session.yaml").write_text(
        "---\nid: demo\nstatus: in_review\n---\n", encoding="utf-8"
    )
    emit_event(
        tmp_path,
        workflow="pm-review",
        instance="demo",
        station="review",
        event="pm_review.completed",
        details={
            "outcome": "request_changes",
            "failed_checks": ["schema", "refs"],
            "passed_checks": [
                "status_transition",
                "fields",
                "markdown_structure",
                "freshness",
                "artifact_presence",
                "no_orphan_additions",
                "comment_provenance",
                "project_standards",
            ],
        },
    )
    return tmp_path


def test_pr_status_renders_latest_verdict(tmp_path):
    from tripwire.cli.pr import pr_cmd

    pd = _scaffold(tmp_path)
    runner = CliRunner()
    result = runner.invoke(pr_cmd, ["status", "demo", "--project-dir", str(pd)])

    assert result.exit_code == 0, result.output
    assert "request_changes" in result.output
    assert "schema" in result.output
    assert "refs" in result.output
    # Passed checks also surface so the user can see what went well.
    assert "freshness" in result.output


def test_pr_status_no_review_yet(tmp_path):
    """A session with no pm_review.completed event yields an exit-1 message."""
    from tripwire.cli.pr import pr_cmd

    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\n"
        "statuses: [planned]\nstatus_transitions:\n  planned: []\n"
        "repos: {}\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    sd = tmp_path / "sessions" / "demo"
    sd.mkdir(parents=True)
    (sd / "session.yaml").write_text(
        "---\nid: demo\nstatus: in_review\n---\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(pr_cmd, ["status", "demo", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "no pm-review" in result.output.lower()


def test_pr_status_uses_latest_when_multiple(tmp_path):
    """Multiple events: only the latest verdict surfaces."""
    from tripwire.cli.pr import pr_cmd
    from tripwire.core.events.log import emit_event

    pd = _scaffold(tmp_path)
    # Append a newer event flipping the verdict to auto-merge.
    emit_event(
        pd,
        workflow="pm-review",
        instance="demo",
        station="review",
        event="pm_review.completed",
        details={
            "outcome": "auto-merge",
            "failed_checks": [],
            "passed_checks": ["schema", "refs"],
        },
    )

    runner = CliRunner()
    result = runner.invoke(pr_cmd, ["status", "demo", "--project-dir", str(pd)])
    assert result.exit_code == 0, result.output
    assert "auto-merge" in result.output
    # The earlier `request_changes` should NOT be the headline verdict.
    # We assert the latest verdict line by checking it's printed first.
    out = result.output
    auto_idx = out.find("auto-merge")
    rc_idx = out.find("request_changes")
    if rc_idx >= 0:
        assert auto_idx < rc_idx, (
            "headline verdict should be the latest (auto-merge), not "
            "the earlier request_changes"
        )


@pytest.fixture
def runner():
    return CliRunner()

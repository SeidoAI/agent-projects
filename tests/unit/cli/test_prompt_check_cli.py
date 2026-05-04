"""Tests for ``tripwire prompt-check invoke``."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner


def _project_dir(tmp_path: Path) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: queued
                  - id: queued
                    next: executing
                    prompt_checks: [pm-session-queue]
                  - id: executing
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    session_dir = tmp_path / "sessions" / "test-session"
    session_dir.mkdir(parents=True)
    (session_dir / "session.yaml").write_text(
        "---\n"
        "uuid: 11111111-1111-4111-8111-111111111111\n"
        "id: test-session\n"
        "name: Test session\n"
        "agent: backend-coder\n"
        "issues: []\n"
        "repos: []\n"
        "status: planned\n"
        "created_at: 2026-04-30T00:00:00Z\n"
        "updated_at: 2026-04-30T00:00:00Z\n"
        "---\n",
        encoding="utf-8",
    )
    return tmp_path


def test_prompt_check_invoke_emits_workflow_event(tmp_path: Path) -> None:
    from tripwire.cli.prompt_check import prompt_check_cmd
    from tripwire.core.events.log import read_events

    project_dir = _project_dir(tmp_path)
    result = CliRunner().invoke(
        prompt_check_cmd,
        [
            "invoke",
            "pm-session-queue",
            "test-session",
            "--project-dir",
            str(project_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = list(
        read_events(
            project_dir,
            workflow="coding-session",
            instance="test-session",
            status="queued",
            event="prompt_check.invoked",
        )
    )
    assert [row["details"]["id"] for row in rows] == ["pm-session-queue"]


def test_prompt_check_invoke_rejects_undeclared_check(tmp_path: Path) -> None:
    from tripwire.cli.prompt_check import prompt_check_cmd

    project_dir = _project_dir(tmp_path)
    result = CliRunner().invoke(
        prompt_check_cmd,
        [
            "invoke",
            "pm-session-review",
            "test-session",
            "--project-dir",
            str(project_dir),
        ],
    )

    assert result.exit_code != 0
    assert "not declared in workflow.yaml" in result.output

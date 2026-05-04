"""tripwire drift report — single coherence score (KUI-128 / A3).

The drift report computes one 0-100 coherence score from weighted
drift signals that already exist in the project: stale pins,
unresolved refs, stale concept-node freshness, and active workflow
drift findings derived from the KUI-123 event log. Higher = healthier.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner

from tripwire.cli.drift import drift_cmd
from tripwire.core.store import save_issue, save_project
from tripwire.models import Issue, ProjectConfig, RepoEntry


def _make_project(tmp_path: Path) -> Path:
    save_project(
        tmp_path,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"o/r": RepoEntry()},
            next_issue_number=1,
        ),
    )
    return tmp_path


def _save_clean_issue(project_dir: Path, key: str) -> None:
    save_issue(
        project_dir,
        Issue(
            id=key,
            title=key,
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body="No refs in body.\n",
        ),
        update_cache=False,
    )


def _write_workflow(project_dir: Path) -> None:
    (project_dir / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: queued
                    next: executing
                  - id: executing
                    prompt_checks: [pm-session-queue]
                    terminal: true
            """
        ),
        encoding="utf-8",
    )


def test_clean_project_scores_perfect(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _save_clean_issue(tmp_path, "TST-1")
    runner = CliRunner()
    result = runner.invoke(
        drift_cmd,
        ["report", "--project-dir", str(tmp_path), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["score"] == 100
    # Breakdown structure
    assert "breakdown" in payload
    assert payload["breakdown"]["stale_pins"] == 0
    assert payload["breakdown"]["unresolved_refs"] == 0
    assert payload["breakdown"]["workflow_drift_findings"] == 0
    assert "workflow_drift_events" not in payload
    assert payload["workflow_drift_findings"] == []


def test_unresolved_refs_drop_the_score(tmp_path: Path) -> None:
    _make_project(tmp_path)
    save_issue(
        tmp_path,
        Issue(
            id="TST-1",
            title="t",
            status="todo",
            priority="medium",
            executor="ai",
            verifier="required",
            body="See [[nonexistent-target]].\n",
        ),
        update_cache=False,
    )
    runner = CliRunner()
    result = runner.invoke(
        drift_cmd,
        ["report", "--project-dir", str(tmp_path), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["score"] < 100
    assert payload["breakdown"]["unresolved_refs"] >= 1


def test_workflow_drift_findings_drop_the_score(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event

    _make_project(tmp_path)
    _save_clean_issue(tmp_path, "TST-1")
    _write_workflow(tmp_path)
    emit_event(
        tmp_path,
        workflow="coding-session",
        instance="session-a",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    runner = CliRunner()
    result = runner.invoke(
        drift_cmd,
        ["report", "--project-dir", str(tmp_path), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["score"] == 98
    assert payload["breakdown"]["workflow_drift_findings"] == 1
    assert payload["workflow_drift_findings"][0]["code"] == (
        "drift/prompt_check_missing"
    )


def test_text_output_includes_score_headline(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _save_clean_issue(tmp_path, "TST-1")
    runner = CliRunner()
    result = runner.invoke(
        drift_cmd,
        ["report", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "100" in result.output
    assert "coherence" in result.output.lower()

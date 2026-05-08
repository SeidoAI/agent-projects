"""Tests for `tripwire.ui.services.workflow_service`."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import yaml

from tripwire.ui.services.workflow_service import build_workflow


def _write_project(tmp_path: Path) -> Path:
    """Write a minimal `project.yaml` and return the project dir."""
    payload = {
        "name": "Fixture",
        "key_prefix": "FX",
        "description": "fixture",
        "phase": "scoping",
        "next_issue_number": 1,
        "next_session_number": 1,
    }
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    for sub in ("issues", "nodes", "sessions"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return tmp_path


def _write_workflow(project_dir: Path) -> None:
    (project_dir / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: queued
                    artifacts:
                      consumes:
                        - id: issue-brief
                          label: issue brief
                  - id: queued
                    next: executing
                    artifacts:
                      produces:
                        - id: plan
                          label: plan.md
                          path: sessions/{session_id}/plan.md
                  - id: executing
                    next: in_review
                    tripwires: [v_uuid_present, v_reference_integrity]
                    prompt_checks: [pm-session-queue]
                  - id: in_review
                    next:
                      - if: review.outcome == approved
                        then: verified
                      - else: executing
                    artifacts:
                      produces:
                        - id: review-notes
                          label: review notes
                  - id: verified
                    next: completed
                  - id: completed
                    jit_prompts: [self-review]
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    command: pm-session-queue
                    trigger: command.pm-session-queue
                    from: planned
                    to: queued
                    controls:
                      tripwires: [v_reference_integrity]
                      prompt_checks: [pm-session-queue]
                    skills: [project-manager]
                    emits:
                      artifacts:
                        - id: plan
                          label: plan.md
                          path: sessions/{session_id}/plan.md
                      events: [session.queued]
                  - id: queued-to-executing
                    actor: pm-agent
                    command: pm-session-spawn
                    trigger: command.pm-session-spawn
                    from: queued
                    to: executing
                    skills: [project-manager, backend-development]
                    emits:
                      events: [session.spawn]
            """
        ),
        encoding="utf-8",
    )


def test_build_workflow_returns_workflow_first_shape(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    _write_workflow(project_dir)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)

    assert set(payload) == {"project_id", "workflows", "registry", "drift"}
    assert payload["project_id"] == "abc"
    assert "lifecycle" not in payload
    assert "tripwires" not in payload
    assert "jit_prompts" not in payload
    assert "connectors" not in payload
    assert "artifacts" not in payload


def test_build_workflow_surfaces_statuses_from_workflow_yaml(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    _write_workflow(project_dir)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)
    workflow = payload["workflows"][0]

    assert workflow["id"] == "coding-session"
    assert workflow["actor"] == "coding-agent"
    assert workflow["trigger"] == "session.spawn"
    assert [status["id"] for status in workflow["statuses"]] == [
        "planned",
        "queued",
        "executing",
        "in_review",
        "verified",
        "completed",
    ]
    executing = workflow["statuses"][2]
    assert executing["tripwires"] == ["v_uuid_present", "v_reference_integrity"]
    assert executing["prompt_checks"] == ["pm-session-queue"]
    in_review = workflow["statuses"][3]
    assert in_review["next"]["kind"] == "conditional"
    assert {"else": "executing"} in in_review["next"]["branches"]


def test_build_workflow_surfaces_routes_from_workflow_yaml(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    _write_workflow(project_dir)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)
    routes = {route["id"]: route for route in payload["workflows"][0]["routes"]}

    route = routes["planned-to-queued"]
    assert route["workflow_id"] == "coding-session"
    assert route["actor"] == "pm-agent"
    assert route["command"] == "pm-session-queue"
    assert route["trigger"] == "command.pm-session-queue"
    assert route["from"] == "planned"
    assert route["to"] == "queued"
    assert route["kind"] == "forward"
    assert route["controls"]["tripwires"] == ["v_reference_integrity"]
    assert route["controls"]["prompt_checks"] == ["pm-session-queue"]
    assert route["skills"] == ["project-manager"]
    assert route["emits"]["artifacts"] == [
        {
            "id": "plan",
            "label": "plan.md",
            "path": "sessions/{session_id}/plan.md",
        }
    ]
    assert route["emits"]["events"] == ["session.queued"]


def test_build_workflow_derives_artifacts_from_status_declarations(
    tmp_path: Path,
) -> None:
    project_dir = _write_project(tmp_path)
    _write_workflow(project_dir)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)
    by_status = {s["id"]: s for s in payload["workflows"][0]["statuses"]}

    assert by_status["planned"]["artifacts"]["consumes"] == [
        {"id": "issue-brief", "label": "issue brief"}
    ]
    assert by_status["queued"]["artifacts"]["produces"] == [
        {
            "id": "plan",
            "label": "plan.md",
            "path": "sessions/{session_id}/plan.md",
        }
    ]


def test_build_workflow_joins_registry_metadata(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    _write_workflow(project_dir)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)
    registry = payload["registry"]

    tripwires = {entry["id"]: entry for entry in registry["tripwires"]}
    assert "v_uuid_present" in tripwires
    assert tripwires["v_uuid_present"]["blocking"] is True
    assert tripwires["v_uuid_present"]["label"] == "uuid present"

    prompts = {entry["id"]: entry for entry in registry["jit_prompts"]}
    assert "self-review" in prompts
    assert prompts["self-review"]["blocking"] is True
    assert prompts["self-review"]["prompt_revealed"] is None
    assert prompts["self-review"]["prompt_redacted"]

    prompt_checks = {entry["id"]: entry for entry in registry["prompt_checks"]}
    assert "pm-session-queue" in prompt_checks
    assert prompt_checks["pm-session-queue"]["blocking"] is True

    commands = {entry["id"]: entry for entry in registry["commands"]}
    assert "pm-session-queue" in commands
    assert commands["pm-session-queue"]["source"].endswith("pm-session-queue.md")

    skills = {entry["id"]: entry for entry in registry["skills"]}
    assert "project-manager" in skills
    assert skills["project-manager"]["source"].endswith("project-manager/SKILL.md")


def test_build_workflow_reveals_jit_prompts_when_pm(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    _write_workflow(project_dir)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=True)
    prompts = payload["registry"]["jit_prompts"]

    assert any(prompt["prompt_revealed"] for prompt in prompts)


def test_build_workflow_reports_definition_drift(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    (project_dir / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: missing
                  - id: completed
                    terminal: true
            """
        ),
        encoding="utf-8",
    )

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)

    assert payload["drift"]["count"] >= 1
    definition_findings = [
        finding
        for finding in payload["drift"]["findings"]
        if finding["source"] == "definition"
    ]
    assert definition_findings[0]["code"] == "workflow/unknown_next_status"


def test_build_workflow_workflows_empty_when_yaml_missing(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)

    payload = build_workflow(project_dir, project_id="abc", is_pm_role=False)

    assert payload["workflows"] == []
    assert payload["drift"] == {"count": 0, "findings": []}

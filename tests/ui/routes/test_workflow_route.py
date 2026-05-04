"""Tests for `GET /api/projects/{pid}/workflow`."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from fastapi.testclient import TestClient


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
                  - id: queued
                    next: in_review
                    validators: [v_uuid_present]
                    jit_prompts: [self-review]
                    artifacts:
                      produces:
                        - id: plan
                          label: plan.md
                  - id: in_review
                    terminal: true
            """
        ),
        encoding="utf-8",
    )


def test_workflow_returns_workflow_first_payload(
    seeded_client: TestClient, project_dir: Path, project_id: str
) -> None:
    _write_workflow(project_dir)

    resp = seeded_client.get(f"/api/projects/{project_id}/workflow")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"project_id", "workflows", "registry", "drift"}
    assert body["project_id"] == project_id
    assert body["workflows"][0]["statuses"][1]["id"] == "queued"
    assert body["workflows"][0]["statuses"][1]["artifacts"]["produces"] == [
        {"id": "plan", "label": "plan.md"}
    ]
    assert "lifecycle" not in body
    assert "connectors" not in body
    assert "artifacts" not in body


def test_workflow_redacts_jit_prompt_for_non_pm(
    seeded_client: TestClient, project_dir: Path, project_id: str
) -> None:
    _write_workflow(project_dir)

    resp = seeded_client.get(f"/api/projects/{project_id}/workflow")

    assert resp.status_code == 200
    for prompt in resp.json()["registry"]["jit_prompts"]:
        assert prompt["prompt_revealed"] is None


def test_workflow_reveals_jit_prompt_for_pm(
    seeded_client: TestClient, project_dir: Path, project_id: str
) -> None:
    _write_workflow(project_dir)

    resp = seeded_client.get(
        f"/api/projects/{project_id}/workflow",
        headers={"X-Tripwire-Role": "pm"},
    )

    assert resp.status_code == 200, resp.text
    revealed = [
        prompt["prompt_revealed"]
        for prompt in resp.json()["registry"]["jit_prompts"]
        if prompt["prompt_revealed"]
    ]
    assert revealed, "expected at least one JIT prompt to expose its body"


def test_workflow_unknown_project_returns_404(client: TestClient) -> None:
    resp = client.get("/api/projects/000000000000/workflow")
    assert resp.status_code == 404, resp.text


def test_workflow_pm_header_case_insensitive(
    seeded_client: TestClient, project_dir: Path, project_id: str
) -> None:
    _write_workflow(project_dir)

    resp = seeded_client.get(
        f"/api/projects/{project_id}/workflow",
        headers={"x-tripwire-role": "PM"},
    )

    assert resp.status_code == 200
    revealed = [
        prompt["prompt_revealed"]
        for prompt in resp.json()["registry"]["jit_prompts"]
        if prompt["prompt_revealed"]
    ]
    assert revealed

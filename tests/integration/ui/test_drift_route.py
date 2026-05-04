"""Integration tests for the drift report route (KUI-157 / I4).

Exercises ``GET /api/projects/{project_id}/drift``: returns
``{score, breakdown, workflow_drift_findings}``.
"""

from __future__ import annotations

import time
from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from fastapi.testclient import TestClient

from tripwire.core.events.log import emit_event
from tripwire.ui.dependencies import reset_project_cache
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "Drift Fixture",
                "key_prefix": "DR",
                "phase": "executing",
                "next_issue_number": 1,
                "next_session_number": 1,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions"):
        (project / sub).mkdir(exist_ok=True)
    return project


@pytest.fixture
def client(project_dir: Path) -> TestClient:
    _project_svc.reload_project_index()
    reset_project_cache()
    _project_svc.seed_project_index([project_dir])
    summary = _project_svc._try_load_summary(project_dir.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    yield TestClient(create_app(dev_mode=True))
    _project_svc.reload_project_index()
    reset_project_cache()


@pytest.fixture
def project_id(project_dir: Path) -> str:
    return _project_svc._project_id(project_dir.resolve())


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


def test_drift_route_returns_score_and_breakdown(
    client: TestClient, project_id: str
) -> None:
    resp = client.get(f"/api/projects/{project_id}/drift")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "score" in payload
    assert isinstance(payload["score"], int)
    assert 0 <= payload["score"] <= 100
    breakdown = payload["breakdown"]
    assert {
        "stale_pins",
        "unresolved_refs",
        "stale_concepts",
        "workflow_drift_findings",
    }.issubset(breakdown.keys())


def test_drift_route_clean_project_returns_full_score(
    client: TestClient, project_id: str
) -> None:
    """Empty project (no issues, no nodes, no events log) → score 100."""
    resp = client.get(f"/api/projects/{project_id}/drift")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["score"] == 100
    assert "workflow_drift_events" not in payload
    assert payload["workflow_drift_findings"] == []


def test_drift_route_includes_workflow_drift_findings_from_events_log(
    client: TestClient, project_id: str, project_dir: Path
) -> None:
    """Workflow findings come from canonical ``events/*.jsonl`` rows."""
    _write_workflow(project_dir)
    emit_event(
        project_dir,
        workflow="coding-session",
        instance="session-a",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    resp = client.get(f"/api/projects/{project_id}/drift")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["breakdown"]["workflow_drift_findings"] == 1
    assert payload["score"] == 98
    findings = payload["workflow_drift_findings"]
    assert len(findings) == 1
    assert findings[0]["code"] == "drift/prompt_check_missing"
    assert findings[0]["workflow"] == "coding-session"
    assert findings[0]["instance"] == "session-a"


def test_drift_route_ignores_legacy_tripwire_events_log(
    client: TestClient, project_id: str, project_dir: Path
) -> None:
    """The v0.9 route must not read stale ``.tripwire/events.log``."""
    events_log = project_dir / ".tripwire" / "events.log"
    events_log.parent.mkdir(parents=True, exist_ok=True)
    events_log.write_text(
        yaml.safe_dump(
            {"event": "workflow_drift", "at": "2026-05-01T00:00:00Z", "kind": "old"},
            default_flow_style=True,
        ),
        encoding="utf-8",
    )
    resp = client.get(f"/api/projects/{project_id}/drift")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["breakdown"]["workflow_drift_findings"] == 0
    assert payload["workflow_drift_findings"] == []

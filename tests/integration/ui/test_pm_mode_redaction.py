"""Integration: PM-mode header gates JIT prompt redaction.

KUI-100 — see `docs/specs/2026-04-26-v08-handoff.md` §2.5. The
`X-Tripwire-Role: pm` header (case-insensitive) is the only gate; missing
the header always redacts.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

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
                "name": "Fixture",
                "key_prefix": "FX",
                "phase": "scoping",
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


def test_no_header_redacts_jit_prompts(client: TestClient, project_id: str) -> None:
    resp = client.get(f"/api/projects/{project_id}/workflow")
    assert resp.status_code == 200, resp.text
    for prompt in resp.json()["registry"]["jit_prompts"]:
        assert prompt["prompt_revealed"] is None
        assert prompt["prompt_redacted"]


def test_pm_header_reveals_jit_prompts(client: TestClient, project_id: str) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/workflow",
        headers={"X-Tripwire-Role": "pm"},
    )
    assert resp.status_code == 200
    revealed = [
        prompt["prompt_revealed"]
        for prompt in resp.json()["registry"]["jit_prompts"]
        if prompt["prompt_revealed"]
    ]
    assert revealed, "expected revealed prompts in PM mode"


def test_pm_header_value_unrelated_role_falls_back_to_redacted(
    client: TestClient, project_id: str
) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/workflow",
        headers={"X-Tripwire-Role": "anonymous"},
    )
    assert resp.status_code == 200
    for prompt in resp.json()["registry"]["jit_prompts"]:
        assert prompt["prompt_revealed"] is None


def test_pm_header_case_insensitive_value(client: TestClient, project_id: str) -> None:
    resp = client.get(
        f"/api/projects/{project_id}/workflow",
        headers={"X-Tripwire-Role": "PM"},
    )
    assert resp.status_code == 200
    revealed = [
        prompt["prompt_revealed"]
        for prompt in resp.json()["registry"]["jit_prompts"]
        if prompt["prompt_revealed"]
    ]
    assert revealed

"""Shared fixtures + envelope helpers for route tests.

Also exposes fixtures used by v1 route tests (KUI-26..34) that need a
real on-disk fixture project seeded into the service-layer index.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tripwire.ui.dependencies import reset_project_cache
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture
def client() -> TestClient:
    """TestClient against the full FastAPI app in dev-mode."""
    return TestClient(create_app(dev_mode=True))


# ---------------------------------------------------------------------------
# v1 route fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_project_state():
    """Clear project-service caches around every route test."""
    _project_svc.reload_project_index()
    reset_project_cache()
    yield
    _project_svc.reload_project_index()
    reset_project_cache()


def make_project(
    project_dir: Path,
    *,
    key_prefix: str = "KUI",
    extra: dict | None = None,
    issue_routes: list[tuple[str, str]] | None = None,
) -> Path:
    """Write a minimal valid `project.yaml` under *project_dir*.

    Optional *extra* kwargs are merged into the YAML payload so tests
    can seed `statuses`, `label_categories`, etc. without reimplementing
    the boilerplate.

    v0.13.1 (B8): the legacy ``status_transitions:`` key is silently
    stripped from *extra* and instead used to seed the
    ``issue-closure`` workflow declared in the per-test ``workflow.yaml``.
    Tests can pass ``issue_routes=[(from, to), ...]`` directly to
    skip the legacy-shape conversion.

    Returns the same path for convenience.
    """
    import yaml

    project_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "name": "TripwireProj",
        "key_prefix": key_prefix,
        "description": "A fixture project",
        "phase": "scoping",
        "next_issue_number": 1,
        "next_session_number": 1,
    }
    legacy_transitions: dict | None = None
    if extra:
        # Pop the legacy `status_transitions:` shape and translate it
        # into the workflow-route form below — keeps the call sites that
        # still pass the old shape working without touching every one.
        legacy_transitions = extra.pop("status_transitions", None)
        payload.update(extra)
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )

    if issue_routes is None and legacy_transitions is not None:
        issue_routes = [
            (frm, to) for frm, tos in legacy_transitions.items() for to in tos
        ]
    for sub in ("issues", "nodes", "sessions"):
        (project_dir / sub).mkdir(exist_ok=True)

    # v0.13.1 (B8): also seed an issue-closure workflow when the test
    # asked for non-trivial issue transitions, so the mutation service
    # can resolve them via `build_issue_transitions`.
    issue_closure_block = ""
    if issue_routes:
        statuses_in_play = sorted(
            {s for route in issue_routes for s in route}
        )
        routes_yaml = "".join(
            f"      - id: ic-{idx}-{f}-to-{t}\n"
            f"        actor: pm-agent\n"
            f"        from: {f}\n"
            f"        to: {t}\n"
            f"        kind: forward\n"
            for idx, (f, t) in enumerate(issue_routes)
        )
        statuses_yaml = "".join(
            f"      - id: {s}\n" for s in statuses_in_play
        )
        issue_closure_block = (
            "  issue-closure:\n"
            "    actor: pm-agent\n"
            "    trigger: command.pm-issue-close\n"
            "    instance:\n"
            "      storage_path: instances/issues/{instance_id}/issue.yaml\n"
            "      status_field: status\n"
            f"      status_enum: {statuses_in_play}\n"
            "    statuses:\n" + statuses_yaml
            + "    routes:\n" + routes_yaml
        )

    # v0.13: UI action service routes session transitions through
    # ``execute_transition`` which requires a ``workflow.yaml``.
    (project_dir / "workflow.yaml").write_text(
        "workflow_schema_version: 1\n"
        "workflows:\n"
        "  coding-session:\n"
        "    actor: coding-agent\n"
        "    trigger: session.spawn\n"
        "    instance:\n"
        "      storage_path: sessions/{instance_id}/session.yaml\n"
        "      status_field: status\n"
        "      status_enum: [planned, queued, executing, in_review,\n"
        "        verified, completed, paused, failed, abandoned]\n"
        "    statuses:\n"
        "      - id: planned\n"
        "      - id: queued\n"
        "      - id: executing\n"
        "      - id: paused\n"
        "      - id: failed\n"
        "      - id: in_review\n"
        "      - id: verified\n"
        "      - id: completed\n"
        "        terminal: true\n"
        "      - id: abandoned\n"
        "        terminal: true\n"
        "    routes:\n"
        "      - id: source-to-planned\n"
        "        actor: pm-agent\n"
        "        from: source:create\n"
        "        to: planned\n"
        "        kind: forward\n"
        "      - id: planned-to-queued\n"
        "        actor: pm-agent\n"
        "        from: planned\n"
        "        to: queued\n"
        "        kind: forward\n"
        "      - id: queued-to-executing\n"
        "        actor: pm-agent\n"
        "        from: queued\n"
        "        to: executing\n"
        "        kind: forward\n"
        "      - id: executing-to-paused\n"
        "        actor: pm-agent\n"
        "        from: executing\n"
        "        to: paused\n"
        "        kind: side\n"
        "      - id: executing-to-failed\n"
        "        actor: code\n"
        "        from: executing\n"
        "        to: failed\n"
        "        kind: side\n"
        "      - id: paused-to-executing\n"
        "        actor: pm-agent\n"
        "        from: paused\n"
        "        to: executing\n"
        "        kind: forward\n"
        "      - id: failed-to-executing\n"
        "        actor: pm-agent\n"
        "        from: failed\n"
        "        to: executing\n"
        "        kind: forward\n"
        "      - id: executing-to-in_review\n"
        "        actor: coding-agent\n"
        "        from: executing\n"
        "        to: in_review\n"
        "        kind: forward\n"
        "      - id: in_review-to-verified\n"
        "        actor: pm-agent\n"
        "        from: in_review\n"
        "        to: verified\n"
        "        kind: forward\n"
        "      - id: verified-to-completed\n"
        "        actor: pm-agent\n"
        "        from: verified\n"
        "        to: completed\n"
        "        kind: forward\n"
        "      - id: completed-to-paused\n"
        "        actor: pm-agent\n"
        "        from: completed\n"
        "        to: paused\n"
        "        kind: revert\n"
        "        preserve_fields:\n"
        "          - runtime_state.claude_session_id\n"
        "          - runtime_state.worktrees\n"
        "      - id: executing-to-abandoned\n"
        "        actor: pm-agent\n"
        "        from: executing\n"
        "        to: abandoned\n"
        "        kind: side\n"
        + issue_closure_block
    )
    return project_dir


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal fixture project on disk with enums/, orchestration/, etc."""
    return make_project(tmp_path / "proj")


@pytest.fixture
def project_id(project_dir: Path) -> str:
    """Stable 12-hex id for *project_dir* matching server-side derivation."""
    return _project_svc._project_id(project_dir.resolve())


@pytest.fixture
def seeded_client(project_dir: Path) -> TestClient:
    """TestClient with *project_dir* registered in the service index.

    Also pre-populates the 60s discovery cache so `GET /api/projects`
    finds the fixture without touching the real filesystem.
    """
    _project_svc.seed_project_index([project_dir])
    summary = _project_svc._try_load_summary(project_dir.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    return TestClient(create_app(dev_mode=True))

"""Tests for `tripwire.ui.services.workflow_service`.

KUI-100 — see `docs/specs/2026-04-26-v08-handoff.md` §2.1 for the
`/api/workflow` graph shape this service builds.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.ui.services.workflow_service import (
    DEFAULT_LIFECYCLE_STATIONS,
    build_workflow,
)


def _write_project(tmp_path: Path, statuses: list[str] | None = None) -> Path:
    """Write a minimal `project.yaml` and return the project dir."""
    payload = {
        "name": "Fixture",
        "key_prefix": "FX",
        "description": "fixture",
        "phase": "scoping",
        "next_issue_number": 1,
        "next_session_number": 1,
    }
    if statuses is not None:
        payload["statuses"] = statuses
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    for sub in ("issues", "nodes", "sessions"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return tmp_path


def test_build_workflow_returns_top_level_keys(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="abc", is_pm_role=False)
    assert set(graph.keys()) >= {
        "project_id",
        "lifecycle",
        "validators",
        "tripwires",
        "connectors",
        "artifacts",
    }
    assert graph["project_id"] == "abc"


def test_build_workflow_uses_default_stations_when_project_has_none(
    tmp_path: Path,
) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    stations = graph["lifecycle"]["stations"]
    assert [s["id"] for s in stations] == [s["id"] for s in DEFAULT_LIFECYCLE_STATIONS]
    # n is 1-indexed.
    assert stations[0]["n"] == 1
    assert all("label" in s and "desc" in s for s in stations)


def test_build_workflow_respects_project_statuses(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path, statuses=["a", "b", "c"])
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    stations = graph["lifecycle"]["stations"]
    assert [s["id"] for s in stations] == ["a", "b", "c"]
    assert [s["n"] for s in stations] == [1, 2, 3]


def test_build_workflow_enumerates_validators(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    validators = graph["validators"]
    assert isinstance(validators, list) and len(validators) > 0
    sample = validators[0]
    # Required fields per §2.1.
    for k in ("id", "kind", "name", "fires_on_station"):
        assert k in sample, f"missing {k!r} on validator: {sample}"
    assert sample["kind"] == "gate"
    # All known checks should surface — at minimum, the well-known ones.
    ids = {v["id"] for v in validators}
    assert "v_uuid_present" in ids
    assert "v_reference_integrity" in ids


def test_build_workflow_enumerates_tripwires(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    tripwires = graph["tripwires"]
    assert isinstance(tripwires, list) and len(tripwires) > 0
    sample = tripwires[0]
    for k in (
        "id",
        "kind",
        "name",
        "fires_on_event",
        "blocks",
        "fires_on_station",
        "prompt_revealed",
        "prompt_redacted",
    ):
        assert k in sample


def test_build_workflow_redacts_tripwire_prompt_when_not_pm(
    tmp_path: Path,
) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    for tw in graph["tripwires"]:
        assert tw["prompt_revealed"] is None
        assert isinstance(tw["prompt_redacted"], str)


def test_build_workflow_reveals_tripwire_prompt_when_pm(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=True)
    revealed_count = 0
    for tw in graph["tripwires"]:
        if isinstance(tw["prompt_revealed"], str) and tw["prompt_revealed"]:
            revealed_count += 1
    assert revealed_count > 0, (
        "expected at least one tripwire to expose its prompt in PM mode"
    )


def test_build_workflow_includes_connectors(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    connectors = graph["connectors"]
    assert "sources" in connectors and "sinks" in connectors
    assert isinstance(connectors["sources"], list)
    assert isinstance(connectors["sinks"], list)


def test_build_workflow_includes_artifacts(tmp_path: Path) -> None:
    project_dir = _write_project(tmp_path)
    graph = build_workflow(project_dir, project_id="x", is_pm_role=False)
    artifacts = graph["artifacts"]
    assert isinstance(artifacts, list) and len(artifacts) > 0
    for a in artifacts:
        for k in ("id", "label", "produced_by"):
            assert k in a

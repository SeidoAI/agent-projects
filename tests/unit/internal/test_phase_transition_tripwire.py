"""Tests for the phase-transition tripwire (KUI-138 / B4).

Fires on ``session.complete`` when ``project.yaml.phase`` is past
``executing`` but issues labelled with the previous phase are still
open. Detects the v0.8.x premature-close pattern: PM bumps the phase
before all the executing-phase issues actually finished.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tripwire._internal.tripwires import TripwireContext
from tripwire._internal.tripwires.phase_transition import (
    PREVIOUS_PHASE,
    PhaseTransitionTripwire,
    _VARIATIONS,
)


def _seed_project(
    project_dir: Path,
    *,
    phase: str,
    issues: list[tuple[str, str, list[str]]],
) -> None:
    """Seed a minimal project: project.yaml + issues/<KEY>/issue.yaml.

    ``issues`` is a list of ``(id, status, labels)`` triples.
    """
    project_yaml = {
        "name": "demo-project",
        "key_prefix": "DEM",
        "phase": phase,
        "repos": {"SeidoAI/demo": {"local": "."}},
    }
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8"
    )

    issues_root = project_dir / "issues"
    issues_root.mkdir(parents=True, exist_ok=True)
    for issue_id, status, labels in issues:
        idir = issues_root / issue_id
        idir.mkdir(parents=True, exist_ok=True)
        body = {
            "id": issue_id,
            "title": f"Issue {issue_id}",
            "priority": "medium",
            "executor": "ai",
            "verifier": "required",
            "status": status,
            "labels": labels,
        }
        (idir / "issue.yaml").write_text(
            "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
            encoding="utf-8",
        )


def _ctx(tmp_path: Path) -> TripwireContext:
    return TripwireContext(
        project_dir=tmp_path,
        session_id="alpha",
        project_id="demo",
    )


def test_phase_transition_class_attrs() -> None:
    tw = PhaseTransitionTripwire()
    assert tw.id == "phase-transition"
    assert tw.fires_on == "session.complete"
    assert tw.blocks is True


def test_previous_phase_table_covers_advanced_phases() -> None:
    # Only phases past `scoping` have a previous phase; the table
    # encodes the scoping → scoped → executing → reviewing chain.
    assert PREVIOUS_PHASE["scoped"] == "scoping"
    assert PREVIOUS_PHASE["executing"] == "scoped"
    assert PREVIOUS_PHASE["reviewing"] == "executing"
    assert "scoping" not in PREVIOUS_PHASE


def test_three_variations_present() -> None:
    assert len(_VARIATIONS) == 3
    for v in _VARIATIONS:
        assert "--ack" in v
        assert "phase" in v.lower()


def test_fire_returns_one_of_the_variations(tmp_path: Path) -> None:
    tw = PhaseTransitionTripwire()
    prompt = tw.fire(_ctx(tmp_path))
    assert prompt in _VARIATIONS


def test_should_fire_clean_transition(tmp_path: Path) -> None:
    """No open issues labelled with the previous phase → silent."""
    _seed_project(
        tmp_path,
        phase="reviewing",
        issues=[
            ("DEM-1", "done", ["phase:executing"]),
            ("DEM-2", "done", ["phase:executing"]),
            ("DEM-3", "verified", ["phase:executing"]),
        ],
    )
    tw = PhaseTransitionTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_should_fire_open_prev_phase_issue(tmp_path: Path) -> None:
    """One open prev-phase issue → fires."""
    _seed_project(
        tmp_path,
        phase="reviewing",
        issues=[
            ("DEM-1", "done", ["phase:executing"]),
            ("DEM-2", "in_progress", ["phase:executing"]),
        ],
    )
    tw = PhaseTransitionTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is True


def test_should_fire_silent_at_scoping(tmp_path: Path) -> None:
    """Phase==scoping has no previous phase → silent regardless."""
    _seed_project(
        tmp_path,
        phase="scoping",
        issues=[
            ("DEM-1", "in_progress", ["phase:scoping"]),
        ],
    )
    tw = PhaseTransitionTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_should_fire_ignores_unrelated_phase_label(tmp_path: Path) -> None:
    """Open issues NOT labelled with previous phase → silent."""
    _seed_project(
        tmp_path,
        phase="reviewing",
        issues=[
            ("DEM-1", "in_progress", ["phase:reviewing"]),  # current phase, not prev
            ("DEM-2", "in_progress", []),  # no phase label
        ],
    )
    tw = PhaseTransitionTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_acknowledged_with_substantive_marker(tmp_path: Path) -> None:
    tw = PhaseTransitionTripwire()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("phase-transition")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abc1234"]}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is True


def test_acknowledged_with_declared_no_findings(tmp_path: Path) -> None:
    tw = PhaseTransitionTripwire()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("phase-transition")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"declared_no_findings": True}), encoding="utf-8"
    )
    assert tw.is_acknowledged(ctx) is True


def test_acknowledged_empty_marker_rejected(tmp_path: Path) -> None:
    tw = PhaseTransitionTripwire()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("phase-transition")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")
    assert tw.is_acknowledged(ctx) is False


def test_acknowledged_no_marker(tmp_path: Path) -> None:
    tw = PhaseTransitionTripwire()
    ctx = _ctx(tmp_path)
    assert tw.is_acknowledged(ctx) is False


@pytest.fixture(autouse=True)
def _isolate_pricing_cache(monkeypatch):
    # No-op fixture kept for symmetry with siblings that touch shared
    # caches; phase_transition has no module-level cache to clear.
    return None

"""Tests for the cost-ceiling tripwire (KUI-142 / B8).

Fires on ``session.complete`` when the session's cumulative cost
(computed from the claude stream-json log via
``compute_session_cost``) exceeds a threshold (default $5).
Configurable via ``project.yaml.tripwires.extra`` for an entry with
``id: cost-ceiling`` and ``params: {ceiling_usd: N}``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from tripwire._internal.tripwires import TripwireContext
from tripwire._internal.tripwires.cost_ceiling import (
    DEFAULT_COST_CEILING_USD,
    CostCeilingTripwire,
    _VARIATIONS,
    _read_ceiling,
)
from tripwire.core.session_cost import CostBreakdown


def _seed_project(project_dir: Path, *, extras: list[dict] | None = None) -> None:
    project_yaml = {
        "name": "demo-project",
        "key_prefix": "DEM",
        "phase": "executing",
        "repos": {"SeidoAI/demo": {"local": "."}},
    }
    if extras is not None:
        project_yaml["tripwires"] = {"extra": extras}
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8"
    )


def _seed_session(
    project_dir: Path,
    session_id: str,
    *,
    log_path: str | None = None,
) -> None:
    sdir = project_dir / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    body: dict = {
        "id": session_id,
        "name": f"Session {session_id}",
        "agent": "backend-coder",
        "issues": [],
        "repos": [{"repo": "SeidoAI/demo", "base_branch": "main"}],
    }
    if log_path is not None:
        body["runtime_state"] = {"log_path": log_path, "worktrees": []}
    (sdir / "session.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _ctx(tmp_path: Path, session_id: str = "alpha") -> TripwireContext:
    return TripwireContext(
        project_dir=tmp_path,
        session_id=session_id,
        project_id="demo",
    )


def _bd(total: float) -> CostBreakdown:
    """Construct a CostBreakdown whose total_usd equals ``total``."""
    bd = CostBreakdown()
    bd.input_usd = total
    return bd


def test_class_attrs() -> None:
    tw = CostCeilingTripwire()
    assert tw.id == "cost-ceiling"
    assert tw.fires_on == "session.complete"
    assert tw.blocks is True


def test_default_ceiling_is_5_usd() -> None:
    assert DEFAULT_COST_CEILING_USD == 5.0


def test_three_variations_present() -> None:
    assert len(_VARIATIONS) == 3
    for v in _VARIATIONS:
        assert "--ack" in v
        assert "$" in v or "cost" in v.lower()


def test_should_fire_under_default_ceiling(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", log_path=str(tmp_path / "log.jsonl"))
    with patch(
        "tripwire._internal.tripwires.cost_ceiling.compute_session_cost",
        return_value=_bd(4.99),
    ):
        tw = CostCeilingTripwire()
        assert tw.should_fire(_ctx(tmp_path)) is False


def test_should_fire_over_default_ceiling(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", log_path=str(tmp_path / "log.jsonl"))
    with patch(
        "tripwire._internal.tripwires.cost_ceiling.compute_session_cost",
        return_value=_bd(5.50),
    ):
        tw = CostCeilingTripwire()
        assert tw.should_fire(_ctx(tmp_path)) is True


def test_should_fire_silent_when_no_log_path(tmp_path: Path) -> None:
    """Session with no recorded log_path → silent (cost = $0)."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", log_path=None)
    tw = CostCeilingTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_per_project_ceiling_override_respected(tmp_path: Path) -> None:
    _seed_project(
        tmp_path,
        extras=[
            {
                "id": "cost-ceiling",
                "fires_on": "session.complete",
                "class": (
                    "tripwire._internal.tripwires.cost_ceiling.CostCeilingTripwire"
                ),
                "params": {"ceiling_usd": 1.0},
            }
        ],
    )
    _seed_session(tmp_path, "alpha", log_path=str(tmp_path / "log.jsonl"))
    with patch(
        "tripwire._internal.tripwires.cost_ceiling.compute_session_cost",
        return_value=_bd(2.0),
    ):
        tw = CostCeilingTripwire()
        # 2.0 > 1.0 (override) → fires; default $5 would have been silent.
        assert tw.should_fire(_ctx(tmp_path)) is True


def test_per_project_ceiling_override_silent_below(tmp_path: Path) -> None:
    _seed_project(
        tmp_path,
        extras=[
            {
                "id": "cost-ceiling",
                "fires_on": "session.complete",
                "class": (
                    "tripwire._internal.tripwires.cost_ceiling.CostCeilingTripwire"
                ),
                "params": {"ceiling_usd": 50.0},
            }
        ],
    )
    _seed_session(tmp_path, "alpha", log_path=str(tmp_path / "log.jsonl"))
    with patch(
        "tripwire._internal.tripwires.cost_ceiling.compute_session_cost",
        return_value=_bd(20.0),
    ):
        tw = CostCeilingTripwire()
        # 20 < 50 → silent; default $5 would have fired.
        assert tw.should_fire(_ctx(tmp_path)) is False


def test_read_ceiling_default(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    assert _read_ceiling(tmp_path) == DEFAULT_COST_CEILING_USD


def test_read_ceiling_uses_extra_params(tmp_path: Path) -> None:
    _seed_project(
        tmp_path,
        extras=[
            {
                "id": "cost-ceiling",
                "fires_on": "session.complete",
                "class": (
                    "tripwire._internal.tripwires.cost_ceiling.CostCeilingTripwire"
                ),
                "params": {"ceiling_usd": 12.5},
            }
        ],
    )
    assert _read_ceiling(tmp_path) == 12.5


def test_acknowledged_with_substantive_marker(tmp_path: Path) -> None:
    tw = CostCeilingTripwire()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("cost-ceiling")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abc1234"]}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is True


def test_fire_returns_one_of_the_variations(tmp_path: Path) -> None:
    tw = CostCeilingTripwire()
    prompt = tw.fire(_ctx(tmp_path))
    assert prompt in _VARIATIONS

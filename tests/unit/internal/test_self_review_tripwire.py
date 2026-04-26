"""Tests for the self-review tripwire — fires on session.complete."""

from __future__ import annotations

import json
from pathlib import Path

from tripwire._internal.tripwires import TripwireContext
from tripwire._internal.tripwires.self_review import _VARIATIONS, SelfReviewTripwire


def test_self_review_class_attrs() -> None:
    tw = SelfReviewTripwire()
    assert tw.id == "self-review"
    assert tw.fires_on == "session.complete"
    assert tw.blocks is True


def test_self_review_fires_returns_one_of_the_variations(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    prompt = tw.fire(ctx)
    assert prompt in _VARIATIONS


def test_self_review_picks_same_variation_for_same_session(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx_a = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    ctx_b = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    assert tw.fire(ctx_a) == tw.fire(ctx_b)


def test_self_review_no_marker_not_acknowledged(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    assert tw.is_acknowledged(ctx) is False


def test_self_review_marker_with_fix_commits_acknowledged(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["c4f81e2"]}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is True


def test_self_review_marker_with_declared_no_findings_acknowledged(
    tmp_path: Path,
) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"declared_no_findings": True}), encoding="utf-8"
    )
    assert tw.is_acknowledged(ctx) is True


def test_self_review_empty_marker_rejected(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")
    assert tw.is_acknowledged(ctx) is False


def test_self_review_empty_fix_commits_rejected(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": []}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is False


def test_self_review_corrupt_marker_not_acknowledged(tmp_path: Path) -> None:
    tw = SelfReviewTripwire()
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("not json", encoding="utf-8")
    assert tw.is_acknowledged(ctx) is False


def test_self_review_three_variations_present() -> None:
    assert len(_VARIATIONS) == 3
    # Each variation must instruct re-running with --ack.
    for v in _VARIATIONS:
        assert "--ack" in v

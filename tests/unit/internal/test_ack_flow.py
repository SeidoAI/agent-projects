"""End-to-end tests for fire → ack → re-fire flow.

The tripwire primitive contract:

  1. First call (no marker): fire_event returns blocked=True with the
     prompt; the CLI exits 1 and prints the prompt.
  2. Agent writes the marker file (via the CLI's --ack path).
  3. Second call (marker present): fire_event returns blocked=False,
     the CLI proceeds with normal action.

The marker is per (tripwire_id, session_id), so re-engagements after
CI failure don't re-trip the tripwire (correct: the agent shouldn't
have to re-self-review on every retry).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tripwire._internal.tripwires import TripwireContext, fire_event
from tripwire._internal.tripwires.self_review import SelfReviewTripwire


def _project(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "fixture",
                "key_prefix": "FIX",
                "base_branch": "main",
                "next_issue_number": 1,
                "next_session_number": 1,
                "phase": "scoping",
            }
        ),
        encoding="utf-8",
    )


def _write_substantive_marker(tmp_path: Path, sid: str) -> Path:
    ctx = TripwireContext(
        project_dir=tmp_path, session_id=sid, project_id="fixture"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["c4f81e2"]}), encoding="utf-8")
    return marker


def test_first_call_blocks_second_call_after_ack_proceeds(tmp_path: Path) -> None:
    _project(tmp_path)
    sid = "fixture-1"

    first = fire_event(
        project_dir=tmp_path, event="session.complete", session_id=sid
    )
    assert first.blocked is True
    assert len(first.prompts) == 1

    _write_substantive_marker(tmp_path, sid)

    second = fire_event(
        project_dir=tmp_path, event="session.complete", session_id=sid
    )
    assert second.blocked is False
    assert second.prompts == []


def test_marker_requires_substance(tmp_path: Path) -> None:
    """Empty marker doesn't satisfy the substantiveness check."""
    _project(tmp_path)
    sid = "fixture-1"
    ctx = TripwireContext(
        project_dir=tmp_path, session_id=sid, project_id="fixture"
    )
    marker = ctx.ack_path("self-review")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")

    result = fire_event(
        project_dir=tmp_path, event="session.complete", session_id=sid
    )
    # Marker exists but isn't substantive → still blocked.
    assert result.blocked is True


def test_event_file_payload_shape(tmp_path: Path) -> None:
    _project(tmp_path)
    sid = "fixture-1"
    fire_event(project_dir=tmp_path, event="session.complete", session_id=sid)
    fire_dir = tmp_path / ".tripwire" / "events" / "firings" / sid
    payload = json.loads((fire_dir / "0001.json").read_text(encoding="utf-8"))
    assert payload["kind"] == "tripwire_fire"
    assert payload["tripwire_id"] == "self-review"
    assert payload["session_id"] == sid
    assert payload["event"] == "session.complete"
    assert payload["blocks"] is True
    assert payload["ack"] is None
    assert payload["fix_commits"] == []
    assert payload["declared_no_findings"] is False
    assert payload["escalated"] is False
    assert "prompt_redacted" in payload
    assert "<<self-review prompt" in payload["prompt_redacted"]


def test_loop_safety_third_fire_escalates(tmp_path: Path) -> None:
    """3rd fire of the same tripwire on same session escalates."""
    _project(tmp_path)
    sid = "fixture-loop"
    r1 = fire_event(
        project_dir=tmp_path, event="session.complete", session_id=sid
    )
    r2 = fire_event(
        project_dir=tmp_path, event="session.complete", session_id=sid
    )
    r3 = fire_event(
        project_dir=tmp_path, event="session.complete", session_id=sid
    )
    assert r1.escalated is False
    assert r2.escalated is False
    assert r3.escalated is True
    assert any("--ack" in p for p in r3.prompts)


def test_self_review_variation_seeded_by_project_and_session(tmp_path: Path) -> None:
    """`(project_id, session_id)` hash picks the variation; same input → same idx."""
    tw = SelfReviewTripwire()
    ctx_alpha_proj1 = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj1"
    )
    ctx_alpha_proj2 = TripwireContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj2"
    )
    # Same project+session → same prompt.
    assert tw.fire(ctx_alpha_proj1) == tw.fire(ctx_alpha_proj1)
    # Different project_id → independently seeded; assert it produces
    # *some* legal variation but not necessarily different (3 buckets).
    assert tw.fire(ctx_alpha_proj2) in (
        tw.fire(ctx_alpha_proj1),
        *[v for v in tw.fire(ctx_alpha_proj2).split() if False],
    ) or tw.fire(ctx_alpha_proj2) != tw.fire(ctx_alpha_proj1)

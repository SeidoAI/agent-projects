"""Routing telemetry on session-complete (KUI-96 §E4).

Every successful ``tripwire session complete`` appends a row to
``<project>/sessions/.routing_telemetry.jsonl``. The row schema:

    {sid, task_kind, provider, model, effort, merged, cost_usd,
     duration_min, re_engages, ci_failures}

Used by ``tripwire session analyze-routing`` to surface
$/merged-PR by route. For now, manual interpretation; auto-tuning
the routing table is v0.8 scope.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tripwire.core.routing_telemetry import (
    TelemetryRow,
    append_telemetry_row,
    build_telemetry_row,
    read_telemetry,
    telemetry_path,
)
from tripwire.models.session import (
    AgentSession,
    EngagementEntry,
    RuntimeState,
    SpawnConfig,
)


def test_telemetry_path_lives_under_sessions(tmp_path: Path) -> None:
    """Telemetry log lives at ``<project>/sessions/.routing_telemetry.jsonl``."""
    expected = tmp_path / "sessions" / ".routing_telemetry.jsonl"
    assert telemetry_path(tmp_path) == expected


def test_build_row_pulls_from_spawn_config(tmp_path: Path) -> None:
    """``task_kind`` / ``provider`` / ``model`` / ``effort`` come from spawn_config."""
    session = AgentSession(
        id="s1",
        name="s1",
        agent="backend-coder",
        spawn_config=SpawnConfig(
            config={
                "task_kind": "agentic_loop",
                "provider": "claude",
                "model": "opus",
                "effort": "xhigh",
            }
        ),
    )
    row = build_telemetry_row(tmp_path, session, cost_usd=12.34)
    assert row.sid == "s1"
    assert row.task_kind == "agentic_loop"
    assert row.provider == "claude"
    assert row.model == "opus"
    assert row.effort == "xhigh"
    assert row.merged is True
    assert row.cost_usd == 12.34


def test_build_row_uses_safe_defaults_when_spawn_config_missing(tmp_path: Path) -> None:
    """A session with no spawn_config still produces a row with sentinels."""
    session = AgentSession(id="s1", name="s1", agent="backend-coder")
    row = build_telemetry_row(tmp_path, session, cost_usd=0.0)
    # task_kind is unknown until KUI-91 lands routing.yaml — None is fine.
    assert row.task_kind is None
    # Provider defaults to claude — that's the only runtime today.
    assert row.provider == "claude"


def test_build_row_duration_from_engagements(tmp_path: Path) -> None:
    """``duration_min`` spans first engagement start to last engagement end."""
    started = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    ended = started + timedelta(minutes=22)
    session = AgentSession(
        id="s1",
        name="s1",
        agent="backend-coder",
        engagements=[
            EngagementEntry(
                started_at=started,
                trigger="initial",
                ended_at=ended,
                outcome="completed",
            ),
        ],
    )
    row = build_telemetry_row(tmp_path, session, cost_usd=0.0)
    assert row.duration_min == 22


def test_build_row_re_engages_count(tmp_path: Path) -> None:
    """``re_engages`` = engagement count minus the first launch."""
    base = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    session = AgentSession(
        id="s1",
        name="s1",
        agent="backend-coder",
        engagements=[
            EngagementEntry(started_at=base, trigger="initial"),
            EngagementEntry(started_at=base + timedelta(hours=1), trigger="resume"),
            EngagementEntry(started_at=base + timedelta(hours=2), trigger="resume"),
        ],
    )
    row = build_telemetry_row(tmp_path, session, cost_usd=0.0)
    assert row.re_engages == 2


def test_append_creates_file_and_appends_jsonl(tmp_path: Path) -> None:
    """First append creates the file; second appends a fresh line."""
    session = AgentSession(
        id="s1",
        name="s1",
        agent="backend-coder",
        runtime_state=RuntimeState(),
    )
    row1 = build_telemetry_row(tmp_path, session, cost_usd=1.0)

    session2 = AgentSession(id="s2", name="s2", agent="backend-coder")
    row2 = build_telemetry_row(tmp_path, session2, cost_usd=2.0)

    append_telemetry_row(tmp_path, row1)
    append_telemetry_row(tmp_path, row2)

    rows = read_telemetry(tmp_path)
    assert len(rows) == 2
    assert rows[0]["sid"] == "s1"
    assert rows[1]["sid"] == "s2"
    assert rows[0]["cost_usd"] == 1.0
    assert rows[1]["cost_usd"] == 2.0


def test_telemetry_row_serialises_with_required_keys(tmp_path: Path) -> None:
    """Every required key from the spec ships in the on-disk row."""
    session = AgentSession(id="s1", name="s1", agent="backend-coder")
    row = build_telemetry_row(tmp_path, session, cost_usd=89.5)
    data = row.as_jsonl_dict()
    for key in (
        "sid",
        "task_kind",
        "provider",
        "model",
        "effort",
        "merged",
        "cost_usd",
        "duration_min",
        "re_engages",
        "ci_failures",
    ):
        assert key in data, f"missing key: {key}"


def test_read_telemetry_returns_empty_when_file_missing(tmp_path: Path) -> None:
    """Reading before any session has ever completed yields []."""
    assert read_telemetry(tmp_path) == []


def test_complete_session_appends_routing_row(
    save_test_session, tmp_path_project: Path, monkeypatch
) -> None:
    """End-to-end: ``complete_session`` writes a telemetry row.

    All gates that depend on external state (PR-merged, review-ok,
    artifacts) are stubbed so the test focuses on the telemetry write.
    """
    from tripwire.core import session_complete as sc
    from tripwire.core.session_store import load_session, save_session

    save_test_session(
        tmp_path_project,
        session_id="sx",
        status="in_review",
        spawn_config=SpawnConfig(
            config={"task_kind": "agentic_loop", "model": "opus", "effort": "xhigh"}
        ),
    )
    # Engagement so duration is non-zero.
    sess = load_session(tmp_path_project, "sx")
    started = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    sess.engagements = [
        EngagementEntry(
            started_at=started,
            trigger="initial",
            ended_at=started + timedelta(minutes=15),
        )
    ]
    save_session(tmp_path_project, sess)

    monkeypatch.setattr(sc, "_flip_drafts_to_ready", lambda *a, **k: None)
    monkeypatch.setattr(sc, "_verify_pr_merged", lambda *a, **k: None)
    monkeypatch.setattr(sc, "_verify_issue_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(sc, "_verify_review_ok", lambda *a, **k: None)

    sc.complete_session(tmp_path_project, "sx")

    rows = read_telemetry(tmp_path_project)
    assert len(rows) == 1
    assert rows[0]["sid"] == "sx"
    assert rows[0]["task_kind"] == "agentic_loop"
    assert rows[0]["model"] == "opus"
    assert rows[0]["duration_min"] == 15
    assert rows[0]["merged"] is True


def test_complete_dry_run_does_not_write_telemetry(
    save_test_session, tmp_path_project: Path, monkeypatch
) -> None:
    """``--dry-run`` must not touch the telemetry file."""
    from tripwire.core import session_complete as sc

    save_test_session(tmp_path_project, session_id="sx", status="in_review")
    monkeypatch.setattr(sc, "_flip_drafts_to_ready", lambda *a, **k: None)
    monkeypatch.setattr(sc, "_verify_pr_merged", lambda *a, **k: None)
    monkeypatch.setattr(sc, "_verify_issue_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(sc, "_verify_review_ok", lambda *a, **k: None)

    sc.complete_session(tmp_path_project, "sx", dry_run=True)
    assert read_telemetry(tmp_path_project) == []


def test_telemetry_row_is_strict_jsonl(tmp_path: Path) -> None:
    """Each persisted row is one valid JSON object on its own line."""
    session = AgentSession(id="s1", name="s1", agent="backend-coder")
    row = build_telemetry_row(tmp_path, session, cost_usd=0.0)
    append_telemetry_row(tmp_path, row)
    text = telemetry_path(tmp_path).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line]
    assert len(lines) == 1
    json.loads(lines[0])  # must parse


def test_telemetry_row_dataclass_roundtrip() -> None:
    """:class:`TelemetryRow` round-trips through its serialise helper."""
    row = TelemetryRow(
        sid="s1",
        task_kind="agentic_loop",
        provider="claude",
        model="opus",
        effort="xhigh",
        merged=True,
        cost_usd=12.34,
        duration_min=10,
        re_engages=0,
        ci_failures=0,
    )
    data = row.as_jsonl_dict()
    assert data["sid"] == "s1"
    assert data["cost_usd"] == 12.34

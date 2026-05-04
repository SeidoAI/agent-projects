"""Tests for the append-only workflow events log (KUI-123).

The substrate is a per-project append-only JSON-Lines log under
``<project>/events/``. One file per UTC date
(``events/<YYYY-MM-DD>.jsonl``). Schema:
``{ts, workflow, instance, status, event, details}``.

All emission goes via :func:`tripwire.core.events.log.emit_event`.
Validators (KUI-120), tripwires (KUI-121), and transitions (KUI-159)
all emit through this surface — drift detection (KUI-124) consumes it.
"""

from __future__ import annotations

import json
from pathlib import Path


def _project_dir(tmp_path: Path) -> Path:
    """Minimal project setup so emit_event can resolve the events dir."""
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_emit_event_appends_jsonl_line(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="v09-workflow-substrate",
        status="executing",
        event="validator.run",
        details={"id": "v_uuid_present", "outcome": "pass"},
    )
    files = sorted((pd / "events").glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert set(payload.keys()) == {
        "ts",
        "workflow",
        "instance",
        "status",
        "event",
        "details",
    }
    assert payload["workflow"] == "coding-session"
    assert payload["status"] == "executing"
    assert payload["event"] == "validator.run"
    assert payload["details"] == {"id": "v_uuid_present", "outcome": "pass"}


def test_emit_event_appends_to_same_file_for_same_date(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    for i in range(3):
        emit_event(
            pd,
            workflow="coding-session",
            instance="s",
            status="executing",
            event="validator.run",
            details={"i": i},
        )
    files = sorted((pd / "events").glob("*.jsonl"))
    assert len(files) == 1, "all events on the same UTC date go in one file"
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["details"]["i"] for line in lines] == [0, 1, 2]


def test_emit_event_filename_is_utc_date(tmp_path: Path) -> None:
    """File naming is `<YYYY-MM-DD>.jsonl` in UTC."""
    import re

    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="w",
        instance="i",
        status="s",
        event="e",
        details={},
    )
    files = list((pd / "events").glob("*.jsonl"))
    assert len(files) == 1
    assert re.match(r"^\d{4}-\d{2}-\d{2}\.jsonl$", files[0].name)


def test_read_events_filters_by_workflow(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event, read_events

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="s",
        status="executing",
        event="e",
        details={},
    )
    emit_event(
        pd,
        workflow="other-workflow",
        instance="s",
        status="executing",
        event="e",
        details={},
    )
    rows = list(read_events(pd, workflow="coding-session"))
    assert len(rows) == 1
    assert rows[0]["workflow"] == "coding-session"


def test_read_events_filters_by_session_instance(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event, read_events

    pd = _project_dir(tmp_path)
    for inst in ("a", "b", "a"):
        emit_event(
            pd,
            workflow="w",
            instance=inst,
            status="s",
            event="e",
            details={},
        )
    rows = list(read_events(pd, instance="a"))
    assert len(rows) == 2
    assert all(r["instance"] == "a" for r in rows)


def test_read_events_filters_by_event_kind(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event, read_events

    pd = _project_dir(tmp_path)
    for kind in ("validator.run", "jit_prompt.fired", "validator.run"):
        emit_event(
            pd,
            workflow="w",
            instance="i",
            status="s",
            event=kind,
            details={},
        )
    rows = list(read_events(pd, event="validator.run"))
    assert len(rows) == 2


def test_read_events_returns_empty_when_log_missing(tmp_path: Path) -> None:
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    rows = list(read_events(pd))
    assert rows == []


def test_emit_event_validates_required_fields(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    import pytest

    with pytest.raises(ValueError):
        emit_event(
            pd,
            workflow="",
            instance="i",
            status="s",
            event="e",
            details={},
        )
    with pytest.raises(ValueError):
        emit_event(
            pd,
            workflow="w",
            instance="i",
            status="s",
            event="",
            details={},
        )


def test_cli_events_tail_shows_recent(tmp_path: Path) -> None:
    """`tripwire events tail` shows the most recent events with the
    standard JSON shape."""
    from click.testing import CliRunner

    from tripwire.cli.events import events_cmd
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    for i in range(3):
        emit_event(
            pd,
            workflow="w",
            instance="i",
            status="s",
            event="e",
            details={"i": i},
        )

    runner = CliRunner()
    result = runner.invoke(
        events_cmd,
        ["tail", "--project-dir", str(pd), "--limit", "10"],
    )
    assert result.exit_code == 0, result.output
    # Each line is a JSON record.
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 3
    payloads = [json.loads(line) for line in lines]
    assert all(p["workflow"] == "w" for p in payloads)


def test_cli_events_filter_narrows_results(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from tripwire.cli.events import events_cmd
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="w",
        instance="a",
        status="s",
        event="validator.run",
        details={},
    )
    emit_event(
        pd,
        workflow="w",
        instance="b",
        status="s",
        event="jit_prompt.fired",
        details={},
    )

    runner = CliRunner()
    result = runner.invoke(
        events_cmd,
        [
            "filter",
            "--project-dir",
            str(pd),
            "--event",
            "validator.run",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "validator.run"

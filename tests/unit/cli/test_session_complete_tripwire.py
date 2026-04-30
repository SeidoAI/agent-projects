"""Tests for the tripwire integration in `tripwire session complete`.

Spec: `docs/specs/2026-04-21-v08-tripwires-as-primitive.md` §6 + KUI-99
issue ACs.

The CLI semantics:

  * First call (no marker, tripwires enabled) → returns the tripwire
    prompt on stdout, exits 1, does NOT run the close-out gates.
  * `--ack` writes the marker (substantive: ≥1 fix-commit SHA OR
    ``declared_no_findings: true``) and exits 0 without running the
    gates. The marker file is what makes the *next* call's
    ``is_acknowledged()`` return True.
  * Second call without ``--ack`` (marker present) → runs the
    close-out gates as before.
  * ``--no-tripwires`` bypasses the registry call entirely (records
    an audit-log entry) and runs the close-out gates.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire._internal.tripwires import TripwireContext
from tripwire.cli.main import cli


def _project(tmp_path: Path, tripwires: dict | None = None) -> None:
    body: dict = {
        "name": "fixture",
        "key_prefix": "FIX",
        "base_branch": "main",
        "next_issue_number": 1,
        "next_session_number": 1,
        "phase": "scoping",
    }
    if tripwires is not None:
        body["tripwires"] = tripwires
    (tmp_path / "project.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")


def test_first_complete_returns_prompt_and_exits_1(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["session", "complete", "fixture-1", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    # The prompt is multi-line; sentinel on a fragment present in every
    # variation.
    assert "--ack" in result.output


def test_first_complete_writes_event_file(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    runner.invoke(
        cli,
        ["session", "complete", "fixture-1", "--project-dir", str(tmp_path)],
    )
    fire_dir = tmp_path / ".tripwire" / "events" / "firings" / "fixture-1"
    assert fire_dir.is_dir()
    assert (fire_dir / "0001.json").is_file()


def test_ack_with_tripwire_id_targets_specific_marker(tmp_path: Path) -> None:
    """`--ack --tripwire-id <id>` writes the marker for the named
    tripwire, not just `self-review`. Required for the v0.9 deviation
    tripwires (phase-transition, followups-not-filed, stopped-to-ask,
    write-count, cost-ceiling) which all fire on `session.complete`
    alongside self-review (codex P1 #2 on PR #79)."""
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--ack",
            "--tripwire-id",
            "phase-transition",
            "--declared-no-findings",
        ],
    )
    assert result.exit_code == 0, result.output
    target = tmp_path / ".tripwire" / "acks" / "phase-transition-fixture-1.json"
    assert target.is_file(), "phase-transition marker missing"
    self_review_marker = tmp_path / ".tripwire" / "acks" / "self-review-fixture-1.json"
    assert not self_review_marker.exists(), (
        "self-review marker leaked when --tripwire-id targeted phase-transition"
    )


def test_ack_default_tripwire_id_remains_self_review(tmp_path: Path) -> None:
    """Backward compat: omitting `--tripwire-id` defaults to
    `self-review` so existing workflows keep working."""
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--ack",
            "--declared-no-findings",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".tripwire" / "acks" / "self-review-fixture-1.json").is_file()


def test_ack_with_fix_commits_writes_marker(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--ack",
            "--fix-commit",
            "c4f81e2",
            "--fix-commit",
            "9b3a02d",
        ],
    )
    assert result.exit_code == 0, result.output
    marker = tmp_path / ".tripwire" / "acks" / "self-review-fixture-1.json"
    assert marker.is_file()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["fix_commits"] == ["c4f81e2", "9b3a02d"]


def test_ack_with_declared_no_findings_writes_marker(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--ack",
            "--declared-no-findings",
        ],
    )
    assert result.exit_code == 0, result.output
    marker = tmp_path / ".tripwire" / "acks" / "self-review-fixture-1.json"
    assert marker.is_file()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["declared_no_findings"] is True


def test_ack_without_substance_rejected(tmp_path: Path) -> None:
    """`--ack` with neither `--fix-commit` nor `--declared-no-findings`
    is rejected — the marker substantiveness check would fail anyway."""
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--ack",
        ],
    )
    assert result.exit_code != 0
    assert (
        "fix-commit" in result.output.lower() or "no-findings" in result.output.lower()
    )


def test_no_tripwires_bypass_skips_fire(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--no-tripwires",
        ],
    )
    # The tripwire is bypassed but the underlying close-out gates run
    # and will fail on a fixture session that has no PRs / artifacts.
    # We assert the bypass audit-log entry exists, which is the gate
    # we're testing here.
    audit = tmp_path / ".tripwire" / "audit" / "tripwire_bypass.log"
    assert audit.is_file()
    body = audit.read_text(encoding="utf-8")
    assert "fixture-1" in body
    assert "session.complete" in body
    # The session.complete close-out then runs and may fail on its
    # own gates — that's not what this test checks.
    del result


def test_project_disabled_skips_fire(tmp_path: Path) -> None:
    _project(tmp_path, {"enabled": False})
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["session", "complete", "fixture-1", "--project-dir", str(tmp_path)],
    )
    # No fire event written.
    fire_dir = tmp_path / ".tripwire" / "events" / "firings" / "fixture-1"
    assert not fire_dir.exists()
    # No bypass audit either — the tripwire was disabled, not bypassed.
    audit = tmp_path / ".tripwire" / "audit" / "tripwire_bypass.log"
    assert not audit.exists()
    del result


def test_ack_after_fire_unblocks_next_call(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    runner.invoke(
        cli,
        ["session", "complete", "fixture-1", "--project-dir", str(tmp_path)],
    )
    runner.invoke(
        cli,
        [
            "session",
            "complete",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--ack",
            "--fix-commit",
            "c4f81e2",
        ],
    )
    # Now is_acknowledged returns True for the marker.
    ctx = TripwireContext(
        project_dir=tmp_path, session_id="fixture-1", project_id="fixture"
    )
    marker = ctx.ack_path("self-review")
    assert marker.is_file()

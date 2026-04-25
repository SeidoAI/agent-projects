"""Snapshot-style tests for `readme_renderer.render`.

We test the rendered output against four fixtures (empty, in-flight,
all-done, > 30 sessions) by asserting on key sections rather than full
golden-file matches. Section-level assertions survive small template
edits without thrashing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tripwire.core.readme_renderer import build_render_context, render
from tripwire.core.session_mermaid import UNFINISHED_THRESHOLD

FIXED_NOW = datetime(2026, 4, 25, 12, 0, 0)


# ============================================================================
# Empty project
# ============================================================================


def test_empty_project_renders_marker_and_section_order(tmp_path_project: Path) -> None:
    out = render(tmp_path_project, now=FIXED_NOW)
    # First line must be the marker.
    assert out.startswith("<!-- tripwire-readme-auto -->")
    # Section order in the body matches the spec hierarchy.
    headings = [
        "# tmp",
        "## At a glance",
        "## Session graph",
        "## Active sessions",
        "## Recent merges",
        "## Critical path",
        "## Roadmap",
        "## Workspace",
        "<summary><b>Issues</b>",
        "<summary><b>All sessions</b>",
        "## Links",
    ]
    last_idx = -1
    for heading in headings:
        idx = out.find(heading)
        assert idx > last_idx, f"{heading!r} missing or out of order in:\n{out}"
        last_idx = idx


def test_empty_project_shows_no_sessions_message(tmp_path_project: Path) -> None:
    out = render(tmp_path_project, now=FIXED_NOW)
    assert "no sessions yet" in out.lower()
    assert "no critical path" in out.lower()


def test_empty_project_includes_mermaid_block(tmp_path_project: Path) -> None:
    out = render(tmp_path_project, now=FIXED_NOW)
    assert "```mermaid" in out
    assert "graph LR" in out


# ============================================================================
# In-flight project
# ============================================================================


def test_in_flight_project_lists_active_sessions(
    tmp_path_project: Path, save_test_session, save_test_issue
) -> None:
    save_test_session(tmp_path_project, "alpha", status="executing")
    save_test_session(
        tmp_path_project, "bravo", status="planned", blocked_by_sessions=["alpha"]
    )
    save_test_session(tmp_path_project, "delta", status="completed")
    save_test_issue(tmp_path_project, "TMP-1", status="todo")
    save_test_issue(tmp_path_project, "TMP-2", status="in_progress")

    out = render(tmp_path_project, now=FIXED_NOW)
    # Active sessions section names the executing session.
    active_block = _section(out, "## Active sessions", "## Recent merges")
    assert "alpha" in active_block
    assert "executing" in active_block
    # The completed session shouldn't show up under active.
    assert "delta" not in active_block

    # Mermaid contains all three (under threshold).
    mermaid_block = _section(out, "```mermaid", "```")
    assert "alpha[" in mermaid_block
    assert "bravo[" in mermaid_block
    assert "delta[" in mermaid_block

    # All-sessions collapsed section names every session.
    all_block = _section(out, "<summary><b>All sessions</b>", "</details>")
    for sid in ("alpha", "bravo", "delta"):
        assert sid in all_block


def test_in_flight_project_health_badge_shows_progress(
    tmp_path_project: Path, save_test_session
) -> None:
    save_test_session(tmp_path_project, "alpha", status="executing")
    out = render(tmp_path_project, now=FIXED_NOW)
    # Some "in progress" indication should appear in the status line.
    status_line = next(
        line for line in out.splitlines() if line.startswith("> **Status:**")
    )
    assert "progress" in status_line.lower() or "🚧" in status_line


# ============================================================================
# All-done
# ============================================================================


def test_all_done_health_badge(tmp_path_project: Path, save_test_session) -> None:
    save_test_session(tmp_path_project, "alpha", status="completed")
    save_test_session(tmp_path_project, "bravo", status="done")
    out = render(tmp_path_project, now=FIXED_NOW)
    status_line = next(
        line for line in out.splitlines() if line.startswith("> **Status:**")
    )
    assert "done" in status_line.lower() or "✓" in status_line


def test_all_done_no_active_sessions(tmp_path_project: Path, save_test_session) -> None:
    save_test_session(tmp_path_project, "alpha", status="completed")
    out = render(tmp_path_project, now=FIXED_NOW)
    active_block = _section(out, "## Active sessions", "## Recent merges")
    assert "no sessions in flight" in active_block.lower()


# ============================================================================
# Truncation: > 30 sessions
# ============================================================================


def test_more_than_threshold_sessions_truncates_mermaid(
    tmp_path_project: Path, save_test_session
) -> None:
    for i in range(UNFINISHED_THRESHOLD):
        save_test_session(tmp_path_project, f"done{i:02d}", status="completed")
    save_test_session(tmp_path_project, "active", status="executing")
    out = render(tmp_path_project, now=FIXED_NOW)
    mermaid_block = _section(out, "```mermaid", "```")
    # Truncated: completed sessions don't appear in the graph but the
    # active session does.
    assert "done00[" not in mermaid_block
    assert "active[" in mermaid_block
    # Note about completed count appears in the graph block.
    assert f"{UNFINISHED_THRESHOLD}" in mermaid_block
    assert "complete" in mermaid_block.lower()


# ============================================================================
# Determinism
# ============================================================================


def test_render_is_deterministic_with_fixed_now(
    tmp_path_project: Path, save_test_session
) -> None:
    save_test_session(tmp_path_project, "alpha", status="executing")
    save_test_session(
        tmp_path_project, "bravo", status="planned", blocked_by_sessions=["alpha"]
    )
    a = render(tmp_path_project, now=FIXED_NOW)
    b = render(tmp_path_project, now=FIXED_NOW)
    assert a == b


# ============================================================================
# Custom template
# ============================================================================


def test_custom_template_path(tmp_path: Path, tmp_path_project: Path) -> None:
    custom = tmp_path / "custom.md.j2"
    custom.write_text(
        "<!-- tripwire-readme-auto -->\n"
        "CUSTOM: {{ project_name }} has {{ total_sessions }} sessions.\n"
    )
    out = render(tmp_path_project, template_path=custom, now=FIXED_NOW)
    assert out.startswith("<!-- tripwire-readme-auto -->")
    assert "CUSTOM: tmp has 0 sessions." in out


# ============================================================================
# Recent merges injection
# ============================================================================


def test_recent_merges_appear_when_passed(tmp_path_project: Path) -> None:
    out = render(
        tmp_path_project,
        now=FIXED_NOW,
        recent_merges=["#42 Add foo", "#41 Fix bar"],
    )
    merges_block = _section(out, "## Recent merges", "## Critical path")
    assert "#42 Add foo" in merges_block
    assert "#41 Fix bar" in merges_block


def test_recent_merges_default_message_when_absent(tmp_path_project: Path) -> None:
    out = render(tmp_path_project, now=FIXED_NOW)
    merges_block = _section(out, "## Recent merges", "## Critical path")
    assert "No recent merges" in merges_block


# ============================================================================
# build_render_context returns the structured shape
# ============================================================================


def test_build_render_context_returns_dict_with_required_keys(
    tmp_path_project: Path,
) -> None:
    ctx = build_render_context(tmp_path_project, now=FIXED_NOW)
    required_keys = {
        "project_name",
        "project_description",
        "tripwire_version",
        "health_badge",
        "session_summary",
        "issue_summary",
        "regenerated_at",
        "validation_label",
        "session_in_flight",
        "session_done",
        "issue_open",
        "issue_closed",
        "critical_path_len",
        "session_mermaid",
        "active_sessions",
        "recent_merges",
        "critical_path",
        "launchable",
        "workspace_path",
        "total_issues",
        "issues_by_status",
        "total_sessions",
        "all_sessions",
        "links",
    }
    missing = required_keys - set(ctx.keys())
    assert not missing, f"missing keys in render context: {missing}"


# ============================================================================
# Helpers
# ============================================================================


def _section(text: str, start_marker: str, end_marker: str) -> str:
    """Slice text between two markers; raise if either is missing."""
    start = text.find(start_marker)
    if start < 0:
        pytest.fail(f"start marker {start_marker!r} not found in:\n{text}")
    after_start = start + len(start_marker)
    end = text.find(end_marker, after_start)
    if end < 0:
        pytest.fail(f"end marker {end_marker!r} not found after {start_marker!r}")
    return text[after_start:end]

"""Tests for `tripwire.core.pr_summary_renderer`.

The renderer is pure — these tests construct ``PrSummary`` instances
directly and assert on the markdown shape: marker line first, sections
expand only when there are non-zero changes, ID lists cap, and the
overall comment respects the 65k char ceiling.
"""

from __future__ import annotations

from tripwire.core.pr_summary_renderer import (
    ID_LIST_CAP,
    MARKER,
    MAX_CHARS,
    ConceptGraphSection,
    CriticalPathSection,
    IssuesSection,
    IssueStatusChange,
    LintSection,
    PrSummary,
    SessionLifecycleChange,
    SessionsSection,
    ValidationSection,
    WorkspaceSyncSection,
    render,
)


def _section_summary_lines(out: str) -> list[str]:
    """Return all <summary>...</summary> contents in the rendered output."""
    lines = []
    for raw in out.splitlines():
        s = raw.strip()
        if s.startswith("<summary>") and s.endswith("</summary>"):
            lines.append(s[len("<summary>") : -len("</summary>")])
    return lines


def _open_summary_lines(out: str) -> list[str]:
    """Return summaries from sections rendered with ``<details open>``."""
    out_lines = out.splitlines()
    open_summaries = []
    for i, raw in enumerate(out_lines):
        if raw.startswith("<details open>") and i + 1 < len(out_lines):
            nxt = out_lines[i + 1].strip()
            if nxt.startswith("<summary>") and nxt.endswith("</summary>"):
                open_summaries.append(nxt[len("<summary>") : -len("</summary>")])
    return open_summaries


# ============================================================================
# Fixture 1: empty — no changes anywhere
# ============================================================================


def test_empty_summary_renders_marker_first():
    out = render(PrSummary(base_sha="abc123", head_sha="def456"))
    assert out.startswith(MARKER)


def test_empty_summary_no_section_is_open():
    out = render(PrSummary(base_sha="abc123", head_sha="def456"))
    assert _open_summary_lines(out) == []


def test_empty_summary_all_seven_sections_present():
    out = render(PrSummary(base_sha="abc123", head_sha="def456"))
    summaries = _section_summary_lines(out)
    assert len(summaries) == 7
    assert any("Validation" in s for s in summaries)
    assert any("Issues" in s for s in summaries)
    assert any("Sessions" in s for s in summaries)
    assert any("Concept graph" in s for s in summaries)
    assert any("Critical path" in s for s in summaries)
    assert any("Workspace sync" in s for s in summaries)
    assert any("Lint" in s for s in summaries)


def test_empty_summary_includes_sha_header():
    out = render(PrSummary(base_sha="abc123", head_sha="def456"))
    assert "`abc123`" in out
    assert "`def456`" in out


def test_long_hex_sha_is_shortened_to_seven_chars():
    out = render(
        PrSummary(
            base_sha="abcdef0123456789abcdef0123456789abcdef01",
            head_sha="0123456789abcdef0123456789abcdef01234567",
        )
    )
    assert "`abcdef0`" in out
    assert "`0123456`" in out


def test_non_hex_ref_passes_through():
    out = render(PrSummary(base_sha="origin/main", head_sha="HEAD"))
    assert "origin/main" in out
    assert "HEAD" in out


# ============================================================================
# Fixture 2: all sections — every section has a non-zero delta
# ============================================================================


def _all_sections_summary() -> PrSummary:
    return PrSummary(
        base_sha="aaaaaaa",
        head_sha="bbbbbbb",
        project_name="acme",
        validation=ValidationSection(
            base_errors=2, head_errors=5, base_warnings=1, head_warnings=3
        ),
        issues=IssuesSection(
            base_counts={"todo": 5, "in_progress": 3, "done": 1},
            head_counts={"todo": 4, "in_progress": 1, "done": 4},
            changes=[
                IssueStatusChange("KUI-1", "todo", "in_progress"),
                IssueStatusChange("KUI-2", "in_progress", "done"),
                IssueStatusChange("KUI-3", "in_progress", "done"),
                IssueStatusChange("KUI-4", "in_progress", "done"),
            ],
        ),
        sessions=SessionsSection(
            base_counts={"planned": 2, "executing": 1, "done": 0},
            head_counts={"planned": 1, "executing": 2, "done": 1},
            changes=[
                SessionLifecycleChange("s-foo", "planned", "executing"),
                SessionLifecycleChange("s-bar", "executing", "done"),
            ],
        ),
        concept_graph=ConceptGraphSection(
            nodes_added=["fastapi-app", "auth"],
            nodes_removed=["legacy-x"],
            nodes_promoted=["payment-flow"],
            base_orphan_refs=3,
            head_orphan_refs=1,
            base_stale_nodes=2,
            head_stale_nodes=2,
        ),
        critical_path=CriticalPathSection(base_length=8, head_length=6),
        workspace_sync=WorkspaceSyncSection(
            linked=True,
            base_promotion_candidates=0,
            head_promotion_candidates=2,
            base_workspace_origin_count=10,
            head_workspace_origin_count=10,
        ),
        lint=LintSection(
            base_errors=0, head_errors=0, base_warnings=2, head_warnings=4
        ),
    )


def test_all_sections_every_summary_is_open():
    out = render(_all_sections_summary())
    open_summaries = _open_summary_lines(out)
    assert len(open_summaries) == 7


def test_all_sections_renders_project_name_in_header():
    out = render(_all_sections_summary())
    assert "**acme**" in out


def test_all_sections_validation_shows_error_delta():
    out = render(_all_sections_summary())
    assert "+3" in out  # 5-2 = +3 errors
    assert "+2" in out  # 3-1 = +2 warnings


def test_all_sections_issues_lists_changes():
    out = render(_all_sections_summary())
    assert "`KUI-1`: todo → in_progress" in out
    assert "`KUI-2`: in_progress → done" in out


def test_all_sections_concept_graph_shows_added_removed_promoted():
    out = render(_all_sections_summary())
    assert "Added (2)" in out
    assert "`fastapi-app`" in out
    assert "Removed (1)" in out
    assert "`legacy-x`" in out
    assert "Promoted to workspace (1)" in out
    assert "`payment-flow`" in out


def test_all_sections_critical_path_reports_shortened():
    out = render(_all_sections_summary())
    assert "shortened by 2" in out


# ============================================================================
# Fixture 3: partial — some sections change, others don't
# ============================================================================


def _partial_summary() -> PrSummary:
    return PrSummary(
        base_sha="1111111",
        head_sha="2222222",
        # Validation flat → closed
        validation=ValidationSection(),
        issues=IssuesSection(
            base_counts={"todo": 3},
            head_counts={"todo": 2, "done": 1},
            changes=[IssueStatusChange("KUI-9", "todo", "done")],
        ),
        # Sessions, concept graph, critical path, workspace, lint all flat
    )


def test_partial_only_changed_sections_are_open():
    out = render(_partial_summary())
    open_summaries = _open_summary_lines(out)
    assert len(open_summaries) == 1
    assert "Issues" in open_summaries[0]


def test_partial_changes_show_clean_icon_on_unchanged_sections():
    out = render(_partial_summary())
    summaries = _section_summary_lines(out)
    validation_line = next(s for s in summaries if "Validation" in s)
    assert validation_line.startswith("✓")
    critical_line = next(s for s in summaries if "Critical path" in s)
    assert critical_line.startswith("✓")


def test_partial_workspace_sync_shows_not_linked_when_unlinked():
    out = render(_partial_summary())
    assert "project not linked" in out


# ============================================================================
# Fixture 4: over-cap — too many ID rows / too long body
# ============================================================================


def test_over_cap_truncates_to_max_chars():
    """The 65k cap is the safety net when something blows past the per-section
    ID-list caps. We force overflow by stuffing one absurdly long id."""
    huge_id = "X" * 70_000
    out = render(
        PrSummary(
            base_sha="aaaaaaa",
            head_sha="bbbbbbb",
            issues=IssuesSection(changes=[IssueStatusChange(huge_id, "todo", "done")]),
        )
    )
    assert len(out) <= MAX_CHARS
    assert "(truncated at 65,000 chars)" in out


def test_id_list_caps_at_constant():
    """The ID list inside one section caps at ``ID_LIST_CAP`` even before
    the global truncation kicks in."""
    changes = [
        IssueStatusChange(f"X-{i}", "todo", "done") for i in range(ID_LIST_CAP + 5)
    ]
    out = render(PrSummary(issues=IssuesSection(changes=changes)))
    assert "…+5 more" in out
    # First N appear, but the (N+1)-th does not
    assert f"`X-{ID_LIST_CAP - 1}`" in out
    assert f"`X-{ID_LIST_CAP}`:" not in out


def test_concept_graph_added_list_caps():
    nodes = [f"node-{i}" for i in range(ID_LIST_CAP + 3)]
    out = render(PrSummary(concept_graph=ConceptGraphSection(nodes_added=nodes)))
    assert f"Added ({ID_LIST_CAP + 3})" in out
    assert "…+3 more" in out


# ============================================================================
# Marker + structure invariants
# ============================================================================


def test_marker_is_always_first_line():
    out = render(_all_sections_summary())
    assert out.splitlines()[0] == MARKER


def test_render_ends_with_newline():
    out = render(PrSummary())
    assert out.endswith("\n")


def test_validation_unchanged_renders_clean_icon():
    out = render(
        PrSummary(
            validation=ValidationSection(
                base_errors=0, head_errors=0, base_warnings=0, head_warnings=0
            )
        )
    )
    summaries = _section_summary_lines(out)
    val_line = next(s for s in summaries if "Validation" in s)
    assert val_line.startswith("✓")


def test_validation_with_errors_renders_failure_icon():
    out = render(PrSummary(validation=ValidationSection(head_errors=3)))
    summaries = _section_summary_lines(out)
    val_line = next(s for s in summaries if "Validation" in s)
    assert val_line.startswith("✗")


def test_signed_zero_when_no_change():
    """Zero deltas show as ``0`` rather than ``+0`` or ``-0``."""
    out = render(PrSummary())
    # With both validation columns at zero we expect a "0" delta cell
    assert "| 0 | 0 | 0 |" in out

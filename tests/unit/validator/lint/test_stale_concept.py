"""KUI-144 (D2) — stale_concept lint.

Warns when a concept node's content_hash is stale AND the node is
referenced by ≥1 active issue or session.
"""

from pathlib import Path

import pytest

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import stale_concept
from tripwire.models.graph import FreshnessResult, FreshnessStatus


def _stub_stale(monkeypatch, stale_node_ids: set[str]) -> None:
    """Stub freshness.check_all_nodes to mark only ``stale_node_ids`` as STALE."""

    def _fake(nodes, _project):
        out: list[FreshnessResult] = []
        for n in nodes:
            if n.id in stale_node_ids:
                out.append(
                    FreshnessResult(
                        node_id=n.id,
                        status=FreshnessStatus.STALE,
                        detail="hash mismatch (test stub)",
                    )
                )
            else:
                out.append(FreshnessResult(node_id=n.id, status=FreshnessStatus.FRESH))
        return out

    monkeypatch.setattr(stale_concept, "check_all_nodes", _fake)


def test_stale_node_referenced_by_active_issue_warns(
    tmp_path_project: Path, save_test_issue, save_test_node, monkeypatch
):
    save_test_node(tmp_path_project, node_id="auth-system")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="in_progress",
        body=(
            "## Context\n[[auth-system]]\n\n## Implements\nx\n\n"
            "## Repo scope\nx\n\n## Requirements\nx\n\n"
            "## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] thing\n\n"
            "## Test plan\n```\nuv run pytest\n```\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
        ),
    )
    _stub_stale(monkeypatch, {"auth-system"})

    ctx = load_context(tmp_path_project)
    results = stale_concept.check(ctx)
    assert len(results) == 1
    assert results[0].code == "stale_concept/referenced"
    assert results[0].severity == "warning"
    assert "auth-system" in results[0].message
    assert "TMP-1" in results[0].message


def test_stale_node_with_no_references_no_warning(
    tmp_path_project: Path, save_test_node, monkeypatch
):
    save_test_node(tmp_path_project, node_id="orphan-concept")
    _stub_stale(monkeypatch, {"orphan-concept"})

    ctx = load_context(tmp_path_project)
    assert stale_concept.check(ctx) == []


def test_fresh_node_with_references_no_warning(
    tmp_path_project: Path, save_test_issue, save_test_node, monkeypatch
):
    save_test_node(tmp_path_project, node_id="auth-system")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="in_progress",
        body="## Context\n[[auth-system]]\n",
    )
    _stub_stale(monkeypatch, set())

    ctx = load_context(tmp_path_project)
    assert stale_concept.check(ctx) == []


def test_stale_node_referenced_only_by_done_issue_no_warning(
    tmp_path_project: Path, save_test_issue, save_test_node, monkeypatch
):
    """Done/canceled issues are no longer 'active' — stale refs don't matter."""
    save_test_node(tmp_path_project, node_id="auth-system")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="done",
        body="## Context\n[[auth-system]]\n",
    )
    _stub_stale(monkeypatch, {"auth-system"})

    ctx = load_context(tmp_path_project)
    assert stale_concept.check(ctx) == []


@pytest.mark.parametrize("session_status", ["completed", "abandoned", "failed"])
def test_stale_node_referenced_only_by_terminal_session_no_warning(
    tmp_path_project: Path,
    save_test_session,
    save_test_node,
    monkeypatch,
    session_status: str,
):
    save_test_node(tmp_path_project, node_id="auth-system")
    save_test_session(
        tmp_path_project,
        session_id="s1",
        status=session_status,
        body="Plan body referencing [[auth-system]] for context.",
    )
    _stub_stale(monkeypatch, {"auth-system"})

    ctx = load_context(tmp_path_project)
    assert stale_concept.check(ctx) == []

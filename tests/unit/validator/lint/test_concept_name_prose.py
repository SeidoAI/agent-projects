"""KUI-145 (D3) — concept_name_as_prose lint.

Warns when a concept node's name (case-folded) appears as prose in
≥N (default 2) issue bodies WITHOUT a ``[[node-id]]`` reference in
those issues. Heuristic — false positives are explicitly accepted by
the spec because the cost is one warning, not a build break.
"""

from pathlib import Path

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import concept_name_prose


def _body(prose: str) -> str:
    return (
        f"## Context\n{prose}\n\n## Implements\nx\n\n"
        "## Repo scope\nx\n\n## Requirements\nx\n\n"
        "## Execution constraints\nstop and ask.\n\n"
        "## Acceptance criteria\n- [ ] thing\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
    )


def test_prose_in_two_or_more_issues_warns(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    # Two issues mention "auth system" in prose with no [[auth-system]] ref.
    save_test_issue(
        tmp_path_project, key="TMP-1", body=_body("We need auth system support.")
    )
    save_test_issue(
        tmp_path_project, key="TMP-2", body=_body("The auth system underpins this.")
    )

    ctx = load_context(tmp_path_project)
    results = concept_name_prose.check(ctx)
    codes = [r.code for r in results]
    assert "concept_name_prose/found" in codes
    found = next(r for r in results if r.code == "concept_name_prose/found")
    assert found.severity == "warning"
    assert "auth-system" in found.message
    # Should mention the issue keys it appeared in.
    assert "TMP-1" in found.message and "TMP-2" in found.message


def test_one_issue_below_threshold_no_warning(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project, key="TMP-1", body=_body("We need auth system support.")
    )

    ctx = load_context(tmp_path_project)
    assert concept_name_prose.check(ctx) == []


def test_proper_reference_does_not_count_as_prose(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    """An issue that uses [[auth-system]] is excluded from the prose count."""
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        body=_body("[[auth-system]] is referenced properly here."),
    )
    save_test_issue(
        tmp_path_project, key="TMP-2", body=_body("auth system as prose only.")
    )

    ctx = load_context(tmp_path_project)
    # Only one issue uses prose — below threshold.
    assert concept_name_prose.check(ctx) == []


def test_node_with_no_prose_match_no_warning(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    save_test_node(tmp_path_project, node_id="user-model", name="User Model")
    save_test_issue(tmp_path_project, key="TMP-1", body=_body("Unrelated text only."))
    save_test_issue(
        tmp_path_project, key="TMP-2", body=_body("Different topic entirely.")
    )

    ctx = load_context(tmp_path_project)
    assert concept_name_prose.check(ctx) == []

"""KUI-146 (D4) — semantic_coverage lint.

For each active issue, warn if its acceptance criteria reference fewer
concept nodes than the project-type threshold. The default threshold
is 0 (off) — projects opt in via
``project.yaml.lint_config.semantic_coverage.min_ac_node_refs`` because
the convention of putting concept refs in AC items is project-policy,
not universal. See `decisions.md` D-1 in the v09-validators session
for the rationale.

Tests below override the threshold via lint_config to exercise the
fire path; the default-off behavior is asserted in
``test_default_off``.
"""

from pathlib import Path

import yaml

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import semantic_coverage


def _body(*, context_refs: str = "", ac_refs: str = "") -> str:
    return (
        f"## Context\n{context_refs}\n\n## Implements\nx\n\n"
        "## Repo scope\nx\n\n## Requirements\nx\n\n"
        "## Execution constraints\nstop and ask.\n\n"
        f"## Acceptance criteria\n- [ ] thing {ac_refs}\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
    )


def _enable_lint(project_dir: Path, min_refs: int = 1) -> None:
    raw = yaml.safe_load((project_dir / "project.yaml").read_text())
    raw.setdefault("lint_config", {})["semantic_coverage"] = {
        "min_ac_node_refs": min_refs
    }
    (project_dir / "project.yaml").write_text(yaml.safe_dump(raw))


def test_active_issue_with_no_ac_refs_warns(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="in_progress",
        body=_body(context_refs="[[auth-system]]", ac_refs=""),
    )
    _enable_lint(tmp_path_project, min_refs=1)

    ctx = load_context(tmp_path_project)
    results = semantic_coverage.check(ctx)
    assert any(r.code == "semantic_coverage/below_threshold" for r in results)
    finding = next(r for r in results if r.code == "semantic_coverage/below_threshold")
    assert finding.severity == "warning"
    assert "TMP-1" in finding.message


def test_active_issue_with_one_ac_ref_passes(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="in_progress",
        body=_body(ac_refs="against [[auth-system]]"),
    )
    _enable_lint(tmp_path_project, min_refs=1)

    ctx = load_context(tmp_path_project)
    assert semantic_coverage.check(ctx) == []


def test_done_issue_skipped(tmp_path_project: Path, save_test_issue, save_test_node):
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="done",
        body=_body(),
    )
    _enable_lint(tmp_path_project, min_refs=1)

    ctx = load_context(tmp_path_project)
    assert semantic_coverage.check(ctx) == []


def test_canceled_issue_skipped(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="canceled",
        body=_body(),
    )
    _enable_lint(tmp_path_project, min_refs=1)

    ctx = load_context(tmp_path_project)
    assert semantic_coverage.check(ctx) == []


def test_default_off(tmp_path_project: Path, save_test_issue, save_test_node):
    """Without explicit lint_config opt-in, the lint stays silent —
    even on issues with 0 AC refs."""
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        status="in_progress",
        body=_body(context_refs="[[auth-system]]", ac_refs=""),
    )

    ctx = load_context(tmp_path_project)
    assert semantic_coverage.check(ctx) == []

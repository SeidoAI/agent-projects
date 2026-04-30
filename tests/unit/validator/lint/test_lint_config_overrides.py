"""KUI-149 (D7) — per-project lint_config threshold overrides.

The lints already read thresholds via ``_thresholds.get_threshold``;
this test exercises the project.yaml override layer end-to-end.
"""

from pathlib import Path

import yaml

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import (
    concept_name_prose,
    mega_issue,
    semantic_coverage,
)


def _set_lint_config(project_dir: Path, cfg: dict) -> None:
    raw = yaml.safe_load((project_dir / "project.yaml").read_text())
    raw["lint_config"] = cfg
    (project_dir / "project.yaml").write_text(yaml.safe_dump(raw))


def test_concept_name_prose_threshold_override(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    """Raise the prose threshold to 5 — two prose hits no longer warn."""
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    body = (
        "## Context\nauth system here\n\n## Implements\nx\n\n"
        "## Repo scope\nx\n\n## Requirements\nx\n\n"
        "## Execution constraints\nstop and ask.\n\n"
        "## Acceptance criteria\n- [ ] thing\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
    )
    save_test_issue(tmp_path_project, key="TMP-1", body=body)
    save_test_issue(tmp_path_project, key="TMP-2", body=body)
    _set_lint_config(tmp_path_project, {"concept_name_prose": {"min_issues": 5}})

    ctx = load_context(tmp_path_project)
    assert concept_name_prose.check(ctx) == []


def test_semantic_coverage_threshold_override(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    """Threshold raised to 1 (default is 0/off) — issues with no AC
    refs now warn."""
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    body = (
        "## Context\n[[auth-system]]\n\n## Implements\nx\n\n"
        "## Repo scope\nx\n\n## Requirements\nx\n\n"
        "## Execution constraints\nstop and ask.\n\n"
        "## Acceptance criteria\n- [ ] thing\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
    )
    save_test_issue(tmp_path_project, key="TMP-1", status="in_progress", body=body)
    _set_lint_config(tmp_path_project, {"semantic_coverage": {"min_ac_node_refs": 1}})

    ctx = load_context(tmp_path_project)
    results = semantic_coverage.check(ctx)
    assert any(r.code == "semantic_coverage/below_threshold" for r in results)


def test_mega_issue_threshold_override(tmp_path_project: Path, save_test_issue):
    """max_children lowered to 2 — three children fires."""
    save_test_issue(tmp_path_project, key="TMP-1")
    for n in range(3):
        save_test_issue(tmp_path_project, key=f"TMP-{n + 2}", parent="TMP-1")
    _set_lint_config(tmp_path_project, {"mega_issue": {"max_children": 2}})

    ctx = load_context(tmp_path_project)
    results = mega_issue.check(ctx)
    assert any(r.code == "mega_issue/too_many_children" for r in results)


def test_unknown_lint_key_ignored(
    tmp_path_project: Path, save_test_issue, save_test_node
):
    """A lint_config block for a lint we don't ship is harmless."""
    save_test_node(tmp_path_project, node_id="auth-system", name="Auth System")
    save_test_issue(tmp_path_project, key="TMP-1", status="in_progress")
    _set_lint_config(tmp_path_project, {"some_future_lint": {"threshold": 99}})

    ctx = load_context(tmp_path_project)
    # Loading still succeeds; existing checks still see defaults.
    assert ctx.project_config is not None

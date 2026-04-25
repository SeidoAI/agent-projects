"""Validator rule `done_implies_artifacts_on_main` (v0.7.9 §A1).

The rule enforces the correctness contract: every session/issue with
``status: done`` must have its required artifacts on ``origin/main``
of the project tracking repo.

Tests stub the git layer rather than spinning up real repos — we're
exercising the validator's branching, not git itself.
"""

from pathlib import Path

import pytest

from tripwire.core import git_helpers
from tripwire.core.validator import (
    check_done_implies_artifacts_on_main,
    load_context,
    validate_project,
)


def _stub_main(monkeypatch, paths: set[str]) -> None:
    """Patch :func:`list_paths_on_main` to return a fixed set of paths."""
    from tripwire.core.validator.lint import done_implies_artifacts_on_main

    monkeypatch.setattr(
        done_implies_artifacts_on_main,
        "list_paths_on_main",
        lambda _project_dir: set(paths),
    )


def _stub_main_unavailable(monkeypatch, message: str = "no remote") -> None:
    from tripwire.core.validator.lint import done_implies_artifacts_on_main

    def _raise(_project_dir):
        raise git_helpers.MainTreeUnavailable(message)

    monkeypatch.setattr(done_implies_artifacts_on_main, "list_paths_on_main", _raise)


def test_no_done_entities_returns_empty(
    tmp_path_project: Path, save_test_issue, monkeypatch
):
    """Cheap path: no `done` issues/sessions → rule does nothing, even
    without git available. (Specifically: `list_paths_on_main` should
    not even be invoked.)"""
    save_test_issue(tmp_path_project, "TMP-1", status="todo")

    called = {"hit": False}

    def _spy(_dir):
        called["hit"] = True
        return set()

    from tripwire.core.validator.lint import done_implies_artifacts_on_main

    monkeypatch.setattr(done_implies_artifacts_on_main, "list_paths_on_main", _spy)

    ctx = load_context(tmp_path_project)
    results = check_done_implies_artifacts_on_main(ctx)
    assert results == []
    assert called["hit"] is False


def test_done_issue_missing_artifact_errors(
    tmp_path_project: Path, save_test_issue, monkeypatch
):
    """`done` issue without developer.md/verified.md on origin/main →
    one error per missing file with code
    ``done_implies_artifacts/missing_on_main``."""
    save_test_issue(tmp_path_project, "TMP-1", status="done")
    _stub_main(monkeypatch, set())  # nothing on main

    ctx = load_context(tmp_path_project)
    results = check_done_implies_artifacts_on_main(ctx)
    codes = {r.code for r in results}
    files_mentioned = {r.message for r in results}

    assert codes == {"done_implies_artifacts/missing_on_main"}
    assert any("issues/TMP-1/developer.md" in m for m in files_mentioned)
    assert any("issues/TMP-1/verified.md" in m for m in files_mentioned)
    assert all(r.severity == "error" for r in results)


def test_done_issue_with_artifacts_on_main_passes(
    tmp_path_project: Path, save_test_issue, monkeypatch
):
    save_test_issue(tmp_path_project, "TMP-1", status="done")
    _stub_main(
        monkeypatch,
        {"issues/TMP-1/developer.md", "issues/TMP-1/verified.md"},
    )

    ctx = load_context(tmp_path_project)
    results = check_done_implies_artifacts_on_main(ctx)
    assert results == []


def test_done_session_missing_self_review_errors(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """The §A1 default `session_required` includes self-review.md and
    pm-response.md. Missing either → error."""
    save_test_session(tmp_path_project, "s1", status="done")
    _stub_main(
        monkeypatch,
        {
            "sessions/s1/task-checklist.md",
            "sessions/s1/verification-checklist.md",
            "sessions/s1/insights.yaml",
            # self-review.md and pm-response.md absent
        },
    )

    ctx = load_context(tmp_path_project)
    results = check_done_implies_artifacts_on_main(ctx)
    files_mentioned = " ".join(r.message for r in results)

    assert "sessions/s1/self-review.md" in files_mentioned
    assert "sessions/s1/pm-response.md" in files_mentioned
    assert all(r.code == "done_implies_artifacts/missing_on_main" for r in results)


def test_done_session_with_all_artifacts_passes(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    save_test_session(tmp_path_project, "s1", status="done")
    _stub_main(
        monkeypatch,
        {
            "sessions/s1/task-checklist.md",
            "sessions/s1/verification-checklist.md",
            "sessions/s1/self-review.md",
            "sessions/s1/pm-response.md",
            "sessions/s1/insights.yaml",
        },
    )

    ctx = load_context(tmp_path_project)
    assert check_done_implies_artifacts_on_main(ctx) == []


def test_offline_main_unavailable_warns_unverified(
    tmp_path_project: Path, save_test_issue, monkeypatch
):
    """Offline / no-remote: emit a single warning, don't error.
    Spec §A1: degrade to "warn unverified" not "skip"."""
    save_test_issue(tmp_path_project, "TMP-1", status="done")
    _stub_main_unavailable(monkeypatch, "fatal: ambiguous argument 'origin/main'")

    ctx = load_context(tmp_path_project)
    results = check_done_implies_artifacts_on_main(ctx)

    assert len(results) == 1
    assert results[0].code == "done_implies_artifacts/main_unavailable"
    assert results[0].severity == "warning"
    assert "git fetch origin" in (results[0].fix_hint or "")


def test_validate_project_integrates_rule(
    tmp_path_project: Path, save_test_issue, monkeypatch
):
    """End-to-end: validate_project picks up the new rule via ALL_CHECKS."""
    save_test_issue(tmp_path_project, "TMP-1", status="done")
    _stub_main(monkeypatch, set())

    report = validate_project(tmp_path_project)
    new_findings = [
        f for f in report.findings if f.code.startswith("done_implies_artifacts/")
    ]
    assert new_findings, "expected the new rule to fire from validate_project"


def test_project_specific_manifest_overrides_defaults(
    tmp_path_project: Path, save_test_issue, monkeypatch
):
    """If project.yaml.artifact_manifest narrows the issue list, only
    those files are required."""
    (tmp_path_project / "project.yaml").write_text(
        "name: tmp\n"
        "key_prefix: TMP\n"
        "next_issue_number: 1\n"
        "next_session_number: 1\n"
        "artifact_manifest:\n"
        "  session_required: []\n"
        "  issue_required: [only-this.md]\n",
        encoding="utf-8",
    )
    save_test_issue(tmp_path_project, "TMP-1", status="done")
    _stub_main(monkeypatch, set())

    ctx = load_context(tmp_path_project)
    results = check_done_implies_artifacts_on_main(ctx)
    assert len(results) == 1
    assert "issues/TMP-1/only-this.md" in results[0].message


# ----------------------------------------------------------------------------
# git_helpers.list_paths_on_main — the underlying helper
# ----------------------------------------------------------------------------


def test_list_paths_on_main_raises_on_non_repo(tmp_path: Path):
    """Bare temp dir is not a git repo → MainTreeUnavailable."""
    with pytest.raises(git_helpers.MainTreeUnavailable):
        git_helpers.list_paths_on_main(tmp_path)

"""Validator rule `self_review_implies_pm_response` (v0.7.9 §A9).

If a session's ``self-review.md`` is on origin/main, its
``pm-response.md`` must be too. Catches the "PM forgot to respond"
state — a session whose author finished and pushed self-review but
the PM never closed the loop.
"""

from pathlib import Path

from tripwire.core import git_helpers
from tripwire.core.validator import load_context
from tripwire.core.validator.lint import self_review_implies_pm_response


def _stub_main(monkeypatch, paths: set[str]) -> None:
    monkeypatch.setattr(
        self_review_implies_pm_response,
        "list_paths_on_main",
        lambda _project_dir: set(paths),
    )


def _stub_main_unavailable(monkeypatch, message: str = "no remote") -> None:
    def _raise(_project_dir):
        raise git_helpers.MainTreeUnavailable(message)

    monkeypatch.setattr(self_review_implies_pm_response, "list_paths_on_main", _raise)


def test_self_review_without_pm_response_errors(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """self-review.md on main but pm-response.md missing → 1 error
    with code ``self_review_implies_pm_response/missing_pm_response``."""
    save_test_session(tmp_path_project, "s1", status="in_review")
    _stub_main(monkeypatch, {"sessions/s1/self-review.md"})

    ctx = load_context(tmp_path_project)
    results = self_review_implies_pm_response.check(ctx)

    assert len(results) == 1
    assert results[0].code == "self_review_implies_pm_response/missing_pm_response"
    assert results[0].severity == "error"
    assert "sessions/s1/pm-response.md" in results[0].message
    assert "s1" in results[0].message


def test_self_review_with_pm_response_passes(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    save_test_session(tmp_path_project, "s1", status="in_review")
    _stub_main(
        monkeypatch,
        {"sessions/s1/self-review.md", "sessions/s1/pm-response.md"},
    )

    ctx = load_context(tmp_path_project)
    assert self_review_implies_pm_response.check(ctx) == []


def test_no_self_review_passes(tmp_path_project: Path, save_test_session, monkeypatch):
    """No self-review.md on main → rule has nothing to assert about
    pm-response.md → no findings (regardless of session status)."""
    save_test_session(tmp_path_project, "s1", status="executing")
    _stub_main(monkeypatch, set())

    ctx = load_context(tmp_path_project)
    assert self_review_implies_pm_response.check(ctx) == []


def test_only_iterates_known_sessions(tmp_path_project: Path, monkeypatch):
    """A self-review.md path on main for a session that doesn't exist
    in the project is ignored — the rule cares about live sessions."""
    _stub_main(
        monkeypatch,
        {"sessions/ghost/self-review.md"},  # no matching session.yaml
    )

    ctx = load_context(tmp_path_project)
    assert self_review_implies_pm_response.check(ctx) == []


def test_offline_main_unavailable_warns_unverified(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """Offline / no-remote: emit one warning, don't error.
    Mirror of done_implies_artifacts/main_unavailable behaviour."""
    save_test_session(tmp_path_project, "s1", status="in_review")
    _stub_main_unavailable(monkeypatch, "fatal: no origin/main")

    ctx = load_context(tmp_path_project)
    results = self_review_implies_pm_response.check(ctx)

    assert len(results) == 1
    assert results[0].code == "self_review_implies_pm_response/main_unavailable"
    assert results[0].severity == "warning"

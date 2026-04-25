"""Validator rule `pm_response_followups_resolve` (v0.7.9 §A9).

Every ``items[].follow_up: KUI-XX`` in a session's pm-response.md
must reference an existing issue. Detects dangling follow-ups that
the PM cited but never created.
"""

from pathlib import Path

import yaml

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import pm_response_followups_resolve


def _write_pm_response(project_dir: Path, sid: str, items: list[dict]) -> None:
    """Write a pm-response.md with the given ``items`` frontmatter."""
    path = project_dir / "sessions" / sid / "pm-response.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump({"items": items}).strip()
    path.write_text(f"---\n{fm}\n---\nbody\n", encoding="utf-8")


def test_dangling_followup_errors(tmp_path_project: Path, save_test_session):
    """follow_up references TMP-99 which doesn't exist → 1 error."""
    save_test_session(tmp_path_project, "s1", status="in_review")
    _write_pm_response(
        tmp_path_project,
        "s1",
        [{"text": "consider edge case", "follow_up": "TMP-99"}],
    )

    ctx = load_context(tmp_path_project)
    results = pm_response_followups_resolve.check(ctx)

    assert len(results) == 1
    assert results[0].code == "pm_response_followups_resolve/dangling_reference"
    assert results[0].severity == "error"
    assert "TMP-99" in results[0].message
    assert "sessions/s1/pm-response.md" == results[0].file


def test_resolving_followup_passes(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1")
    save_test_session(tmp_path_project, "s1", status="in_review")
    _write_pm_response(
        tmp_path_project,
        "s1",
        [{"text": "ok", "follow_up": "TMP-1"}],
    )

    ctx = load_context(tmp_path_project)
    assert pm_response_followups_resolve.check(ctx) == []


def test_no_pm_response_passes(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="planned")
    ctx = load_context(tmp_path_project)
    assert pm_response_followups_resolve.check(ctx) == []


def test_pm_response_without_items_passes(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="in_review")
    path = tmp_path_project / "sessions" / "s1" / "pm-response.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nitems: []\n---\n", encoding="utf-8")

    ctx = load_context(tmp_path_project)
    assert pm_response_followups_resolve.check(ctx) == []


def test_pm_response_item_without_followup_passes(
    tmp_path_project: Path, save_test_session
):
    """An item with text but no follow_up: key shouldn't fire."""
    save_test_session(tmp_path_project, "s1", status="in_review")
    _write_pm_response(tmp_path_project, "s1", [{"text": "no follow-up needed"}])

    ctx = load_context(tmp_path_project)
    assert pm_response_followups_resolve.check(ctx) == []


def test_unparseable_pm_response_warns(tmp_path_project: Path, save_test_session):
    """Garbage frontmatter shouldn't crash the rule; emit a warning."""
    save_test_session(tmp_path_project, "s1", status="in_review")
    path = tmp_path_project / "sessions" / "s1" / "pm-response.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a frontmatter file at all\n", encoding="utf-8")

    ctx = load_context(tmp_path_project)
    results = pm_response_followups_resolve.check(ctx)

    assert len(results) == 1
    assert results[0].code == "pm_response_followups_resolve/parse_error"
    assert results[0].severity == "warning"


def test_multiple_dangling_one_error_per_followup(
    tmp_path_project: Path, save_test_session
):
    save_test_session(tmp_path_project, "s1", status="in_review")
    _write_pm_response(
        tmp_path_project,
        "s1",
        [
            {"text": "a", "follow_up": "TMP-50"},
            {"text": "b", "follow_up": "TMP-51"},
        ],
    )

    ctx = load_context(tmp_path_project)
    results = pm_response_followups_resolve.check(ctx)

    codes = [r.code for r in results]
    refs = sorted(
        ref for r in results for ref in ("TMP-50", "TMP-51") if ref in r.message
    )
    assert codes == ["pm_response_followups_resolve/dangling_reference"] * 2
    assert refs == ["TMP-50", "TMP-51"]

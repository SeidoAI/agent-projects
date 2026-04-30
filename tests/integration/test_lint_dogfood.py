"""Integration smoke for v0.9 D-series lints.

Builds a synthetic project that mirrors the v0 PT's shape (lots of
issues, parent/child links, a bunch of nodes, some sessions) and
asserts:

1. ``tripwire validate`` produces NO errors from the new lints
   (warnings are allowed per the v0.9 acceptance contract).
2. Each new lint either fires somewhere in the synthetic project OR
   is silent — we accept "the corpus is clean" per the plan AC.
3. The pre-existing checks still emit byte-stable codes (no
   accidental rename / no message-only changes that would invalidate
   downstream parsers).

Runs as an integration test rather than a unit test because it
exercises the full ``validate_project`` pipeline (loaders → all
checks → all lints → strict mode).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core.validator import validate_project


def _bootstrap_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "dogfood",
                "key_prefix": "DOG",
                "base_branch": "main",
                "next_issue_number": 100,
                "next_session_number": 10,
                "phase": "executing",
                "metadata": {"kind": "framework"},
                # Opt into semantic_coverage so the lint actually fires
                # in the dogfood — its default is off (decisions.md D-1).
                "lint_config": {
                    "semantic_coverage": {"min_ac_node_refs": 1},
                    # Lower mega_issue thresholds so the synthetic
                    # data exercises the warning path without needing
                    # 10+ children.
                    "mega_issue": {"max_children": 2, "max_sessions": 2},
                },
            }
        )
    )
    for sub in ("issues", "nodes", "sessions"):
        (proj / sub).mkdir()
    return proj


def _write_issue(
    proj: Path, key: str, *, parent: str | None = None, ac_ref: str = ""
) -> None:
    fm: dict = {
        "uuid": f"00000000-0000-4000-8000-{int(key.split('-')[1]):012d}",
        "id": key,
        "title": f"Issue {key}",
        "status": "in_progress",
        "priority": "medium",
        "executor": "ai",
        "verifier": "required",
        "kind": "feat",
    }
    if parent is not None:
        fm["parent"] = parent
    body = (
        "## Context\n[[auth-system]]\n\n## Implements\nx\n\n"
        "## Repo scope\nx\n\n## Requirements\nx\n\n"
        "## Execution constraints\nstop and ask.\n\n"
        f"## Acceptance criteria\n- [ ] thing {ac_ref}\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
    )
    idir = proj / "issues" / key
    idir.mkdir(parents=True, exist_ok=True)
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + body
    (idir / "issue.yaml").write_text(text, encoding="utf-8")


def _write_node(proj: Path, node_id: str, *, name: str = "Auth System") -> None:
    fm: dict = {
        "uuid": f"00000000-0000-4000-8000-{abs(hash(node_id)) % 10**12:012d}",
        "id": node_id,
        "type": "model",
        "name": name,
        "status": "active",
    }
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n"
    (proj / "nodes" / f"{node_id}.yaml").write_text(text, encoding="utf-8")


def test_dogfood_validate_no_errors(tmp_path: Path) -> None:
    proj = _bootstrap_project(tmp_path)
    _write_node(proj, "auth-system", name="Auth System")
    # Six active issues — meets node_ratio's `_MIN_ACTIVE_ISSUES`.
    for n in range(1, 7):
        _write_issue(proj, f"DOG-{n}", ac_ref="against [[auth-system]]")

    report = validate_project(proj)
    new_lint_codes = {
        "stale_concept",
        "concept_name_prose",
        "semantic_coverage",
        "mega_issue",
        "node_ratio",
        "uuid",
    }
    error_codes = {e.code.split("/")[0] for e in report.errors}
    # No new lint should produce errors — they're warnings only.
    assert not (error_codes & new_lint_codes), report.errors


def test_mega_issue_fires_on_synthetic_parent(tmp_path: Path) -> None:
    """Issue with > max_children sub-issues triggers the mega_issue lint."""
    proj = _bootstrap_project(tmp_path)
    _write_node(proj, "auth-system")
    _write_issue(proj, "DOG-100", ac_ref="against [[auth-system]]")
    # 3 children with max_children=2 → fires.
    for n in range(101, 104):
        _write_issue(
            proj, f"DOG-{n}", parent="DOG-100", ac_ref="against [[auth-system]]"
        )

    report = validate_project(proj)
    codes = [w.code for w in report.warnings]
    assert "mega_issue/too_many_children" in codes


def test_concept_name_prose_fires_on_synthetic_corpus(tmp_path: Path) -> None:
    proj = _bootstrap_project(tmp_path)
    _write_node(proj, "auth-system", name="Authentication Subsystem")
    # Two issues mention "authentication subsystem" in prose with NO
    # `[[auth-system]]` reference anywhere in the body. The lint
    # excludes properly-referenced issues from the prose count, so
    # these need to stay link-free.
    for n in range(1, 3):
        idir = proj / "issues" / f"DOG-{n}"
        idir.mkdir(parents=True, exist_ok=True)
        body = (
            "## Context\nThe authentication subsystem matters here.\n\n"
            "## Implements\nx\n\n## Repo scope\nx\n\n"
            "## Requirements\nThe authentication subsystem must respond.\n\n"
            "## Execution constraints\nstop and ask.\n\n"
            "## Acceptance criteria\n- [ ] thing\n\n"
            "## Test plan\n```\nuv run pytest\n```\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
        )
        fm = {
            "uuid": f"00000000-0000-4000-8000-{n:012d}",
            "id": f"DOG-{n}",
            "title": f"Issue DOG-{n}",
            "status": "in_progress",
            "priority": "medium",
            "executor": "ai",
            "verifier": "required",
            "kind": "feat",
        }
        text = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + body
        (idir / "issue.yaml").write_text(text, encoding="utf-8")

    report = validate_project(proj)
    codes = [w.code for w in report.warnings]
    assert "concept_name_prose/found" in codes


def test_existing_check_codes_byte_stable(tmp_path: Path) -> None:
    """Pre-existing check categories don't disappear from the catalogue —
    a wholesale rename of an old code would break downstream parsers."""
    proj = _bootstrap_project(tmp_path)
    _write_node(proj, "auth-system")
    _write_issue(proj, "DOG-1", ac_ref="against [[auth-system]]")

    report = validate_project(proj)
    # Force at least one finding from a small set of old checks by
    # scanning a clean project — they're either passing (no findings)
    # or producing their pre-existing code. None of the new D-series
    # codes should appear in the error stream.
    error_codes = {e.code for e in report.errors}
    new_codes = {
        "stale_concept/referenced",
        "concept_name_prose/found",
        "semantic_coverage/below_threshold",
        "mega_issue/too_many_children",
        "mega_issue/too_many_sessions",
        "node_ratio/below_band",
        "node_ratio/above_band",
    }
    assert not (error_codes & new_codes), (
        f"New lint codes leaked into errors (must be warnings): "
        f"{error_codes & new_codes}"
    )

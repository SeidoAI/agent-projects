"""v0.7.9 §A3 — pm_response validator rules.

Two rules ship in this session:

- ``pm_response_covers_self_review``: every bullet under a
  ``## Lens N:`` heading in self-review.md must have a matching
  ``items[].quote_excerpt`` in pm-response.yaml (substring match).
  Code: ``pm_response/incomplete_coverage``.

- ``pm_response_followups_resolve``: every
  ``items[].follow_up: KUI-XX`` in pm-response.yaml must reference
  an existing issue. Code: ``pm_response/missing_followup``.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.validator import (
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
    load_context,
)


def _seed_session_artifacts(
    project_dir: Path, sid: str, *, self_review: str, pm_response: str
) -> None:
    sdir = project_dir / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "self-review.md").write_text(self_review, encoding="utf-8")
    (sdir / "pm-response.yaml").write_text(pm_response, encoding="utf-8")


# ---------------------------------------------------------------------------
# pm_response_covers_self_review
# ---------------------------------------------------------------------------


class TestPmResponseCoversSelfReview:
    def test_pm_response_covers_self_review_passes_when_all_addressed(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _seed_session_artifacts(
            tmp_path_project,
            "s1",
            self_review=(
                "## Lens 1: AC met\n"
                "- alpha thing\n"
                "- beta thing\n"
            ),
            pm_response=(
                "items:\n"
                '  - quote_excerpt: "alpha"\n'
                "    decision: accepted\n"
                '  - quote_excerpt: "beta"\n'
                "    decision: accepted\n"
            ),
        )
        ctx = load_context(tmp_path_project)
        assert check_pm_response_covers_self_review(ctx) == []

    def test_pm_response_covers_self_review_fails_with_5_items_and_4_responses(
        self, tmp_path_project, save_test_session
    ) -> None:
        """Issue AC fixture: deliberate 5 self-review items, 4 pm-response
        items — must produce ``pm_response/incomplete_coverage``."""
        save_test_session(tmp_path_project, "s1", status="executing")
        _seed_session_artifacts(
            tmp_path_project,
            "s1",
            self_review=(
                "## Lens 1: AC\n"
                "- alpha thing\n"
                "- beta thing\n"
                "## Lens 2: Decisions\n"
                "- gamma thing\n"
                "## Lens 3: Skipped\n"
                "- delta thing\n"
                "## Lens 4: Quality\n"
                "- epsilon thing\n"
            ),
            pm_response=(
                "items:\n"
                '  - quote_excerpt: "alpha"\n    decision: accepted\n'
                '  - quote_excerpt: "beta"\n    decision: accepted\n'
                '  - quote_excerpt: "gamma"\n    decision: accepted\n'
                '  - quote_excerpt: "delta"\n    decision: accepted\n'
                # epsilon missing on purpose
            ),
        )
        ctx = load_context(tmp_path_project)
        results = check_pm_response_covers_self_review(ctx)

        assert len(results) >= 1
        codes = {r.code for r in results}
        assert "pm_response/incomplete_coverage" in codes
        # Failing self-review item is mentioned in the error message.
        joined = " ".join(r.message for r in results)
        assert "epsilon" in joined

    def test_pm_response_covers_self_review_skips_when_self_review_absent(
        self, tmp_path_project, save_test_session
    ) -> None:
        """If self-review.md isn't on disk, this rule has nothing to
        check — done_implies_artifacts_on_main is the rule that
        enforces presence."""
        save_test_session(tmp_path_project, "s1", status="executing")
        # No artifacts written.
        ctx = load_context(tmp_path_project)
        assert check_pm_response_covers_self_review(ctx) == []

    def test_pm_response_covers_self_review_fails_when_pm_response_missing(
        self, tmp_path_project, save_test_session
    ) -> None:
        """Self-review present, pm-response absent → every self-review
        item is uncovered."""
        save_test_session(tmp_path_project, "s1", status="executing")
        sdir = tmp_path_project / "sessions" / "s1"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "self-review.md").write_text(
            "## Lens 1: AC\n- alpha\n- beta\n", encoding="utf-8"
        )
        ctx = load_context(tmp_path_project)
        results = check_pm_response_covers_self_review(ctx)
        codes = {r.code for r in results}
        assert "pm_response/missing_file" in codes

    def test_pm_response_covers_self_review_handles_malformed_yaml(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        _seed_session_artifacts(
            tmp_path_project,
            "s1",
            self_review="## Lens 1: AC\n- alpha\n",
            pm_response="items:\n  - : not parseable\n",
        )
        ctx = load_context(tmp_path_project)
        results = check_pm_response_covers_self_review(ctx)
        codes = {r.code for r in results}
        assert "pm_response/parse_error" in codes


# ---------------------------------------------------------------------------
# pm_response_followups_resolve
# ---------------------------------------------------------------------------


class TestPmResponseFollowupsResolve:
    def test_followup_referencing_existing_issue_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ) -> None:
        save_test_issue(tmp_path_project, "TMP-1")
        save_test_session(tmp_path_project, "s1", status="executing")
        sdir = tmp_path_project / "sessions" / "s1"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "pm-response.yaml").write_text(
            "items:\n"
            '  - quote_excerpt: "x"\n'
            "    decision: deferred\n"
            "    follow_up: TMP-1\n",
            encoding="utf-8",
        )
        ctx = load_context(tmp_path_project)
        assert check_pm_response_followups_resolve(ctx) == []

    def test_followup_referencing_nonexistent_issue_fails(
        self, tmp_path_project, save_test_session
    ) -> None:
        """AC fixture: ``follow_up: KUI-9999`` (no such issue) → fails
        with code ``pm_response/missing_followup``."""
        save_test_session(tmp_path_project, "s1", status="executing")
        sdir = tmp_path_project / "sessions" / "s1"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "pm-response.yaml").write_text(
            "items:\n"
            '  - quote_excerpt: "x"\n'
            "    decision: deferred\n"
            "    follow_up: KUI-9999\n",
            encoding="utf-8",
        )
        ctx = load_context(tmp_path_project)
        results = check_pm_response_followups_resolve(ctx)
        codes = {r.code for r in results}
        assert "pm_response/missing_followup" in codes
        joined = " ".join(r.message for r in results)
        assert "KUI-9999" in joined

    def test_followups_resolve_skips_when_pm_response_absent(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        ctx = load_context(tmp_path_project)
        assert check_pm_response_followups_resolve(ctx) == []

    def test_followups_resolve_ignores_items_without_follow_up(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="executing")
        sdir = tmp_path_project / "sessions" / "s1"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "pm-response.yaml").write_text(
            "items:\n"
            '  - quote_excerpt: "x"\n'
            "    decision: accepted\n"
            '  - quote_excerpt: "y"\n'
            "    decision: rejected\n",
            encoding="utf-8",
        )
        ctx = load_context(tmp_path_project)
        assert check_pm_response_followups_resolve(ctx) == []

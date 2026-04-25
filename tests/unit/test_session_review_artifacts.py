"""Tests for `core/session_review_artifacts.py` — pure functions that
parse self-review.md + pm-response.yaml and produce a side-by-side
report.

Sibling to ``core/session_review.py`` (which reviews a PR diff vs.
issue ACs). These two modules are intentionally separate: different
inputs, different consumers, different gates downstream.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_self_review(session_dir: Path, body: str) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "self-review.md").write_text(body, encoding="utf-8")


def _write_pm_response(session_dir: Path, body: str) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "pm-response.yaml").write_text(body, encoding="utf-8")


# ----------------------------------------------------------------------------
# parse_self_review_items
# ----------------------------------------------------------------------------


class TestParseSelfReviewItems:
    def test_returns_one_item_per_bullet_under_each_lens(self) -> None:
        from tripwire.core.session_review_artifacts import parse_self_review_items

        body = (
            "# Self-review — s1\n\n"
            "## Lens 1: AC met but not really\n"
            "- mypy disables 9 categories — soft yes\n"
            "- README rendered — soft yes\n\n"
            "## Lens 2: Unilateral decisions\n"
            "- went with click.Path over plain Path\n\n"
            "## Lens 3: Skipped workflow\n"
            "- skipped manual dry-run\n\n"
            "## Lens 4: Quality degradation over time\n"
            "- last commit has thinner docstrings\n"
        )
        items = parse_self_review_items(body)
        assert len(items) == 5
        assert items[0].lens == 1
        assert items[0].text.startswith("mypy disables 9 categories")
        assert items[2].lens == 2
        assert items[3].lens == 3
        assert items[4].lens == 4

    def test_ignores_lens_section_header_text(self) -> None:
        """Header text like 'AC met but not really' must not be parsed
        as a self-review item."""
        from tripwire.core.session_review_artifacts import parse_self_review_items

        body = (
            "## Lens 1: AC met but not really\n"
            "<walk every [x]…>\n\n"
            "## Lens 2: Unilateral decisions\n"
            "- only-real-bullet\n"
        )
        items = parse_self_review_items(body)
        assert len(items) == 1
        assert items[0].text == "only-real-bullet"

    def test_empty_self_review_returns_empty_list(self) -> None:
        from tripwire.core.session_review_artifacts import parse_self_review_items

        assert parse_self_review_items("") == []
        assert parse_self_review_items("# heading only\n") == []


# ----------------------------------------------------------------------------
# parse_pm_response_items
# ----------------------------------------------------------------------------


class TestParsePmResponseItems:
    def test_returns_quote_excerpts_and_decisions(self) -> None:
        from tripwire.core.session_review_artifacts import parse_pm_response_items

        body = (
            "read_at: 2026-04-25T15:00:00Z\n"
            "read_by: pm\n"
            "items:\n"
            '  - quote_excerpt: "mypy disables 9 categories"\n'
            "    decision: deferred\n"
            "    follow_up: KUI-91\n"
            "    note: tighten in v0.7.10\n"
        )
        items = parse_pm_response_items(body)
        assert len(items) == 1
        assert items[0].quote_excerpt == "mypy disables 9 categories"
        assert items[0].decision == "deferred"
        assert items[0].follow_up == "KUI-91"

    def test_no_items_key_returns_empty_list(self) -> None:
        from tripwire.core.session_review_artifacts import parse_pm_response_items

        assert parse_pm_response_items("read_at: x\n") == []

    def test_malformed_yaml_raises(self) -> None:
        from tripwire.core.session_review_artifacts import parse_pm_response_items

        with pytest.raises(ValueError):
            parse_pm_response_items("items:\n  - : not: parseable\n")


# ----------------------------------------------------------------------------
# build_report
# ----------------------------------------------------------------------------


class TestBuildReport:
    def test_pairs_self_review_items_with_pm_response_via_substring(
        self, tmp_path: Path
    ) -> None:
        from tripwire.core.session_review_artifacts import build_report

        sdir = tmp_path / "sessions" / "s1"
        _write_self_review(
            sdir,
            "## Lens 1: AC\n- mypy disables 9 categories\n- README rendered\n",
        )
        _write_pm_response(
            sdir,
            "items:\n"
            '  - quote_excerpt: "mypy disables 9"\n'
            "    decision: deferred\n"
            "    follow_up: KUI-91\n"
            '  - quote_excerpt: "README rendered"\n'
            "    decision: accepted\n",
        )

        report = build_report(tmp_path, "s1")
        assert report.self_review_present
        assert report.pm_response_present
        assert len(report.pairs) == 2
        assert report.pairs[0].self_review_text.startswith("mypy disables 9")
        assert report.pairs[0].pm_response is not None
        assert report.pairs[0].pm_response.decision == "deferred"
        assert report.unaddressed == []

    def test_unaddressed_self_review_item_flagged(self, tmp_path: Path) -> None:
        from tripwire.core.session_review_artifacts import build_report

        sdir = tmp_path / "sessions" / "s1"
        _write_self_review(
            sdir,
            "## Lens 1: AC\n- alpha thing\n- beta thing\n- gamma thing\n",
        )
        _write_pm_response(
            sdir,
            "items:\n"
            '  - quote_excerpt: "alpha"\n'
            "    decision: accepted\n"
            '  - quote_excerpt: "gamma"\n'
            "    decision: accepted\n",
        )

        report = build_report(tmp_path, "s1")
        assert len(report.unaddressed) == 1
        assert report.unaddressed[0].text == "beta thing"

    def test_missing_self_review_marks_absent_no_crash(self, tmp_path: Path) -> None:
        from tripwire.core.session_review_artifacts import build_report

        # No files at all in sessions/s1/
        sdir = tmp_path / "sessions" / "s1"
        sdir.mkdir(parents=True)

        report = build_report(tmp_path, "s1")
        assert not report.self_review_present
        assert not report.pm_response_present
        assert report.pairs == []

    def test_missing_pm_response_with_self_review_present(self, tmp_path: Path) -> None:
        from tripwire.core.session_review_artifacts import build_report

        sdir = tmp_path / "sessions" / "s1"
        _write_self_review(sdir, "## Lens 1: AC\n- alpha thing\n")
        report = build_report(tmp_path, "s1")
        assert report.self_review_present
        assert not report.pm_response_present
        # Every self-review item is unaddressed when pm-response absent.
        assert len(report.unaddressed) == 1

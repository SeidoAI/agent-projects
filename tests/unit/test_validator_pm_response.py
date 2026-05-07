"""pm_response validator rules.

Two coherence rules ship in this module:

- ``pm_response_covers_self_review``: every bullet under a
  ``## Lens N:`` heading in self-review.md must have a matching
  ``items[].quote_excerpt`` in pm-response.yaml (substring match).
  Code: ``pm_response/incomplete_coverage``.

- ``pm_response_followups_resolve``: every
  ``items[].follow_up: KUI-XX`` in pm-response.yaml must reference
  an existing issue. Code: ``pm_response/missing_followup``.

v0.11.1: both checks are gated on the manifest's
``pm-response.produced_at`` (``completed`` by default), so they only
fire on sessions that have reached the lifecycle threshold. Earlier
behaviour (firing on every status, including ``executing``) caused
agents at exit-protocol time to mistake the PM-side fix-hint for an
agent task — see the project-kb-pivot post-mortem. Missing-file
enforcement is delegated to ``check_artifact_presence``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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


def _augment_manifest_with_pm_response(project_dir: Path) -> None:
    """Add a `pm-response` entry to the test project's artifact manifest.

    The bare `tmp_path_project` fixture ships a one-artifact manifest
    (`plan`). The pm-response coherence checks consult the manifest for
    `pm-response.produced_at` to gate themselves; without an entry, both
    checks short-circuit. This helper writes the realistic shipping
    shape: pm-response declared with `produced_at: completed`,
    `produced_by: pm`, `owned_by: pm`.
    """
    import yaml

    manifest_path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["artifacts"].append(
        {
            "name": "pm-response",
            "file": "pm-response.yaml",
            "template": "pm-response.yaml.j2",
            "produced_at": "completed",
            "produced_by": "pm",
            "owned_by": "pm",
            "required": True,
            "approval_gate": False,
        }
    )
    manifest_path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture(autouse=True)
def _ensure_pm_response_manifest_entry(tmp_path_project: Path) -> None:
    """Every test in this module operates on a manifest that declares
    `pm-response` — that's the shape the coherence checks gate against."""
    _augment_manifest_with_pm_response(tmp_path_project)


# ---------------------------------------------------------------------------
# pm_response_covers_self_review
# ---------------------------------------------------------------------------


class TestPmResponseCoversSelfReview:
    def test_pm_response_covers_self_review_passes_when_all_addressed(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="completed")
        _seed_session_artifacts(
            tmp_path_project,
            "s1",
            self_review=("## Lens 1: AC met\n- alpha thing\n- beta thing\n"),
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
        save_test_session(tmp_path_project, "s1", status="completed")
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
        # New v0.11.1 behaviour: hint self-identifies as a PM action.
        joined_hints = " ".join((r.fix_hint or "") for r in results)
        assert "PM action" in joined_hints

    def test_pm_response_covers_self_review_skips_when_self_review_absent(
        self, tmp_path_project, save_test_session
    ) -> None:
        """If self-review.md isn't on disk, this rule has nothing to
        check — `check_artifact_presence` enforces presence."""
        save_test_session(tmp_path_project, "s1", status="completed")
        # No artifacts written.
        ctx = load_context(tmp_path_project)
        assert check_pm_response_covers_self_review(ctx) == []

    def test_pm_response_covers_self_review_returns_empty_when_pm_response_missing(
        self, tmp_path_project, save_test_session
    ) -> None:
        """v0.11.1: missing pm-response.yaml is no longer reported by the
        coverage check (it's a presence concern handled by
        `check_artifact_presence`). The coverage check returns no
        findings when there's nothing to cover against."""
        save_test_session(tmp_path_project, "s1", status="completed")
        sdir = tmp_path_project / "sessions" / "s1"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "self-review.md").write_text(
            "## Lens 1: AC\n- alpha\n- beta\n", encoding="utf-8"
        )
        ctx = load_context(tmp_path_project)
        results = check_pm_response_covers_self_review(ctx)
        codes = {r.code for r in results}
        # The deleted code must no longer surface from this check.
        assert "pm_response/missing_file" not in codes
        # And no other findings are emitted — the coverage check has no
        # work to do without a pm-response to cover against.
        assert results == []

    def test_pm_response_covers_self_review_handles_malformed_yaml(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="completed")
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
        # Hint identifies this as a PM action.
        hint = next(
            r.fix_hint or "" for r in results if r.code == "pm_response/parse_error"
        )
        assert "PM action" in hint


# ---------------------------------------------------------------------------
# pm_response_followups_resolve
# ---------------------------------------------------------------------------


class TestPmResponseFollowupsResolve:
    def test_followup_referencing_existing_issue_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ) -> None:
        save_test_issue(tmp_path_project, "TMP-1")
        save_test_session(tmp_path_project, "s1", status="completed")
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
        save_test_session(tmp_path_project, "s1", status="completed")
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
        # Hint self-identifies as PM action.
        hint = next(r.fix_hint or "" for r in results)
        assert "PM action" in hint

    def test_followups_resolve_skips_when_pm_response_absent(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="completed")
        ctx = load_context(tmp_path_project)
        assert check_pm_response_followups_resolve(ctx) == []

    def test_followups_resolve_ignores_items_without_follow_up(
        self, tmp_path_project, save_test_session
    ) -> None:
        save_test_session(tmp_path_project, "s1", status="completed")
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


# ---------------------------------------------------------------------------
# v0.11.1 — produced_at gate (regression: agent-side validate must not
# surface pm_response/* findings while the session is still pre-completed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    ["planned", "queued", "executing", "in_review", "verified"],
)
class TestProducedAtGate:
    """For every pre-completed status, both checks must return zero
    findings even when the on-disk content would otherwise fail.

    Reproduces the project-kb-pivot trap: agent at executing wrote
    self-review.md without authoring pm-response.yaml; the validator
    used to fire `pm_response/missing_file` on that state and misdirect
    the agent into authoring a PM-owned artifact. After v0.11.1 the
    coherence checks no longer fire pre-completion.
    """

    def test_coverage_check_returns_empty_pre_completion(
        self, tmp_path_project, save_test_session, status: str
    ) -> None:
        save_test_session(tmp_path_project, "s1", status=status)
        sdir = tmp_path_project / "sessions" / "s1"
        sdir.mkdir(parents=True, exist_ok=True)
        # Self-review present but no pm-response — the original trap.
        (sdir / "self-review.md").write_text(
            "## Lens 1: AC\n- alpha\n- beta\n", encoding="utf-8"
        )
        ctx = load_context(tmp_path_project)
        assert check_pm_response_covers_self_review(ctx) == []

    def test_coverage_check_skips_malformed_pm_response_pre_completion(
        self, tmp_path_project, save_test_session, status: str
    ) -> None:
        save_test_session(tmp_path_project, "s1", status=status)
        _seed_session_artifacts(
            tmp_path_project,
            "s1",
            self_review="## Lens 1: AC\n- alpha\n",
            pm_response="items:\n  - : not parseable\n",
        )
        ctx = load_context(tmp_path_project)
        assert check_pm_response_covers_self_review(ctx) == []

    def test_followups_check_skips_unresolved_followup_pre_completion(
        self, tmp_path_project, save_test_session, status: str
    ) -> None:
        save_test_session(tmp_path_project, "s1", status=status)
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
        assert check_pm_response_followups_resolve(ctx) == []

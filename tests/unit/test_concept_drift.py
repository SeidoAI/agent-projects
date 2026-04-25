"""Tests for `lint/concept_drift` — the precision-first orphan-concept lint."""

from pathlib import Path

import pytest

from tripwire.core import lint_rules  # noqa: F401 — registers rules
from tripwire.core.linter import Linter

FINDINGS_CODE = "lint/concept_drift"


# ---------------------------------------------------------------------------
# Noise-zone stripping
# ---------------------------------------------------------------------------


def _findings(project: Path) -> list:
    linter = Linter(project_dir=project)
    return [f for f in linter.run_stage("scoping") if f.code == FINDINGS_CODE]


class TestNoiseStripping:
    def test_section_headers_ignored(self, save_test_issue, tmp_path_project):
        """Markdown headers like `## Context` shouldn't yield findings."""
        # Three issues all with the same header text so cross-issue count
        # would otherwise dominate.
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="## Context Free Section\nordinary prose.\n",
            )
        assert all(
            "Context Free Section" not in f.message for f in _findings(tmp_path_project)
        )

    def test_fenced_code_blocks_ignored(self, save_test_issue, tmp_path_project):
        """Multi-word title-case inside fenced code blocks isn't prose."""
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="```\nMy Special Thing called CodeBlock Marker\n```\n",
            )
        assert all(
            "CodeBlock Marker" not in f.message for f in _findings(tmp_path_project)
        )

    def test_existing_refs_ignored(
        self, save_test_issue, save_test_node, tmp_path_project
    ):
        """A `[[node-id]]` reference already links to a node — never a finding."""
        save_test_node(tmp_path_project, node_id="some-node", name="Some Node")
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="See [[some-node]] for details.\n",
            )
        # No multi-word title-case terms left after the [[some-node]] strip.
        # Specifically, the term inside the brackets shouldn't surface as a
        # candidate.
        assert not any("some-node" in f.message for f in _findings(tmp_path_project))

    def test_inline_code_ignored(self, save_test_issue, tmp_path_project):
        """Inline-code-fenced terms (e.g. `My Marker`) shouldn't surface."""
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="run `Special Marker Phrase` to do x.\n",
            )
        assert all(
            "Special Marker Phrase" not in f.message
            for f in _findings(tmp_path_project)
        )

    def test_urls_ignored(self, save_test_issue, tmp_path_project):
        """A URL with title-case path segments isn't prose."""
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="see https://example.com/Some/Marker/Path now.\n",
            )
        assert all("Marker Path" not in f.message for f in _findings(tmp_path_project))


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------


class TestCandidateExtraction:
    def test_multiword_title_case_cross_issue_flagged(
        self, save_test_issue, tmp_path_project
    ):
        """A multi-word Title Case phrase in 2+ issues is a finding."""
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="The WebSocket Hub coordinates events across clients.\n",
            )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert any("WebSocket Hub" in m for m in msgs)

    def test_kebab_case_repeated_flagged(self, save_test_issue, tmp_path_project):
        """kebab-case in prose strongly suggests a missing-bracket ref,
        but on real-world spec content single mentions are mostly
        implementation-detail noise. Require ≥2 occurrences (across or
        within issues) — calibrated on tripwire-v0."""
        save_test_issue(
            tmp_path_project,
            key="TMP-1",
            title="Stub",
            body="The kanban-board matters. Update kanban-board layout.\n",
        )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert any("kanban-board" in m for m in msgs)

    def test_kebab_case_single_mention_not_flagged(
        self, save_test_issue, tmp_path_project
    ):
        """One mention of a kebab term isn't enough signal anymore."""
        save_test_issue(
            tmp_path_project,
            key="TMP-1",
            title="Stub",
            body="The kanban-board appears once.\n",
        )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("kanban-board" in m for m in msgs)

    def test_single_word_title_case_not_flagged(
        self, save_test_issue, tmp_path_project
    ):
        """Single-word Title Case is not a candidate — that's the old rule's
        false-positive zone."""
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="We use Stripe for payments.\n",
            )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("Stripe" in m for m in msgs)

    def test_single_issue_single_mention_not_flagged(
        self, save_test_issue, tmp_path_project
    ):
        """A multi-word phrase mentioned once in one issue is too weak."""
        save_test_issue(
            tmp_path_project,
            key="TMP-1",
            title="Stub",
            body="A passing reference to The Random Phrase appears here.\n",
        )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("Random Phrase" in m for m in msgs)

    def test_within_issue_repeat_flagged(self, save_test_issue, tmp_path_project):
        """3+ mentions within one issue = enough signal even if no other issue
        mentions it."""
        body = (
            "We use the Background Worker. The Background Worker handles jobs.\n"
            "The Background Worker is critical.\n"
        )
        save_test_issue(tmp_path_project, key="TMP-1", title="Stub", body=body)
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert any("Background Worker" in m for m in msgs)


# ---------------------------------------------------------------------------
# Filter against existing nodes (incl. fuzzy)
# ---------------------------------------------------------------------------


class TestNodeFiltering:
    def test_exact_node_name_filtered(
        self, save_test_issue, save_test_node, tmp_path_project
    ):
        save_test_node(tmp_path_project, node_id="websocket-hub", name="WebSocket Hub")
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="The WebSocket Hub coordinates events.\n",
            )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("WebSocket Hub" in m for m in msgs)

    def test_fuzzy_node_match_filtered(
        self, save_test_issue, save_test_node, tmp_path_project
    ):
        """`Project Shell` in prose should match the `project-shell` node."""
        save_test_node(tmp_path_project, node_id="project-shell", name="Project Shell")
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="The Project Shell coordinates layouts.\n",
            )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("Project Shell" in m for m in msgs)

    def test_kebab_form_matches_node_id(
        self, save_test_issue, save_test_node, tmp_path_project
    ):
        """Bare kebab-case `project-shell` should also match the node id."""
        save_test_node(tmp_path_project, node_id="project-shell", name="Project Shell")
        save_test_issue(
            tmp_path_project,
            key="TMP-1",
            title="Stub",
            body="Tweak the project-shell settings.\n",
        )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("project-shell" in m for m in msgs)


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_allowlisted_term_suppressed(self, save_test_issue, tmp_path_project):
        allow = tmp_path_project / "lint" / "concept-allowlist.yaml"
        allow.parent.mkdir(parents=True)
        allow.write_text(
            'allowlist:\n  - term: "WebSocket Hub"\n    reason: "stub."\n',
            encoding="utf-8",
        )
        for i in range(1, 4):
            save_test_issue(
                tmp_path_project,
                key=f"TMP-{i}",
                title=f"Stub {i}",
                body="The WebSocket Hub coordinates everything.\n",
            )
        msgs = [f.message for f in _findings(tmp_path_project)]
        assert not any("WebSocket Hub" in m for m in msgs)

    def test_malformed_allowlist_propagates(self, save_test_issue, tmp_path_project):
        """If the allowlist is malformed, the lint run errors out — fail
        loudly rather than silently bypass the file."""
        allow = tmp_path_project / "lint" / "concept-allowlist.yaml"
        allow.parent.mkdir(parents=True)
        allow.write_text("allowlist:\n  - term: x\n", encoding="utf-8")  # no reason
        save_test_issue(
            tmp_path_project, key="TMP-1", title="Stub", body="Some Random Phrase.\n"
        )
        with pytest.raises(Exception):  # noqa: B017 — exact type is allowlist's
            _findings(tmp_path_project)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestReporting:
    def test_global_cap(self, save_test_issue, tmp_path_project):
        """Cap total findings at MAX_FINDINGS (one finding per term)."""
        from tripwire.core.lint_rules.concept_drift import MAX_FINDINGS

        # Generate enough qualifying kebab-case terms (each appearing
        # within-issue ≥2) to exceed the cap.
        n_terms = MAX_FINDINGS + 5
        body_lines = []
        for i in range(n_terms):
            body_lines.append(f"foo alpha{i:03}-beta{i:03} matters.")
            body_lines.append(f"foo alpha{i:03}-beta{i:03} matters again.")
        save_test_issue(
            tmp_path_project,
            key="TMP-1",
            title="Stub",
            body="\n".join(body_lines) + "\n",
        )
        findings = _findings(tmp_path_project)
        assert len(findings) <= MAX_FINDINGS

    def test_finding_includes_fix_hint(self, save_test_issue, tmp_path_project):
        save_test_issue(
            tmp_path_project,
            key="TMP-1",
            title="Stub",
            body="The kanban-board is central. The kanban-board ships next.\n",
        )
        findings = _findings(tmp_path_project)
        kanban = [f for f in findings if "kanban-board" in f.message]
        assert kanban
        assert kanban[0].fix_hint  # non-empty
        assert kanban[0].severity == "warning"

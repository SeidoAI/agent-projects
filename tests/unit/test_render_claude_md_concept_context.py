"""Tests for v0.7.3 item F — CLAUDE.md "Concept context" section.

When a session's plan.md references concept nodes via `[[id]]`, the
prep-rendered CLAUDE.md surfaces those references with their node-file
paths so the agent reads them at session start. This closes the
"agent burns reconnaissance discovering plan-referenced concepts"
gap.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.concept_context import ConceptContextEntry
from tripwire.models.session import WorktreeEntry
from tripwire.runtimes.prep import render_claude_md


def _setup_worktree(path: Path) -> Path:
    """Minimal code worktree: an existing directory. CLAUDE.md ends up here."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_claude_md(worktree: Path) -> str:
    return (worktree / "CLAUDE.md").read_text()


class TestConceptContextRendering:
    def test_section_present_when_refs_exist(self, tmp_path):
        wt = _setup_worktree(tmp_path / "code")
        concepts = [
            ConceptContextEntry(
                id="user-model",
                node_path=Path("/proj/nodes/user-model.yaml"),
                exists=True,
            ),
            ConceptContextEntry(
                id="auth-flow",
                node_path=Path("/proj/nodes/auth-flow.yaml"),
                exists=True,
            ),
        ]
        render_claude_md(
            code_worktree=wt,
            agent_id="backend-coder",
            skill_names=["backend-development"],
            worktrees=[
                WorktreeEntry(
                    repo="X/y",
                    clone_path=str(wt.parent),
                    worktree_path=str(wt),
                    branch="feat/x",
                )
            ],
            session_id="s1",
            concept_context=concepts,
        )
        body = _read_claude_md(wt)
        assert "## Concept context" in body
        assert "[[user-model]]" in body
        assert "[[auth-flow]]" in body
        assert "/proj/nodes/user-model.yaml" in body
        # Both nodes exist — no warning marker.
        assert "NODE FILE NOT FOUND" not in body

    def test_warning_marker_on_unresolved_ref(self, tmp_path):
        wt = _setup_worktree(tmp_path / "code")
        concepts = [
            ConceptContextEntry(
                id="ghost",
                node_path=Path("/proj/nodes/ghost.yaml"),
                exists=False,
            ),
        ]
        render_claude_md(
            code_worktree=wt,
            agent_id="backend-coder",
            skill_names=["backend-development"],
            worktrees=[
                WorktreeEntry(
                    repo="X/y",
                    clone_path=str(wt.parent),
                    worktree_path=str(wt),
                    branch="feat/x",
                )
            ],
            session_id="s1",
            concept_context=concepts,
        )
        body = _read_claude_md(wt)
        assert "[[ghost]]" in body
        assert "NODE FILE NOT FOUND" in body

    def test_section_omitted_when_no_refs(self, tmp_path):
        """Empty concept context → no Concept context section at all.

        Avoids polluting CLAUDE.md with an empty heading when the plan
        has no [[refs]].
        """
        wt = _setup_worktree(tmp_path / "code")
        render_claude_md(
            code_worktree=wt,
            agent_id="backend-coder",
            skill_names=["backend-development"],
            worktrees=[
                WorktreeEntry(
                    repo="X/y",
                    clone_path=str(wt.parent),
                    worktree_path=str(wt),
                    branch="feat/x",
                )
            ],
            session_id="s1",
            concept_context=[],
        )
        body = _read_claude_md(wt)
        assert "## Concept context" not in body
        # Other sections still rendered.
        assert "## Worktrees" in body
        assert "## Session" in body

    def test_concept_context_change_invalidates_sentinel(self, tmp_path):
        """Re-render with a different concept_context must rewrite CLAUDE.md.

        Sentinel-based idempotency was the failure mode that motivated
        bumping the sentinel hash to fold concept_context in.
        """
        wt = _setup_worktree(tmp_path / "code")
        first = [
            ConceptContextEntry(
                id="alpha",
                node_path=Path("/proj/nodes/alpha.yaml"),
                exists=True,
            ),
        ]
        common_kwargs = {
            "code_worktree": wt,
            "agent_id": "backend-coder",
            "skill_names": ["backend-development"],
            "worktrees": [
                WorktreeEntry(
                    repo="X/y",
                    clone_path=str(wt.parent),
                    worktree_path=str(wt),
                    branch="feat/x",
                )
            ],
            "session_id": "s1",
        }
        render_claude_md(concept_context=first, **common_kwargs)
        assert "[[alpha]]" in _read_claude_md(wt)

        second = [
            ConceptContextEntry(
                id="beta",
                node_path=Path("/proj/nodes/beta.yaml"),
                exists=True,
            ),
        ]
        render_claude_md(concept_context=second, **common_kwargs)
        body = _read_claude_md(wt)
        assert "[[beta]]" in body
        assert "[[alpha]]" not in body

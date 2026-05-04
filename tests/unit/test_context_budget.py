"""Context budget tests — ensure tripwire-sourced content stays within bounds.

The PM skill is the single largest source of agent context. These tests
measure the total size of everything tripwire ships into a project and fail
if it exceeds a budget. This prevents accidental context bloat.

Budget rationale: the PM agent in v0.2 consumed ~160k tokens after
`tripwire init`, leaving ~40k for actual work in a 200k window. Planning
docs are user content (out of our control), but tripwire-sourced context
is ours to manage.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.templates import get_templates_dir

TEMPLATES_DIR = get_templates_dir()


def _total_chars(directory: Path) -> int:
    """Sum of all text file sizes under a directory."""
    total = 0
    for f in directory.rglob("*"):
        if f.is_file() and f.suffix in (".md", ".yaml", ".j2", ".py"):
            total += len(f.read_text(encoding="utf-8"))
    return total


def _total_lines(directory: Path) -> int:
    """Sum of all text file lines under a directory."""
    total = 0
    for f in directory.rglob("*"):
        if f.is_file() and f.suffix in (".md", ".yaml", ".j2", ".py"):
            total += len(f.read_text(encoding="utf-8").splitlines())
    return total


# ============================================================================
# PM skill budget
# ============================================================================


def test_pm_skill_total_size_under_budget() -> None:
    """The PM skill (SKILL.md + references + examples) must stay under 153KB.

    v0.2 was ~106KB. v0.6a added BRANCH_NAMING.md + priority hierarchy
    + handoff.yaml schema + v0.6a error codes + lint section.
    v0.7.5 adds the "Review feedback cycle" section to
    WORKFLOWS_REVIEW.md. Budget bumped to 148KB to accommodate; revisit
    when v0.7.5 PR2 lands "Pattern detection across PRs".
    v0.8x bumps to 153KB for the new SCHEMA_INBOX.md reference doc + the
    "Inbox — escalating to the human" section in SKILL.md (PM-as-curator
    of the dashboard's left-column attention queue).
    v0.9.6 (workflow codification stage 1) bumps to 160KB for the new
    MONITOR_CRITERIA.md reference doc — codifies the pm-monitor signal
    vocabulary the PM agent uses to drive the overseer loop.
    """
    pm_dir = TEMPLATES_DIR / "skills" / "project-manager"
    total = _total_chars(pm_dir)
    assert total < 160_000, (
        f"PM skill is {total:,} chars ({total / 1024:.0f} KB). "
        f"Budget is 160KB. Consolidate or trim reference docs."
    )


def test_pm_skill_md_under_budget() -> None:
    """SKILL.md itself should stay under 20KB.

    It's the one file agents reliably read. Keep it focused.
    """
    skill_md = TEMPLATES_DIR / "skills" / "project-manager" / "SKILL.md"
    size = len(skill_md.read_text(encoding="utf-8"))
    assert size < 20_000, (
        f"SKILL.md is {size:,} chars ({size / 1024:.0f} KB). "
        f"Budget is 20KB. Move detail to reference docs."
    )


# ============================================================================
# Total init budget
# ============================================================================


def test_total_templates_under_budget() -> None:
    """Everything `tripwire init` copies must stay under the total budget.

    v0.2 was ~217KB. v0.6a bumped to 275KB. v0.7b bumped to 285KB for
    spawn/defaults.yaml + issue_artifacts + /pm-issue-artifact. v0.7.2
    bumped to 295KB for pm-session-review expansion + spawn defaults
    resume_prompt_template / disallowed_tools additions. v0.7.8 bumped
    to 305KB for the auto-README template + CD workflow template.
    v0.7.9 bumped to 310KB for the spawn-template rewrite (per-worktree
    exit sequence + ruff gate + transition step) plus the runtime
    monitor invocation fields. v0.7.10 §D (KUI-95) bumps to 325KB for
    the codex-review workflow + codex-reviewer agent + protocol doc.
    v0.8x bumps to 332KB for the inbox primitive (SCHEMA_INBOX.md
    reference doc + the SKILL.md inbox-authoring section). v0.9.6 first
    bumped to 335KB for workflow.yaml source-of-truth gates and prompt-check
    invocation instructions, then to 345KB when the default process map
    started declaring PM workflows, routes, commands, skills, and emitted
    artifacts as first-class workflow.yaml data.
    """
    total = _total_chars(TEMPLATES_DIR)
    assert total < 345_000, (
        f"Total templates are {total:,} chars ({total / 1024:.0f} KB). Budget is 345KB."
    )


# ============================================================================
# Individual skill budgets
# ============================================================================


def test_each_non_pm_skill_under_budget() -> None:
    """Non-PM skills should each stay under 30KB."""
    skills_dir = TEMPLATES_DIR / "skills"
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name == "project-manager":
            continue
        total = _total_chars(skill_dir)
        assert total < 30_000, (
            f"Skill '{skill_dir.name}' is {total:,} chars ({total / 1024:.0f} KB). "
            f"Budget is 30KB."
        )

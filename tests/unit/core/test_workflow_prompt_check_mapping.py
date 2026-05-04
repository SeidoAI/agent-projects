"""Prompt-check implementation catalog for workflow.yaml references."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def test_collect_prompt_checks_returns_packaged_commands(tmp_path: Path) -> None:
    from tripwire.core.workflow.prompt_checks import collect_prompt_checks

    ids = {pc.id for pc in collect_prompt_checks(tmp_path)}
    assert "pm-session-queue" in ids
    assert "pm-session-review" in ids
    assert "pm-validate" in ids


def test_known_prompt_check_ids_returns_packaged_set(tmp_path: Path) -> None:
    from tripwire.core.workflow.registry import known_prompt_check_ids

    ids = known_prompt_check_ids(tmp_path)
    assert "pm-session-queue" in ids
    assert "pm-session-review" in ids


def test_project_local_override_wins_over_packaged(tmp_path: Path) -> None:
    from tripwire.core.workflow.prompt_checks import collect_prompt_checks

    overrides = tmp_path / ".tripwire" / "commands"
    overrides.mkdir(parents=True)
    (overrides / "pm-session-spawn.md").write_text(
        dedent(
            """\
            ---
            name: pm-session-spawn
            description: project-local override
            ---

            override body
            """
        ),
        encoding="utf-8",
    )

    pcs = {pc.id: pc for pc in collect_prompt_checks(tmp_path)}
    assert pcs["pm-session-spawn"].description == "project-local override"
    assert pcs["pm-session-spawn"].source == overrides / "pm-session-spawn.md"


def test_workflow_well_formed_resolves_prompt_check_refs(tmp_path: Path) -> None:
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    next: s2
                    prompt_checks: [pm-session-queue, does-not-exist]
                  - id: s2
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    from tripwire.core.validator import load_context
    from tripwire.core.validator.checks.workflow import check_workflow_well_formed

    ctx = load_context(tmp_path)
    findings = check_workflow_well_formed(ctx)
    codes = [f.code for f in findings]
    assert "workflow/unknown_prompt_check" in codes
    msgs = [f.message for f in findings if f.code == "workflow/unknown_prompt_check"]
    assert any("does-not-exist" in m for m in msgs)
    assert not any("pm-session-queue" in m for m in msgs)


def test_no_prompt_check_fires_at_frontmatter_remains() -> None:
    root = Path("src/tripwire/templates/commands")
    offenders = [
        str(path)
        for path in root.glob("*.md")
        if "fires_at:" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []

"""JIT prompt implementation catalog for workflow.yaml references."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def _write_project(project_dir: Path) -> None:
    (project_dir / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )


def test_known_jit_prompt_ids_come_from_manifest(tmp_path: Path) -> None:
    from tripwire.core.workflow.registry import known_jit_prompt_ids

    _write_project(tmp_path)
    ids = known_jit_prompt_ids(tmp_path)
    assert "self-review" in ids
    assert "write-count" in ids


def test_jit_prompt_status_refs_come_from_workflow_yaml(tmp_path: Path) -> None:
    from tripwire.core.workflow.registry import jit_prompt_status_refs

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: completed
                    terminal: true
                    jit_prompts: [self-review]
            """
        ),
        encoding="utf-8",
    )

    assert jit_prompt_status_refs(tmp_path, "self-review") == [
        ("coding-session", "completed")
    ]


def test_unreferenced_event_prompts_do_not_fire(tmp_path: Path) -> None:
    from tripwire._internal.jit_prompts import fire_jit_prompt_event

    _write_project(tmp_path)
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: completed
                    terminal: true
            """
        ),
        encoding="utf-8",
    )

    result = fire_jit_prompt_event(
        project_dir=tmp_path,
        event="session.complete",
        session_id="fixture",
    )
    assert result.blocked is False
    assert result.prompts == []


def test_no_jit_prompt_at_metadata_remains() -> None:
    root = Path("src/tripwire/_internal/jit_prompts")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if " at =" in text or "\nat:" in text:
            offenders.append(str(path))
    assert offenders == []

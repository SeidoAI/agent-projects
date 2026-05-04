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
                  - id: executing
                    next: completed
                  - id: completed
                    terminal: true
                routes:
                  - id: executing-to-completed
                    actor: pm-agent
                    from: executing
                    to: completed
                    controls:
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


def test_default_workflow_declares_all_builtin_jit_prompts() -> None:
    """Every implemented JIT prompt class must be referenced in
    ``workflow.yaml.j2``. Some are referenced under ``tripwires:`` rather
    than ``jit_prompts:`` — the four-primitive split classifies an impl
    by the kind of *control* it represents (hard pass/fail vs hidden +
    ack), not by the Python directory it ships in. ``cost-ceiling`` is
    the canonical example: lives under ``_internal/jit_prompts/`` for
    historical reasons but is referenced as a tripwire because it's a
    hard cap. Until the stage-2 module rename relocates it, the test
    accepts a reference under any control slot.
    """

    import yaml

    from tripwire.core.workflow.registry import known_jit_prompt_ids

    template = Path("src/tripwire/templates/workflow.yaml.j2").read_text(
        encoding="utf-8"
    )
    parsed = yaml.safe_load(template)
    declared = set()
    for workflow in parsed["workflows"].values():
        for status in workflow["statuses"]:
            for slot in ("jit_prompts", "tripwires", "heuristics", "prompt_checks"):
                declared.update(status.get(slot, []))
        for route in workflow.get("routes", []):
            controls = route.get("controls") or {}
            for slot in ("jit_prompts", "tripwires", "heuristics", "prompt_checks"):
                declared.update(controls.get(slot, []))
    assert known_jit_prompt_ids() - declared == set()

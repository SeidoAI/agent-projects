"""Unit tests for ``tripwire.core.workflow.schema`` and ``loader``.

Covers KUI-119: parsing the per-project ``workflow.yaml`` into a typed
dataclass tree and well-formedness validation. The loader is read-only:
it returns a typed model and never mutates state.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

# ----------------------------------------------------------------------
# Schema: parsing happy paths
# ----------------------------------------------------------------------


def test_loader_parses_minimal_workflow(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: queued
                    next: spawned
                  - id: spawned
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    assert "coding-session" in spec.workflows
    wf = spec.workflows["coding-session"]
    assert wf.actor == "coding-agent"
    assert wf.trigger == "session.spawn"
    assert [s.id for s in wf.statuses] == ["queued", "spawned"]
    assert wf.statuses[0].next.kind == "single"
    assert wf.statuses[0].next.single == "spawned"
    assert wf.statuses[1].next.kind == "terminal"


def test_loader_parses_conditional_next(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: executing
                    next:
                      - if: agent.role == frontend
                        then: review-frontend
                      - else: review-backend
                  - id: review-frontend
                    terminal: true
                  - id: review-backend
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    nxt = spec.workflows["coding-session"].statuses[0].next
    assert nxt.kind == "conditional"
    assert nxt.conditional is not None
    assert len(nxt.conditional) == 2
    first, last = nxt.conditional
    assert first.predicate is not None
    assert first.predicate.field == "agent.role"
    assert first.predicate.op == "=="
    assert first.predicate.value == "frontend"
    assert first.then == "review-frontend"
    assert last.predicate is None  # else branch
    assert last.then == "review-backend"


def test_loader_parses_inequality_predicate(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    next:
                      - if: agent.role != frontend
                        then: s2
                      - else: s3
                  - id: s2
                    terminal: true
                  - id: s3
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    nxt = load_workflows(tmp_path).workflows["w"].statuses[0].next
    assert nxt.conditional is not None
    assert nxt.conditional[0].predicate is not None
    assert nxt.conditional[0].predicate.op == "!="


def test_loader_parses_prompt_checks_validators_jit_prompts(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

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
                    prompt_checks: [pm-session-launch]
                    validators: [schema-valid, refs-resolved]
                    jit_prompts: [cost-ceiling]
                  - id: s2
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    s1 = load_workflows(tmp_path).workflows["w"].statuses[0]
    assert s1.prompt_checks == ["pm-session-launch"]
    assert s1.validators == ["schema-valid", "refs-resolved"]
    assert s1.jit_prompts == ["cost-ceiling"]


def test_loader_parses_status_artifacts(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    terminal: true
                    artifacts:
                      consumes:
                        - id: issue-brief
                          label: issue brief
                      produces:
                        - id: plan
                          label: plan.md
                          path: sessions/{session_id}/plan.md
            """
        ),
        encoding="utf-8",
    )
    status = load_workflows(tmp_path).workflows["w"].statuses[0]
    assert [a.id for a in status.artifacts.consumes] == ["issue-brief"]
    assert status.artifacts.produces[0].id == "plan"
    assert status.artifacts.produces[0].label == "plan.md"
    assert status.artifacts.produces[0].path == "sessions/{session_id}/plan.md"


def test_loader_parses_explicit_routes(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: executing
                  - id: executing
                    terminal: true
                routes:
                  - id: planned-to-executing
                    actor: pm-agent
                    command: pm-session-spawn
                    trigger: command.pm-session-spawn
                    from: planned
                    to: executing
                    label: spawn
                    controls:
                      validators: [v_uuid_present]
                      jit_prompts: [self-review]
                      prompt_checks: [pm-session-spawn]
                    skills: [project-manager, backend-development]
                    emits:
                      artifacts:
                        - id: plan
                          label: plan.md
                          path: sessions/{session_id}/plan.md
                      events: [session.spawn]
                      comments: [spawned]
                      status_changes: [executing]
            """
        ),
        encoding="utf-8",
    )

    route = load_workflows(tmp_path).workflows["coding-session"].routes[0]

    assert route.id == "planned-to-executing"
    assert route.actor == "pm-agent"
    assert route.command == "pm-session-spawn"
    assert route.trigger == "command.pm-session-spawn"
    assert route.from_ref == "planned"
    assert route.to_ref == "executing"
    assert route.kind == "forward"
    assert route.controls.validators == ["v_uuid_present"]
    assert route.controls.jit_prompts == ["self-review"]
    assert route.controls.prompt_checks == ["pm-session-spawn"]
    assert route.skills == ["project-manager", "backend-development"]
    assert [artifact.id for artifact in route.emits.artifacts] == ["plan"]
    assert route.emits.events == ["session.spawn"]
    assert route.emits.comments == ["spawned"]
    assert route.emits.status_changes == ["executing"]


def test_loader_reports_stale_stations_key(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                stations:
                  - id: s1
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    assert spec.workflows["w"].statuses == []
    findings = validate_workflow_spec(
        spec,
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    assert [finding.code for finding in findings] == ["workflow/stale_stations_key"]
    assert "stale `stations:`" in findings[0].message


def test_loader_supports_multiple_workflows(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              a:
                actor: a
                trigger: t
                statuses:
                  - id: s
                    terminal: true
              b:
                actor: a
                trigger: t
                statuses:
                  - id: s
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    assert set(spec.workflows.keys()) == {"a", "b"}


def test_loader_returns_empty_when_file_missing(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    spec = load_workflows(tmp_path)
    assert spec.workflows == {}


def test_loader_does_not_mutate_state(tmp_path: Path) -> None:
    """Loading must not write any files."""
    from tripwire.core.workflow.loader import load_workflows

    yml = tmp_path / "workflow.yaml"
    yml.write_text(
        "workflows:\n  w:\n    actor: a\n    trigger: t\n    statuses:\n"
        "      - id: s\n        terminal: true\n",
        encoding="utf-8",
    )
    contents_before = yml.read_text(encoding="utf-8")
    files_before = sorted(p.name for p in tmp_path.iterdir())
    load_workflows(tmp_path)
    assert yml.read_text(encoding="utf-8") == contents_before
    assert sorted(p.name for p in tmp_path.iterdir()) == files_before


# ----------------------------------------------------------------------
# Well-formedness validator
# ----------------------------------------------------------------------


def test_validator_rejects_unreferenced_station_in_next(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    next: nonexistent
                  - id: s2
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    findings = validate_workflow_spec(
        spec,
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_next_status" in codes


def test_validator_rejects_undeclared_validator_ref(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    validators: [does-not-exist]
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators={"schema-valid"},
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_validator" in codes


def test_validator_rejects_undeclared_tripwire_ref(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    jit_prompts: [unknown-tw]
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts={"self-review"},
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_jit_prompt" in codes


def test_validator_rejects_undeclared_prompt_check_ref(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    prompt_checks: [unknown-prompt-check]
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks={"pm-session-launch"},
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_prompt_check" in codes


def test_validator_rejects_bad_route_refs(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: planned
                    next: completed
                  - id: completed
                    terminal: true
                routes:
                  - id: bad-route
                    actor: outsider
                    command: pm-missing
                    from: planned
                    to: missing
                    controls:
                      validators: [v_missing]
                      jit_prompts: [missing-prompt]
                      prompt_checks: [pm-missing-check]
                    skills: [missing-skill]
                  - id: bad-route
                    actor: pm-agent
                    from: ""
                    to: completed
            """
        ),
        encoding="utf-8",
    )

    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators={"v_uuid_present"},
        known_jit_prompts={"self-review"},
        known_prompt_checks={"pm-session-spawn"},
        known_commands={"pm-session-spawn"},
        known_skills={"project-manager"},
    )

    codes = [f.code for f in findings]
    assert "workflow/duplicate_route_id" in codes
    assert "workflow/unknown_actor" in codes
    assert "workflow/missing_route_endpoint" in codes
    assert "workflow/unknown_route_status" in codes
    assert "workflow/unknown_command" in codes
    assert "workflow/unknown_skill" in codes
    assert "workflow/unknown_validator" in codes
    assert "workflow/unknown_jit_prompt" in codes
    assert "workflow/unknown_prompt_check" in codes


def test_validator_rejects_terminal_with_next(tmp_path: Path) -> None:
    """A status can be terminal OR declare next, never both — cyclic
    terminal misuse means a status marked terminal that nonetheless
    chains forward."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

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
                    terminal: true
                  - id: s2
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/terminal_with_next" in codes


def test_validator_rejects_duplicate_status_ids(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    terminal: true
                  - id: s1
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/duplicate_status_id" in codes


def test_validator_rejects_no_terminal_status(tmp_path: Path) -> None:
    """Every workflow must reach a terminal — no all-cyclic graphs."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

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
                  - id: s2
                    next: s1
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/no_terminal_status" in codes


def test_validator_clean_on_well_formed(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: queued
                    next: executing
                    prompt_checks: [pm-session-launch]
                  - id: executing
                    validators: [schema-valid]
                    jit_prompts: [cost-ceiling]
                    next:
                      - if: agent.role == frontend
                        then: review-frontend
                      - else: review-backend
                  - id: review-frontend
                    next: verified
                  - id: review-backend
                    next: verified
                  - id: verified
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators={"schema-valid"},
        known_jit_prompts={"cost-ceiling"},
        known_prompt_checks={"pm-session-launch"},
    )
    assert findings == []


# ----------------------------------------------------------------------
# Cross-links
# ----------------------------------------------------------------------


def test_loader_parses_cross_links(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              triage:
                actor: pm-agent
                trigger: t
                statuses:
                  - id: act
                    next: done
                    cross_links:
                      - workflow: coding-session
                        status: planned
                        label: spawn coding session
                  - id: done
                    terminal: true
              coding-session:
                actor: coding-agent
                trigger: t
                statuses:
                  - id: planned
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    act = spec.workflows["triage"].statuses_by_id["act"]
    assert len(act.cross_links) == 1
    link = act.cross_links[0]
    assert link.workflow == "coding-session"
    assert link.status == "planned"
    assert link.label == "spawn coding session"
    assert link.kind == "triggers"


def test_validator_warns_on_unknown_cross_link_workflow(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    terminal: true
                    cross_links:
                      - workflow: nonexistent-workflow
                        status: somewhere
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/cross_link_unknown_workflow" in codes


def test_validator_warns_on_unknown_cross_link_status(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              triage:
                actor: pm-agent
                trigger: t
                statuses:
                  - id: act
                    terminal: true
                    cross_links:
                      - workflow: coding-session
                        status: nonexistent-status
              coding-session:
                actor: coding-agent
                trigger: t
                statuses:
                  - id: planned
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/cross_link_unknown_status" in codes


# ----------------------------------------------------------------------
# Predicate parsing
# ----------------------------------------------------------------------


def test_predicate_parse_equality() -> None:
    from tripwire.core.workflow.schema import Predicate

    p = Predicate.parse("agent.role == frontend")
    assert p.field == "agent.role"
    assert p.op == "=="
    assert p.value == "frontend"


def test_predicate_parse_inequality() -> None:
    from tripwire.core.workflow.schema import Predicate

    p = Predicate.parse("session.kind != bugfix")
    assert p.field == "session.kind"
    assert p.op == "!="
    assert p.value == "bugfix"


def test_predicate_parse_rejects_unsupported_operator() -> None:
    from tripwire.core.workflow.schema import Predicate

    with pytest.raises(ValueError):
        Predicate.parse("agent.role > frontend")


def test_predicate_parse_rejects_missing_operator() -> None:
    from tripwire.core.workflow.schema import Predicate

    with pytest.raises(ValueError):
        Predicate.parse("agent.role frontend")


# ----------------------------------------------------------------------
# Predicate evaluation
# ----------------------------------------------------------------------


def test_predicate_eval_equality_dot_path() -> None:
    from tripwire.core.workflow.schema import Predicate

    p = Predicate.parse("agent.role == frontend")
    assert p.evaluate({"agent": {"role": "frontend"}}) is True
    assert p.evaluate({"agent": {"role": "backend"}}) is False
    assert p.evaluate({}) is False  # missing field falsy


def test_predicate_eval_inequality_dot_path() -> None:
    from tripwire.core.workflow.schema import Predicate

    p = Predicate.parse("agent.role != frontend")
    assert p.evaluate({"agent": {"role": "frontend"}}) is False
    assert p.evaluate({"agent": {"role": "backend"}}) is True

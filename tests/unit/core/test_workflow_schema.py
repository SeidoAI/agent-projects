"""Unit tests for ``tripwire.core.workflow.schema`` and ``loader``.

Covers KUI-119 + the v0.13 schema convergence: parsing the per-project
``workflow.yaml`` into a typed dataclass tree and well-formedness
validation. The loader is read-only: it returns a typed model and
never mutates state.

Routes are the single source of structural arrows;
``statuses[].next:`` is not a recognized key and surfaces as
``workflow/unknown_key`` at load time.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

# ----------------------------------------------------------------------
# Schema: parsing happy paths
# ----------------------------------------------------------------------


def test_loader_parses_minimal_workflow(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: queued
                  - id: spawned
                    terminal: true
                routes:
                  - id: queued-to-spawned
                    actor: pm-agent
                    from: queued
                    to: spawned
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    assert spec.schema_version == 1
    assert "coding-session" in spec.workflows
    wf = spec.workflows["coding-session"]
    assert wf.actor == "coding-agent"
    assert wf.trigger == "session.spawn"
    assert [s.id for s in wf.statuses] == ["queued", "spawned"]
    assert wf.statuses[0].terminal is False
    assert wf.statuses[1].terminal is True


def test_loader_parses_prompt_checks_tripwires_jit_prompts(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    prompt_checks: [pm-session-launch]
                    tripwires: [schema-valid, refs-resolved]
                    heuristics: [quality-drift, mega-issue]
                    jit_prompts: [cost-ceiling]
                  - id: s2
                    terminal: true
                routes:
                  - id: s1-to-s2
                    actor: pm-agent
                    from: s1
                    to: s2
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    s1 = load_workflows(tmp_path).workflows["w"].statuses[0]
    assert s1.prompt_checks == ["pm-session-launch"]
    assert s1.tripwires == ["schema-valid", "refs-resolved"]
    assert s1.heuristics == ["quality-drift", "mega-issue"]
    assert s1.jit_prompts == ["cost-ceiling"]


def test_loader_parses_route_signals_and_heuristics(tmp_path: Path) -> None:
    """Routes carry pm-monitor signal vocabulary + heuristic controls."""

    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              pm-monitor:
                actor: pm-agent
                trigger: command.pm-monitor
                statuses:
                  - id: scan
                  - id: dispatch
                    terminal: true
                routes:
                  - id: dispatch-launch
                    actor: pm-agent
                    from: scan
                    to: dispatch
                    kind: forward
                    signals: [signal.session_unblocked, signal.inbox_inbound_new]
                    controls:
                      tripwires: [v_session_state_readable]
                      heuristics: [stale-node-count-high]
            """
        ),
        encoding="utf-8",
    )
    route = load_workflows(tmp_path).workflows["pm-monitor"].routes[0]
    assert route.signals == [
        "signal.session_unblocked",
        "signal.inbox_inbound_new",
    ]
    assert route.controls.tripwires == ["v_session_state_readable"]
    assert route.controls.heuristics == ["stale-node-count-high"]


def test_loader_parses_cross_link_pm_subagent_dispatch(tmp_path: Path) -> None:
    """Cross-links carry the pm_subagent_dispatch flag for pm-monitor."""

    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              pm-monitor:
                actor: pm-agent
                trigger: command.pm-monitor
                statuses:
                  - id: dispatch
                    terminal: true
                    cross_links:
                      - workflow: code-review
                        status: received
                        label: launch review
                        kind: triggers
                        pm_subagent_dispatch: true
                      - workflow: inbox-handling
                        status: pending
                        label: escalate to user
                        kind: triggers
            """
        ),
        encoding="utf-8",
    )
    links = load_workflows(tmp_path).workflows["pm-monitor"].statuses[0].cross_links
    assert links[0].pm_subagent_dispatch is True
    assert links[1].pm_subagent_dispatch is False


def test_loader_parses_status_artifacts(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
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
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
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
                      tripwires: [v_uuid_present]
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
    assert route.controls.tripwires == ["v_uuid_present"]
    assert route.controls.jit_prompts == ["self-review"]
    assert route.controls.prompt_checks == ["pm-session-spawn"]
    assert route.skills == ["project-manager", "backend-development"]
    assert [artifact.id for artifact in route.emits.artifacts] == ["plan"]
    assert route.emits.events == ["session.spawn"]
    assert route.emits.comments == ["spawned"]
    assert route.emits.status_changes == ["executing"]


def test_loader_parses_v013_route_fields(tmp_path: Path) -> None:
    """v0.13: routes declare preserve_fields, clear_fields,
    side_effects, rollback, and typed triggers."""
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: completed
                  - id: paused
                    terminal: true
                routes:
                  - id: completed-to-paused-reopen
                    actor: pm-agent
                    from: completed
                    to: paused
                    kind: revert
                    trigger:
                      type: command
                      name: tripwire-session-reopen
                    preserve_fields:
                      - runtime_state.claude_session_id
                      - runtime_state.worktrees
                    clear_fields: []
                    side_effects:
                      - flip_drafts_to_draft
                      - append_audit_log_entry
                    rollback: atomic
            """
        ),
        encoding="utf-8",
    )

    route = load_workflows(tmp_path).workflows["coding-session"].routes[0]
    assert route.kind == "revert"
    assert route.preserve_fields == [
        "runtime_state.claude_session_id",
        "runtime_state.worktrees",
    ]
    assert route.clear_fields == []
    assert route.side_effects == ["flip_drafts_to_draft", "append_audit_log_entry"]
    assert route.rollback == "atomic"
    assert route.trigger_typed is not None
    assert route.trigger_typed.type == "command"
    assert route.trigger_typed.name == "tripwire-session-reopen"


def test_loader_emits_no_statuses_declared_when_block_missing(tmp_path: Path) -> None:
    """Hard-migration policy: a workflow with no `statuses:` block fails
    loudly with a generic error. Stale shapes (e.g. an old `stations:`
    block from before the rename) hit the same code path — the loader
    never knew the old key name.
    """
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
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
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [finding.code for finding in findings]
    assert "workflow/no_statuses_declared" in codes
    assert "workflow/stale_stations_key" not in codes
    finding = next(f for f in findings if f.code == "workflow/no_statuses_declared")
    assert finding.severity == "error"
    assert "no `statuses:`" in finding.message


def test_loader_emits_unknown_key_for_each_offending_field(tmp_path: Path) -> None:
    """Hard-migration policy: any key not in the recognized set at any
    level fires a `workflow/unknown_key` finding. The check is
    name-blind — it surfaces stale shapes (e.g. a stale `validators:`
    list on a status) and plain typos with the same mechanism.
    """
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                actorr: typo
                statuses:
                  - id: s
                    terminal: true
                    validators: [v_uuid_present]
                routes:
                  - id: r1
                    from: s
                    to: s
                    kind: side
                    controls:
                      validators: [v_uuid_present]
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    findings = spec.load_findings
    codes = [f.code for f in findings]
    assert codes.count("workflow/unknown_key") == 3, [f.message for f in findings]
    messages = [f.message for f in findings if f.code == "workflow/unknown_key"]
    assert any("'actorr'" in m and "workflow 'w'" in m for m in messages)
    assert any("'validators'" in m and "status 's'" in m for m in messages)
    assert any("'validators'" in m and "route 'r1' `controls:`" in m for m in messages)


def test_loader_supports_multiple_workflows(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
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
        "workflow_schema_version: 1\nworkflows:\n  w:\n    actor: a\n    trigger: t\n"
        "    statuses:\n      - id: s\n        terminal: true\n",
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


def test_validator_rejects_unknown_route_status(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                  - id: s2
                    terminal: true
                routes:
                  - id: r-bad
                    actor: pm-agent
                    from: s1
                    to: nonexistent
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    spec = load_workflows(tmp_path)
    findings = validate_workflow_spec(
        spec,
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_route_status" in codes


def test_validator_rejects_undeclared_validator_ref(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    tripwires: [does-not-exist]
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires={"schema-valid"},
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_tripwire" in codes


def test_validator_rejects_undeclared_tripwire_ref(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
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
        known_tripwires=set(),
        known_heuristics=set(),
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
            workflow_schema_version: 1
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
        known_tripwires=set(),
        known_heuristics=set(),
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
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: planned
                  - id: completed
                    terminal: true
                routes:
                  - id: bad-route
                    actor: outsider
                    command: pm-missing
                    from: planned
                    to: missing
                    controls:
                      tripwires: [v_missing]
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
        known_tripwires={"v_uuid_present"},
        known_heuristics=set(),
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
    assert "workflow/unknown_tripwire" in codes
    assert "workflow/unknown_jit_prompt" in codes
    assert "workflow/unknown_prompt_check" in codes


def test_validator_emits_unknown_key_for_legacy_next(  # legacy-allow: name fixed by plan
    tmp_path: Path,
) -> None:
    """``statuses[].next:`` is not a recognized key. Any file declaring
    it surfaces the generic ``workflow/unknown_key`` finding (the same
    finding any other typo would produce)."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                    next: s2
                  - id: s2
                    terminal: true
                routes:
                  - id: s1-to-s2
                    actor: pm-agent
                    from: s1
                    to: s2
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_key" in codes
    unknown = next(
        f
        for f in findings
        if f.code == "workflow/unknown_key" and "'next'" in f.message
    )
    assert unknown.status == "s1"


def test_validator_rejects_duplicate_status_ids(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
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
        known_tripwires=set(),
        known_heuristics=set(),
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
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                  - id: s2
                routes:
                  - id: s1-to-s2
                    actor: pm-agent
                    from: s1
                    to: s2
                    kind: forward
                  - id: s2-to-s1
                    actor: pm-agent
                    from: s2
                    to: s1
                    kind: return
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
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
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: queued
                    prompt_checks: [pm-session-launch]
                  - id: executing
                    tripwires: [schema-valid]
                    jit_prompts: [cost-ceiling]
                  - id: verified
                    terminal: true
                routes:
                  - id: queued-to-executing
                    actor: pm-agent
                    from: queued
                    to: executing
                    kind: forward
                  - id: executing-to-verified
                    actor: pm-agent
                    from: executing
                    to: verified
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires={"schema-valid"},
        known_heuristics=set(),
        known_jit_prompts={"cost-ceiling"},
        known_prompt_checks={"pm-session-launch"},
    )
    assert findings == []


# ----------------------------------------------------------------------
# v0.13 lints — schema_version, reachability, traps, recovery, reverts
# ----------------------------------------------------------------------


def test_validator_emits_missing_schema_version(tmp_path: Path) -> None:
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
                  - id: s
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/missing_schema_version" in codes


def test_validator_emits_missing_schema_version_for_wrong_version(
    tmp_path: Path,
) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 2
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/missing_schema_version" in codes


def test_validator_rejects_unreachable_status(tmp_path: Path) -> None:
    """A non-initial status with no inbound route is unreachable."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                  - id: s2
                    terminal: true
                  - id: orphan
                    terminal: true
                routes:
                  - id: s1-to-s2
                    actor: pm-agent
                    from: s1
                    to: s2
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unreachable_status" in codes
    finding = next(f for f in findings if f.code == "workflow/unreachable_status")
    assert finding.status == "orphan"


def test_validator_rejects_trap_status(tmp_path: Path) -> None:
    """A non-terminal status with no outbound route is a dead end."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: s1
                  - id: trap
                  - id: done
                    terminal: true
                routes:
                  - id: s1-to-trap
                    actor: pm-agent
                    from: s1
                    to: trap
                    kind: forward
                  - id: s1-to-done
                    actor: pm-agent
                    from: s1
                    to: done
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/trap_status" in codes
    finding = next(f for f in findings if f.code == "workflow/trap_status")
    assert finding.status == "trap"


def test_validator_rejects_no_recovery_path(tmp_path: Path) -> None:
    """An off-path status (paused, failed) must have a route back to an
    on-path status; if the only outbound is to abandoned that's a dead
    end matching PM handoff #5 Gap C."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: queued
                  - id: executing
                  - id: completed
                    terminal: true
                  - id: paused
                  - id: abandoned
                    terminal: true
                routes:
                  - id: q-to-e
                    actor: pm-agent
                    from: queued
                    to: executing
                    kind: forward
                  - id: e-to-c
                    actor: pm-agent
                    from: executing
                    to: completed
                    kind: forward
                  - id: e-to-p
                    actor: pm-agent
                    from: executing
                    to: paused
                    kind: side
                  - id: p-to-a
                    actor: pm-agent
                    from: paused
                    to: abandoned
                    kind: side
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/no_recovery_path" in codes


def test_validator_warns_on_lossy_revert(tmp_path: Path) -> None:
    """A revert kind route with no preserve_fields throws away runtime
    state on rollback — emit a warning."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: completed
                    terminal: true
                  - id: paused
                    terminal: true
                routes:
                  - id: completed-to-paused
                    actor: pm-agent
                    from: completed
                    to: paused
                    kind: revert
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    lossy = [f for f in findings if f.code == "workflow/lossy_revert"]
    assert len(lossy) == 1
    assert lossy[0].severity == "warning"


def test_validator_rejects_unknown_side_effect(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: a
                  - id: b
                    terminal: true
                routes:
                  - id: r
                    actor: pm-agent
                    from: a
                    to: b
                    kind: forward
                    side_effects: [does_not_exist]
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
        known_side_effects={"flip_drafts_to_draft"},
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_side_effect" in codes


def test_validator_lints_unknown_side_effect_no_op_when_registry_absent(
    tmp_path: Path,
) -> None:
    """Until WS2 plumbs the registry, an unknown side-effect id is
    ignored — passing ``known_side_effects=None`` (default) skips the
    check entirely."""
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: a
                  - id: b
                    terminal: true
                routes:
                  - id: r
                    actor: pm-agent
                    from: a
                    to: b
                    kind: forward
                    side_effects: [does_not_exist]
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_side_effect" not in codes


def test_validator_rejects_unknown_status_field_path(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows
    from tripwire.core.workflow.schema import validate_workflow_spec

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: a
                  - id: b
                    terminal: true
                routes:
                  - id: r
                    actor: pm-agent
                    from: a
                    to: b
                    kind: forward
                    preserve_fields: [runtime_state.claude_session_id, bogus_top_level]
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
        known_status_field_paths={"runtime_state", "status", "engagements"},
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_status_field" in codes


# ----------------------------------------------------------------------
# Cross-links
# ----------------------------------------------------------------------


def test_loader_parses_cross_links(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              triage:
                actor: pm-agent
                trigger: t
                statuses:
                  - id: act
                    cross_links:
                      - workflow: coding-session
                        status: planned
                        label: spawn coding session
                  - id: done
                    terminal: true
                routes:
                  - id: act-to-done
                    actor: pm-agent
                    from: act
                    to: done
                    kind: forward
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
            workflow_schema_version: 1
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
        known_tripwires=set(),
        known_heuristics=set(),
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
            workflow_schema_version: 1
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
        known_tripwires=set(),
        known_heuristics=set(),
        known_jit_prompts=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/cross_link_unknown_status" in codes

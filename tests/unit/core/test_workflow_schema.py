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
                stations:
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
    assert [s.id for s in wf.stations] == ["queued", "spawned"]
    assert wf.stations[0].next.kind == "single"
    assert wf.stations[0].next.single == "spawned"
    assert wf.stations[1].next.kind == "terminal"


def test_loader_parses_conditional_next(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                stations:
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
    nxt = spec.workflows["coding-session"].stations[0].next
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
                stations:
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
    nxt = load_workflows(tmp_path).workflows["w"].stations[0].next
    assert nxt.conditional is not None
    assert nxt.conditional[0].predicate is not None
    assert nxt.conditional[0].predicate.op == "!="


def test_loader_parses_prompt_checks_validators_tripwires(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              w:
                actor: a
                trigger: t
                stations:
                  - id: s1
                    next: s2
                    prompt_checks: [pm-session-launch]
                    validators: [schema-valid, refs-resolved]
                    tripwires: [cost-ceiling]
                  - id: s2
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    s1 = load_workflows(tmp_path).workflows["w"].stations[0]
    assert s1.prompt_checks == ["pm-session-launch"]
    assert s1.validators == ["schema-valid", "refs-resolved"]
    assert s1.tripwires == ["cost-ceiling"]


def test_loader_supports_multiple_workflows(tmp_path: Path) -> None:
    from tripwire.core.workflow.loader import load_workflows

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              a:
                actor: a
                trigger: t
                stations:
                  - id: s
                    terminal: true
              b:
                actor: a
                trigger: t
                stations:
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
        "workflows:\n  w:\n    actor: a\n    trigger: t\n    stations:\n"
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
                stations:
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
        known_tripwires=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_next_station" in codes


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
                stations:
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
        known_tripwires=set(),
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
                stations:
                  - id: s1
                    tripwires: [unknown-tw]
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_tripwires={"self-review"},
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_tripwire" in codes


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
                stations:
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
        known_tripwires=set(),
        known_prompt_checks={"pm-session-launch"},
    )
    codes = [f.code for f in findings]
    assert "workflow/unknown_prompt_check" in codes


def test_validator_rejects_terminal_with_next(tmp_path: Path) -> None:
    """A station can be terminal OR declare next, never both — cyclic
    terminal misuse means a station marked terminal that nonetheless
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
                stations:
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
        known_tripwires=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/terminal_with_next" in codes


def test_validator_rejects_duplicate_station_ids(tmp_path: Path) -> None:
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
                  - id: s1
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    findings = validate_workflow_spec(
        load_workflows(tmp_path),
        known_validators=set(),
        known_tripwires=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/duplicate_station_id" in codes


def test_validator_rejects_no_terminal_station(tmp_path: Path) -> None:
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
                stations:
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
        known_tripwires=set(),
        known_prompt_checks=set(),
    )
    codes = [f.code for f in findings]
    assert "workflow/no_terminal_station" in codes


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
                stations:
                  - id: queued
                    next: executing
                    prompt_checks: [pm-session-launch]
                  - id: executing
                    validators: [schema-valid]
                    tripwires: [cost-ceiling]
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
        known_tripwires={"cost-ceiling"},
        known_prompt_checks={"pm-session-launch"},
    )
    assert findings == []


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

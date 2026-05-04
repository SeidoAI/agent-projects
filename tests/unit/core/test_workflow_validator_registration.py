"""Validator implementation catalog for workflow.yaml references."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def test_every_check_has_unique_workflow_catalog_id() -> None:
    from tripwire.core.validator import ALL_CHECKS
    from tripwire.core.workflow.registry import validator_id_for

    ids = [validator_id_for(fn) for fn in ALL_CHECKS]
    assert len(ids) == len(set(ids))
    assert "v_uuid_present" in ids
    assert "v_stale_concept" in ids
    assert "v_check" not in ids


def test_declared_validator_ids_come_from_workflow_yaml(tmp_path: Path) -> None:
    from tripwire.core.workflow.registry import declared_validator_ids

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
                    validators: [v_uuid_present]
                  - id: executing
                    terminal: true
                    validators: [v_reference_integrity, v_uuid_present]
            """
        ),
        encoding="utf-8",
    )

    assert declared_validator_ids(tmp_path) == [
        "v_workflow_well_formed",
        "v_uuid_present",
        "v_reference_integrity",
    ]


def test_no_validator_placement_decorators_remain() -> None:
    root = Path("src/tripwire")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "registers_at(" in text or "__tripwire_workflow_status__" in text:
            offenders.append(str(path))
    assert offenders == []


def test_all_declared_validators_resolve_to_implementations(tmp_path: Path) -> None:
    from tripwire.core.workflow.registry import (
        declared_validator_ids,
        validator_checks_for_ids,
        validator_id_for,
    )

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
                    validators: [v_uuid_present, v_enum_values]
            """
        ),
        encoding="utf-8",
    )

    ids = declared_validator_ids(tmp_path)
    checks = validator_checks_for_ids(ids)
    resolved = {validator_id_for(check) for check in checks}
    assert {"v_workflow_well_formed", "v_uuid_present", "v_enum_values"} <= resolved


def test_validate_project_runs_only_workflow_declared_validators(
    tmp_path: Path, monkeypatch
) -> None:
    from tripwire.core import validator
    from tripwire.core.validator._types import CheckResult

    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
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
                    validators: [v_selected]
            """
        ),
        encoding="utf-8",
    )

    def check_selected(ctx):
        return [
            CheckResult(
                code="selected/fired",
                severity="warning",
                file=None,
                message="selected fired",
            )
        ]

    def check_omitted(ctx):
        return [
            CheckResult(
                code="omitted/fired",
                severity="warning",
                file=None,
                message="omitted fired",
            )
        ]

    monkeypatch.setattr(validator, "ALL_CHECKS", [check_selected, check_omitted])

    report = validator.validate_project(tmp_path)
    codes = [finding.code for finding in report.warnings]
    assert "selected/fired" in codes
    assert "omitted/fired" not in codes

"""Unit tests for ``check_instance_shape_conforms`` (v0.13.1).

The check enforces per-workflow instance-shape contracts declared via
the ``instance:`` block in ``workflow.yaml``. For each materialised
instance found via :func:`list_instances`, it asserts:

- every entry in ``required_fields`` is present
  (missing → ``instance/missing_required_field``);
- the ``status_field`` value is in ``status_enum``
  (out-of-enum → ``instance/invalid_status_value``).

Workflows without an ``instance:`` block are skipped silently — the
missing-block warning is owned by ``check_workflow_well_formed``.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.validator._types import ValidationContext
from tripwire.core.validator.checks.structure import check_instance_shape_conforms
from tripwire.core.workflow.instance_io import save_instance


def _write_demo_workflow(
    tmp_path: Path,
    *,
    storage_path: str = "instances/demos/{instance_id}/demo.yaml",
    status_enum: list[str] | None = None,
    required_fields: list[str] | None = None,
) -> None:
    """Drop a workflow.yaml declaring a single ``demo`` workflow."""
    if status_enum is None:
        status_enum = ["planned", "completed"]
    if required_fields is None:
        required_fields = ["id", "status"]
    parts = [
        "workflow_schema_version: 1",
        "workflows:",
        "  demo:",
        "    actor: pm-agent",
        "    trigger: demo.start",
        "    instance:",
        f"      storage_path: {storage_path}",
        "      status_field: status",
        f"      status_enum: [{', '.join(status_enum)}]",
        f"      required_fields: [{', '.join(required_fields)}]",
        "    statuses:",
        "      - id: planned",
        "      - id: completed",
        "        terminal: true",
        "    routes:",
        "      - id: planned-to-completed",
        "        actor: pm-agent",
        "        from: planned",
        "        to: completed",
        "        kind: forward",
    ]
    (tmp_path / "workflow.yaml").write_text("\n".join(parts) + "\n", encoding="utf-8")


def _ctx(tmp_path: Path) -> ValidationContext:
    return ValidationContext(project_dir=tmp_path)


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_happy_path_no_findings(tmp_path: Path) -> None:
    _write_demo_workflow(tmp_path)
    save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "planned"})
    save_instance(tmp_path, "demo", "d2", {"id": "d2", "status": "completed"})
    assert check_instance_shape_conforms(_ctx(tmp_path)) == []


# ---------------------------------------------------------------------------
# missing required field
# ---------------------------------------------------------------------------


def test_missing_required_field_fires(tmp_path: Path) -> None:
    _write_demo_workflow(tmp_path, required_fields=["id", "status", "title"])
    # title is required but not present.
    save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "planned"})
    results = check_instance_shape_conforms(_ctx(tmp_path))
    findings = [r for r in results if r.code == "instance/missing_required_field"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding.field == "title"
    assert "d1" in finding.message
    assert finding.file == "instances/demos/d1/demo.yaml"


# ---------------------------------------------------------------------------
# invalid status enum value
# ---------------------------------------------------------------------------


def test_invalid_status_enum_value_fires(tmp_path: Path) -> None:
    _write_demo_workflow(tmp_path)
    # `bogus` is not in [planned, completed].
    save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "bogus"})
    results = check_instance_shape_conforms(_ctx(tmp_path))
    findings = [r for r in results if r.code == "instance/invalid_status_value"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding.field == "status"
    assert "bogus" in finding.message


# ---------------------------------------------------------------------------
# multiple instances — only the bad one is flagged
# ---------------------------------------------------------------------------


def test_only_the_bad_instance_is_flagged(tmp_path: Path) -> None:
    _write_demo_workflow(tmp_path)
    save_instance(tmp_path, "demo", "good", {"id": "good", "status": "planned"})
    # `bad` carries an out-of-enum status.
    save_instance(tmp_path, "demo", "bad", {"id": "bad", "status": "deleted"})
    results = check_instance_shape_conforms(_ctx(tmp_path))
    # Only the bad instance should appear; the good one is silent.
    assert all("bad" in r.message for r in results), [r.message for r in results]
    assert all("good" not in r.message for r in results), [r.message for r in results]
    assert len(results) == 1
    assert results[0].code == "instance/invalid_status_value"


# ---------------------------------------------------------------------------
# workflow without `instance:` block — silently skipped
# ---------------------------------------------------------------------------


def test_workflow_without_instance_block_is_silent(tmp_path: Path) -> None:
    # Workflow.yaml that omits the `instance:` block — the missing-block
    # warning is owned by check_workflow_well_formed, not this check.
    parts = [
        "workflow_schema_version: 1",
        "workflows:",
        "  demo:",
        "    actor: pm-agent",
        "    trigger: demo.start",
        "    statuses:",
        "      - id: planned",
        "      - id: completed",
        "        terminal: true",
        "    routes:",
        "      - id: planned-to-completed",
        "        actor: pm-agent",
        "        from: planned",
        "        to: completed",
        "        kind: forward",
    ]
    (tmp_path / "workflow.yaml").write_text("\n".join(parts) + "\n", encoding="utf-8")
    assert check_instance_shape_conforms(_ctx(tmp_path)) == []


# ---------------------------------------------------------------------------
# missing workflow.yaml — silent
# ---------------------------------------------------------------------------


def test_missing_workflow_yaml_is_silent(tmp_path: Path) -> None:
    """A project without workflow.yaml has no instances to validate."""
    assert check_instance_shape_conforms(_ctx(tmp_path)) == []

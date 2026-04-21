"""Unit tests for dynamic enum loading from <project>/enums/."""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core.enum_loader import load_enums


def write_enum(project_dir: Path, name: str, values: list[dict]) -> None:
    enums_dir = project_dir / "enums"
    enums_dir.mkdir(exist_ok=True)
    (enums_dir / f"{name}.yaml").write_text(
        yaml.safe_dump({"name": name, "values": values}),
        encoding="utf-8",
    )


def test_falls_back_to_packaged_defaults_when_no_enums_dir(tmp_path: Path) -> None:
    registry = load_enums(tmp_path)
    # Should still have all packaged-default enums.
    assert "issue_status" in registry.enums
    assert "priority" in registry.enums
    assert "agent_state" in registry.enums

    issue_status = registry.get("issue_status")
    assert issue_status is not None
    assert issue_status.source == "default"
    assert "todo" in issue_status.value_ids()
    assert "in_progress" in issue_status.value_ids()


def test_project_enum_overrides_default(tmp_path: Path) -> None:
    write_enum(
        tmp_path,
        "issue_status",
        [
            {"id": "open", "label": "Open"},
            {"id": "closed", "label": "Closed"},
        ],
    )
    registry = load_enums(tmp_path)
    issue_status = registry.get("issue_status")
    assert issue_status is not None
    assert issue_status.source == "project"
    assert issue_status.value_ids() == ("open", "closed")
    assert "todo" not in issue_status.value_ids()  # default value not present
    assert registry.is_valid("issue_status", "open")
    assert not registry.is_valid("issue_status", "todo")


def test_project_can_extend_default_with_extra_value(tmp_path: Path) -> None:
    # Add an `qa` value on top of the default issue statuses.
    write_enum(
        tmp_path,
        "issue_status",
        [
            {"id": "backlog", "label": "Backlog"},
            {"id": "todo", "label": "To Do"},
            {"id": "in_progress", "label": "In Progress"},
            {"id": "qa", "label": "QA"},
            {"id": "done", "label": "Done"},
        ],
    )
    registry = load_enums(tmp_path)
    assert registry.is_valid("issue_status", "qa")
    assert registry.is_valid("issue_status", "todo")
    assert not registry.is_valid("issue_status", "verifying")  # we removed it


def test_project_defines_brand_new_enum(tmp_path: Path) -> None:
    # An enum name that doesn't exist in the packaged defaults.
    write_enum(
        tmp_path,
        "deployment_env",
        [
            {"id": "dev", "label": "Development"},
            {"id": "stage", "label": "Staging"},
            {"id": "prod", "label": "Production"},
        ],
    )
    registry = load_enums(tmp_path)
    assert "deployment_env" in registry.enums
    assert registry.is_valid("deployment_env", "stage")


def test_value_color_preserved(tmp_path: Path) -> None:
    write_enum(
        tmp_path,
        "issue_status",
        [{"id": "todo", "label": "To Do", "color": "blue"}],
    )
    registry = load_enums(tmp_path)
    issue_status = registry.get("issue_status")
    assert issue_status is not None
    assert issue_status.values[0].color == "blue"


def test_get_returns_none_for_unknown_enum(tmp_path: Path) -> None:
    registry = load_enums(tmp_path)
    assert registry.get("nonexistent_enum") is None
    assert registry.is_valid("nonexistent_enum", "anything") is False
    assert registry.value_ids("nonexistent_enum") == ()

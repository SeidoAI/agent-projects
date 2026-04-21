"""Tests for tripwire.ui.services.enum_service."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tripwire.ui.services.enum_service import (
    EnumDescriptor,
    EnumValue,
    get_enum,
    list_enums,
)


def _write_enum(project_dir: Path, name: str, content: str) -> None:
    d = project_dir / "enums"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(content, encoding="utf-8")


class TestListEnums:
    def test_empty_when_no_enums_dir(self, tmp_path_project: Path):
        # tmp_path_project fixture doesn't create enums/
        assert list_enums(tmp_path_project) == {}

    def test_loads_structured_enum(self, tmp_path_project: Path):
        _write_enum(
            tmp_path_project,
            "issue_status",
            "name: issue_status\n"
            "values:\n"
            "  - value: todo\n"
            "    label: Todo\n"
            "  - value: done\n"
            "    label: Done\n"
            "    color: '#00ff00'\n",
        )

        result = list_enums(tmp_path_project)
        assert "issue_status" in result
        enum = result["issue_status"]
        assert isinstance(enum, EnumDescriptor)
        assert enum.name == "issue_status"
        assert enum.values[0] == EnumValue(value="todo", label="Todo")
        assert enum.values[1].color == "#00ff00"

    def test_loads_flat_list(self, tmp_path_project: Path):
        _write_enum(
            tmp_path_project,
            "priority",
            "- low\n- medium\n- high\n",
        )

        result = list_enums(tmp_path_project)
        enum = result["priority"]
        assert [v.value for v in enum.values] == ["low", "medium", "high"]
        # Default label is title-cased.
        assert enum.values[0].label == "Low"
        # Colour defaults to None for flat list.
        assert enum.values[0].color is None

    def test_default_label_from_snake_case(self, tmp_path_project: Path):
        _write_enum(
            tmp_path_project,
            "states",
            "- in_progress\n",
        )
        enum = list_enums(tmp_path_project)["states"]
        assert enum.values[0].label == "In Progress"

    def test_legacy_id_field_accepted(self, tmp_path_project: Path):
        _write_enum(
            tmp_path_project,
            "kind",
            "values:\n  - id: feat\n  - id: fix\n    label: Bug Fix\n",
        )
        enum = list_enums(tmp_path_project)["kind"]
        assert enum.values[0] == EnumValue(value="feat", label="Feat")
        assert enum.values[1].label == "Bug Fix"

    def test_broken_enum_is_skipped_with_warning(
        self,
        tmp_path_project: Path,
        caplog: pytest.LogCaptureFixture,
    ):
        _write_enum(
            tmp_path_project,
            "good",
            "- a\n- b\n",
        )
        # Broken — values must be a list, here it's a string.
        _write_enum(
            tmp_path_project,
            "bad",
            "values: not-a-list\n",
        )

        with caplog.at_level(
            logging.WARNING, logger="tripwire.ui.services.enum_service"
        ):
            result = list_enums(tmp_path_project)

        assert "good" in result
        assert "bad" not in result
        assert "skipping" in caplog.text


class TestGetEnum:
    def test_returns_enum(self, tmp_path_project: Path):
        _write_enum(
            tmp_path_project,
            "issue_status",
            "values:\n  - value: todo\n    label: Todo\n",
        )
        enum = get_enum(tmp_path_project, "issue_status")
        assert enum.values[0] == EnumValue(value="todo", label="Todo")

    def test_raises_file_not_found(self, tmp_path_project: Path):
        with pytest.raises(FileNotFoundError):
            get_enum(tmp_path_project, "ghost")

    def test_description_passed_through(self, tmp_path_project: Path):
        _write_enum(
            tmp_path_project,
            "priority",
            "values:\n  - value: high\n    description: Do first\n",
        )
        enum = get_enum(tmp_path_project, "priority")
        assert enum.values[0].description == "Do first"

    def test_empty_enum_file_returns_empty(self, tmp_path_project: Path):
        _write_enum(tmp_path_project, "empty", "")
        enum = get_enum(tmp_path_project, "empty")
        assert enum.values == []

    def test_unknown_fields_logged_not_included(
        self,
        tmp_path_project: Path,
        caplog: pytest.LogCaptureFixture,
    ):
        _write_enum(
            tmp_path_project,
            "test",
            "values:\n  - value: a\n    unknown_field: surprise\n",
        )
        with caplog.at_level(logging.DEBUG, logger="tripwire.ui.services.enum_service"):
            enum = get_enum(tmp_path_project, "test")
        assert enum.values[0].value == "a"
        # The unknown field is not on the DTO; only standard fields are exposed.
        assert "unknown_field" not in enum.values[0].model_dump()

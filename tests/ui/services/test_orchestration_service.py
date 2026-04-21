"""Tests for tripwire.ui.services.orchestration_service."""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.ui.services.orchestration_service import (
    OrchestrationPattern,
    _deep_merge,
    get_active_pattern,
    get_session_pattern,
)


def _write_pattern(project_dir: Path, name: str, content: str) -> None:
    d = project_dir / "orchestration"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _deep_merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_top_level_union(self):
        assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_nested_dict_union(self):
        result = _deep_merge(
            {"nested": {"a": 1, "b": 2}},
            {"nested": {"b": 3, "c": 4}},
        )
        assert result == {"nested": {"a": 1, "b": 3, "c": 4}}

    def test_list_replace_not_append(self):
        assert _deep_merge({"xs": [1, 2]}, {"xs": [3]}) == {"xs": [3]}

    def test_override_wins_on_scalar(self):
        assert _deep_merge({"k": "a"}, {"k": "b"}) == {"k": "b"}


# ---------------------------------------------------------------------------
# get_active_pattern
# ---------------------------------------------------------------------------


class TestGetActivePattern:
    def test_loads_default_pattern(self, tmp_path_project: Path):
        _write_pattern(
            tmp_path_project,
            "default",
            "name: default\n"
            "plan_approval_required: true\n"
            "auto_merge_on_pass: false\n"
            "hooks: []\n"
            "rules:\n"
            "  - event: session.completed\n"
            "    action: notify\n"
            "    description: Ping the user\n",
        )

        pattern = get_active_pattern(tmp_path_project)
        assert isinstance(pattern, OrchestrationPattern)
        assert pattern.name == "default"
        assert pattern.plan_approval_required is True
        assert pattern.auto_merge_on_pass is False
        assert len(pattern.rules) == 1
        assert pattern.rules[0].event == "session.completed"
        assert pattern.overrides_applied is None

    def test_missing_file_raises(self, tmp_path_project: Path):
        # tmp_path_project default_pattern = "default" but no file exists
        with pytest.raises(FileNotFoundError):
            get_active_pattern(tmp_path_project)

    def test_source_path_recorded(self, tmp_path_project: Path):
        _write_pattern(tmp_path_project, "default", "name: default\n")
        pattern = get_active_pattern(tmp_path_project)
        assert pattern.source_path.endswith("orchestration/default.yaml")


# ---------------------------------------------------------------------------
# get_session_pattern
# ---------------------------------------------------------------------------


class TestGetSessionPattern:
    def test_no_overrides(
        self, tmp_path_project: Path, save_test_session
    ):
        _write_pattern(
            tmp_path_project,
            "default",
            "name: default\nauto_merge_on_pass: false\n",
        )
        save_test_session(tmp_path_project, "s1")

        pattern = get_session_pattern(tmp_path_project, "s1")
        assert pattern.auto_merge_on_pass is False
        assert pattern.overrides_applied is None

    def test_flat_override_applied(
        self, tmp_path_project: Path, save_test_session
    ):
        _write_pattern(
            tmp_path_project,
            "default",
            "name: default\nauto_merge_on_pass: false\n",
        )
        save_test_session(
            tmp_path_project,
            "s1",
            orchestration={
                "overrides": {"auto_merge_on_pass": True},
            },
        )

        pattern = get_session_pattern(tmp_path_project, "s1")
        assert pattern.auto_merge_on_pass is True
        assert pattern.overrides_applied == ["auto_merge_on_pass"]

    def test_nested_override_deep_merged(
        self, tmp_path_project: Path, save_test_session
    ):
        _write_pattern(
            tmp_path_project,
            "default",
            "name: default\n"
            "limits:\n"
            "  max_retries: 3\n"
            "  timeout: 60\n",
        )
        save_test_session(
            tmp_path_project,
            "s1",
            orchestration={
                "overrides": {
                    "limits": {"max_retries": 5},
                },
            },
        )

        pattern = get_session_pattern(tmp_path_project, "s1")
        # overrides_applied lists the top-level key whose value changed.
        assert "limits" in pattern.overrides_applied

    def test_session_selects_alternate_pattern(
        self, tmp_path_project: Path, save_test_session
    ):
        _write_pattern(
            tmp_path_project,
            "default",
            "name: default\nauto_merge_on_pass: false\n",
        )
        _write_pattern(
            tmp_path_project,
            "fast",
            "name: fast\nauto_merge_on_pass: true\n",
        )
        save_test_session(
            tmp_path_project,
            "s1",
            orchestration={"pattern": "fast"},
        )

        pattern = get_session_pattern(tmp_path_project, "s1")
        assert pattern.name == "fast"
        assert pattern.auto_merge_on_pass is True

    def test_missing_pattern_file_raises(
        self, tmp_path_project: Path, save_test_session
    ):
        # Default pattern file absent.
        save_test_session(tmp_path_project, "s1")
        with pytest.raises(FileNotFoundError):
            get_session_pattern(tmp_path_project, "s1")

    def test_overrides_applied_only_changed_keys(
        self, tmp_path_project: Path, save_test_session
    ):
        _write_pattern(
            tmp_path_project,
            "default",
            "name: default\nauto_merge_on_pass: false\n",
        )
        # An override that doesn't change the value shouldn't be listed.
        save_test_session(
            tmp_path_project,
            "s1",
            orchestration={
                "overrides": {"auto_merge_on_pass": False},
            },
        )

        pattern = get_session_pattern(tmp_path_project, "s1")
        assert pattern.overrides_applied == []

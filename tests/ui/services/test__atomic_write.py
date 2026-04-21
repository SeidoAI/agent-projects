"""Tests for the atomic-write helper used by mutation services."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tripwire.ui.services._atomic_write import (
    append_jsonl,
    atomic_write_text,
    atomic_write_yaml,
)


class TestAtomicWriteText:
    def test_creates_file_with_content(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        atomic_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_directory(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "out.txt"
        atomic_write_text(target, "x")
        assert target.read_text(encoding="utf-8") == "x"

    def test_overwrites_existing_file(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        target.write_text("old", encoding="utf-8")
        atomic_write_text(target, "new")
        assert target.read_text(encoding="utf-8") == "new"

    def test_no_tmp_debris_on_success(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        atomic_write_text(target, "content")
        # Only the target file should remain in the directory.
        assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]

    def test_no_tmp_debris_on_failure(self, tmp_path: Path, monkeypatch):
        """If os.replace raises, the tmp file is cleaned up."""
        import os

        def boom(src, dst):
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError, match="simulated"):
            atomic_write_text(tmp_path / "out.txt", "content")
        # No stray .tmp files left behind.
        assert list(tmp_path.iterdir()) == []


class TestAtomicWriteYaml:
    def test_writes_yaml_block_style(self, tmp_path: Path):
        target = tmp_path / "out.yaml"
        atomic_write_yaml(target, {"a": 1, "b": [2, 3]})
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"a": 1, "b": [2, 3]}

    def test_preserves_key_order(self, tmp_path: Path):
        target = tmp_path / "out.yaml"
        atomic_write_yaml(target, {"zebra": 1, "apple": 2})
        text = target.read_text(encoding="utf-8")
        # With sort_keys=False, zebra comes first.
        assert text.index("zebra") < text.index("apple")


class TestAppendJsonl:
    def test_appends_single_line(self, tmp_path: Path):
        target = tmp_path / "audit.jsonl"
        append_jsonl(target, {"action": "foo"})
        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == {"action": "foo"}

    def test_appends_to_existing_file(self, tmp_path: Path):
        target = tmp_path / "audit.jsonl"
        append_jsonl(target, {"n": 1})
        append_jsonl(target, {"n": 2})
        lines = target.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["n"] for line in lines] == [1, 2]

    def test_creates_parent_directory(self, tmp_path: Path):
        target = tmp_path / "logs" / "audit.jsonl"
        append_jsonl(target, {"action": "foo"})
        assert target.is_file()

    def test_encodes_non_json_values_as_strings(self, tmp_path: Path):
        """datetimes and other non-JSON types coerce via ``default=str``."""
        from datetime import datetime, timezone

        target = tmp_path / "audit.jsonl"
        moment = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        append_jsonl(target, {"when": moment})
        record = json.loads(target.read_text(encoding="utf-8"))
        assert record["when"].startswith("2026-04-14")

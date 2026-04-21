"""Unit tests for the YAML frontmatter + Markdown body parser."""

from __future__ import annotations

import pytest

from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)


class TestParseFrontmatterBody:
    def test_basic_parse(self) -> None:
        text = "---\nid: SEI-1\ntitle: Test\n---\n## Body\n\nSome content.\n"
        fm, body = parse_frontmatter_body(text)
        assert fm == {"id": "SEI-1", "title": "Test"}
        assert body == "## Body\n\nSome content.\n"

    def test_empty_body(self) -> None:
        text = "---\nid: SEI-1\n---\n"
        fm, body = parse_frontmatter_body(text)
        assert fm == {"id": "SEI-1"}
        assert body == ""

    def test_body_with_code_block(self) -> None:
        text = "---\nid: SEI-1\n---\n## Test\n\n```python\ndef foo():\n    pass\n```\n"
        fm, body = parse_frontmatter_body(text)
        assert fm == {"id": "SEI-1"}
        assert "```python" in body
        assert "def foo()" in body

    def test_nested_yaml_in_frontmatter(self) -> None:
        text = (
            "---\n"
            "id: SEI-1\n"
            "labels:\n"
            "  - foo\n"
            "  - bar\n"
            "source:\n"
            "  repo: SeidoAI/x\n"
            "  path: src/a.py\n"
            "---\n"
            "Body.\n"
        )
        fm, _body = parse_frontmatter_body(text)
        assert fm["labels"] == ["foo", "bar"]
        assert fm["source"]["repo"] == "SeidoAI/x"

    def test_missing_opening_delimiter_raises(self) -> None:
        with pytest.raises(ParseError, match="must begin with"):
            parse_frontmatter_body("just a body, no frontmatter\n")

    def test_missing_closing_delimiter_raises(self) -> None:
        with pytest.raises(ParseError, match="must be closed"):
            parse_frontmatter_body("---\nid: SEI-1\nno closing\n")

    def test_invalid_yaml_raises(self) -> None:
        with pytest.raises(ParseError, match="Invalid YAML"):
            parse_frontmatter_body("---\nid: : :\n---\nbody\n")

    def test_non_mapping_frontmatter_raises(self) -> None:
        # A YAML list at the top level is not a mapping.
        with pytest.raises(ParseError, match="must be a YAML mapping"):
            parse_frontmatter_body("---\n- foo\n- bar\n---\nbody\n")


class TestSerializeFrontmatterBody:
    def test_basic_serialise(self) -> None:
        text = serialize_frontmatter_body(
            {"id": "SEI-1", "title": "Test"}, "## Body\nContent.\n"
        )
        assert text.startswith("---\n")
        assert "id: SEI-1" in text
        assert "title: Test" in text
        assert "## Body" in text

    def test_round_trip(self) -> None:
        original_fm = {"id": "SEI-1", "labels": ["a", "b"], "priority": "high"}
        original_body = "## Header\n\nLine 1.\nLine 2.\n"
        text = serialize_frontmatter_body(original_fm, original_body)
        fm, body = parse_frontmatter_body(text)
        assert fm == original_fm
        assert body == original_body

    def test_preserves_key_order(self) -> None:
        fm = {"uuid": "abc", "id": "SEI-1", "title": "T", "status": "todo"}
        text = serialize_frontmatter_body(fm, "")
        # Check that uuid appears before id, id before title, etc.
        assert text.find("uuid:") < text.find("id:") < text.find("title:")

    def test_empty_body_serialises(self) -> None:
        text = serialize_frontmatter_body({"id": "SEI-1"}, "")
        _fm, body = parse_frontmatter_body(text)
        assert body == ""

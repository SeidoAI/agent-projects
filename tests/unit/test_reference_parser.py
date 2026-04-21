"""Unit tests for the reference parser ([[node-id]] extraction)."""

from __future__ import annotations

from tripwire.core.reference_parser import extract_references, replace_references


class TestExtractReferences:
    def test_no_refs(self) -> None:
        assert extract_references("just plain text") == []

    def test_single_ref(self) -> None:
        assert extract_references("see [[user-model]] for details") == ["user-model"]

    def test_multiple_refs(self) -> None:
        body = "uses [[user-model]] and [[auth-endpoint]]"
        assert extract_references(body) == ["user-model", "auth-endpoint"]

    def test_duplicates_preserved(self) -> None:
        body = "[[foo]] then [[foo]] again"
        assert extract_references(body) == ["foo", "foo"]

    def test_inside_code_block_skipped(self) -> None:
        body = (
            "Outside [[real-ref]]\n"
            "```\n"
            "this [[fake-ref]] is in a code block\n"
            "```\n"
            "After [[other-ref]]\n"
        )
        refs = extract_references(body)
        assert "real-ref" in refs
        assert "other-ref" in refs
        assert "fake-ref" not in refs

    def test_tilde_fence_also_skipped(self) -> None:
        body = "Outside [[real]]\n~~~\n[[fake]]\n~~~\nAfter [[real2]]\n"
        refs = extract_references(body)
        assert "real" in refs
        assert "real2" in refs
        assert "fake" not in refs

    def test_nested_brackets_not_matched(self) -> None:
        # `[Linktext](url)` and `[plain]` should not match the [[id]] pattern.
        body = "[link](https://x.com) and [single] but [[real-ref]] yes"
        assert extract_references(body) == ["real-ref"]

    def test_uppercase_refs_rejected(self) -> None:
        # Refs must be lowercase slugs. `[[UserModel]]` is not a node id.
        assert extract_references("see [[UserModel]]") == []

    def test_complex_realistic_body(self) -> None:
        body = (
            "## Context\n"
            "The API needs a JWT endpoint. Must consume [[user-model]] and "
            "respect [[dec-007-rate-limiting]].\n"
            "\n"
            "## Test plan\n"
            "```bash\n"
            "uv run pytest [[fake-ref]]\n"
            "```\n"
            "\n"
            "## Dependencies\n"
            "[[user-model]] must land first.\n"
        )
        refs = extract_references(body)
        assert refs == ["user-model", "dec-007-rate-limiting", "user-model"]


class TestReplaceReferences:
    def test_basic_replace(self) -> None:
        body = "see [[user-model]] for details"
        result = replace_references(body, lambda nid: f"<{nid}>")
        assert result == "see <user-model> for details"

    def test_multiple_replace(self) -> None:
        body = "[[a]] and [[b]]"
        result = replace_references(body, lambda nid: nid.upper())
        assert result == "A and B"

    def test_skips_code_blocks(self) -> None:
        body = "Outside [[a]]\n```\n[[b]]\n```\nAfter [[c]]\n"
        result = replace_references(body, lambda nid: f"<{nid}>")
        assert "<a>" in result
        assert "<c>" in result
        assert "<b>" not in result
        assert "[[b]]" in result  # untouched inside the code block

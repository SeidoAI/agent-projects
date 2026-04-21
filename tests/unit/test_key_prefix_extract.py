"""Tests for `_extract_key_prefix` in `tripwire.cli.init`.

The extractor takes a project name and produces a short uppercase
prefix suitable for issue keys (e.g. `MPC-42`). It splits on common
separators and camelCase boundaries, takes the first letter of each
segment, uppercases, and pads single-word names to at least two
characters. Returns `None` when no valid prefix can be derived.
"""

from __future__ import annotations

import pytest

from tripwire.cli.init import KEY_PREFIX_PATTERN, _extract_key_prefix


@pytest.mark.parametrize(
    "name,expected",
    [
        # Hyphen-separated
        ("my-project-cool", "MPC"),
        ("agent-project", "AP"),
        ("kb-pivot", "KP"),
        ("project-kb-pivot", "PKP"),
        # Underscore-separated
        ("my_project_cool", "MPC"),
        ("snake_case_name", "SCN"),
        # Space-separated
        ("my project cool", "MPC"),
        # Dot-separated
        ("my.project.cool", "MPC"),
        # camelCase / PascalCase
        ("MyProjectCool", "MPC"),
        ("myProjectCool", "MPC"),
        # Single-word names → padded to 2 chars from the first segment
        ("backend", "BA"),
        ("frontend", "FR"),
        ("api", "AP"),
        # Mixed separators
        ("web-app_backend", "WAB"),
        ("My-Project.Cool", "MPC"),
    ],
)
def test_extract_produces_expected_prefix(name: str, expected: str) -> None:
    assert _extract_key_prefix(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        # Leading digit → invalid per KEY_PREFIX_PATTERN
        "2024-retro",
        "1password",
        # Empty / whitespace only
        "",
        "   ",
        # Non-alphanumeric only
        "---",
        "___",
        "...",
    ],
)
def test_extract_returns_none_for_invalid(name: str) -> None:
    assert _extract_key_prefix(name) is None


def test_extract_result_always_matches_pattern() -> None:
    """Every non-None result must satisfy the validator's regex."""
    for name in [
        "my-project",
        "MyProject",
        "backend",
        "web-app-backend-v2",
        "project_alpha",
    ]:
        result = _extract_key_prefix(name)
        assert result is not None
        assert KEY_PREFIX_PATTERN.match(result), (
            f"Extracted {result!r} from {name!r} does not match pattern"
        )


def test_extract_handles_single_character_name() -> None:
    """Single-letter names pad to 2 chars if possible, else stay at 1."""
    # `a` has no second character to pad from → result is `A` (valid per regex).
    assert _extract_key_prefix("a") == "A"


def test_extract_handles_trailing_digits_in_segment() -> None:
    """Digits in the middle of a segment are allowed."""
    # `v2` → takes `V`, then pads with `2` from the first segment.
    # But actually the segment is "v2", so initial is "V", and the
    # second char of the first segment is "2" — which is alphanumeric
    # but is a digit. We allow it per KEY_PREFIX_PATTERN which allows
    # digits after the leading letter.
    assert _extract_key_prefix("v2") == "V2"


def test_extract_handles_mixed_case_with_separators() -> None:
    """camelCase segments split by separators are fully decomposed."""
    # `My-ProjectCool` → segments after separator split: ["My", "ProjectCool"]
    # → after camelCase split: ["My", "Project", "Cool"] → "MPC"
    assert _extract_key_prefix("My-ProjectCool") == "MPC"

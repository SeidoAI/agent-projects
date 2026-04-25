"""Tests for `<project>/lint/concept-allowlist.yaml` loader."""

from pathlib import Path

import pytest

from tripwire.core.lint_allowlist import (
    AllowlistError,
    load_concept_allowlist,
)


def test_missing_file_returns_empty_set(tmp_path_project: Path) -> None:
    """No allowlist file → empty allowlist, no error.

    The allowlist is opt-in; projects without one shouldn't see errors.
    """
    assert load_concept_allowlist(tmp_path_project) == set()


def test_loads_terms_from_yaml(tmp_path_project: Path) -> None:
    """Standard schema: list of {term, reason}."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text(
        "allowlist:\n"
        '  - term: "Stripe"\n'
        '    reason: "Third-party reference, not a load-bearing concept."\n'
        '  - term: "JSON"\n'
        '    reason: "Format name; cross-cutting but not node-shaped."\n',
        encoding="utf-8",
    )
    assert load_concept_allowlist(tmp_path_project) == {"stripe", "json"}


def test_terms_normalised_to_lowercase(tmp_path_project: Path) -> None:
    """Normalised case so callers can match against any-case candidates."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text(
        "allowlist:\n"
        '  - term: "WebSocket Hub"\n'
        '    reason: "Mentioned once."\n',
        encoding="utf-8",
    )
    assert load_concept_allowlist(tmp_path_project) == {"websocket hub"}


def test_missing_reason_raises(tmp_path_project: Path) -> None:
    """Required `reason` field — silent suppression isn't allowed."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text(
        "allowlist:\n  - term: \"Stripe\"\n",
        encoding="utf-8",
    )
    with pytest.raises(AllowlistError, match="reason"):
        load_concept_allowlist(tmp_path_project)


def test_empty_reason_raises(tmp_path_project: Path) -> None:
    """Empty / whitespace-only reason is the same as missing — rejected."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text(
        'allowlist:\n  - term: "Stripe"\n    reason: "   "\n',
        encoding="utf-8",
    )
    with pytest.raises(AllowlistError, match="reason"):
        load_concept_allowlist(tmp_path_project)


def test_missing_term_raises(tmp_path_project: Path) -> None:
    """A `reason` without a `term` is also malformed."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text(
        'allowlist:\n  - reason: "stub"\n',
        encoding="utf-8",
    )
    with pytest.raises(AllowlistError, match="term"):
        load_concept_allowlist(tmp_path_project)


def test_no_allowlist_key_returns_empty(tmp_path_project: Path) -> None:
    """A file with no `allowlist:` key (e.g. a comment-only stub) → empty set."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text("# nothing here yet\n", encoding="utf-8")
    assert load_concept_allowlist(tmp_path_project) == set()


def test_top_level_must_be_mapping(tmp_path_project: Path) -> None:
    """A bare list at the root is malformed — the schema is `{allowlist: [...]}`."""
    allowlist_path = tmp_path_project / "lint" / "concept-allowlist.yaml"
    allowlist_path.parent.mkdir(parents=True)
    allowlist_path.write_text(
        "- term: Stripe\n  reason: x\n",
        encoding="utf-8",
    )
    with pytest.raises(AllowlistError, match="mapping"):
        load_concept_allowlist(tmp_path_project)

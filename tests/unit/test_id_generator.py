"""Unit tests for sequential key formatting and parsing."""

from __future__ import annotations

import pytest

from tripwire.core.id_generator import format_key, is_valid_key, parse_key


class TestFormatKey:
    def test_basic(self) -> None:
        assert format_key("SEI", 42) == "SEI-42"
        assert format_key("PKB", 1) == "PKB-1"
        assert format_key("X", 999) == "X-999"

    def test_lowercase_prefix_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_key("sei", 1)

    def test_empty_prefix_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_key("", 1)

    def test_zero_or_negative_number_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_key("SEI", 0)
        with pytest.raises(ValueError):
            format_key("SEI", -1)


class TestParseKey:
    def test_basic(self) -> None:
        assert parse_key("SEI-42") == ("SEI", 42)
        assert parse_key("PKB-1") == ("PKB", 1)

    def test_with_digits_in_prefix(self) -> None:
        assert parse_key("X1-5") == ("X1", 5)

    def test_invalid_format_raises(self) -> None:
        for bad in ["sei-1", "SEI", "SEI-", "-1", "SEI 1", "SEI-1.0", "SEI-abc"]:
            with pytest.raises(ValueError):
                parse_key(bad)


class TestIsValidKey:
    def test_valid(self) -> None:
        for k in ["SEI-1", "PKB-42", "X-9999"]:
            assert is_valid_key(k)

    def test_invalid(self) -> None:
        for k in ["sei-1", "SEI", "SEI-", "-1", "SEI 1"]:
            assert not is_valid_key(k)

"""Unit tests for UUID generation and validation helpers."""

from __future__ import annotations

from uuid import UUID

import pytest

from tripwire.core.uuid_helpers import coerce_uuid, generate_uuid, is_valid_uuid


def test_generate_uuid_returns_uuid4() -> None:
    u = generate_uuid()
    assert isinstance(u, UUID)
    assert u.version == 4


def test_generate_uuid_returns_distinct_values() -> None:
    seen = {generate_uuid() for _ in range(100)}
    assert len(seen) == 100


class TestIsValidUuid:
    def test_valid_string(self) -> None:
        assert is_valid_uuid("7c3a4b1d-9f2e-4a8c-b5d6-1e2f3a4b5c6d")

    def test_valid_uuid_object(self) -> None:
        assert is_valid_uuid(generate_uuid())

    def test_invalid_string(self) -> None:
        assert not is_valid_uuid("not-a-uuid")
        assert not is_valid_uuid("")
        assert not is_valid_uuid("12345")

    def test_none_is_invalid(self) -> None:
        assert not is_valid_uuid(None)  # type: ignore[arg-type]


class TestCoerceUuid:
    def test_string_to_uuid(self) -> None:
        u = coerce_uuid("7c3a4b1d-9f2e-4a8c-b5d6-1e2f3a4b5c6d")
        assert isinstance(u, UUID)

    def test_uuid_passthrough(self) -> None:
        original = generate_uuid()
        assert coerce_uuid(original) is original

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            coerce_uuid("nope")

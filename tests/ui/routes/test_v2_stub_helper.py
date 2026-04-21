"""Unit tests for the shared v2 stub envelope helper."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tripwire.ui.routes._v2_stub import (
    V2_DEFAULT_PLAN,
    V2_NOT_IMPLEMENTED_CODE,
    raise_v2_not_implemented,
)


class TestRaiseV2NotImplemented:
    def test_raises_http_exception_with_501(self):
        with pytest.raises(HTTPException) as exc:
            raise_v2_not_implemented("containers.list is v2")
        assert exc.value.status_code == 501

    def test_envelope_shape(self):
        with pytest.raises(HTTPException) as exc:
            raise_v2_not_implemented("messages.list is v2")
        detail = exc.value.detail
        assert isinstance(detail, dict)
        assert detail["detail"] == "messages.list is v2"
        assert detail["code"] == V2_NOT_IMPLEMENTED_CODE
        assert detail["extras"] == {"plan": V2_DEFAULT_PLAN}

    def test_custom_plan_pointer(self):
        with pytest.raises(HTTPException) as exc:
            raise_v2_not_implemented("github.list_prs", plan="docs/tripwire-github.md")
        assert exc.value.detail["extras"] == {"plan": "docs/tripwire-github.md"}

    def test_code_constant_is_v2_not_implemented(self):
        assert V2_NOT_IMPLEMENTED_CODE == "v2/not_implemented"

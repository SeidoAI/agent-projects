"""Shared fixtures + envelope helper for v2 stub route tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tripwire.ui.routes._v2_stub import V2_NOT_IMPLEMENTED_CODE
from tripwire.ui.server import create_app


@pytest.fixture
def client() -> TestClient:
    """TestClient against the full FastAPI app in dev-mode."""
    return TestClient(create_app(dev_mode=True))


def assert_v2_envelope(resp) -> None:
    """Assert *resp* is the canonical v2 501 envelope.

    The expected body shape is::

        {"detail": {"detail": <str>, "code": "v2/not_implemented",
                    "extras": <dict>}}
    """
    assert resp.status_code == 501, f"expected 501, got {resp.status_code}"
    body = resp.json()
    assert "detail" in body, body
    detail = body["detail"]
    assert isinstance(detail, dict), detail
    assert detail["code"] == V2_NOT_IMPLEMENTED_CODE
    assert isinstance(detail.get("detail"), str) and detail["detail"]
    assert isinstance(detail.get("extras"), dict)

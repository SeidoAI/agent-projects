"""Tests for the shared v1 error envelope (`routes/_common.py`).

Covers the envelope helper, the flattening exception handler, and the
handler's interaction with pre-existing error shapes (v2 stub nested
envelope, FastAPI's default string-detail behaviour).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tripwire.ui.routes._common import (
    ErrorEnvelope,
    envelope_exception,
    install_error_handlers,
)


def _app_with_route(route) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)
    app.get("/boom")(route)
    return TestClient(app)


class TestEnvelopeException:
    def test_builds_http_exception_with_status(self):
        exc = envelope_exception(404, code="thing/not_found", detail="gone")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 404

    def test_detail_carries_envelope(self):
        exc = envelope_exception(409, code="x/y", detail="nope", hint="try z")
        assert exc.detail == {"detail": "nope", "code": "x/y", "hint": "try z"}

    def test_omits_hint_when_absent(self):
        exc = envelope_exception(400, code="x/y", detail="nope")
        assert exc.detail == {"detail": "nope", "code": "x/y"}


class TestErrorEnvelopeModel:
    def test_required_fields(self):
        env = ErrorEnvelope(detail="msg", code="foo/bar")
        assert env.detail == "msg"
        assert env.code == "foo/bar"
        assert env.hint is None

    def test_hint_roundtrip(self):
        env = ErrorEnvelope(detail="msg", code="foo/bar", hint="fix it")
        assert env.model_dump() == {
            "detail": "msg",
            "code": "foo/bar",
            "hint": "fix it",
        }


class TestFlattenHandler:
    def test_v1_envelope_flattened_to_top_level(self):
        async def route() -> None:
            raise envelope_exception(404, code="resource/not_found", detail="gone")

        client = _app_with_route(route)
        r = client.get("/boom")
        assert r.status_code == 404
        assert r.json() == {"detail": "gone", "code": "resource/not_found"}

    def test_v1_envelope_includes_hint(self):
        async def route() -> None:
            raise envelope_exception(
                409, code="state/invalid", detail="bad move", hint="try again"
            )

        client = _app_with_route(route)
        r = client.get("/boom")
        assert r.status_code == 409
        assert r.json() == {
            "detail": "bad move",
            "code": "state/invalid",
            "hint": "try again",
        }

    def test_plain_string_detail_passes_through(self):
        async def route() -> None:
            raise HTTPException(status_code=418, detail="teapot")

        client = _app_with_route(route)
        r = client.get("/boom")
        assert r.status_code == 418
        # FastAPI default shape: {"detail": "teapot"}
        assert r.json() == {"detail": "teapot"}

    def test_non_envelope_dict_detail_passes_through(self):
        """v2 stubs raise a dict detail with `extras` — handler must not flatten."""

        async def route() -> None:
            raise HTTPException(
                status_code=501,
                detail={
                    "detail": "v2 not ready",
                    "code": "v2/not_implemented",
                    "extras": {"plan": "docs/foo.md"},
                },
            )

        client = _app_with_route(route)
        r = client.get("/boom")
        assert r.status_code == 501
        body = r.json()
        # Default FastAPI serialisation nests the dict detail — keep that.
        assert body == {
            "detail": {
                "detail": "v2 not ready",
                "code": "v2/not_implemented",
                "extras": {"plan": "docs/foo.md"},
            }
        }


class TestHandlerPreservesHeaders:
    def test_envelope_response_preserves_status(self):
        async def route() -> None:
            raise envelope_exception(422, code="request/invalid", detail="bad body")

        client = _app_with_route(route)
        r = client.get("/boom")
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/json")


class TestInstallErrorHandlers:
    def test_installs_exception_handler(self):
        app = FastAPI()
        install_error_handlers(app)
        # The Starlette HTTPException handler must be registered.
        from starlette.exceptions import HTTPException as StarletteHTTPException

        assert StarletteHTTPException in app.exception_handlers


class TestAppIntegration:
    """End-to-end: the real app factory installs handlers."""

    def test_real_app_flattens_envelope(self):
        from tripwire.ui.server import create_app

        app = create_app(dev_mode=True)

        @app.get("/__test_envelope__")
        async def _boom() -> None:
            raise envelope_exception(404, code="test/not_found", detail="integration")

        client = TestClient(app)
        r = client.get("/__test_envelope__")
        assert r.status_code == 404
        assert r.json() == {"detail": "integration", "code": "test/not_found"}


@pytest.mark.parametrize(
    "status,code,detail",
    [
        (400, "x/bad_request", "bad"),
        (404, "x/not_found", "gone"),
        (409, "x/conflict", "no"),
        (422, "x/invalid", "huh"),
        (500, "x/internal", "oops"),
    ],
)
def test_envelope_exception_parametrised(status, code, detail):
    exc = envelope_exception(status, code=code, detail=detail)
    assert exc.status_code == status
    assert exc.detail["code"] == code
    assert exc.detail["detail"] == detail

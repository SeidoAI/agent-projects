"""Shared 501 envelope helper for v2 stub routes.

All v2 stub modules raise the same error envelope via
``raise_v2_not_implemented`` so the frontend's ``isV2NotImplemented(err)``
detector can rely on a canonical ``code`` field rather than parsing
free-form detail strings.

See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from typing import Any, Literal, NoReturn

from fastapi import HTTPException
from pydantic import BaseModel

V2_NOT_IMPLEMENTED_CODE = "v2/not_implemented"
V2_DEFAULT_PLAN = "docs/agent-containers.md"


class V2NotImplementedDetail(BaseModel):
    """Inner body of the canonical v2 501 envelope — the dict that
    ``raise_v2_not_implemented`` passes as ``HTTPException.detail``.
    """

    detail: str
    code: Literal["v2/not_implemented"]
    extras: dict[str, Any]


class V2NotImplementedEnvelope(BaseModel):
    """Top-level shape of a v2 501 response.

    FastAPI wraps ``HTTPException.detail`` under a top-level ``detail``
    key, so the wire payload is ``{"detail": {<V2NotImplementedDetail>}}``.
    Declared here so OpenAPI's 501 response schema matches what clients
    actually receive.
    """

    detail: V2NotImplementedDetail


V2_RESPONSES: dict[int | str, dict[str, Any]] = {
    501: {
        "model": V2NotImplementedEnvelope,
        "description": "Not implemented in v1",
    }
}


def raise_v2_not_implemented(
    detail: str,
    *,
    plan: str = V2_DEFAULT_PLAN,
) -> NoReturn:
    """Raise a 501 ``HTTPException`` with the canonical v2 envelope.

    The FastAPI response body is::

        {"detail": {"detail": <detail>, "code": "v2/not_implemented",
                    "extras": {"plan": <plan>}}}
    """
    raise HTTPException(
        status_code=501,
        detail={
            "detail": detail,
            "code": V2_NOT_IMPLEMENTED_CODE,
            "extras": {"plan": plan},
        },
    )

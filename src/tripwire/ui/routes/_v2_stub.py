"""Shared 501 envelope helper for v2 stub routes.

All v2 stub modules raise the same error envelope via
``raise_v2_not_implemented`` so the frontend's ``isV2NotImplemented(err)``
detector can rely on a canonical ``code`` field rather than parsing
free-form detail strings.

See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

V2_NOT_IMPLEMENTED_CODE = "v2/not_implemented"
V2_DEFAULT_PLAN = "docs/tripwire-containers.md"


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

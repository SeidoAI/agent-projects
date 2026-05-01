"""Tests for shared route parameter validators."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tripwire.ui.routes._params import ensure_session_id


@pytest.mark.parametrize(
    "sid",
    [
        "session-a",
        "TST-S1",
        "X1-S42",
        "s_done",
        "S1",
        "abc123",
        "1-session",
    ],
)
def test_ensure_session_id_accepts_known_session_id_shapes(sid: str) -> None:
    ensure_session_id(sid)


@pytest.mark.parametrize(
    "sid",
    [
        "",
        ".",
        "..",
        "../session",
        "session/plan",
        r"..\session",
        " session",
        "session ",
        "bad.value",
        "bad$value",
        "-bad",
    ],
)
def test_ensure_session_id_rejects_path_like_or_noncanonical_values(
    sid: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        ensure_session_id(sid)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "session/bad_slug"

"""Integration tests for the v2 messages stub router (KUI-42)."""

from __future__ import annotations

import inspect

from tests.ui.routes.conftest import assert_v2_envelope


class TestMessageRoutes501:
    def test_create(self, client):
        assert_v2_envelope(
            client.post(
                "/api/messages",
                json={
                    "session_id": "s1",
                    "type": "question",
                    "priority": "normal",
                    "body": "hi",
                },
            )
        )

    def test_list(self, client):
        assert_v2_envelope(client.get("/api/messages", params={"session_id": "s1"}))

    def test_pending(self, client):
        assert_v2_envelope(
            client.get("/api/messages/pending", params={"session_id": "s1"})
        )

    def test_respond(self, client):
        assert_v2_envelope(
            client.post(
                "/api/messages/abc/respond",
                json={"body": "ok", "decision": "approve"},
            )
        )


class TestUnreadV1:
    def test_returns_zero_count(self, client):
        # v1 has no agent containers, so /unread is the one v2-stub
        # endpoint that can answer truthfully: there is no inbox, the
        # count is always 0. (KUI-73)
        r = client.get("/api/messages/unread")
        assert r.status_code == 200
        assert r.json() == {"count": 0}


class TestMessagesOpenAPI:
    def test_all_paths_tagged_messages_v2(self, client):
        spec = client.get("/openapi.json").json()
        paths = spec["paths"]
        expected = {
            "/api/messages": ("post", "get"),
            "/api/messages/pending": ("get",),
            "/api/messages/{message_id}/respond": ("post",),
            "/api/messages/unread": ("get",),
        }
        for path, methods in expected.items():
            assert path in paths, f"missing OpenAPI path {path}"
            for method in methods:
                op = paths[path][method]
                assert "messages (v2)" in op.get("tags", []), (
                    f"{path}.{method} missing messages (v2) tag"
                )


class TestNoSqliteImport:
    def test_sqlite_not_imported(self):
        # sys.modules is global and pollutable by coverage and other test
        # modules, so inspect the stub source directly instead.
        from tripwire.ui.routes import messages
        from tripwire.ui.services import message_service

        for mod in (messages, message_service):
            src = inspect.getsource(mod)
            assert "import sqlite3" not in src, (
                f"{mod.__name__} imports sqlite3 — v2 stub should not"
            )
            assert "from sqlite3" not in src, (
                f"{mod.__name__} imports from sqlite3 — v2 stub should not"
            )

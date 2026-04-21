"""v0.6b node frontmatter additions: origin, scope, workspace_sha."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tripwire.models.node import ConceptNode


def _base_node(**overrides):
    defaults = {
        "uuid": uuid4(),
        "id": "test-node",
        "type": "concept",
        "name": "Test",
        "status": "active",
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(overrides)
    return ConceptNode(**defaults)


class TestOriginAndScope:
    def test_defaults_to_local_local(self):
        n = _base_node()
        assert n.origin == "local"
        assert n.scope == "local"

    def test_accepts_workspace_origin(self):
        n = _base_node(
            origin="workspace",
            scope="workspace",
            workspace_sha="a3f2b1c",
            workspace_pulled_at=datetime.now(tz=timezone.utc),
        )
        assert n.origin == "workspace"
        assert n.workspace_sha == "a3f2b1c"

    def test_workspace_origin_without_sha_allowed(self):
        """Canonical workspace nodes (in the workspace repo itself) have
        origin=workspace but no workspace_sha — that's project-side
        bookkeeping stamped at pull time.
        """
        n = _base_node(origin="workspace", scope="workspace")
        assert n.workspace_sha is None

    def test_local_origin_forbids_workspace_sha(self):
        with pytest.raises(ValidationError):
            _base_node(origin="local", scope="local", workspace_sha="a3f2b1c")

    def test_forked_keeps_workspace_sha(self):
        """origin=workspace, scope=local (detached fork) keeps workspace_sha."""
        n = _base_node(
            origin="workspace",
            scope="local",
            workspace_sha="a3f2b1c",
            workspace_pulled_at=datetime.now(tz=timezone.utc),
        )
        assert n.scope == "local"
        assert n.workspace_sha == "a3f2b1c"

    def test_promotion_candidate_no_workspace_sha(self):
        """origin=local, scope=workspace (promotion candidate): no sha yet."""
        n = _base_node(origin="local", scope="workspace")
        assert n.origin == "local"
        assert n.scope == "workspace"
        assert n.workspace_sha is None

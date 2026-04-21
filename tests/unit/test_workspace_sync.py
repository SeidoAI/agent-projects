"""workspace_sync.merge_nodes: 3-way merge engine.

Covers trivial cases (fast-forward, no upstream changes, no changes,
non-overlapping auto-merge) and conflict detection. Agent-mediated
brief generation is separately tested in test_merge_brief.
"""

from tripwire.core.workspace_sync import (
    MergeStatus,
    merge_nodes,
)


def _node_dict(**overrides):
    base = {
        "id": "n",
        "name": "Name",
        "description": "Base description.",
        "related_to": ["a", "b"],
    }
    base.update(overrides)
    return base


class TestMergeEngine:
    def test_fast_forward_when_ours_equals_base(self):
        base = _node_dict()
        ours = _node_dict()  # unchanged locally
        theirs = _node_dict(description="Updated upstream.")
        result = merge_nodes(base=base, ours=ours, theirs=theirs)
        assert result.status is MergeStatus.FAST_FORWARD
        assert result.merged is not None
        assert result.merged["description"] == "Updated upstream."

    def test_no_upstream_changes(self):
        base = _node_dict()
        ours = _node_dict(description="Changed locally.")
        theirs = _node_dict()  # unchanged upstream
        result = merge_nodes(base=base, ours=ours, theirs=theirs)
        assert result.status is MergeStatus.NO_UPSTREAM_CHANGES
        assert result.merged is not None
        assert result.merged["description"] == "Changed locally."

    def test_no_changes_when_all_three_match(self):
        base = _node_dict()
        result = merge_nodes(base=base, ours=dict(base), theirs=dict(base))
        assert result.status is MergeStatus.NO_CHANGES

    def test_non_overlapping_fields_auto_merge(self):
        base = _node_dict()
        ours = _node_dict(description="Local change.")
        theirs = _node_dict(related_to=["a", "b", "c"])
        result = merge_nodes(base=base, ours=ours, theirs=theirs)
        assert result.status is MergeStatus.AUTO_MERGED
        assert result.merged is not None
        assert result.merged["description"] == "Local change."
        assert result.merged["related_to"] == ["a", "b", "c"]
        assert set(result.auto_merged_fields) == {"description", "related_to"}

    def test_overlapping_conflict_returns_conflict_status(self):
        base = _node_dict()
        ours = _node_dict(description="Local change.")
        theirs = _node_dict(description="Upstream change.")
        result = merge_nodes(base=base, ours=ours, theirs=theirs)
        assert result.status is MergeStatus.CONFLICT
        assert "description" in result.conflicting_fields

    def test_bookkeeping_fields_ignored(self):
        """uuid/created_at/updated_at/workspace_sha etc. don't count as changes."""
        base = _node_dict(uuid="u1", workspace_sha="a")
        ours = _node_dict(uuid="u1", workspace_sha="b")  # only bookkeeping changed
        theirs = _node_dict(uuid="u1", workspace_sha="c")
        result = merge_nodes(base=base, ours=ours, theirs=theirs)
        assert result.status is MergeStatus.NO_CHANGES

    def test_structural_same_new_value(self):
        """Both sides changed to the same new value — classified as auto-merged."""
        base = _node_dict()
        ours = _node_dict(description="Shared change.")
        theirs = _node_dict(description="Shared change.")
        result = merge_nodes(base=base, ours=ours, theirs=theirs)
        # Since ours == theirs on this field, no conflict; either is fine.
        assert result.status in (
            MergeStatus.AUTO_MERGED,
            MergeStatus.FAST_FORWARD,
            MergeStatus.NO_UPSTREAM_CHANGES,
        )
        assert result.merged is not None
        assert result.merged["description"] == "Shared change."

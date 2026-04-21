"""Merge brief generator: structured output for agent mediation."""

from tripwire.core.merge_brief import (
    MergeType,
    build_merge_brief,
    delete_merge_brief,
    list_pending_briefs,
    load_merge_brief,
    save_merge_brief,
)


def _node_dict(**overrides):
    base = {
        "id": "n",
        "name": "Name",
        "description": "base description",
        "related_to": ["a"],
    }
    base.update(overrides)
    return base


class TestBuildBrief:
    def test_brief_contains_base_ours_theirs(self):
        base = _node_dict()
        ours = _node_dict(description="ours desc")
        theirs = _node_dict(description="theirs desc")
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc123",
            base=base,
            ours=ours,
            theirs=theirs,
        )
        assert brief.node_id == "n"
        assert brief.base_sha == "abc123"
        assert brief.base_version == base
        assert brief.ours_version == ours
        assert brief.theirs_version == theirs

    def test_field_diff_conflict_status(self):
        base = _node_dict(related_to=["a"])
        ours = _node_dict(description="ours", related_to=["a", "b"])
        theirs = _node_dict(description="theirs", related_to=["a", "c"])
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc",
            base=base,
            ours=ours,
            theirs=theirs,
        )
        by_field = {d.field: d.status for d in brief.field_diffs}
        assert by_field["description"] == "conflict"
        assert by_field["related_to"] == "conflict"

    def test_field_diff_ours_only(self):
        base = _node_dict()
        ours = _node_dict(description="ours only")
        theirs = _node_dict()  # unchanged
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc",
            base=base,
            ours=ours,
            theirs=theirs,
        )
        by_field = {d.field: d.status for d in brief.field_diffs}
        assert by_field["description"] == "ours_only"

    def test_field_diff_theirs_only(self):
        base = _node_dict()
        ours = _node_dict()
        theirs = _node_dict(description="theirs only")
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc",
            base=base,
            ours=ours,
            theirs=theirs,
        )
        by_field = {d.field: d.status for d in brief.field_diffs}
        assert by_field["description"] == "theirs_only"

    def test_generates_hints_on_conflict(self):
        base = _node_dict()
        ours = _node_dict(description="ours")
        theirs = _node_dict(description="theirs")
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc",
            base=base,
            ours=ours,
            theirs=theirs,
        )
        assert len(brief.hints) > 0


class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc",
            base=_node_dict(),
            ours=_node_dict(description="o"),
            theirs=_node_dict(description="t"),
        )
        save_merge_brief(tmp_path, brief)
        loaded = load_merge_brief(tmp_path, "n")
        assert loaded is not None
        assert loaded.node_id == "n"
        assert loaded.base_sha == "abc"
        assert loaded.merge_type is MergeType.PULL

    def test_delete_brief(self, tmp_path):
        brief = build_merge_brief(
            node_id="n",
            merge_type=MergeType.PULL,
            base_sha="abc",
            base=_node_dict(),
            ours=_node_dict(description="o"),
            theirs=_node_dict(description="t"),
        )
        save_merge_brief(tmp_path, brief)
        delete_merge_brief(tmp_path, "n")
        assert load_merge_brief(tmp_path, "n") is None

    def test_list_pending_briefs(self, tmp_path):
        for nid in ("a", "b", "c"):
            save_merge_brief(
                tmp_path,
                build_merge_brief(
                    node_id=nid,
                    merge_type=MergeType.PULL,
                    base_sha="abc",
                    base=_node_dict(id=nid),
                    ours=_node_dict(id=nid, description="o"),
                    theirs=_node_dict(id=nid, description="t"),
                ),
            )
        pending = list_pending_briefs(tmp_path)
        assert sorted(pending) == ["a", "b", "c"]

    def test_list_pending_empty_dir(self, tmp_path):
        assert list_pending_briefs(tmp_path) == []

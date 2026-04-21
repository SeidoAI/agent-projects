"""Insights model + store."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from tripwire.core.insights_store import (
    load_insights,
    record_rejection,
    rejected_path,
    save_insights,
)
from tripwire.models.insights import InsightsFile, NodeProposal


def test_new_node_proposal_requires_name_and_body():
    with pytest.raises(ValidationError):
        NodeProposal(
            kind="new_node",
            id="x",
            type="decision",
            # missing name + body
            rationale="r",
        )


def test_new_node_proposal_requires_type():
    with pytest.raises(ValidationError):
        NodeProposal(
            kind="new_node",
            id="pg-tuning",
            # missing type
            name="PG Tuning",
            body="notes",
            rationale="why",
        )


def test_update_node_proposal_requires_delta():
    with pytest.raises(ValidationError):
        NodeProposal(
            kind="update_node",
            id="x",
            # missing delta
            rationale="r",
        )


def test_new_node_proposal_valid():
    p = NodeProposal(
        kind="new_node",
        id="pg-tuning",
        type="decision",
        name="PG Tuning",
        body="notes",
        rationale="why",
    )
    assert p.body == "notes"
    assert p.type == "decision"
    assert p.delta is None


def test_update_node_proposal_valid():
    p = NodeProposal(
        kind="update_node",
        id="auth-system",
        delta="added refresh token rotation",
        rationale="security update",
    )
    assert p.delta is not None
    assert p.body is None


def test_insights_file_roundtrip(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1")

    insights = InsightsFile(
        proposals=[
            NodeProposal(
                kind="new_node",
                id="pg-vacuum",
                type="decision",
                name="PG VACUUM tuning",
                body="tuning notes",
                related=["database"],
                rationale="worth elevating",
            ),
        ]
    )
    save_insights(tmp_path_project, "s1", insights)

    loaded = load_insights(tmp_path_project, "s1")
    assert len(loaded.proposals) == 1
    assert loaded.proposals[0].id == "pg-vacuum"
    assert loaded.proposals[0].related == ["database"]


def test_load_insights_missing_returns_empty(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1")
    loaded = load_insights(tmp_path_project, "s1")
    assert loaded.proposals == []


def test_record_rejection(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1")
    record_rejection(tmp_path_project, "s1", "some-proposal", "too vague")
    record_rejection(tmp_path_project, "s1", "other", "duplicate")

    path = rejected_path(tmp_path_project, "s1")
    assert path.is_file()

    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(data["rejected"]) == 2
    assert data["rejected"][0]["id"] == "some-proposal"
    assert data["rejected"][0]["reason"] == "too vague"

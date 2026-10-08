import pytest
from test_workspace_api import create_workspace, send

from app.errors import ConflictError
from app.services.proposal_lifecycle import APPLY, REJECT, UNDO, should_execute_transition


@pytest.mark.parametrize(
    ("status", "transition", "expected"),
    [
        ("pending", APPLY, True),
        ("applied", APPLY, False),
        ("pending", REJECT, True),
        ("rejected", REJECT, False),
        ("applied", UNDO, True),
        ("undone", UNDO, False),
    ],
)
def test_transition_runs_once_and_replays_terminal_receipts(status, transition, expected):
    assert should_execute_transition(
        status, transition, conflict_message="not available"
    ) is expected


@pytest.mark.parametrize(
    ("status", "transition"),
    [
        ("rejected", APPLY),
        ("failed", APPLY),
        ("applied", REJECT),
        ("pending", UNDO),
    ],
)
def test_transition_rejects_illegal_state_without_side_effect(status, transition):
    with pytest.raises(ConflictError, match="not available"):
        should_execute_transition(status, transition, conflict_message="not available")


def test_asset_proposal_apply_replay_returns_original_receipt_without_second_topic(app):
    workspace = create_workspace(app)
    agent = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
        if item["agentId"] == "creator_material_curator"
    )
    conversation = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"]},
    ).json()
    send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "帮我新增一个选题：只应创建一次"},
    )
    proposal = next(
        item
        for item in send(
            app,
            "GET",
            f"/api/agent-conversations/{conversation['id']}/asset-proposals",
        ).json()
        if item["actionType"] == "topic.create_or_update"
    )

    first = send(app, "POST", f"/api/asset-proposals/{proposal['id']}/apply")
    second = send(app, "POST", f"/api/asset-proposals/{proposal['id']}/apply")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    topics = send(app, "GET", f"/api/workspaces/{workspace['id']}/topics").json()
    assert [item["title"] for item in topics] == ["帮我新增一个选题：只应创建一次"]


def test_asset_proposal_reject_replay_returns_original_receipt(app):
    workspace = create_workspace(app)
    agent = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
        if item["agentId"] == "creator_material_curator"
    )
    conversation = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"]},
    ).json()
    send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "帮我新增一个选题：不要采用"},
    )
    proposal = next(
        item
        for item in send(
            app,
            "GET",
            f"/api/agent-conversations/{conversation['id']}/asset-proposals",
        ).json()
        if item["actionType"] == "topic.create_or_update"
    )

    first = send(app, "POST", f"/api/asset-proposals/{proposal['id']}/reject")
    second = send(app, "POST", f"/api/asset-proposals/{proposal['id']}/reject")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert send(app, "GET", f"/api/workspaces/{workspace['id']}/topics").json() == []

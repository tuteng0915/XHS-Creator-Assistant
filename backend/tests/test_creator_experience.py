import asyncio
import json

import pytest
from test_workspace_api import create_workspace, request, send

from app.errors import ValidationError
from app.models import ModelCallResponse, SimulationRunCreate
from app.services.agent_conversations import RealAgentConversationModelProvider
from app.services.audience_analyses import AudienceAnalysisCreate, AudienceResult


def topic(app, workspace_id, title="选题"):
    return send(app, "POST", f"/api/workspaces/{workspace_id}/topics", json={"title": title}).json()


def profile(app, workspace_id):
    return send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/source-materials",
        json={
            "type": "xhs_creator_profile",
            "name": "主页",
            "content": json.dumps(
                {
                    "schemaVersion": "xhs-creator-profile/v1",
                    "creator": {"displayName": "创作者"},
                    "notes": [
                        {
                            "noteId": str(i),
                            "title": "留学体验",
                            "desc": "真实经历",
                            "comments": [{"content": "想了解申请费用"}],
                        }
                        for i in range(12)
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ).json()


def test_topic_body_pin_and_edit_conflict(app):
    wid = create_workspace(app)["id"]
    first, second = topic(app, wid, "早期选题"), topic(app, wid, "近期选题")
    patched = send(
        app,
        "PATCH",
        f"/api/topics/{first['id']}",
        json={
            "body": "中文正文\n原样保存🌱",
            "pinned": True,
            "expectedUpdatedAt": first["updatedAt"],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["body"] == "中文正文\n原样保存🌱"
    assert patched.json()["generatedSnapshot"] == first["generatedSnapshot"]
    assert send(app, "GET", f"/api/workspaces/{wid}/topics").json()[0]["id"] == first["id"]
    assert (
        send(
            app,
            "PATCH",
            f"/api/topics/{first['id']}",
            json={
                "body": "过时修改",
                "expectedUpdatedAt": first["updatedAt"],
            },
        ).status_code
        == 409
    )
    assert second["body"] == ""


def test_account_creation_requires_valid_submission_and_reuses_job(app, monkeypatch):
    service = app.state.xhs_capture_service
    scheduled = []
    monkeypatch.setattr(service, "_schedule", scheduled.append)
    before = len(send(app, "GET", "/api/workspaces").json())
    assert (
        send(
            app, "POST", "/api/creator-accounts/import", json={"profileUrl": "https://example.com"}
        ).status_code
        == 422
    )
    assert len(send(app, "GET", "/api/workspaces").json()) == before
    payload = {"profileUrl": "https://www.xiaohongshu.com/user/profile/5d2aefea0000000010004907"}
    created = send(app, "POST", "/api/creator-accounts/import", json=payload)
    assert created.status_code == 201
    repeated = send(app, "POST", "/api/creator-accounts/import", json=payload)
    assert repeated.json()["id"] == created.json()["id"]
    assert len(scheduled) == 1
    assert len(send(app, "GET", "/api/workspaces").json()) == before + 1


def audience_output():
    return {
        "summary": "四类样本受众",
        "limitations": "评论样本不代表真实粉丝构成",
        "groups": [
            {
                "id": str(i),
                "name": f"分组{i}",
                "profile": "关注申请规划",
                "coreConcern": "费用",
                "estimatedPercent": value,
                "evidence": ["想了解申请费用"],
            }
            for i, value in enumerate([10, 40, 20, 30])
        ],
    }


def test_audience_validation():
    result = AudienceResult.model_validate(audience_output())
    assert [g.estimated_percent for g in result.groups] == [40, 30, 20, 10]
    bad = audience_output()
    bad["groups"][0]["estimatedPercent"] = 99
    with pytest.raises(ValueError):
        AudienceResult.model_validate(bad)


def test_audience_persistence_scope_and_simulation_top_three(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    selected_topic = topic(app, wid)
    service = app.state.audience_analysis_service

    class Model:
        calls = 0

        async def call_operation(self, operation, context):
            self.calls += 1
            assert len(context["notes"]) == 10
            return ModelCallResponse(output=audience_output(), model_metadata={"model": "test"})

    model = Model()
    service.model_call_service = model

    async def exercise():
        payload = AudienceAnalysisCreate(source_material_id=source["id"])
        created = service.create(wid, payload)
        duplicate = service.create(wid, payload)
        assert duplicate.id == created.id
        await asyncio.gather(*list(service.tasks.values()))
        loaded = service.get(created.id)
        assert loaded.status == "completed"
        assert loaded.input_snapshot["scope"]["selectedNoteCount"] == 10
        assert model.calls == 1
        return created.id

    run_id = asyncio.run(exercise())
    run = app.state.simulation_service.create(
        wid,
        SimulationRunCreate(
            topic_id=selected_topic["id"], audience_analysis_id=run_id, mode="live"
        ),
    )
    assert [p["id"] for p in run.input_snapshot["audiencePersonas"]] == ["1", "3", "2"]
    other = create_workspace(app)["id"]
    with pytest.raises(ValidationError):
        app.state.simulation_service.create(
            other, SimulationRunCreate(manual_topic="不应跨账号读取", audience_analysis_id=run_id)
        )
    assert send(app, "GET", f"/api/workspaces/{other}/audience-analyses").json() == []


def test_audience_restart_marks_interrupted_failed(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    service = app.state.audience_analysis_service
    with service.database.transaction() as c:
        c.execute(
            "INSERT INTO audience_analyses(id,workspace_id,source_material_id,status,"
            "input_snapshot_json,created_at) VALUES('interrupted',?,?,'running','{}','now')",
            (wid, source["id"]),
        )
    service.resume()
    assert service.get("interrupted").status == "failed"


@pytest.mark.parametrize("conflict", [False, True])
def test_canvas_live_context_persistence_and_conflict(app, conflict):
    wid = create_workspace(app)["id"]
    selected = topic(app, wid)
    agents = send(app, "GET", f"/api/workspaces/{wid}/agents").json()
    agent = next(a for a in agents if a["agentId"] == "topic_draft_editor")
    payload = {
        "agentAssetId": agent["id"],
        "contextTarget": {"assetType": "topic", "assetId": selected["id"]},
    }
    created = send(app, "POST", f"/api/workspaces/{wid}/agent-conversations", json=payload).json()
    assert "id" in created, created
    assert (
        send(app, "POST", f"/api/workspaces/{wid}/agent-conversations", json=payload).json()["id"]
        == created["id"]
    )

    class Model:
        async def call_operation(self, operation, context):
            assert operation.value == "creator_edit"
            assert context["topic"]["id"] == selected["id"]
            if conflict:
                app.state.topic_service.update(
                    selected["id"],
                    __import__("app.models", fromlist=["TopicUpdate"]).TopicUpdate(
                        body="用户的新修改", expected_updated_at=selected["updatedAt"]
                    ),
                )
            return ModelCallResponse(
                output={"reply": "已调整开头", "update": {"title": "新标题", "body": "AI 正文"}},
                model_metadata={},
            )

    service = app.state.agent_conversation_service
    service.live_provider = RealAgentConversationModelProvider(Model())

    async def exercise():
        response = await request(
            app,
            "POST",
            f"/api/agent-conversations/{created['id']}/messages",
            json={"content": "修改开头", "mode": "live", "clientMessageKey": "canvas-1"},
        )
        assert response.status_code == 200
        if service._tasks:
            await asyncio.gather(*list(service._tasks.values()))

    asyncio.run(exercise())
    stored = app.state.topic_service.get(selected["id"])
    assert stored.body == ("用户的新修改" if conflict else "AI 正文")
    history = service.get(created["id"])
    assert history.messages[-1].model_metadata["canvasApplyStatus"] == (
        "conflict" if conflict else "applied"
    )
    assert history.messages[-1].model_metadata["canvasUpdate"]["body"] == "AI 正文"

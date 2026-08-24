import asyncio
import json

from fastapi import FastAPI
from test_workspace_api import create_workspace, send


def create_text_material(
    app: FastAPI, workspace_id: str, material_type: str, content: str
) -> dict:
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/source-materials",
        json={"type": material_type, "name": material_type, "content": content},
    )
    assert response.status_code == 201
    return response.json()


def create_completed_topic_from_account_run(app: FastAPI) -> tuple[dict, dict]:
    workspace = create_workspace(app)
    historical = create_text_material(
        app,
        workspace["id"],
        "historical_posts",
        "二本逆袭G5?别再被这种标题骗了｜赞1.4k 藏980｜爆",
    )
    comments = create_text_material(
        app,
        workspace["id"],
        "comments",
        "中介那部分太真实了，我现在就纠结要不要DIY。",
    )
    run_response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
            "mode": "demo",
        },
    )
    assert run_response.status_code == 201
    run = run_response.json()
    asyncio.run(app.state.account_workflow_service.collect_events(run["id"]))
    completed_run = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    candidate = completed_run["stageResults"]["topics"]["topics"][0]
    topic_response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/topics",
        json={
            "title": candidate["title"],
            "angle": candidate["angle"],
            "associatedPainPoint": candidate["pain"],
            "whyItFits": candidate["whyFit"],
            "sourceAnalysisRunId": completed_run["id"],
        },
    )
    assert topic_response.status_code == 201
    return workspace, topic_response.json()


def test_generate_draft_from_topic_persists_snapshots(app: FastAPI) -> None:
    workspace, topic = create_completed_topic_from_account_run(app)

    response = send(
        app,
        "POST",
        f"/api/topics/{topic['id']}/drafts/generate",
        json={"mode": "demo"},
    )

    assert response.status_code == 201
    draft = response.json()
    assert draft["workspaceId"] == workspace["id"]
    assert draft["topicId"] == topic["id"]
    assert draft["kind"] == "content_structure"
    assert draft["sourceAnalysisRunId"] == topic["sourceAnalysisRunId"]
    assert draft["status"] == "completed"
    assert draft["generatedSnapshot"]["structure"]["topicChosen"] == topic["title"]
    assert draft["editableContent"] == draft["generatedSnapshot"]
    assert draft["inputSnapshot"]["topic"]["sourceAnalysisRunId"] == topic[
        "sourceAnalysisRunId"
    ]
    assert "voiceFingerprint" in draft["inputSnapshot"]["analysisContext"]

    history = send(app, "GET", f"/api/workspaces/{workspace['id']}/drafts")
    assert history.status_code == 200
    assert history.json()[0]["id"] == draft["id"]


def test_generate_content_brief_from_topic_persists_as_draft_kind(
    app: FastAPI,
) -> None:
    workspace, topic = create_completed_topic_from_account_run(app)

    response = send(
        app,
        "POST",
        f"/api/topics/{topic['id']}/briefs/generate",
        json={"mode": "demo"},
    )

    assert response.status_code == 201
    brief = response.json()
    assert brief["workspaceId"] == workspace["id"]
    assert brief["topicId"] == topic["id"]
    assert brief["kind"] == "content_brief"
    assert brief["status"] == "completed"
    assert brief["generatedSnapshot"]["brief"]["topicTitle"] == topic["title"]
    assert brief["editableContent"] == brief["generatedSnapshot"]
    assert brief["modelMetadata"]["kind"] == "content_brief"

    edited_content = {
        **brief["editableContent"],
        "brief": {
            **brief["editableContent"]["brief"],
            "corePoint": "用户确认后的核心观点",
        },
    }
    updated = send(
        app,
        "PATCH",
        f"/api/drafts/{brief['id']}",
        json={
            "editableContent": edited_content,
            "expectedUpdatedAt": brief["updatedAt"],
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["editableContent"]["brief"]["corePoint"] == "用户确认后的核心观点"
    assert body["generatedSnapshot"]["brief"]["corePoint"] == brief["generatedSnapshot"][
        "brief"
    ]["corePoint"]

    history = send(app, "GET", f"/api/workspaces/{workspace['id']}/drafts")
    assert {item["kind"] for item in history.json()} == {"content_brief"}


def test_generate_structure_from_content_brief_uses_brief_snapshot(
    app: FastAPI,
) -> None:
    _workspace, topic = create_completed_topic_from_account_run(app)
    brief = send(
        app,
        "POST",
        f"/api/topics/{topic['id']}/briefs/generate",
        json={"mode": "demo"},
    ).json()

    response = send(
        app,
        "POST",
        f"/api/drafts/{brief['id']}/structure/generate",
        json={"mode": "demo"},
    )

    assert response.status_code == 201
    structure = response.json()
    assert structure["kind"] == "content_structure"
    assert structure["topicId"] == topic["id"]
    assert structure["inputSnapshot"]["sourceBrief"]["draftId"] == brief["id"]
    assert structure["inputSnapshot"]["sourceBrief"]["editableContent"]["brief"][
        "topicTitle"
    ] == topic["title"]
    assert structure["modelMetadata"]["sourceBriefDraftId"] == brief["id"]
    assert structure["generatedSnapshot"]["structure"]["topicChosen"] == topic["title"]


def test_update_draft_edits_current_content_not_generated_snapshot(
    app: FastAPI,
) -> None:
    _workspace, topic = create_completed_topic_from_account_run(app)
    draft = send(
        app,
        "POST",
        f"/api/topics/{topic['id']}/drafts/generate",
        json={"mode": "demo"},
    ).json()
    edited_content = {
        **draft["editableContent"],
        "structure": {
            **draft["editableContent"]["structure"],
            "reuse": "用户手动改写后的复用结构",
        },
    }

    updated = send(
        app,
        "PATCH",
        f"/api/drafts/{draft['id']}",
        json={
            "editableContent": edited_content,
            "expectedUpdatedAt": draft["updatedAt"],
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["editableContent"]["structure"]["reuse"] == "用户手动改写后的复用结构"
    assert body["generatedSnapshot"]["structure"]["reuse"] == draft["generatedSnapshot"][
        "structure"
    ]["reuse"]


def test_simulation_can_start_from_draft_snapshot(app: FastAPI) -> None:
    workspace, topic = create_completed_topic_from_account_run(app)
    draft = send(
        app,
        "POST",
        f"/api/topics/{topic['id']}/drafts/generate",
        json={"mode": "demo"},
    ).json()

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/simulation-runs",
        json={"draftId": draft["id"], "mode": "demo"},
    )

    assert created.status_code == 201
    simulation = created.json()
    assert simulation["topicId"] == topic["id"]
    assert simulation["draftId"] == draft["id"]
    assert simulation["inputSnapshot"]["targetType"] == "draft"
    assert simulation["inputSnapshot"]["draft"]["draftId"] == draft["id"]

    graph_state = app.state.simulation_workflow_service.initial_state_for_run(
        simulation["id"]
    )
    graph_topic_json = json.dumps(graph_state["topic"], ensure_ascii=False)
    assert "editableContent" in graph_state["topic"]["draft"]
    assert "generatedSnapshot" not in graph_topic_json
    assert "updatedAt" not in graph_topic_json

    asyncio.run(app.state.simulation_workflow_service.collect_events(simulation["id"]))
    completed = send(app, "GET", f"/api/simulation-runs/{simulation['id']}").json()
    assert completed["status"] == "completed"
    assert completed["inputSnapshot"]["draft"]["editableContent"]["structure"][
        "topicChosen"
    ] == topic["title"]

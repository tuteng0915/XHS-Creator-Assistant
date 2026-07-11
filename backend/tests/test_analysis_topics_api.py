import pytest
from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.errors import ConflictError
from app.models import AnalysisRunStatus, AnalysisRunTransition, AnalysisStageUpdate


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


def test_account_analysis_run_lifecycle_preserves_input_snapshot(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    historical = create_text_material(
        app,
        workspace["id"],
        "historical_posts",
        "二本逆袭G5？别再被这种标题骗了｜赞1.4k 藏980｜爆",
    )
    comments = create_text_material(
        app,
        workspace["id"],
        "comments",
        "中介那部分太真实了，我现在就纠结要不要DIY。",
    )

    created = send(
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
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "pending"
    assert "纠结要不要DIY" in run["inputSnapshot"]["comments"]["content"]
    context_pack = run["inputSnapshot"]["contextPack"]
    assert context_pack["mode"] == "workspace_pack"
    assert context_pack["scope"] == "broad"
    assert context_pack["requester"]["workflowId"] == "account_diagnosis"
    item_keys = {item["key"] for item in context_pack["items"]}
    assert {
        "account_profile",
        "source_materials_overview",
        "analysis_history_overview",
        "topic_library_overview",
        "draft_history_overview",
        "simulation_history_overview",
        "selected_historical_posts",
        "selected_comment_samples",
    }.issubset(item_keys)
    comment_item = next(
        item for item in context_pack["items"] if item["key"] == "selected_comment_samples"
    )
    assert "纠结要不要DIY" in comment_item["text"]
    assert context_pack["snapshot"]["contentHash"]

    updated_comments = send(
        app,
        "PATCH",
        f"/api/source-materials/{comments['id']}",
        json={
            "content": "后续编辑不应改写历史快照。",
            "expectedUpdatedAt": comments["updatedAt"],
        },
    )
    assert updated_comments.status_code == 200

    stage = app.state.analysis_service.update_stage(
        run["id"],
        "profile",
        AnalysisStageUpdate(
            status=AnalysisRunStatus.COMPLETED,
            result={"profile": {"pillars": ["留学决策"]}},
            model_metadata={"mode": "demo"},
        ),
    )
    stage_json = stage.model_dump(mode="json", by_alias=True)
    assert stage_json["status"] == "running"
    assert stage_json["stageResults"]["profile"]["profile"]["pillars"] == [
        "留学决策"
    ]

    completed = app.state.analysis_service.transition(
        run["id"],
        AnalysisRunTransition(
            status=AnalysisRunStatus.COMPLETED,
            model_metadata={"mode": "demo"},
        ),
    )
    completed_json = completed.model_dump(mode="json", by_alias=True)
    assert completed_json["completedAt"] is not None
    assert "纠结要不要DIY" in completed_json["inputSnapshot"]["comments"]["content"]

    with pytest.raises(ConflictError, match="Completed analysis runs are immutable"):
        app.state.analysis_service.update_stage(
            run["id"],
            "topics",
            AnalysisStageUpdate(
                status=AnalysisRunStatus.COMPLETED,
                result={"topics": []},
            ),
        )


def test_internal_execution_mutation_and_model_call_routes_are_not_public(
    app: FastAPI,
) -> None:
    patch_run = send(
        app,
        "PATCH",
        "/api/analysis-runs/not-public",
        json={"status": "completed"},
    )
    assert patch_run.status_code == 405

    put_stage = send(
        app,
        "PUT",
        "/api/analysis-runs/not-public/stages/profile",
        json={"status": "completed", "result": {}},
    )
    assert put_stage.status_code == 404

    model_call = send(
        app,
        "POST",
        "/api/model-calls",
        json={"operation": "profile", "context": {}},
    )
    assert model_call.status_code == 404


def test_trend_analysis_snapshot_reads_server_stored_csv(app: FastAPI) -> None:
    workspace = create_workspace(app)
    csv_content = (
        "标题,点赞,收藏,标签\n"
        "普通人如何开始数字游民,45,57,#远程工作\n"
    ).encode()
    upload = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials/trend-csv",
        data={"name": "数字游民热帖", "keyword": "数字游民"},
        files={"file": ("trend.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 201
    material = upload.json()

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "trend_analysis",
            "trendCsvMaterialId": material["id"],
            "mode": "demo",
        },
    )
    assert created.status_code == 201
    snapshot = created.json()["inputSnapshot"]
    assert snapshot["trendCsv"]["keyword"] == "数字游民"
    assert snapshot["trendCsv"]["ranking"] == {
        "method": "likes_plus_collects_desc",
        "limit": 50,
    }
    assert snapshot["trendCsv"]["rankedPosts"][0]["title"] == "普通人如何开始数字游民"
    assert "rawText" not in snapshot["trendCsv"]
    context_pack = snapshot["contextPack"]
    assert context_pack["mode"] == "workspace_pack"
    assert context_pack["requester"]["workflowId"] == "trend_analysis"
    ranked_item = next(
        item
        for item in context_pack["items"]
        if item["key"] == "selected_trend_top_ranked_posts"
    )
    assert ranked_item["data"]["rankedPosts"][0]["title"] == "普通人如何开始数字游民"
    assert "rawText" not in ranked_item["data"]


def test_topic_library_create_select_edit_archive(app: FastAPI) -> None:
    workspace = create_workspace(app)
    historical = create_text_material(app, workspace["id"], "historical_posts", "爆款")
    comments = create_text_material(app, workspace["id"], "comments", "痛点")
    run = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
        },
    ).json()

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/topics",
        json={
            "title": "5万块中介费，该花的是这3步",
            "angle": "拆分外包环节",
            "associatedPainPoint": "DIY vs 中介",
            "whyItFits": "延续账号避坑拆解风格",
            "sourceAnalysisRunId": run["id"],
        },
    )
    assert created.status_code == 201
    topic = created.json()
    assert topic["sourceWorkflow"] == "account_diagnosis"
    assert topic["generatedSnapshot"]["title"] == "5万块中介费，该花的是这3步"

    selected = send(app, "POST", f"/api/topics/{topic['id']}/select")
    assert selected.status_code == 200
    assert selected.json()["status"] == "selected"
    assert (
        send(app, "GET", f"/api/workspaces/{workspace['id']}").json()[
            "currentTopicId"
        ]
        == topic["id"]
    )

    edited = send(
        app,
        "PATCH",
        f"/api/topics/{topic['id']}",
        json={
            "title": "中介费到底该花在哪三步",
            "angle": "按环节配置预算",
            "expectedUpdatedAt": selected.json()["updatedAt"],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["angle"] == "按环节配置预算"
    assert edited.json()["generatedSnapshot"] == topic["generatedSnapshot"]

    archived = send(app, "POST", f"/api/topics/{topic['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

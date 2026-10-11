import asyncio
import json
from copy import deepcopy

import pytest
from fastapi import FastAPI
from test_account_profile_check import expected_source_led_display, source_led_model_output
from test_workspace_api import create_workspace, send

from app.workflows.account_diagnosis import (
    ACCOUNT_GRAPH_NODE_ORDER,
    FakeAccountDiagnosisModelProvider,
)


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


def create_account_run(app: FastAPI, mode: str = "demo") -> dict:
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
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
            "mode": mode,
        },
    )
    assert response.status_code == 201
    return response.json()


def collect(app: FastAPI, run_id: str, stop_after_node: str | None = None) -> list[dict]:
    return asyncio.run(
        app.state.account_workflow_service.collect_events(
            run_id, stop_after_node=stop_after_node
        )
    )


def test_account_graph_state_keeps_full_source_material_outside_state(
    app: FastAPI,
) -> None:
    run = create_account_run(app)

    assert ACCOUNT_GRAPH_NODE_ORDER == [
        "profile_analysis",
        "topic_generation",
        "finalize",
    ]
    state = app.state.account_workflow_service.initial_state_for_run(run["id"])

    assert state["historical_posts_material_id"] == run["inputSnapshot"][
        "historicalPosts"
    ]["materialId"]
    assert state["comments_material_id"] == run["inputSnapshot"]["comments"][
        "materialId"
    ]
    assert "二本逆袭" not in json.dumps(state, ensure_ascii=False)
    assert "纠结要不要DIY" not in json.dumps(state, ensure_ascii=False)


def test_fake_account_graph_routes_and_persists_successful_stages(
    app: FastAPI,
) -> None:
    run = create_account_run(app)
    events = collect(app, run["id"])

    event_types = [event["data"]["eventType"] for event in events]
    assert event_types.count("stage.succeeded") == 3
    assert event_types[-1] == "run.succeeded"
    assert all(
        {"eventId", "runId", "runType", "stageKey", "status", "sequence", "occurredAt", "data"}
        <= set(event)
        for event in events
    )

    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["stageResults"]["profile"]["profile"]["pillars"]
    assert completed["stageResults"]["pain_points"]["painPoints"]
    assert completed["stageResults"]["topics"]["topics"][0]["title"]
    assert "structure" not in completed["stageResults"]

    topics = send(
        app, "GET", f"/api/workspaces/{run['workspaceId']}/topics"
    ).json()
    assert len(topics) == 2
    assert topics[0]["sourceAnalysisRunId"] == run["id"]
    assert topics[0]["sourceWorkflow"] == "account_diagnosis"
    assert topics[0]["status"] == "candidate"
    assert topics[0]["title"]

    duplicate = send(
        app,
        "POST",
        f"/api/workspaces/{run['workspaceId']}/topics",
        json={
            "title": topics[0]["title"],
            "angle": "重复保存不应新增",
            "sourceAnalysisRunId": run["id"],
        },
    )
    assert duplicate.status_code == 201
    topics_after_duplicate_save = send(
        app, "GET", f"/api/workspaces/{run['workspaceId']}/topics"
    ).json()
    assert len(topics_after_duplicate_save) == 2


def test_parallel_stage_failure_allows_partial_account_result(app: FastAPI) -> None:
    run = create_account_run(app)
    app.state.account_workflow_service.fake_provider = FakeAccountDiagnosisModelProvider(
        failures={"profile"}
    )

    events = collect(app, run["id"])

    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "profile"
        for event in events
    )
    assert events[-1]["data"]["eventType"] == "run.partial"
    partial = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert partial["status"] == "partially_completed"
    assert "profile" in partial["stageErrors"]
    assert "pain_points" in partial["stageResults"]
    assert "topics" in partial["stageResults"]


def test_account_graph_restart_resumes_from_persisted_stage_results(
    app: FastAPI,
) -> None:
    run = create_account_run(app)
    provider = FakeAccountDiagnosisModelProvider()
    app.state.account_workflow_service.fake_provider = provider

    first_events = collect(app, run["id"], stop_after_node="profile_analysis")
    interrupted = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert interrupted["status"] == "running"
    assert "profile" in interrupted["stageResults"]
    assert "pain_points" in interrupted["stageResults"]
    assert first_events[-1]["data"]["eventType"] == "stage.succeeded"

    restarted_provider = FakeAccountDiagnosisModelProvider()
    app.state.account_workflow_service.fake_provider = restarted_provider
    second_events = collect(app, run["id"])

    assert "profile" not in restarted_provider.calls
    assert "pain_points" not in restarted_provider.calls
    assert restarted_provider.calls == ["topics"]
    assert second_events[-1]["data"]["eventType"] == "run.succeeded"
    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"


def test_live_account_graph_uses_injectable_provider_and_validates_output(
    app: FastAPI,
) -> None:
    class InvalidProvider(FakeAccountDiagnosisModelProvider):
        async def topics(self, **kwargs):
            self.calls.append("topics")
            return {"topics": [{"angle": "缺少 title"}], "titles": []}

    run = create_account_run(app, mode="live")
    provider = InvalidProvider()
    app.state.account_workflow_service.live_provider = provider

    events = collect(app, run["id"])

    assert provider.calls == ["profile", "pain_points", "topics"]
    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "topics"
        for event in events
    )
    result = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert result["status"] == "partially_completed"
    assert result["stageErrors"]["topics"] == "Model response failed structured validation"


def create_source_led_account_run(app):
    workspace = create_workspace(app)
    profile = create_text_material(app, workspace["id"], "xhs_creator_profile", json.dumps({
        "schemaVersion": "xhs-creator-profile/v1", "creator": {"displayName": "测试账号"},
        "notes": [
            {"noteId": "11", "title": "真实标题", "desc": "先准备材料，再逐项核对。"},
            {"noteId": "outside-selection", "title": "未选标题", "desc": "不能读取的另一篇"},
        ],
    }, ensure_ascii=False))
    response = send(app, "POST", f"/api/workspaces/{workspace['id']}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": profile["id"],
        "selectedNoteIds": ["11"], "mode": "live",
    })
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("legacy", [False, True])
def test_live_account_profile_compiles_source_readings_to_legacy_display_and_keeps_raw(app, legacy):
    formulas, takeaways = expected_source_led_display()
    output = ({"profile": {"titleFormulas": formulas, "contrast": {"takeaways": takeaways}}}
              if legacy else source_led_model_output())
    before = deepcopy(output)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            self.calls.append("profile")
            return output

    run = create_source_led_account_run(app)
    provider = Provider()
    app.state.account_workflow_service.live_provider = provider
    events = collect(app, run["id"])
    result = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert result["status"] == "completed"
    assert provider.calls.count("profile") == 1
    profile = result["stageResults"]["profile"]["profile"]
    assert profile["titleFormulas"] == formulas
    assert profile["contrast"]["takeaways"] == takeaways
    assert not {"reportFormat", "titleReadings", "nextMoves"} & profile.keys()
    succeeded = [event for event in events if event["stageKey"] == "profile"
                 and event["data"]["eventType"] == "stage.succeeded"]
    assert len(succeeded) == 1
    assert output == before


@pytest.mark.parametrize("problem", ["title_fragment", "wrong_source", "body_quote"])
def test_live_account_profile_bad_source_readings_never_persist_completed_profile(app, problem):
    output = source_led_model_output()
    if problem == "title_fragment":
        output["profile"]["titleReadings"][0]["parts"][0]["text"] = "新加的标题成分"
    elif problem == "wrong_source":
        # This note exists in the workspace but is deliberately outside the frozen subset.
        output["profile"]["titleReadings"][0]["noteId"] = "outside-selection"
    else:
        output["profile"]["nextMoves"][0]["sourceQuote"] = "原文没有的引用"
    before = deepcopy(output)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            self.calls.append("profile")
            return output

    run = create_source_led_account_run(app)
    provider = Provider()
    app.state.account_workflow_service.live_provider = provider
    events = collect(app, run["id"])
    result = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert provider.calls.count("profile") == 1
    assert result["status"] != "completed"
    assert "profile" not in result["stageResults"] and "profile" in result["stageErrors"]
    assert not any(event["stageKey"] == "profile"
                   and event["data"]["eventType"] == "stage.succeeded" for event in events)
    assert output == before


def test_live_profile_v3_persists_structural_metadata_and_exact_expression_quotes(app):
    workspace = create_workspace(app)
    source = create_text_material(app, workspace["id"], "xhs_creator_profile", json.dumps({
        "schemaVersion": "xhs-creator-profile/v1", "creator": {"displayName": "合成测试账号"},
        "notes": [
            {"noteId": "fictional-source", "title": "两种木块摆法",
             "desc": "左边摆成一排。右边围成圆圈。最后留出空位。"},
            {"noteId": "not-selected", "title": "未选的作品", "desc": "未选正文不应进入结构分析。"},
        ],
    }, ensure_ascii=False))
    run = send(app, "POST", f"/api/workspaces/{workspace['id']}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": source["id"],
        "selectedNoteIds": ["fictional-source"], "mode": "live",
    }).json()
    raw = {"profile": {"reportFormat": "source-led/v3", "structureReading": {
        "noteId": "n1", "kind": "comparison", "scope": "section", "scopeLabel": "两种摆法",
        "overview": "并列呈现两个摆放方案", "units": [
            {"label": "一排", "excerptIds": ["b1"], "reading": "展示左边的排列"},
            {"label": "圆圈", "excerptIds": ["b2"], "reading": "展示右边的排列"},
        ],
    }, "expressionReadings": [{
        "kind": "wording", "technique": "用动作说明形状", "application": "选择能看见动作的词",
        "examples": [{"noteId": "n1", "excerptId": "b2", "quote": "围成圆圈"}],
    }], "titleReadings": [], "nextMoves": []}}
    before = deepcopy(raw)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            self.calls.append("profile")
            return raw

    provider = Provider()
    app.state.account_workflow_service.live_provider = provider
    collect(app, run["id"])
    stored = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert stored["status"] == "completed"
    assert provider.calls.count("profile") == 1
    profile = stored["stageResults"]["profile"]["profile"]
    assert profile["viralStructure"] == {
        "name": "两种木块摆法", "kind": "comparison", "scope": "section", "scopeLabel": "两种摆法",
        "overview": "并列呈现两个摆放方案",
        "steps": ["一排：展示左边的排列", "圆圈：展示右边的排列"],
    }
    assert profile["hookStyles"] == []
    assert profile["voiceFingerprint"] == [
        "《两种木块摆法》的写法：用动作说明形状。原句：“围成圆圈”。借鉴方式：选择能看见动作的词",
    ]
    assert "未选正文" not in json.dumps(profile, ensure_ascii=False)
    assert raw == before


@pytest.mark.parametrize("source_id", ["n1", "n2"])
def test_lean_profile_candidate_roundtrips_note_sources_and_rejects_unselected_notes(
    app, source_id,
):
    raw = {"profile": {"reportFormat": "editorial/v1", "summary": {
        "text": "用具体动作说明整理过程", "noteIds": [source_id],
    }, "keywords": [{"text": "逐项核对", "noteIds": [source_id]}],
        "directions": [], "strengths": [], "writing": [],
        "nextSteps": [{"text": "下次整理可以继续围绕一次关键取舍展开", "noteIds": [source_id]}]}}
    before = deepcopy(raw)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            self.calls.append("profile")
            return raw

    run = create_source_led_account_run(app)
    provider = Provider()
    app.state.account_workflow_service.live_provider = provider
    collect(app, run["id"])
    stored = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert provider.calls.count("profile") == 1
    assert raw == before
    if source_id == "n2":
        assert "profile" in stored["stageErrors"]
        assert "profile" not in stored["stageResults"]
        return
    assert stored["status"] == "completed"
    portrait = stored["stageResults"]["profile"]["profile"]["accountPortrait"]
    assert portrait["summary"]["evidence"] == [{"noteId": "11", "scope": "note"}]
    assert portrait["nextSteps"][0] == {
        "statement": raw["profile"]["nextSteps"][0]["text"],
        "evidence": [{"noteId": "11", "scope": "note"}], "counterexamples": [],
    }
    # Re-reading the saved history does not regenerate a report or need the model.
    again = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert again["stageResults"] == stored["stageResults"]
    assert provider.calls.count("profile") == 1

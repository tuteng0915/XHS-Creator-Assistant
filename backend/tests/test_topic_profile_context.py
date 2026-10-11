import json
from copy import deepcopy

import pytest
from test_account_diagnosis_evidence import selected_snapshot
from test_account_langgraph_workflow import collect, create_account_run
from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, send

from app.services.account_diagnosis_evidence import topic_profile_context
from app.workflows.account_diagnosis import FakeAccountDiagnosisModelProvider

PROFILE = {
    "pillars": ["日常经历"],
    "voiceFingerprint": ["从具体处境讲起"],
    "accountPortrait": {"summary": {"statement": "生活记录"}},
    "contrast": {
        "winners": [{"title": "同名笔记", "metric": "收藏999；分享None"}],
        "losers": [{"title": "同名笔记", "metric": "点赞-1"}],
        "winFactors": ["收藏率30%导致推荐更多"],
        "loseFactors": ["分享率15%导致质量低"],
        "takeaways": ["先讲一个场景，再讲取舍。"],
        "extraModelMetric": 999,
    },
    "performanceObservations": {"modelInjected": 999},
}
AT = "2026-10-04T00:00:00+00:00"


def test_structured_context_separates_counts_from_interpretation_without_mutation():
    snapshot = selected_snapshot()
    for note in snapshot["xhsCreatorProfile"]["notes"]:
        note["title"] = "同名笔记"
    before = deepcopy(snapshot)
    original = deepcopy(PROFILE)
    result = topic_profile_context(PROFILE, snapshot, AT)
    assert "contrast" not in result
    assert result["writingSuggestions"] == PROFILE["contrast"]["takeaways"]
    assert not any(value in json.dumps(result, ensure_ascii=False)
                   for value in ("999", "None", "30%", "15%"))
    facts = result["performanceObservations"]
    assert [note["noteId"] for note in facts["notes"]] == ["n1", "n2"]
    assert [note["metrics"]["shares"] for note in facts["notes"]] == [0, None]
    assert facts["metricSummaries"][3]["missingCount"] == 1
    assert facts["coverage"]["snapshotAt"] == AT
    result["pillars"].append("供应商侧意外修改")
    result["accountPortrait"]["summary"]["statement"] = "已改"
    facts["notes"][0]["metrics"]["liked"] = 999
    assert original == PROFILE
    assert snapshot == before


@pytest.mark.parametrize("contrast", [None, {}, {"takeaways": "不是数组"},
                                      {"takeaways": [None, 42, {}, "", " ", "写法建议"]}])
def test_empty_structured_snapshot_never_falls_back_to_model_metrics(contrast):
    result = topic_profile_context({**PROFILE, "contrast": contrast},
                                   {"xhsCreatorProfile": {"notes": []}}, AT)
    assert "contrast" not in result
    assert result["performanceObservations"]["notes"] == []
    assert result["writingSuggestions"] in ([], ["写法建议"])


def test_legacy_and_missing_profile_remain_compatible():
    result = topic_profile_context(PROFILE, {}, AT)
    assert result == PROFILE
    result["contrast"]["winners"].clear()
    assert PROFILE["contrast"]["winners"]
    assert topic_profile_context(None, selected_snapshot(), AT) is None


@pytest.mark.parametrize("takeaways, expected", [
    ([], ["延续具体场景，再补上选择理由。"]),
    ([None, " "], ["延续具体场景，再补上选择理由。"]),
    (["旧版已确认建议"], ["旧版已确认建议"]),
])
def test_lean_next_steps_supply_topic_suggestions_without_overwriting_legacy(
    takeaways, expected,
):
    profile = {
        "accountPortrait": {
            "expressionPatterns": [{"statement": "从具体处境讲起", "evidence": []}],
            "nextSteps": [
                {"statement": "延续具体场景，再补上选择理由。", "evidence": []},
                None, {"statement": " "}, {"statement": 42},
            ],
        },
        "contrast": {"takeaways": takeaways},
    }
    original = deepcopy(profile)
    result = topic_profile_context(profile, selected_snapshot(), AT)
    assert result["writingSuggestions"] == expected
    assert "viralStructure" not in result
    assert "voiceFingerprint" not in result
    result["accountPortrait"]["nextSteps"][0]["statement"] = "下游编辑"
    assert profile == original
    # Text-only historical reports keep their old, unprojected payload.
    assert topic_profile_context(profile, {}, AT) == original


@pytest.mark.parametrize("resume", [False, True])
def test_graph_uses_frozen_context_on_fresh_and_resumed_runs(app, resume):
    workspace = create_workspace(app)
    payload = {"schemaVersion": "xhs-creator-profile/v1", "creator": {"displayName": "测试"},
               **selected_snapshot()["xhsCreatorProfile"]}
    source = create_text_material(app, workspace["id"], "xhs_creator_profile", json.dumps(payload))
    response = send(app, "POST", f"/api/workspaces/{workspace['id']}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": source["id"],
        "selectedNoteIds": ["n2"], "mode": "demo",
    })
    assert response.status_code == 201
    run = response.json()
    received = []

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            self.calls.append("profile")
            return {"profile": deepcopy(PROFILE)}

        async def topics(self, **kwargs):
            received.append(deepcopy(kwargs["profile"]))
            kwargs["profile"]["pillars"].clear()
            return await super().topics(**kwargs)

    provider = Provider()
    app.state.account_workflow_service.fake_provider = provider
    if resume:
        collect(app, run["id"], stop_after_node="profile_analysis")
        # Editing the live asset must not change the frozen selection or numbers.
        payload["notes"][1]["metrics"]["liked"] = 999
        edited = send(app, "PATCH", f"/api/source-materials/{source['id']}",
                      json={"content": json.dumps(payload),
                            "expectedUpdatedAt": source["updatedAt"]})
        assert edited.status_code == 200
        provider = Provider()
        service = app.state.account_workflow_service
        app.state.account_workflow_service = type(service)(
            database=service.database, analysis_repository=service.analysis_repository,
            checkpoint_repository=service.checkpoint_repository,
            analysis_service=service.analysis_service, fake_provider=provider,
            live_provider=service.live_provider,
        )
    collect(app, run["id"])
    saved = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert saved["status"] == "completed"
    assert provider.calls == (["topics"] if resume else ["profile", "pain_points", "topics"])
    assert len(received) == 1
    context = received[0]
    assert "contrast" not in context
    assert context["performanceObservations"]["coverage"]["selectedNoteIds"] == ["n2"]
    assert context["performanceObservations"]["notes"][0]["metrics"]["liked"] == 2
    assert context["performanceObservations"]["notes"][0]["metrics"]["shares"] is None
    assert saved["stageResults"]["profile"]["profile"]["contrast"] == PROFILE["contrast"]
    assert saved["stageResults"]["profile"]["profile"]["pillars"] == PROFILE["pillars"]
    assert "performanceObservations" not in saved["stageResults"]["profile"]["profile"]
    collect(app, run["id"])
    assert len(received) == 1


def test_text_only_graph_preserves_legacy_profile_for_topics(app):
    received = []

    class Provider(FakeAccountDiagnosisModelProvider):
        async def topics(self, **kwargs):
            received.append(deepcopy(kwargs["profile"]))
            return await super().topics(**kwargs)

    app.state.account_workflow_service.fake_provider = Provider()
    run = create_account_run(app)
    collect(app, run["id"])
    saved = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert received == [saved["stageResults"]["profile"]["profile"]]

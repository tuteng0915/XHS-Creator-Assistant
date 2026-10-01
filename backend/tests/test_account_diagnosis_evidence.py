import asyncio
import json
from datetime import UTC, datetime, timedelta

from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, send

from app.services.account_diagnosis_evidence import build_account_observations, verified_portrait
from app.workflows.account_diagnosis import FakeAccountDiagnosisModelProvider


def selected_snapshot():
    return {
        "analysisRange": {"availableNoteCount": 3, "selectedNoteIds": ["n1", "n2"]},
        "xhsCreatorProfile": {
            "source": {"importedAt": "2026-09-20T08:00:00+00:00"},
            "notes": [
                {
                    "noteId": "n1",
                    "title": "第一条",
                    "desc": "中文正文甲",
                    "publishedAt": "2026-09-01T00:00:00Z",
                    "metrics": {"liked": 10, "collected": 3, "comments": 2, "shares": 0},
                    "comments": [{"content": "你好"}],
                },
                {
                    "noteId": "n2",
                    "title": "第二条",
                    "desc": "中文正文乙",
                    "metrics": {"liked": 2, "collected": 0},
                    "comments": [],
                },
            ],
        },
    }


def test_observations_use_selected_snapshot_and_preserve_missingness():
    snapshot = selected_snapshot()
    result = build_account_observations(snapshot, "2026-09-21T00:00:00+00:00")

    assert result["coverage"]["selectedNoteIds"] == ["n1", "n2"]
    assert result["coverage"]["selectedCount"] == 2
    assert result["coverage"]["availableCount"] == 3
    assert result["coverage"]["missingDateCount"] == 1
    assert result["coverage"]["missingMetricCounts"] == {
        "liked": 0,
        "collected": 0,
        "comments": 1,
        "shares": 1,
    }
    assert result["coverage"]["capturedCommentCount"] == 1
    assert result["notes"][0]["title"] == "第一条"
    assert result["notes"][0]["likesRankInSelection"] == 1
    assert result["notes"][1]["likesRankInSelection"] == 2
    assert result["notes"][1]["metrics"]["comments"] is None
    assert "正文甲" not in json.dumps(result, ensure_ascii=False)
    assert build_account_observations({}, "2026-09-21T00:00:00+00:00") is None


def test_portrait_keeps_only_quotes_from_selected_note():
    portrait = {
        "summary": {
            "statement": "关注中文主题",
            "evidence": [{"noteId": "n1", "quote": "中文正文甲"}],
        },
        "recurringThemes": [
            {"statement": "不相关引用", "evidence": [{"noteId": "n2", "quote": "中文正文甲"}]},
            {"statement": "未选中", "evidence": [{"noteId": "n3", "quote": "标题"}]},
            {"statement": "仅一条例子", "evidence": [{"noteId": "n2", "quote": "第二条"}]},
            {"statement": "重复引用同一篇", "evidence": [
                {"noteId": "n1", "quote": "第一条"},
                {"noteId": "n1", "quote": "中文正文甲"},
            ]},
            {"statement": "有跨笔记依据", "evidence": [
                {"noteId": "n1", "quote": "第一条"},
                {"noteId": "n2", "quote": "第二条"},
            ]},
        ],
        "readerValue": [],
        "expressionPatterns": [],
    }
    result = verified_portrait(portrait, selected_snapshot())
    assert result["summary"]["evidence"] == [{"noteId": "n1", "quote": "中文正文甲"}]
    assert [claim["statement"] for claim in result["recurringThemes"]] == ["有跨笔记依据"]
    assert (
        verified_portrait({"summary": {"statement": "无依据", "evidence": []}}, selected_snapshot())
        is None
    )


def test_chronology_and_counterexamples_require_selected_original_evidence():
    notes = [
        {
            "noteId": f"n{index}",
            "title": f"笔记{index}",
            "desc": f"内容{index}",
            "publishedAt": (
                datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=10 * index)
            ).isoformat(),
            "metrics": {"liked": index + 1},
            "comments": [],
        }
        for index in range(8)
    ]
    snapshot = {"xhsCreatorProfile": {"notes": notes}}
    chronology = build_account_observations(snapshot, "2026-09-30T00:00:00Z")["chronology"]
    assert chronology["status"] == "comparable"
    assert chronology["earlier"]["noteIds"] == ["n0", "n1", "n2", "n3"]
    assert chronology["later"]["noteIds"] == ["n4", "n5", "n6", "n7"]

    portrait = {
        "summary": {
            "statement": "常见一种方向",
            "evidence": [{"noteId": "n0", "quote": "内容0"}],
            "counterexamples": [
                {"noteId": "n6", "quote": "内容6"},
                {"noteId": "other", "quote": "外部"},
            ],
        },
        "recentChange": {
            "statement": "后期转向另一类内容",
            "evidence": [{"noteId": "n1", "quote": "内容1"}, {"noteId": "n5", "quote": "内容5"}],
        },
    }
    verified = verified_portrait(portrait, snapshot, chronology)
    assert verified["summary"]["counterexamples"] == [{"noteId": "n6", "quote": "内容6"}]
    assert verified["recentChange"]["statement"] == "后期转向另一类内容"

    portrait["recentChange"]["evidence"] = [
        {"noteId": "n0", "quote": "内容0"},
        {"noteId": "n1", "quote": "内容1"},
    ]
    assert verified_portrait(portrait, snapshot, chronology)["recentChange"] is None
    portrait["recentChange"]["evidence"] = [
        {"noteId": "n0", "quote": "内容0"},
        {"noteId": "n5", "quote": "内容5"},
    ]
    portrait["recentChange"]["statement"] = "后期点赞增长"
    assert verified_portrait(portrait, snapshot, chronology)["recentChange"] is None

    short = notes[:5]
    assert (
        build_account_observations({"xhsCreatorProfile": {"notes": short}}, "2026-09-30T00:00:00Z")[
            "chronology"
        ]["status"]
        == "insufficient_data"
    )
    duplicate = [{**note, "noteId": "n0"} if note["noteId"] == "n7" else note for note in notes]
    assert (
        build_account_observations(
            {"xhsCreatorProfile": {"notes": duplicate}}, "2026-09-30T00:00:00Z"
        )["chronology"]["status"]
        == "insufficient_data"
    )
    assert (
        verified_portrait(portrait, {"xhsCreatorProfile": {"notes": duplicate}}, chronology) is None
    )


def test_xhs_account_run_persists_facts_and_filters_unsupported_claims(app):
    workspace = create_workspace(app)
    source = create_text_material(
        app,
        workspace["id"],
        "xhs_creator_profile",
        json.dumps(
            {
                "schemaVersion": "xhs-creator-profile/v1",
                "creator": {"displayName": "测试账号"},
                **{
                    "source": selected_snapshot()["xhsCreatorProfile"]["source"],
                    "notes": selected_snapshot()["xhsCreatorProfile"]["notes"],
                },
            },
            ensure_ascii=False,
        ),
    )
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "xhsCreatorProfileInputAssetId": source["id"],
            "selectedNoteIds": ["n1"],
            "mode": "live",
        },
    )
    assert response.status_code == 201
    run = response.json()
    assert "发布时间：2026-09-01" in run["inputSnapshot"]["historicalPosts"]["content"]
    assert "第二条" not in run["inputSnapshot"]["historicalPosts"]["content"]

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            output = await super().profile(**kwargs)
            output["profile"] = {
                **output["profile"],
                "accountPortrait": {
                    "summary": {
                        "statement": "有中文正文",
                        "evidence": [{"noteId": "n1", "quote": "中文正文甲"}],
                    },
                    "recurringThemes": [
                        {
                            "statement": "错误引用",
                            "evidence": [{"noteId": "n2", "quote": "中文正文乙"}],
                        },
                    ],
                },
            }
            return output

    app.state.account_workflow_service.live_provider = Provider()
    asyncio.run(app.state.account_workflow_service.collect_events(run["id"]))
    result = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()["stageResults"]["profile"]
    assert result["observations"]["coverage"]["selectedNoteIds"] == ["n1"]
    assert result["observations"]["notes"][0]["publishedAt"].startswith("2026-09-01")
    assert result["profile"]["accountPortrait"]["summary"]["statement"] == "有中文正文"
    assert result["profile"]["accountPortrait"]["recurringThemes"] == []

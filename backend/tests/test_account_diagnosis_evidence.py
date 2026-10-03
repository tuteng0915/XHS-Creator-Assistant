import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, send

from app.services.account_diagnosis_evidence import (
    build_account_observations,
    profile_stage_input,
    verified_portrait,
)
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


def test_metrics_are_ranked_separately_without_mutating_selected_snapshot():
    snapshot = selected_snapshot()
    snapshot["xhsCreatorProfile"]["notes"].append({
        "noteId": "n3", "title": "收藏更多的一篇",
        "metrics": {"liked": 10, "collected": 90, "comments": 0},
    })
    before = deepcopy(snapshot)
    result = build_account_observations(snapshot, "2026-10-03T00:00:00Z")
    summaries = {item["metric"]: item for item in result["metricSummaries"]}
    assert summaries == {
        "liked": {"metric": "liked", "validCount": 3, "missingCount": 0,
                  "median": 10, "rankMethod": "dense_descending"},
        "collected": {"metric": "collected", "validCount": 3, "missingCount": 0,
                      "median": 3, "rankMethod": "dense_descending"},
        "comments": {"metric": "comments", "validCount": 2, "missingCount": 1,
                     "median": 1, "rankMethod": "dense_descending"},
        "shares": {"metric": "shares", "validCount": 1, "missingCount": 2,
                   "median": 0, "rankMethod": "dense_descending"},
    }
    assert [item["metricRanksInSelection"]["liked"] for item in result["notes"]] == [1, 2, 1]
    assert [item["metricRanksInSelection"]["collected"] for item in result["notes"]] == [2, 3, 1]
    assert [item["metricRanksInSelection"]["shares"] for item in result["notes"]] == [1, None, None]
    assert all(item["likesRankInSelection"] == item["metricRanksInSelection"]["liked"]
               for item in result["notes"])
    assert snapshot == before
    assert build_account_observations(snapshot, "2026-10-03T00:00:00Z") == result
    reordered = deepcopy(snapshot)
    reordered["xhsCreatorProfile"]["notes"].reverse()
    reversed_result = build_account_observations(reordered, "2026-10-03T00:00:00Z")
    assert reversed_result["metricSummaries"] == result["metricSummaries"]
    assert reversed_result["notes"] == list(reversed(result["notes"]))


@pytest.mark.parametrize("values, expected_median, expected_ranks", [
    ([], None, []),
    ([None, None], None, [None, None]),
    ([0], 0, [1]),
    ([0, 0, 0], 0, [1, 1, 1]),
    ([1, 2], 1.5, [2, 1]),
    ([1, 2, 1_000_000], 2, [3, 2, 1]),
    ([4, None, 4, 2, 0], 3, [1, None, 1, 2, 3]),
])
def test_metric_summary_small_samples_missingness_and_outliers(
    values, expected_median, expected_ranks,
):
    snapshot = {"xhsCreatorProfile": {"notes": [
        {"noteId": f"n{index}", "metrics": {"liked": value}}
        for index, value in enumerate(values)
    ]}}
    result = build_account_observations(snapshot, "2026-10-03T00:00:00Z")
    summary = result["metricSummaries"][0]
    assert summary["median"] == expected_median
    assert summary["validCount"] == sum(value is not None for value in values)
    assert summary["missingCount"] == sum(value is None for value in values)
    assert [item["metricRanksInSelection"]["liked"] for item in result["notes"]] == expected_ranks
    assert result["metricSummaries"][1]["median"] is None


@pytest.mark.parametrize("invalid", [True, False, -1, "12", 1.5, {}, []])
def test_metric_summary_does_not_coerce_invalid_values(invalid):
    snapshot = {"xhsCreatorProfile": {"notes": [{"noteId": "n1", "metrics": {
        key: invalid for key in ("liked", "collected", "comments", "shares")
    }}]}}
    result = build_account_observations(snapshot, "2026-10-03T00:00:00Z")
    for summary in result["metricSummaries"]:
        assert summary["validCount"] == 0
        assert summary["missingCount"] == 1
        assert summary["median"] is None
        assert result["notes"][0]["metricRanksInSelection"][summary["metric"]] is None


def test_metric_summary_uses_selection_not_available_count_or_captured_comments():
    snapshot = selected_snapshot()
    snapshot["analysisRange"]["availableNoteCount"] = 100
    snapshot["xhsCreatorProfile"]["notes"] = snapshot["xhsCreatorProfile"]["notes"][:1]
    snapshot.update(accountPositioning="写自己的经历", historicalPosts={"content": "历史笔记原文"})
    model_input, result = profile_stage_input(snapshot, "2026-10-03T00:00:00Z")
    assert model_input == {"positioning": "写自己的经历", "historicalPosts": "历史笔记原文"}
    assert all(item["validCount"] == 1 for item in result["metricSummaries"])
    assert result["metricSummaries"][2]["median"] == 2
    assert result["coverage"]["capturedCommentCount"] == 1
    assert result["coverage"]["availableCount"] == 100
    assert all(item["noteId"] == "n1" for item in result["notes"])


def test_stitched_quotes_do_not_pass_and_original_ellipsis_is_allowed():
    snapshot = selected_snapshot()
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = (
        "先核对费用，再决定是否报名。记得预留时间。等待……也可以是准备。"
    )
    def claim(quote):
        return {"statement": "帮助读者考虑行动条件", "evidence": [
            {"noteId": "n1", "quote": quote},
        ]}
    assert verified_portrait({"summary": claim("先核对费用……预留时间")}, snapshot) is None
    for quote in ("先核对费用，再决定是否报名。", "等待……也可以是准备。"):
        result = verified_portrait({"summary": claim(quote)}, snapshot)
        assert result["summary"]["evidence"][0]["quote"] == quote


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


def test_portrait_keeps_grounded_keywords_strengths_and_encouragement():
    portrait = {
        "keywords": [
            {"statement": "中文分享", "evidence": [{"noteId": "n1", "quote": "中文正文甲"}]},
            {"statement": "中文分享", "evidence": [{"noteId": "n2", "quote": "中文正文乙"}]},
            {"statement": "未经支持", "evidence": [{"noteId": "n2", "quote": "中文正文甲"}]},
        ],
        "strengths": [
            {
                "statement": "用具体内容帮助读者",
                "evidence": [{"noteId": "n1", "quote": "中文正文甲"}],
            },
            {"statement": "凭空夸奖", "evidence": [{"noteId": "missing", "quote": "不存在"}]},
        ],
        "encouragement": {
            "statement": "这份分享值得继续做下去",
            "evidence": [{"noteId": "n2", "quote": "中文正文乙"}],
        },
    }
    result = verified_portrait(portrait, selected_snapshot())
    assert [item["statement"] for item in result["keywords"]] == ["中文分享"]
    assert [item["statement"] for item in result["strengths"]] == ["用具体内容帮助读者"]
    assert result["encouragement"]["statement"] == "这份分享值得继续做下去"
    assert "keywords" not in verified_portrait(
        {"summary": {"statement": "旧画像", "evidence": [{"noteId": "n1", "quote": "第一条"}]}},
        selected_snapshot(),
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
                    "keywords": [
                        {
                            "statement": "中文分享",
                            "evidence": [{"noteId": "n1", "quote": "中文正文甲"}],
                        }
                    ],
                    "strengths": [
                        {
                            "statement": "能把经验写具体",
                            "evidence": [{"noteId": "n1", "quote": "中文正文甲"}],
                        }
                    ],
                    "encouragement": {
                        "statement": "这份分享值得继续做下去",
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
    assert result["observations"]["metricSummaries"][1] == {
        "metric": "collected", "validCount": 1, "missingCount": 0,
        "median": 3, "rankMethod": "dense_descending",
    }
    assert result["observations"]["notes"][0]["metricRanksInSelection"] == {
        "liked": 1, "collected": 1, "comments": 1, "shares": 1,
    }
    assert result["profile"]["accountPortrait"]["summary"]["statement"] == "有中文正文"
    assert result["profile"]["accountPortrait"]["keywords"][0]["statement"] == "中文分享"
    assert result["profile"]["accountPortrait"]["strengths"][0]["statement"] == "能把经验写具体"
    assert (
        result["profile"]["accountPortrait"]["encouragement"]["statement"]
        == "这份分享值得继续做下去"
    )
    assert result["profile"]["accountPortrait"]["recurringThemes"] == []

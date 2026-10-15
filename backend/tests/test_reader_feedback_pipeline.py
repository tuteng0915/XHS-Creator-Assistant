import asyncio
import json
from copy import deepcopy

import pytest

from app.models import ModelCallResponse
from app.services.reader_feedback_pipeline import (
    MAX_CANDIDATES,
    MAX_SELECTED,
    RETRIEVE_PROMPT,
    VERSION,
    comment_catalog,
    run_reader_feedback,
)

AUTHOR = "1234567890abcdef"
READER = "fedcba0987654321"


def response(output, metadata=None):
    return ModelCallResponse(output=output, model_metadata=metadata or {})


def candidates(count=6):
    return {"candidates": [
        {"theme": f"反馈主题 {index}", "intensity": "中", "commentIds": [f"c{index}"]}
        for index in range(1, count + 1)
    ]}


def source_profile(count=6):
    return {"notes": [{
        "noteId": "frozen-note", "title": "这份已保存的申请攻略", "authorHash": AUTHOR,
        "comments": [
            {"commentId": f"original-{index}", "authorHash": READER,
             "content": f"原始评论 {index}：能补充申请步骤吗？"}
            for index in range(1, count + 1)
        ],
    }]}


class Calls:
    def __init__(self, retrieve, rank=None, metadata=None):
        self.results = {"retrieve": retrieve, "rank": rank}
        self.metadata = metadata
        self.requests = []

    async def __call__(self, stage, system, user):
        self.requests.append({"stage": stage, "system": system, "user": json.loads(user)})
        result = self.results[stage]
        if isinstance(result, BaseException):
            raise result
        return response(result, self.metadata)


def run(calls, profile=None, comments="", on_update=None):
    return asyncio.run(run_reader_feedback(comments, profile, calls, on_update))


def test_catalog_excludes_verified_authors_keeps_unknowns_and_preserves_frozen_source():
    profile = source_profile(1)
    profile["notes"][0]["comments"] += [
        {"commentId": "author", "authorHash": AUTHOR.upper(), "content": "作者回复勿引用"},
        {"commentId": "unknown", "content": "我想了解下一步", "sourceRole": "author"},
        {"commentId": "blank", "content": "  "},
        {"commentId": "image", "image": "placeholder.png"},
    ]
    profile["notes"] += [
        {"noteId": "bad-hash", "authorHash": "invalid", "comments": [
            {"authorHash": "invalid", "content": "无效身份标识不能判为作者"},
        ]},
        None,
        {"noteId": "bad-comments", "comments": "not-a-list"},
    ]
    before = deepcopy(profile)
    catalog = comment_catalog("旧派生文本：作者回复勿引用", profile)

    assert profile == before
    assert [item["id"] for item in catalog] == ["c1", "c2", "c3"]
    assert [item["commentId"] for item in catalog] == ["original-1", "unknown", ""]
    assert [item["text"] for item in catalog] == [
        "原始评论 1：能补充申请步骤吗？", "我想了解下一步", "无效身份标识不能判为作者",
    ]
    assert catalog[0]["noteTitle"] == "这份已保存的申请攻略"
    assert catalog[0]["noteId"] == "frozen-note"


def test_pipeline_uses_frozen_profile_not_legacy_derived_text_and_hides_author_hashes():
    profile = source_profile(1)
    profile["notes"][0]["comments"] += [
        {"authorHash": AUTHOR, "content": "不能进入模型的作者回答"},
        {"content": "未知身份也可提问"},
    ]
    before = deepcopy(profile)
    calls = Calls(candidates(2), {"selectedIds": ["f2", "f1"]})
    result = run(calls, profile, "旧派生原文混有作者回答")

    sent = json.dumps(calls.requests, ensure_ascii=False)
    assert "不能进入模型的作者回答" not in sent
    assert "旧派生原文混有作者回答" not in sent
    assert AUTHOR not in sent and READER not in sent
    assert result.output["painPoints"][0]["evidence"] == ["未知身份也可提问"]
    assert profile == before


@pytest.mark.parametrize("profile,comments", [
    (None, "\n  \n"),
    ({"notes": []}, "不能拿旧派生文本充当候选"),
    ({"notes": [{"comments": [{"content": " "}, {"image": "x"}]}]}, "旧文本"),
    ({"notes": [{"authorHash": AUTHOR, "comments": [
        {"authorHash": AUTHOR, "content": "仅作者发言"},
    ]}]}, "旧文本"),
])
def test_no_eligible_text_returns_empty_without_model_calls(profile, comments):
    calls = Calls(AssertionError("must not call retrieval"))
    updates = []

    async def update(progress):
        updates.append(progress)

    result = run(calls, profile, comments, update)
    assert result.output == {"painPoints": []}
    assert result.model_metadata["requestCount"] == 0
    assert result.model_metadata["sourceCommentCount"] == 0
    assert result.model_metadata["calls"] == []
    assert calls.requests == updates == []


@pytest.mark.parametrize("recalled", [
    {"candidates": []},
    {"candidates": [{"theme": "无来源", "commentIds": ["unknown"]}]},
])
def test_no_valid_recalled_candidates_stops_after_one_call(recalled):
    calls = Calls(recalled, AssertionError("must not rank"))
    result = run(calls, source_profile(1))
    assert result.output == {"painPoints": []}
    assert result.model_metadata["requestCount"] == 1
    assert result.model_metadata["candidateCount"] == 0
    assert [item["stage"] for item in calls.requests] == ["retrieve"]


def test_retrieval_binds_original_quotes_and_counts_distinct_comment_ids():
    profile = source_profile(3)
    profile["notes"][0]["comments"][1]["content"] = "  第二条原文要保留空格  "
    profile["notes"][0]["comments"][2]["content"] = profile["notes"][0]["comments"][0]["content"]
    recalled = {"candidates": [
        {"theme": "  申请步骤  ", "intensity": "夸张", "count": 999,
         "evidence": ["模型编造的引用"],
         "commentIds": ["c1", "c2", "missing", "c1", None, "c3"]},
        {"theme": "申请步骤", "commentIds": ["c3", "c2", "c1"]},
        {"theme": "没有可用引用", "commentIds": ["missing"]},
        {"theme": "  ", "commentIds": ["c1"]},
        None,
    ]}
    calls = Calls(recalled, {"selectedIds": ["f1"]})
    result = run(calls, profile)
    assert result.output == {"painPoints": [{
        "theme": "申请步骤", "intensity": "中", "count": 3,
        "evidence": ["原始评论 1：能补充申请步骤吗？", "  第二条原文要保留空格  "],
    }]}
    assert result.model_metadata["candidateCount"] == 1


def test_single_comment_can_be_recalled_and_ranked_without_filling_four_slots():
    calls = Calls(candidates(1), {"selectedIds": ["f1"]})
    result = run(calls, source_profile(1))
    assert len(result.output["painPoints"]) == 1
    assert result.output["painPoints"][0]["count"] == 1
    assert result.model_metadata["requestCount"] == 2
    assert result.model_metadata["selectedCandidateIds"] == ["f1"]
    assert "rankingFallback" not in result.model_metadata


def test_ranking_preserves_order_deduplicates_ignores_unknown_ids_and_caps_four():
    calls = Calls(candidates(), {"selectedIds": [
        "missing", "f5", "f2", "f5", None, 1, {}, "f6", "f1", "f3", "f4",
    ]})
    result = run(calls, source_profile())
    assert [item["theme"] for item in result.output["painPoints"]] == [
        "反馈主题 5", "反馈主题 2", "反馈主题 6", "反馈主题 1",
    ]
    assert len(result.output["painPoints"]) == MAX_SELECTED
    assert result.model_metadata["selectedCandidateIds"] == ["f5", "f2", "f6", "f1"]
    assert "rankingFallback" not in result.model_metadata


@pytest.mark.parametrize("ranked,fallback", [
    ({"selectedIds": []}, "no_valid_selection"),
    ({"selectedIds": ["missing", None, {}, 0]}, "no_valid_selection"),
    ({"selectedIds": "f2"}, "no_valid_selection"),
    ({}, "no_valid_selection"),
    (RuntimeError("upstream-key-secret 原始评论不应记录"), "ranking_failed"),
])
def test_unusable_ranking_preserves_first_four_recalled_candidates(ranked, fallback):
    calls = Calls(candidates(), ranked)
    result = run(calls, source_profile())
    assert [item["theme"] for item in result.output["painPoints"]] == [
        "反馈主题 1", "反馈主题 2", "反馈主题 3", "反馈主题 4",
    ]
    assert result.model_metadata["selectedCandidateIds"] == ["f1", "f2", "f3", "f4"]
    assert result.model_metadata["rankingFallback"] == fallback
    assert result.model_metadata["requestCount"] == 2
    assert len(calls.requests) == 2
    assert "upstream-key-secret" not in json.dumps(result.model_metadata, ensure_ascii=False)
    expected = "failed" if fallback == "ranking_failed" else "completed"
    assert result.model_metadata["calls"][-1]["status"] == expected


@pytest.mark.parametrize("stage", ["retrieve", "rank"])
def test_cancellation_propagates_without_fallback_or_extra_calls(stage):
    calls = Calls(
        asyncio.CancelledError() if stage == "retrieve" else candidates(1),
        asyncio.CancelledError(),
    )
    with pytest.raises(asyncio.CancelledError):
        run(calls, source_profile(1))
    assert [item["stage"] for item in calls.requests] == (
        ["retrieve"] if stage == "retrieve" else ["retrieve", "rank"]
    )


def test_legacy_plain_text_keeps_nonempty_lines_as_original_quotes():
    calls = Calls(candidates(2), {"selectedIds": ["f2", "f1"]})
    result = run(calls, comments="  请问有面试嘛？  \n\n感谢分享\n ")
    assert calls.requests[0]["user"]["comments"] == [
        {"id": "c1", "text": "  请问有面试嘛？  "},
        {"id": "c2", "text": "感谢分享"},
    ]
    assert [item["evidence"] for item in result.output["painPoints"]] == [
        ["感谢分享"], ["  请问有面试嘛？  "],
    ]


def test_progress_reports_retrieval_then_ranking_before_each_model_call():
    order = []
    calls = Calls(candidates(1), {"selectedIds": ["f1"]})

    async def update(progress):
        order.append(("progress", deepcopy(progress)))

    async def call(stage, system, user):
        order.append(("call", stage))
        return await calls(stage, system, user)

    result = run(call, source_profile(1), on_update=update)
    assert [(kind, value if kind == "call" else value["phase"]) for kind, value in order] == [
        ("progress", "feedback_retrieval"), ("call", "retrieve"),
        ("progress", "feedback_ranking"), ("call", "rank"),
    ]
    assert order[0][1] == {
        "phase": "feedback_retrieval", "status": "running", "completed": 0,
        "total": 2, "preview": "",
    }
    assert order[2][1]["completed"] == 1
    assert order[2][1]["total"] == 2
    assert "反馈主题 1" in order[2][1]["preview"]
    assert "progress" not in result.model_metadata


def test_metadata_keeps_safe_diagnostics_without_original_text_credentials_or_provider_dump():
    raw = "这是一条不能重复存到元数据的评论原文"
    profile = source_profile(1)
    profile["notes"][0]["comments"][0]["content"] = raw
    calls = Calls(candidates(1), {"selectedIds": ["f1"]}, metadata={
        "provider": "qwen", "model": "qwen-plus", "systemPromptHash": "abc123",
        "apiKey": "sk-secret", "rawResponse": raw,
        "request": {"authorization": "Bearer sk-secret", "sourceText": raw},
        "reasoning": raw,
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15,
                  "input_tokens": -1, "output_tokens": True, "secret": "sk-secret"},
    })
    result = run(calls, profile)
    metadata = json.dumps(result.model_metadata, ensure_ascii=False)
    assert raw not in metadata and "sk-secret" not in metadata
    assert result.model_metadata["calls"] == [
        {"stage": stage, "status": "completed", "provider": "qwen", "model": "qwen-plus",
         "systemPromptHash": "abc123", "usage": {
             "prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15,
         }}
        for stage in ("retrieve", "rank")
    ]
    assert result.model_metadata["sourceCommentCount"] == 1
    assert result.output["painPoints"][0]["evidence"] == [raw]


def test_retrieval_bounds_candidates_before_ranking():
    calls = Calls(candidates(MAX_CANDIDATES + 5), {"selectedIds": [f"f{MAX_CANDIDATES}"]})
    result = run(calls, source_profile(MAX_CANDIDATES + 5))
    assert len(calls.requests[1]["user"]["candidates"]) == MAX_CANDIDATES
    assert result.model_metadata["candidateCount"] == MAX_CANDIDATES
    assert result.model_metadata["selectedCandidateIds"] == [f"f{MAX_CANDIDATES}"]


def test_rank_has_original_quotes_and_their_note_context_for_ambiguous_short_feedback():
    profile = source_profile(3)
    profile["notes"][0]["comments"][0]["content"] = "这个还可以报名吗？"
    profile["notes"][0]["comments"][1]["content"] = "需要准备什么？"
    profile["notes"][0]["comments"][2]["content"] = "未召回的评论不应进入排序"
    calls = Calls(candidates(2), {"selectedIds": ["f2"]})
    run(calls, profile)
    ranked_context = calls.requests[1]["user"]
    serialized = json.dumps(ranked_context, ensure_ascii=False)
    assert "这个还可以报名吗？" in serialized
    assert "需要准备什么？" in serialized
    assert "这份已保存的申请攻略" in serialized
    assert "未召回的评论不应进入排序" not in serialized
    assert [(item["id"], item["commentIds"]) for item in ranked_context["candidates"]] == [
        ("f1", ["c1"]), ("f2", ["c2"]),
    ]
    assert ranked_context["comments"] == [
        {"id": "c1", "text": "这个还可以报名吗？", "noteTitle": "这份已保存的申请攻略"},
        {"id": "c2", "text": "需要准备什么？", "noteTitle": "这份已保存的申请攻略"},
    ]


def test_whole_sample_recall_keeps_late_questions_available_before_candidate_limit():
    # Transport coverage, not a substitute for a real-model recall check.
    profile = source_profile(120)
    for comment in profile["notes"][0]["comments"]:
        comment["content"] = "谢谢分享，很喜欢！"
    profile["notes"].append({
        "noteId": "last-note", "title": "第一次参加行业活动",
        "comments": [
            {"commentId": "late-question", "content": "没到现场能否由同行者代为展示？"},
            {"commentId": "specific-praise", "content": "报名步骤的截图让我少填错了一项"},
        ],
    })
    calls = Calls({"candidates": [
        {"theme": "是否可委托同行者展示", "commentIds": ["c121"]},
        {"theme": "报名步骤截图帮助减少填报错误", "commentIds": ["c122"]},
    ]}, {"selectedIds": ["f1", "f2"]})
    result = run(calls, profile)

    sent = calls.requests[0]
    assert sent["system"] == RETRIEVE_PROMPT
    assert "先读完全部 comments" in sent["system"]
    assert f"最多{MAX_CANDIDATES}项候选" in sent["system"]
    assert "需要不同回答的问题分开" in sent["system"]
    assert len(sent["user"]["comments"]) == 122
    assert sent["user"]["comments"][-2] == {
        "id": "c121", "text": "没到现场能否由同行者代为展示？", "noteTitle": "第一次参加行业活动",
    }
    assert result.model_metadata["promptVersion"] == VERSION
    assert result.model_metadata["requestCount"] == 2
    assert result.model_metadata["sourceCommentCount"] == 122
    assert [item["count"] for item in result.output["painPoints"]] == [1, 1]
    assert result.output["painPoints"][0]["evidence"] == ["没到现场能否由同行者代为展示？"]

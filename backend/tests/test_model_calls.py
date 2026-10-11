import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.errors import ValidationError
from app.models import ModelOperation
from app.services.model_calls import ModelCallService


class FakeAsyncClient:
    requests: list[dict[str, Any]] = []
    response_body: dict[str, Any] = {}
    response_status_code = 200
    options: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).options = kwargs

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        self.requests.append({"url": url, "headers": headers, "json": json})
        return httpx.Response(self.response_status_code, json=self.response_body)


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_path": Path(":memory:"),
        "upload_directory": Path(":memory:"),
    }
    values.update(overrides)
    return Settings(**values)


def test_reader_feedback_prompt_accepts_sparse_unknown_and_positive_comments():
    from app.services.model_calls import PROMPT_READER_FEEDBACK

    source = "请问有面试嘛？\n感谢分享"
    service = ModelCallService(settings())
    system, user = service._build_prompt(ModelOperation.PAIN_POINTS, {
        "sourceText": source, "sourceKind": "reader_comments",
    })

    assert system == PROMPT_READER_FEEDBACK
    assert user == source
    assert "0~5" in system and "不强制凑足条数" in system
    assert "明确提问、具体需求、困惑和正向反馈" in system
    assert "单条明确提问或需求也可保留" in system
    assert "不改写成困难或痛点" in system
    assert "unknown 表示身份无法比较，仍可根据其原文分析反馈" in system
    assert "不确认其读者身份" in system
    assert "文本确实没有可识别的反馈信息时" in system
    assert "逐字引用" in system
    assert service._validate_model_output(ModelOperation.PAIN_POINTS, {"painPoints": []}) == {
        "painPoints": [],
    }


@pytest.mark.parametrize("context", [
    {"sourceText": "以下是小红书相关热帖的标题和内容，请归纳痛点"},
    {"comments": "普通文本评论"},
    {"sourceText": "# 小红书一级评论样本（由 xhs_creator_profile 派生）"},
    {"sourceText": "其他输入", "sourceKind": "other"},
])
def test_generic_pain_prompt_is_not_changed_or_selected_by_source_text(context):
    from app.services.model_calls import PROMPT_PAIN_POINTS

    system, user = ModelCallService(settings())._build_prompt(ModelOperation.PAIN_POINTS, context)

    assert system == PROMPT_PAIN_POINTS
    assert user == context.get("sourceText", context.get("comments"))


def test_account_provider_uses_feedback_retrieval_but_trend_provider_stays_generic():
    from app.models import ModelCallResponse
    from app.workflows.account_diagnosis import RealAccountDiagnosisModelProvider
    from app.workflows.trend_analysis import RealTrendAnalysisModelProvider

    received = []

    class Model:
        async def call_operation(self, operation, context):
            received.append((operation, context))
            return ModelCallResponse(output={"painPoints": []}, model_metadata={})

        async def call_reader_feedback_step(self, stage, system, user):
            received.append((stage, json.loads(user)))
            return ModelCallResponse(output={"candidates": []}, model_metadata={})

    model = Model()
    account_result = asyncio.run(RealAccountDiagnosisModelProvider(model).pain_points(
        comments="请问有面试嘛？",
    ))
    trend_result = asyncio.run(RealTrendAnalysisModelProvider(model).pain_points(
        trend_keyword="申请", posts_text="热帖正文",
    ))

    assert account_result == trend_result == {"painPoints": []}
    assert received[0] == ("retrieve", {
        "comments": [{"id": "c1", "text": "请问有面试嘛？"}],
    })
    assert received[1][0] == ModelOperation.PAIN_POINTS
    assert set(received[1][1]) == {"sourceText"}
    assert "归纳读者高频痛点" in received[1][1]["sourceText"]


@pytest.mark.parametrize("stage,budget,output", [
    ("retrieve", 2200, {"candidates": [{"theme": "面试询问", "commentIds": ["c1"]}]}),
    ("rank", 500, {"selectedIds": ["f2", "f1"]}),
])
def test_feedback_steps_use_configured_qwen_and_phase_budgets(monkeypatch, stage, budget, output):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus", "choices": [{"message": {"content": json.dumps(output)}}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 8},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="placeholder-key"))

    response = asyncio.run(service.call_reader_feedback_step(stage, "阶段提示", "原文材料"))

    assert response.output == output
    assert response.model_metadata["stage"] == stage
    request = FakeAsyncClient.requests[0]["json"]
    assert request["model"] == "qwen-plus"
    assert request["max_tokens"] == budget
    assert request["messages"] == [
        {"role": "system", "content": "阶段提示"}, {"role": "user", "content": "原文材料"},
    ]
    assert service._output_budget(ModelOperation.PAIN_POINTS, {}) == 1000
    assert service._output_budget(ModelOperation.PROFILE, {"_readerFeedbackStage": stage}) == 6000


def test_feedback_step_rejects_unknown_phase_before_a_request():
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="placeholder-key"))
    with pytest.raises(ValidationError, match="Unsupported reader feedback stage"):
        asyncio.run(service.call_reader_feedback_step("unknown", "", ""))


@pytest.mark.parametrize("stage", ["retrieve", "rank"])
def test_feedback_step_does_not_use_truncated_json(monkeypatch, stage):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {"choices": [{
        "message": {"content": '{"selectedIds":["f1"]}'}, "finish_reason": "length",
    }]}
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="placeholder-key"))
    with pytest.raises(ValidationError, match="输出不完整"):
        asyncio.run(service.call_reader_feedback_step(stage, "", ""))


@pytest.mark.parametrize("feedback", [[], [
    {"theme": "正向反馈：感谢分享", "intensity": "中", "count": 1, "evidence": ["感谢分享"]},
]])
def test_account_topics_do_not_turn_positive_or_empty_feedback_into_pain(feedback):
    from app.services.model_calls import PROMPT_TOPICS, PROMPT_TOPICS_B

    service = ModelCallService(settings())
    context = {"profile": {"pillars": ["申请经验"]}, "painPoints": feedback}
    account_system, account_user = service._build_prompt(ModelOperation.TOPICS, context)
    trend_system, _ = service._build_prompt(ModelOperation.TREND_TOPICS, context)

    assert account_system == PROMPT_TOPICS
    assert "正向反馈不得改写成痛点" in account_system
    assert "可依据账号诊断（profile）建议选题" in account_system
    assert "而非已验证的读者需求" in account_system
    assert "topics[0] 必须对应" not in account_system
    assert "申请经验" in account_user
    assert json.dumps(feedback, ensure_ascii=False) in account_user
    assert trend_system == PROMPT_TOPICS_B
    assert "topics[0] 必须对应 painPoints[0]" in trend_system


def test_qwen_profile_length_stop_is_not_accepted_even_with_parseable_json(monkeypatch):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "choices": [{"finish_reason": "length", "message": {"content": '{"profile":{}}'}}],
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="fake"))
    with pytest.raises(ValidationError, match="账号画像输出达到长度上限"):
        asyncio.run(service.call_operation(ModelOperation.PROFILE, {"historicalPosts": "中文"}))
    assert len(FakeAsyncClient.requests) == 1
    assert FakeAsyncClient.requests[0]["json"]["max_tokens"] == 6000


def test_content_collaboration_prompt_uses_one_role_aware_strict_turn_contract():
    system, user = ModelCallService(settings())._build_prompt(
        ModelOperation.CONTENT_COLLABORATION_TURN,
        {
            "schemaVersion": "content-collaboration-role-packet/v2",
            "role": "research",
            "roleTask": {"objective": "建立可写证据"},
            "writingFocus": {
                "selection": {"start": 0, "end": 2, "text": "原文"},
                "readerMessage": {"content": "这里想看得更清楚"},
            },
            "creativeBrief": {"target": {"title": "冻结选题"}},
            "upstreamHandoff": {"content": "先查证", "candidates": []},
            "evidence": {"allowedSources": [{"id": "target:topic", "text": "原文"}]},
        },
    )
    assert "research：交给 writing 时" in system
    assert "candidateSuggestions" in system
    assert "usedCandidateIds" in system
    assert "artifactRefs" in system
    assert "不能借一条相关引用把它包装成已知事实" in system
    assert "不能用“例如”" not in system
    assert "冻结选题" in user
    assert "target:topic" in user
    assert '"writingFocus"' in user
    assert "这里想看得更清楚" in user
    assert "只精修这一个片段" in system
    assert "而非整篇或讲解" in system
    assert "不必硬凑 copy_option" in system
    assert "核心动作、责任主体、立场和判断强度" in system
    assert "把它们改成反问" in system
    assert "不要求作者从读者猜测的原因中选答案" in system
    assert "直接给有收益的 copy_option" in system


def test_qwen_content_collaboration_length_stop_is_not_accepted(monkeypatch):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": '{"turn":{"summary":"未完成"}}'},
            }
        ]
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="fake"))
    with pytest.raises(ValidationError, match="协作角色输出达到长度上限"):
        asyncio.run(
            service.call_operation(
                ModelOperation.CONTENT_COLLABORATION_TURN,
                {"role": "research", "frozenContext": {"allowedSources": []}},
            )
        )
    assert len(FakeAsyncClient.requests) == 1
    assert FakeAsyncClient.requests[0]["json"]["max_tokens"] == 1800


def test_content_collaboration_turn_does_not_unwrap_a_loose_model_envelope():
    with pytest.raises(
        ValidationError,
        match="Model response for content_collaboration_turn missing turn",
    ):
        ModelCallService._validate_model_output(
            ModelOperation.CONTENT_COLLABORATION_TURN,
            {"data": {"turn": {"summary": "不该接受"}}},
        )


def test_profile_prompt_keeps_contexts_distinct_without_removing_positive_synthesis():
    context = {
        "positioning": "跨领域记录",
        "historicalPosts": "学校导师关心适应生活。\n公司带教提供每周成长路径。",
    }
    system, user = ModelCallService(settings())._build_prompt(ModelOperation.PROFILE, context)
    assert "主体与场景" in system
    assert "不同内容线可以并列成立" in system
    assert "若结论限定某个具体场景，依据也须来自该场景" in system
    assert "不必硬造融合身份或把不同经历接成一个故事" in system
    assert "真实笔记例子及它让阅读更好的地方" in system
    assert "语气真诚、积极、有鼓励感" in system
    assert context["historicalPosts"] in user


def test_profile_prompt_teaches_short_contiguous_quotes_without_banning_source_ellipsis():
    system, _ = ModelCallService(settings())._build_prompt(ModelOperation.PROFILE, {})
    assert "建议 10～40 字" in system
    assert "分成两个 evidence" in system
    assert "不用省略号拼接" in system
    assert "先核对费用" not in system
    assert "原文本来有省略号可以照抄" in system


def test_profile_review_handles_missing_metrics_and_scene_specific_claims():
    system, user = ModelCallService(settings())._build_prompt(ModelOperation.PROFILE, {
        "historicalPosts": "毕业记录：赞 3，分享 None。学校与工作是两段经历。",
    })
    assert "跨场景的材料可以支持共同的写作方式" in system
    assert "依据也须来自该场景" in system
    assert "null 是未获取，不补零" in system
    assert "不因一篇互动少就否定它的记录价值" in system
    assert "数字排序由页面展示，不再生成一套榜单" in system
    assert "按实际可读文字分析" in system
    assert "不要为没读到的正文臆造步骤、结论，或批评它缺少论证" in system
    assert "分享 None" in user  # Instructions do not mutate the frozen source.


def test_profile_review_methods_preserve_schema_and_use_only_supplied_context():
    service = ModelCallService(settings())
    system, user = service._build_prompt(ModelOperation.PROFILE, {
        "positioning": "本人经验分享",
        "historicalPosts": "笔记甲：赞 0，收藏 8；正文是一次选择的取舍。",
        "unrelatedSimulation": "不应进入画像的模拟结论",
    })
    assert "分别看点赞、收藏、评论、分享" in system
    assert "未提供曝光时不计算互动率" in system
    assert "主题、场景、核心表达与写法" in system
    assert "不要求每篇都有冲突、金句或固定篇幅" in system
    assert "参考哪篇的哪个做法、适合什么写作场景、下一次可以尝试的一个动作" in system
    assert "examples 只用输入中的原始标题" in system
    assert "各栏各司其职" in system
    assert "800～1200" in system
    assert "假设示例" not in system
    assert "winners、losers、winFactors、loseFactors 均留空数组" in system
    assert user == (
        "账号定位：\n本人经验分享\n\n历史笔记：\n"
        "笔记甲：赞 0，收藏 8；正文是一次选择的取舍。"
    )


def test_profile_report_distinguishes_case_identity_and_requests_actions_not_invented_scenes():
    system, _ = ModelCallService(settings())._build_prompt(ModelOperation.PROFILE, {})
    assert "同一篇里有多个申请人、学生、朋友或案例，也须各自独立" in system
    assert "一个人的学校、工作、项目或经历不能移给另一个人" in system
    assert "选一处自己确实记得的细节" in system
    assert "不代写虚构现场、身体反应、数字或个人经历" in system
    assert "summary 不是字符串" in system
    assert "与 accountPortrait 同级" in system
    schema = json.loads(system.split("schema:\n", 1)[1])
    profile = schema["profile"]
    assert isinstance(profile["accountPortrait"]["summary"], dict)
    assert profile["contrast"]["winners"] == []
    assert profile["contrast"]["losers"] == []
    assert "voiceFingerprint" not in profile["accountPortrait"]


def test_profile_review_roundtrip_keeps_existing_output_and_single_request(monkeypatch):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "fake-qwen",
        "choices": [{"finish_reason": "stop", "message": {"content": (
            '{"profile":{"voiceFingerprint":["短句先讲取舍，再解释理由"],'
            '"contrast":{"takeaways":["参考笔记甲的对比顺序；有实际选择经历时，'
            '先写关键权衡，再给自己的决定。"]}}}'
        )}}],
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="fake"))
    result = asyncio.run(service.call_operation(ModelOperation.PROFILE, {
        "positioning": "选择经历", "historicalPosts": "笔记甲的正文",
    }))
    assert len(FakeAsyncClient.requests) == 1
    request = FakeAsyncClient.requests[0]["json"]
    assert "先认识账号，再谈可尝试的改进" in request["messages"][0]["content"]
    assert request["max_tokens"] == 6000
    assert FakeAsyncClient.options["timeout"].as_dict() == dict(
        connect=90, read=180, write=90, pool=90,
    )
    assert result.output["profile"]["voiceFingerprint"] == ["短句先讲取舍，再解释理由"]
    assert isinstance(result.output["profile"]["contrast"]["takeaways"][0], str)
    assert result.model_metadata["model"] == "fake-qwen"


@pytest.mark.parametrize("operation", list(ModelOperation))
def test_only_qwen_profile_has_configurable_read_timeout(operation):
    service = ModelCallService(settings(qwen_profile_read_timeout_seconds=150))

    async def check():
        async with service._qwen_client(operation) as client:
            assert client.timeout.as_dict() == dict(
                connect=90, read=150 if operation == ModelOperation.PROFILE else 90,
                write=90, pool=90,
            )
    asyncio.run(check())


def test_profile_budget_change_keeps_other_operations_unchanged(monkeypatch):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "choices": [{"finish_reason": "stop", "message": {"content": '{"painPoints":[]}'}}],
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="fake"))
    result = asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "中文"}))
    assert result.output == {"painPoints": []}
    assert FakeAsyncClient.requests[0]["json"]["max_tokens"] == 1000


def test_audience_prompts_separate_teaching_examples_from_observations():
    service = ModelCallService(settings())
    system, user = service._build_prompt(ModelOperation.AUDIENCE_ANALYSIS,
                                        {"notes": [{"title": "当前账号唯一材料"}]})
    assert "教学示例" in system and "unknowns" in system
    assert "当前账号唯一材料" in user
    assert "住宿和保险" not in user
    system, user = service._build_prompt(ModelOperation.SIMULATION_REACTION,
                                        {"persona": {"id": "p"}, "topic": {"title": "测试"}})
    assert "observedEpisodes" in system and "教学" not in user
    system, user = service._build_prompt(ModelOperation.SIMULATION_DEBATE, {
        "persona": {"id": "p"}, "topic": {"title": "测试"},
        "priorReaction": {"understanding": "自己的第一理解"},
        "otherReactions": [{"messageId": "initial:other", "quote": "对方公开的问题"}],
    })
    assert "自己的第一理解" in user and "对方公开的问题" in user
    assert "replyToId" in system and "changeReason" in system


def test_creation_prompts_distinguish_evidence_from_generated_suggestions():
    service = ModelCallService(settings())
    for operation in [ModelOperation.TOPICS, ModelOperation.TREND_TOPICS]:
        system, _ = service._build_prompt(operation, {})
        assert "pendingSuggestions" in system and "亲历" in system
    system, user = service._build_prompt(ModelOperation.CREATOR_EDIT, {
        "topic": {"angle": "旧 AI 建议的虚构意象"},
        "factSources": [{"id": "current-user-message", "text": "我没有去过后台"}],
    })
    assert "不是作者亲历证据" in system
    assert "sourceQuote" in system and "supportedClaims" in system
    assert "我没有去过后台" in user


def test_creator_prompt_teaches_four_modes_without_new_output_fields():
    system, _ = ModelCallService(settings())._build_prompt(ModelOperation.CREATOR_EDIT, {})
    for mode in ("讨论角度", "起草", "定向改稿", "检查风格"):
        assert mode in system
    assert "未指定部分逐字保留" in system
    assert "包括段落顺序和换行" in system
    assert "两个示例是操作说明，不是可写入稿件的素材" in system
    assert "不把用户采用一次改写自动说成长期偏好" in system
    assert "仍返回完整 title/body，不返回局部补丁" in system
    assert "用户只问“像不像我”" in system
    assert "更新会写入当前选题，不能修改其他资产" in system


def test_qwen_provider_uses_openai_compatible_chat_completions(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [{"message": {"content": '{"painPoints":[]}'}}],
        "usage": {"total_tokens": 12},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="dashscope-key",
            qwen_model="qwen-plus",
        )
    )
    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"})
    )

    assert response.output == {"painPoints": []}
    assert response.model_metadata == {
        "provider": "qwen",
        "modelSource": "response",
        "systemPromptHash": hashlib.sha256(
            FakeAsyncClient.requests[0]["json"]["messages"][0]["content"].encode("utf-8")
        ).hexdigest(),
        "model": "qwen-plus",
        "usage": {"total_tokens": 12},
        "operation": "pain_points",
    }
    request = FakeAsyncClient.requests[0]
    assert request["url"] == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert request["headers"]["authorization"] == "Bearer dashscope-key"
    assert request["json"]["model"] == "qwen-plus"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert request["json"]["messages"][0]["role"] == "system"
    assert request["json"]["messages"][1] == {
        "role": "user",
        "content": "中文评论",
    }


def test_qwen_provider_uses_configured_compatible_base_url_and_parses_fenced_json(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [
            {
                "message": {
                    "content": (
                        "```json\n"
                        '{"painPoints":[{"theme":"预算焦虑","intensity":"高","count":2,"evidence":["太贵了"]}]}'
                        "\n```"
                    )
                }
            }
        ],
        "usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
            qwen_base_url=(
                "https://workspace-id.cn-beijing.maas.aliyuncs.com"
                "/compatible-mode/v1"
            ),
        )
    )

    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "太贵了\n预算不够"})
    )

    assert response.output == {
        "painPoints": [
            {
                "theme": "预算焦虑",
                "intensity": "高",
                "count": 2,
                "evidence": ["太贵了"],
            }
        ]
    }
    assert response.model_metadata["provider"] == "qwen"
    assert response.model_metadata["model"] == "qwen-plus"
    request = FakeAsyncClient.requests[0]
    assert request["url"] == (
        "https://workspace-id.cn-beijing.maas.aliyuncs.com"
        "/compatible-mode/v1/chat/completions"
    )
    assert request["json"]["model"] == "qwen-plus"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert request["json"]["messages"][1] == {
        "role": "user",
        "content": "太贵了\n预算不够",
    }


def test_qwen_provider_repairs_json_wrapped_in_prose(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [
            {
                "message": {
                    "content": (
                        "下面是 JSON 结果：\n"
                        '{"painPoints":[{"theme":"选校焦虑","intensity":"高","count":3,"evidence":["冲不冲"]}]}'
                        "\n以上供参考。"
                    )
                }
            }
        ],
        "usage": {"total_tokens": 42},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "冲不冲"})
    )

    assert response.output["painPoints"][0]["theme"] == "选校焦虑"


def test_qwen_provider_unwraps_structured_result_wrapper(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [
            {
                "message": {
                    "content": (
                        '{"result":{"painPoints":[{"theme":"时间焦虑",'
                        '"intensity":"中","count":1,"evidence":["来不及"]}]}}'
                    )
                }
            }
        ],
        "usage": {"total_tokens": 18},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "来不及"})
    )

    assert response.output["painPoints"][0]["theme"] == "时间焦虑"


def test_qwen_provider_reads_tool_call_arguments_when_content_is_blank(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "structured_response",
                                "arguments": '{"painPoints":[]}',
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"total_tokens": 14},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "中文评论"})
    )

    assert response.output == {"painPoints": []}


def test_qwen_provider_rejects_wrong_structured_root(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [{"message": {"content": '{"items":[]}'}}],
        "usage": {"total_tokens": 12},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    with pytest.raises(
        ValidationError,
        match="Model response for pain_points missing painPoints",
    ):
        asyncio.run(
            service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "太贵了"})
        )


def test_agent_chat_json_requires_proposed_actions_list(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [{"message": {"content": '{"reply":"ok"}'}}],
        "usage": {"total_tokens": 12},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    with pytest.raises(
        ValidationError,
        match="Model response for agent_chat missing proposedActions",
    ):
        asyncio.run(
            service.call_operation(
                ModelOperation.AGENT_CHAT,
                {
                    "agent": {"displayName": "测试 Agent"},
                    "contextPack": {"items": []},
                    "messages": [],
                    "userMessage": "请确认。",
                },
            )
        )


def test_agent_chat_accepts_plain_text_model_reply(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [{"message": {"content": "我已读取当前 workspace context。"}}],
        "usage": {"total_tokens": 16},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    response = asyncio.run(
        service.call_operation(
            ModelOperation.AGENT_CHAT,
            {
                "agent": {"displayName": "测试 Agent"},
                "contextPack": {"items": []},
                "messages": [],
                "userMessage": "请确认。",
            },
        )
    )

    assert response.output == {
        "reply": "我已读取当前 workspace context。",
        "proposedActions": [],
    }
    assert response.model_metadata["operation"] == "agent_chat"


def test_qwen_provider_reports_http_errors(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 400
    FakeAsyncClient.response_body = {"error": {"message": "model not found"}}
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="bad-model",
        )
    )

    with pytest.raises(ValidationError, match=r"Model call failed \(400\)"):
        asyncio.run(
            service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"})
        )


def test_qwen_provider_requires_api_key() -> None:
    service = ModelCallService(settings(model_provider="qwen"))

    with pytest.raises(ValidationError, match="QWEN_API_KEY or DASHSCOPE_API_KEY"):
        asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"comments": ""}))


def test_anthropic_provider_remains_supported(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "claude-sonnet-4-20250514",
        "content": [{"type": "text", "text": '{"painPoints":[]}'}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="anthropic",
            anthropic_api_key="anthropic-key",
            anthropic_model="claude-sonnet-4-20250514",
        )
    )
    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"})
    )

    assert response.output == {"painPoints": []}
    assert response.model_metadata["provider"] == "anthropic"
    request = FakeAsyncClient.requests[0]
    assert request["url"] == "https://api.anthropic.com/v1/messages"
    assert request["headers"]["x-api-key"] == "anthropic-key"


def test_anthropic_provider_can_use_compatible_base_url(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-anthropic-compatible",
        "content": [{"type": "text", "text": '{"painPoints":[]}'}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="anthropic",
            anthropic_api_key="compatible-key",
            anthropic_model="qwen-compatible",
            anthropic_base_url="https://example.test/apps/anthropic",
        )
    )

    asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"}))

    request = FakeAsyncClient.requests[0]
    assert request["url"] == "https://example.test/apps/anthropic/v1/messages"
    assert request["headers"]["x-api-key"] == "compatible-key"
    assert request["json"]["model"] == "qwen-compatible"


def test_anthropic_provider_can_use_exact_messages_url(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-anthropic-compatible",
        "content": [{"type": "text", "text": '{"painPoints":[]}'}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="anthropic",
            anthropic_api_key="compatible-key",
            anthropic_model="qwen-compatible",
            anthropic_messages_url="https://example.test/apps/anthropic/v1/messages",
        )
    )

    asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"}))

    request = FakeAsyncClient.requests[0]
    assert request["url"] == "https://example.test/apps/anthropic/v1/messages"

import asyncio
import hashlib
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
    assert "不要把学校导师的关心写成实习团队的特点" in system
    assert "你擅长写清支持与成长的具体过程" in system
    assert "不要说作者已用该理论解决技术问题" in system
    assert "语气真诚、积极、有鼓励感" in system
    assert context["historicalPosts"] in user


def test_profile_prompt_teaches_short_contiguous_quotes_without_banning_source_ellipsis():
    system, _ = ModelCallService(settings())._build_prompt(ModelOperation.PROFILE, {})
    assert "建议 10～40 字" in system
    assert "分成两个 evidence" in system
    assert "不可改成“先核对费用……预留时间”" in system
    assert "原文本来有省略号可以照抄" in system


def test_profile_review_handles_missing_metrics_and_scene_specific_claims():
    system, user = ModelCallService(settings())._build_prompt(ModelOperation.PROFILE, {
        "historicalPosts": "毕业记录：赞 3，分享 None。学校与工作是两段经历。",
    })
    assert "跨场景的材料可以支持共同的写作方式" in system
    assert "依据也须来自该场景" in system
    assert "省略该项或写“未提供”" in system
    assert "不能原样输出 None/null，也不能补零" in system
    assert "没有超出互动数字本身的具体内容依据就留空" in system
    assert "可以肯定它的记录价值" in system
    assert "样例仅示范表达方法，不是输入账号的事实" in system
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
    assert "核心表达、具体例子或论据、标题承诺" in system
    assert "不要求每篇都有冲突、金句或固定篇幅" in system
    assert "参考哪篇的什么做法 → 什么情况下可复用 → 下次可尝试的具体调整" in system
    assert "沿用字符串数组，不新增字段" in system
    assert "假设示例（不是本账号事实）" in system
    assert user == (
        "账号定位：\n本人经验分享\n\n历史笔记：\n"
        "笔记甲：赞 0，收藏 8；正文是一次选择的取舍。"
    )


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
    assert "复盘方法：先认识账号" in request["messages"][0]["content"]
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

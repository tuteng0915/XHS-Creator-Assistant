import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.errors import ValidationError
from app.main import create_app
from app.models import ModelCallResponse, ModelOperation
from app.services.content_collaboration import CollaborationMessage
from app.services.content_collaboration_provider import RealContentCollaborationProvider


class FakeModelCallService:
    def __init__(self, output: dict, *, provider: str = "qwen") -> None:
        self.settings = SimpleNamespace(model_provider=provider)
        self.output = output
        self.calls: list[tuple[ModelOperation, dict]] = []

    async def call_operation(self, operation: ModelOperation, context: dict) -> ModelCallResponse:
        self.calls.append((operation, context))
        return ModelCallResponse(
            output=self.output,
            model_metadata={
                "provider": "qwen",
                "model": "qwen-plus",
                "operation": operation.value,
                "systemPromptHash": "prompt-hash",
                "usage": {"total_tokens": 24},
            },
        )


def frozen_context() -> tuple[CollaborationMessage, dict]:
    message = CollaborationMessage(
        id="creator-1",
        sender="creator",
        to="research",
        content="请先核对这段经历能否支撑这个选题。",
    )
    return message, {
        "target": {
            "assetType": "topic",
            "assetId": "topic-1",
            "title": "把一次选择讲清楚",
            "body": "我先写了当时为何犹豫，再写最后如何决定。",
            "angle": "用一次真实选择说明判断过程",
        },
        "sessionContext": {
            "workspaceContext": {
                "snapshot": {"contentHash": "frozen-pack"},
                "contextEnvelope": {"operation": "content_collaboration"},
                "omitted": [{"reason": "no images"}],
                "items": [
                    {
                        "key": "account_profile",
                        "data": {"accountPositioning": "诚实记录成长中的选择"},
                    }
                ],
            }
        },
        "transcript": [message.model_dump()],
        "transcriptTruncated": False,
    }


def writing_handoff_context() -> tuple[CollaborationMessage, dict]:
    research = CollaborationMessage(
        id="research-1",
        sender="research",
        to="writing",
        content="可围绕‘先写犹豫，再写决定’组织判断过程。",
        reply_to="creator-1",
    )
    _, context = frozen_context()
    context["transcript"] = [*context["transcript"], research.model_dump()]
    context["upstreamCandidates"] = [
        {
            "candidateId": "research-1:0",
            "kind": "evidence",
            "title": "可写的经历顺序",
            "body": "先交代犹豫，再呈现最后如何决定。",
            "confidence": "supported",
            "evidenceRefs": [
                {"sourceId": "target:topic", "quote": "先写了当时为何犹豫"}
            ],
        }
    ]
    context["sessionContext"]["workspaceContext"]["items"].extend(
        [
            {
                "key": "analysis_history_overview",
                "data": [{"summary": "历史笔记使用具体场景解释选择"}],
            },
            {
                "key": "draft_history_overview",
                "data": [{"title": "旧草稿", "summary": "叙事较快进入结论"}],
            },
        ]
    )
    return research, context


def test_live_provider_projects_frozen_context_and_preserves_model_receipt() -> None:
    message, context = frozen_context()
    model = FakeModelCallService(
        {
            "turn": {
                "summary": "现有材料能支撑‘如何决定’，但还缺少取舍标准的原话。",
                "nextRecipient": "writing",
                "candidateSuggestions": [
                    {
                        "kind": "evidence",
                        "title": "已经可用的经历线索",
                        "body": "可先保留‘先写犹豫，再写决定’这一真实顺序。",
                        "confidence": "supported",
                        "evidenceRefs": [
                            {"sourceId": "target:topic", "quote": "先写了当时为何犹豫"}
                        ],
                    },
                    {
                        "kind": "open_question",
                        "title": "还需要补的判断标准",
                        "body": "当时最关键的取舍标准是什么？",
                        "confidence": "needs_creator",
                        "evidenceRefs": [],
                    },
                ],
            }
        }
    )

    turn = asyncio.run(
        RealContentCollaborationProvider(model).run(
            role="research", message=message, context=context
        )
    )

    assert turn.to == "writing"
    assert "已经可用的经历线索" in turn.content
    assert turn.model_metadata["provider"] == "qwen"
    assert turn.model_metadata["candidateSuggestions"][0]["kind"] == "evidence"
    operation, projected = model.calls[0]
    assert operation == ModelOperation.CONTENT_COLLABORATION_TURN
    assert projected["schemaVersion"] == "content-collaboration-role-packet/v2"
    assert "sessionContext" not in projected
    assert projected["creativeBrief"]["target"]["title"] == "把一次选择讲清楚"
    assert projected["roleTask"]["stage"] == "evidence_to_writing_brief"
    assert projected["upstreamHandoff"]["sourceId"] == "message:creator-1"
    assert {source["id"] for source in projected["evidence"]["allowedSources"]} >= {
        "target:topic",
        "workspace:account_profile",
        "message:creator-1",
    }


def test_writing_receives_retrieved_research_candidates_and_original_evidence() -> None:
    message, context = writing_handoff_context()
    model = FakeModelCallService(
        {
            "turn": {
                "summary": "把研究确认的经历顺序变成四步叙事，交给评审检查。",
                "nextRecipient": "review",
                "usedCandidateIds": ["research-1:0"],
                "candidateSuggestions": [
                    {
                        "kind": "outline",
                        "title": "从犹豫到决定的判断线",
                        "body": (
                            "开场：交代犹豫；推进：写出两个方向的拉扯；转折：落在最终判断；"
                            "收束：让读者带走判断过程。"
                        ),
                        "confidence": "supported",
                        "evidenceRefs": [
                            {"sourceId": "target:topic", "quote": "再写最后如何决定"}
                        ],
                    }
                ],
            }
        }
    )

    turn = asyncio.run(
        RealContentCollaborationProvider(model).run(
            role="writing", message=message, context=context
        )
    )

    assert turn.to == "review"
    assert turn.model_metadata["usedCandidateIds"] == ["research-1:0"]
    _, packet = model.calls[0]
    assert packet["roleTask"]["stage"] == "evidence_to_readable_structure"
    assert packet["upstreamHandoff"]["candidates"][0]["candidateId"] == "research-1:0"
    assert "target:topic" in {
        source["id"] for source in packet["evidence"]["allowedSources"]
    }
    assert "workspace:analysis_history_overview" not in {
        source["id"] for source in packet["evidence"]["allowedSources"]
    }
    # The upstream evidence reference is deliberately pulled back in even
    # though writing normally receives a smaller source slice than research.
    assert "target:topic" in packet["evidence"]["sourceGroups"]["creativeBrief"]


def test_writing_with_an_upstream_handoff_must_name_the_candidate_it_uses() -> None:
    message, context = writing_handoff_context()
    model = FakeModelCallService(
        {
            "turn": {
                "summary": "这里有一份结构。",
                "nextRecipient": "review",
                "candidateSuggestions": [
                    {
                        "kind": "outline",
                        "title": "结构",
                        "body": "开场写犹豫；推进写取舍；转折写决定；收束写判断。",
                        "confidence": "supported",
                        "evidenceRefs": [
                            {"sourceId": "target:topic", "quote": "再写最后如何决定"}
                        ],
                    }
                ],
            }
        }
    )

    with pytest.raises(ValidationError, match="必须明确使用至少一条上游候选"):
        asyncio.run(
            RealContentCollaborationProvider(model).run(
                role="writing", message=message, context=context
            )
        )


@pytest.mark.parametrize(
    "output, expected",
    [
        (
            {
                "turn": {
                    "summary": "越权路由",
                    "nextRecipient": "review",
                    "candidateSuggestions": [],
                }
            },
            "research 不能将本轮交接给 review",
        ),
        (
            {
                "turn": {
                    "summary": "错误来源",
                    "nextRecipient": "creator",
                    "candidateSuggestions": [
                        {
                            "kind": "evidence",
                            "title": "无效",
                            "body": "不应接受。",
                            "confidence": "supported",
                            "evidenceRefs": [{"sourceId": "outside", "quote": "不存在"}],
                        }
                    ],
                }
            },
            "未提供的冻结来源",
        ),
        (
            {
                "turn": {
                    "summary": "假引文",
                    "nextRecipient": "creator",
                    "candidateSuggestions": [
                        {
                            "kind": "evidence",
                            "title": "错误",
                            "body": "不应接受。",
                            "confidence": "supported",
                            "evidenceRefs": [
                                {"sourceId": "target:topic", "quote": "我从未写过的句子"}
                            ],
                        }
                    ],
                }
            },
            "逐字定位",
        ),
        (
            {
                "turn": {
                    "summary": "不明确推断",
                    "nextRecipient": "creator",
                    "candidateSuggestions": [
                        {
                            "kind": "evidence",
                            "title": "错误类型",
                            "body": "可以把它写成系列。",
                            "confidence": "inference",
                            "evidenceRefs": [],
                        }
                    ],
                }
            },
            "明确标记为推断或待验证",
        ),
        (
            {
                "turn": {
                    "summary": "多余字段",
                    "nextRecipient": "creator",
                    "candidateSuggestions": [],
                },
                "topic": {"title": "不得写入"},
            },
            "返回格式不符合",
        ),
    ],
)
def test_live_provider_fails_closed_for_invalid_handoff(output: dict, expected: str) -> None:
    message, context = frozen_context()
    model = FakeModelCallService(output)
    with pytest.raises(ValidationError, match=expected):
        asyncio.run(
            RealContentCollaborationProvider(model).run(
                role="research", message=message, context=context
            )
        )
    assert len(model.calls) == 1


def test_live_provider_never_switches_to_non_qwen_global_provider() -> None:
    message, context = frozen_context()
    model = FakeModelCallService({"turn": {}}, provider="anthropic")
    with pytest.raises(ValidationError, match="仅支持已配置的 DeepSeek / Qwen"):
        asyncio.run(
            RealContentCollaborationProvider(model).run(
                role="research", message=message, context=context
            )
        )
    assert model.calls == []


def test_app_does_not_silently_force_qwen_when_another_provider_is_explicit(settings) -> None:
    application = create_app(
        replace(settings, model_provider="anthropic", qwen_api_key="test-qwen-key",
                deepseek_api_key="test-deepseek-key")
    )
    provider = application.state.content_collaboration_service.live_provider
    assert isinstance(provider, RealContentCollaborationProvider)
    assert provider.model_call_service.settings.model_provider == "anthropic"
    assert provider.writing_model_call_service.settings.model_provider == "deepseek"

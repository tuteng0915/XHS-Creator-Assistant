import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_content_collaboration_sessions import create_workspace_and_topic, until

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import (
    ContentCollaborationMessageCreate,
    ContentCollaborationSessionCreate,
    CreatorContextSelection,
    ModelCallResponse,
    ModelOperation,
    TextSourceMaterialCreate,
)
from app.repositories.analysis_runs import AnalysisRunRepository
from app.services.common import utc_now
from app.services.content_collaboration import CollaborationMessage, SpecialistTurn
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.model_calls import PROMPT_SINGLE_CREATOR_WRITING


class WriterRecorder:
    def __init__(self):
        self.calls = []

    async def run(self, *, role, message, context):
        self.calls.append((role, message, context))
        # Even a legacy injected provider requesting a handoff gets only one call.
        return SpecialistTurn(content=f"方案 {message.content}", to="review")


def setup_writer(app):
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    provider = WriterRecorder()
    service.live_provider = provider
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate(
            assistant_mode="single_writer",
            context_target={"assetType": "topic", "assetId": topic["id"]},
        ),
    )
    return workspace, topic, service, provider, session


def analysis(
    app, workspace_id, *, marker="选中账号结果", status="completed", kind="account_analysis"
):
    now = utc_now()
    if kind == "account_analysis":
        with app.state.database.transaction() as c:
            row = AnalysisRunRepository().create(
                c,
                workspace_id=workspace_id,
                workflow_type="account_diagnosis",
                input_snapshot_json=json.dumps({"secret": "原始评论不得进入"}),
                idempotency_key=None,
                now=now,
            )
            c.execute(
                "UPDATE analysis_runs SET status=?,stage_results_json=?,completed_at=? WHERE id=?",
                (
                    status,
                    json.dumps(
                        {
                            "profile": {"summary": marker},
                            "pain_points": {},
                            "topics": [{"title": "历史选题不进入"}],
                        }
                    ),
                    now,
                    row["id"],
                ),
            )
            return {"kind": kind, "id": row["id"]}
    material = app.state.source_service.create_text(
        workspace_id,
        TextSourceMaterialCreate(
            type="historical_posts",
            name="受众材料",
            content="原始笔记不得进入",
        ),
    )
    item_id = str(uuid4())
    with app.state.database.transaction() as c:
        c.execute(
            "INSERT INTO audience_analyses(id,workspace_id,source_material_id,status,"
            "input_snapshot_json,result_json,created_at,completed_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                item_id,
                workspace_id,
                material.id,
                status,
                '{"secret":"原始评论不得进入"}',
                json.dumps({"groups": [{"id": "reader", "name": marker}]}),
                now,
                now,
            ),
        )
    return {"kind": kind, "id": item_id}


def payload(key, references=(), **extra):
    return ContentCollaborationMessageCreate(
        content=key,
        recipient="writing",
        request_key=key,
        creator_context_selection={"references": list(references)},
        **extra,
    )


async def send(service, workspace_id, session_id, request):
    await service.send_message(workspace_id, session_id, request)
    await until(
        lambda: service.get(workspace_id, session_id).execution_status not in {"queued", "running"}
    )
    return service.get(workspace_id, session_id)


def test_single_writer_empty_context_never_builds_workspace_pack(app, monkeypatch):
    monkeypatch.setattr(
        app.state.content_collaboration_service.context_access_service,
        "build_workspace_pack",
        lambda *a, **k: pytest.fail("no overview read"),
    )
    workspace, _, service, provider, session = setup_writer(app)
    assert session.assistant_mode == "single_writer"
    assert session.context_revision == 0
    assert session.creator_context_selection.references == []
    result = asyncio.run(send(service, workspace["id"], session.id, payload("先聊角度")))
    assert len(provider.calls) == 1
    role, _, context = provider.calls[0]
    assert role == "writing"
    assert set(context["target"]) == {"assetType", "assetId", "title", "body", "updatedAt"}
    encoded = json.dumps(context, ensure_ascii=False)
    assert "具体、真诚地分享选择过程" not in encoded
    assert "workspaceContext" not in encoded
    assert "不知道如何讲清经历" not in encoded
    assert context["sessionContext"]["creatorContextSnapshot"]["references"] == []
    assert result.context_revision == 1
    assert len(result.messages) == 2
    assert result.messages[-1].recipient == "creator"
    assert result.runs[0].input_snapshot["maxTurns"] == 1
    assert service.list(workspace["id"])[0].context_revision == 1


def test_selected_exact_results_freeze_without_raw_input_or_related_topics(app):
    workspace, _, service, provider, session = setup_writer(app)
    chosen = analysis(app, workspace["id"])
    audience = analysis(app, workspace["id"], kind="audience_analysis", marker="选中读者结果")
    analysis(app, workspace["id"], marker="没有选择的记录")
    result = asyncio.run(
        send(service, workspace["id"], session.id, payload("起草", [audience, chosen]))
    )
    context = provider.calls[0][2]
    encoded = json.dumps(context, ensure_ascii=False)
    assert "选中账号结果" in encoded and "选中读者结果" in encoded
    for forbidden in ("没有选择的记录", "原始评论不得进入", "原始笔记不得进入", "历史选题不进入"):
        assert forbidden not in encoded
    snapshot = result.runs[0].input_snapshot
    with app.state.database.transaction() as c:
        c.execute("UPDATE analysis_runs SET user_notes='后来复盘备注' WHERE id=?", (chosen["id"],))
    assert service.get(workspace["id"], session.id).runs[0].input_snapshot == snapshot
    assert len(snapshot["sessionContext"]["creatorContextSnapshot"]["references"]) == 2
    assert all(
        item["sourceVersion"]
        for item in snapshot["sessionContext"]["creatorContextSnapshot"]["references"]
    )


def test_selection_change_and_change_back_start_new_transcript_segments(app):
    workspace, _, service, provider, session = setup_writer(app)
    chosen = analysis(app, workspace["id"])
    audience = analysis(app, workspace["id"], kind="audience_analysis")

    async def run():
        await send(service, workspace["id"], session.id, payload("旧段一", [chosen, audience]))
        await send(
            service, workspace["id"], session.id, payload("旧段二", [audience, chosen, chosen])
        )
        await send(service, workspace["id"], session.id, payload("无参考段"))
        return await send(
            service, workspace["id"], session.id, payload("重新加回", [chosen, audience])
        )

    result = asyncio.run(run())
    contexts = [item[2] for item in provider.calls]
    assert [item["sessionContext"]["contextRevision"] for item in contexts] == [1, 1, 2, 3]
    assert "旧段一" in json.dumps(contexts[1], ensure_ascii=False)
    assert [item["content"] for item in contexts[2]["transcript"]] == ["无参考段"]
    assert [item["content"] for item in contexts[3]["transcript"]] == ["重新加回"]
    assert all(item["upstreamCandidates"] == [] for item in contexts)
    assert len(result.messages) == 8  # Old segments remain readable.
    assert result.context_revision == 3


@pytest.mark.parametrize(
    "problem", ["missing", "other_workspace", "pending", "failed", "partially_completed"]
)
def test_invalid_reference_fails_before_model_and_message_append(app, problem):
    workspace, _, service, provider, session = setup_writer(app)
    if problem == "missing":
        reference = {"kind": "account_analysis", "id": "missing"}
    elif problem == "other_workspace":
        other, _ = create_workspace_and_topic(app)
        reference = analysis(app, other["id"])
    else:
        reference = analysis(app, workspace["id"], status=problem)
    with pytest.raises((ValidationError, NotFoundError)):
        asyncio.run(
            service.send_message(workspace["id"], session.id, payload(problem, [reference]))
        )
    assert provider.calls == []
    assert service.get(workspace["id"], session.id).messages == []


def test_oversized_reference_is_rejected_not_silently_excerpted(app):
    workspace, _, service, provider, session = setup_writer(app)
    reference = analysis(app, workspace["id"], marker="长" * 49_000)
    with pytest.raises(ValidationError, match="参考材料过多"):
        asyncio.run(service.send_message(workspace["id"], session.id, payload("超限", [reference])))
    assert not provider.calls


@pytest.mark.parametrize("location", ["input_snapshot_json", "model_metadata_json"])
def test_account_reference_preserves_authored_showcase_origin(app, location):
    workspace, _, service, provider, session = setup_writer(app)
    reference = analysis(app, workspace["id"])
    with app.state.database.transaction() as c:
        c.execute(
            f"UPDATE analysis_runs SET {location}=? WHERE id=?",
            (
                json.dumps({"origin": "oracle_showcase", "privateDiagnostic": "do not send"}),
                reference["id"],
            ),
        )
    result = asyncio.run(
        send(service, workspace["id"], session.id, payload("用这个示例", [reference]))
    )
    frozen = result.runs[0].input_snapshot["sessionContext"]["creatorContextSnapshot"][
        "references"
    ][0]
    assert frozen["sourceOrigin"] == "oracle_showcase"
    assert "privateDiagnostic" not in json.dumps(provider.calls[0][2])


def test_explicit_selection_required_and_idempotency_includes_canonical_references(app):
    workspace, _, service, provider, session = setup_writer(app)
    chosen = analysis(app, workspace["id"])

    async def run():
        with pytest.raises(ValidationError, match="明确本轮参考"):
            await service.send_message(
                workspace["id"],
                session.id,
                ContentCollaborationMessageCreate(
                    content="缺选择",
                    recipient="writing",
                    request_key="missing-selection",
                ),
            )
        request = payload("同一个请求", [chosen])
        first = await send(service, workspace["id"], session.id, request)
        replay = await service.send_message(
            workspace["id"], session.id, payload("同一个请求", [chosen, chosen])
        )
        assert len(first.messages) == len(replay.messages)
        with pytest.raises(ConflictError):
            await service.send_message(workspace["id"], session.id, payload("同一个请求"))

    asyncio.run(run())
    assert len(provider.calls) == 1


def test_single_writer_local_rewrite_preserves_scope_without_other_context(app):
    workspace, topic, service, provider, session = setup_writer(app)
    with app.state.database.transaction() as c:
        c.execute(
            "UPDATE topics SET body='保留前文。只改这里。保留后文。' WHERE id=?", (topic["id"],)
        )
    request = payload(
        "精修",
        writing_focus={
            "expectedUpdatedAt": topic["updated_at"],
            "selection": {"start": 5, "end": 10, "text": "只改这里。"},
        },
    )
    result = asyncio.run(send(service, workspace["id"], session.id, request))
    assert provider.calls[0][2]["writingFocus"]["selection"]["text"] == "只改这里。"
    assert result.messages[-1].model_metadata["writingFocus"]["selection"]["text"] == "只改这里。"


def test_single_writer_provider_selects_non_team_prompt_and_all_explicit_sources(app):
    class FakeCalls:
        settings = SimpleNamespace(model_provider="qwen")
        calls = []

        async def call_operation(self, operation, context):
            self.calls.append(context)
            return ModelCallResponse(
                output={
                    "turn": {
                        "summary": "把转折放在判断之后。",
                        "nextRecipient": "creator",
                        "usedCandidateIds": [],
                        "candidateSuggestions": [
                            {
                                "kind": "copy_option",
                                "title": "建议版本",
                                "body": "直接可用的新表达",
                                "confidence": "inference",
                                "evidenceRefs": [],
                            }
                        ],
                    }
                },
                model_metadata={"provider": "qwen"},
            )

    calls = FakeCalls()
    message = CollaborationMessage(sender="creator", to="writing", content="改一下")
    context = {
        "assistantMode": "single_writer",
        "target": {"title": "当前稿", "body": "原文"},
        "sessionContext": {
            "workspaceContext": {"items": [{"key": "account_profile", "data": "不应该读取"}]},
            "creatorContextSnapshot": {
                "references": [
                    {
                        "kind": "account_analysis",
                        "id": "a",
                        "content": {"summary": "全部选中内容" * 500},
                        "sourceOrigin": "oracle_showcase",
                    }
                ]
            },
        },
        "transcript": [message.model_dump(), {"id": "old-ai", "sender": "writing",
                                              "content": "我去年做过未经确认的事。"}],
        "upstreamCandidates": [],
    }
    turn = asyncio.run(
        RealContentCollaborationProvider(calls).run(
            role="writing", message=message, context=context
        )
    )
    assert turn.to == "creator"
    assert len(calls.calls) == 1
    packet = calls.calls[0]
    assert packet["assistantMode"] == "single_writer"
    assert "upstreamHandoff" not in packet
    assert "不应该读取" not in json.dumps(packet, ensure_ascii=False)
    assert "全部选中内容" * 500 in json.dumps(packet, ensure_ascii=False)
    assert "oracle_showcase" in json.dumps(packet, ensure_ascii=False)
    assert packet["evidence"]["sourceGroups"]["analysisObservationsNotPersonalFacts"] == [
        "reference:account_analysis:a",
    ]
    assert packet["evidence"]["sourceGroups"]["creatorDialogue"] == [f"message:{message.id}"]
    assert not any(item["id"] == "message:old-ai"
                   for item in packet["evidence"]["allowedSources"])
    assert "previousSuggestions" not in packet
    assert packet["conversation"] == [
        {"sourceId": "message:old-ai", "role": "assistant", "content": "我去年做过未经确认的事。"},
        {"sourceId": f"message:{message.id}", "role": "user", "content": "改一下"},
    ]
    assert "历史评论者" in next(item for item in packet["evidence"]["allowedSources"]
                            if item["id"] == "reference:account_analysis:a")["useBoundary"]
    system, _ = app.state.model_call_service._build_prompt(
        ModelOperation.CONTENT_COLLABORATION_TURN,
        packet,
    )
    assert system == PROMPT_SINGLE_CREATOR_WRITING
    assert "research" not in system


def test_selection_reference_count_limit_and_legacy_compatibility(app):
    with pytest.raises(ValueError):
        CreatorContextSelection(
            references=[{"kind": "account_analysis", "id": str(i)} for i in range(9)]
        )
    workspace, topic = create_workspace_and_topic(app)
    session = app.state.content_collaboration_service.create(
        workspace["id"],
        ContentCollaborationSessionCreate(
            context_target={"assetType": "topic", "assetId": topic["id"]},
        ),
    )
    assert session.assistant_mode == "legacy_team"
    assert session.creator_context_selection is None
    assert "workspaceContext" in session.initial_context_snapshot


def test_single_writer_keeps_full_bounded_conversation_message_text():
    text = "作者补充" * 1_000 + "结尾不能遗漏"
    context = {
        "assistantMode": "single_writer",
        "transcript": [{"id": "prior", "sender": "creator", "to": "writing", "content": text}],
    }
    sources = RealContentCollaborationProvider._allowed_sources(context)
    assert sources["message:prior"]["text"] == text


def test_single_writer_prompt_states_reference_shape_and_fact_preserving_edit_scope():
    # This checks instructions and wire shape, not whether a real rewrite is
    # semantically faithful. That still needs a separately observed model check.
    prompt = PROMPT_SINGLE_CREATOR_WRITING
    assert "evidenceRefs 用对象数组" in prompt
    assert '{"sourceId":"本轮允许的来源ID","quote":"来源中的逐字原句"}' in prompt
    assert "纯写法建议可用空数组" in prompt
    assert "通过句序、动词、节奏、衔接或删冗" in prompt
    assert "观点可以鲜明、可以跨篇提炼" in prompt
    assert "confidence=inference 也不授权虚构" in prompt
    assert "从零起草也遵守事实边界" in prompt
    assert "助手旧回复不证明作者做过什么" in prompt
    assert "摘要只说本版的写作取舍" in prompt
    assert "copy_option.title 写文章标题" in prompt
    assert "整篇首稿或整篇重写" in prompt
    assert '"title":"建议版本"' not in prompt
    assert "title 和 body 填本轮实际成果" in prompt
    assert "读者条件、时限、数量、规则、经历与结果按其原有来源使用" in prompt
    # No concrete test story is embedded in the general writing instructions.
    assert "幻灯片" not in prompt
    assert "同事" not in prompt
    assert "系统下周关闭" not in prompt
    assert "我去年对照两边课程表" not in prompt


def test_single_writer_wire_still_rejects_string_evidence_references():
    from pydantic import ValidationError as PydanticValidationError

    from app.services.content_collaboration_provider import _WireOutput

    with pytest.raises(PydanticValidationError):
        _WireOutput.model_validate(
            {
                "turn": {
                    "summary": "建议改稿",
                    "nextRecipient": "creator",
                    "usedCandidateIds": [],
                    "candidateSuggestions": [
                        {
                            "kind": "copy_option",
                            "title": "建议版本",
                            "body": "替换文字",
                            "confidence": "inference",
                            "evidenceRefs": ["target:topic"],
                        }
                    ],
                }
            }
        )

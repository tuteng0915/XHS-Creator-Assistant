from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    DraftGenerateRequest,
    DraftKind,
    DraftResponse,
    DraftStatus,
    ModelOperation,
)
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.drafts import DraftRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now
from app.services.drafts import DraftService
from app.services.model_calls import ModelCallService
from app.workflows.account_diagnosis import StructureStageResult


class StructureModelProvider(Protocol):
    async def content_brief(self, *, context: dict[str, Any]) -> dict[str, Any]: ...

    async def structure(self, *, context: dict[str, Any]) -> dict[str, Any]: ...


class FakeStructureModelProvider:
    async def content_brief(self, *, context: dict[str, Any]) -> dict[str, Any]:
        topic = context.get("topic")
        topic_title = str(
            topic.get("title") if isinstance(topic, dict) else context.get("topic", "")
        )
        angle = str(topic.get("angle", "") if isinstance(topic, dict) else "")
        return {
            "brief": {
                "topicTitle": topic_title,
                "refinedAngle": angle or f"把「{topic_title}」收束成一个可执行判断框架",
                "targetReader": "正在做内容决策但缺少判断标准的目标读者",
                "readerPain": "知道问题重要，但不知道如何判断、如何行动。",
                "contentPromise": "看完后能获得一套清晰判断标准和下一步行动清单。",
                "corePoint": "用具体标准替代泛泛建议，让读者能自己做判断。",
                "formatRecommendation": "小红书图文笔记 / 清单型结构",
                "openingHook": f"先抛出一个和「{topic_title}」直接相关的真实困惑。",
                "argumentPath": ["提出读者困惑", "拆解判断标准", "给出行动清单"],
                "materialNeeds": ["真实案例", "评论区原话", "反例或常见误区"],
                "titleDirections": [
                    f"{topic_title}：真正要先判断的 3 件事",
                    f"别急着做{topic_title}，先看这个标准",
                ],
                "cta": "引导读者收藏并留言补充自己的情况。",
                "risks": ["避免制造焦虑", "避免把个案包装成普适结论"],
                "revisionSuggestions": ["补一个具体例子", "把标题承诺和正文结构对齐"],
            }
        }

    async def structure(self, *, context: dict[str, Any]) -> dict[str, Any]:
        topic = str(context.get("topic") or "")
        background = str(context.get("background") or "")
        return {
            "structure": {
                "topicChosen": topic,
                "outline": [
                    {"sec": "开场钩子", "ct": f"用一个具体问题切入：{topic}"},
                    {"sec": "核心拆解", "ct": "分步骤说明判断标准、执行路径和常见误区。"},
                    {"sec": "行动收束", "ct": "给出读者可以立即收藏或执行的清单。"},
                ],
                "reuse": background or "问题切入 → 标准拆解 → 行动清单。",
            }
        }


class RealStructureModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def content_brief(self, *, context: dict[str, Any]) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.CONTENT_BRIEF,
            context,
        )
        return response.output

    async def structure(self, *, context: dict[str, Any]) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.STRUCTURE,
            context,
        )
        return response.output


class ContentBriefData(BaseModel):
    topicTitle: str = ""
    refinedAngle: str = ""
    targetReader: str = ""
    readerPain: str = ""
    contentPromise: str = ""
    corePoint: str = ""
    formatRecommendation: str = ""
    openingHook: str = ""
    argumentPath: list[str] = Field(default_factory=list)
    materialNeeds: list[str] = Field(default_factory=list)
    titleDirections: list[str] = Field(default_factory=list)
    cta: str = ""
    risks: list[str] = Field(default_factory=list)
    revisionSuggestions: list[str] = Field(default_factory=list)


class ContentBriefStageResult(BaseModel):
    brief: ContentBriefData


class DraftGenerationService:
    def __init__(
        self,
        database: SQLiteDatabase,
        draft_repository: DraftRepository,
        draft_service: DraftService,
        workspace_repository: WorkspaceRepository,
        topic_repository: TopicRepository,
        analysis_repository: AnalysisRunRepository,
        fake_provider: StructureModelProvider,
        live_provider: StructureModelProvider,
    ) -> None:
        self.database = database
        self.draft_repository = draft_repository
        self.draft_service = draft_service
        self.workspace_repository = workspace_repository
        self.topic_repository = topic_repository
        self.analysis_repository = analysis_repository
        self.fake_provider = fake_provider
        self.live_provider = live_provider

    async def generate_from_topic(
        self, topic_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        return await self._generate(
            topic_id,
            payload,
            kind=DraftKind.CONTENT_STRUCTURE,
            operation_key="structure",
        )

    async def generate_brief_from_topic(
        self, topic_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        return await self._generate(
            topic_id,
            payload,
            kind=DraftKind.CONTENT_BRIEF,
            operation_key="brief",
        )

    async def generate_structure_from_brief(
        self, draft_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        with self.database.read() as connection:
            brief_draft = self.draft_repository.get(connection, draft_id)
            if brief_draft["kind"] != DraftKind.CONTENT_BRIEF.value:
                raise ValidationError("Only content brief drafts can generate structure")
            topic = self.topic_repository.get(connection, brief_draft["topic_id"])
            workspace = self.workspace_repository.get(connection, topic["workspace_id"])
            source_run = (
                self.analysis_repository.get(connection, topic["source_analysis_run_id"])
                if topic["source_analysis_run_id"]
                else None
            )

        input_snapshot = self._input_snapshot(workspace, topic, source_run, payload.mode)
        input_snapshot["sourceBrief"] = {
            "draftId": brief_draft["id"],
            "kind": brief_draft["kind"],
            "editableContent": json.loads(brief_draft["editable_content_json"]),
        }
        context = self._model_context(input_snapshot, DraftKind.CONTENT_STRUCTURE)
        provider = self.live_provider if payload.mode == "live" else self.fake_provider
        status = DraftStatus.COMPLETED
        generated_snapshot: dict[str, Any] = {}
        stage_errors: dict[str, str] = {}
        model_metadata = {
            "engine": "draft_generation",
            "mode": payload.mode,
            "kind": DraftKind.CONTENT_STRUCTURE.value,
            "sourceBriefDraftId": brief_draft["id"],
        }
        completed_at: str | None = utc_now()
        try:
            output = await provider.structure(context=context)
            generated_snapshot = StructureStageResult.model_validate(output).model_dump(
                mode="json"
            )
        except Exception as error:
            status = DraftStatus.FAILED
            stage_errors["structure"] = self._error_message(error)
            completed_at = utc_now()

        now = utc_now()
        with self.database.transaction() as connection:
            row = self.draft_repository.create(
                connection,
                workspace_id=topic["workspace_id"],
                topic_id=topic["id"],
                kind=DraftKind.CONTENT_STRUCTURE.value,
                source_analysis_run_id=topic["source_analysis_run_id"],
                source_workflow=topic["source_workflow"],
                status=status.value,
                generated_snapshot_json=json.dumps(
                    generated_snapshot, ensure_ascii=False
                ),
                editable_content_json=json.dumps(
                    generated_snapshot, ensure_ascii=False
                ),
                input_snapshot_json=json.dumps(input_snapshot, ensure_ascii=False),
                stage_errors_json=json.dumps(stage_errors, ensure_ascii=False),
                model_metadata_json=json.dumps(model_metadata, ensure_ascii=False),
                now=now,
                completed_at=completed_at,
            )
        return self.draft_service._to_response(row)

    async def _generate(
        self,
        topic_id: str,
        payload: DraftGenerateRequest,
        *,
        kind: DraftKind,
        operation_key: str,
    ) -> DraftResponse:
        with self.database.read() as connection:
            topic = self.topic_repository.get(connection, topic_id)
            workspace = self.workspace_repository.get(connection, topic["workspace_id"])
            source_run = (
                self.analysis_repository.get(connection, topic["source_analysis_run_id"])
                if topic["source_analysis_run_id"]
                else None
            )

        input_snapshot = self._input_snapshot(workspace, topic, source_run, payload.mode)
        context = self._model_context(input_snapshot, kind)
        provider = self.live_provider if payload.mode == "live" else self.fake_provider
        status = DraftStatus.COMPLETED
        generated_snapshot: dict[str, Any] = {}
        stage_errors: dict[str, str] = {}
        model_metadata = {
            "engine": "draft_generation",
            "mode": payload.mode,
            "kind": kind.value,
        }
        completed_at: str | None = utc_now()
        try:
            if kind == DraftKind.CONTENT_BRIEF:
                output = await provider.content_brief(context=context)
                generated_snapshot = ContentBriefStageResult.model_validate(
                    output
                ).model_dump(mode="json")
            else:
                output = await provider.structure(context=context)
                generated_snapshot = StructureStageResult.model_validate(
                    output
                ).model_dump(mode="json")
        except Exception as error:
            status = DraftStatus.FAILED
            stage_errors[operation_key] = self._error_message(error)
            completed_at = utc_now()

        now = utc_now()
        with self.database.transaction() as connection:
            row = self.draft_repository.create(
                connection,
                workspace_id=topic["workspace_id"],
                topic_id=topic["id"],
                kind=kind.value,
                source_analysis_run_id=topic["source_analysis_run_id"],
                source_workflow=topic["source_workflow"],
                status=status.value,
                generated_snapshot_json=json.dumps(
                    generated_snapshot, ensure_ascii=False
                ),
                editable_content_json=json.dumps(
                    generated_snapshot, ensure_ascii=False
                ),
                input_snapshot_json=json.dumps(input_snapshot, ensure_ascii=False),
                stage_errors_json=json.dumps(stage_errors, ensure_ascii=False),
                model_metadata_json=json.dumps(model_metadata, ensure_ascii=False),
                now=now,
                completed_at=completed_at,
        )
        return self.draft_service._to_response(row)

    def _input_snapshot(
        self,
        workspace: dict,
        topic: dict,
        source_run: dict | None,
        mode: str,
    ) -> dict[str, Any]:
        stage_results = json.loads(source_run["stage_results_json"]) if source_run else {}
        analysis_context: dict[str, Any] = {}
        if source_run and source_run["workflow_type"] == "account_diagnosis":
            profile = stage_results.get("profile", {}).get("profile", {})
            analysis_context = {
                "voiceFingerprint": profile.get("voiceFingerprint", []),
                "viralStructure": profile.get("viralStructure", {}),
            }
            portrait = profile.get("accountPortrait")
            if isinstance(portrait, dict):
                expressions = portrait.get("expressionPatterns")
                if not analysis_context["voiceFingerprint"] and isinstance(expressions, list):
                    analysis_context["expressionPatterns"] = [
                        item["statement"] for item in expressions
                        if isinstance(item, dict) and isinstance(item.get("statement"), str)
                        and item["statement"].strip()
                    ]
                next_steps = portrait.get("nextSteps")
                if isinstance(next_steps, list):
                    contrast = profile.get("contrast")
                    takeaways = contrast.get("takeaways") if isinstance(contrast, dict) else None
                    suggestions = [
                        item for item in takeaways if isinstance(item, str) and item.strip()
                    ] if isinstance(takeaways, list) else []
                    analysis_context["writingSuggestions"] = suggestions or [
                        item["statement"] for item in next_steps
                        if isinstance(item, dict) and isinstance(item.get("statement"), str)
                        and item["statement"].strip()
                    ]
        elif source_run and source_run["workflow_type"] == "trend_analysis":
            trend = stage_results.get("trend_analysis", {}).get("trendAnalysis", {})
            analysis_context = {
                "viralPatterns": trend.get("viralPatterns", []),
                "opportunityWindows": trend.get("opportunityWindows", []),
            }
        return {
            "mode": mode,
            "workspaceId": workspace["id"],
            "workspaceName": workspace["name"],
            "accountPositioning": workspace["account_positioning"],
            "positioningVersion": workspace["positioning_version"],
            "topic": {
                "topicId": topic["id"],
                "title": topic["title"],
                "angle": topic["angle"],
                "associatedPainPoint": topic["associated_pain_point"],
                "whyItFits": topic["why_it_fits"],
                "sourceWorkflow": topic["source_workflow"],
                "sourceAnalysisRunId": topic["source_analysis_run_id"],
            },
            "analysisContext": analysis_context,
        }

    @staticmethod
    def _model_context(snapshot: dict[str, Any], kind: DraftKind) -> dict[str, Any]:
        topic = snapshot["topic"]
        analysis_context = snapshot.get("analysisContext", {})
        source_brief = snapshot.get("sourceBrief", {})
        brief_content = (
            source_brief.get("editableContent", {})
            if isinstance(source_brief, dict)
            else {}
        )
        background = ""
        account_background = {}
        if analysis_context.get("voiceFingerprint"):
            account_background["voiceFingerprint"] = analysis_context["voiceFingerprint"]
        structure = analysis_context.get("viralStructure")
        # ProfileStageResult supplies {"name": "", "steps": []} even when the
        # report never proposed a structure. Do not send that default as context.
        if isinstance(structure, dict) and any(structure.values()):
            account_background["viralStructure"] = structure
        for key in ("expressionPatterns", "writingSuggestions"):
            if analysis_context.get(key):
                account_background[key] = analysis_context[key]
        if account_background:
            background = json.dumps(account_background, ensure_ascii=False)
        elif analysis_context.get("viralPatterns"):
            background = "；".join(analysis_context.get("viralPatterns", []))
        if brief_content:
            background = "\n".join(
                [
                    background,
                    "创作 Brief：",
                    json.dumps(brief_content, ensure_ascii=False),
                ]
            ).strip()
        if kind == DraftKind.CONTENT_BRIEF:
            return {
                "positioning": snapshot.get("accountPositioning", ""),
                "topic": topic,
                "background": background,
            }
        return {
            "positioning": snapshot.get("accountPositioning", ""),
            "topic": topic.get("title", ""),
            "background": background,
        }

    @staticmethod
    def _error_message(error: Exception) -> str:
        if isinstance(error, PydanticValidationError):
            return "Model response failed structured validation"
        if isinstance(error, ValidationError):
            return str(error)
        return str(error) or error.__class__.__name__

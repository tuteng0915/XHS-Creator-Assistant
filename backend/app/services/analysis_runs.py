from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Iterable

from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    AnalysisRunBatchCreate,
    AnalysisRunCreate,
    AnalysisRunResponse,
    AnalysisRunStatus,
    AnalysisRunSummary,
    AnalysisRunTransition,
    AnalysisStageUpdate,
    RunReviewUpdate,
    SourceMaterialType,
    WorkflowType,
)
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.media_assets import MediaAssetRepository
from app.repositories.source_materials import SourceMaterialRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now
from app.services.context_access import ContextAccessService
from app.services.creator_analysis_scope import note_published_at, scope_creator_profile

STAGE_KEYS = {
    WorkflowType.ACCOUNT_DIAGNOSIS.value: {
        "profile",
        "pain_points",
        "topics",
        "structure",
    },
    WorkflowType.TREND_ANALYSIS.value: {
        "trend_analysis",
        "pain_points",
        "topics",
        "titles",
        "structure",
    },
    WorkflowType.VIDEO_CREATOR_QUALITY.value: {
        "creator_profile",
        "video_quality",
        "incentive_fit",
    },
}


class AnalysisRunService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: AnalysisRunRepository,
        workspace_repository: WorkspaceRepository,
        source_repository: SourceMaterialRepository,
        media_asset_repository: MediaAssetRepository,
        topic_repository: TopicRepository,
        settings: Settings,
        context_access_service: ContextAccessService,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.source_repository = source_repository
        self.media_asset_repository = media_asset_repository
        self.topic_repository = topic_repository
        self.settings = settings
        self.context_access_service = context_access_service

    def create(
        self, workspace_id: str, payload: AnalysisRunCreate
    ) -> AnalysisRunResponse:
        with self.database.transaction() as connection:
            workspace = self.workspace_repository.get(connection, workspace_id)
            idempotency_key = (
                payload.idempotency_key.strip()
                if payload.idempotency_key is not None
                else None
            )
            if idempotency_key:
                existing = self.repository.get_by_idempotency_key(
                    connection,
                    workspace_id=workspace_id,
                    idempotency_key=idempotency_key,
                )
                if existing is not None:
                    return self._to_response(existing)
            snapshot = self._build_input_snapshot(connection, workspace, payload)
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                workflow_type=payload.workflow_type.value,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                idempotency_key=idempotency_key,
                now=utc_now(),
            )
        return self._to_response(row)

    def create_batch(
        self, workspace_id: str, payload: AnalysisRunBatchCreate
    ) -> list[AnalysisRunResponse]:
        profile_asset_ids = (
            payload.account_profile_input_asset_ids
            or payload.account_profile_material_ids
        )
        xhs_profile_asset_ids = (
            payload.xhs_creator_profile_input_asset_ids
            or payload.xhs_creator_profile_material_ids
        )
        if profile_asset_ids and xhs_profile_asset_ids:
            raise ValidationError(
                "Batch run accepts either account profiles or XHS creator profiles, not both"
            )
        if xhs_profile_asset_ids and payload.workflow_type not in {
            WorkflowType.ACCOUNT_DIAGNOSIS,
            WorkflowType.VIDEO_CREATOR_QUALITY,
        }:
            raise ValidationError(
                "XHS creator profile batch input is only supported for "
                "account diagnosis or video creator quality"
            )
        batch_asset_ids = profile_asset_ids or xhs_profile_asset_ids
        if not batch_asset_ids:
            raise ValidationError(
                "At least one account profile or XHS creator profile input asset is required"
            )
        runs: list[AnalysisRunResponse] = []
        for index, input_asset_id in enumerate(batch_asset_ids):
            runs.append(
                self.create(
                    workspace_id,
                    AnalysisRunCreate(
                        workflow_type=payload.workflow_type,
                        idempotency_key=(
                            f"{payload.idempotency_key}:{index}"
                            if payload.idempotency_key
                            else None
                        ),
                        account_profile_input_asset_id=(
                            input_asset_id if profile_asset_ids else None
                        ),
                        historical_posts_input_asset_id=(
                            payload.historical_posts_input_asset_id
                            or payload.historical_posts_material_id
                        ),
                        comments_input_asset_id=(
                            payload.comments_input_asset_id
                            or payload.comments_material_id
                        ),
                        trend_csv_input_asset_id=(
                            payload.trend_csv_input_asset_id
                            or payload.trend_csv_material_id
                        ),
                        video_creator_samples_input_asset_id=(
                            payload.video_creator_samples_input_asset_id
                            or payload.video_creator_samples_material_id
                        ),
                        xhs_creator_profile_input_asset_id=(
                            input_asset_id if xhs_profile_asset_ids else None
                        ),
                        media_asset_ids=payload.media_asset_ids,
                        mode=payload.mode,
                    ),
                )
            )
        return runs

    def export_csv(
        self,
        workspace_id: str,
        *,
        workflow_type: WorkflowType | None = None,
        run_ids: Iterable[str] | None = None,
    ) -> str:
        selected_ids = set(run_ids or [])
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "run_id",
                "workflow_type",
                "status",
                "profile_source",
                "profile_name",
                "created_at",
                "completed_at",
                "stage_results_json",
                "stage_errors_json",
            ],
        )
        writer.writeheader()
        for row in rows:
            if workflow_type is not None and row["workflow_type"] != workflow_type.value:
                continue
            if selected_ids and row["id"] not in selected_ids:
                continue
            snapshot = json.loads(row["input_snapshot_json"])
            profile = snapshot.get("accountProfile", {})
            writer.writerow(
                {
                    "run_id": row["id"],
                    "workflow_type": row["workflow_type"],
                    "status": row["status"],
                    "profile_source": profile.get("source", "workspace"),
                    "profile_name": profile.get("name", ""),
                    "created_at": row["created_at"],
                    "completed_at": row["completed_at"] or "",
                    "stage_results_json": row["stage_results_json"],
                    "stage_errors_json": row["stage_errors_json"],
                }
            )
        return output.getvalue()

    def list(self, workspace_id: str) -> list[AnalysisRunSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        return [AnalysisRunSummary.model_validate({
            **row, "origin": json.loads(row["input_snapshot_json"]).get("origin"),
        }) for row in rows]

    def get(self, run_id: str) -> AnalysisRunResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, run_id)
        return self._to_response(row)

    def update_review(
        self, run_id: str, payload: RunReviewUpdate
    ) -> AnalysisRunResponse:
        current = self.get(run_id)
        user_notes = (
            payload.user_notes if payload.user_notes is not None else current.user_notes
        )
        review_status = (
            payload.review_status.value
            if payload.review_status is not None
            else current.review_status.value
        )
        if payload.user_notes is None and payload.review_status is None:
            raise ValidationError("No review changes provided")
        with self.database.transaction() as connection:
            row = self.repository.update_review(
                connection,
                run_id=run_id,
                user_notes=user_notes,
                review_status=review_status,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def transition(
        self, run_id: str, payload: AnalysisRunTransition
    ) -> AnalysisRunResponse:
        if payload.status == AnalysisRunStatus.PENDING:
            raise ValidationError("Analysis run cannot transition back to pending")
        with self.database.transaction() as connection:
            current = self.repository.get(connection, run_id)
            metadata = {
                **json.loads(current["model_metadata_json"]),
                **payload.model_metadata,
            }
            row = self.repository.set_status(
                connection,
                run_id=run_id,
                status=payload.status.value,
                model_metadata_json=json.dumps(metadata, ensure_ascii=False),
                now=utc_now(),
            )
        return self._to_response(row)

    def update_stage(
        self, run_id: str, stage_key: str, payload: AnalysisStageUpdate
    ) -> AnalysisRunResponse:
        if payload.status == AnalysisRunStatus.PENDING:
            raise ValidationError("Stage cannot be marked pending")
        with self.database.transaction() as connection:
            current = self.repository.get(connection, run_id)
            allowed = STAGE_KEYS[current["workflow_type"]]
            if stage_key not in allowed:
                raise ValidationError("Stage is not part of this workflow")

            results = json.loads(current["stage_results_json"])
            errors = json.loads(current["stage_errors_json"])
            metadata = json.loads(current["model_metadata_json"])

            if payload.result is not None:
                results[stage_key] = payload.result
            if payload.error:
                errors[stage_key] = payload.error
            elif stage_key in errors and payload.status == AnalysisRunStatus.COMPLETED:
                errors.pop(stage_key)
            if payload.model_metadata:
                metadata[stage_key] = payload.model_metadata

            row = self.repository.update_stage(
                connection,
                run_id=run_id,
                status=payload.status.value,
                stage_results_json=json.dumps(results, ensure_ascii=False),
                stage_errors_json=json.dumps(errors, ensure_ascii=False),
                model_metadata_json=json.dumps(metadata, ensure_ascii=False),
                now=utc_now(),
            )
            if (
                stage_key == "topics"
                and payload.status == AnalysisRunStatus.COMPLETED
            ):
                self._materialize_topics_from_stage_result(
                    connection,
                    run=current,
                    topics_result=results.get("topics", {}),
                )
        return self._to_response(row)

    def _materialize_topics_from_stage_result(
        self,
        connection,
        *,
        run: dict,
        topics_result: dict,
    ) -> None:
        source_workflow = run["workflow_type"]
        if source_workflow not in {
            WorkflowType.ACCOUNT_DIAGNOSIS.value,
            WorkflowType.TREND_ANALYSIS.value,
        }:
            return
        if self.topic_repository.list_by_source_analysis_run(connection, run["id"]):
            return
        topic_items = topics_result.get("topics") if isinstance(topics_result, dict) else None
        if not isinstance(topic_items, list):
            return
        now = utc_now()
        for index, item in enumerate(topic_items):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("topic") or "").strip()
            if not title:
                continue
            why_parts = [
                str(item.get("whyFit") or item.get("whyItFits") or "").strip(),
                str(item.get("whyTrending") or "").strip(),
            ]
            self.topic_repository.create(
                connection,
                workspace_id=run["workspace_id"],
                title=title,
                angle=str(item.get("angle") or ""),
                associated_pain_point=str(
                    item.get("pain")
                    or item.get("associatedPainPoint")
                    or item.get("painPoint")
                    or ""
                ),
                why_it_fits="\n".join(part for part in why_parts if part),
                generated_snapshot_json=json.dumps(
                    {
                        **item,
                        "sourceAnalysisRunId": run["id"],
                        "sourceWorkflow": source_workflow,
                        "sourceTopicIndex": index,
                    },
                    ensure_ascii=False,
                ),
                source_analysis_run_id=run["id"],
                source_workflow=source_workflow,
                now=now,
            )

    def _build_input_snapshot(
        self,
        connection,
        workspace: dict,
        payload: AnalysisRunCreate,
    ) -> dict:
        xhs_asset_id = (
            payload.xhs_creator_profile_input_asset_id
            or payload.xhs_creator_profile_material_id
        )
        if payload.selected_note_ids is not None and (
            payload.workflow_type != WorkflowType.ACCOUNT_DIAGNOSIS or not xhs_asset_id
        ):
            raise ValidationError("逐条选择笔记仅适用于创作者档案的账号诊断。")
        if payload.workflow_type == WorkflowType.ACCOUNT_DIAGNOSIS and xhs_asset_id:
            return self._build_xhs_account_diagnosis_snapshot(
                connection, workspace, payload, xhs_asset_id
            )

        profile = self._resolve_account_profile(connection, workspace, payload)
        base = {
            "mode": payload.mode,
            "workspaceId": workspace["id"],
            "workspaceName": workspace["name"],
            "accountPositioning": profile["content"],
            "accountProfile": profile,
            "positioningVersion": workspace["positioning_version"],
        }
        if payload.workflow_type == WorkflowType.ACCOUNT_DIAGNOSIS:
            historical = self._require_material(
                connection,
                payload.historical_posts_input_asset_id
                or payload.historical_posts_material_id,
                workspace["id"],
                SourceMaterialType.HISTORICAL_POSTS.value,
                "Historical posts input asset is required",
            )
            comments = self._require_material(
                connection,
                payload.comments_input_asset_id or payload.comments_material_id,
                workspace["id"],
                SourceMaterialType.COMMENTS.value,
                "Comments input asset is required",
            )
            workflow_snapshot = {
                **base,
                "historicalPosts": {
                    "inputAssetId": historical["id"],
                    "materialId": historical["id"],
                    "name": historical["name"],
                    "content": historical["text_content"],
                    "updatedAt": historical["updated_at"],
                },
                "comments": {
                    "inputAssetId": comments["id"],
                    "materialId": comments["id"],
                    "name": comments["name"],
                    "content": comments["text_content"],
                    "updatedAt": comments["updated_at"],
                },
            }
            workflow_snapshot["contextPack"] = (
                self.context_access_service.build_workspace_pack(
                    connection,
                    workspace=workspace,
                    requester={
                        "workflowId": payload.workflow_type.value,
                        "agentId": "account_diagnosis_workflow",
                        "skillId": "analysis.account_diagnosis",
                    },
                    purpose="create_account_diagnosis_analysis_run",
                    selectors=[
                        "account_positioning",
                        "historical_posts_text",
                        "comment_samples_text",
                        "input_assets_overview",
                        "analysis_history_overview",
                        "topic_library_overview",
                        "draft_history_overview",
                        "simulation_history_overview",
                    ],
                    deep_items=[
                        self.context_access_service.deep_item(
                            key="selected_historical_posts",
                            asset_type="input_asset",
                            asset_id=historical["id"],
                            selector="historical_posts_text",
                            role="historical_posts",
                            data={
                                "workspaceId": workspace["id"],
                                "materialId": historical["id"],
                                "name": historical["name"],
                                "updatedAt": historical["updated_at"],
                                "charCount": len(historical["text_content"] or ""),
                            },
                            text=historical["text_content"] or "",
                        ),
                        self.context_access_service.deep_item(
                            key="selected_comment_samples",
                            asset_type="input_asset",
                            asset_id=comments["id"],
                            selector="comment_samples_text",
                            role="comments",
                            data={
                                "workspaceId": workspace["id"],
                                "materialId": comments["id"],
                                "name": comments["name"],
                                "updatedAt": comments["updated_at"],
                                "charCount": len(comments["text_content"] or ""),
                            },
                            text=comments["text_content"] or "",
                        ),
                    ],
                )
            )
            return workflow_snapshot

        if payload.workflow_type == WorkflowType.TREND_ANALYSIS:
            trend_csv = self._require_material(
                connection,
                payload.trend_csv_input_asset_id or payload.trend_csv_material_id,
                workspace["id"],
                SourceMaterialType.TREND_CSV.value,
                "Trend CSV input asset is required",
            )
            ranked_posts = self._rank_trend_posts(
                self._read_upload_text(trend_csv["stored_key"])
            )
            workflow_snapshot = {
                **base,
                "trendCsv": {
                    "inputAssetId": trend_csv["id"],
                    "materialId": trend_csv["id"],
                    "name": trend_csv["name"],
                    "keyword": trend_csv["keyword"],
                    "originalFilename": trend_csv["original_filename"],
                    "rowCount": trend_csv["row_count"],
                    "updatedAt": trend_csv["updated_at"],
                    "rankedPosts": ranked_posts,
                    "ranking": {
                        "method": "likes_plus_collects_desc",
                        "limit": 50,
                    },
                },
            }
            workflow_snapshot["contextPack"] = (
                self.context_access_service.build_workspace_pack(
                    connection,
                    workspace=workspace,
                    requester={
                        "workflowId": payload.workflow_type.value,
                        "agentId": "trend_analysis_workflow",
                        "skillId": "analysis.trend_analysis",
                    },
                    purpose="create_trend_analysis_run",
                    selectors=[
                        "account_positioning",
                        "trend_top_ranked_posts",
                        "input_assets_overview",
                        "analysis_history_overview",
                        "topic_library_overview",
                        "draft_history_overview",
                        "simulation_history_overview",
                    ],
                    deep_items=[
                        self.context_access_service.deep_item(
                            key="selected_trend_top_ranked_posts",
                            asset_type="input_asset",
                            asset_id=trend_csv["id"],
                            selector="trend_top_ranked_posts",
                            role="trend_csv",
                            data={
                                "workspaceId": workspace["id"],
                                "materialId": trend_csv["id"],
                                "name": trend_csv["name"],
                                "keyword": trend_csv["keyword"],
                                "originalFilename": trend_csv["original_filename"],
                                "rowCount": trend_csv["row_count"],
                                "ranking": {
                                    "method": "likes_plus_collects_desc",
                                    "limit": 50,
                                },
                                "rankedPosts": ranked_posts,
                            },
                        )
                    ],
                )
            )
            return workflow_snapshot

        media_assets = self._resolve_media_asset_snapshots(
            connection,
            workspace["id"],
            payload.media_asset_ids,
        )
        if xhs_asset_id:
            xhs_asset = self._require_material(
                connection,
                xhs_asset_id,
                workspace["id"],
                SourceMaterialType.XHS_CREATOR_PROFILE.value,
                "XHS creator profile input asset is required",
            )
            xhs_profile = self._parse_xhs_creator_profile(
                xhs_asset["text_content"] or ""
            )
            media_assets = self._resolve_media_asset_snapshots(
                connection,
                workspace["id"],
                self._xhs_cover_media_asset_ids(xhs_profile) + payload.media_asset_ids,
            )
            evidence_pack = self._build_xhs_video_creator_evidence_pack(
                xhs_profile, media_assets
            )
            workflow_snapshot = {
                **base,
                "xhsCreatorProfile": {
                    "inputAssetId": xhs_asset["id"],
                    "materialId": xhs_asset["id"],
                    "name": xhs_asset["name"],
                    "updatedAt": xhs_asset["updated_at"],
                    "schemaVersion": xhs_profile.get("schemaVersion"),
                    "source": self._public_xhs_source(xhs_profile),
                    "creator": xhs_profile.get("creator", {}),
                    "noteCount": evidence_pack["noteStats"]["totalNotes"],
                    "commentCount": evidence_pack["noteStats"]["commentCount"],
                },
                "videoCreatorSamples": {
                    "source": "xhs_creator_profile",
                    "inputAssetId": xhs_asset["id"],
                    "materialId": xhs_asset["id"],
                    "name": f"{xhs_asset['name']} · 派生视频创作样本",
                    "content": self._derive_video_creator_samples_from_evidence_pack(
                        evidence_pack
                    ),
                    "updatedAt": xhs_asset["updated_at"],
                    "derivedFrom": "xhs_creator_profile",
                },
                "videoCreatorEvidencePack": evidence_pack,
                "mediaAssets": media_assets,
            }
            workflow_snapshot["contextPack"] = (
                self.context_access_service.build_workspace_pack(
                    connection,
                    workspace=workspace,
                    requester={
                        "workflowId": payload.workflow_type.value,
                        "agentId": "video_creator_quality_workflow",
                        "skillId": "analysis.video_creator_quality",
                    },
                    purpose="create_video_creator_quality_analysis_run_from_xhs_creator_profile",
                    selectors=[
                        "account_positioning",
                        "xhs_creator_profile",
                        "input_assets_overview",
                        "analysis_history_overview",
                        "topic_library_overview",
                        "draft_history_overview",
                        "simulation_history_overview",
                        "media_assets_overview",
                    ],
                    deep_items=[
                        self.context_access_service.deep_item(
                            key="selected_xhs_creator_profile_for_video_quality",
                            asset_type="input_asset",
                            asset_id=xhs_asset["id"],
                            selector="xhs_video_creator_evidence_pack",
                            role="xhs_creator_profile",
                            data={
                                "workspaceId": workspace["id"],
                                "materialId": xhs_asset["id"],
                                "name": xhs_asset["name"],
                                "updatedAt": xhs_asset["updated_at"],
                                "evidencePack": evidence_pack,
                            },
                        )
                    ]
                    + [
                        self.context_access_service.deep_item(
                            key=f"selected_media_asset_{media['mediaAssetId']}",
                            asset_type="media_asset",
                            asset_id=media["mediaAssetId"],
                            selector="media_asset_derived_snapshot",
                            role="media_asset",
                            data=media,
                        )
                        for media in workflow_snapshot["mediaAssets"]
                    ],
                )
            )
            return workflow_snapshot

        video_samples = self._require_material(
            connection,
            payload.video_creator_samples_input_asset_id
            or payload.video_creator_samples_material_id,
            workspace["id"],
            SourceMaterialType.VIDEO_CREATOR_SAMPLES.value,
            "Video creation samples input asset is required",
        )
        workflow_snapshot = {
            **base,
            "videoCreatorSamples": {
                "inputAssetId": video_samples["id"],
                "materialId": video_samples["id"],
                "name": video_samples["name"],
                "content": video_samples["text_content"],
                "updatedAt": video_samples["updated_at"],
            },
            "videoCreatorEvidencePack": self._build_text_video_creator_evidence_pack(
                video_samples["text_content"] or "", media_assets
            ),
            "mediaAssets": media_assets,
        }
        workflow_snapshot["contextPack"] = (
            self.context_access_service.build_workspace_pack(
                connection,
                workspace=workspace,
                requester={
                    "workflowId": payload.workflow_type.value,
                    "agentId": "video_creator_quality_workflow",
                    "skillId": "analysis.video_creator_quality",
                },
                purpose="create_video_creator_quality_analysis_run",
                selectors=[
                    "account_positioning",
                    "video_creator_samples_text",
                    "input_assets_overview",
                    "analysis_history_overview",
                    "topic_library_overview",
                    "draft_history_overview",
                    "simulation_history_overview",
                    "media_assets_overview",
                ],
                deep_items=[
                    self.context_access_service.deep_item(
                        key="selected_video_creator_samples",
                        asset_type="input_asset",
                        asset_id=video_samples["id"],
                        selector="video_creator_samples_text",
                        role="video_creator_samples",
                        data={
                            "workspaceId": workspace["id"],
                            "materialId": video_samples["id"],
                            "name": video_samples["name"],
                            "updatedAt": video_samples["updated_at"],
                            "charCount": len(video_samples["text_content"] or ""),
                        },
                        text=video_samples["text_content"] or "",
                    )
                ]
                + [
                    self.context_access_service.deep_item(
                        key=f"selected_media_asset_{media['mediaAssetId']}",
                        asset_type="media_asset",
                        asset_id=media["mediaAssetId"],
                        selector="media_asset_derived_snapshot",
                        role="media_asset",
                        data=media,
                    )
                    for media in workflow_snapshot["mediaAssets"]
                ],
            )
        )
        return workflow_snapshot

    def _build_text_video_creator_evidence_pack(
        self, samples_text: str, media_assets: list[dict]
    ) -> dict:
        media_refs = self._media_asset_refs(media_assets)
        has_video_understanding = any(
            asset.get("type") == "video"
            and (asset.get("derived") or {}).get("videoUnderstanding")
            for asset in media_assets
        )
        has_cover_or_image_understanding = any(
            asset.get("type") == "image"
            and (
                (asset.get("derived") or {}).get("imageUnderstanding")
                or (asset.get("derived") or {}).get("visualSummary")
            )
            for asset in media_assets
        )
        limitations = []
        if not has_video_understanding:
            limitations.append(
                "未提供已确认的视频理解结果；不得声称看过完整视频、镜头、剪辑或口型。"
            )
        if not has_cover_or_image_understanding:
            limitations.append(
                "未提供已确认的封面/截图理解结果；视觉判断只能来自用户文本备注。"
            )
        scope = {
            "sourceType": "video_creator_samples",
            "hasVideoNotes": None,
            "hasVideoUnderstanding": has_video_understanding,
            "hasImageUnderstanding": has_cover_or_image_understanding,
            "hasComments": "评论" in samples_text,
            "mediaAssetCount": len(media_refs),
        }
        return {
            "schemaVersion": "video-creator-evidence-pack/v1",
            "source": {"type": "video_creator_samples"},
            "creator": {"displayName": self._infer_creator_name_from_text(samples_text)},
            "noteStats": {
                "totalNotes": None,
                "videoNotes": None,
                "normalNotes": None,
                "commentCount": None,
            },
            "videoNotes": [],
            "topEngagementNotes": [],
            "scriptDrivenSignals": self._keyword_signals(
                samples_text,
                ["剧情", "短剧", "剧本", "角色", "主角", "反转", "世界观", "连续"],
                "operator_note",
            ),
            "commercialSignals": self._keyword_signals(
                samples_text,
                ["商单", "品牌", "合作", "广告", "带货", "种草", "推广"],
                "operator_note",
            ),
            "techExplorationSignals": self._keyword_signals(
                samples_text,
                ["AI", "AIGC", "工具", "模型", "教程", "技术", "prompt", "工作流"],
                "operator_note",
            ),
            "audienceSignals": self._keyword_signals(
                samples_text,
                ["评论", "催更", "收藏", "转发", "粉丝", "互动"],
                "operator_note",
            ),
            "mediaAssetRefs": media_refs,
            "evidenceScope": scope,
            "evidenceLimitations": limitations,
            "recommendedNextEvidence": self._video_evidence_recommendations(scope),
        }

    def _build_xhs_video_creator_evidence_pack(
        self, profile: dict, media_assets: list[dict]
    ) -> dict:
        creator = profile.get("creator") if isinstance(profile.get("creator"), dict) else {}
        source = profile.get("source") if isinstance(profile.get("source"), dict) else {}
        notes = [note for note in profile.get("notes", []) if isinstance(note, dict)]
        video_notes = [note for note in notes if str(note.get("type") or "") == "video"]
        normal_notes = [note for note in notes if str(note.get("type") or "") != "video"]
        comment_count = sum(
            len(note.get("comments", []))
            for note in notes
            if isinstance(note.get("comments"), list)
        )
        top_notes = sorted(notes, key=self._engagement_score, reverse=True)[:10]
        searchable_text = "\n".join(
            " ".join(
                [
                    str(note.get("title") or ""),
                    str(note.get("desc") or ""),
                    " ".join(str(tag) for tag in note.get("tags", []) or []),
                    " ".join(
                        str(comment.get("content") or "")
                        for comment in note.get("comments", [])[:5]
                        if isinstance(comment, dict)
                    )
                    if isinstance(note.get("comments"), list)
                    else "",
                ]
            )
            for note in notes
        )
        media_refs = self._xhs_media_asset_refs(notes, media_assets)
        has_video_understanding = any(
            ref.get("type") == "video" and ref.get("hasVideoUnderstanding")
            for ref in media_refs
        )
        has_cover_understanding = any(
            ref.get("type") == "image" and ref.get("hasImageUnderstanding")
            for ref in media_refs
        )
        limitations = []
        if not video_notes:
            limitations.append(
                "该主页导入结果没有 video 类型笔记；视频质量只能基于图文/封面/评论等间接证据判断。"
            )
        if not has_video_understanding:
            limitations.append(
                "未提供已确认的视频理解结果；不得声称看过完整视频、镜头、剪辑或口型。"
            )
        if media_refs and not has_cover_understanding:
            limitations.append(
                "存在封面媒体资产，但未保存图片理解结果；视觉判断只能引用封面 caption 或用户备注。"
            )
        scope = {
            "sourceType": "xhs_creator_profile",
            "hasVideoNotes": bool(video_notes),
            "hasVideoUnderstanding": has_video_understanding,
            "hasImageUnderstanding": has_cover_understanding,
            "hasComments": comment_count > 0,
            "mediaAssetCount": len(media_refs),
        }
        return {
            "schemaVersion": "video-creator-evidence-pack/v1",
            "source": {
                "type": "xhs_creator_profile",
                "platform": source.get("platform", "xiaohongshu"),
                "fixtureCode": source.get("fixtureCode"),
                "crawler": source.get("crawler"),
            },
            "creator": {
                "displayName": creator.get("displayName") or source.get("fixtureCode") or "未知",
                "profileText": self._truncate(creator.get("profileText"), 1000),
            },
            "noteStats": {
                "totalNotes": len(notes),
                "videoNotes": len(video_notes),
                "normalNotes": len(normal_notes),
                "commentCount": comment_count,
            },
            "videoNotes": [self._compact_xhs_note(note) for note in video_notes[:20]],
            "topEngagementNotes": [self._compact_xhs_note(note) for note in top_notes],
            "scriptDrivenSignals": self._keyword_signals(
                searchable_text,
                ["剧情", "短剧", "剧本", "角色", "主角", "反转", "世界观", "连续"],
                "text_observation",
            ),
            "commercialSignals": self._keyword_signals(
                searchable_text,
                ["商单", "品牌", "合作", "广告", "带货", "种草", "推广"],
                "text_observation",
            ),
            "techExplorationSignals": self._keyword_signals(
                searchable_text,
                ["AI", "AIGC", "工具", "模型", "教程", "技术", "prompt", "工作流"],
                "text_observation",
            ),
            "audienceSignals": self._audience_signals_from_xhs(notes),
            "mediaAssetRefs": media_refs,
            "evidenceScope": scope,
            "evidenceLimitations": limitations,
            "recommendedNextEvidence": self._video_evidence_recommendations(scope),
        }

    def _derive_video_creator_samples_from_evidence_pack(self, evidence_pack: dict) -> str:
        source_type = evidence_pack.get("source", {}).get("type")
        creator = evidence_pack.get("creator", {})
        stats = evidence_pack.get("noteStats", {})
        lines = [
            f"# 视频创作样本（由 {source_type} 派生）",
            "",
            f"- 创作者：{creator.get('displayName') or '未知'}",
            f"- 笔记数：{stats.get('totalNotes')}",
            f"- 视频笔记数：{stats.get('videoNotes')}",
            f"- 一级评论数：{stats.get('commentCount')}",
            "",
        ]
        top_notes = evidence_pack.get("topEngagementNotes") or []
        if top_notes:
            lines.extend(["## 高互动内容", ""])
            for index, note in enumerate(top_notes[:10], start=1):
                metrics = note.get("metrics") or {}
                lines.extend(
                    [
                        f"{index}. {note.get('title') or '未命名笔记'}",
                        (
                            f"   - 类型：{note.get('type') or 'unknown'}；"
                            f"赞：{metrics.get('liked')}; 收藏：{metrics.get('collected')}; "
                            f"评论：{metrics.get('comments')}; 分享：{metrics.get('shares')}"
                        ),
                        f"   - 摘要：{note.get('descSnippet') or '无'}",
                    ]
                )
        for key, label in [
            ("scriptDrivenSignals", "剧本/叙事信号"),
            ("commercialSignals", "商单/商业信号"),
            ("techExplorationSignals", "技术探索信号"),
            ("audienceSignals", "受众反馈信号"),
            ("evidenceLimitations", "证据限制"),
        ]:
            values = evidence_pack.get(key) or []
            if values:
                lines.extend(["", f"## {label}", ""])
                for value in values:
                    if isinstance(value, dict):
                        evidence_type = value.get("evidenceType") or "inference"
                        evidence_text = value.get("text") or value
                        lines.append(
                            f"- [{evidence_type}] {evidence_text}"
                        )
                    else:
                        lines.append(f"- {value}")
        return "\n".join(lines).rstrip() + "\n"

    def _compact_xhs_note(self, note: dict) -> dict:
        metrics = note.get("metrics") if isinstance(note.get("metrics"), dict) else {}
        comments = note.get("comments") if isinstance(note.get("comments"), list) else []
        return {
            "noteId": note.get("noteId") or "",
            "type": note.get("type") or "normal",
            "title": self._truncate(note.get("title"), 120),
            "descSnippet": self._truncate(note.get("desc"), 240),
            "tags": note.get("tags")[:8] if isinstance(note.get("tags"), list) else [],
            "metrics": {
                "liked": metrics.get("liked"),
                "collected": metrics.get("collected"),
                "comments": metrics.get("comments"),
                "shares": metrics.get("shares"),
                "engagementScore": self._engagement_score(note),
            },
            "topComments": [
                self._truncate(comment.get("content"), 120)
                for comment in comments[:5]
                if isinstance(comment, dict) and comment.get("content")
            ],
            "coverMediaAssetId": note.get("coverMediaAssetId") or "",
        }

    def _audience_signals_from_xhs(self, notes: list[dict]) -> list[dict]:
        signals: list[dict] = []
        for note in notes[:20]:
            comments = note.get("comments") if isinstance(note.get("comments"), list) else []
            for comment in comments[:3]:
                if not isinstance(comment, dict) or not comment.get("content"):
                    continue
                signals.append(
                    {
                        "evidenceType": "comment",
                        "text": self._truncate(
                            f"{note.get('title') or '未命名笔记'}：{comment.get('content')}",
                            180,
                        ),
                    }
                )
        return signals[:12]

    def _xhs_media_asset_refs(
        self, notes: list[dict], media_assets: list[dict]
    ) -> list[dict]:
        by_id = {asset["mediaAssetId"]: asset for asset in media_assets}
        refs: list[dict] = []
        for note in notes:
            media_asset_id = note.get("coverMediaAssetId")
            if not media_asset_id:
                continue
            asset = by_id.get(media_asset_id)
            derived = (asset or {}).get("derived") or {}
            refs.append(
                {
                    "noteId": note.get("noteId") or "",
                    "noteTitle": self._truncate(note.get("title"), 120),
                    "mediaAssetId": media_asset_id,
                    "type": (asset or {}).get("type", "image"),
                    "name": (asset or {}).get("name", ""),
                    "hasImageUnderstanding": bool(
                        derived.get("imageUnderstanding")
                        or derived.get("visualSummary")
                        or derived.get("qwenUnderstanding")
                    ),
                    "hasVideoUnderstanding": bool(derived.get("videoUnderstanding")),
                }
            )
        for asset in media_assets:
            if not any(ref["mediaAssetId"] == asset["mediaAssetId"] for ref in refs):
                derived = asset.get("derived") or {}
                refs.append(
                    {
                        "noteId": "",
                        "noteTitle": "",
                        "mediaAssetId": asset["mediaAssetId"],
                        "type": asset.get("type", ""),
                        "name": asset.get("name", ""),
                        "hasImageUnderstanding": bool(
                            derived.get("imageUnderstanding")
                            or derived.get("visualSummary")
                            or derived.get("qwenUnderstanding")
                        ),
                        "hasVideoUnderstanding": bool(derived.get("videoUnderstanding")),
                    }
                )
        return refs

    @staticmethod
    def _xhs_cover_media_asset_ids(profile: dict) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        notes = profile.get("notes") if isinstance(profile.get("notes"), list) else []
        for note in notes:
            if not isinstance(note, dict):
                continue
            media_asset_id = str(note.get("coverMediaAssetId") or "").strip()
            if media_asset_id and media_asset_id not in seen:
                ids.append(media_asset_id)
                seen.add(media_asset_id)
        return ids

    def _media_asset_refs(self, media_assets: list[dict]) -> list[dict]:
        refs: list[dict] = []
        for asset in media_assets:
            derived = asset.get("derived") or {}
            refs.append(
                {
                    "mediaAssetId": asset.get("mediaAssetId"),
                    "type": asset.get("type"),
                    "name": asset.get("name"),
                    "hasImageUnderstanding": bool(
                        derived.get("imageUnderstanding")
                        or derived.get("visualSummary")
                        or derived.get("qwenUnderstanding")
                    ),
                    "hasVideoUnderstanding": bool(derived.get("videoUnderstanding")),
                }
            )
        return refs

    @staticmethod
    def _video_evidence_recommendations(scope: dict) -> list[str]:
        recommendations: list[str] = []
        if not scope.get("hasVideoUnderstanding"):
            recommendations.append(
                "补充至少 1 条代表视频的视频理解结果、关键帧理解结果或人工转写。"
            )
        if scope.get("mediaAssetCount", 0) and not scope.get("hasImageUnderstanding"):
            recommendations.append("补充封面或关键截图的图片理解结果。")
        if not scope.get("hasComments"):
            recommendations.append("补充评论样本，验证受众反馈和催更/转化信号。")
        return recommendations

    @staticmethod
    def _keyword_signals(text: str, keywords: list[str], evidence_type: str) -> list[dict]:
        signals: list[dict] = []
        lower_text = text.lower()
        for keyword in keywords:
            if keyword.lower() in lower_text:
                signals.append(
                    {
                        "evidenceType": evidence_type,
                        "text": f"输入中出现“{keyword}”相关线索。",
                    }
                )
        return signals[:8]

    @staticmethod
    def _infer_creator_name_from_text(text: str) -> str:
        for marker in ["创作者：", "账号：", "@"]:
            if marker not in text:
                continue
            fragment = text.split(marker, 1)[1].strip()
            return fragment.splitlines()[0].strip()[:80]
        return ""

    @staticmethod
    def _truncate(value, limit: int) -> str:
        text = str(value or "").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @staticmethod
    def _public_xhs_source(profile: dict) -> dict:
        source = profile.get("source") if isinstance(profile.get("source"), dict) else {}
        return {
            key: source[key]
            for key in ["platform", "fixtureCode", "importedAt", "crawler"]
            if source.get(key)
        }

    def _engagement_score(self, note: dict) -> int:
        return (
            self._metric(note, "liked")
            + self._metric(note, "collected")
            + self._metric(note, "comments")
            + self._metric(note, "shares")
        )

    def _build_xhs_account_diagnosis_snapshot(
        self,
        connection,
        workspace: dict,
        payload: AnalysisRunCreate,
        xhs_asset_id: str,
    ) -> dict:
        xhs_asset = self._require_material(
            connection,
            xhs_asset_id,
            workspace["id"],
            SourceMaterialType.XHS_CREATOR_PROFILE.value,
            "XHS creator profile input asset is required",
        )
        xhs_profile = self._parse_xhs_creator_profile(xhs_asset["text_content"] or "")
        xhs_profile, analysis_range = scope_creator_profile(
            xhs_profile, payload.analysis_scope, selected_note_ids=payload.selected_note_ids,
        )
        account_positioning = self._derive_xhs_account_positioning(xhs_profile)
        historical_text = self._derive_xhs_historical_posts_text(xhs_profile)
        comments_text = self._derive_xhs_comments_text(xhs_profile)
        workflow_snapshot = {
            "mode": payload.mode,
            "workspaceId": workspace["id"],
            "workspaceName": workspace["name"],
            "accountPositioning": account_positioning,
            "analysisRange": analysis_range,
            "accountProfile": {
                "source": "xhs_creator_profile",
                "inputAssetId": xhs_asset["id"],
                "materialId": xhs_asset["id"],
                "name": xhs_asset["name"],
                "content": account_positioning,
                "updatedAt": xhs_asset["updated_at"],
            },
            "positioningVersion": workspace["positioning_version"],
            "xhsCreatorProfile": {
                "inputAssetId": xhs_asset["id"],
                "materialId": xhs_asset["id"],
                "name": xhs_asset["name"],
                "updatedAt": xhs_asset["updated_at"],
                "schemaVersion": xhs_profile.get("schemaVersion"),
                "source": self._public_xhs_source(xhs_profile),
                "creator": xhs_profile.get("creator", {}),
                "noteCount": len(xhs_profile.get("notes", [])),
                "commentCount": sum(
                    len(note.get("comments", []))
                    for note in xhs_profile.get("notes", [])
                    if isinstance(note, dict)
                ),
                "notes": xhs_profile.get("notes", []),
            },
            "historicalPosts": {
                "inputAssetId": xhs_asset["id"],
                "materialId": xhs_asset["id"],
                "name": f"{xhs_asset['name']} · 派生历史笔记",
                "content": historical_text,
                "updatedAt": xhs_asset["updated_at"],
                "derivedFrom": "xhs_creator_profile",
            },
            "comments": {
                "inputAssetId": xhs_asset["id"],
                "materialId": xhs_asset["id"],
                "name": f"{xhs_asset['name']} · 派生评论样本",
                "content": comments_text,
                "updatedAt": xhs_asset["updated_at"],
                "derivedFrom": "xhs_creator_profile",
            },
        }
        workflow_snapshot["contextPack"] = (
            self.context_access_service.build_workspace_pack(
                connection,
                workspace=workspace,
                requester={
                    "workflowId": payload.workflow_type.value,
                    "agentId": "account_diagnosis_workflow",
                    "skillId": "analysis.account_diagnosis",
                },
                purpose="create_account_diagnosis_analysis_run_from_xhs_creator_profile",
                selected_evidence_only=(payload.analysis_scope != "all"
                                        or payload.selected_note_ids is not None),
                selectors=[
                    "account_positioning",
                    "xhs_creator_profile",
                    "input_assets_overview",
                    "media_assets_overview",
                    "analysis_history_overview",
                    "topic_library_overview",
                    "draft_history_overview",
                    "simulation_history_overview",
                ],
                deep_items=[
                    self.context_access_service.deep_item(
                        key="selected_xhs_creator_profile",
                        asset_type="input_asset",
                        asset_id=xhs_asset["id"],
                        selector="xhs_creator_profile_json",
                        role="xhs_creator_profile",
                        data={
                            "workspaceId": workspace["id"],
                            "materialId": xhs_asset["id"],
                            "name": xhs_asset["name"],
                            "updatedAt": xhs_asset["updated_at"],
                            "noteCount": workflow_snapshot["xhsCreatorProfile"][
                                "noteCount"
                            ],
                            "commentCount": workflow_snapshot["xhsCreatorProfile"][
                                "commentCount"
                            ],
                        },
                        text=json.dumps(xhs_profile, ensure_ascii=False),
                    )
                ],
            )
        )
        return workflow_snapshot

    def _parse_xhs_creator_profile(self, content: str) -> dict:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValidationError("XHS creator profile asset must contain valid JSON") from error
        if not isinstance(payload, dict):
            raise ValidationError("XHS creator profile asset must be a JSON object")
        if payload.get("schemaVersion") != "xhs-creator-profile/v1":
            raise ValidationError("Unsupported XHS creator profile schema")
        notes = payload.get("notes")
        if not isinstance(notes, list) or not notes:
            raise ValidationError("XHS creator profile must contain notes")
        return payload

    def _derive_xhs_account_positioning(self, profile: dict) -> str:
        creator = profile.get("creator") if isinstance(profile.get("creator"), dict) else {}
        source = profile.get("source") if isinstance(profile.get("source"), dict) else {}
        notes = [note for note in profile.get("notes", []) if isinstance(note, dict)]
        tags: Counter[str] = Counter()
        top_notes = sorted(
            notes,
            key=lambda note: self._metric(note, "liked"),
            reverse=True,
        )[:5]
        for note in notes:
            for tag in note.get("tags", []) if isinstance(note.get("tags"), list) else []:
                if tag:
                    tags[str(tag)] += 1
        display_name = creator.get("displayName") or source.get("fixtureCode") or "未知"
        platform = source.get("platform", "xiaohongshu")
        crawler = source.get("crawler", "MediaCrawler")
        comment_count = sum(len(note.get("comments", [])) for note in notes)
        lines = [
            f"小红书创作者主页：{display_name}",
            f"数据来源：{platform} / {crawler}",
            f"笔记数：{len(notes)}；一级评论数：{comment_count}",
        ]
        if tags:
            lines.append("高频标签：" + "、".join(tag for tag, _ in tags.most_common(12)))
        if top_notes:
            lines.append("高互动内容：" + "；".join(note.get("title", "") for note in top_notes))
        lines.append("这是从小红书抓取结果生成的结构化输入摘要，不是人工填写的账号定位。")
        return "\n".join(lines)

    def _derive_xhs_historical_posts_text(self, profile: dict) -> str:
        lines = ["# 小红书历史笔记（由 xhs_creator_profile 派生）", ""]
        for index, note in enumerate(profile.get("notes", []), start=1):
            if not isinstance(note, dict):
                continue
            metrics = note.get("metrics") if isinstance(note.get("metrics"), dict) else {}
            tags = note.get("tags") if isinstance(note.get("tags"), list) else []
            published_at = note_published_at(note)
            lines.extend(
                [
                    f"## {index}. {note.get('title') or '未命名笔记'}",
                    "",
                    f"- note_id：{note.get('noteId') or '未知'}",
                    f"- 发布时间：{published_at.date().isoformat() if published_at else '未知'}",
                    f"- 类型：{note.get('type') or 'normal'}",
                    f"- 链接：{note.get('noteUrl') or '未知'}",
                    (
                        f"- 赞：{metrics.get('liked', '未知')}；"
                        f"收藏：{metrics.get('collected', '未知')}；"
                        f"评论：{metrics.get('comments', '未知')}；"
                        f"分享：{metrics.get('shares', '未知')}"
                    ),
                ]
            )
            if tags:
                lines.append("- 标签：" + "、".join(str(tag) for tag in tags))
            if note.get("coverMediaAssetId"):
                lines.append(f"- 封面 MediaAsset：{note['coverMediaAssetId']}")
            lines.extend(["", str(note.get("desc") or "（未抓取到正文。）"), ""])
        return "\n".join(lines).rstrip() + "\n"

    def _derive_xhs_comments_text(self, profile: dict) -> str:
        lines = ["# 小红书一级评论样本（由 xhs_creator_profile 派生）", ""]
        for note in profile.get("notes", []):
            if not isinstance(note, dict):
                continue
            comments = note.get("comments") if isinstance(note.get("comments"), list) else []
            lines.extend(
                [
                    f"## {note.get('title') or '未命名笔记'}",
                    "",
                    f"- note_id：{note.get('noteId') or '未知'}",
                    f"- 抓取评论数：{len(comments)}",
                    "",
                ]
            )
            if not comments:
                lines.extend(["（本次未抓取到一级评论。）", ""])
                continue
            for index, comment in enumerate(comments, start=1):
                if not isinstance(comment, dict):
                    continue
                lines.extend(
                    [
                        f"{index}. {comment.get('content') or '（图片评论或空文本评论）'}",
                        (
                            f"   - comment_id：{comment.get('commentId') or '未知'}；"
                            f"赞：{comment.get('likeCount', '未知')}；"
                            f"二级评论数：{comment.get('subCommentCount', '未知')}"
                        ),
                    ]
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _metric(note: dict, key: str) -> int:
        metrics = note.get("metrics") if isinstance(note.get("metrics"), dict) else {}
        value = metrics.get(key)
        return value if isinstance(value, int) else 0

    def _resolve_media_asset_snapshots(
        self,
        connection,
        workspace_id: str,
        media_asset_ids: list[str],
    ) -> list[dict]:
        compact_assets: list[dict] = []
        seen: set[str] = set()
        for asset_id in media_asset_ids:
            clean_id = asset_id.strip()
            if not clean_id or clean_id in seen:
                continue
            seen.add(clean_id)
            row = self.media_asset_repository.get(connection, clean_id)
            if row["workspace_id"] != workspace_id:
                raise ValidationError("Media asset does not belong to this workspace")
            compact_assets.append(self.context_access_service._summarize_media_asset(row))
        return compact_assets

    def _require_material(
        self,
        connection,
        material_id: str | None,
        workspace_id: str,
        material_type: str,
        missing_message: str,
    ) -> dict:
        if material_id is None:
            raise ValidationError(missing_message)
        row = self.source_repository.get(connection, material_id)
        if row["workspace_id"] != workspace_id:
            raise ValidationError("Source material does not belong to this workspace")
        if row["type"] != material_type:
            raise ValidationError("Source material type does not match this workflow")
        return row

    def _resolve_account_profile(
        self,
        connection,
        workspace: dict,
        payload: AnalysisRunCreate,
    ) -> dict:
        if payload.manual_account_profile and payload.account_profile_material_id:
            raise ValidationError(
                "Use either manual account profile or account profile material"
            )
        if payload.manual_account_profile is not None:
            content = payload.manual_account_profile.strip()
            if not content:
                raise ValidationError("Manual account profile cannot be blank")
            return {
                "source": "manual",
                "inputAssetId": None,
                "materialId": None,
                "name": "Manual profile",
                "content": content,
                "updatedAt": None,
            }
        account_profile_asset_id = (
            payload.account_profile_input_asset_id
            or payload.account_profile_material_id
        )
        if account_profile_asset_id is not None:
            material = self._require_material(
                connection,
                account_profile_asset_id,
                workspace["id"],
                SourceMaterialType.ACCOUNT_PROFILE.value,
                "Account profile input asset is required",
            )
            return {
                "source": "input_asset",
                "inputAssetId": material["id"],
                "materialId": material["id"],
                "name": material["name"],
                "content": material["text_content"] or "",
                "updatedAt": material["updated_at"],
            }
        return {
            "source": "workspace",
            "inputAssetId": None,
            "materialId": None,
            "name": workspace["name"],
            "content": workspace["account_positioning"],
            "updatedAt": workspace["updated_at"],
        }

    def _read_upload_text(self, stored_key: str) -> str:
        root = self.settings.upload_directory.resolve()
        path = (root / stored_key).resolve()
        if root not in path.parents:
            raise ValidationError("Stored CSV path is invalid")
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValidationError("Stored CSV must use UTF-8 encoding") from error

    def _rank_trend_posts(self, csv_text: str) -> list[dict[str, str | int]]:
        reader = csv.reader(io.StringIO(csv_text, newline=""))
        try:
            raw_headers = next(reader)
        except StopIteration as error:
            raise ValidationError("Stored CSV must contain a header row") from error
        headers = [self._normalize_trend_header(header) for header in raw_headers]
        posts: list[dict[str, str | int]] = []
        for values in reader:
            row = {
                headers[index]: value.strip()
                for index, value in enumerate(values[: len(headers)])
                if headers[index]
            }
            title = str(row.get("title") or row.get("标题") or "").strip()
            if not title:
                continue
            likes = self._parse_int(row.get("likes"))
            collects = self._parse_int(row.get("collects"))
            comments = self._parse_int(row.get("comments"))
            posts.append(
                {
                    "rankSourceIndex": len(posts) + 1,
                    "title": title,
                    "likes": likes,
                    "collects": collects,
                    "comments": comments,
                    "tags": str(row.get("tags") or ""),
                    "contentSnippet": str(row.get("content_snippet") or "")[:180],
                    "engagementScore": likes + collects,
                }
            )
        posts.sort(key=lambda post: int(post["engagementScore"]), reverse=True)
        return posts[:50]

    @staticmethod
    def _normalize_trend_header(header: str) -> str:
        normalized = header.strip().lower()
        replacements = {
            "标题": "title",
            "获赞数": "likes",
            "点赞": "likes",
            "收藏数": "collects",
            "收藏": "collects",
            "评论数": "comments",
            "评论": "comments",
            "标签": "tags",
            "正文": "content_snippet",
            "内容": "content_snippet",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        return normalized

    @staticmethod
    def _parse_int(value: object) -> int:
        try:
            return int(str(value or "0").replace(",", "").strip())
        except ValueError:
            return 0

    @staticmethod
    def _to_response(row: dict) -> AnalysisRunResponse:
        snapshot = json.loads(row["input_snapshot_json"])
        return AnalysisRunResponse.model_validate(
            {
                **row,
                "origin": snapshot.get("origin"),
                "input_snapshot": snapshot,
                "stage_results": json.loads(row["stage_results_json"]),
                "stage_errors": json.loads(row["stage_errors_json"]),
                "model_metadata": json.loads(row["model_metadata_json"]),
            }
        )

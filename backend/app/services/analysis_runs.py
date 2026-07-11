from __future__ import annotations

import csv
import io
import json

from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    AnalysisRunCreate,
    AnalysisRunResponse,
    AnalysisRunStatus,
    AnalysisRunSummary,
    AnalysisRunTransition,
    AnalysisStageUpdate,
    SourceMaterialType,
    WorkflowType,
)
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.source_materials import SourceMaterialRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now

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
}


class AnalysisRunService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: AnalysisRunRepository,
        workspace_repository: WorkspaceRepository,
        source_repository: SourceMaterialRepository,
        settings: Settings,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.source_repository = source_repository
        self.settings = settings

    def create(
        self, workspace_id: str, payload: AnalysisRunCreate
    ) -> AnalysisRunResponse:
        with self.database.transaction() as connection:
            workspace = self.workspace_repository.get(connection, workspace_id)
            snapshot = self._build_input_snapshot(connection, workspace, payload)
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                workflow_type=payload.workflow_type.value,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                now=utc_now(),
            )
        return self._to_response(row)

    def list(self, workspace_id: str) -> list[AnalysisRunSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        return [AnalysisRunSummary.model_validate(row) for row in rows]

    def get(self, run_id: str) -> AnalysisRunResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, run_id)
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
        return self._to_response(row)

    def _build_input_snapshot(
        self,
        connection,
        workspace: dict,
        payload: AnalysisRunCreate,
    ) -> dict:
        base = {
            "mode": payload.mode,
            "workspaceId": workspace["id"],
            "workspaceName": workspace["name"],
            "accountPositioning": workspace["account_positioning"],
            "positioningVersion": workspace["positioning_version"],
        }
        if payload.workflow_type == WorkflowType.ACCOUNT_DIAGNOSIS:
            historical = self._require_material(
                connection,
                payload.historical_posts_material_id,
                workspace["id"],
                SourceMaterialType.HISTORICAL_POSTS.value,
                "Historical posts material is required",
            )
            comments = self._require_material(
                connection,
                payload.comments_material_id,
                workspace["id"],
                SourceMaterialType.COMMENTS.value,
                "Comments material is required",
            )
            return {
                **base,
                "historicalPosts": {
                    "materialId": historical["id"],
                    "name": historical["name"],
                    "content": historical["text_content"],
                    "updatedAt": historical["updated_at"],
                },
                "comments": {
                    "materialId": comments["id"],
                    "name": comments["name"],
                    "content": comments["text_content"],
                    "updatedAt": comments["updated_at"],
                },
            }

        trend_csv = self._require_material(
            connection,
            payload.trend_csv_material_id,
            workspace["id"],
            SourceMaterialType.TREND_CSV.value,
            "Trend CSV material is required",
        )
        return {
            **base,
            "trendCsv": {
                "materialId": trend_csv["id"],
                "name": trend_csv["name"],
                "keyword": trend_csv["keyword"],
                "originalFilename": trend_csv["original_filename"],
                "rowCount": trend_csv["row_count"],
                "updatedAt": trend_csv["updated_at"],
                "rankedPosts": self._rank_trend_posts(
                    self._read_upload_text(trend_csv["stored_key"])
                ),
                "ranking": {
                    "method": "likes_plus_collects_desc",
                    "limit": 50,
                },
            },
        }

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
        return AnalysisRunResponse.model_validate(
            {
                **row,
                "input_snapshot": json.loads(row["input_snapshot_json"]),
                "stage_results": json.loads(row["stage_results_json"]),
                "stage_errors": json.loads(row["stage_errors_json"]),
                "model_metadata": json.loads(row["model_metadata_json"]),
            }
        )

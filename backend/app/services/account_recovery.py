"""Explicit, immutable account-diagnosis recovery using the original inputs."""

import json

from app.errors import ConflictError, ValidationError
from app.services.common import utc_now


def recover_account(service, run_id: str, stage: str):
    if stage not in {"profile", "pain_points", "topics"}:
        raise ValidationError("请选择账号画像、读者反馈或选题阶段。")
    with service.database.transaction() as c:
        source = service.repository.get(c, run_id)
        if source["workflow_type"] != "account_diagnosis":
            raise ValidationError("此入口只恢复账号诊断。")
        if source["status"] not in {"failed", "partially_completed", "completed"}:
            raise ConflictError("请等待当前诊断结束。")
        key = f"account-recovery:{run_id}"
        existing = service.repository.get_by_idempotency_key(
            c,
            workspace_id=source["workspace_id"],
            idempotency_key=key,
        )
        if existing:
            if json.loads(existing["model_metadata_json"])["recovery"]["stage"] != stage:
                raise ConflictError("此记录已有恢复任务，请打开该任务后继续。")
            return service._to_response(existing)
        results = json.loads(source["stage_results_json"])
        errors = json.loads(source["stage_errors_json"])
        metadata = json.loads(source["model_metadata_json"])
        image_failures = any(
            r.get("status") == "failed"
            for r in metadata.get("profile", {}).get("imageReadings", [])
        )
        if (
            stage not in errors
            and not (stage == "topics" and metadata.get("topicsStale"))
            and not (stage == "profile" and image_failures)
        ):
            raise ValidationError("该阶段已经完成，无需重试。")
        results.pop(stage, None)
        errors.pop(stage, None)
        metadata["recovery"] = {"sourceRunId": run_id, "stage": stage}
        metadata["topicsStale"] = bool(stage != "topics" and results.get("topics"))
        row = service.repository.create(
            c,
            workspace_id=source["workspace_id"],
            workflow_type=source["workflow_type"],
            input_snapshot_json=source["input_snapshot_json"],
            idempotency_key=key,
            now=utc_now(),
        )
        c.execute(
            "UPDATE analysis_runs SET stage_results_json=?, stage_errors_json=?, "
            "model_metadata_json=?, user_notes=?, review_status=? WHERE id=?",
            (
                json.dumps(results, ensure_ascii=False),
                json.dumps(errors, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                source["user_notes"],
                source["review_status"],
                row["id"],
            ),
        )
        return service._to_response(service.repository.get(c, row["id"]))

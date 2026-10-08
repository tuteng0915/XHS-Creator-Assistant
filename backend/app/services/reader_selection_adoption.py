"""Validate recommendation adoption inside the simulation creation transaction."""
from app.errors import ConflictError, ValidationError
from app.models import SimulationRunCreate
from app.services.reader_selection_requests import ReaderSelectionRequestService
from app.services.reader_selections import ReaderSelectionService


def selection_adoption_snapshot(c, database, workspace_id: str, payload: SimulationRunCreate):
    if payload.reader_selection_id is None:
        if payload.reader_selection_input_hash is not None:
            raise ValidationError("推荐指纹需要配合推荐记录使用")
        return ({"source": "manual", "actualFanIds": list(payload.simulated_fan_ids)}
                if payload.simulated_fan_ids is not None else None)
    if payload.reader_selection_input_hash is None or payload.simulated_fan_ids is None:
        raise ValidationError("采用推荐需要提供原输入指纹和最终读者名单")
    if payload.audience_analysis_id is not None:
        raise ValidationError("采用推荐不能同时使用旧受众分析来源")
    selections = ReaderSelectionService(database)
    requests = ReaderSelectionRequestService(selections)
    row = selections.repository.get(c, workspace_id, payload.reader_selection_id)
    saved = selections.response(row)
    if saved.status not in {"completed", "partially_completed"} or saved.result is None:
        raise ConflictError("推荐尚未成功完成，请等待或手动选择读者")
    if not saved.result.proposed_readers:
        raise ConflictError("这次推荐没有匹配读者，请按手动选择继续")
    if saved.input_hash != payload.reader_selection_input_hash:
        raise ConflictError("推荐输入指纹不匹配，请重新打开推荐或手动选择")
    request = requests.stored_request(row)
    if request is None:
        raise ConflictError("旧推荐缺少来源，不能核验，请重新推荐或手动选择")
    if (request.topic_id, request.draft_id, request.manual_topic,
        request.source_material_id, request.note_id, request.account_profile_id) != (
        payload.topic_id, payload.draft_id, payload.manual_topic,
        payload.source_material_id, payload.note_id, payload.account_profile_id,
    ):
        raise ConflictError("推荐不属于当前分析对象，请重新推荐或手动选择")
    if request.panel_task != payload.panel_task:
        raise ConflictError("试读任务已变化，请重新推荐，或按当前手选名单继续")
    if requests.freshness(c, row).status != "current":
        raise ConflictError("推荐依据已变化或不可用，请重新推荐，或按当前手选名单继续")
    candidate_ids = {candidate.id for candidate in saved.input_snapshot.candidates}
    if not set(payload.simulated_fan_ids).issubset(candidate_ids):
        raise ValidationError("最终读者不属于这次推荐的候选池")
    candidate_names = {
        candidate.id: candidate.name for candidate in saved.input_snapshot.candidates
    }
    proposed = [{**reader.model_dump(by_alias=True), "name": candidate_names[reader.fan_id]}
                for reader in saved.result.proposed_readers]
    proposed_ids = [reader.fan_id for reader in saved.result.proposed_readers]
    return {
        "source": "recommended" if payload.simulated_fan_ids == proposed_ids
        and not payload.persona_overrides else "adjusted",
        "readerSelectionId": saved.id, "inputHash": saved.input_hash,
        "proposedReaders": proposed, "actualFanIds": list(payload.simulated_fan_ids),
        **({"personaOverridesAfterRecommendation": {
            fan_id: override.model_dump(by_alias=True, exclude_none=True)
            for fan_id, override in payload.persona_overrides.items()
        }} if payload.persona_overrides else {}),
        "validationWarnings": [warning.model_dump(by_alias=True)
                               for warning in saved.result.validation_warnings],
    }

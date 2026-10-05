from copy import deepcopy

import pytest
from pydantic import ValidationError as PydanticValidationError
from test_simulated_fans import seeded as seeded

from app.errors import ValidationError
from app.services.audience_target import reader_visible_target
from app.services.reader_selection import (
    prepare_reader_selection,
    selection_input_hash,
    validate_reader_selection,
)
from app.services.simulated_fans import FanResponse
from app.workflows.audience_simulation import AudienceSimulationWorkflowService


def fan(id="a", **changes):
    return FanResponse.model_validate({
        "id": id, "workspaceId": "w", "sourceAnalysisId": "analysis", "sourceGroupId": id,
        "status": "active", "createdAt": "2026-10-03T00:00:00Z",
        "updatedAt": "2026-10-03T00:00:00Z", "original": {"profile": "不可覆盖的原始定义"},
        "editable": {"name": f"读者{id}", "interests": ["职业发展", "个人成长"],
                     "profile": "想先试，再核对成本🌱", "coreConcern": "明确本周第一步",
                     "contentPreference": "有步骤和成本", "expressionStyle": "先收藏，必要时提问"},
        **changes,
    })


def snapshot(**changes):
    return {"workspaceId": "w", "accountPositioning": "跨领域创作",
            "topic": {"title": "文科生 AI 小练习", "body": "先选一个任务，半小时做个样例。",
                      "whyItFits": "内部策略", "associatedPainPoint": "不可见的痛点"}, **changes}


def proposal(id="a", **changes):
    return {"fanId": id, "fitReason": "具体小任务与尝试需求相关",
            "contribution": "关注开始所需的步骤与投入", "relation": "direct", **changes}


def test_pack_uses_all_active_editable_cards_and_does_not_mutate_sources():
    fans = [fan(str(i)) for i in range(8)] + [fan("old", status="archived")]
    before = [f.model_dump() for f in fans]
    source = snapshot(readerSelection={"reason": "他必须反对"}, previousReactions=["旧评论"])
    original = deepcopy(source)
    inputs = prepare_reader_selection("w", source, fans)
    assert len(inputs.candidates) == 8  # desiredCount is not an input pool cutoff.
    assert inputs.candidates[0].profile == fans[0].editable.profile
    assert "original" not in inputs.candidates[0].model_dump()
    assert set(inputs.model_dump(by_alias=True)) == {
        "workspaceId", "accountPositioning", "target", "candidates",
        "desiredCount", "selectorVersion", "panelTask",
    }
    assert "内部策略" not in str(inputs.target)
    assert "他必须反对" not in str(inputs.target)
    inputs.candidates[0].interests.append("新增")
    inputs.target["body"] = "修改输入副本"
    assert [f.model_dump() for f in fans] == before
    assert source == original


@pytest.mark.parametrize("change", ["account", "duplicate", "version", "snapshot"])
def test_rejects_mixed_account_or_ambiguous_input_pool(change):
    fans, source = [fan()], snapshot()
    if change == "account":
        fans.append(fan("b", workspaceId="other"))
    elif change == "duplicate":
        fans.append(fan())
    elif change == "version":
        fans[0].updated_at = " "
    else:
        source["workspaceId"] = "other"
    with pytest.raises(ValidationError):
        prepare_reader_selection("w", source, fans)


@pytest.mark.parametrize("count", [0, -1, True, "3", 2.5])
def test_requested_count_must_be_a_positive_integer(count):
    with pytest.raises(PydanticValidationError):
        prepare_reader_selection("w", snapshot(), [fan()], desired_count=count)


def test_has_no_three_reader_cap_and_accepts_fewer_valid_matches():
    inputs = prepare_reader_selection("w", snapshot(), [fan(str(i)) for i in range(6)],
                                      desired_count=6)
    result = validate_reader_selection({"proposedReaders": [proposal(str(i)) for i in range(5)]},
                                       inputs)
    assert result.status == "completed"
    assert len(result.proposed_readers) == 5


def test_no_match_is_a_valid_result_even_for_empty_pool():
    for fans in ([], [fan()]):
        inputs = prepare_reader_selection("w", snapshot(), fans)
        result = validate_reader_selection(
            {"proposedReaders": [], "unmatchedReason": "暂无合适视角"}, inputs,
        )
        assert result.status == "completed"
        assert result.proposed_readers == []


@pytest.mark.parametrize("output", [None, [], {}, {"proposedReaders": "a"},
    {"proposedReaders": []}, {"proposedReaders": [], "unmatchedReason": " "},
    {"proposedReaders": [proposal()], "persona": "重写人物"}])
def test_rejects_invalid_envelopes_without_inventing_fallbacks(output):
    with pytest.raises(ValidationError):
        validate_reader_selection(output, prepare_reader_selection("w", snapshot(), [fan()]))


def test_invalid_items_preserve_valid_items_and_report_their_indices():
    inputs = prepare_reader_selection("w", snapshot(), [fan(), fan("b")], desired_count=5)
    result = validate_reader_selection({"proposedReaders": [
        proposal(), proposal("unknown"), proposal("b", profile="改成爱争论的人"),
        proposal("b", fitReason="  "), 123,
    ]}, inputs)
    assert result.status == "partially_completed"
    assert [r.fan_id for r in result.proposed_readers] == ["a"]
    assert [(w.index, w.code) for w in result.validation_warnings] == [
        (1, "unknown_reader"), (2, "invalid_item"), (3, "invalid_item"), (4, "invalid_item"),
    ]


def test_duplicate_ids_are_all_rejected_without_choosing_between_conflicting_reasons():
    inputs = prepare_reader_selection("w", snapshot(), [fan(), fan("b")])
    result = validate_reader_selection({"proposedReaders": [
        proposal(), proposal(fitReason="另一理由"), proposal("b", relation="adjacent"),
    ]}, inputs)
    assert result.status == "partially_completed"
    assert [r.fan_id for r in result.proposed_readers] == ["b"]
    assert [w.code for w in result.validation_warnings] == ["duplicate_reader"] * 2
    failed = validate_reader_selection({"proposedReaders": [proposal("missing")]}, inputs)
    assert failed.status == "failed"
    assert failed.proposed_readers == []


def test_rejects_excess_results_instead_of_silently_taking_the_first_three():
    inputs = prepare_reader_selection("w", snapshot(), [fan(str(i)) for i in range(4)])
    with pytest.raises(ValidationError, match="未自动裁剪"):
        validate_reader_selection({"proposedReaders": [proposal(str(i)) for i in range(4)]}, inputs)


def test_same_pool_different_topics_keeps_roles_but_changes_input_fingerprint():
    fans = [fan(), fan("b")]
    fans[1].editable.profile = "先核对投入和替代路径，再决定是否尝试"
    fans[1].editable.core_concern = "判断时间和预算是否值得投入"
    inputs = prepare_reader_selection("w", snapshot(), fans)
    other = prepare_reader_selection("w", snapshot(topic={"title": "留学预算如何安排", "body": ""}),
                                     fans)
    assert inputs.candidates == other.candidates
    assert inputs.candidates[0].interests == inputs.candidates[1].interests
    assert inputs.candidates[0].profile != inputs.candidates[1].profile
    assert selection_input_hash(inputs) != selection_input_hash(other)
    before = inputs.model_dump()
    response = {"proposedReaders": [proposal("b"), proposal()]}
    result = validate_reader_selection(response, inputs)
    assert [r.fan_id for r in result.proposed_readers] == ["b", "a"]
    assert inputs.model_dump() == before
    second_result = validate_reader_selection({"proposedReaders": [proposal(
        "b", fitReason="预算安排与核对投入的需求相关", contribution="比较不同支出的取舍",
    )]}, other)
    assert [r.fan_id for r in second_result.proposed_readers] == ["b"]
    assert other.candidates == inputs.candidates
    result.proposed_readers[0].fit_reason = "修改副本"
    assert response["proposedReaders"][0]["fitReason"] != "修改副本"
    assert selection_input_hash(inputs) == selection_input_hash(inputs.model_copy(deep=True))
    revised = inputs.model_copy(deep=True)
    revised.candidates[0].updated_at = "2026-10-03T01:00:00Z"
    assert selection_input_hash(inputs) != selection_input_hash(revised)


@pytest.mark.parametrize("field,value", [
    ("fitReason", "长" * 201), ("contribution", " "), ("relation", "critic"),
    ("name", "新名字"), ("interests", ["偷偷换兴趣"]),
])
def test_output_cannot_redefine_people_or_assign_a_mandatory_stance(field, value):
    inputs = prepare_reader_selection("w", snapshot(), [fan()])
    result = validate_reader_selection({"proposedReaders": [proposal(**{field: value})]}, inputs)
    assert result.status == "failed"
    assert result.validation_warnings[0].code == "invalid_item"


def test_archived_or_other_account_ids_cannot_be_returned_as_matches():
    inputs = prepare_reader_selection("w", snapshot(), [fan(), fan("old", status="archived")])
    result = validate_reader_selection({"proposedReaders": [proposal("old"), proposal("other")]},
                                       inputs)
    assert result.status == "failed"
    assert all(w.code == "unknown_reader" for w in result.validation_warnings)


def test_shared_draft_target_preserves_old_shape_and_excludes_strategy_and_selection_reasons():
    source = snapshot(targetType="draft", readerSelection={"fitReason": "必须质疑"}, draft={
        "generatedSnapshot": {"secret": "旧生成"},
        "editableContent": {"structure": {"topicChosen": "当前题目", "internal": "内部",
            "outline": [{"sec": "开头", "ct": "正文", "intent": "说服观众"}, None]},
            "brief": {"corePoint": "核心观点", "argumentPath": ["第一步"],
                      "targetAudience": "目标"}},
    })
    before = deepcopy(source)
    target = reader_visible_target(source)
    assert target == AudienceSimulationWorkflowService._simulation_target_context(source)
    assert target["draft"] == {"editableContent": {
        "structure": {"topicChosen": "当前题目", "outline": [{"sec": "开头", "ct": "正文"}]},
        "brief": {"corePoint": "核心观点", "argumentPath": ["第一步"]},
    }}
    assert target["previewLevel"] == "outline"
    assert "必须质疑" not in str(target)
    target["draft"]["editableContent"]["brief"]["argumentPath"].append("新增")
    assert source == before
    assert reader_visible_target(snapshot(topic={"title": "只有标题"}))["previewLevel"] == "concept"


def test_saved_asset_adapter_uses_current_editable_values_without_writing(app, seeded):
    wid, _, _, _ = seeded
    fans = app.state.simulated_fan_service.list(wid)
    original = [f.model_dump() for f in fans]
    inputs = prepare_reader_selection(wid, snapshot(workspaceId=wid), fans)
    assert inputs.candidates[0].id == fans[0].id
    assert inputs.candidates[0].profile == fans[0].editable.profile
    validate_reader_selection({"proposedReaders": [proposal(fans[0].id)]}, inputs)
    assert [f.model_dump() for f in app.state.simulated_fan_service.list(wid)] == original

import pytest
from pydantic import ValidationError

from app.services.account_report_contract import (
    AccountReportOutputError,
    OverviewOutput,
    ReadingOutput,
)


def test_optional_overview_fields_do_not_require_empty_placeholders():
    parsed = OverviewOutput.model_validate({"displayNote": "辅助说明"})
    assert parsed.model_dump() == {
        "summary": None, "directions": [], "hypotheses": [], "readings": [],
    }
    parsed.directions.append({"text": "独立列表"})
    assert OverviewOutput().directions == []


def test_short_valid_questions_and_directions_are_allowed_without_length_gates():
    output = {
        "summary": {"text": " 生活记录 ", "noteIds": [" n1 "], "extra": "显示说明"},
        "directions": [{"text": " 日常 ", "noteIds": ["n1"]}],
        "hypotheses": [" 如何制造反差？ "],
        "readings": [{"noteId": "n1", "question": " 如何制造反差？ ", "extra": True}],
    }
    parsed = OverviewOutput.model_validate(output)
    assert parsed.summary.text == "生活记录"
    assert parsed.summary.noteIds == ["n1"]
    assert parsed.directions[0].text == "日常"
    assert parsed.readings[0].question == "如何制造反差？"
    assert parsed.hypotheses == ["如何制造反差？"]
    assert "extra" not in str(parsed.model_dump())


def test_auxiliary_observations_do_not_reject_rich_text_or_extra_optional_entries():
    output = {
        "assessment": "  " + "具体观察。" * 300 + "  ",
        "correction": "  " + "修正说明。" * 100 + "  ",
        "examples": [{"excerptIds": ["b1"], "interpretation": "解读。" * 100}] * 4,
        "other": "附加信息",
    }
    parsed = ReadingOutput.model_validate(output)
    assert parsed.assessment == output["assessment"].strip()
    assert parsed.correction == output["correction"].strip()
    assert len(parsed.examples) == 4
    overview = OverviewOutput.model_validate({
        "directions": [{"text": "一段观察。" * 100, "noteIds": ["n1"]}] * 4,
        "readings": [{"noteId": "n1", "question": "一个问题？" * 100}] * 4,
    })
    assert len(overview.directions) == len(overview.readings) == 4


def test_reading_only_needs_its_observation_and_retains_explicit_sources():
    assert ReadingOutput.model_validate({"assessment": " 先给场景。 "}).model_dump() == {
        "assessment": "先给场景。", "correction": "", "examples": [],
    }
    reading = ReadingOutput.model_validate({"assessment": "观察", "examples": [
        {"excerptIds": ["b1"], "interpretation": " 一个例子 ", "display": "可忽略"},
    ]})
    assert reading.examples[0].model_dump() == {
        "excerptIds": ["b1"], "interpretation": "一个例子",
    }


@pytest.mark.parametrize("assessment", [None, "", " \n\t ", 123, [], {}])
def test_empty_or_nontext_reading_is_still_not_an_observation(assessment):
    with pytest.raises(ValidationError):
        ReadingOutput.model_validate({"assessment": assessment})


@pytest.mark.parametrize("value", [
    {"summary": {"text": "观察", "noteIds": []}},
    {"summary": {"text": "观察", "noteIds": [" "]}},
    {"readings": [{"question": "如何制造反差？"}]},
    {"readings": [{"noteId": "n1", "question": " "}]},
])
def test_present_auxiliary_items_still_need_a_real_reference_shape(value):
    with pytest.raises(ValidationError):
        OverviewOutput.model_validate(value)


def test_output_error_keeps_only_safe_metadata_and_numeric_usage():
    error = AccountReportOutputError("invalid_json", metadata={
        "provider": "qwen", "model": "qwen3.8-max", "stage": "read",
        "responseFormat": "json_object",
        "raw": "secret", "reasoning_content": "secret", "api_key": "secret",
        "usage": {"total_tokens": 5, "completion_tokens": True, "prompt_tokens": -1,
                  "input_tokens": "8", "other": 100,
                  "completion_tokens_details": {"reasoning_tokens": 2,
                                                "reasoning_content": "secret"}},
    })
    assert error.code == "invalid_json"
    assert error.metadata is error.model_metadata
    assert error.model_metadata["usage"] == {"total_tokens": 5, "reasoning_tokens": 2}
    assert "secret" not in str(error.__dict__)
    override = AccountReportOutputError("source_validation", usage={"total_tokens": 9})
    assert override.model_metadata == {"usage": {"total_tokens": 9}}
    override.pipeline_metadata = {"requestCount": 2}
    assert override.pipeline_metadata["requestCount"] == 2

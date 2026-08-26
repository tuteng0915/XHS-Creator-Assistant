from pathlib import Path

from app.models import ModelOperation
from app.services.model_calls import ModelCallService

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qwen"


def test_qwen_fixture_pain_points_wrapper_and_snake_case_are_normalized() -> None:
    text = (FIXTURE_ROOT / "pain_points_wrapped.json").read_text(encoding="utf-8")

    output = ModelCallService._parse_model_output(ModelOperation.PAIN_POINTS, text)

    assert "painPoints" in output
    assert output["painPoints"][0]["theme"] == "选校决策焦虑"


def test_qwen_fixture_agent_chat_fenced_json_and_aliases_are_normalized() -> None:
    text = (FIXTURE_ROOT / "agent_chat_fenced.txt").read_text(encoding="utf-8")

    output = ModelCallService._parse_model_output(ModelOperation.AGENT_CHAT, text)

    assert output["reply"].startswith("模型 API 可用")
    assert output["proposedActions"][0]["type"] == "topic.create_or_update"


def test_qwen_fixture_video_quality_alias_is_normalized() -> None:
    text = (FIXTURE_ROOT / "video_quality_alias.json").read_text(encoding="utf-8")

    output = ModelCallService._parse_model_output(
        ModelOperation.VIDEO_QUALITY_ANALYSIS,
        text,
    )

    assert output["videoQuality"]["overallScore"] == 62
    assert output["videoQuality"]["evidenceConfidence"] == "低"


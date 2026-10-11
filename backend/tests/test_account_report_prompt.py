import asyncio
import json

import pytest

from app.errors import ValidationError
from app.models import ModelCallResponse, ModelOperation
from app.services.account_report_prompt import (
    LEGACY_PROFILE_PROMPT_VERSION,
    PROFILE_PROMPT_VERSION,
    SOURCE_LED_PROFILE_PROMPT,
    build_source_led_profile_prompt,
    profile_prompt_version,
)
from app.services.model_calls import PROMPT_PROFILE, ModelCallService


def test_optional_readings_do_not_replace_the_whole_account_or_structure_task():
    context = {"historicalPosts": json.dumps({
        "schemaVersion": "account-reading-input/v2", "notes": [
            {"noteId": "saved-a", "title": "一篇具体作品", "body": "先观察。再作判断。"},
            {"noteId": "saved-b", "title": "另一种内容价值", "body": "提供可用的方法。"},
        ],
    }, ensure_ascii=False)}
    system, default_user = build_source_led_profile_prompt(context)
    enhanced_system, enhanced_user = build_source_led_profile_prompt(context, reading_observations=[
        {"noteId": "n1", "assessment": "值得参考的观察", "correction": "", "examples": []},
    ])
    assert enhanced_system == system == SOURCE_LED_PROFILE_PROMPT
    assert enhanced_user.startswith(default_user)
    assert "从全部所选作品中认识题材、具体做法与阅读价值" in enhanced_user
    assert "未精读的作品同样可以成为代表作" in enhanced_user
    assert "正文组织直接回看代表作全文" in enhanced_user
    assert "回到对应原句再决定是否采用" in enhanced_user
    assert "提供可用的方法。" in enhanced_user
    assert "值得参考的观察" in enhanced_user
    assert "QSheep" not in enhanced_user and "放弃保研" not in enhanced_user
    # None of this changes the single-call rollback's prompt or source input.
    assert "以下是可选精读素材" not in default_user
    assert build_source_led_profile_prompt(context, reading_observations=[]) == (
        system, default_user,
    )


def test_structured_profile_uses_source_led_task_without_modifying_input(settings):
    packet = {"schemaVersion": "account-reading-input/v2", "notes": [
        {"noteId": "n1", "title": "同题的不同写法", "body": "保留 原始标点……"},
    ]}
    context = {"positioning": "虚构账号", "historicalPosts": json.dumps(packet, ensure_ascii=False)}
    system, user = ModelCallService(settings)._build_prompt(ModelOperation.PROFILE, context)
    assert system == SOURCE_LED_PROFILE_PROMPT
    # Qwen's JSON-object mode requires a literal JSON instruction in the messages.
    assert "json" in system.lower()
    actual = json.loads(user.split("历史笔记：\n", 1)[1].split("\n\n请按", 1)[0])
    assert actual["schemaVersion"] == "account-reading-input/v3"
    assert actual["notes"][0]["title"] == packet["notes"][0]["title"]
    assert "".join(item["text"] for item in actual["notes"][0]["bodyExcerpts"]) \
        == packet["notes"][0]["body"]
    assert json.loads(context["historicalPosts"]) == packet
    assert "titleReadings" in system and "structureReading" in system
    assert "source-led/v3" in user
    assert "固定六部分模板" in user
    assert "每项只拆一个原始标题" in system
    assert "内容决策" in system
    assert profile_prompt_version(context) == PROFILE_PROMPT_VERSION
    # No examples from QSheep's old reports are planted as model facts.
    assert "QSheep" not in system and "放弃保研" not in system


@pytest.mark.parametrize("source", [None, "旧版文字材料", "{", "[]", "null",
                                    '{"schemaVersion":"account-reading-input/v1"}'])
def test_plain_text_and_unknown_packets_keep_legacy_prompt_and_version(settings, source):
    context = {"historicalPosts": source}
    system, _ = ModelCallService(settings)._build_prompt(ModelOperation.PROFILE, context)
    assert system == PROMPT_PROFILE
    assert profile_prompt_version(context) == LEGACY_PROFILE_PROMPT_VERSION


def test_template_has_separate_deliverables_and_no_account_specific_examples():
    for heading in ("账号印象", "内容方向", "具体优势", "标题与开头", "正文组织", "下一步建议"):
        assert heading in SOURCE_LED_PROFILE_PROMPT
    assert "下次写{已有题材}时，可以{一个具体编辑动作}" in SOURCE_LED_PROFILE_PROMPT
    assert "不诊断原文不存在的缺点" in SOURCE_LED_PROFILE_PROMPT
    assert "没有依据的可选内容用空数组" in SOURCE_LED_PROFILE_PROMPT
    assert "不推断图片、视频、未选篇目" in SOURCE_LED_PROFILE_PROMPT
    assert "QSheep" not in SOURCE_LED_PROFILE_PROMPT
    assert "传媒" not in SOURCE_LED_PROFILE_PROMPT


def test_pattern_template_separates_relationships_and_scopes_style_examples():
    for term in ("narrative", "comparison", "repeated_blocks", "scope=section", "scopeLabel",
                 "expressionReadings", "technique", "application", "examples", "fromExcerptId"):
        assert term in SOURCE_LED_PROFILE_PROMPT
    assert "不预设线性三步" in SOURCE_LED_PROFILE_PROMPT
    assert "只有一篇就只解释这一篇" in SOURCE_LED_PROFILE_PROMPT
    assert "不把自我呼唤当自称" in SOURCE_LED_PROFILE_PROMPT
    assert "opening必须来自实际开头" in SOURCE_LED_PROFILE_PROMPT
    assert "不再同时输出viralStructure、hookStyles、voiceFingerprint" in SOURCE_LED_PROFILE_PROMPT
    # The illustrative JSON is a real contract, not pseudo-JSON the model must guess at.
    example = json.loads('{"profile":' + SOURCE_LED_PROFILE_PROMPT.split('\n{"profile":', 1)[1])
    profile = example["profile"]
    assert profile["reportFormat"] == "source-led/v3"
    assert set(profile["structureReading"]) == {
        "noteId", "kind", "scope", "scopeLabel", "overview", "units",
    }
    assert {"viralStructure", "hookStyles", "voiceFingerprint"}.isdisjoint(profile)
    assert list(profile["expressionReadings"][0]).index("examples") \
        < list(profile["expressionReadings"][0]).index("technique")
    assert set(profile["expressionReadings"][0]["examples"][0]) == {
        "noteId", "fromExcerptId", "toExcerptId",
    }
    assert list(profile["structureReading"]).index("units") \
        < list(profile["structureReading"]).index("overview")
    assert "不能说正文已完成讲解" in SOURCE_LED_PROFILE_PROMPT


@pytest.mark.parametrize("fails", [False, True])
def test_structured_report_is_one_bounded_request_not_read_edit_loop(settings, monkeypatch, fails):
    service, calls = ModelCallService(settings), []
    context = {"historicalPosts": json.dumps({
        "schemaVersion": "account-reading-input/v2", "notes": [],
    })}
    response = ModelCallResponse(output={"profile": {"reportFormat": "source-led/v3"}},
                                 model_metadata={"model": "qwen-test"})

    async def call_once(operation, source, **kwargs):
        calls.append((operation, source, kwargs))
        if fails:
            raise ValidationError("接口失败")
        return response

    monkeypatch.setattr(service, "_call_qwen", call_once)
    if fails:
        with pytest.raises(ValidationError, match="接口失败"):
            asyncio.run(service.call_operation(ModelOperation.PROFILE, context))
    else:
        assert asyncio.run(service.call_operation(ModelOperation.PROFILE, context)) == response
    assert calls == [(ModelOperation.PROFILE, context, {})]

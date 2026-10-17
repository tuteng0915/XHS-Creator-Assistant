from copy import deepcopy

import pytest
from test_audience_simulation_workflow import collect
from test_panel_protocol import guided, recommendation
from test_simulated_fans import seeded as seeded
from test_workspace_api import send

from app.models import ModelCallResponse, ModelOperation
from app.services.editor_feedback import reader_concern_catalog, validate_editor_feedback
from app.services.feedback_anchors import feedback_anchor_catalog, feedback_anchor_prompt_context
from app.services.model_calls import PROMPT_SIMULATION_SYNTHESIS, ModelCallService
from app.workflows.audience_simulation import RealAudienceSimulationModelProvider

TOPIC = {
    "title": "先试一次",
    "body": "🌱先试一次。\n先试一次。",
    "panelTask": guided().model_dump(by_alias=True),
}
PERSONAS = [{"id": "a"}, {"id": "b"}]
REACTIONS = [
    {
        "messageId": "initial:a",
        "personaId": "a",
        "action": "no_comment",
        "understanding": "步骤清楚",
    }
]
REPLIES = [{"messageId": "reply:b", "personaId": "b", "response": "补充一点"}]


def card(**changes):
    return {
        "id": "f1",
        "kind": "keep",
        "sourceType": "reader",
        "sourceMessageIds": ["initial:a"],
        "target": {"field": "body", "quote": "先试一次。", "occurrence": 2},
        "observation": "步骤清楚",
        "reason": "能直接行动",
        "beneficiaries": ["a"],
        "priority": "first",
        **changes,
    }


def validate(raw, **changes):
    return validate_editor_feedback(
        raw,
        **{
            "topic": TOPIC,
            "personas": PERSONAS,
            "reactions": REACTIONS,
            "replies": REPLIES,
            **changes,
        },
    )


def test_repeat_anchor_uses_unicode_codepoints_and_private_source_stays_private():
    raw = [card()]
    before = deepcopy((raw, TOPIC, REACTIONS))
    result = validate(raw)
    saved = result["editorFeedback"][0]
    target = saved["target"]
    assert target["start"] == 7 and target["end"] == 12
    assert TOPIC["body"][target["start"] : target["end"]] == target["quote"]
    assert target["coordinateSystem"] == "unicode_code_points"
    assert len(target["contentHash"]) == 64
    assert saved["sources"] == [
        {"messageId": "initial:a", "personaId": "a", "channel": "private_reading"}
    ]
    assert (raw, TOPIC, REACTIONS) == before


def test_material_feedback_asks_author_without_proposing_facts():
    raw = card(kind="add_material", sourceType="editor_optional", sourceMessageIds=[],
               priority="optional", materialRequests=["哪个练习让你敢开口？"], suggestedText="")
    result = validate([raw])
    assert result["editorFeedbackValidation"]["status"] == "validated"
    assert result["editorFeedback"][0]["materialRequests"] == ["哪个练习让你敢开口？"]
    assert result["contentAdjustments"] == ["可选：步骤清楚；待作者补充：哪个练习让你敢开口？"]


@pytest.mark.parametrize("changes", [
    {"kind": "add_material"},
    {"kind": "add_material", "materialRequests": ["请补真实经历"], "suggestedText": "同伴鼓掌了"},
    {"kind": "rewrite", "materialRequests": ["请补真实经历"], "suggestedText": "同伴鼓掌了"},
])
def test_material_contract_does_not_masquerade_as_ready_copy(changes):
    result = validate([card(sourceType="editor_optional", sourceMessageIds=[],
                            priority="optional", **changes)])
    assert result["editorFeedback"] == []
    rejected = result["editorFeedbackValidation"]["rejected"]
    assert rejected[0]["reason"] == "invalid_material_contract"
    assert result["contentAdjustments"] == []


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"sourceMessageIds": []}, "invalid_source"),
        ({"sourceMessageIds": ["initial:missing"]}, "invalid_source"),
        ({"sourceMessageIds": ["initial:a", "initial:a"]}, "invalid_source"),
        ({"beneficiaries": ["unknown"]}, "unknown_beneficiary"),
        ({"target": {"field": "body", "quote": "没出现"}}, "invalid_anchor"),
        ({"target": {"field": "body", "quote": "先试一次。", "occurrence": 3}}, "invalid_anchor"),
        ({"target": {"field": "body", "quote": " "}}, "invalid_anchor"),
        (
            {"target": {"field": "body", "quote": "先试一次。", "occurrence": True}},
            "invalid_fields",
        ),
        ({"target": {"field": "whole", "quote": "先试一次。"}}, "invalid_anchor"),
        ({"sourceType": "editor_optional"}, "invalid_source"),
        ({"observation": ""}, "invalid_fields"),
    ],
)
def test_rejects_bad_card_and_retains_other_valid_feedback(change, reason):
    result = validate([card(**change), card(id="good")])
    assert [c["id"] for c in result["editorFeedback"]] == ["good"]
    assert result["editorFeedbackValidation"] == {
        "status": "partial",
        "rejected": [{"index": 0, "reason": reason}],
    }


def test_editor_optional_is_explicitly_optional_without_reader_attribution():
    saved = validate(
        [
            card(
                sourceType="editor_optional",
                sourceMessageIds=[],
                priority="optional",
                target={"field": "whole"},
            )
        ]
    )["editorFeedback"][0]
    assert saved["sources"] == []
    assert "start" not in saved["target"]
    assert not validate([card(sourceType="editor_optional", sourceMessageIds=[])])["editorFeedback"]


def test_duplicate_ids_blank_replies_and_missing_people_are_not_valid_sources():
    assert not validate([card(), card()])["editorFeedback"]
    assert not validate(
        [card(sourceMessageIds=["reply:b"])], replies=[{**REPLIES[0], "response": ""}]
    )["editorFeedback"]
    assert not validate([card()], personas=[{"id": "b"}])["editorFeedback"]
    assert not validate([card()], reactions=REACTIONS * 2)["editorFeedback"]


def test_public_reply_and_public_comment_channels_are_derived_not_model_claims():
    result = validate(
        [card(sourceMessageIds=["initial:a", "reply:b"])],
        reactions=[{**REACTIONS[0], "action": "comment", "quote": "步骤很清楚"}],
    )
    assert [s["channel"] for s in result["editorFeedback"][0]["sources"]] == [
        "public_comment",
        "public_reply",
    ]


def test_missing_empty_and_malformed_collections_are_distinct():
    assert validate(None)["editorFeedbackValidation"]["status"] == "not_returned"
    assert validate([])["editorFeedbackValidation"]["status"] == "validated"
    for raw in ({}, "broken", [card()] * 7):
        assert validate(raw)["editorFeedbackValidation"]["status"] == "invalid"


def test_title_and_body_cannot_be_joined_to_fabricate_an_anchor():
    assert not validate([card(target={"field": "title", "quote": "先试一次🌱"})])["editorFeedback"]
    assert validate([card(target={"field": "title", "quote": "先试一次"})])["editorFeedback"]
    changed = validate([card()], topic={**TOPIC, "body": TOPIC["body"] + "后来的修改"})
    assert (
        changed["editorFeedback"][0]["target"]["contentHash"]
        != validate([card()])["editorFeedback"][0]["target"]["contentHash"]
    )


def test_new_prompt_and_budget_do_not_change_legacy_synthesis(settings):
    service = ModelCallService(settings)
    operation = ModelOperation.SIMULATION_SYNTHESIS
    assert service._build_prompt(operation, {"topic": {}})[0] == PROMPT_SIMULATION_SYNTHESIS
    prompt = service._build_prompt(operation, {"topic": TOPIC})[0]
    assert "sourceMessageIds" in prompt and "editor_optional" in prompt
    assert "其他字段均为字符串" not in prompt
    assert '"editorFeedback":[]}}' in prompt
    assert prompt.count('{"synthesis":') == 1
    assert "reader 来源的修改必须对应这次反应中实际未解决的问题" in prompt
    assert "target.quote 不能填读者的评论" in prompt
    assert "suggestedText 必须对应 target.field" in prompt
    assert "contentAdjustments 由程序从有效反馈卡生成" in prompt
    assert "你是发布前预演的评审员" not in prompt
    assert service._output_budget(operation, {"topic": {}}) == 1600
    assert service._output_budget(operation, {"topic": TOPIC}) == 3200
    legacy_user = service._build_prompt(operation, {"topic": {}})[1]
    assert "textAnchors" not in legacy_user
    assert "readerConcerns" not in legacy_user
    user = service._build_prompt(operation, {"topic": TOPIC})[1]
    assert "textAnchors" in user
    assert "readerConcerns" in user
    assert feedback_anchor_catalog(TOPIC)["items"][0]["id"] in user
    assert "不能把“不上传私人信息”改说成“不上传”" in prompt


@pytest.mark.parametrize("kind", ["keep", "clarify"])
@pytest.mark.parametrize("new_protocol", [True, False])
def test_workflow_persists_feedback_diagnostics_without_mutating_topic_or_retrying(
    app, seeded, new_protocol, kind
):
    wid, target, _, _, payload = recommendation(
        app, seeded, guided(discussionEnabled=False) if new_protocol else None
    )
    payload.mode = "live"
    calls = []

    class Model:
        async def call_operation(self, operation, context):
            calls.append(operation)
            if operation == ModelOperation.SIMULATION_REACTION:
                output = {
                    "reaction": {
                        "personaId": context["persona"]["id"],
                        "action": "no_comment",
                        "stance": "理解",
                        "understanding": "有意思",
                        "concerns": ["不知道怎么开始"] if kind == "clarify" else [],
                    }
                }
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                source = context["reactions"][0]
                good = card(
                    kind=kind,
                    sourceMessageIds=[source["messageId"]],
                    beneficiaries=[source["personaId"]],
                    target={"field": "title", "anchorId":
                            feedback_anchor_catalog(context["topic"])["items"][0]["id"]},
                )
                if kind == "clarify":
                    good["readerConcernIds"] = [reader_concern_catalog(
                        context["personas"], context["reactions"], context["debateResponses"],
                    )["items"][0]["id"]]
                output = {
                    "synthesis": {
                        "verdict": "保留清楚的表达",
                        "contentAdjustments": ["旧格式建议仍可读"],
                        "editorFeedback": [good, card(id="bad")],
                    }
                }
            return ModelCallResponse(output=output, model_metadata={"model": "fake-feedback"})

    app.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(
        Model()
    )
    run = app.state.simulation_service.create(wid, payload)
    before = deepcopy(run.input_snapshot)
    events = collect(app, run.id)
    saved = app.state.simulation_service.get(run.id)
    assert saved.status.value == "completed"
    assert saved.synthesis["contentAdjustments"] == (
        (["步骤清楚"] if kind == "clarify" else [])
        if new_protocol else ["旧格式建议仍可读"]
    )
    if new_protocol:
        assert saved.synthesis["editorFeedbackValidation"]["status"] == "partial"
        assert (
            saved.synthesis["editorFeedback"][0]["target"]["contentHash"]
            == before["targetContentHash"]
        )
        assert saved.synthesis["editorFeedback"][0]["sources"][0]["channel"] == "private_reading"
        if kind == "clarify":
            concern_text = saved.synthesis["editorFeedback"][0]["readerConcerns"][0]["text"]
            assert concern_text == "不知道怎么开始"
    else:
        assert "editorFeedback" not in saved.synthesis
        assert "editorFeedbackValidation" not in saved.synthesis
    assert saved.input_snapshot == before
    assert send(app, "GET", f"/api/topics/{target['id']}").json() == target
    assert any(e["data"].get("synthesis", {}).get("editorFeedback") for e in events) == new_protocol
    replay = collect(app, run.id)
    assert any(e["data"].get("synthesis") == saved.synthesis for e in replay)
    assert calls == [ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_SYNTHESIS]


def test_overlapping_quotes_and_line_breaks_have_explicit_occurrence_semantics():
    repeated = validate(
        [card(target={"field": "body", "quote": "哈哈", "occurrence": 2})],
        topic={**TOPIC, "body": "哈哈哈"},
    )["editorFeedback"][0]["target"]
    assert (repeated["start"], repeated["end"]) == (1, 3)
    multiline = validate([card(target={"field": "body", "quote": "。\n先", "occurrence": 1})])
    assert multiline["editorFeedback"][0]["target"]["quote"] == "。\n先"


def test_catalog_ids_expand_to_existing_saved_contract_without_mutating_inputs():
    topic = {**TOPIC, "body": "🌱\n先试一次。先试一次。"}
    anchor = feedback_anchor_catalog(topic)["items"][-1]
    raw = [card(target={"field": "body", "anchorId": anchor["id"]})]
    before = deepcopy((topic, raw))
    saved = validate(raw, topic=topic)["editorFeedback"][0]["target"]
    assert saved["quote"] == "先试一次。"
    assert (saved["start"], saved["end"], saved["occurrence"]) == (7, 12, 2)
    assert "anchorId" not in saved  # Existing frontend and stored-history shape.
    assert saved["coordinateSystem"] == "unicode_code_points"
    assert (topic, raw) == before


@pytest.mark.parametrize(
    "mode", ["wrong_field", "unknown", "comment_id", "mixed", "occurrence", "stale", "whole"],
)
def test_bad_catalog_id_cannot_be_used_to_guess_or_repair_a_location(mode):
    anchor = feedback_anchor_catalog(TOPIC)["items"][-1]
    target = {"field": "body", "anchorId": anchor["id"]}
    topic = TOPIC
    if mode == "wrong_field":
        target["field"] = "title"
    elif mode == "unknown":
        target["anchorId"] = "body:999:unknown"
    elif mode == "comment_id":
        target["anchorId"] = "initial:a"
    elif mode == "mixed":
        target["quote"] = "先试一次。"
    elif mode == "occurrence":
        target["occurrence"] = 2
    elif mode == "stale":
        topic = {**TOPIC, "body": TOPIC["body"] + "已修改"}
    else:
        target["field"] = "whole"
    result = validate(
        [card(target=target), card(id="unaffected", target={"field": "whole"})], topic=topic,
    )
    assert [c["id"] for c in result["editorFeedback"]] == ["unaffected"]
    assert result["editorFeedbackValidation"]["rejected"] == [
        {"index": 0, "reason": "invalid_anchor"},
    ]


def test_catalog_is_bounded_exact_and_excludes_non_source_data():
    topic = {"title": "标题", "body": "🌱" * 601 + "\n" + "重复句。" * 80,
             "panelTask": {"focusQuestions": ["不是原文"]}, "privateNote": "不要定位"}
    before = deepcopy(topic)
    catalog = feedback_anchor_catalog(topic)
    assert len(catalog["items"]) == 64
    assert catalog["complete"] is False
    assert len({a["id"] for a in catalog["items"]}) == 64
    for a in catalog["items"]:
        assert a["quote"] == topic[a["field"]][a["start"]:a["end"]]
        assert len(a["quote"]) <= 600
    assert topic == before
    assert all(set(a) == {"id", "field", "quote"}
               for a in feedback_anchor_prompt_context(topic)["items"])
    assert feedback_anchor_catalog({"body": " \n", "title": None})["items"] == []
    assert feedback_anchor_catalog({**topic, "previewLevel": "outline"})["items"] == []
    assert feedback_anchor_catalog(TOPIC)["complete"] is True


def test_reader_change_needs_a_recorded_concern_but_keep_and_editor_ideas_do_not():
    reactions = [{**REACTIONS[0], "concerns": ["两种结果都正确时怎么选？"]}]
    concern = reader_concern_catalog(PERSONAS, reactions, [])["items"][0]
    raw = [card(kind="clarify", readerConcernIds=[concern["id"]])]
    before = deepcopy((reactions, raw))
    saved = validate(raw, reactions=reactions)["editorFeedback"][0]
    assert saved["readerConcerns"] == [concern]
    assert saved["sources"][0]["channel"] == "private_reading"
    assert (reactions, raw) == before
    assert not validate(raw)["editorFeedback"]
    result = validate([
        card(id="invented", kind="clarify"),
        card(id="positive"),
        card(id="idea", kind="explore", sourceType="editor_optional",
             sourceMessageIds=[], priority="optional"),
    ])
    assert [c["id"] for c in result["editorFeedback"]] == ["positive", "idea"]
    assert result["editorFeedbackValidation"]["rejected"] == [
        {"index": 0, "reason": "invalid_reader_concern"},
    ]


@pytest.mark.parametrize("mode", ["unknown", "wrong_message", "duplicate", "keep", "optional"])
def test_concern_refs_cannot_be_invented_borrowed_or_added_to_other_card_types(mode):
    reactions = [{**REACTIONS[0], "concerns": ["怎么选择？"]}]
    concern = reader_concern_catalog(PERSONAS, reactions, REPLIES)["items"][0]
    changes = {"kind": "clarify", "readerConcernIds": [concern["id"]]}
    if mode == "unknown":
        changes["readerConcernIds"] = ["concern:unknown"]
    elif mode == "wrong_message":
        changes["sourceMessageIds"] = ["reply:b"]
    elif mode == "duplicate":
        changes["readerConcernIds"] *= 2
    elif mode == "keep":
        changes["kind"] = "keep"
    else:
        changes.update(sourceType="editor_optional", sourceMessageIds=[], priority="optional")
    result = validate([card(**changes)], reactions=reactions)
    assert result["editorFeedbackValidation"]["rejected"][0]["reason"] == "invalid_reader_concern"


def test_catalog_keeps_exact_concerns_and_excludes_unknown_or_duplicate_messages():
    reactions = [{**REACTIONS[0], "concerns": ["  是否可以只选一版？ ", "", None]}]
    replies = [{**REPLIES[0], "newConcerns": ["是否需要公开发布？"]}]
    before = deepcopy((reactions, replies))
    catalog = reader_concern_catalog(PERSONAS, reactions, replies)
    assert [c["text"] for c in catalog["items"]] == [
        "  是否可以只选一版？ ", "是否需要公开发布？",
    ]
    assert catalog["items"][1]["field"] == "newConcerns"
    assert (reactions, replies) == before
    assert reader_concern_catalog([], reactions, replies)["items"] == []
    assert reader_concern_catalog(PERSONAS, reactions * 2, [])["items"] == []
    assert reader_concern_catalog(PERSONAS, [], [{**replies[0], "response": ""}])["items"] == []
    changed = [{**reactions[0], "concerns": ["换一个问题"]}]
    changed_id = reader_concern_catalog(PERSONAS, changed, [])["items"][0]["id"]
    assert changed_id != catalog["items"][0]["id"]


def test_concern_catalog_reports_unrecorded_and_bounded_inputs_without_shortening():
    assert reader_concern_catalog(PERSONAS, REACTIONS, [])["complete"] is False
    empty = [{**REACTIONS[0], "concerns": []}]
    assert reader_concern_catalog(PERSONAS, empty, []) == {
        "version": "reader-concerns/v1", "items": [], "complete": True,
    }
    large = [{**REACTIONS[0], "concerns": ["长" * 1201] + [f"问题{i}" for i in range(65)]}]
    catalog = reader_concern_catalog(PERSONAS, large, [])
    assert len(catalog["items"]) == 64 and catalog["complete"] is False
    assert catalog["items"][0]["text"] == "问题0"


def test_public_reply_concern_remains_an_internal_assessment():
    replies = [{**REPLIES[0], "newConcerns": ["这两个版本都对时选哪一个？"]}]
    concern = reader_concern_catalog(PERSONAS, [], replies)["items"][0]
    saved = validate([card(kind="clarify", sourceMessageIds=["reply:b"],
                           readerConcernIds=[concern["id"]])], replies=replies)["editorFeedback"][0]
    assert saved["readerConcerns"][0]["field"] == "newConcerns"
    assert saved["sources"][0]["channel"] == "public_reply"

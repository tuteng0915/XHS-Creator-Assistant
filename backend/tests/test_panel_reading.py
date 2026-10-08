import asyncio
import json
from copy import deepcopy

import pytest
from test_panel_retest_check import Model, load_check
from test_simulated_fans import seeded as seeded

from app.models import ModelOperation
from app.services.editor_feedback import reader_concern_catalog
from app.services.feedback_anchors import feedback_anchor_catalog
from app.services.model_calls import ModelCallService
from app.services.panel_reading import compact_reader, resolve_reaction_anchor
from app.workflows.audience_simulation import PersonaReactionResult


def reader():
    return {
        "id": "r", "name": "动手派", "profile": "想知道投入是否值得",
        "expressionStyle": "短句询问成本", "userAdjusted": True,
        "evidence": ["费用多少"], "evidenceRefs": [{"quote": "费用多少"}],
        "observedEpisodes": [{
            "noteId": "old", "noteTitle": "历史练习", "noteExcerpt": "旧正文" * 200,
            "observedComment": text, "contextLimit": "触发位置未知",
        } for text in ["费用多少", "练几次", "费用多少"]],
    }


def topic():
    return {"title": "免费练习", "body": "自己练习，无需报名。", "panelTask": {
        "protocolVersion": "panel/v1", "readingMode": "natural", "discussionEnabled": False,
        "focusQuestions": [],
    }}


def test_context_deduplicates_history_and_preserves_authored_traits():
    persona = reader()
    before = deepcopy(persona)
    compact = compact_reader(persona)
    assert compact["expressionStyle"] == persona["expressionStyle"]
    assert len(compact["historicalExamples"]) == 1
    example = compact["historicalExamples"][0]
    assert example["comments"] == ["费用多少", "练几次"]
    assert len(example["noteExcerpt"]) == 400
    assert example["excerptTruncated"]
    assert example["contextLimit"] == "触发位置未知"
    assert "evidence" not in compact and "evidenceRefs" not in compact
    assert "historicalExamples" not in compact_reader(persona, include_history=False)
    assert persona == before


def test_context_limits_distinct_examples_without_inventing_unpaired_history():
    persona = reader()
    persona["observedEpisodes"] = [dict(persona["observedEpisodes"][0], noteId=str(i))
                                   for i in range(5)]
    assert len(compact_reader(persona)["historicalExamples"]) == 2
    del persona["observedEpisodes"]
    assert "historicalExamples" not in compact_reader(persona)


def test_panel_prompt_places_current_text_after_compact_persona(settings):
    service = ModelCallService(settings)
    system, user = service._build_prompt(ModelOperation.SIMULATION_REACTION,
                                        {"persona": reader(), "topic": topic()})
    data = json.loads(user)
    assert list(data) == ["persona", "topic", "textAnchors"]
    assert data["topic"] == topic()
    assert "satisfiedNeeds" in system and "triggerAnchorId" in system
    assert "同一人物" in system and "不再把预约当作缺失信息" in system
    for operation in (ModelOperation.SIMULATION_DEBATE, ModelOperation.SIMULATION_SYNTHESIS):
        _, user = service._build_prompt(operation, {
            "persona": reader(), "personas": [reader()], "topic": topic(),
        })
        assert "旧正文" not in user and "evidenceRefs" not in user
        assert "想知道投入是否值得" in user


def test_anchor_selection_resolves_exact_text_without_mutation():
    target = topic()
    anchor = feedback_anchor_catalog(target)["items"][1]
    output = {"reaction": {"personaId": "r", "stance": "喜欢",
                           "triggerAnchorId": anchor["id"], "satisfiedNeeds": ["无需报名"]}}
    before = deepcopy(output)
    result = PersonaReactionResult.model_validate(resolve_reaction_anchor(output, target))
    assert result.reaction.triggerQuote == target["body"]
    assert result.reaction.satisfiedNeeds == ["无需报名"]
    assert output == before


@pytest.mark.parametrize("anchor_id", ["wrong", "body:0:old-fingerprint", [], ""])
def test_invalid_anchor_rejected(anchor_id):
    with pytest.raises(ValueError, match="编号不属于"):
        resolve_reaction_anchor({"reaction": {"triggerAnchorId": anchor_id}}, topic())


def test_anchor_conflict_rejected_and_legacy_untouched():
    target = topic()
    anchor = feedback_anchor_catalog(target)["items"][0]
    with pytest.raises(ValueError, match="冲突"):
        resolve_reaction_anchor({"reaction": {
            "triggerAnchorId": anchor["id"], "triggerQuote": "改写的引文",
        }}, target)
    legacy = {"reaction": {"personaId": "r", "stance": "喜欢", "triggerQuote": "免费练习"}}
    assert resolve_reaction_anchor(legacy, target) is legacy
    assert PersonaReactionResult.model_validate(legacy).reaction.satisfiedNeeds == []


def test_satisfied_needs_do_not_become_editor_concerns():
    reactions = [{"personaId": "r", "messageId": "initial:r", "stance": "喜欢",
                  "understanding": "条件清楚", "satisfiedNeeds": ["免费"],
                  "concerns": ["不清楚每周练几次"]}]
    catalog = reader_concern_catalog([{"id": "r"}], reactions, [])
    assert [item["text"] for item in catalog["items"]] == ["不清楚每周练几次"]


def test_anchored_reactions_and_satisfied_needs_survive_workflow(app, seeded, settings):
    class AnchoredModel(Model):
        async def call_operation(self, operation, context):
            response = await super().call_operation(operation, context)
            if operation == ModelOperation.SIMULATION_REACTION:
                response.output["reaction"].update(
                    triggerAnchorId=feedback_anchor_catalog(context["topic"])["items"][0]["id"],
                    satisfiedNeeds=["单次耗时清楚"],
                )
            return response

    module = load_check()
    wid, _, _, fans = seeded
    report = asyncio.run(module.check(app.state.database.path, wid,
                                     [f["id"] for f in fans[:2]], settings, AnchoredModel()))
    assert report["status"] == "completed"
    for run in report["runs"]:
        for reaction in run["reactionResults"]:
            assert reaction["satisfiedNeeds"] == ["单次耗时清楚"]
            assert reaction["triggerQuote"] == module.TITLE
    assert report["sourceDatabaseUnchanged"]

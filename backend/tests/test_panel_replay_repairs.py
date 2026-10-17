"""Local-only repairs: preserve evidence and concrete advice, not generated facts."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_audience_evidence import context, ref
from test_editor_feedback import card, validate
from test_panel_quality import edit_decisions, editing

from app.services.audience_analyses import validate_audience_output
from app.services.audience_evidence import canonical_comment_parents, evidence_issues
from app.services.editor_feedback import reader_concern_catalog, validate_editor_feedback
from app.services.panel_quality import PanelReview, apply_review, prepare_review


def test_unique_comment_id_restores_parent_and_keeps_persona_without_mutating_receipt():
    data = context()
    output = {"summary": "候选读者", "limitations": "仅为假设", "groups": [{
        "id": "g", "name": "费用比较者", "profile": "想比较申请成本",
        "evidenceRefs": [ref(noteId="c").model_dump(by_alias=True)],
    }]}
    before = deepcopy((output, data))
    result, diagnostics = validate_audience_output(output, data)
    assert len(result["groups"]) == 1
    assert result["groups"][0]["evidenceRefs"][0]["noteId"] == "n"
    assert result["groups"][0]["observedEpisodes"][0]["commentId"] == "c"
    assert diagnostics["referenceRepairs"][0]["original"]["noteId"] == "c"
    assert diagnostics["referenceRepairs"][0]["resolved"]["noteId"] == "n"
    assert (output, data) == before


@pytest.mark.parametrize("failure", [
    "duplicate_comment", "duplicate_note", "author", "excluded_author", "wrong_quote",
    "missing_comment", "conflicting_parent", "note_reference",
])
def test_parent_recovery_never_guesses_or_bypasses_author_exclusion(failure):
    data = context()
    reference = ref(noteId="c")
    if failure == "duplicate_comment":
        data["notes"][0]["comments"].append({"commentId": "c", "content": "别的内容"})
    elif failure == "duplicate_note":
        data["notes"].append({**data["notes"][0], "comments": []})
    elif failure == "author":
        data["notes"][0]["comments"][0]["sourceRole"] = "author"
    elif failure == "excluded_author":
        data["notes"][0]["excludedAuthorCommentIds"] = ["c"]
    elif failure == "wrong_quote":
        reference = ref(noteId="c", quote="编造的话")
    elif failure == "missing_comment":
        reference = ref(noteId="c", commentId="missing")
    elif failure == "conflicting_parent":
        data["notes"].append({"noteId": "c", "title": "别篇", "content": "", "comments": []})
    else:
        reference = ref(noteId="c", sourceType="note")
    refs, repairs = canonical_comment_parents([reference], data)
    assert refs == [reference] and repairs == []
    assert evidence_issues(refs, data)


def test_already_valid_comment_reference_stays_exact():
    refs = [ref()]
    resolved, repairs = canonical_comment_parents(refs, context())
    assert resolved == refs and repairs == []
    assert evidence_issues(resolved, context()) == []


@pytest.mark.parametrize("kind", ["clarify", "rewrite", "explore"])
def test_question_only_kind_mismatch_is_losslessly_normalized(kind):
    raw = [card(kind=kind, sourceType="editor_optional", sourceMessageIds=[],
                priority="optional", suggestedText="", materialRequests=["哪一步先比较？"])]
    before = deepcopy(raw)
    result = validate(raw)
    saved = result["editorFeedback"][0]
    assert saved["kind"] == "add_material"
    assert saved["observation"] == raw[0]["observation"]
    assert saved["materialRequests"] == raw[0]["materialRequests"]
    assert result["editorFeedbackValidation"]["normalized"] == [
        {"id": "f1", "from": kind, "to": "add_material"}]
    assert raw == before


@pytest.mark.parametrize("change", [
    {"sourceMessageIds": ["initial:missing"]},
    {"target": {"field": "body", "quote": "并不存在的原文"}},
])
def test_kind_correction_cannot_rescue_invalid_source_or_anchor(change):
    result = validate([card(kind="clarify", materialRequests=["先比较哪一步？"], **change)])
    assert result["editorFeedback"] == []
    assert "normalized" not in result["editorFeedbackValidation"]


def test_questions_and_optional_ideas_do_not_trigger_copy_fact_checker():
    context, output = editing()
    for row in output["synthesis"]["editorFeedback"]:
        row.update(suggestedText="", materialRequests=["查完两条路后怎么比较？"])
    assert prepare_review("simulation_synthesis", context, output) is None
    output["synthesis"]["editorFeedback"][0].update(kind="explore", materialRequests=[])
    assert prepare_review("simulation_synthesis", context, output) is None


def test_mixed_feedback_checks_only_replacement_text():
    context, output = editing()
    question = {**output["synthesis"]["editorFeedback"][0], "id": "question",
                "suggestedText": "", "materialRequests": ["查完后先比较什么？"]}
    output["synthesis"]["editorFeedback"].append(question)
    plan = prepare_review("simulation_synthesis", context, output)
    assert plan.ids == ["new_fact", "wording"]
    assert [e["id"] for e in plan.context["edits"]] == plan.ids
    result, _ = apply_review(plan, output, edit_decisions())
    assert result["synthesis"]["editorFeedback"][-1] == question


def test_old_omit_decision_cannot_delete_question_only_feedback():
    context, output = editing()
    row = output["synthesis"]["editorFeedback"][0]
    row.update(suggestedText="", materialRequests=["查完两条路后怎么比较？"])
    output["synthesis"]["editorFeedback"] = [row]
    # Replay an old checker packet, not an invented verdict for a new plan.
    plan = PanelReview("edit_facts", "saved", {}, [row["id"]])
    result, _ = apply_review(plan, output, {"decisions": [{
        "id": row["id"], "decision": "omit", "reason": "改变范围", "questions": [],
    }]})
    assert result["synthesis"]["editorFeedback"] == [row]


def test_material_conversion_keeps_specific_observation_and_recorded_reader_problem():
    context, output = editing()
    context["reactions"][0]["concerns"] = ["怎么把这次小改进写进简历或面试里讲？"]
    concern = reader_concern_catalog(context["personas"], context["reactions"], [])["items"][0]
    row = output["synthesis"]["editorFeedback"][0]
    row.update(sourceType="reader", sourceMessageIds=["initial:p"],
               readerConcernIds=[concern["id"]],
               observation="缺少把小改进转成简历讲法的具体示范")
    before = deepcopy((context, output))
    plan = prepare_review("simulation_synthesis", context, output)
    result, _ = apply_review(plan, output, edit_decisions())
    saved = result["synthesis"]["editorFeedback"][0]
    assert saved["observation"] == row["observation"]
    assert saved["suggestedText"] == ""
    assert concern["text"] in saved["materialRequests"][0]
    assert "五次" not in saved["materialRequests"][0]
    checked = validate_editor_feedback(result["synthesis"]["editorFeedback"],
        topic=context["topic"], personas=context["personas"],
        reactions=context["reactions"], replies=[])
    assert checked["editorFeedbackValidation"]["status"] == "validated"
    assert (context, output) == before
    assert "readerConcerns" not in str(plan.prompt)  # local provenance, not more prompt


def replay_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "replay_audience_panel.py"
    spec = importlib.util.spec_from_file_location("offline_panel_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_reuses_original_review_packet_and_never_calls_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("offline replay must not open a network connection")

    monkeypatch.setattr(socket, "socket", forbidden)
    context_data, output = editing()
    audience = {"summary": "候选", "limitations": "假设", "groups": [{
        "id": "g", "name": "费用比较者", "profile": "想比较成本",
        "evidenceRefs": [ref(noteId="c").model_dump(by_alias=True)],
    }]}
    plan = prepare_review("simulation_synthesis", context_data, output)
    report = {
        "accounts": [{"account": "甲", "audienceContext": context(),
                      "analysis": {"result": {"groups": []}},
                      "simulation": {"synthesis": {"editorFeedback": []}}}],
        "calls": [{"account": "甲", "index": 2, "operation": "simulation_synthesis",
                   "status": "completed", "context": context_data}],
        "requests": [
            {"account": "甲", "callIndex": 1, "operation": "audience_analysis",
             "rawContent": json.dumps(audience)},
            {"account": "甲", "callIndex": 2, "operation": "simulation_synthesis",
             "rawContent": json.dumps(output)},
            {"account": "甲", "callIndex": 2, "operation": "simulation_synthesis",
             "rawContent": json.dumps(edit_decisions()),
             "packet": {"messages": [{"content": plan.system},
                                     {"content": json.dumps(plan.context)}]}},
        ],
    }
    before = deepcopy(report)
    result = replay_module().replay(report)
    assert result["modelRequests"] == 0 and result["sourceUnchanged"]
    assert result["accounts"][0]["audience"]["afterAccepted"] == 1
    assert len(result["accounts"][0]["feedback"]["after"]) == 2
    assert report == before

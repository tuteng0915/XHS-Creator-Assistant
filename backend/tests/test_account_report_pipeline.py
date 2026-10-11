import asyncio
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.models import ModelCallResponse
from app.services.account_diagnosis_evidence import verified_portrait
from app.services.account_report_passages import reading_fragments
from app.services.account_report_pipeline import (
    PIPELINE_VERSION,
    TEXT_SCOPE,
    run_staged_account_report,
)
from app.services.account_report_sources import build_report_sources
from app.workflows.account_diagnosis import ProfileStageResult


def source_notes():
    return [
        {"noteId": "stable-a", "title": "甲篇：先确认条件",
         "body": "甲篇开头。先核对费用。甲篇结尾。",
         "metrics": {"liked": 123456}, "comments": [{"content": "不应进入精读"}]},
        {"noteId": "stable-b", "title": "乙篇：承认尚未展开",
         "body": "乙篇开头。这里只是一个预告。乙篇结尾。",
         "metrics": {"liked": 987654}},
        {"noteId": "stable-c", "title": "丙篇：另一种题材",
         "body": "丙篇独有的正文不应进入其他精读。"},
    ]


def context_for(notes=None):
    return {
        "positioning": "作者提供的账号定位",
        "historicalPosts": json.dumps({
            "schemaVersion": "account-reading-input/v2",
            "notes": source_notes() if notes is None else notes,
            "metrics": {"liked": "packet-private"},
        }, ensure_ascii=False),
        "accountObservations": {"metrics": "context-private"},
    }


def overview_for(ids=("n1", "n2")):
    return {
        "summary": claim("初步猜想：每篇都给出了完整行动路径。"),
        "directions": [claim("在具体问题里确认条件")],
        "hypotheses": ["先确认约束再给出行动路径"],
        "readings": [{"noteId": note_id, "question": f"这篇是否真的给出了完整路径？{note_id}"}
                     for note_id in ids],
    }


def reading_for(note_id):
    if note_id == "n1":
        return {
            "assessment": "甲篇通过核对条件提供行动参照。", "correction": "",
            "examples": [{"excerptIds": ["b2"],
                          "interpretation": "以明确动作说明准备工作。"}],
        }
    return {
        "assessment": "乙篇只提出后续要谈的问题，正文尚未展开。",
        "correction": "这篇是预告，不能据此认定已经给出完整行动路径。",
        "examples": [{"excerptIds": ["b2"],
                      "interpretation": "明确标注预告边界，避免把设问当成结论。"}],
    }


def claim(text, ids=("n1",)):
    return {"text": text, "noteIds": list(ids)}


def synthesis_for(*, examples=True):
    return {
        "summary": claim("关注具体问题的判断过程；既有行动经验，也有待展开的设问。", ("n1", "n2")),
        "keywords": [claim("具体判断")],
        "directions": [claim("从条件和问题切入经验分享。", ("n1", "n2"))],
        "strengths": [{"text": "把判断落到能观察的细节。", "exampleIds": ["e1"]}]
        if examples else [],
        "writing": [{"text": "交代文字的用途和边界。", "exampleIds": ["e2"]}]
        if examples else [],
        "nextSteps": [claim("下一篇可展开一个具体问题，先列条件，再让读者比较选项。")],
    }


class FakeCalls:
    def __init__(self, *, notes=None, ids=("n1", "n2"), overview=None,
                 readings=None, synthesis=None):
        self.notes = source_notes() if notes is None else notes
        self.overview = overview_for(ids) if overview is None else overview
        self.readings = {note_id: reading_for(note_id) for note_id in ids}
        if readings is not None:
            self.readings.update(readings)
        self.synthesis = synthesis_for() if synthesis is None else synthesis
        self.calls = []

    async def __call__(self, stage, system, user):
        payload = json.loads(user)
        self.calls.append((stage, system, payload))
        if stage == "overview":
            output = self.overview
        elif stage == "read":
            note_id = next(f"n{index}" for index, note in enumerate(self.notes, 1)
                           if note["title"] == payload["note"]["title"])
            output = self.readings[note_id]
        else:
            assert stage == "synthesis"
            output = self.synthesis
        return ModelCallResponse(output=deepcopy(output), model_metadata={"model": "fake"})


def snapshot_for(notes):
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": note["noteId"], "title": note["title"], "desc": note["body"]}
        for note in notes
    ]}}


def test_all_stage_prompts_share_the_saved_text_and_missing_material_scope():
    model = FakeCalls()
    asyncio.run(run_staged_account_report(context_for(), model))
    assert all(system.startswith(TEXT_SCOPE) for _, system, _ in model.calls)
    for limitation in ("已保存的标题和文字正文", "未读取图片内文字或视频", "不保证材料包含全文",
                       "未提供论证不等于原作没有论证", "不能据此断言是预告"):
        assert limitation in TEXT_SCOPE


@pytest.mark.parametrize("body", [
    "", "   \r\n\t", "  首句。\r\n下一句！\nemoji🙂保留。尾部  ",
    "长" * 321, "重复。中间。重复。", "English one. English two?\n尾句",
])
def test_reading_fragment_catalog_is_reversible_positioned_and_preserves_full_title(body):
    title = "完整标题" * 50
    fragments = reading_fragments(title, body)
    assert fragments["t"] == {"excerptId": "t", "source": "title", "quote": title,
                               "start": 0, "end": len(title)}
    body_fragments = [fragment for fragment in fragments.values() if fragment["source"] == "body"]
    assert "".join(fragment["quote"] for fragment in body_fragments) == body
    offset = 0
    for index, fragment in enumerate(body_fragments, 1):
        assert fragment["excerptId"] == f"b{index}"
        assert fragment["start"] == offset
        assert fragment["end"] == offset + len(fragment["quote"])
        assert body[fragment["start"]:fragment["end"]] == fragment["quote"]
        assert len(fragment["quote"]) <= 160
        offset = fragment["end"]
    assert offset == len(body)


def test_only_selected_readings_build_local_catalogs_after_overview(monkeypatch):
    from app.services import account_report_pipeline

    model = FakeCalls()
    events = []
    selected_titles = [note["title"] for note in source_notes()[:2]]

    def fragments(title, body):
        assert events and events[0] == "overview"
        assert title in selected_titles
        events.append(("catalog", title))
        return reading_fragments(title, body)

    async def call(stage, system, user):
        events.append(stage)
        if stage == "overview":
            assert events == ["overview"]
        return await model(stage, system, user)

    monkeypatch.setattr(account_report_pipeline, "reading_fragments", fragments)
    asyncio.run(run_staged_account_report(context_for(), call))
    assert {event[1] for event in events if isinstance(event, tuple)} == set(selected_titles)


def test_overview_parallel_isolated_readings_synthesis_and_program_bound_examples():
    async def scenario():
        notes = source_notes()
        notes[0]["body"] += "保留完整原文" * 1500
        context = context_for(notes)
        before = deepcopy(context)
        model = FakeCalls(notes=notes, ids=("n2", "n1"))
        calls, entered, finished, updates = [], set(), [], []
        both_started, first_reported = asyncio.Event(), asyncio.Event()

        async def progress(update):
            updates.append(deepcopy(update))
            if update["phase"] == "reading" and update["completed"] == 1:
                first_reported.set()

        async def call(stage, system, user):
            payload = json.loads(user)
            calls.append((stage, payload))
            assert "json" in system.lower()
            if stage == "read":
                title = payload["note"]["title"]
                entered.add(title)
                if len(entered) == 2:
                    both_started.set()
                await both_started.wait()
                if title == notes[1]["title"]:
                    await first_reported.wait()
                finished.append(title)
            if stage == "synthesis":
                assert finished == [notes[0]["title"], notes[1]["title"]]
            return await model(stage, system, user)

        result = await asyncio.wait_for(
            run_staged_account_report(context, call, on_update=progress), timeout=2,
        )
        assert context == before
        assert [stage for stage, _ in calls] == ["overview", "read", "read", "synthesis"]
        overview_payload = calls[0][1]
        assert overview_payload == {"account": context["positioning"], "notes": [
            {"noteId": f"n{index}", "title": note["title"], "body": note["body"]}
            for index, note in enumerate(notes, 1)
        ]}
        for _, payload in calls[1:3]:
            source = next(note for note in notes if note["title"] == payload["note"]["title"])
            assert set(payload) == {"question", "note"}
            catalog = build_report_sources(snapshot_for([source]))[source["noteId"]]
            assert payload["note"] == {
                "title": source["title"], "bodyExcerpts": [
                    {"excerptId": key, "text": text}
                    for key, text in catalog.items() if key != "t"
                ],
            }
            assert "".join(item["text"] for item in payload["note"]["bodyExcerpts"]) \
                == source["body"]
            assert "body" not in payload["note"]
            serialized = json.dumps(payload, ensure_ascii=False)
            assert model.overview["summary"]["text"] not in serialized
            assert context["positioning"] not in serialized
            for other in notes:
                if other is not source:
                    assert other["title"] not in serialized
                    assert other["body"] not in serialized
        synthesis_payload = calls[-1][1]
        assert set(synthesis_payload) == {"initialView", "notes", "readings"}
        assert "readings" not in synthesis_payload["initialView"]
        assert synthesis_payload["initialView"] == {
            key: model.overview[key] for key in ("summary", "directions", "hypotheses")
        }
        assert [item["noteId"] for item in synthesis_payload["readings"]] == ["n2", "n1"]
        assert [item["question"] for item in synthesis_payload["readings"]] \
            == [item["question"] for item in model.overview["readings"]]
        assert [item["examples"] for item in synthesis_payload["readings"]] == [
            [{"id": "e1", "observation": reading_for("n2")["examples"][0]["interpretation"]}],
            [{"id": "e2", "observation": reading_for("n1")["examples"][0]["interpretation"]}],
        ]
        assert synthesis_payload["readings"][0]["correction"] == reading_for("n2")["correction"]
        serialized = json.dumps(synthesis_payload, ensure_ascii=False)
        for note in notes:
            assert note["body"] not in serialized
        for quote in ("先核对费用。", "这里只是一个预告。"):
            assert quote not in serialized
        for _, payload in calls:
            serialized = json.dumps(payload, ensure_ascii=False)
            for private in ("metrics", "comments", "123456", "987654", "stable-a",
                            "packet-private", "context-private"):
                assert private not in serialized

        portrait = result.output["profile"]["accountPortrait"]
        assert portrait["strengths"] == [{
            "statement": "把判断落到能观察的细节。",
            "evidence": [{"noteId": "stable-b", "scope": "note"}],
            "examples": [{"noteId": "stable-b", "title": notes[1]["title"],
                          "fragments": [{"excerptId": "b2", "source": "body",
                                         "quote": "这里只是一个预告。", "start": 5, "end": 14}],
                          "interpretation": "明确标注预告边界，避免把设问当成结论。"}],
        }]
        assert portrait["expressionPatterns"][0]["evidence"] == [
            {"noteId": "stable-a", "scope": "note"},
        ]
        assert portrait["summary"]["statement"] == model.synthesis["summary"]["text"]
        assert portrait["summary"]["evidence"] == [
            {"noteId": "stable-a", "scope": "note"},
            {"noteId": "stable-b", "scope": "note"},
        ]
        metadata = result.model_metadata
        assert metadata["accountReportMode"] == "staged"
        assert metadata["promptVersion"] == PIPELINE_VERSION
        assert metadata["representativeNoteIds"] == ["stable-b", "stable-a"]
        assert [item["noteId"] for item in metadata["calls"] if item["stage"] == "read"] \
            == ["stable-b", "stable-a"]
        assert [item["id"] for item in metadata["boundExamples"]] == ["e1", "e2"]
        for bound in metadata["boundExamples"]:
            note = next(note for note in notes if note["noteId"] == bound["stableId"])
            assert bound["title"] == note["title"]
            for fragment in bound["fragments"]:
                assert note[fragment["source"]][fragment["start"]:fragment["end"]] \
                    == fragment["quote"]
        assert all("examples" not in item for item in metadata["readingAssessments"])
        assert [(item["phase"], item["status"], item["completed"], item["total"])
                for item in updates] == [
            ("overview", "running", 0, 1), ("overview", "completed", 1, 1),
            ("reading", "running", 0, 2), ("reading", "running", 1, 2),
            ("reading", "completed", 2, 2), ("synthesis", "running", 0, 1),
            ("synthesis", "completed", 1, 1),
        ]
        assert updates[1]["preview"] == model.overview["summary"]["text"]
        assert updates[3]["preview"] \
            == f"《{notes[0]['title']}》：{reading_for('n1')['assessment']}"
        assert updates[4]["preview"].splitlines() == [
            f"《{notes[1]['title']}》：{reading_for('n2')['assessment']}",
            f"《{notes[0]['title']}》：{reading_for('n1')['assessment']}",
        ]
        parsed = ProfileStageResult.model_validate(result.output).profile.accountPortrait
        assert parsed == portrait
        verified = verified_portrait(parsed, snapshot_for(notes))
        for key, value in portrait.items():
            if isinstance(value, list):
                assert [item["statement"] for item in verified[key]] \
                    == [item["statement"] for item in value]
        assert verified["summary"]["statement"] == portrait["summary"]["statement"]
        for section in ("strengths", "expressionPatterns"):
            assert verified[section][0]["examples"] == portrait[section][0]["examples"]

    asyncio.run(scenario())


def test_input_and_forced_selection_are_frozen_before_callbacks_can_change_them():
    context = context_for()
    original_notes = json.loads(context["historicalPosts"])["notes"]
    forced = ["n1", "n2"]
    model = FakeCalls()

    async def progress(update):
        if update["phase"] == "overview" and update["status"] == "running":
            context["historicalPosts"] = context_for([])["historicalPosts"]
            context["positioning"] = "中途替换定位"
            forced[:] = ["n3"]

    result = asyncio.run(run_staged_account_report(
        context, model, on_update=progress, representative_note_ids=forced,
    ))
    payload = model.calls[0][2]
    assert payload["account"] == "作者提供的账号定位"
    assert payload["representativeNoteIds"] == ["n1", "n2"]
    assert [note["body"] for note in payload["notes"]] \
        == [note["body"] for note in original_notes]
    assert result.model_metadata["representativeNoteIds"] == ["stable-a", "stable-b"]


def test_slow_progress_store_cannot_overwrite_newer_reading_counts_or_previews():
    async def scenario():
        model = FakeCalls()
        first_store_started, release_first_store = asyncio.Event(), asyncio.Event()
        second_model_returned = asyncio.Event()
        published, callback_counts, model_returns = [], [], []

        async def progress(update):
            if update["phase"] != "reading":
                return
            callback_counts.append(update["completed"])
            if update["completed"] == 1:
                first_store_started.set()
                await release_first_store.wait()
            published.append(deepcopy(update))

        async def call(stage, system, user):
            if stage == "read":
                is_second = json.loads(user)["note"]["title"] == source_notes()[1]["title"]
                if is_second:
                    await first_store_started.wait()
                response = await model(stage, system, user)
                model_returns.append("n2" if is_second else "n1")
                if is_second:
                    second_model_returned.set()
                return response
            if stage == "synthesis":
                assert [update["completed"] for update in published] == [0, 1, 2]
            return await model(stage, system, user)

        task = asyncio.create_task(run_staged_account_report(
            context_for(), call, on_update=progress,
        ))
        try:
            await asyncio.wait_for(second_model_returned.wait(), timeout=2)
            # The second model has returned while the first publication is blocked.
            # Its progress must wait; model requests themselves must not wait.
            before_release = deepcopy(published)
            callbacks_before_release = list(callback_counts)
        finally:
            release_first_store.set()
        result = await asyncio.wait_for(task, timeout=2)
        assert model_returns == ["n1", "n2"]
        assert [update["completed"] for update in before_release] == [0]
        assert callbacks_before_release == [0, 1]
        assert [update["completed"] for update in published] == [0, 1, 2]
        assert published[-1]["status"] == "completed"
        assert published[-1]["preview"].splitlines() == [
            f"《{source_notes()[0]['title']}》：{reading_for('n1')['assessment']}",
            f"《{source_notes()[1]['title']}》：{reading_for('n2')['assessment']}",
        ]
        assert len(result.model_metadata["calls"]) == 4

    asyncio.run(scenario())


@pytest.mark.parametrize("ids", [("n1", "n1"), ("n1", "n404"), ("stable-a",), (),
                                ("n1", "n2", "n3", "n4")])
def test_invalid_overview_selection_stops_before_readings(ids):
    model = FakeCalls(ids=ids)
    with pytest.raises((ValueError, PydanticValidationError)):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.calls] == ["overview"]


@pytest.mark.parametrize("section", ["summary", "directions"])
@pytest.mark.parametrize("note_ids", [["n404"], ["stable-a"], []])
def test_overview_claims_require_known_local_source_ids_before_any_reading(section, note_ids):
    overview = overview_for()
    target = overview[section] if section == "summary" else overview[section][0]
    target["noteIds"] = note_ids
    model = FakeCalls(overview=overview)
    with pytest.raises((ValueError, PydanticValidationError)):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.calls] == ["overview"]


@pytest.mark.parametrize("section", ["summary", "directions"])
def test_overview_does_not_accept_unattributed_legacy_plain_text_claims(section):
    overview = overview_for()
    overview[section] = "没有来源的总结" if section == "summary" else ["没有来源的方向"]
    model = FakeCalls(overview=overview)
    with pytest.raises(PydanticValidationError):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.calls] == ["overview"]


def test_overview_claim_attribution_reaches_synthesis_without_losing_unread_note_refs():
    overview = overview_for()
    overview["summary"] = claim("乙篇提出后续问题，丙篇提供不同题材。", ("n2", "n3"))
    overview["directions"] = [claim("后续问题的预告。", ("n2",)),
                              claim("另一种题材的观察。", ("n3",))]
    model = FakeCalls(overview=overview)
    before = deepcopy(overview)
    asyncio.run(run_staged_account_report(context_for(), model))
    initial = model.calls[-1][2]["initialView"]
    assert initial["summary"] == before["summary"]
    assert initial["directions"] == before["directions"]
    assert [item["noteIds"] for item in initial["directions"]] == [["n2"], ["n3"]]
    assert model.overview == before


def test_synthesis_receives_the_exact_question_a_reader_correction_answers():
    overview = overview_for()
    overview["hypotheses"] = ["先确认约束再给出行动路径", "每篇都用类比解释经验"]
    overview["readings"][1]["question"] = "这篇是否真的用类比解释经验？"
    reading = reading_for("n2")
    reading["correction"] = "这个判断不成立。"
    model = FakeCalls(overview=overview, readings={"n2": reading})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    conclusion = model.calls[-1][2]["readings"][1]
    assert conclusion["noteId"] == "n2"
    assert conclusion["question"] == overview["readings"][1]["question"]
    assert conclusion["correction"] == "这个判断不成立。"
    assert result.model_metadata["readingAssessments"][1]["question"] \
        == overview["readings"][1]["question"]


@pytest.mark.parametrize("note_count", [2, 3])
def test_unforced_multiple_note_input_requires_at_least_two_representatives(note_count):
    notes = source_notes()[:note_count]
    model = FakeCalls(notes=notes, ids=("n1",))
    with pytest.raises(ValueError, match="代表作|至少|精读"):
        asyncio.run(run_staged_account_report(context_for(notes), model))
    assert [stage for stage, _, _ in model.calls] == ["overview"]


def test_explicit_evaluation_can_still_read_one_representative_from_multiple_notes():
    synthesis = synthesis_for()
    synthesis["writing"] = []
    model = FakeCalls(ids=("n1",), synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(
        context_for(), model, representative_note_ids=["n1"],
    ))
    assert [stage for stage, _, _ in model.calls] == ["overview", "read", "synthesis"]
    assert result.model_metadata["representativeNoteIds"] == ["stable-a"]


@pytest.mark.parametrize("forced", [[], ["n1", "n1"], ["stable-a"], ["n4"],
                                    ["n1", "n2", "n3", "n4"]])
def test_invalid_fixed_selection_fails_before_any_model_call(forced):
    model = FakeCalls()
    with pytest.raises(ValueError, match="固定精读范围"):
        asyncio.run(run_staged_account_report(
            context_for(), model, representative_note_ids=forced,
        ))
    assert model.calls == []


def test_fixed_evaluation_rejects_swapped_representatives_but_accepts_reordering():
    model = FakeCalls(ids=("n2", "n3"))
    with pytest.raises(ValueError, match="不能用换作品代替验收"):
        asyncio.run(run_staged_account_report(
            context_for(), model, representative_note_ids=["n1", "n2"],
        ))
    assert len(model.calls) == 1
    model = FakeCalls(ids=("n2", "n1"))
    result = asyncio.run(run_staged_account_report(
        context_for(), model, representative_note_ids=["n1", "n2"],
    ))
    assert result.model_metadata["representativeNoteIds"] == ["stable-b", "stable-a"]


@pytest.mark.parametrize("excerpt_ids", [
    ["b404"], ["n2:b2"], ["stable-b:b2"], [], ["b1", "b2", "b3", "t"],
    ["b2", "b2"], ["b3", "b2"], ["b2", "t"], [1],
])
def test_invalid_excerpt_id_selections_are_rejected(excerpt_ids):
    reading = reading_for("n1")
    reading["examples"][0]["excerptIds"] = excerpt_ids
    model = FakeCalls(readings={"n1": reading})
    with pytest.raises((ValueError, PydanticValidationError)):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert "synthesis" not in [stage for stage, _, _ in model.calls]


def test_an_excerpt_id_present_only_in_another_note_cannot_be_selected():
    notes = source_notes()
    notes[1]["body"] += "另一篇第四句。"
    assert "b4" in build_report_sources(snapshot_for(notes))["stable-b"]
    reading = reading_for("n1")
    reading["examples"][0]["excerptIds"] = ["b4"]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    with pytest.raises(ValueError):
        asyncio.run(run_staged_account_report(context_for(notes), model))
    assert "synthesis" not in [stage for stage, _, _ in model.calls]


@pytest.mark.parametrize("excerpt_id", ["t", "b1"])
def test_blank_only_title_or_body_excerpt_is_not_usable_evidence(excerpt_id):
    notes = source_notes()
    notes[0].update(title="   ", body="   \n实际正文。")
    reading = reading_for("n1")
    reading["examples"][0]["excerptIds"] = [excerpt_id]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    with pytest.raises(ValueError):
        asyncio.run(run_staged_account_report(context_for(notes), model))
    assert "synthesis" not in [stage for stage, _, _ in model.calls]


@pytest.mark.parametrize("mixed", [False, True])
def test_new_reader_contract_rejects_legacy_or_mixed_free_quote_output(mixed):
    reading = reading_for("n1")
    old = {"source": "body", "quote": "先核对费用。", "interpretation": "以动作说明准备。"}
    if mixed:
        old["excerptIds"] = ["b2"]
    reading["examples"] = [old]
    model = FakeCalls(readings={"n1": reading})
    with pytest.raises(PydanticValidationError):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert "synthesis" not in [stage for stage, _, _ in model.calls]


@pytest.mark.parametrize("different_interpretation", [False, True])
def test_one_source_location_can_support_multiple_reading_groups(different_interpretation):
    reading = reading_for("n1")
    duplicate = deepcopy(reading["examples"][0])
    if different_interpretation:
        duplicate["interpretation"] = "同一句也能从表达节奏的角度解释。"
    reading["examples"].append(duplicate)
    synthesis = synthesis_for()
    synthesis["strengths"][0]["exampleIds"] = ["e1", "e2"]
    synthesis["writing"] = []
    model = FakeCalls(readings={"n1": reading}, synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    bound = result.model_metadata["boundExamples"][:2]
    assert [example["id"] for example in bound] == ["e1", "e2"]
    assert bound[0]["fragments"] == bound[1]["fragments"]
    assert [example["interpretation"] for example in bound] \
        == [example["interpretation"] for example in reading["examples"]]
    portrait = result.output["profile"]["accountPortrait"]
    verified = verified_portrait(portrait, snapshot_for(source_notes()))
    assert len(verified["strengths"][0]["examples"]) == 2
    assert verified["strengths"][0]["examples"] == portrait["strengths"][0]["examples"]


def test_identical_text_at_distinct_title_and_body_locations_remains_separate_examples():
    notes = source_notes()
    notes[0]["title"] = "先核对费用。"
    reading = reading_for("n1")
    reading["examples"].append({"excerptIds": ["t"],
                                "interpretation": "原标题直接点明准备动作。"})
    model = FakeCalls(notes=notes, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    examples = result.model_metadata["boundExamples"][:2]
    assert [example["id"] for example in examples] == ["e1", "e2"]
    assert [example["fragments"][0]["source"] for example in examples] == ["body", "title"]
    assert [example["fragments"][0]["start"] for example in examples] == [5, 0]


def test_title_example_preserves_exact_whitespace_source_offsets_and_true_identity():
    notes = source_notes()
    notes[0]["title"] = "  这是标题  "
    reading = reading_for("n1")
    reading["examples"][0]["excerptIds"] = ["t"]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    bound = result.model_metadata["boundExamples"][0]
    assert bound["fragments"] == [{"excerptId": "t", "source": "title", "start": 0,
                                    "end": 8, "quote": "  这是标题  "}]
    assert bound["title"] == notes[0]["title"]
    assert bound["stableId"] == "stable-a"
    finding = result.output["profile"]["accountPortrait"]["strengths"][0]
    assert finding["examples"][0]["fragments"][0]["quote"] == "  这是标题  "
    verified = verified_portrait(result.output["profile"]["accountPortrait"], snapshot_for(notes))
    assert verified["strengths"][0]["examples"] == finding["examples"]


def test_noncontiguous_fragments_keep_one_shared_interpretation_without_fabricated_joined_quote():
    notes = source_notes()
    notes[0]["body"] = "开头。先把问题问清。中间补充条件。再把条件问清。"
    reading = reading_for("n1")
    reading["examples"] = [{"excerptIds": ["b2", "b4"],
                            "interpretation": "两处相同句式把提问对象从问题推进到条件。"}]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    example = result.output["profile"]["accountPortrait"]["strengths"][0]["examples"][0]
    assert example["interpretation"] == reading["examples"][0]["interpretation"]
    assert "quote" not in example
    assert [fragment["quote"] for fragment in example["fragments"]] \
        == ["先把问题问清。", "再把条件问清。"]
    assert example["fragments"][0]["end"] < example["fragments"][1]["start"]
    conclusion = model.calls[-1][2]["readings"][0]["examples"]
    assert conclusion == [{"id": "e1", "observation": example["interpretation"]}]
    verified = verified_portrait(result.output["profile"]["accountPortrait"], snapshot_for(notes))
    assert verified["strengths"][0]["examples"] == [example]


def test_repeated_identical_short_sentences_are_bound_by_distinct_ids_and_offsets():
    notes = source_notes()
    repeated, middle = "再试一次。", "中间说明。"
    notes[0]["body"] = repeated + middle + repeated
    reading = reading_for("n1")
    reading["examples"] = [{"excerptIds": ["b1", "b3"],
                            "interpretation": "重复相同短句形成前后呼应。"}]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    example = result.model_metadata["boundExamples"][0]
    assert example["fragments"] == [
        {"excerptId": "b1", "source": "body", "quote": repeated,
         "start": 0, "end": len(repeated)},
        {"excerptId": "b3", "source": "body", "quote": repeated,
         "start": len(repeated + middle), "end": len(notes[0]["body"])},
    ]
    portrait = result.output["profile"]["accountPortrait"]
    verified = verified_portrait(portrait, snapshot_for(notes))
    assert verified["strengths"][0]["examples"] == portrait["strengths"][0]["examples"]


def test_overlapping_excerpt_groups_can_reuse_one_fragment_without_losing_either_explanation():
    reading = reading_for("n1")
    reading["examples"] = [
        {"excerptIds": ["b1", "b2"], "interpretation": "从开头引出动作。"},
        {"excerptIds": ["b2", "b3"], "interpretation": "把动作接到后面的收束。"},
    ]
    synthesis = synthesis_for()
    synthesis["strengths"][0]["exampleIds"] = ["e1", "e2"]
    synthesis["writing"] = []
    model = FakeCalls(readings={"n1": reading}, synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    portrait = result.output["profile"]["accountPortrait"]
    examples = portrait["strengths"][0]["examples"]
    assert examples[0]["fragments"][-1] == examples[1]["fragments"][0]
    assert [example["interpretation"] for example in examples] \
        == [example["interpretation"] for example in reading["examples"]]
    verified = verified_portrait(portrait, snapshot_for(source_notes()))
    assert verified["strengths"][0]["examples"] == examples


@pytest.mark.parametrize("fragment_count", [4, 6])
def test_four_to_six_continuous_questions_and_a_reused_fragment_survive_as_complete_groups(
    fragment_count,
):
    notes = source_notes()
    notes[0]["body"] = "谁来决定？谁来解释？谁来承担？问题在哪？条件如何？下一步呢？"
    reading = reading_for("n1")
    reading["examples"] = [
        {"excerptIds": [f"b{index}" for index in range(1, fragment_count + 1)],
         "interpretation": "连续设问把注意力从决策者推进到具体行动。"},
        {"excerptIds": ["b4"], "interpretation": "第四问把关注点转向问题本身。"},
    ]
    synthesis = synthesis_for()
    synthesis["strengths"][0]["exampleIds"] = ["e1", "e2"]
    synthesis["writing"][0]["exampleIds"] = ["e1"]
    model = FakeCalls(notes=notes, readings={"n1": reading}, synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    portrait = result.output["profile"]["accountPortrait"]
    examples = portrait["strengths"][0]["examples"]
    assert len(examples[0]["fragments"]) == fragment_count
    assert [fragment["excerptId"] for fragment in examples[0]["fragments"]] \
        == reading["examples"][0]["excerptIds"]
    assert examples[0]["fragments"][3] == examples[1]["fragments"][0]
    assert portrait["expressionPatterns"][0]["examples"] == [examples[0]]
    verified = verified_portrait(portrait, snapshot_for(notes))
    assert verified["strengths"][0]["examples"] == examples
    assert verified["expressionPatterns"][0]["examples"] == [examples[0]]


def test_more_than_six_fragments_in_one_reading_group_is_rejected():
    notes = source_notes()
    notes[0]["body"] = "一。二。三。四。五。六。七。"
    reading = reading_for("n1")
    reading["examples"] = [{"excerptIds": [f"b{index}" for index in range(1, 8)],
                            "interpretation": "超过单组片段上限。"}]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    with pytest.raises(PydanticValidationError):
        asyncio.run(run_staged_account_report(context_for(notes), model))
    assert "synthesis" not in [stage for stage, _, _ in model.calls]


def test_nine_fragments_across_three_groups_survive_with_deduplicated_note_scope_evidence():
    notes = source_notes()
    notes[0]["body"] = "甲一。甲二。甲三。甲四。甲五。甲六。"
    notes[1]["body"] = "乙一。乙二。乙三。"
    readings = {
        "n1": {**reading_for("n1"), "examples": [
            {"excerptIds": ["b1", "b2", "b3"], "interpretation": "第一组形成三句排比。"},
            {"excerptIds": ["b4", "b5", "b6"], "interpretation": "第二组继续推进层次。"},
        ]},
        "n2": {**reading_for("n2"), "examples": [
            {"excerptIds": ["b1", "b2", "b3"], "interpretation": "另一篇也有三句并列。"},
        ]},
    }
    synthesis = synthesis_for()
    synthesis["strengths"][0]["exampleIds"] = ["e1", "e2", "e3"]
    synthesis["writing"] = []
    model = FakeCalls(notes=notes, readings=readings, synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    portrait = ProfileStageResult.model_validate(result.output).profile.accountPortrait
    finding = portrait["strengths"][0]
    assert finding["evidence"] == [{"noteId": "stable-a", "scope": "note"},
                                    {"noteId": "stable-b", "scope": "note"}]
    assert len(finding["examples"]) == 3
    assert sum(len(example["fragments"]) for example in finding["examples"]) == 9
    verified = verified_portrait(portrait, snapshot_for(notes))
    assert verified["strengths"][0]["examples"] == finding["examples"]


def test_long_original_title_selected_by_id_is_not_truncated_or_rejected_by_legacy_quote_limit():
    notes = source_notes()
    notes[0]["title"] = "完整原标题" * 50
    reading = reading_for("n1")
    reading["examples"] = [{"excerptIds": ["t"], "interpretation": "完整标题仍是一个来源片段。"}]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    portrait = result.output["profile"]["accountPortrait"]
    example = portrait["strengths"][0]["examples"][0]
    assert example["fragments"] == [reading_fragments(notes[0]["title"], notes[0]["body"])["t"]]
    assert len(example["fragments"][0]["quote"]) > 160
    verified = verified_portrait(portrait, snapshot_for(notes))
    assert verified["strengths"][0]["examples"] == [example]


@pytest.mark.parametrize("mode", ["unknown", "duplicate-in-finding"])
def test_synthesis_rejects_unknown_or_repeated_example_ids_within_one_claim(mode):
    synthesis = synthesis_for()
    if mode == "unknown":
        synthesis["strengths"][0]["exampleIds"] = ["e404"]
    else:
        synthesis["strengths"][0]["exampleIds"] = ["e1", "e1"]
    model = FakeCalls(synthesis=synthesis)
    with pytest.raises(ValueError, match="重复|不存在"):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.calls].count("synthesis") == 1


@pytest.mark.parametrize("reuse_section", ["strengths", "writing"])
def test_same_example_can_support_different_claims_without_rebinding_or_shared_mutable_fragments(
    reuse_section,
):
    synthesis = synthesis_for()
    second = {"text": "同一原文也提供另一项具体观察。", "exampleIds": ["e1"]}
    if reuse_section == "strengths":
        synthesis["strengths"].append(second)
    else:
        synthesis["writing"] = [second]
    result = asyncio.run(run_staged_account_report(context_for(), FakeCalls(synthesis=synthesis)))
    portrait = result.output["profile"]["accountPortrait"]
    section = "strengths" if reuse_section == "strengths" else "expressionPatterns"
    index = 1 if reuse_section == "strengths" else 0
    first = portrait["strengths"][0]["examples"][0]
    reused = portrait[section][index]["examples"][0]
    assert first == reused
    assert first["fragments"] is not reused["fragments"]
    verified = verified_portrait(portrait, snapshot_for(source_notes()))
    assert verified["strengths"][0]["examples"] == [first]
    assert verified[section][index]["examples"] == [reused]


@pytest.mark.parametrize("section", ["summary", "keywords", "directions", "nextSteps"])
def test_synthesis_rejects_unknown_source_note_in_every_claim_section(section):
    synthesis = synthesis_for()
    target = synthesis[section] if section == "summary" else synthesis[section][0]
    target["noteIds"] = ["n404"]
    with pytest.raises(ValueError, match="未提供的笔记"):
        asyncio.run(run_staged_account_report(context_for(), FakeCalls(synthesis=synthesis)))


def test_source_refs_are_resolved_and_deduplicated_without_inventing_quotes():
    synthesis = synthesis_for()
    synthesis["summary"]["noteIds"] = ["n3", "n1", "n3"]
    result = asyncio.run(run_staged_account_report(context_for(), FakeCalls(synthesis=synthesis)))
    assert result.output["profile"]["accountPortrait"]["summary"]["evidence"] == [
        {"noteId": "stable-c", "scope": "note"}, {"noteId": "stable-a", "scope": "note"},
    ]


def test_empty_examples_allow_empty_strengths_and_writing_without_synthetic_evidence():
    readings = {note_id: {**reading_for(note_id), "examples": []} for note_id in ("n1", "n2")}
    model = FakeCalls(readings=readings, synthesis=synthesis_for(examples=False))
    result = asyncio.run(run_staged_account_report(context_for(), model))
    portrait = result.output["profile"]["accountPortrait"]
    assert portrait["strengths"] == portrait["expressionPatterns"] == []
    assert result.model_metadata["boundExamples"] == []
    assert all(item["examples"] == [] for item in model.calls[-1][2]["readings"])


def test_single_note_runs_exactly_three_calls_and_keeps_one_note_scope():
    notes = source_notes()[:1]
    synthesis = synthesis_for()
    synthesis["summary"]["noteIds"] = ["n1"]
    synthesis["directions"][0]["noteIds"] = ["n1"]
    synthesis["writing"] = []
    model = FakeCalls(notes=notes, ids=("n1",), synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    assert [stage for stage, _, _ in model.calls] == ["overview", "read", "synthesis"]
    assert result.model_metadata["representativeNoteIds"] == ["stable-a"]
    assert len(result.model_metadata["boundExamples"]) == 1


def test_three_representatives_use_at_most_five_model_calls_and_can_leave_examples_unused():
    readings = {"n3": {
        "assessment": "丙篇有不同题材。", "correction": "不能强求全部共享写法。",
        "examples": [{"excerptIds": ["b1"],
                      "interpretation": "保持对不同作品的区分。"}],
    }}
    model = FakeCalls(ids=("n1", "n2", "n3"), readings=readings)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.calls] \
        == ["overview", "read", "read", "read", "synthesis"]
    assert len(result.model_metadata["calls"]) == 5
    assert len(result.model_metadata["boundExamples"]) == 3
    assert result.model_metadata["representativeNoteIds"] == ["stable-a", "stable-b", "stable-c"]
    portrait = result.output["profile"]["accountPortrait"]
    assert all(example["noteId"] != "stable-c"
               for section in ("strengths", "expressionPatterns")
               for finding in portrait[section] for example in finding["examples"])


@pytest.mark.parametrize("failure", ["provider", "excerpt-validation", "callback"])
def test_failed_read_cancels_pending_sibling_and_never_runs_synthesis(failure):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        model = FakeCalls()
        stages = []

        async def progress(update):
            if failure == "callback" and update["phase"] == "reading" and update["completed"] == 1:
                raise RuntimeError("进度回调失败")

        async def call(stage, system, user):
            stages.append(stage)
            if stage != "read":
                return await model(stage, system, user)
            if json.loads(user)["note"]["title"] == source_notes()[1]["title"]:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            await started.wait()
            if failure == "provider":
                raise RuntimeError("精读接口失败")
            response = await model(stage, system, user)
            if failure == "excerpt-validation":
                response.output["examples"][0]["excerptIds"] = ["b404"]
            return response

        with pytest.raises((RuntimeError, ValueError), match="失败|片段"):
            await asyncio.wait_for(
                run_staged_account_report(context_for(), call, on_update=progress), timeout=2,
            )
        assert cancelled.is_set()
        assert stages == ["overview", "read", "read"]

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["overview", "synthesis"])
def test_stage_provider_failure_is_not_retried_or_replaced_with_partial_output(stage):
    model = FakeCalls()
    calls = []

    async def call(current, system, user):
        calls.append(current)
        if current == stage:
            raise RuntimeError(f"{stage} failed")
        return await model(current, system, user)

    with pytest.raises(RuntimeError, match=f"{stage} failed"):
        asyncio.run(run_staged_account_report(context_for(), call))
    assert calls == (["overview"] if stage == "overview"
                     else ["overview", "read", "read", "synthesis"])


def test_metadata_keeps_per_call_records_and_sums_only_integer_token_usage():
    model = FakeCalls()
    metadata = []

    async def call(stage, system, user):
        response = await model(stage, system, user)
        index = len(metadata) + 1
        usage = {"prompt_tokens": index, "completion_tokens": 2 * index,
                 "total_tokens": 3 * index, "cached_tokens": 99}
        if stage == "synthesis":
            usage.update(prompt_tokens=True, completion_tokens="8", total_tokens=12.5)
        item = {"model": "fake", "requestId": f"call-{index}", "usage": usage}
        metadata.append(item)
        return ModelCallResponse(output=response.output, model_metadata=item)

    result = asyncio.run(run_staged_account_report(context_for(), call))
    assert len(result.model_metadata["calls"]) == 4
    assert result.model_metadata["usage"] == {
        "prompt_tokens": 6, "completion_tokens": 12, "total_tokens": 18,
    }
    assert [item["metadata"]["requestId"] for item in result.model_metadata["calls"]] \
        == ["call-1", "call-2", "call-3", "call-4"]
    before = deepcopy(result.model_metadata)
    for item in metadata:
        item["usage"]["prompt_tokens"] = 100000
    assert result.model_metadata == before


@pytest.mark.parametrize("packet", [
    {"schemaVersion": "account-reading-input/v1", "notes": source_notes()},
    {"schemaVersion": "account-reading-input/v2", "notes": []},
    {"schemaVersion": "account-reading-input/v2", "notes": "not-list"},
    {"schemaVersion": "account-reading-input/v2", "notes": ["not-an-object"]},
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": "  "}]},
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": 1}]},
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": "a", "body": []}]},
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": "a", "title": None}]},
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": "a"}, {"noteId": "a"}]},
])
def test_invalid_source_packet_is_rejected_before_model_use(packet):
    model = FakeCalls()
    with pytest.raises(ValueError):
        asyncio.run(run_staged_account_report({"historicalPosts": json.dumps(packet)}, model))
    assert model.calls == []


@pytest.mark.parametrize("stage", ["overview", "read", "synthesis"])
def test_stage_outputs_reject_additional_unbound_fields(stage):
    model = FakeCalls()
    target = {"overview": model.overview, "read": model.readings["n1"],
              "synthesis": model.synthesis}[stage]
    target["inventedNoteTitle"] = "不能由模型替换真实原标题"
    with pytest.raises(PydanticValidationError, match="Extra inputs"):
        asyncio.run(run_staged_account_report(context_for(), model))


def test_keyword_length_is_validated_before_assembling_report():
    synthesis = synthesis_for()
    synthesis["keywords"][0]["text"] = "长" * 13
    with pytest.raises(ValueError, match="关键词不能超过12字"):
        asyncio.run(run_staged_account_report(context_for(), FakeCalls(synthesis=synthesis)))


def test_valid_long_staged_claims_and_bound_examples_survive_profile_verification():
    notes = source_notes()
    notes[0]["title"] = "完整原标题" * 20
    notes[0]["body"] = "开头。" + "甲" * 159 + "。" + "乙" * 159 + "。"
    readings = {"n1": {
        "assessment": "有完整例子。", "correction": "",
        "examples": [{"excerptIds": ["b2"], "interpretation": "释" * 200},
                     {"excerptIds": ["b3"], "interpretation": "析" * 200}],
    }}
    synthesis = synthesis_for()
    synthesis["summary"]["text"] = "总" * 200
    synthesis["directions"][0]["text"] = "方" * 200
    synthesis["strengths"][0].update(text="判" * 200, exampleIds=["e1", "e2"])
    synthesis["writing"][0]["exampleIds"] = ["e3"]
    synthesis["nextSteps"][0]["text"] = "试" * 200
    model = FakeCalls(notes=notes, readings=readings, synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    portrait = ProfileStageResult.model_validate(result.output).profile.accountPortrait
    verified = verified_portrait(portrait, snapshot_for(notes))
    assert verified is not None
    assert verified["summary"] is not None
    assert verified["summary"]["statement"] == "总" * 200
    for section in ("readerValue", "strengths", "expressionPatterns", "nextSteps"):
        assert [item["statement"] for item in verified[section]] \
            == [item["statement"] for item in portrait[section]]
    assert len(verified["strengths"][0]["examples"]) == 2
    assert verified["strengths"][0]["examples"] == portrait["strengths"][0]["examples"]
    assert sum(sum(len(fragment["quote"]) for fragment in item["fragments"])
               + len(item["interpretation"])
               for item in verified["strengths"][0]["examples"]) > 700


@pytest.mark.parametrize(("target", "change"), [
    ("group", {"title": "模型改写的错误标题"}),
    ("group", {"noteId": "stable-b"}),
    ("group", {"interpretation": ""}),
    ("fragment", {"source": "title"}),
    ("fragment", {"source": []}),
    ("fragment", {"quote": "原文没有这句话"}),
    ("fragment", {"start": 0}),
    ("fragment", {"end": 10000}),
    ("fragment", {"start": True}),
    ("fragment", {"excerptId": "b404"}),
])
def test_profile_verifier_rejects_tampered_bound_example_blocks_without_crashing(target, change):
    result = asyncio.run(run_staged_account_report(context_for(), FakeCalls()))
    portrait = deepcopy(result.output["profile"]["accountPortrait"])
    example = portrait["strengths"][0]["examples"][0]
    (example if target == "group" else example["fragments"][0]).update(change)
    verified = verified_portrait(portrait, snapshot_for(source_notes()))
    assert verified is not None
    assert verified["strengths"] == []
    assert verified["expressionPatterns"][0]["examples"] \
        == portrait["expressionPatterns"][0]["examples"]


def test_profile_verifier_requires_bound_example_to_match_the_claim_evidence():
    result = asyncio.run(run_staged_account_report(context_for(), FakeCalls()))
    portrait = deepcopy(result.output["profile"]["accountPortrait"])
    portrait["strengths"][0]["evidence"] = [{"noteId": "stable-b", "scope": "note"}]
    verified = verified_portrait(portrait, snapshot_for(source_notes()))
    assert verified is not None
    assert verified["strengths"] == []

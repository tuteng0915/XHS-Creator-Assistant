"""Deterministic tests: staged generation uses the shared source-led report contract."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from app.models import ModelCallResponse
from app.services.account_diagnosis_evidence import verified_portrait
from app.services.account_report_contract import AccountReportOutputError
from app.services.account_report_delivery import compile_usable_account_report
from app.services.account_report_editorial import compile_editorial_profile
from app.services.account_report_passages import reading_fragments
from app.services.account_report_pipeline import (
    DEFAULT_READING_QUESTION,
    FORMAT_RECOVERY_PROMPT,
    MAX_EXTRA_REQUESTS,
    OVERVIEW_PROMPT,
    PIPELINE_VERSION,
    READ_PROMPT,
    SYNTHESIS_PROMPT,
    TEXT_SCOPE,
    run_staged_account_report,
)
from app.services.account_report_prompt import (
    SOURCE_LED_PROFILE_PROMPT,
    build_source_led_profile_prompt,
)
from app.services.account_report_sources import prepare_source_led_context
from app.workflows.account_diagnosis import ProfileStageResult


def source_notes():
    return [
        {"noteId": "stable-a", "title": "甲篇：先确认条件",
         "body": "甲篇开头。先核对费用。甲篇结尾。",
         "metrics": {"liked": 123456}, "comments": [{"content": "不应进入精读"}]},
        {"noteId": "stable-b", "title": "乙篇：从问题出发",
         "body": "乙篇开头。换个角度看这个问题。乙篇结尾。",
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


def claim(text, ids=("n1",)):
    return {"text": text, "noteIds": list(ids)}


def overview_for(ids=("n1", "n2")):
    return {
        "summary": claim("初步猜想：这些篇目关注如何判断具体条件。"),
        "directions": [claim("在具体问题里确认条件")],
        "hypotheses": ["不同篇目怎样组织判断的依据？"],
        "readings": [{"noteId": note_id, "question": f"这篇具体怎样组织判断？{note_id}"}
                     for note_id in ids],
    }


def fragmentary_overview(shape):
    output = overview_for()
    if shape == "summary-fragment":
        output["summary"]["text"] = "围绕"
    else:
        assert shape == "planning-fragments"
        output["directions"][0]["text"] = "以"
        output["readings"][0]["question"] = "这篇用"
    return output


def reading_for(note_id):
    if note_id == "n1":
        return {
            "assessment": "标题用“先”明确准备顺序；开头后写核对费用，再以结尾收束。",
            "correction": "",
            "examples": [{"excerptIds": ["b2"],
                          "interpretation": "以明确动作说明准备工作。"}],
        }
    return {
        "assessment": "标题把注意力放在问题上，正文从开头转向另一种观察角度再收束。",
        "correction": "本篇强调换角度看问题，不能直接归为核对条件的行动路径。",
        "examples": [{"excerptIds": ["b2"],
                      "interpretation": "用“换个角度”明确提示看问题的方向发生变化。"}],
    }


def source_claim(text, ids=("n1",), excerpt_id="t"):
    return {"statement": text, "evidence": [
        {"noteId": note_id, "excerptId": excerpt_id} for note_id in ids
    ]}


def synthesis_for(*, notes=None, examples=True):
    notes = source_notes() if notes is None else notes
    ids = tuple(f"n{index}" for index in range(1, min(2, len(notes)) + 1))
    title = notes[0]["title"]
    return {"profile": {
        "reportFormat": "source-led/v3",
        "accountPortrait": {
            "summary": source_claim("你主要写具体问题的判断过程。不同篇目有各自的展开方式。", ids),
            "keywords": [source_claim("具体判断")],
            "recurringThemes": [source_claim("经验判断：不同条件怎样影响选择", ids)]
            if len(ids) > 1 else [],
            "strengths": [source_claim(f"在《{title}》里，你把判断落到明确动作。", ("n1",), "b2")]
            if examples else [],
        },
        "titleReadings": [{"noteId": "n1", "parts": [{"text": title, "role": "点明关注点"}]}],
        "expressionReadings": [{
            "examples": [{"noteId": "n1", "fromExcerptId": "b2", "toExcerptId": "b2"}],
            "kind": "wording", "technique": "用具体动作说明判断过程。",
            "application": "适合需要交代准备条件的经验分享。",
        }] if examples else [],
        "structureReading": {
            "noteId": "n1", "units": [
                {"excerptIds": ["b1"], "label": "引入", "reading": "先交代观察起点"},
                {"excerptIds": ["b2", "b3"], "label": "展开与收束", "reading": "呈现动作后收束"},
            ], "kind": "narrative", "scope": "whole_note", "scopeLabel": "",
            "overview": "从开头引入观察，再展开具体动作并收束。",
        } if examples else None,
        "nextMoves": [{
            "sourceNoteId": "n1", "sourceExcerptId": "b2", "basis": "把判断落在具体动作上。",
            "action": "下次写经验判断时，可以并列比较两种条件，让读者看清选择依据。",
        }] if examples else [],
    }}


def decode_payload(stage, user):
    if stage != "synthesis":
        return json.loads(user)
    source = user.split("历史笔记：\n", 1)[1].split("\n\n请按固定六部分模板", 1)[0]
    payload = json.loads(source)
    marker = "\n\n可选精读观察：\n"
    payload["readings"] = json.loads(user.split(marker, 1)[1]) if marker in user else []
    return payload


class FakeCalls:
    def __init__(self, *, notes=None, ids=("n1", "n2"), overview=None,
                 readings=None, synthesis=None):
        self.notes = source_notes() if notes is None else notes
        self.overview = overview_for(ids) if overview is None else overview
        self.readings = {note_id: reading_for(note_id) for note_id in ids}
        if readings is not None:
            self.readings.update(readings)
        self.synthesis = synthesis_for(notes=self.notes) if synthesis is None else synthesis
        self.calls = []

    async def __call__(self, stage, system, user):
        payload = decode_payload(stage, user)
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


class ScriptedCalls(FakeCalls):
    """One outcome per actual call, with per-stage/note deterministic failures."""

    def __init__(self, failures, **kwargs):
        super().__init__(**kwargs)
        self.failures = {key: list(values) for key, values in failures.items()}
        self.raw_calls = []
        self.counts = {}

    async def __call__(self, stage, system, user):
        self.raw_calls.append((stage, system, user))
        response = await super().__call__(stage, system, user)
        note_id = ""
        if stage == "read":
            title = json.loads(user)["note"]["title"]
            note_id = next(f"n{index}" for index, note in enumerate(self.notes, 1)
                           if note["title"] == title)
        key = stage, note_id
        self.counts[key] = self.counts.get(key, 0) + 1
        response.model_metadata = {
            "model": "fake", "requestId": f"call-{len(self.raw_calls)}",
            "usage": {"prompt_tokens": 1, "completion_tokens": 2,
                      "total_tokens": 3, "reasoning_tokens": 1},
        }
        remaining = self.failures.get(key, [])
        if remaining:
            outcome = remaining.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            response.output = deepcopy(outcome)
            response.model_metadata["privateResponse"] = "private-invalid-response"
        return response


def snapshot_for(notes):
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": note["noteId"], "title": note["title"], "desc": note["body"]}
        for note in notes
    ]}}


@pytest.mark.parametrize("body", [
    "", "   \r\n\t", "  首句。\r\n下一句！\nemoji🙂保留。尾部  ",
    "长" * 321, "重复。中间。重复。", "English one. English two?\n尾句",
])
def test_every_selected_body_is_reversible_in_synthesis_including_an_unread_note(body):
    notes = source_notes()
    notes[2].update(title="完整标题" * 50, body=body, type="normal")
    model = FakeCalls(notes=notes)
    asyncio.run(run_staged_account_report(context_for(notes), model))
    payload = model.calls[-1][2]
    expected = json.loads(prepare_source_led_context(context_for(notes))["historicalPosts"])
    assert payload["notes"] == expected["notes"]
    assert payload["readingScope"] == expected["readingScope"]
    assert payload["readingScope"]["selectedNoteCount"] == 3
    assert [item["noteId"] for item in payload["readings"]] == ["n1", "n2"]
    for original, projected in zip(notes, payload["notes"], strict=True):
        assert projected["title"] == original["title"]
        assert "".join(item["text"] for item in projected["bodyExcerpts"]) == original["body"]
        assert not {"body", "quote", "stableId", "metrics", "comments"} & projected.keys()
        assert all(set(item) == {"excerptId", "text"} for item in projected["bodyExcerpts"])
    assert payload["notes"][2]["type"] == "normal"


def test_only_selected_readings_bind_positioned_catalogs_after_overview(monkeypatch):
    from app.services import account_report_pipeline

    model, events = FakeCalls(), []
    selected_titles = [note["title"] for note in source_notes()[:2]]

    def fragments(title, body):
        assert events and events[0] == "overview"
        assert title in selected_titles
        events.append(("catalog", title))
        return reading_fragments(title, body)

    async def call(stage, system, user):
        events.append(stage)
        return await model(stage, system, user)

    monkeypatch.setattr(account_report_pipeline, "reading_fragments", fragments)
    asyncio.run(run_staged_account_report(context_for(), call))
    assert {event[1] for event in events if isinstance(event, tuple)} == set(selected_titles)


def test_input_selection_synthesis_sources_and_compiler_snapshot_are_frozen_before_callbacks():
    context, forced, model = context_for(), ["n1", "n2"], FakeCalls()
    original = deepcopy(context)

    async def progress(update):
        if update["phase"] == "overview" and update["status"] == "running":
            context["historicalPosts"] = context_for([])["historicalPosts"]
            context["positioning"] = "中途替换定位"
            forced[:] = ["n3"]

    result = asyncio.run(run_staged_account_report(
        context, model, on_update=progress, representative_note_ids=forced,
    ))
    assert model.calls[0][2]["account"] == original["positioning"]
    assert model.calls[0][2]["representativeNoteIds"] == ["n1", "n2"]
    projected = json.loads(prepare_source_led_context(original)["historicalPosts"])
    assert model.calls[-1][2]["notes"] == projected["notes"]
    assert result.output == compile_usable_account_report(
        model.synthesis, snapshot_for(source_notes()),
    )
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
            before_release, callbacks_before_release = deepcopy(published), list(callback_counts)
        finally:
            release_first_store.set()
        await asyncio.wait_for(task, timeout=2)
        assert model_returns == ["n1", "n2"]
        assert [update["completed"] for update in before_release] == [0]
        assert callbacks_before_release == [0, 1]
        assert [update["completed"] for update in published] == [0, 1, 2]
        assert published[-1]["status"] == "completed"
        assert published[-1]["preview"].splitlines() == [
            f"《{source_notes()[0]['title']}》：{reading_for('n1')['assessment']}",
            f"《{source_notes()[1]['title']}》：{reading_for('n2')['assessment']}",
        ]

    asyncio.run(scenario())


def test_explicit_evaluation_can_still_read_one_representative_from_multiple_notes():
    model = FakeCalls(ids=("n1",))
    result = asyncio.run(run_staged_account_report(
        context_for(), model, representative_note_ids=["n1"],
    ))
    assert [stage for stage, _, _ in model.calls] == ["overview", "read", "synthesis"]
    assert len(model.calls[-1][2]["notes"]) == 3
    assert result.model_metadata["representativeNoteIds"] == ["stable-a"]


@pytest.mark.parametrize("forced", [[], ["n1", "n1"], ["stable-a"], ["n4"],
                                    ["n1", "n2", "n3", "n4"]])
def test_invalid_fixed_selection_fails_before_any_model_call(forced):
    model = FakeCalls()
    with pytest.raises(ValueError, match="固定精读范围"):
        asyncio.run(run_staged_account_report(context_for(), model, representative_note_ids=forced))
    assert model.calls == []


@pytest.mark.parametrize("keys", [
    (["b2"], ["b2"]), (["b1", "b2"], ["b2", "b3"]), (["b1", "b3"], ["b3"]),
])
def test_overlapping_and_noncontiguous_groups_are_auditable_without_duplicate_source_text(keys):
    reading = reading_for("n1")
    reading["examples"] = [
        {"excerptIds": ids, "interpretation": f"第{index}种具体观察。"}
        for index, ids in enumerate(keys, 1)
    ]
    model = FakeCalls(readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    bound = result.model_metadata["boundExamples"][:2]
    assert [example["id"] for example in bound] == ["e1", "e2"]
    catalog = reading_fragments(source_notes()[0]["title"], source_notes()[0]["body"])
    assert [example["fragments"] for example in bound] \
        == [[catalog[key] for key in ids] for ids in keys]
    assert model.calls[-1][2]["readings"][0]["examples"] == [
        {"excerptIds": ids, "observation": example["interpretation"]}
        for ids, example in zip(keys, reading["examples"], strict=True)
    ]
    assert "quote" not in json.dumps(model.calls[-1][2]["readings"])
    assert "fragments" not in json.dumps(model.calls[-1][2]["readings"])


@pytest.mark.parametrize("fragment_count", [4, 6])
def test_complete_question_groups_and_reused_fragments_survive_audit_and_expression_compile(
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
    synthesis = synthesis_for(notes=notes)
    synthesis["profile"]["expressionReadings"][0]["examples"][0].update(
        fromExcerptId="b1", toExcerptId=f"b{fragment_count}",
    )
    model = FakeCalls(notes=notes, readings={"n1": reading}, synthesis=synthesis)
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    bound = result.model_metadata["boundExamples"]
    assert len(bound[0]["fragments"]) == fragment_count
    assert bound[0]["fragments"][3] == bound[1]["fragments"][0]
    whole = "".join(fragment["quote"] for fragment in bound[0]["fragments"])
    assert whole in result.output["profile"]["voiceFingerprint"][0]


@pytest.mark.parametrize("title", ["  这是标题  ", "完整原标题" * 50, "先核对费用。"])
def test_title_fragments_preserve_whitespace_length_position_and_identity(title):
    notes = source_notes()
    notes[0]["title"] = title
    reading = reading_for("n1")
    reading["examples"] = [
        {"excerptIds": ["t"], "interpretation": "标题本身的具体观察。"},
        {"excerptIds": ["b2"], "interpretation": "正文动作的具体观察。"},
    ]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    model.synthesis["profile"]["accountPortrait"]["strengths"][0]["statement"] = (
        "在这篇作品中，你把判断落到明确动作。"
    )
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    first, second = result.model_metadata["boundExamples"][:2]
    assert first["fragments"] == [{"excerptId": "t", "source": "title", "quote": title,
                                    "start": 0, "end": len(title)}]
    assert first["stableId"] == second["stableId"] == "stable-a"
    assert second["fragments"][0]["source"] == "body"
    assert result.output["profile"]["titleFormulas"][0]["examples"] == [title]


def test_empty_reader_examples_do_not_prevent_synthesis_reading_the_original_sources():
    readings = {note_id: {**reading_for(note_id), "examples": []} for note_id in ("n1", "n2")}
    model = FakeCalls(readings=readings)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["boundExamples"] == []
    assert all(item["examples"] == [] for item in model.calls[-1][2]["readings"])
    assert "先核对费用。" in result.output["profile"]["voiceFingerprint"][0]


def test_empty_optional_sections_compile_without_synthetic_evidence():
    result = asyncio.run(run_staged_account_report(
        context_for(), FakeCalls(synthesis=synthesis_for(examples=False)),
    ))
    profile = result.output["profile"]
    assert profile["accountPortrait"]["strengths"] == []
    assert profile["voiceFingerprint"] == profile["hookStyles"] == []
    assert profile["viralStructure"] == {"name": "", "steps": []}


def test_single_note_runs_exactly_three_calls_and_keeps_one_source_scope():
    notes = source_notes()[:1]
    model = FakeCalls(notes=notes, ids=("n1",))
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    assert [stage for stage, _, _ in model.calls] == ["overview", "read", "synthesis"]
    assert result.model_metadata["requestCount"] == 3
    assert result.model_metadata["retryCount"] == 0
    assert result.model_metadata["representativeNoteIds"] == ["stable-a"]
    assert len(result.model_metadata["boundExamples"]) == 1
    assert len(model.calls[-1][2]["notes"]) == 1


def test_three_representatives_use_at_most_five_model_calls_and_can_leave_observations_unused():
    reading = {"assessment": "丙篇有不同题材。", "correction": "不能强求全部共享写法。",
               "examples": [{"excerptIds": ["b1"], "interpretation": "保持对不同作品的区分。"}]}
    model = FakeCalls(ids=("n1", "n2", "n3"), readings={"n3": reading})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.calls] \
        == ["overview", "read", "read", "read", "synthesis"]
    assert len(result.model_metadata["calls"]) == 5
    assert result.model_metadata["requestCount"] == 5
    assert result.model_metadata["retryCount"] == 0
    assert len(result.model_metadata["boundExamples"]) == 3
    assert result.model_metadata["representativeNoteIds"] == ["stable-a", "stable-b", "stable-c"]


def test_parent_cancellation_cancels_both_readers_without_synthesis():
    async def scenario():
        model = FakeCalls()
        started, cancelled, both_started = set(), set(), asyncio.Event()

        async def call(stage, system, user):
            if stage != "read":
                return await model(stage, system, user)
            title = json.loads(user)["note"]["title"]
            started.add(title)
            if len(started) == 2:
                both_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.add(title)
                raise

        task = asyncio.create_task(run_staged_account_report(context_for(), call))
        await asyncio.wait_for(both_started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert started == cancelled
        assert [stage for stage, _, _ in model.calls] == ["overview"]

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["overview", "synthesis"])
def test_stage_provider_failure_is_not_retried_or_replaced_with_partial_output(stage):
    model, calls = FakeCalls(), []

    async def call(current, system, user):
        calls.append(current)
        if current == stage:
            raise RuntimeError(f"{stage} failed")
        return await model(current, system, user)

    with pytest.raises(RuntimeError, match=f"{stage} failed"):
        asyncio.run(run_staged_account_report(context_for(), call))
    assert calls == (["overview"] if stage == "overview"
                     else ["overview", "read", "read", "synthesis"])


def test_metadata_sums_integer_usage_without_double_counting_reasoning_or_retaining_content():
    model, metadata = FakeCalls(), []

    async def call(stage, system, user):
        response = await model(stage, system, user)
        index = len(metadata) + 1
        usage = {"prompt_tokens": index, "completion_tokens": 2 * index,
                 "total_tokens": 3 * index, "reasoning_tokens": index, "cached_tokens": 99}
        if stage == "synthesis":
            usage.update(prompt_tokens=True, completion_tokens="8", total_tokens=12.5,
                         reasoning_tokens=False)
        item = {"model": "fake", "requestId": f"call-{index}", "usage": usage}
        metadata.append(item)
        return ModelCallResponse(output=response.output, model_metadata=item)

    result = asyncio.run(run_staged_account_report(context_for(), call))
    assert result.model_metadata["usage"] == {
        "prompt_tokens": 6, "completion_tokens": 12, "total_tokens": 18, "reasoning_tokens": 6,
    }
    assert [item["metadata"]["requestId"] for item in result.model_metadata["calls"]] \
        == ["call-1", "call-2", "call-3", "call-4"]
    before = deepcopy(result.model_metadata)
    for item in metadata:
        item["usage"]["prompt_tokens"] = 100000
    assert result.model_metadata == before


@pytest.mark.parametrize("error", [RuntimeError("unknown failure"), ValueError("bad config"),
                                  PermissionError("unauthorized"), asyncio.CancelledError()])
def test_non_output_exceptions_are_never_retried(error):
    model = ScriptedCalls({("overview", ""): [error]})
    with pytest.raises(type(error)):
        asyncio.run(run_staged_account_report(context_for(), model))
    assert model.counts == {("overview", ""): 1}


@pytest.mark.parametrize("failure", [401, 503, "runtime"])
def test_late_non_output_failure_keeps_prior_usage_and_actual_calls_without_retry(failure):
    if failure == "runtime":
        error = RuntimeError("private-runtime-detail")
    else:
        request = httpx.Request("POST", "https://provider.invalid/model")
        response = httpx.Response(failure, request=request)
        error = httpx.HTTPStatusError("private-http-detail", request=request, response=response)
    message = str(error)
    model = ScriptedCalls({("synthesis", ""): [error]})
    with pytest.raises(type(error)) as raised:
        asyncio.run(run_staged_account_report(context_for(), model))
    assert raised.value is error and str(raised.value) == message
    assert [stage for stage, _, _ in model.raw_calls] == [
        "overview", "read", "read", "synthesis",
    ]
    metadata = error.pipeline_metadata
    assert metadata["requestCount"] == 4 and metadata["retryCount"] == 0
    assert metadata["usage"] == {"prompt_tokens": 3, "completion_tokens": 6,
                                 "total_tokens": 9, "reasoning_tokens": 3}
    assert [call["status"] for call in metadata["calls"]] == [
        "completed", "completed", "completed", "failed",
    ]
    last = metadata["calls"][-1]
    assert last["stage"] == "synthesis" and last["requestIndex"] == 4
    assert last["errorCode"] == "request_failed" and last["usageUnavailable"] is True
    assert "metadata" not in last
    assert "private-" not in json.dumps(metadata)


def test_unknown_compiler_runtime_failure_keeps_usage_without_becoming_retryable(monkeypatch):
    from app.services import account_report_pipeline

    error = RuntimeError("private-compiler-detail")

    def fail_compile(output, snapshot, *, omissions=None):
        raise error

    monkeypatch.setattr(account_report_pipeline, "compile_usable_account_report", fail_compile)
    model = ScriptedCalls({})
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(run_staged_account_report(context_for(), model))
    assert raised.value is error
    metadata = error.pipeline_metadata
    assert metadata["requestCount"] == 4 and metadata["retryCount"] == 0
    assert metadata["usage"]["total_tokens"] == 12
    assert metadata["calls"][-1]["status"] == "failed"
    assert metadata["calls"][-1]["errorCode"] == "processing_failed"
    assert metadata["calls"][-1]["metadata"]["usage"]["total_tokens"] == 3
    assert "private-" not in json.dumps(metadata)


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
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": "a", "bodyExcerpts": []}]},
    {"schemaVersion": "account-reading-input/v2", "notes": [{"noteId": "n2"}, {"noteId": "a"}]},
])
def test_invalid_or_ambiguous_source_packet_is_rejected_before_model_use(packet):
    model = FakeCalls()
    with pytest.raises(ValueError):
        asyncio.run(run_staged_account_report({"historicalPosts": json.dumps(packet)}, model))
    assert model.calls == []


@pytest.mark.parametrize("grouped", [False, True])
def test_old_saved_single_and_grouped_reports_stay_readable_without_the_old_generator(grouped):
    notes = source_notes()
    note, quote = notes[0], "先核对费用。"
    example = {"noteId": note["noteId"], "title": note["title"],
               "interpretation": "以动作说明准备。"}
    if grouped:
        example["fragments"] = [reading_fragments(note["title"], note["body"])["b2"]]
        evidence = {"noteId": note["noteId"], "scope": "note"}
    else:
        start = note["body"].index(quote)
        example.update(source="body", quote=quote, start=start, end=start + len(quote))
        evidence = {"noteId": note["noteId"], "quote": quote}
    saved = {"profile": {"accountPortrait": {
        "summary": {"statement": "旧报告仍有原来的判断。", "evidence": [evidence]},
        "strengths": [{"statement": "具体动作提供参照。", "evidence": [evidence],
                       "examples": [example]}],
    }}}
    before = deepcopy(saved)
    compiled = compile_editorial_profile(saved, snapshot_for(notes))
    assert compiled == saved == before
    parsed = ProfileStageResult.model_validate(compiled).profile.accountPortrait
    assert verified_portrait(parsed, snapshot_for(notes))["strengths"][0]["examples"] == [example]
    assert saved == before



def test_default_prompt_is_the_final_contract_and_auxiliary_selection_is_optional():
    assert PIPELINE_VERSION.endswith("v5.1-balanced-default")
    assert MAX_EXTRA_REQUESTS == 1
    assert SYNTHESIS_PROMPT == SOURCE_LED_PROFILE_PROMPT
    assert OVERVIEW_PROMPT.startswith(TEXT_SCOPE)
    assert READ_PROMPT.startswith(TEXT_SCOPE)
    assert "没有合适篇目可以不选" in OVERVIEW_PROMPT
    assert "先认识本篇的题材与具体做法" in READ_PROMPT
    assert "原句怎么写→产生什么阅读作用→同类内容如何沿用" in READ_PROMPT
    assert "b编号仅用于定位原文，不表示自然段" in READ_PROMPT
    assert "不必每篇都拆标题、标点和全文结构" in READ_PROMPT
    assert "兼顾不同题材与内容价值" in OVERVIEW_PROMPT


def test_readers_run_in_parallel_but_synthesis_does_not_inherit_overview_or_questions():
    async def scenario():
        model = FakeCalls()
        started = set()
        both_started = asyncio.Event()
        events = []

        async def call(stage, system, user):
            payload = decode_payload(stage, user)
            events.append(stage)
            if stage == "read":
                title = payload["note"]["title"]
                started.add(title)
                if len(started) == 2:
                    both_started.set()
                await both_started.wait()
                assert set(payload) == {"question", "note"}
                assert "account" not in payload and "summary" not in payload
                for other in source_notes():
                    if other["title"] != title:
                        assert other["title"] not in user and other["body"] not in user
            elif stage == "synthesis":
                assert len(started) == 2
                assert system == SOURCE_LED_PROFILE_PROMPT
                assert model.overview["summary"]["text"] not in user
                assert model.overview["hypotheses"][0] not in user
                assert "initialView" not in user
                assert all("question" not in observation for observation in payload["readings"])
                assert [item["assessment"] for item in payload["readings"]] == [
                    reading_for(note_id)["assessment"] for note_id in ("n1", "n2")
                ]
                assert "context-private" not in user and "packet-private" not in user
                assert "不应进入精读" not in user
            return await model(stage, system, user)

        result = await asyncio.wait_for(run_staged_account_report(context_for(), call), timeout=2)
        assert events == ["overview", "read", "read", "synthesis"]
        assert result.output == compile_usable_account_report(
            model.synthesis, snapshot_for(source_notes()),
        )
        assert result.model_metadata["omittedStages"] == {}
        assert result.model_metadata["degradedStages"] == {}
        assert result.model_metadata["omissionCount"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("missing", ["summary", "directions", "hypotheses", "readings"])
def test_missing_overview_fields_are_not_retried(missing):
    overview = overview_for()
    del overview[missing]
    model = ScriptedCalls({}, overview=overview)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.output["profile"]
    assert model.counts[("overview", "")] == 1
    assert result.model_metadata["retryCount"] == 0
    assert result.model_metadata["requestCount"] == (2 if missing == "readings" else 4)


@pytest.mark.parametrize("overview", [{}, {"readings": []}, {"summary": "bad"},
                                       {"readings": [{"noteId": "n404", "question": "why"}]}])
def test_no_readings_use_the_exact_default_prompt_without_a_fallback_call(overview):
    model = ScriptedCalls({}, overview=overview)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert [stage for stage, _, _ in model.raw_calls] == ["overview", "synthesis"]
    assert model.raw_calls[-1][1:] == build_source_led_profile_prompt(context_for())
    assert result.model_metadata["representativeNoteIds"] == []
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("overview", [
    {}, {"readings": []}, {"readings": [{"noteId": "n2", "question": "如何制造反差？"}]},
])
def test_fixed_selection_is_program_authority_even_when_the_model_omits_or_swaps_it(overview):
    model = FakeCalls(overview=overview)
    result = asyncio.run(run_staged_account_report(
        context_for(), model, representative_note_ids=["n1"],
    ))
    assert result.model_metadata["representativeNoteIds"] == ["stable-a"]
    reader = next(payload for stage, _, payload in model.calls if stage == "read")
    assert reader["question"] == DEFAULT_READING_QUESTION
    assert reader["note"]["title"] == source_notes()[0]["title"]


def test_fixed_selection_is_preserved_even_when_overview_json_is_invalid():
    model = ScriptedCalls({("overview", ""): [AccountReportOutputError("invalid_json")]})
    result = asyncio.run(run_staged_account_report(
        context_for(), model, representative_note_ids=["n1", "n2"],
    ))
    assert result.model_metadata["representativeNoteIds"] == ["stable-a", "stable-b"]
    assert result.model_metadata["omittedStages"] == {"overview": 1}
    assert [call["status"] for call in result.model_metadata["calls"]] == [
        "omitted", "completed", "completed", "completed",
    ]


@pytest.mark.parametrize("question", [None, "", "  ", 123])
def test_auto_selection_with_a_valid_note_id_does_not_require_a_model_question(question):
    task = {"noteId": "n1"}
    if question is not None:
        task["question"] = question
    overview = {"readings": [task]}
    model = FakeCalls(overview=overview)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["representativeNoteIds"] == ["stable-a"]
    assert [stage for stage, _, _ in model.calls] == ["overview", "read", "synthesis"]
    assert model.calls[1][2]["question"] == DEFAULT_READING_QUESTION
    assert model.overview == overview
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("ids,expected", [
    (("n1", "n1"), ["stable-a"]), (("n1", "n404"), ["stable-a"]),
    (("stable-a",), []), ((), []),
    (("n1", "n2", "n3", "n4"), ["stable-a", "stable-b", "stable-c"]),
])
def test_only_legal_unique_representatives_run_without_forcing_two(ids, expected):
    model = FakeCalls(ids=ids)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["representativeNoteIds"] == expected
    assert result.model_metadata["requestCount"] == 2 + len(expected)
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("section", ["summary", "directions"])
@pytest.mark.parametrize("invalid", [
    {"text": "无效来源", "noteIds": ["n404"]}, {"text": "没有来源", "noteIds": []},
    "无来源旧文字", {"text": 123, "noteIds": ["n1"]},
])
def test_invalid_overview_claim_is_dropped_without_losing_valid_selection(section, invalid):
    overview = overview_for()
    overview[section] = invalid if section == "summary" else [invalid, claim("有效短方向")]
    model = FakeCalls(overview=overview)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["representativeNoteIds"] == ["stable-a", "stable-b"]
    assert result.model_metadata["degradedStages"] == {"overview": 1}
    assert result.model_metadata["retryCount"] == 0


def test_short_valid_question_and_missing_correction_do_not_add_admission_gates():
    overview = overview_for(("n1",))
    overview["summary"] = claim("独立判断")
    overview["readings"][0]["question"] = "如何制造反差？"
    reading = {"assessment": "用反问引入。"}
    model = FakeCalls(overview=overview, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["readingAssessments"][0]["assessment"] == reading["assessment"]
    assert result.model_metadata["readingAssessments"][0]["correction"] == ""
    assert result.model_metadata["boundExamples"] == []
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("bad", [
    {"excerptIds": ["b404"], "interpretation": "错来源"},
    {"excerptIds": ["n2:b2"], "interpretation": "串台"},
    {"excerptIds": ["b2", "b2"], "interpretation": "重复"},
    {"excerptIds": ["b3", "b2"], "interpretation": "倒序"},
    {"excerptIds": [], "interpretation": "无来源"},
    {"excerptIds": [1], "interpretation": "错类型"},
    {"source": "body", "quote": "凭空引用", "interpretation": "旧例子"},
])
def test_one_bad_reading_example_does_not_discard_assessment_or_good_example(bad):
    reading = reading_for("n1")
    good = deepcopy(reading["examples"][0])
    reading["examples"] = [bad, good]
    model = FakeCalls(readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    example = result.model_metadata["boundExamples"][0]
    assert example["fragments"][0]["quote"] == "先核对费用。"
    assert len([item for item in result.model_metadata["boundExamples"]
                if item["stableId"] == "stable-a"]) == 1
    assert result.model_metadata["readingAssessments"][0]["assessment"] == reading["assessment"]
    assert result.model_metadata["degradedStages"] == {"read": 1}
    assert result.model_metadata["retryCount"] == 0


def test_fragment_id_existing_only_in_another_note_is_not_bound():
    notes = source_notes()
    notes[1]["body"] += "另一篇第四句。"
    reading = reading_for("n1")
    reading["examples"][0]["excerptIds"] = ["b4"]
    result = asyncio.run(run_staged_account_report(
        context_for(notes), FakeCalls(notes=notes, readings={"n1": reading}),
    ))
    assert all(item["stableId"] != "stable-a" for item in result.model_metadata["boundExamples"])
    assert result.model_metadata["representativeNoteIds"] == ["stable-a", "stable-b"]


@pytest.mark.parametrize("excerpt_id", ["t", "b1"])
def test_blank_source_example_is_removed_but_report_remains_available(excerpt_id):
    notes = source_notes()
    notes[0].update(title="   ", body="   \n实际正文。")
    reading = reading_for("n1")
    reading["examples"][0]["excerptIds"] = [excerpt_id]
    model = FakeCalls(notes=notes, readings={"n1": reading})
    result = asyncio.run(run_staged_account_report(context_for(notes), model))
    assert all(item["stableId"] != "stable-a" for item in result.model_metadata["boundExamples"])
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("code", ["invalid_json", "output_truncated", "empty_output",
                                  "invalid_response", "schema_validation"])
@pytest.mark.parametrize("stage", ["overview", "read"])
def test_auxiliary_output_failures_are_omitted_once_with_known_usage_retained(stage, code):
    key = (stage, "n1" if stage == "read" else "")
    model = ScriptedCalls({key: [AccountReportOutputError(code, usage={"total_tokens": 7})]})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    metadata = result.model_metadata
    assert metadata["retryCount"] == 0 and model.counts[key] == 1
    assert metadata["omittedStages"] == {stage: 1}
    failed = next(call for call in metadata["calls"] if call["status"] == "omitted")
    assert failed["errorCode"] == code and failed["metadata"]["usage"]["total_tokens"] == 7
    assert metadata["usage"]["total_tokens"] == 7 + 3 * (metadata["requestCount"] - 1)
    assert "private-" not in json.dumps(metadata)


def test_omitted_reader_does_not_cancel_sibling_or_publish_an_invented_success_preview():
    async def scenario():
        started, omitted = asyncio.Event(), asyncio.Event()
        updates = []
        model = FakeCalls()

        async def progress(update):
            updates.append(deepcopy(update))
            if update["phase"] == "reading" and update["completed"] == 1:
                omitted.set()

        async def call(stage, system, user):
            if stage != "read":
                return await model(stage, system, user)
            if json.loads(user)["note"]["title"] == source_notes()[1]["title"]:
                started.set()
                await omitted.wait()
                return await model(stage, system, user)
            await started.wait()
            raise AccountReportOutputError("invalid_json", usage={"total_tokens": 11})

        result = await asyncio.wait_for(run_staged_account_report(
            context_for(), call, on_update=progress,
        ), timeout=2)
        assert result.model_metadata["representativeNoteIds"] == ["stable-b"]
        assert result.model_metadata["omittedStages"] == {"read": 1}
        finished = [update for update in updates if update["phase"] == "reading"]
        assert [update["completed"] for update in finished] == [0, 1, 2]
        assert finished[1]["preview"] == ""
        assert source_notes()[1]["title"] in finished[-1]["preview"]
        assert source_notes()[0]["title"] not in finished[-1]["preview"]

    asyncio.run(scenario())


def test_all_invalid_reader_assessments_fall_back_to_the_same_default_call():
    model = ScriptedCalls({}, readings={"n1": {}, "n2": {"assessment": "  "}})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert model.raw_calls[-1][1:] == build_source_led_profile_prompt(context_for())
    assert result.model_metadata["requestCount"] == 4
    assert result.model_metadata["omittedStages"] == {"read": 2}
    assert result.model_metadata["readingAssessments"] == []
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("code", ["invalid_json", "output_truncated", "empty_output"])
def test_only_unusable_final_report_retries_once_without_repeating_auxiliary_work(code):
    model = ScriptedCalls({("synthesis", ""): [AccountReportOutputError(
        code, usage={"total_tokens": 9},
    )]})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert model.counts == {("overview", ""): 1, ("read", "n1"): 1,
                            ("read", "n2"): 1, ("synthesis", ""): 2}
    assert result.model_metadata["retryCount"] == 1
    assert result.model_metadata["usage"]["total_tokens"] == 21
    first, second = model.raw_calls[-2:]
    assert first[2] == second[2]
    assert second[1] == first[1] + "\n\n" + FORMAT_RECOVERY_PROMPT


def test_empty_final_report_retries_but_missing_optional_sections_does_not():
    empty = {"profile": {"reportFormat": "source-led/v3", "accountPortrait": {}}}
    model = ScriptedCalls({("synthesis", ""): [empty]})
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["retryCount"] == 1
    sparse = synthesis_for()
    for key in ("titleReadings", "expressionReadings", "structureReading", "nextMoves"):
        sparse["profile"].pop(key)
    sparse["profile"]["accountPortrait"].pop("keywords")
    model = ScriptedCalls({}, synthesis=sparse)
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["retryCount"] == 0
    assert result.output["profile"]["accountPortrait"]["summary"]


def test_missing_summary_can_still_deliver_useful_source_bound_expression_analysis():
    synthesis = synthesis_for()
    synthesis["profile"]["accountPortrait"] = {}
    result = asyncio.run(run_staged_account_report(context_for(), FakeCalls(synthesis=synthesis)))
    assert result.output["profile"]["voiceFingerprint"]
    assert result.model_metadata["retryCount"] == 0


@pytest.mark.parametrize("section", [
    "titleReadings", "expressionReadings", "structureReading", "nextMoves",
])
def test_bad_optional_final_section_does_not_discard_the_report(section):
    synthesis = synthesis_for()
    synthesis["profile"][section] = (
        [{"invented": "bad"}] if section != "structureReading" else {"bad": True}
    )
    result = asyncio.run(run_staged_account_report(context_for(), FakeCalls(synthesis=synthesis)))
    assert result.output["profile"]["accountPortrait"]["summary"]
    assert result.model_metadata["retryCount"] == 0
    assert result.model_metadata["degradedStages"] == {"synthesis": 1}


def test_three_readings_and_one_final_recovery_never_exceed_six_requests():
    model = ScriptedCalls(
        {("synthesis", ""): [AccountReportOutputError("invalid_json")]},
        ids=("n1", "n2", "n3"),
    )
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert result.model_metadata["requestCount"] == 6
    assert result.model_metadata["retryCount"] == 1


def test_second_final_failure_remains_clear_and_retains_safe_audit():
    model = ScriptedCalls({("synthesis", ""): [
        AccountReportOutputError("invalid_json", usage={"total_tokens": 4}),
        AccountReportOutputError("empty_output", usage={"total_tokens": 5}),
    ]})
    with pytest.raises(AccountReportOutputError) as raised:
        asyncio.run(run_staged_account_report(context_for(), model))
    metadata = raised.value.pipeline_metadata
    assert metadata["requestCount"] == 5 and metadata["retryCount"] == 1
    assert metadata["usage"]["total_tokens"] == 18
    assert "private-" not in json.dumps(metadata)


@pytest.mark.parametrize("failure", ["provider", "callback"])
def test_true_request_or_callback_failure_cancels_pending_reader(failure):
    async def scenario():
        model = FakeCalls()
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def progress(update):
            if failure == "callback" and update["phase"] == "reading" and update["completed"] == 1:
                raise RuntimeError("progress failure")

        async def call(stage, system, user):
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
                raise RuntimeError("request failure")
            return await model(stage, system, user)

        with pytest.raises(RuntimeError):
            await asyncio.wait_for(run_staged_account_report(
                context_for(), call, on_update=progress,
            ), timeout=2)
        assert cancelled.is_set()

    asyncio.run(scenario())


def test_final_recovery_callback_failure_is_not_mistaken_for_bad_model_output():
    model = ScriptedCalls({("synthesis", ""): [AccountReportOutputError("invalid_json")]})

    async def progress(update):
        if "recovery" in update:
            raise AccountReportOutputError("invalid_response")

    with pytest.raises(AccountReportOutputError) as raised:
        asyncio.run(run_staged_account_report(context_for(), model, on_update=progress))
    assert model.counts[("synthesis", "")] == 1
    assert raised.value.pipeline_metadata["retryCount"] == 0


@pytest.mark.parametrize("stage", ["overview", "read"])
def test_extra_unbound_output_fields_are_ignored_and_never_replace_source_text(stage):
    model = FakeCalls()
    target = model.overview if stage == "overview" else model.readings["n1"]
    target["inventedNoteTitle"] = "不能替换原文"
    result = asyncio.run(run_staged_account_report(context_for(), model))
    assert "不能替换原文" not in json.dumps(result.output, ensure_ascii=False)
    assert result.model_metadata["retryCount"] == 0

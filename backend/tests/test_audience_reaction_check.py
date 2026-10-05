import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.models import ModelCallResponse, ModelOperation
from app.services.audience_evidence import discussion_coverage
from app.services.model_calls import ModelCallService


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_audience_reactions.py"
    spec = importlib.util.spec_from_file_location("reaction_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analysis_report(module):
    return {"status": "partially_completed", "inputHash": "saved-input",
            "result": {"method": "evidence_grounded_v1", "limitations": "测试假设",
                       "groups": [{**p, "evidenceBasis": "comment_observed"}
                                  for p in module.authored_case()["personas"]]},
            "output": {"groups": [{"id": "rejected", "name": "被拒绝的角色"}]}}


def test_analysis_case_keeps_requested_order_fields_and_source_unchanged(tmp_path):
    module = load_check()
    report = analysis_report(module)
    path = tmp_path / "analysis.json"
    raw = json.dumps(report, ensure_ascii=False)
    path.write_text(raw, encoding="utf-8")
    case = module.analysis_case(path, ["quiet", "action", "check"])
    assert case["origin"] == "analysis_report_not_saved_fan_assets"
    assert case["selectedGroupIds"] == ["quiet", "action", "check"]
    assert [p["id"] for p in case["personas"]] == case["selectedGroupIds"]
    for persona in case["personas"]:
        original = next(p for p in report["result"]["groups"] if p["id"] == persona["id"])
        for field in ["name", "profile", "interests", "coreConcern",
                      "contentPreference", "expressionStyle"]:
            assert persona[field] == original[field]
        assert persona["evidenceStatus"] == "hypothesis"
    assert path.read_text(encoding="utf-8") == raw
    assert case["sourceInputHash"] == "saved-input"


@pytest.mark.parametrize("ids", [[], ["action", "action"], ["rejected"],
                                ["action", "check", "quiet", "extra"]])
def test_analysis_case_rejects_invalid_selection_before_any_calls(tmp_path, ids):
    module = load_check()
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis_report(module)), encoding="utf-8")
    with pytest.raises(ValueError):
        module.analysis_case(path, ids)


def test_analysis_preview_does_not_load_settings_or_construct_provider(
    tmp_path, monkeypatch, capsys,
):
    module = load_check()
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis_report(module)), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("free preview must not initialize a provider or database")

    monkeypatch.setattr(module.Settings, "from_environment", forbidden)
    monkeypatch.setattr(module, "create_app", forbidden)
    monkeypatch.setattr(sys, "argv", ["check", "--audience-from", str(path),
                                    "--group-ids", "action", "check", "quiet"])
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["selectedGroupIds"] == ["action", "check", "quiet"]


def test_initial_check_uses_product_context_preserves_case_and_never_runs_graph(monkeypatch):
    module = load_check()
    case = module.authored_case()
    episode = {"noteId": "n1", "commentId": "c1", "noteTitle": "过去的笔记",
               "noteExcerpt": "过去的正文", "observedComment": "过去的评论",
               "evidenceQuote": "过去的评论", "contextLimit": "历史案例，不是待测正文"}
    case["personas"][0]["observedEpisodes"] = [episode]
    before = json.dumps(case)

    def forbidden(*args, **kwargs):
        raise AssertionError("must not use a database or full graph")

    monkeypatch.setattr(module, "create_app", forbidden)
    model = Model()
    report = asyncio.run(module.run_initial_check(model, case))
    assert report["paidRequests"] == 3
    assert report["requestAttempts"] == 3
    assert report["receivedStructuredResponses"] == 3
    assert report["billingStatus"] == "not_verified"
    assert report["status"] == "completed"
    assert report["semanticStatus"] == "not_reviewed"
    assert report["executedStages"] == ["initial_reactions"]
    assert len(report["reactions"]) == 3
    for operation, context in model.calls:
        assert operation == ModelOperation.SIMULATION_REACTION
        assert set(context) == {"topic", "persona"}
        assert context["topic"]["body"] == case["topic"]["body"]
        assert context["topic"]["previewLevel"] == "text_draft"
    assert json.dumps(case) == before
    assert model.calls[0][1]["persona"]["observedEpisodes"] == [episode]


def test_initial_check_keeps_partial_results_and_raw_invalid_reactions_without_retry():
    module = load_check()

    class Invalid(Model):
        async def call_operation(self, operation, context):
            response = await super().call_operation(operation, context)
            if context["persona"]["id"] == "action":
                response.output["reaction"]["personaId"] = "someone-else"
            elif context["persona"]["id"] == "check":
                response.output["reaction"]["triggerQuote"] = "正文没有的句子"
            return response

    model = Invalid()
    report = asyncio.run(module.run_initial_check(model, module.authored_case()))
    assert report["status"] == "partially_completed"
    assert list(report["stageErrors"]) == ["initial_reactions.action", "initial_reactions.check"]
    assert [r["personaId"] for r in report["reactions"]] == ["quiet"]
    assert len(model.calls) == 3
    assert report["calls"][0]["output"]["reaction"]["personaId"] == "someone-else"
    assert report["reactions"][0]["quote"] == ""


def test_initial_check_records_provider_failure_without_repeating_or_leaking_error():
    module = load_check()

    class Failed:
        count = 0

        async def call_operation(self, operation, context):
            self.count += 1
            raise RuntimeError("private-provider-error-secret")

    model = Failed()
    report = asyncio.run(module.run_initial_check(model, module.authored_case()))
    assert model.count == 3
    assert report["status"] == "failed"
    assert report["reactions"] == []
    assert report["requestAttempts"] == 3
    assert report["receivedStructuredResponses"] == 0
    assert report["billingStatus"] == "not_verified"
    assert "private-provider-error-secret" not in json.dumps(report)


class Model:
    def __init__(self, fail_action=False):
        self.fail_action = fail_action
        self.calls = []

    async def call_operation(self, operation, context):
        self.calls.append((operation, context))
        if operation == ModelOperation.SIMULATION_REACTION:
            persona_id = context["persona"]["id"]
            if self.fail_action and persona_id == "action":
                raise RuntimeError("provider failure")
            output = {"reaction": {
                "personaId": persona_id, "stance": "喜欢",
                "action": "comment" if persona_id == "action" else "no_comment",
                "quote": "先试第一步" if persona_id == "action" else "",
                "understanding": f"private-understanding-{persona_id}",
                "triggerQuote": "今天先用十分钟", "concerns": ["私下担心"],
            }}
        elif operation == ModelOperation.SIMULATION_DEBATE:
            output = {"debateResponse": {
                "personaId": context["persona"]["id"], "response": "同意先试第一步",
                "replyToId": context["otherReactions"][0]["messageId"],
            }}
        else:
            assert operation == ModelOperation.SIMULATION_SYNTHESIS
            output = {"synthesis": {"verdict": "测试运行，不是真实观测"}}
        return ModelCallResponse(output=output, model_metadata={"model": "injected"})


def test_check_uses_actual_graph_and_only_temporary_database(settings):
    settings.database_path.write_bytes(b"untouched-production-sentinel")
    model = Model()
    report = asyncio.run(load_check().run_check(model, settings))
    assert settings.database_path.read_bytes() == b"untouched-production-sentinel"
    assert report["case"]["origin"] == "authored_test_not_real_followers"
    assert report["status"] == "completed"
    assert report["paidRequests"] == 6
    assert report["requiresSemanticReview"] is True
    assert len(report["reactions"]) == 3
    assert {r["personaId"] for r in report["debateResponses"]} == {"check", "quiet"}
    for operation, context in model.calls:
        if operation == ModelOperation.SIMULATION_REACTION:
            assert context["topic"]["body"] == report["case"]["topic"]["body"]
            assert "otherReactions" not in context
        if operation == ModelOperation.SIMULATION_DEBATE:
            assert context["priorReaction"]["personaId"] == context["persona"]["id"]
            assert context["otherReactions"] == [
                {"messageId": "initial:action", "personaId": "action", "quote": "先试第一步",
                 "round": 1},
            ]
            assert "private-understanding-action" not in json.dumps(context)
        if operation == ModelOperation.SIMULATION_SYNTHESIS:
            coverage = context["discussionCoverage"]
            assert coverage["initialSilentPersonaIds"] == ["check", "quiet"]
            assert coverage["missingInitialPersonaIds"] == []
            assert coverage["missingDiscussionPersonaIds"] == []


def test_check_does_not_repeat_paid_call_on_graph_retry(settings):
    model = Model(fail_action=True)
    report = asyncio.run(load_check().run_check(model, settings))
    assert report["status"] == "partially_completed"
    assert report["stageErrors"]
    assert report["paidRequests"] == 4  # Three independent attempts and synthesis.
    assert len([1 for op, c in model.calls if op == ModelOperation.SIMULATION_REACTION
                and c["persona"]["id"] == "action"]) == 1
    assert len(report["reactions"]) == 2
    assert not report["debateResponses"]
    assert "RuntimeError" in [c.get("errorType") for c in report["calls"]]


def test_default_cli_only_previews_authored_case():
    script = Path(__file__).resolve().parents[2] / "scripts/check_audience_reactions.py"
    completed = subprocess.run([sys.executable, str(script)], capture_output=True,
                               text=True, check=True)
    case = json.loads(completed.stdout)
    assert case["caseId"] == "same-text-three-readers-v1"
    assert len(case["personas"]) == 3
    assert len({tuple(p["interests"]) for p in case["personas"]}) == 1
    assert len({p["coreConcern"] for p in case["personas"]}) == 3


def test_coverage_distinguishes_silence_missing_and_no_discussion():
    personas = [{"id": p} for p in ["a", "b", "c", "d"]]
    reactions = [{"personaId": "a", "action": "comment", "quote": "先试试"},
                 {"personaId": "b", "action": "no_comment"},
                 {"personaId": "c", "action": "no_comment"}]
    coverage = discussion_coverage(personas, reactions, [{"personaId": "b", "response": ""}])
    assert coverage["missingInitialPersonaIds"] == ["d"]
    assert coverage["discussionEligiblePersonaIds"] == ["b", "c"]
    assert coverage["missingDiscussionPersonaIds"] == ["c"]
    assert coverage["discussionSilentPersonaIds"] == ["b"]
    assert coverage["publicReplyCount"] == 0
    empty = discussion_coverage(personas[1:3], reactions[1:], [])
    assert empty["discussionEligiblePersonaIds"] == []
    assert empty["missingDiscussionPersonaIds"] == []


def test_synthesis_prompt_receives_coverage_and_preserves_text_preview_context(settings):
    coverage = {"discussionSilentPersonaIds": ["quiet"], "missingDiscussionPersonaIds": []}
    system, user = ModelCallService(settings)._build_prompt(ModelOperation.SIMULATION_SYNTHESIS, {
        "topic": {"previewLevel": "text_draft", "body": "不需要写代码"},
        "discussionCoverage": coverage,
    })
    assert "沉默选择，不是失败或缺失" in system
    assert "text_draft 是完整文字预演" in system
    assert "不因一个词的其他含义" in system
    assert "必须是字符串数组" in system
    assert "不要新增输入里没有的工具或服务品牌" in system
    assert "面向创作者的文字不能包含字段名" in system
    assert json.dumps(coverage, ensure_ascii=False) in user


def test_reaction_prompt_keeps_context_and_short_quotes_without_failed_candidate(settings):
    persona = {"id": "action", "profile": "习惯找入口", "interests": ["职业发展"],
               "observedEpisodes": [{"observedComment": "怎么报名"}]}
    target = {"title": "新的自助练习", "body": "不需要报名，先在自己的文档里试一下。"}
    system, user = ModelCallService(settings)._build_prompt(
        ModelOperation.SIMULATION_REACTION, {"persona": persona, "topic": target},
    )
    assert "本篇已经解决的问题不重复追问" in system
    assert "读完不评论" in system
    assert "先拿一张公开菜单" not in system
    assert "不自行加入省略号拼接" in system
    assert json.dumps(persona, ensure_ascii=False) in user
    assert json.dumps(target, ensure_ascii=False) in user


def test_initial_check_rejects_spliced_trigger_but_keeps_literal_original_ellipsis():
    module = load_check()

    class Spliced(Model):
        async def call_operation(self, operation, context):
            response = await super().call_operation(operation, context)
            if context["persona"]["id"] == "action":
                response.output["reaction"]["triggerQuote"] = "先核对费用……再决定"
            else:
                response.output["reaction"]["triggerQuote"] = "想一想……不用急"
            return response

    case = module.authored_case()
    case["topic"]["body"] = "先核对费用，确认条件，再决定。想一想……不用急。"
    report = asyncio.run(module.run_initial_check(Spliced(), case))
    assert report["stageErrors"] == {"initial_reactions.action": "ValueError"}
    assert [r["personaId"] for r in report["reactions"]] == ["check", "quiet"]
    assert report["calls"][0]["output"]["reaction"]["triggerQuote"] == "先核对费用……再决定"


def test_synthesis_replay_only_spends_one_call_and_keeps_prior_outputs(settings):
    module = load_check()
    baseline = asyncio.run(module.run_check(Model(), settings))
    before = json.dumps(baseline, ensure_ascii=False)
    model = Model()
    updated = asyncio.run(module.recheck_synthesis(model, baseline))
    assert updated["paidRequests"] == 1
    assert model.calls[0][0] == ModelOperation.SIMULATION_SYNTHESIS
    assert updated["reactions"] == baseline["reactions"]
    assert updated["debateResponses"] == baseline["debateResponses"]
    assert json.dumps(baseline, ensure_ascii=False) == before
    assert model.calls[0][1]["discussionCoverage"]["missingDiscussionPersonaIds"] == []
    assert model.calls[0][1]["topic"]["previewLevel"] == "text_draft"


def test_failed_synthesis_replay_retains_raw_output_and_does_not_retry(settings):
    module = load_check()
    baseline = asyncio.run(module.run_check(Model(), settings))

    class Malformed:
        calls = 0

        async def call_operation(self, operation, context):
            self.calls += 1
            return ModelCallResponse(output={"synthesis": {
                "verdict": "测试", "contentAdjustments": [{"location": "正文", "reason": "原因"}],
            }}, model_metadata={})

    model = Malformed()
    report = asyncio.run(module.recheck_synthesis(model, baseline))
    assert model.calls == 1
    assert report["status"] == "partially_completed"
    assert report["stageErrors"]["synthesis"] == "ValidationError"
    assert report["synthesis"] == {}
    assert report["calls"][0]["output"]["synthesis"]["contentAdjustments"][0]["location"] == "正文"
    assert report["reactions"] == baseline["reactions"]


def test_panel_synthesis_preview_is_free_and_does_not_initialize_settings(
    tmp_path, monkeypatch, capsys,
):
    module = load_check()
    baseline = {
        "case": module.authored_case(), "personas": [], "reactions": [], "debateResponses": [],
    }
    path = tmp_path / "source.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    before = path.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not read settings or initialize a database")

    monkeypatch.setattr(module.Settings, "from_environment", forbidden)
    monkeypatch.setattr(module, "create_app", forbidden)
    monkeypatch.setattr(sys, "argv", ["check", "--synthesis-from", str(path), "--panel-feedback"])
    assert module.main() == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["modelCalls"] == 0
    assert preview["taskOverrideAppliedToSynthesisOnly"] is True
    assert preview["target"]["panelTask"]["readingMode"] == "natural"
    assert path.read_bytes() == before


def test_panel_synthesis_validates_cards_and_keeps_frozen_input_and_raw_output(settings):
    module = load_check()
    baseline = asyncio.run(module.run_check(Model(), settings))
    before = json.dumps(baseline)

    class Feedback:
        calls = 0

        async def call_operation(self, operation, context):
            self.calls += 1
            assert operation == ModelOperation.SIMULATION_SYNTHESIS
            source = context["reactions"][0]
            assert "panelTask" in context["topic"]
            good = {"id": "f1", "kind": "keep", "sourceType": "reader",
                    "sourceMessageIds": [source["messageId"]], "target": {"field": "whole"},
                    "observation": "有具体步骤", "reason": "读者能开始", "priority": "first"}
            return ModelCallResponse(output={"synthesis": {"verdict": "测试",
                "editorFeedback": [good, {**good, "id": "bad", "sourceMessageIds": ["missing"]}]}},
                model_metadata={"model": "fake"})

    model = Feedback()
    report = asyncio.run(module.recheck_synthesis(model, baseline, panel_feedback=True))
    assert model.calls == report["paidRequests"] == 1
    assert report["synthesis"]["editorFeedbackValidation"]["status"] == "partial"
    assert len(report["synthesis"]["editorFeedback"]) == 1
    assert len(report["calls"][0]["output"]["synthesis"]["editorFeedback"]) == 2
    assert len(report["synthesisInputHash"]) == 64
    assert report["executedStages"] == ["synthesis"]
    assert report["semanticStatus"] == "not_reviewed"
    assert report["personas"] == baseline["personas"]
    assert report["reactions"] == baseline["reactions"]
    assert json.dumps(baseline) == before


def test_panel_feedback_requires_a_saved_synthesis_source(monkeypatch):
    module = load_check()
    monkeypatch.setattr(sys, "argv", ["check", "--panel-feedback"])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2

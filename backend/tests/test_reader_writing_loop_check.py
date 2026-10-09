import asyncio
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import ModelCallResponse, ModelOperation


def load():
    path = Path(__file__).resolve().parents[2] / "scripts/check_reader_writing_loop.py"
    spec = importlib.util.spec_from_file_location("reader_writing_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen(count=4):
    module = load()
    accounts, previous, plan = [], [], {}
    for index in range(count):
        reader = {
            "id": f"reader-{index}",
            "name": f"读者{index}",
            "profile": "关心选择代价",
            "coreConcern": "先看有没有真实取舍",
            "expressionStyle": "短句说一个看法",
            "observedEpisodes": [
                {
                    "noteId": "old",
                    "commentId": "old-comment",
                    "noteTitle": "旧文章",
                    "noteExcerpt": "不可送出的旧正文",
                    "observedComment": "历史秘密评论",
                    "evidenceQuote": "历史秘密评论",
                }
            ],
        }
        case = {
            "noteId": f"note-{index}",
            "role": "primary",
            "title": "关于选择",
            "body": "开头😀。我想记录这次选择。结尾保持不变。",
        }
        case["sourceHash"] = module.fingerprint({"title": case["title"], "body": case["body"]})
        second_reader = {
            **deepcopy(reader),
            "id": f"reader-{index}-second",
            "name": f"另一位读者{index}",
        }
        account = {
            "name": f"account-{index}",
            "workspaceId": f"workspace-{index}",
            "readers": [reader, second_reader] if index != 2 else [],
            "cases": [case],
        }
        accounts.append(account)
        previous.append({"workspaceId": account["workspaceId"], "readers": [reader, second_reader]})
        plan[account["name"]] = ((reader["id"], second_reader["id"]), "检查真实选择")
    manifest = {"accounts": accounts}
    prior = {"manifestHash": module.fingerprint(manifest), "accounts": previous}
    return module, manifest, prior, plan


def cases(count=4):
    module, manifest, prior, plan = frozen(count)
    return module.prepare_cases(manifest, prior, plan)


class Model:
    def __init__(
        self,
        *,
        fail_at=None,
        silent=False,
        first_silent=False,
        wrong_reader=False,
        bad_copy=False,
        open_question=False,
    ):
        self.settings = SimpleNamespace(model_provider="qwen")
        self.calls = []
        self.fail_at, self.silent = fail_at, silent
        self.first_silent = first_silent
        self.wrong_reader, self.bad_copy = wrong_reader, bad_copy
        self.open_question = open_question

    async def call_operation(self, operation, context):
        self.calls.append((operation, deepcopy(context)))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("never-print-private-key-or-body")
        if operation == ModelOperation.SIMULATION_REACTION:
            silent = self.silent or self.first_silent and len(self.calls) == 1
            output = {
                "reaction": {
                    "personaId": "other" if self.wrong_reader else context["persona"]["id"],
                    "stance": "犹豫",
                    "action": "no_comment" if silent else "comment",
                    "quote": "我想看你当时为什么这样选。",
                    "triggerQuote": "我想记录这次选择。",
                    "understanding": "内部理解不得传给写作者或公开聊天",
                    "concerns": ["内部担心不得冒充公开留言"],
                }
            }
        elif operation == ModelOperation.CONTENT_COLLABORATION_TURN:
            kind = "outline" if self.bad_copy else "copy_option"
            if self.open_question:
                kind = "open_question"
            output = {
                "turn": {
                    "summary": "保留原口气，聚焦选择。",
                    "nextRecipient": "creator",
                    "candidateSuggestions": [
                        {
                            "kind": kind,
                            "title": "选中段落",
                            "body": "我想先记录这次选择，也留下当时的犹豫。",
                            "confidence": "needs_creator" if self.open_question else "supported",
                            "evidenceRefs": [
                                {"sourceId": "target:topic", "quote": "我想记录这次选择。"}
                            ],
                        }
                    ],
                    "usedCandidateIds": [],
                }
            }
        else:
            assert operation == ModelOperation.PANEL_INTERVIEW
            output = {"reply": "现在更清楚了，但怎么取舍的我还想听。"}
        return ModelCallResponse(
            output=output,
            model_metadata={
                "model": "mock-qwen",
                "provider": "qwen",
                "usage": {"total_tokens": 20},
                "systemPromptHash": "mock-system",
                "apiKey": "never-save-this-key",
            },
        )


def test_prepare_uses_existing_and_prior_readers_without_mutating_freeze():
    module, manifest, prior, plan = frozen()
    before = deepcopy((manifest, prior))
    prepared = module.prepare_cases(manifest, prior, plan)
    assert len(prepared) == 4
    assert prepared[2]["readerOrigin"] == "prior_check_only"
    assert (manifest, prior) == before
    assert all("observedEpisodes" not in reader for row in prepared for reader in row["readers"])
    assert prepared[0]["historicalCommentsForLocalAudit"]["reader-0"] == ["历史秘密评论"]


def test_prepare_rejects_tampered_source_or_missing_reader():
    module, manifest, prior, plan = frozen(1)
    prior["manifestHash"] = "wrong"
    with pytest.raises(ValueError, match="冻结清单"):
        module.prepare_cases(manifest, prior, plan)
    prior["manifestHash"] = module.fingerprint(manifest)
    manifest["accounts"][0]["cases"][0]["body"] += "changed"
    prior["manifestHash"] = module.fingerprint(manifest)
    with pytest.raises(ValueError, match="笔记指纹"):
        module.prepare_cases(manifest, prior, plan)
    module, manifest, prior, plan = frozen(1)
    plan["account-0"] = (("missing", "reader-0"), "missing")
    with pytest.raises(ValueError, match="读者缺失"):
        module.prepare_cases(manifest, prior, plan)


def test_four_calls_per_account_and_semantic_results_remain_unreviewed():
    model = Model()
    prepared = cases()
    before = deepcopy(prepared)
    report = asyncio.run(load().check(prepared, model))
    assert report["status"] == "completed_unreviewed"
    assert len(model.calls) == report["requestAttempts"] == 16
    assert prepared == before
    assert all(
        a["requestAttempts"] == 4 and a["status"] == "completed_unreviewed"
        for a in report["accounts"]
    )
    assert report["semanticStatus"] == "not_reviewed"
    assert all(
        v["status"] == "not_reviewed"
        for a in report["accounts"]
        for v in a["qualityReview"].values()
    )
    assert "apiKey" not in json.dumps(report)
    assert all(
        call["contextHash"] and call["elapsedSeconds"] >= 0
        for row in report["accounts"]
        for call in row["calls"]
    )


def test_no_historical_comments_or_private_thoughts_leak_between_stages():
    model = Model()
    report = asyncio.run(load().check(cases(1), model))
    for _, context in model.calls:
        assert "历史秘密评论" not in json.dumps(context, ensure_ascii=False)
        assert "不可送出的旧正文" not in json.dumps(context, ensure_ascii=False)
    for _, context in model.calls[2:]:
        assert "内部理解不得" not in json.dumps(context, ensure_ascii=False)
        assert "内部担心不得" not in json.dumps(context, ensure_ascii=False)
    # Both initial readers read the same work without each other's reactions.
    assert "reactions" not in model.calls[0][1]
    assert "reactions" not in model.calls[1][1]
    assert model.calls[0][1]["topic"] == model.calls[1][1]["topic"]
    revisit = model.calls[3][1]
    assert revisit["publicHistory"] == [
        {"role": "reader", "senderName": "读者0", "content": "我想看你当时为什么这样选。"}
    ]
    assert revisit["reader"]["id"] == model.calls[0][1]["persona"]["id"]
    assert "contentAdjustments" not in json.dumps(revisit)
    focus = report["accounts"][0]["writingFocus"]
    assert focus["readerMessage"]["content"] == revisit["publicHistory"][0]["content"]


def test_writing_focus_reaches_real_provider_packet():
    model = Model()
    report = asyncio.run(load().check(cases(1), model))
    packet = model.calls[2][1]
    focus = packet.get("writingFocus") or packet.get("creativeBrief", {}).get("writingFocus")
    assert focus is not None, "真实写作 provider 必须带入本轮定向片段与公开读者意见"
    assert focus["selection"] == report["accounts"][0]["writingFocus"]["selection"]
    assert focus["readerMessage"]["content"] == "我想看你当时为什么这样选。"
    service = load().ModelCallService(model.settings)
    system, user = service._build_prompt(ModelOperation.CONTENT_COLLABORATION_TURN, packet)
    assert json.loads(user)["writingFocus"] == focus
    assert "selection" in system
    assert "内部担心不得" not in user


def test_unicode_codepoint_selection_and_exact_non_target_preservation():
    module = load()
    body = "开头😀。我想记录这次选择。结尾保持不变。"
    selection = module.choose_selection(body, "我想记录这次选择。")
    assert selection == {"start": 4, "end": 13, "text": "我想记录这次选择。"}
    revised, checks = module.splice(body, selection, "保留真实取舍。")
    assert revised == "开头😀。保留真实取舍。结尾保持不变。"
    assert checks == {
        "nonTargetCharactersUnchanged": True,
        "replacementIsDifferent": True,
        "offsetUnit": "unicode_codepoint",
    }
    with pytest.raises(ValueError, match="不一致"):
        module.splice(body, {**selection, "text": "wrong"}, "new")


@pytest.mark.parametrize("failure", [1, 2, 3, 4])
def test_first_failure_stops_batch_without_retry_or_secret_in_error(failure):
    model = Model(fail_at=failure)
    report = asyncio.run(load().check(cases(), model))
    assert report["status"] == "stopped_on_failure"
    assert report["requestAttempts"] == len(model.calls) == failure
    assert len(report["accounts"]) == 1
    assert "never-print" not in json.dumps(report)


def test_silent_reader_is_not_forced_into_feedback_or_rewritten():
    model = Model(silent=True)
    report = asyncio.run(load().check(cases(), model))
    assert report["requestAttempts"] == 8
    assert all(a["status"] == "no_public_feedback" for a in report["accounts"])
    assert all(op == ModelOperation.SIMULATION_REACTION for op, _ in model.calls)


@pytest.mark.parametrize("kwargs,expected", [({"wrong_reader": True}, 1)])
def test_invalid_output_stops_without_semantic_retry(kwargs, expected):
    model = Model(**kwargs)
    report = asyncio.run(load().check(cases(), model))
    assert report["status"] == "stopped_on_failure"
    assert len(model.calls) == expected


@pytest.mark.parametrize(
    "kwargs,status",
    [({"bad_copy": True}, "no_rewrite"), ({"open_question": True}, "needs_creator")],
)
def test_no_copy_is_valid_and_does_not_trigger_revisit_or_stop_next_account(kwargs, status):
    model = Model(**kwargs)
    report = asyncio.run(load().check(cases(2), model))
    assert report["status"] == "completed_unreviewed"
    assert report["maxRequests"] == 8
    assert report["requestAttempts"] == 6
    assert all(row["status"] == status for row in report["accounts"])
    assert all("revised" not in row and "revisit" not in row for row in report["accounts"])
    assert all(op != ModelOperation.PANEL_INTERVIEW for op, _ in model.calls)


def test_account_subset_is_explicit_ordered_and_budgeted():
    module, manifest, prior, plan = frozen()
    selected = module.select_plan(["account-2", "account-3"], plan)
    prepared = module.prepare_cases(manifest, prior, selected)
    report = asyncio.run(module.check(prepared, Model()))
    assert [row["name"] for row in report["accounts"]] == ["account-2", "account-3"]
    assert report["maxRequests"] == report["requestAttempts"] == 8
    assert module.select_plan(None, plan) == plan


@pytest.mark.parametrize("names", [["unknown"], ["account-0", "account-0"], []])
def test_account_subset_rejects_unknown_or_duplicate_names_before_model_use(names):
    module, _, _, plan = frozen()
    with pytest.raises(ValueError):
        module.select_plan(names, plan)


def test_http_budget_counts_hidden_extra_requests_before_dispatch():
    module = load()

    class UnexpectedExtraRequest(module.ModelCallService):
        def __init__(self):
            self.settings = SimpleNamespace(model_provider="qwen")
            self.delegate = Model()
            self.before_request = None

        # Suppress actual prompt construction in this transport-budget unit test.
        def _build_prompt(self, operation, context):
            return "mock", "mock"

        async def call_operation(self, operation, context):
            self.before_request()
            if operation == ModelOperation.CONTENT_COLLABORATION_TURN:
                self.before_request()
            return await self.delegate.call_operation(operation, context)

    service = UnexpectedExtraRequest()
    report = asyncio.run(module.check(cases(), service))
    assert report["status"] == "stopped_on_failure"
    assert report["requestAttempts"] == report["accounts"][0]["requestAttempts"] == 4
    # The fifth HTTP was denied before sending the revisit request.
    assert len(service.delegate.calls) == 3


def test_second_readers_public_feedback_is_used_if_first_reader_is_silent():
    model = Model(first_silent=True)
    report = asyncio.run(load().check(cases(1), model))
    assert report["requestAttempts"] == 4
    assert report["accounts"][0]["selectedReaderId"] == "reader-0-second"
    assert model.calls[3][1]["reader"]["id"] == "reader-0-second"
    focus = report["accounts"][0]["writingFocus"]
    assert focus["readerMessage"]["personaId"] == "reader-0-second"
    assert focus["readerReference"]["messageId"] == "initial:reader-0-second"


def test_more_than_four_accounts_is_rejected_before_any_model_request():
    model = Model()
    with pytest.raises(ValueError, match="最多四个"):
        asyncio.run(load().check([*cases(), cases(1)[0]], model))
    assert not model.calls

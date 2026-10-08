import asyncio
import importlib.util
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from test_simulated_fans import seeded as seeded

from app.models import ModelCallResponse, ModelOperation


def load():
    path = Path(__file__).resolve().parents[2] / "scripts/check_four_account_panel.py"
    spec = importlib.util.spec_from_file_location("four_panel_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(count=4):
    return {
        "accounts": [
            {
                "name": f"account-{i}",
                "workspaceId": str(i),
                "readerOrigin": "saved_assets",
                "limitation": "不是盲测",
                "readers": [
                    {
                        "id": f"r{i}-{j}",
                        "name": f"reader{j}",
                        "profile": "喜欢先试一下",
                        "observedEpisodes": [
                            {
                                "noteId": "primary",
                                "commentId": "c1",
                                "noteTitle": "保密评论",
                                "noteExcerpt": "旧正文",
                                "observedComment": "不可偷看",
                                "evidenceQuote": "不可偷看",
                            }
                        ],
                    }
                    for j in range(2)
                ],
                "cases": [
                    {
                        "noteId": "primary",
                        "role": "primary",
                        "title": "测试正文",
                        "body": "自己练习",
                    },
                    {"noteId": "reserved", "role": "reserved", "title": "留存", "body": "未调用"},
                ],
            }
            for i in range(count)
        ]
    }


class Model:
    def __init__(self, fail=False, unmatched=False):
        self.calls = []
        self.fail, self.unmatched = fail, unmatched

    async def call_operation(self, op, context):
        self.calls.append((op, context))
        if self.fail and len(self.calls) == 1:
            raise RuntimeError("never-log-secret")
        if op == ModelOperation.READER_SELECTION:
            output = {
                "proposedReaders": [
                    {
                        "fanId": p["id"],
                        "fitReason": "正文相符",
                        "contribution": "先试一遍",
                        "relation": "direct",
                    }
                    for p in context["candidates"]
                ],
                "unmatchedReason": "",
            }
            if self.unmatched:
                output = {"proposedReaders": [], "unmatchedReason": "没有相关人物"}
        elif op == ModelOperation.SIMULATION_REACTION:
            output = {
                "reaction": {
                    "personaId": context["persona"]["id"],
                    "stance": "喜欢",
                    "action": "no_comment",
                    "satisfiedNeeds": ["能直接尝试"],
                }
            }
        else:
            output = {"synthesis": {"verdict": "测试完成", "editorFeedback": []}}
        return ModelCallResponse(
            output=output, model_metadata={"model": "test", "apiKey": "secret"}
        )


def test_four_accounts_use_own_readers_only_and_no_target_comments():
    module = load()
    frozen = manifest()
    before = deepcopy(frozen)
    model = Model()
    report = asyncio.run(module.check(frozen, model))
    assert len(model.calls) == report["requestAttempts"] == 16
    assert all(a["status"] == "completed" for a in report["accounts"])
    for op, context in model.calls:
        if op == ModelOperation.SIMULATION_REACTION:
            assert context["persona"]["observedEpisodes"] == []
        assert "未调用" not in json.dumps(context, ensure_ascii=False)
    assert frozen == before
    assert "apiKey" not in json.dumps(report)


def test_failure_stops_one_case_without_retry_and_other_accounts_still_run():
    model = Model(fail=True)
    report = asyncio.run(load().check(manifest(), model))
    assert report["requestAttempts"] == 13
    assert [a["status"] for a in report["accounts"]] == ["failed"] + ["completed"] * 3
    assert "never-log-secret" not in json.dumps(report)


def test_no_matching_readers_does_not_make_up_personas():
    report = asyncio.run(load().check(manifest(), Model(unmatched=True)))
    assert report["requestAttempts"] == 4
    assert all(a["status"] == "unmatched" for a in report["accounts"])


def test_reserved_cases_do_not_change_manifest_or_reuse_primary_responses():
    frozen = manifest(count=1)
    before = deepcopy(frozen)
    model = Model()
    report = asyncio.run(load().check(frozen, model, case_role="reserved"))
    assert report["caseRole"] == "reserved"
    assert report["accounts"][0]["topic"]["body"] == "未调用"
    assert report["requestAttempts"] == 4
    assert frozen == before
    with pytest.raises(ValueError, match="另一组"):
        asyncio.run(load().check(frozen, Model(), previous=report))


def test_global_request_cap():
    report = asyncio.run(load().check(manifest(count=5), Model()))
    assert report["requestAttempts"] == 17
    assert report["accounts"][-1]["status"] == "failed"


def test_http_budget_includes_independent_reviews():
    module = load()

    class TwoRequests(module.ModelCallService):
        def __init__(self):
            self.before_request = None
            self.model = Model()

        async def call_operation(self, op, context):
            self.before_request()
            if op in {ModelOperation.READER_SELECTION, ModelOperation.SIMULATION_SYNTHESIS}:
                self.before_request()
            return await self.model.call_operation(op, context)

    report = asyncio.run(module.check(manifest(), TwoRequests()))
    assert report["requestAttempts"] == 17
    assert sum(c.get("requestCount", 0) for c in report["calls"]) == 17
    assert report["accounts"][-1]["status"] == "failed"


def test_generated_readers_are_not_substituted_after_failed_generation():
    frozen = manifest()
    frozen["accounts"][0].update(
        readers=[], readerOrigin="generated_for_check_only", audienceContext={"notes": []}
    )
    model = Model(fail=True)
    report = asyncio.run(load().check(frozen, model))
    assert model.calls[0][0] == ModelOperation.AUDIENCE_ANALYSIS
    assert report["accounts"][0]["status"] == "failed"
    assert report["requestAttempts"] == 13


def test_freeze_reads_source_and_does_not_change_db(app, seeded):
    module = load()
    wid, _, _, _ = seeded
    path = app.state.database.path
    before = path.read_bytes()
    with sqlite3.connect(path) as c:
        name = c.execute("SELECT name FROM creator_workspaces WHERE id=?", (wid,)).fetchone()[0]
        profile = json.loads(
            c.execute(
                "SELECT text_content FROM source_materials WHERE workspace_id=? "
                "AND type='xhs_creator_profile'",
                (wid,),
            ).fetchone()[0]
        )
    ids = [n["noteId"] for n in profile["notes"][:2]]
    frozen = module.freeze(path, {name: ids})
    assert len(frozen["accounts"][0]["readers"]) == 4
    assert [x["noteId"] for x in frozen["accounts"][0]["cases"]] == ids
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        module.freeze(path, {"不存在": ids})


def test_legacy_nested_snake_case_is_normalized_before_episode_filter():
    frozen = manifest(count=1)
    for p in frozen["accounts"][0]["readers"]:
        p["observedEpisodes"] = [
            {
                "note_id": "primary",
                "comment_id": "c1",
                "note_title": "标题",
                "note_excerpt": "旧正文",
                "observed_comment": "不可偷看",
                "evidence_quote": "不可偷看",
            }
        ]
    report = asyncio.run(load().check(frozen, Model()))
    assert report["accounts"][0]["status"] == "completed"
    assert report["requestAttempts"] == 4


def test_cached_responses_are_replayed_without_paid_requests_or_model_error_retry():
    module = load()
    frozen = manifest(count=1)
    previous = asyncio.run(module.check(frozen, Model()))
    model = Model()
    replay = asyncio.run(module.check(frozen, model, previous=previous))
    assert model.calls == []
    assert replay["requestAttempts"] == 0
    assert replay["accounts"][0]["status"] == "completed"
    failed = asyncio.run(module.check(frozen, Model(fail=True)))
    replay = asyncio.run(module.check(frozen, model, previous=failed))
    assert model.calls == []
    assert replay["accounts"][0]["status"] == "failed"


def test_recovery_keeps_total_budget_including_original_calls():
    module = load()
    frozen = manifest(count=1)
    previous = asyncio.run(module.check(frozen, Model()))
    previous.update(calls=previous["calls"][:1], requestAttempts=16)
    model = Model()
    replay = asyncio.run(module.check(frozen, model, previous=previous))
    assert replay["requestAttempts"] == len(model.calls) == 1
    assert replay["accounts"][0]["status"] == "failed"


def test_recovery_rejects_changed_prompt_without_new_request():
    module = load()
    frozen = manifest(count=1)
    previous = asyncio.run(module.check(frozen, Model()))

    class ChangedModel(Model):
        def _build_prompt(self, operation, context):
            return "changed system", "same user"

    model = ChangedModel()
    replay = asyncio.run(module.check(frozen, model, previous=previous))
    assert model.calls == []
    assert replay["requestAttempts"] == 0
    assert replay["accounts"][0]["status"] == "failed"

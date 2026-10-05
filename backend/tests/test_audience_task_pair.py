import asyncio
from copy import deepcopy

import pytest
from test_audience_reaction_check import Model, load_check

from app.models import ModelOperation


def case(module):
    value = module.authored_case()
    value["personas"] = value["personas"][:1]
    value["personas"][0]["observedEpisodes"] = [{
        "noteId": "history", "commentId": "comment", "noteTitle": "旧招募",
        "noteExcerpt": "旧活动报名", "observedComment": "怎么投递",
        "evidenceQuote": "怎么投递",
    }]
    return value


def test_pair_changes_only_body_and_freezes_persona_with_history():
    module = load_check()
    source = case(module)
    before = deepcopy(source)
    model = Model()
    report = asyncio.run(module.run_task_pair(model, source))
    assert report["requestAttempts"] == 2
    assert report["status"] == "completed"
    assert report["semanticStatus"] == "not_reviewed"
    assert report["skippedVariants"] == []
    assert all(op == ModelOperation.SIMULATION_REACTION for op, _ in model.calls)
    a, b = [context for _, context in model.calls]
    assert a["persona"] == b["persona"]
    assert a["persona"]["observedEpisodes"][0]["observedComment"] == "怎么投递"
    assert {key for key in a["topic"] if a["topic"][key] != b["topic"][key]} == {"body"}
    assert "无需报名" in a["topic"]["body"]
    assert "需要先报名" in b["topic"]["body"]
    assert "control" not in a and "reviewQuestions" not in a
    assert a["persona"] is not b["persona"]
    assert source == before
    hashes = report["pair"]["targetHashes"]
    assert hashes["self_guided"] != hashes["recruitment"]


def test_pair_stops_after_provider_failure_without_retry():
    module = load_check()
    model = Model(fail_action=True)
    report = asyncio.run(module.run_task_pair(model, case(module)))
    assert len(model.calls) == 1
    assert report["requestAttempts"] == 1
    assert report["status"] == "failed"
    assert report["skippedVariants"] == ["recruitment"]
    assert "provider failure" not in str(report)


@pytest.mark.parametrize("count", [0, 2, 3])
def test_pair_rejects_wrong_role_count_before_billing(count):
    module = load_check()
    source = module.authored_case()
    source["personas"] = source["personas"][:count]
    model = Model()
    with pytest.raises(ValueError, match="一位角色"):
        asyncio.run(module.run_task_pair(model, source))
    assert model.calls == []

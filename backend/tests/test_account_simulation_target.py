"""Account, published-note and creation rooms share readers without mutating assets."""
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError as SchemaError
from test_reader_selection import proposal
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import PanelTask, SimulationRunCreate
from app.services.audience_target import reader_visible_target
from app.services.common import utc_now
from app.services.reader_selection_requests import ReaderSelectionRequest


def replace_profile(app, source_id, profile):
    with app.state.database.transaction() as c:
        c.execute("UPDATE source_materials SET text_content=?,updated_at=? WHERE id=?",
                  (json.dumps(profile, ensure_ascii=False), utc_now(), source_id))


@pytest.fixture
def account(app, seeded):
    wid, source, _, fans = seeded
    profile = {
        "creator": {"displayName": "慢慢来", "profileText": "记录学习和工作里的小尝试",
                    "metrics": {"fans": 12345}},
        "accountStrategy": "不要传给读者的内部策略",
        "notes": [{"noteId": str(i), "title": f"第{i}篇学习记录",
                   "desc": f"从第{i}个具体例子开始。" + ("例" * 1800 if i == 0 else "再做下一步。"),
                   "metrics": {"views": 89191},
                   "comments": [{"content": "历史评论不许当做模拟意见"}],
                   "cover": {"url": "private-image"}} for i in range(25)],
    }
    replace_profile(app, source["id"], profile)
    return wid, source, fans, profile


def recommended_account(app, account):
    wid, source, fans, _ = account
    request = ReaderSelectionRequest(request_key="account-recommendation",
                                     account_profile_id=source["id"], panel_task=PanelTask())
    selection = app.state.reader_selection_requests.create(wid, request)
    claim = app.state.reader_selection_service.claim(wid, selection.id)
    selection = app.state.reader_selection_service.complete(wid, selection.id, claim.token, {
        "proposedReaders": [proposal(fans[0]["id"])],
    })
    payload = SimulationRunCreate(account_profile_id=source["id"],
                                  simulated_fan_ids=[fans[0]["id"]], panel_task=PanelTask(),
                                  reader_selection_id=selection.id,
                                  reader_selection_input_hash=selection.input_hash)
    return request, selection, payload


def test_account_uses_same_bounded_distributed_text_for_retrieval_and_readers(app, account):
    wid, source, _, _ = account
    _, selection, payload = recommended_account(app, account)
    run = app.state.simulation_service.create(wid, payload)
    target = reader_visible_target(run.input_snapshot)
    assert target == selection.input_snapshot.target
    assert target["targetType"] == target["previewLevel"] == "account"
    assert target["simulationCategory"] == "account"
    assert run.topic_id is None and run.draft_id is None
    assert send(app, "GET", f"/api/workspaces/{wid}/topics").json() == []
    frozen = run.input_snapshot["sourceAccount"]
    assert frozen["sourceMaterialId"] == source["id"]
    assert frozen["biography"] == "记录学习和工作里的小尝试"
    assert len(frozen["notes"]) == 12
    assert frozen["notes"][0]["noteId"] == "0" and frozen["notes"][-1]["noteId"] == "24"
    assert len({n["noteId"] for n in frozen["notes"]}) == 12
    assert all(len(n["title"]) + len(n["body"]) <= 1200 for n in frozen["notes"])
    assert frozen["scope"]["totalNoteCount"] == 25
    assert frozen["scope"]["omittedNoteCount"] == 13
    assert frozen["scope"]["truncatedNoteCount"] == 1
    assert "13 篇" in frozen["scope"]["omissionNotice"]
    serialized = json.dumps(target, ensure_ascii=False)
    for forbidden in ("89191", "12345", "历史评论", "内部策略", "private-image", "sourceUpdatedAt"):
        assert forbidden not in serialized
    assert run.simulation_category == "account"
    assert run.target_title == "慢慢来 · 账号整体"
    summary = send(app, "GET", f"/api/workspaces/{wid}/simulation-runs").json()[0]
    assert summary["simulationCategory"] == "account"
    assert summary["sourceMaterialId"] == source["id"]
    assert summary["noteId"] is None and summary["targetTitle"] == run.target_title


def test_account_snapshot_is_frozen_and_sampled_text_changes_expire_recommendation(app, account):
    wid, source, _, profile = account
    request, selection, payload = recommended_account(app, account)
    run = app.state.simulation_service.create(wid, payload)
    frozen = deepcopy(run.input_snapshot)
    profile["notes"][0]["metrics"] = {"views": 1}
    profile["notes"][0]["comments"] = [{"content": "新评论"}]
    replace_profile(app, source["id"], profile)
    observe = app.state.reader_selection_requests.observe
    assert observe(wid, selection.id).freshness.status == "current"
    profile["notes"][24]["title"] = "新标题改变了整体内容"
    replace_profile(app, source["id"], profile)
    assert observe(wid, selection.id).freshness.status == "stale"
    with pytest.raises(ConflictError, match="依据已变化"):
        app.state.simulation_service.create(wid, payload)
    assert app.state.reader_selection_requests.create(wid, request) == selection
    profile["notes"] = []
    replace_profile(app, source["id"], profile)
    assert observe(wid, selection.id).freshness.status == "unavailable"
    assert app.state.simulation_service.get(run.id).input_snapshot == frozen


def test_account_and_note_recommendations_cannot_be_interchanged(app, account):
    wid, source, _, _ = account
    _, _, payload = recommended_account(app, account)
    with pytest.raises(ConflictError, match="不属于当前"):
        app.state.simulation_service.create(wid, payload.model_copy(update={
            "account_profile_id": None, "source_material_id": source["id"], "note_id": "0",
        }))
    assert app.state.simulation_service.list(wid) == []


def test_account_sources_cannot_cross_workspace_or_use_other_asset_type(app, account):
    _, source, _, _ = account
    other = create_workspace(app)["id"]
    with pytest.raises(NotFoundError):
        app.state.simulation_service.create(other, SimulationRunCreate(
            account_profile_id=source["id"],
        ))
    with pytest.raises(NotFoundError):
        app.state.reader_selection_requests.create(other, ReaderSelectionRequest(
            request_key="other-account", account_profile_id=source["id"],
        ))
    with app.state.database.transaction() as c:
        c.execute("UPDATE source_materials SET type='historical_posts' WHERE id=?", (source["id"],))
    with pytest.raises(NotFoundError):
        app.state.simulation_service.create(account[0], SimulationRunCreate(
            account_profile_id=source["id"],
        ))


@pytest.mark.parametrize("notes", [[], [None, {}], [{"noteId": "empty", "desc": " "}]])
def test_account_requires_readable_note_samples(app, account, notes):
    wid, source, _, profile = account
    profile["notes"] = notes
    replace_profile(app, source["id"], profile)
    with pytest.raises(ValidationError, match="可供阅读"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_profile_id=source["id"],
        ))


def test_single_note_account_and_legacy_history_category(app, account):
    wid, source, fans, profile = account
    profile["notes"] = profile["notes"][1:2]
    replace_profile(app, source["id"], profile)
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        account_profile_id=source["id"], simulated_fan_ids=[fans[0]["id"]],
    ))
    assert run.input_snapshot["sourceAccount"]["scope"]["sampledNoteCount"] == 1
    note = app.state.simulation_service.create(wid, SimulationRunCreate(
        source_material_id=source["id"], note_id="1", simulated_fan_ids=[fans[0]["id"]],
    ))
    manual = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="还没写的标题",
    ))
    for item, expected in ((note, "published_note"), (manual, "creation")):
        snapshot = deepcopy(item.input_snapshot)
        snapshot.pop("simulationCategory")
        with app.state.database.transaction() as c:
            c.execute("UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
                      (json.dumps(snapshot, ensure_ascii=False), item.id))
        assert app.state.simulation_service.get(item.id).simulation_category == expected
        assert next(s for s in app.state.simulation_service.list(wid)
                    if s.id == item.id).simulation_category == expected


def test_local_reader_adjustment_is_frozen_not_saved_and_marks_adoption_adjusted(app, account):
    wid, _, fans, _ = account
    _, selection, base = recommended_account(app, account)
    changes = {"profile": "愿意长期关注能直接拿去试的小练习", "coreConcern": "下一周能尝试什么",
               "expressionStyle": "先举一个具体例子，然后问一个短问题"}
    payload = SimulationRunCreate.model_validate({
        **base.model_dump(by_alias=True), "personaOverrides": {fans[0]["id"]: changes},
    })
    run = app.state.simulation_service.create(wid, payload)
    persona = run.input_snapshot["audiencePersonas"][0]
    assert all(persona[key] == value for key, value in changes.items())
    assert persona["sessionOverride"] == changes and persona["userAdjusted"]
    assert run.input_snapshot["personaOverrides"] == {fans[0]["id"]: changes}
    adoption = run.input_snapshot["readerSelection"]
    assert adoption["source"] == "adjusted"
    assert adoption["personaOverridesAfterRecommendation"] == {fans[0]["id"]: changes}
    assert send(app, "GET", f"/api/simulated-fans/{fans[0]['id']}").json() == fans[0]
    assert app.state.reader_selection_service.get(wid, selection.id) == selection
    plain = app.state.simulation_service.create(wid, base)
    assert plain.input_snapshot["audiencePersonas"][0]["profile"] == fans[0]["editable"]["profile"]
    assert plain.input_snapshot["readerSelection"]["source"] == "recommended"


def test_manual_local_adjustment_and_unselected_reader_rejection(app, account):
    wid, source, fans, _ = account
    data = {"accountProfileId": source["id"], "simulatedFanIds": [fans[0]["id"]],
            "personaOverrides": {fans[0]["id"]: {"coreConcern": "愿意持续读的原因"}}}
    run = app.state.simulation_service.create(wid, SimulationRunCreate.model_validate(data))
    assert run.input_snapshot["readerSelection"]["source"] == "manual"
    data["personaOverrides"] = {fans[1]["id"]: {"profile": "没选择的人不应出现"}}
    with pytest.raises(ValidationError, match="已选择"):
        app.state.simulation_service.create(wid, SimulationRunCreate.model_validate(data))


@pytest.mark.parametrize("override", [
    {}, {"profile": " "}, {"coreConcern": ""}, {"expressionStyle": "x" * 2001},
    {"name": "不支持的修改"}, {"profile": 123},
])
def test_invalid_local_adjustments_are_rejected(override):
    with pytest.raises(SchemaError):
        SimulationRunCreate.model_validate({"manualTopic": "测试", "simulatedFanIds": ["f"],
                                            "personaOverrides": {"f": override}})


def test_account_target_exclusive_and_legacy_request_identity_stable(app, account):
    wid, source, _, _ = account
    with pytest.raises(SchemaError):
        ReaderSelectionRequest(request_key="two", account_profile_id=source["id"],
                               manual_topic="标题")
    with pytest.raises(ValidationError, match="请选择一个"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_profile_id=source["id"], manual_topic="标题",
        ))
    identity = json.loads(ReaderSelectionRequest(request_key="old", manual_topic="标题").identity())
    assert "accountProfileId" not in identity and "sourceMaterialId" not in identity
    assert identity == {"topicId": None, "draftId": None, "manualTopic": "标题", "desiredCount": 3}

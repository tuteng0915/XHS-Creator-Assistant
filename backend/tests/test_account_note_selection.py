"""Explicit account scopes use one exact, frozen set for recommendation and reading."""
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError as SchemaError
from test_account_simulation_target import account as account
from test_account_simulation_target import replace_profile
from test_reader_selection import proposal
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import AccountNoteSelection, PanelTask, SimulationRunCreate
from app.services import account_simulation_target as account_targets
from app.services.audience_target import reader_visible_target
from app.services.reader_selection_prompt import selection_prompt
from app.services.reader_selection_requests import ReaderSelectionRequest


def scope(source_id, note_ids):
    return AccountNoteSelection(source_material_id=source_id, selected_note_ids=note_ids)


def recommend(app, account, note_ids, key="selected-account"):
    wid, source, fans, _ = account
    selected = scope(source["id"], note_ids)
    request = ReaderSelectionRequest(
        request_key=key, account_note_selection=selected, panel_task=PanelTask(),
    )
    selection = app.state.reader_selection_requests.create(wid, request)
    claim = app.state.reader_selection_service.claim(wid, selection.id)
    selection = app.state.reader_selection_service.complete(wid, selection.id, claim.token, {
        "proposedReaders": [proposal(fans[0]["id"])],
    })
    payload = SimulationRunCreate(
        account_note_selection=selected, simulated_fan_ids=[fans[0]["id"]],
        panel_task=PanelTask(), reader_selection_id=selection.id,
        reader_selection_input_hash=selection.input_hash,
    )
    return request, selection, payload


def test_explicit_subset_is_shared_frozen_and_does_not_leak_all_account_summary(app, account):
    wid, source, _, profile = account
    profile["creator"].update({"bio": "真实简介", "profileText": "全账号总结包含未选择的秘密内容"})
    profile["notes"][24]["desc"] = "未选择的另一篇秘密内容"
    replace_profile(app, source["id"], profile)
    _, selection, payload = recommend(app, account, ["2", "0"])
    run = app.state.simulation_service.create(wid, payload)
    target = reader_visible_target(run.input_snapshot)
    assert target == selection.input_snapshot.target
    frozen = run.input_snapshot["sourceAccount"]
    assert [note["noteId"] for note in frozen["notes"]] == ["0", "2"]
    assert frozen["biography"] == "真实简介"
    assert frozen["scope"]["selectedNoteIds"] == ["0", "2"]
    assert frozen["scope"]["selectedNoteCount"] == frozen["scope"]["sampledNoteCount"] == 2
    assert frozen["scope"]["selectionMethod"] == "explicit_ids"
    assert frozen["scope"]["sourceMaterialId"] == source["id"]
    assert frozen["scope"]["truncatedNoteCount"] == 1
    assert "1200 字" in frozen["scope"]["omissionNotice"]
    assert run.target_title == "慢慢来 · 所选 2 篇笔记"
    assert run.simulation_category == "account"
    assert run.source_material_id == source["id"] and run.note_id is None
    _, prompt = selection_prompt(selection.input_snapshot)
    for secret in ("全账号总结", "秘密内容", "内部策略", "历史评论", "private-image", "89191"):
        assert secret not in json.dumps(target, ensure_ascii=False)
        assert secret not in prompt
    assert run.input_snapshot["readerSelection"]["source"] == "recommended"
    original = deepcopy(run.input_snapshot)
    profile["notes"] = []
    replace_profile(app, source["id"], profile)
    assert app.state.simulation_service.get(run.id).input_snapshot == original
    assert app.state.reader_selection_requests.observe(wid, selection.id).freshness.status \
        == "unavailable"


def test_more_than_twelve_selected_notes_all_enter_recommendation_and_simulation(app, account):
    wid, _, _, _ = account
    ids = [str(index) for index in range(1, 21)]
    _, selection, payload = recommend(app, account, ids)
    run = app.state.simulation_service.create(wid, payload)
    frozen = run.input_snapshot["sourceAccount"]
    assert [note["noteId"] for note in frozen["notes"]] == ids
    assert frozen["scope"]["selectedNoteCount"] == 20
    assert frozen["scope"]["selectedNoteIds"] == sorted(ids)
    assert "20 篇" in frozen["scope"]["omissionNotice"]
    assert reader_visible_target(run.input_snapshot) == selection.input_snapshot.target
    _, prompt = selection_prompt(selection.input_snapshot)
    for index in range(1, 21):
        assert f"第{index}篇学习记录" in prompt
        assert f"从第{index}个具体例子开始。" in prompt


def test_same_set_order_replays_but_different_set_conflicts_and_changes_hash(app, account):
    wid, source, _, _ = account
    request, selection, payload = recommend(app, account, ["2", "1"])
    reordered = ReaderSelectionRequest(
        request_key=request.request_key,
        account_note_selection=scope(source["id"], ["1", "2"]), panel_task=PanelTask(),
    )
    assert reordered.identity() == request.identity()
    assert app.state.reader_selection_requests.create(wid, reordered) == selection
    reordered_run = payload.model_copy(update={
        "account_note_selection": scope(source["id"], ["1", "2"]),
    })
    assert app.state.simulation_service.create(wid, reordered_run).input_snapshot[
        "readerSelection"
    ]["source"] == "recommended"
    changed = request.model_copy(update={"account_note_selection": scope(source["id"], ["3"])})
    with pytest.raises(ConflictError, match="不同目标"):
        app.state.reader_selection_requests.create(wid, changed)
    with pytest.raises(ConflictError, match="不属于当前"):
        app.state.simulation_service.create(wid, payload.model_copy(update={
            "account_note_selection": scope(source["id"], ["3"]),
        }))
    different = app.state.reader_selection_requests.create(
        wid, changed.model_copy(update={"request_key": "different-set"}),
    )
    assert different.input_hash != selection.input_hash


def test_same_titles_and_bodies_with_distinct_ids_are_distinct_targets(app, account):
    wid, source, _, profile = account
    profile["notes"][2].update({"title": profile["notes"][1]["title"],
                                "desc": profile["notes"][1]["desc"]})
    replace_profile(app, source["id"], profile)
    _, first, payload = recommend(app, account, ["1"], key="same-title-first")
    _, second, _ = recommend(app, account, ["2"], key="same-title-second")
    assert first.input_snapshot.target["body"] == second.input_snapshot.target["body"]
    assert first.input_hash != second.input_hash
    with pytest.raises(ConflictError, match="不属于当前"):
        app.state.simulation_service.create(wid, payload.model_copy(update={
            "account_note_selection": scope(source["id"], ["2"]),
        }))


def test_only_selected_text_changes_expire_recommendation_and_legacy_history_stays_frozen(
    app, account,
):
    wid, source, _, profile = account
    legacy = app.state.simulation_service.create(wid, SimulationRunCreate(
        account_profile_id=source["id"],
    ))
    legacy_snapshot = deepcopy(legacy.input_snapshot)
    request, selection, payload = recommend(app, account, ["1", "2"])
    profile["creator"]["profileText"] = "全账号摘要后来被更新"
    profile["notes"][24]["desc"] = "未选笔记改变"
    profile["notes"][1]["metrics"] = {"liked": 123}
    replace_profile(app, source["id"], profile)
    observe = app.state.reader_selection_requests.observe
    assert observe(wid, selection.id).freshness.status == "current"
    profile["notes"][1]["desc"] = "所选笔记改变"
    replace_profile(app, source["id"], profile)
    assert observe(wid, selection.id).freshness.status == "stale"
    with pytest.raises(ConflictError, match="依据已变化"):
        app.state.simulation_service.create(wid, payload)
    assert app.state.reader_selection_requests.create(wid, request) == selection
    assert app.state.simulation_service.get(legacy.id).input_snapshot == legacy_snapshot
    assert len(legacy_snapshot["sourceAccount"]["notes"]) == 12


@pytest.mark.parametrize("change", ["append", "delete"])
def test_unselected_note_inventory_changes_keep_recommendation_current_and_adoptable(
    app, account, change,
):
    wid, source, _, profile = account
    request, selection, payload = recommend(app, account, ["1", "2"])
    before = app.state.simulation_service.create(wid, payload)
    original_snapshot = deepcopy(before.input_snapshot)
    original_target = selection.input_snapshot.target
    assert "totalNoteCount" not in original_target["accountScope"]
    assert "omittedNoteCount" not in original_target["accountScope"]
    if change == "append":
        profile["notes"].append({"noteId": "new-unselected", "title": "新笔记", "desc": "未选正文"})
        expected_count = 26
    else:
        profile["notes"] = [note for note in profile["notes"] if note["noteId"] != "24"]
        expected_count = 24
    replace_profile(app, source["id"], profile)
    observed = app.state.reader_selection_requests.observe(wid, selection.id)
    assert observed.freshness.status == "current"
    assert observed.freshness.current_input_hash == selection.input_hash
    reread = app.state.reader_selection_requests.create(wid, request.model_copy(update={
        "request_key": f"after-unselected-{change}",
    }))
    assert reread.input_hash == selection.input_hash
    assert reread.input_snapshot.target == original_target
    run = app.state.simulation_service.create(wid, payload)
    assert run.input_snapshot["readerSelection"]["source"] == "recommended"
    assert reader_visible_target(run.input_snapshot) == original_target
    assert run.input_snapshot["sourceAccount"]["scope"]["totalNoteCount"] == expected_count
    assert run.input_snapshot["sourceAccount"]["scope"]["omittedNoteCount"] == expected_count - 2
    assert app.state.simulation_service.get(before.id).input_snapshot == original_snapshot
    # Removing an actual selected note still makes the recommendation unusable.
    profile["notes"] = [note for note in profile["notes"] if note["noteId"] != "1"]
    replace_profile(app, source["id"], profile)
    assert app.state.reader_selection_requests.observe(wid, selection.id).freshness.status \
        == "unavailable"
    with pytest.raises(ConflictError, match="依据已变化"):
        app.state.simulation_service.create(wid, payload)


def test_unselected_inventory_does_not_spend_selected_content_size_budget(
    app, account, monkeypatch,
):
    wid, source, _, profile = account
    profile["notes"] = profile["notes"][:9]
    replace_profile(app, source["id"], profile)
    baseline = app.state.simulation_service.create(wid, SimulationRunCreate(
        account_note_selection=scope(source["id"], ["1", "2"]),
    ))
    target = reader_visible_target(baseline.input_snapshot)
    limit = len(json.dumps(target, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(account_targets, "MAX_ACCOUNT_TARGET_BYTES", limit)
    _, selection, payload = recommend(app, account, ["1", "2"])
    # 9 → 10 changes the serialized inventory count's width, but not reading content.
    profile["notes"].append({"noteId": "new-unselected", "title": "第十篇", "desc": "未选正文"})
    replace_profile(app, source["id"], profile)
    assert app.state.reader_selection_requests.observe(wid, selection.id).freshness.status \
        == "current"
    run = app.state.simulation_service.create(wid, payload)
    assert reader_visible_target(run.input_snapshot) == target
    assert run.input_snapshot["sourceAccount"]["scope"]["totalNoteCount"] == 10


@pytest.mark.parametrize("selection", [
    {}, {"sourceMaterialId": "source", "selectedNoteIds": []},
    {"sourceMaterialId": "source", "selectedNoteIds": ["a", "a"]},
    {"sourceMaterialId": "source", "selectedNoteIds": [" "]},
    {"sourceMaterialId": " ", "selectedNoteIds": ["a"]},
    {"sourceMaterialId": "source", "selectedNoteIds": [1]},
    {"sourceMaterialId": "source", "selectedNoteIds": "a"},
])
def test_malformed_selection_is_rejected_by_both_contracts(selection):
    with pytest.raises(SchemaError):
        ReaderSelectionRequest.model_validate({
            "requestKey": "invalid", "accountNoteSelection": selection,
        })
    with pytest.raises(SchemaError):
        SimulationRunCreate.model_validate({"accountNoteSelection": selection})


@pytest.mark.parametrize("ids", [["not-present"], ["1", "foreign-id"]])
def test_nonexistent_or_mixed_foreign_ids_do_not_fall_back_to_all_notes(app, account, ids):
    wid, source, _, _ = account
    selected = scope(source["id"], ids)
    with pytest.raises(ValidationError, match="所选笔记无效"):
        app.state.reader_selection_requests.create(wid, ReaderSelectionRequest(
            request_key="invalid-set", account_note_selection=selected,
        ))
    with pytest.raises(ValidationError, match="所选笔记无效"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_note_selection=selected,
        ))
    assert app.state.simulation_service.list(wid) == []
    assert app.state.reader_selection_service.pending() == []


def test_cross_workspace_material_is_rejected_for_both_paths(app, account):
    _, source, _, _ = account
    other = create_workspace(app)["id"]
    selected = scope(source["id"], ["1"])
    with pytest.raises(NotFoundError):
        app.state.reader_selection_requests.create(other, ReaderSelectionRequest(
            request_key="cross-account", account_note_selection=selected,
        ))
    with pytest.raises(NotFoundError):
        app.state.simulation_service.create(other, SimulationRunCreate(
            account_note_selection=selected,
        ))


@pytest.mark.parametrize("notes", [
    [{"noteId": "dup", "desc": "甲"}, {"noteId": "dup", "desc": "乙"}],
    [{"noteId": "dup", "desc": "甲"}, {"noteId": "dup", "desc": ""}],
])
def test_ambiguous_stored_ids_fail_instead_of_picking_first(app, account, notes):
    wid, source, _, profile = account
    profile["notes"] = notes
    replace_profile(app, source["id"], profile)
    with pytest.raises(ValidationError, match="所选笔记无效"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_note_selection=scope(source["id"], ["dup"]),
        ))


def test_legacy_fallback_ids_match_browser_after_filtering_malformed_rows(app, account):
    wid, source, _, profile = account
    profile["notes"] = [None, {"title": "旧第一篇", "desc": "旧正文"}, "bad",
                        {"title": "旧第二篇", "desc": "另一个正文"}]
    replace_profile(app, source["id"], profile)
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        account_note_selection=scope(source["id"], ["1"]),
    ))
    assert run.input_snapshot["sourceAccount"]["notes"] == [
        {"noteId": "1", "title": "旧第二篇", "body": "另一个正文"},
    ]


def test_selected_empty_note_fails_without_silently_dropping_it(app, account):
    wid, source, _, profile = account
    profile["notes"][2].update({"title": "", "desc": " "})
    replace_profile(app, source["id"], profile)
    with pytest.raises(ValidationError, match="未自动省略"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_note_selection=scope(source["id"], ["1", "2"]),
        ))


def test_oversize_selection_fails_both_paths_without_creating_partial_scope(app, account):
    wid, source, _, profile = account
    for note in profile["notes"]:
        note["desc"] = "长" * 2000
    replace_profile(app, source["id"], profile)
    selected = scope(source["id"], [str(index) for index in range(25)])
    with pytest.raises(ValidationError, match="不会自动省略"):
        app.state.reader_selection_requests.create(wid, ReaderSelectionRequest(
            request_key="too-long", account_note_selection=selected,
        ))
    with pytest.raises(ValidationError, match="不会自动省略"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_note_selection=selected,
        ))
    assert app.state.simulation_service.list(wid) == []
    assert app.state.reader_selection_service.pending() == []


def test_explicit_selection_exclusive_with_legacy_target_and_old_identity_unchanged(app, account):
    wid, source, _, _ = account
    selected = scope(source["id"], ["1"])
    with pytest.raises(SchemaError):
        ReaderSelectionRequest(request_key="two", account_note_selection=selected,
                               account_profile_id=source["id"])
    with pytest.raises(ValidationError, match="请选择一个"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            account_note_selection=selected, account_profile_id=source["id"],
        ))
    legacy = ReaderSelectionRequest(request_key="old", account_profile_id=source["id"])
    assert "accountNoteSelection" not in json.loads(legacy.identity())


def test_http_accepts_explicit_target_and_rejects_empty_selection_before_execution(app, account):
    wid, source, _, _ = account
    response = send(app, "POST", f"/api/workspaces/{wid}/simulation-runs", json={
        "accountNoteSelection": {"sourceMaterialId": source["id"], "selectedNoteIds": ["1", "2"]},
    })
    assert response.status_code == 201, response.text
    assert response.json()["inputSnapshot"]["sourceAccount"]["scope"]["selectedNoteIds"] \
        == ["1", "2"]
    for suffix, extra in (("simulation-runs", {}), ("reader-selections", {"requestKey": "bad"})):
        response = send(app, "POST", f"/api/workspaces/{wid}/{suffix}", json={
            **extra, "accountNoteSelection": {"sourceMaterialId": source["id"],
                                               "selectedNoteIds": []},
        })
        assert response.status_code == 422

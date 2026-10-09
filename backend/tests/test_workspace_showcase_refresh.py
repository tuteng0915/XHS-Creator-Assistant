"""A prose refresh cannot rewrite sources, adoption lineage or reviewed histories."""
import json
import sqlite3
from copy import deepcopy

import pytest
from test_workspace_showcases import bundle, histories, rows  # noqa: F401

from app.services.simulated_fans import FanCreate
from app.services.workspace_showcase_refresh import (
    prepare_workspace_showcase_refresh,
    refresh_workspace_showcases,
)
from app.services.workspace_showcases import seed_workspace_showcases


@pytest.fixture
def installed(bundle):  # noqa: F811 - imported pytest fixture
    database, original, sources = bundle
    report = seed_workspace_showcases(database, original, apply=True)
    polished = deepcopy(original)
    for case in polished:
        case["portrait"]["summary"] += "重点在亲自尝试之后的判断。"
        case["readers"][0]["profile"] += "先看这次尝试适不适合自己。"
        case["panel"]["reactions"][0]["quote"] = "这次尝试挺有意思，我想先看你怎么开始的。"
        case["panel"]["outcome"]["summary"] += "读者也认可尝试本身的价值。"
    return database, original, polished, sources, report


def test_preparation_is_read_only_and_contains_hashes_not_private_snapshots(installed):
    database, _, polished, _, _ = installed
    before = histories(database)
    plan = prepare_workspace_showcase_refresh(database, polished)
    assert plan["changedRecords"] == 12
    assert sum(map(len, plan["expectedRecords"].values())) == 12
    assert len(plan["expectedSources"]) == len(plan["expectedWorkspaces"]) == 4
    assert all(len(value) == 64 for table in plan["expectedRecords"].values()
               for value in table.values())
    assert plan["expectedReferences"] == []
    assert "真实示例材料" not in json.dumps(plan, ensure_ascii=False)
    assert histories(database) == before


def test_refresh_only_updates_whitelisted_content_and_preserves_frozen_data(installed,
                                                                          monkeypatch):
    database, _, polished, _, _ = installed
    before = histories(database)
    protected = {table: rows(database, table) for table in
                 ("creator_workspaces", "source_materials", "simulated_fans", "topics")}
    monkeypatch.setattr("app.services.workspace_showcase_refresh.utc_now",
                        lambda: "2099-01-01T00:00:00+00:00")
    plan = prepare_workspace_showcase_refresh(database, polished)
    result = refresh_workspace_showcases(database, polished, plan)
    assert result["updatedRecords"] == 12 and result["newRecords"] == 0
    assert {table: rows(database, table) for table in protected} == protected
    allowed = {
        "analysis_runs": {"stage_results_json", "model_metadata_json", "updated_at"},
        "audience_analyses": {"result_json", "diagnostics_json", "model_metadata_json"},
        "simulation_runs": {"input_snapshot_json", "persona_definitions_json",
                            "reaction_results_json", "debate_results_json", "synthesis_json",
                            "model_metadata_json", "updated_at"},
    }
    after = histories(database)
    for table in before:
        assert len(before[table]) == len(after[table]) == 4
        for old, new in zip(before[table], after[table], strict=True):
            assert {key: value for key, value in old.items() if key not in allowed[table]} == {
                key: value for key, value in new.items() if key not in allowed[table]}
            old_meta, new_meta = map(json.loads, (old["model_metadata_json"],
                                                  new["model_metadata_json"]))
            assert all(new_meta[key] == value for key, value in old_meta.items())
            assert new_meta["contentRevision"] == "polish-1"
            assert new_meta["contentHash"] == result["contentHash"]
            if table == "analysis_runs":
                old_stages, new_stages = map(json.loads, (old["stage_results_json"],
                                                          new["stage_results_json"]))
                assert old_stages["profile"]["observations"] == (
                    new_stages["profile"]["observations"]
                )
            if table == "simulation_runs":
                old_input, new_input = map(json.loads, (old["input_snapshot_json"],
                                                        new["input_snapshot_json"]))
                for snapshot in (old_input, new_input):
                    snapshot.pop("audiencePersonas")
                    snapshot.pop("oracleInterview")
                assert old_input == new_input


def test_unmodified_content_and_repeat_refresh_are_true_noops(installed):
    database, original, polished, _, _ = installed
    before = histories(database)
    plan = prepare_workspace_showcase_refresh(database, original)
    assert plan["changedRecords"] == 0
    assert refresh_workspace_showcases(database, original, plan)["updatedRecords"] == 0
    assert histories(database) == before
    refresh_workspace_showcases(database, polished,
                                prepare_workspace_showcase_refresh(database, polished))
    before = histories(database)
    plan = prepare_workspace_showcase_refresh(database, polished)
    assert refresh_workspace_showcases(database, polished, plan)["updatedRecords"] == 0
    assert histories(database) == before
    # The normal seed path never silently refreshes an existing example.
    assert seed_workspace_showcases(database, original, apply=True)["newRecords"] == 0
    assert histories(database) == before


def test_already_applied_plan_cannot_be_replayed(installed):
    database, _, polished, _, _ = installed
    plan = prepare_workspace_showcase_refresh(database, polished)
    refresh_workspace_showcases(database, polished, plan)
    before = histories(database)
    with pytest.raises(ValueError, match="自检查后发生变化"):
        refresh_workspace_showcases(database, polished, plan)
    assert histories(database) == before


@pytest.mark.parametrize("field,value", [("user_notes", "这是我自己的备注"),
                                         ("review_status", "reviewed")])
def test_existing_human_review_blocks_preparation(installed, field, value):
    database, _, polished, _, report = installed
    target = report["cases"][0]["recordIds"]["analysis"]
    with database.transaction() as connection:
        connection.execute(f"UPDATE analysis_runs SET {field}=? WHERE id=?", (value, target))
    before = histories(database)
    with pytest.raises(ValueError, match="人工备注"):
        prepare_workspace_showcase_refresh(database, polished)
    assert histories(database) == before


@pytest.mark.parametrize("change", ["record", "source", "workspace", "content", "review"])
def test_stale_plan_aborts_every_update(installed, change):
    database, _, polished, sources, report = installed
    plan = prepare_workspace_showcase_refresh(database, polished)
    with database.transaction() as connection:
        if change == "record":
            connection.execute("UPDATE audience_analyses SET error='changed' WHERE id=?",
                               (report["cases"][-1]["recordIds"]["audience"],))
        elif change == "source":
            connection.execute("UPDATE source_materials SET name='新的材料名' WHERE id=?",
                               (sources[-1]["id"],))
        elif change == "workspace":
            connection.execute("UPDATE creator_workspaces SET updated_at='2099-01-01T00:00:00Z' "
                               "WHERE id=?", (sources[-1]["workspace_id"],))
        elif change == "review":
            connection.execute("UPDATE simulation_runs SET user_notes='刚写的备注' WHERE id=?",
                               (report["cases"][-1]["recordIds"]["simulation"],))
        else:
            polished[-1]["panel"]["outcome"]["summary"] += "不同的润色内容。"
    before = histories(database)
    with pytest.raises(ValueError):
        refresh_workspace_showcases(database, polished, plan)
    assert histories(database) == before


@pytest.mark.parametrize("when", ["before", "after"])
@pytest.mark.parametrize("asset", ["fan", "topic"])
def test_adopted_assets_prevent_history_replacement(app, installed, when, asset):
    database, _, polished, _, report = installed
    first = report["cases"][0]
    plan = prepare_workspace_showcase_refresh(database, polished) if when == "after" else None
    if asset == "fan":
        app.state.simulated_fan_service.create(first["workspaceId"], FanCreate(
            source_analysis_id=first["recordIds"]["audience"],
            source_group_id=polished[0]["readers"][0]["id"],
        ))
    else:
        from app.services.simulation_topic_ideas import SimulationTopicIdeaService
        SimulationTopicIdeaService(database).adopt(
            first["workspaceId"], first["recordIds"]["simulation"], "idea-1",
        )
    before = histories(database)
    assets = {table: rows(database, table) for table in ("simulated_fans", "topics")}
    with pytest.raises(ValueError, match="其他产品记录引用"):
        if plan is None:
            prepare_workspace_showcase_refresh(database, polished)
        else:
            refresh_workspace_showcases(database, polished, plan)
    assert histories(database) == before
    assert {table: rows(database, table) for table in assets} == assets


@pytest.mark.parametrize("defect", ["quote", "idea_id", "participant_order", "reply_target"])
def test_frozen_quotes_and_identity_relationships_cannot_change(installed, defect):
    database, _, polished, _, _ = installed
    case = polished[-1]
    if defect == "quote":
        case["portrait"]["strengths"][0]["quote"] += "。"
    elif defect == "idea_id":
        case["panel"]["outcome"]["topicIdeas"][0]["id"] = "different-idea"
    elif defect == "participant_order":
        case["panel"]["participant_ids"].reverse()
    else:
        case["panel"]["replies"][0]["to"] = case["panel"]["participant_ids"][1]
    before = histories(database)
    with pytest.raises(ValueError):
        prepare_workspace_showcase_refresh(database, polished)
    assert histories(database) == before


def test_changed_original_material_is_not_reimported_into_history(installed):
    database, _, polished, sources, _ = installed
    with database.transaction() as connection:
        source = dict(connection.execute("SELECT * FROM source_materials WHERE id=?",
                                         (sources[0]["id"],)).fetchone())
        profile = json.loads(source["text_content"])
        profile["notes"][0]["metrics"]["liked"] = 900
        connection.execute("UPDATE source_materials SET text_content=? WHERE id=?",
                           (json.dumps(profile, ensure_ascii=False), source["id"]))
    before = histories(database)
    with pytest.raises(ValueError, match="输入已变化"):
        prepare_workspace_showcase_refresh(database, polished)
    assert histories(database) == before


@pytest.mark.parametrize("field,value", [("provider", "qwen"), ("modelCalled", True)])
def test_refresh_rejects_model_backed_records(installed, field, value):
    database, _, polished, _, report = installed
    target = report["cases"][0]["recordIds"]["audience"]
    with database.transaction() as connection:
        row = connection.execute("SELECT model_metadata_json FROM audience_analyses WHERE id=?",
                                 (target,)).fetchone()
        metadata = json.loads(row[0])
        metadata[field] = value
        connection.execute("UPDATE audience_analyses SET model_metadata_json=? WHERE id=?",
                           (json.dumps(metadata), target))
    with pytest.raises(ValueError, match="未经模型调用"):
        prepare_workspace_showcase_refresh(database, polished)


def test_late_update_error_rolls_back_all_twelve_records(installed):
    database, _, polished, _, report = installed
    target = report["cases"][-1]["recordIds"]["simulation"]
    plan = prepare_workspace_showcase_refresh(database, polished)
    with database.transaction() as connection:
        connection.execute("CREATE TRIGGER reject_refresh BEFORE UPDATE ON simulation_runs "
                           f"WHEN NEW.id='{target}' BEGIN "
                           "SELECT RAISE(ABORT, 'test late failure'); END")
    before = histories(database)
    with pytest.raises(sqlite3.IntegrityError, match="test late failure"):
        refresh_workspace_showcases(database, polished, plan)
    assert histories(database) == before

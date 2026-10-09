"""Curated histories stay inside real accounts and never become automatic assets."""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest
from test_workspace_api import send

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.source_materials import SourceMaterialRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.audience_target import reader_visible_target
from app.services.panel_interviews import PanelInterviewCreate
from app.services.simulated_fans import FanCreate
from app.services.workspace_showcases import ORIGIN, PROFILE_IDENTITIES, seed_workspace_showcases

NOW = "2026-10-01T00:00:00+00:00"
PROTECTED = ("creator_workspaces", "source_materials", "simulated_fans", "topics")


@pytest.fixture
def bundle(app):
    database = app.state.database
    cases, sources = [], []
    with database.transaction() as connection:
        for key, (profile_id, name) in PROFILE_IDENTITIES.items():
            workspace = WorkspaceRepository().create(
                connection, name=f"{name} 的工作区", account_positioning="保留作者定位", now=NOW,
            )
            notes = [{"noteId": f"{key}-{index}", "title": f"{name} 的笔记 {index}",
                      "desc": f"这是 {name} 的真实示例材料 {index}，我愿意先做一个小尝试。",
                      "metrics": {"liked": 8 + index, "collected": 2, "comments": 0,
                                  "shares": 1}, "comments": []} for index in range(2)]
            profile = {"schemaVersion": "xhs-creator-profile/v1",
                       "source": {"profileUrl":
                                  f"https://www.xiaohongshu.com/user/profile/{profile_id}"},
                       "creator": {"displayName": name}, "notes": notes}
            source = SourceMaterialRepository().create_text(
                connection, workspace_id=workspace["id"], material_type="xhs_creator_profile",
                name=f"XHS {name} 创作者主页", content=json.dumps(profile, ensure_ascii=False),
                now=NOW,
            )
            sources.append(source)
            readers = [{"id": f"{key}-reader-{index}", "name": ["先试一步", "保留余地"][index],
                        "profile": ["先看能否做一个小尝试", "在意尝试之后能否退回"][index],
                        "coreConcern": ["怎样开始", "能否中途退出"][index],
                        "interests": ["个人成长"], "expressionStyle": "围绕一个细节追问",
                        "evidence": {"noteId": notes[index]["noteId"],
                                     "quote": "我愿意先做一个小尝试"}} for index in range(2)]
            cases.append({"key": key, "anchor_note_id": notes[0]["noteId"],
                          "note_ids": [note["noteId"] for note in notes],
                          "portrait": {"summary": "用自己的小尝试讲清楚一个选择。",
                                       "keywords": [{"statement": "个人尝试",
                                                     "noteId": notes[0]["noteId"],
                                                     "quote": "我愿意先做一个小尝试"}],
                                       "strengths": [{"statement": "把行动缩小到能开始的一步。",
                                                      "noteId": notes[1]["noteId"],
                                                      "quote": "我愿意先做一个小尝试"}]},
                          "readers": readers,
                          "panel": {"target_note_id": notes[0]["noteId"],
                                    "participant_ids": [reader["id"] for reader in readers],
                                    "reactions": [{"readerId": reader["id"],
                                                   "quote": "这个小尝试我愿意看下去。",
                                                   "understanding": "先试再决定。",
                                                   "concerns": [reader["coreConcern"]]}
                                                  for reader in readers],
                                    "replies": [{"readerId": readers[1]["id"],
                                                 "to": readers[0]["id"],
                                                 "quote": "我更想知道不合适时怎样退出。"}],
                                    "question": "下一篇想先看什么？",
                                    "answers": [{"readerId": reader["id"],
                                                 "quote": reader["coreConcern"]}
                                                for reader in readers],
                                    "outcome": {"summary": "保留尝试过程，再说清停下的条件。",
                                                "directions": ["下次写一个尝试后的决定。"],
                                                "topicIdeas": [{"id": "idea-1",
                                                                "title": "我怎么决定继续或停下",
                                                                "angle": "用一次具体尝试展开"}]}}})
    return database, cases, sources


def rows(database, table):
    with database.read() as connection:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]


def histories(database):
    return {table: rows(database, table)
            for table in ("analysis_runs", "audience_analyses", "simulation_runs")}


def replace_profile(database, source, transform):
    with database.transaction() as connection:
        profile = json.loads(connection.execute("SELECT text_content FROM source_materials "
                                               "WHERE id=?", (source["id"],)).fetchone()[0])
        transform(profile)
        connection.execute("UPDATE source_materials SET text_content=? WHERE id=?",
                           (json.dumps(profile, ensure_ascii=False), source["id"]))


def test_dry_run_is_read_only_and_reports_existing_account_destinations(bundle):
    database, cases, sources = bundle
    before = {table: rows(database, table) for table in (*PROTECTED, *histories(database))}
    result = seed_workspace_showcases(database, cases)
    assert result["mode"] == "dry_run"
    assert result["newRecords"] == 12
    assert [case["sourceMaterialId"] for case in result["cases"]] == [s["id"] for s in sources]
    assert {table: rows(database, table) for table in before} == before


def test_installs_twelve_completed_histories_without_live_calls_or_asset_adoption(app, bundle,
                                                                               monkeypatch):
    database, cases, _ = bundle
    call = AsyncMock(side_effect=AssertionError("No model call is allowed"))
    monkeypatch.setattr(app.state.model_call_service, "call_operation", call)
    before = {table: rows(database, table) for table in PROTECTED}
    report = seed_workspace_showcases(database, cases, apply=True)
    assert report["newRecords"] == 12
    assert {table: rows(database, table) for table in PROTECTED} == before
    for table, records in histories(database).items():
        assert len(records) == 4
        assert {record["status"] for record in records} == {"completed"}
        for record in records:
            metadata = json.loads(record["model_metadata_json"])
            assert metadata["origin"] == ORIGIN
            assert metadata["modelCalled"] is False
            assert metadata["provider"] == "handwritten_oracle"
            snapshot = json.loads(record["input_snapshot_json"])
            assert snapshot["origin"] == ORIGIN
            if table == "analysis_runs":
                stages = json.loads(record["stage_results_json"])
                assert set(stages) == {"profile"}
                portrait = stages["profile"]["profile"]["accountPortrait"]
                assert portrait["strengths"][0]["evidence"][0]["quote"] == "我愿意先做一个小尝试"
                assert portrait["summary"]["evidence"] == portrait["strengths"][0]["evidence"]
                assert stages["profile"]["observations"]["schemaVersion"] == (
                    "xhs-account-observations/v1"
                )
            if table == "simulation_runs":
                assert record["topic_id"] is None and record["draft_id"] is None
                assert snapshot["simulationCategory"] == "published_note"
                encoded = json.dumps(reader_visible_target(snapshot), ensure_ascii=False,
                                     sort_keys=True, separators=(",", ":"), allow_nan=False)
                assert snapshot["targetContentHash"] == hashlib.sha256(encoded.encode()).hexdigest()
                assert snapshot["readerSelection"]["source"] == ORIGIN
                assert snapshot["readerSelection"]["proposedReaders"] == []
                assert snapshot["oracleInterview"]["question"] == "下一篇想先看什么？"
                assert "editorFeedback" not in json.loads(record["synthesis_json"])
    call.assert_not_called()


def test_idempotent_replay_preserves_old_records_and_new_user_notes(bundle):
    database, cases, sources = bundle
    with database.transaction() as connection:
        repository = AnalysisRunRepository()
        original = repository.create(connection, workspace_id=sources[0]["workspace_id"],
                                     workflow_type="account_diagnosis", input_snapshot_json="{}",
                                     idempotency_key="previous-run", now=NOW)
        repository.set_status(connection, run_id=original["id"], status="completed",
                              model_metadata_json="{}", now=NOW)
    previous = rows(database, "analysis_runs")
    first = seed_workspace_showcases(database, cases, apply=True)
    assert next(row for row in rows(database, "analysis_runs")
                if row["id"] == original["id"]) == previous[0]
    with database.transaction() as connection:
        connection.execute("UPDATE analysis_runs SET user_notes='保留这句用户备注' WHERE id=?",
                           (first["cases"][0]["recordIds"]["analysis"],))
    before = histories(database)
    second = seed_workspace_showcases(database, cases, apply=True)
    assert second["newRecords"] == 0
    assert all(case["alreadyInstalled"] for case in second["cases"])
    assert histories(database) == before


@pytest.mark.parametrize("defect", ["missing_note", "wrong_quote", "foreign_evidence",
                                   "missing_anchor", "duplicate_note", "wrong_profile_id",
                                   "wrong_creator", "wrong_domain", "foreign_participant",
                                   "missing_portrait_quote", "wrong_portrait_quote"])
def test_invalid_last_case_rolls_back_the_entire_bundle(bundle, defect):
    database, original, sources = bundle
    cases = deepcopy(original)
    last = cases[-1]
    if defect == "missing_note":
        last["note_ids"].append("missing")
    elif defect == "wrong_quote":
        last["readers"][0]["evidence"]["quote"] = "凭空捏造的引文"
    elif defect == "foreign_evidence":
        last["readers"][0]["evidence"]["noteId"] = cases[0]["note_ids"][0]
    elif defect == "missing_anchor":
        last["anchor_note_id"] = "missing"
    elif defect == "duplicate_note":
        replace_profile(database, sources[-1], lambda p: p["notes"].append(p["notes"][0]))
    elif defect == "wrong_profile_id":
        replace_profile(database, sources[-1], lambda p: p["source"].update(
            profileUrl=f"https://www.xiaohongshu.com/user/profile/{PROFILE_IDENTITIES['ag'][0]}"))
    elif defect == "wrong_creator":
        replace_profile(database, sources[-1],
                        lambda p: p["creator"].update(displayName="同名假账号"))
    elif defect == "wrong_domain":
        replace_profile(database, sources[-1], lambda p: p["source"].update(
            profileUrl=f"https://example.com/user/profile/{PROFILE_IDENTITIES['yiliyu'][0]}"))
    elif defect == "foreign_participant":
        last["panel"]["participant_ids"].append(cases[0]["readers"][0]["id"])
    elif defect == "missing_portrait_quote":
        del last["portrait"]["keywords"][0]["quote"]
    elif defect == "wrong_portrait_quote":
        last["portrait"]["strengths"][0]["quote"] = "用不存在的引用证明优势"
    before = histories(database)
    with pytest.raises(ValueError):
        seed_workspace_showcases(database, cases, apply=True)
    assert histories(database) == before


def test_duplicate_anchor_in_another_account_is_rejected(bundle):
    database, cases, sources = bundle
    first_note = json.loads(sources[0]["text_content"])["notes"][0]
    replace_profile(database, sources[1], lambda p: p["notes"].append(first_note))
    with pytest.raises(ValueError, match="多个档案"):
        seed_workspace_showcases(database, cases, apply=True)
    assert all(not values for values in histories(database).values())


def test_incomplete_existing_bundle_is_not_silently_repaired(bundle):
    database, cases, _ = bundle
    report = seed_workspace_showcases(database, cases, apply=True)
    with database.transaction() as connection:
        connection.execute("DELETE FROM simulation_runs WHERE id=?",
                           (report["cases"][0]["recordIds"]["simulation"],))
    before = histories(database)
    with pytest.raises(ValueError, match="不完整"):
        seed_workspace_showcases(database, cases, apply=True)
    assert histories(database) == before


def test_late_database_error_rolls_back_preceding_inserts(bundle):
    database, cases, _ = bundle
    last_id = seed_workspace_showcases(database, cases)["cases"][-1]["recordIds"]["simulation"]
    with database.transaction() as connection:
        connection.execute("CREATE TRIGGER reject_last_showcase BEFORE INSERT ON simulation_runs "
                           f"WHEN NEW.id='{last_id}' BEGIN "
                           "SELECT RAISE(ABORT, 'test late failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="test late failure"):
        seed_workspace_showcases(database, cases, apply=True)
    assert all(not values for values in histories(database).values())


def test_imported_history_keeps_original_body_after_source_changes(app, bundle):
    database, cases, sources = bundle
    first = seed_workspace_showcases(database, cases, apply=True)["cases"][0]
    before = app.state.simulation_service.get(first["recordIds"]["simulation"])
    replace_profile(database, sources[0], lambda p: p["notes"][0].update(desc="后来的不同正文"))
    after = app.state.simulation_service.get(before.id)
    assert after.input_snapshot == before.input_snapshot
    assert after.input_snapshot["topic"]["body"] != "后来的不同正文"


def test_summaries_detail_manual_adoption_and_interview_guard(app, bundle):
    database, cases, _ = bundle
    report = seed_workspace_showcases(database, cases, apply=True)
    first, second = report["cases"][:2]
    workspace_id, ids = first["workspaceId"], first["recordIds"]
    for kind, route in (("analysis", "analysis-runs"), ("audience", "audience-analyses"),
                        ("simulation", "simulation-runs")):
        listing = send(app, "GET", f"/api/workspaces/{workspace_id}/{route}")
        assert listing.status_code == 200, listing.text
        assert listing.json()[0]["origin"] == ORIGIN
        response = send(app, "GET", f"/api/{route}/{ids[kind]}")
        assert response.status_code == 200, response.text
        assert response.json()["origin"] == ORIGIN
    simulation = app.state.simulation_service.get(ids["simulation"])
    assert simulation.source_material_id == first["sourceMaterialId"]
    assert simulation.note_id == cases[0]["panel"]["target_note_id"]
    group = cases[0]["readers"][0]["id"]
    fan = app.state.simulated_fan_service.create(workspace_id, FanCreate(
        source_analysis_id=ids["audience"], source_group_id=group,
    ))
    assert fan.workspace_id == workspace_id and fan.source_group_id == group
    with pytest.raises(ValidationError):
        app.state.simulated_fan_service.create(second["workspaceId"], FanCreate(
            source_analysis_id=ids["audience"], source_group_id=group,
        ))
    endpoint = f"/api/workspaces/{workspace_id}/simulation-runs/{ids['simulation']}"
    response = send(app, "POST", endpoint + "/topic-ideas/idea-1/adopt")
    assert response.status_code == 200, response.text
    assert response.json()["workspaceId"] == workspace_id
    assert len(rows(database, "topics")) == 1
    assert send(app, "POST", endpoint + "/topic-ideas/idea-1/adopt").json() == response.json()
    question = PanelInterviewCreate(request_key="oracle-question", question="能再解释一下吗？")
    with pytest.raises(ValidationError, match="预写示例"):
        app.state.panel_interview_service.create(workspace_id, ids["simulation"], question)
    assert rows(database, "panel_interviews") == []
    assert app.state.panel_interview_service.list(workspace_id, ids["simulation"]) == []


def test_interview_guard_also_checks_metadata_if_snapshot_marker_is_absent(app, bundle):
    database, cases, _ = bundle
    first = seed_workspace_showcases(database, cases, apply=True)["cases"][0]
    simulation_id = first["recordIds"]["simulation"]
    with database.transaction() as connection:
        connection.execute("UPDATE simulation_runs SET input_snapshot_json="
                           "json_remove(input_snapshot_json,'$.origin') WHERE id=?",
                           (simulation_id,))
    with pytest.raises(ValidationError, match="预写示例"):
        app.state.panel_interview_service.create(first["workspaceId"], simulation_id,
            PanelInterviewCreate(request_key="oracle-question", question="再解释一下？"))


def load_cli():
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_workspace_showcases.py"
    spec = importlib.util.spec_from_file_location("seed_workspace_showcases_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_requires_apply_and_writes_private_verified_backup(bundle, monkeypatch, tmp_path):
    database, cases, _ = bundle
    script = load_cli()
    monkeypatch.setattr(script, "ROOT", tmp_path)
    content = ModuleType("app.services.workspace_showcase_content")
    content.WORKSPACE_SHOWCASES = cases
    monkeypatch.setitem(sys.modules, content.__name__, content)
    report = script.main(["--database", str(database.path)])
    assert report["mode"] == "dry_run"
    assert not (tmp_path / "data" / "backups").exists()
    assert all(not values for values in histories(database).values())
    report = script.main(["--database", str(database.path), "--apply"])
    backup = Path(report["backup"])
    assert backup.is_relative_to(tmp_path / "data" / "backups")
    assert backup.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT count(*) FROM simulation_runs").fetchone()[0] == 0
    assert report["newRecords"] == 12
    again = script.main(["--database", str(database.path), "--apply"])
    assert again["newRecords"] == 0 and "backup" not in again
    assert len(list(backup.parent.iterdir())) == 1


def test_missing_database_is_never_created(tmp_path):
    path = tmp_path / "absent.sqlite3"
    with pytest.raises(ValueError, match="数据库不存在"):
        seed_workspace_showcases(SQLiteDatabase(path), [])
    assert not path.exists()


def test_cli_backup_failure_prevents_writes(bundle, monkeypatch):
    database, cases, _ = bundle
    script = load_cli()
    content = ModuleType("app.services.workspace_showcase_content")
    content.WORKSPACE_SHOWCASES = cases
    monkeypatch.setitem(sys.modules, content.__name__, content)

    def fail_backup(_):
        raise ValueError("备份失败")

    monkeypatch.setattr(script, "backup_database", fail_backup)
    with pytest.raises(ValueError, match="备份失败"):
        script.main(["--database", str(database.path), "--apply"])
    assert all(not values for values in histories(database).values())

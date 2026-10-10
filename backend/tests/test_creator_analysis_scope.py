import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, send

from app.errors import ValidationError
from app.services.audience_analyses import AudienceAnalysisCreate
from app.services.creator_analysis_scope import scope_creator_profile


def profile():
    return {
        "schemaVersion": "xhs-creator-profile/v1",
        "creator": {"displayName": "测试账号", "profileText": "不应进入局部分析的全量总结"},
        "notes": [
            {"noteId": str(index), "title": f"笔记{index}", "desc": f"正文{index}",
             "publishedAt": (datetime(2026, 9, 23, tzinfo=UTC) - timedelta(days=index)).isoformat(),
             "comments": [{"content": f"评论{index}"}]}
            for index in range(15)
        ],
    }


def test_recent_scope_keeps_exactly_ten_and_does_not_mutate_source():
    original = profile()
    scoped, metadata = scope_creator_profile(original, "recent_10")
    assert len(original["notes"]) == 15
    assert len(scoped["notes"]) == 10
    assert metadata["selectedNoteIds"] == [str(index) for index in range(10)]
    assert "profileText" not in scoped["creator"]


def test_date_scope_handles_seconds_milliseconds_unknown_dates_and_empty_range():
    now = datetime(2026, 9, 23, tzinfo=UTC)
    raw = profile()
    raw["notes"][0]["publishedAt"] = now.timestamp()
    raw["notes"][1]["publishedAt"] = now.timestamp() * 1000
    raw["notes"][2]["publishedAt"] = "未知"
    scoped, metadata = scope_creator_profile(raw, "last_7_days", now=now)
    assert len(scoped["notes"]) == 7
    assert metadata["unknownDateCount"] == 1
    with pytest.raises(ValidationError, match="没有笔记"):
        scope_creator_profile(raw, "last_7_days", now=now + timedelta(days=60))


def test_scoped_api_snapshot_and_context_exclude_unselected_evidence(app: FastAPI):
    workspace = create_workspace(app)
    material = create_text_material(
        app, workspace["id"], "xhs_creator_profile", json.dumps(profile(), ensure_ascii=False)
    )
    create_text_material(app, workspace["id"], "historical_posts", "其他材料不能混入范围")
    response = send(app, "POST", f"/api/workspaces/{workspace['id']}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": material["id"],
        "analysisScope": "recent_10", "mode": "demo",
    })
    assert response.status_code == 201
    snapshot = response.json()["inputSnapshot"]
    assert snapshot["analysisRange"]["selectedNoteCount"] == 10
    assert "正文14" not in json.dumps(snapshot, ensure_ascii=False)
    assert "其他材料不能混入范围" not in json.dumps(snapshot, ensure_ascii=False)
    assert snapshot["contextPack"]["scope"] == "selected_evidence"
    assert "评论0" in snapshot["comments"]["content"]


def test_scope_does_not_allow_another_accounts_material(app: FastAPI):
    first, second = create_workspace(app), create_workspace(app)
    material = create_text_material(app, first["id"], "xhs_creator_profile", json.dumps(profile()))
    response = send(app, "POST", f"/api/workspaces/{second['id']}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": material["id"],
        "analysisScope": "recent_10",
    })
    assert response.status_code == 422


def test_manual_selection_uses_exact_notes_and_does_not_mutate_source():
    raw = profile()
    scoped, metadata = scope_creator_profile(raw, "all", selected_note_ids=["14", "2"])
    assert metadata["scope"] == "custom"
    assert metadata["selectedNoteIds"] == ["2", "14"]
    assert [n["title"] for n in scoped["notes"]] == ["笔记2", "笔记14"]
    assert "profileText" not in scoped["creator"]
    assert len(raw["notes"]) == 15
    assert "profileText" in raw["creator"]


@pytest.mark.parametrize("ids", [[], ["missing"], ["1", "1"], ["1", "other-account-note"]])
def test_invalid_manual_selection_rejected(ids):
    with pytest.raises(ValidationError, match="所选笔记无效"):
        scope_creator_profile(profile(), "all", selected_note_ids=ids)


def test_legacy_missing_ids_match_browser_fallback_and_duplicate_source_ids_rejected():
    raw = profile()
    raw["notes"][2].pop("noteId")
    scoped, metadata = scope_creator_profile(raw, "all", selected_note_ids=["2"])
    assert metadata["selectedNoteIds"] == ["2"]
    assert scoped["notes"][0]["title"] == "笔记2"
    raw["notes"][3]["noteId"] = "2"
    with pytest.raises(ValidationError):
        scope_creator_profile(raw, "all", selected_note_ids=["2"])


def test_manual_api_selection_persists_only_selected_evidence(app):
    wid = create_workspace(app)["id"]
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(profile()))
    payload = {"workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": source["id"],
               "analysisScope": "all", "selectedNoteIds": ["2", "14"], "mode": "demo"}
    response = send(app, "POST", f"/api/workspaces/{wid}/analysis-runs", json=payload)
    assert response.status_code == 201
    run = response.json()
    snapshot = run["inputSnapshot"]
    assert snapshot["analysisRange"]["scope"] == "custom"
    assert snapshot["analysisRange"]["selectedNoteIds"] == ["2", "14"]
    assert snapshot["contextPack"]["scope"] == "selected_evidence"
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "正文14" in serialized and "评论14" in serialized
    assert "正文0" not in serialized and "评论0" not in serialized
    assert "全量总结" not in serialized
    reopened = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert reopened["inputSnapshot"] == snapshot
    for ids in [[], ["foreign"], ["2", "2"]]:
        assert send(app, "POST", f"/api/workspaces/{wid}/analysis-runs", json={
            **payload, "selectedNoteIds": ids,
        }).status_code == 422


def test_metric_rankings_keep_zero_and_partial_values_and_deterministic_ties():
    raw = {"notes": [
        {"noteId": "missing", "metrics": {}},
        {"noteId": "bad", "metrics": {"liked": -1, "shares": True}},
        {"noteId": "zero", "metrics": {"liked": 0}},
        {"noteId": "b", "publishedAt": "2026-10-02", "metrics": {"liked": 8}},
        {"noteId": "a", "publishedAt": "2026-10-02", "metrics": {"liked": 8}},
        {"noteId": "newer", "publishedAt": "2026-10-03", "metrics": {"liked": 8}},
        {"noteId": "complete", "metrics": {"liked": 2, "collected": 3, "comments": 4, "shares": 5}},
    ]}
    _, likes = scope_creator_profile(raw, "most_liked_10")
    assert likes["selectedNoteIds"] == ["newer", "a", "b", "complete", "zero"]
    _, interactions = scope_creator_profile(raw, "most_engaged_10")
    assert interactions["selectedNoteIds"] == ["complete", "newer", "a", "b", "zero"]
    observations = interactions["ranking"]["observations"]
    assert observations[0]["value"] == 14
    assert observations[0]["missingMetrics"] == []
    assert observations[1]["includedMetrics"] == ["liked"]
    assert observations[1]["missingMetrics"] == ["collected", "comments", "shares"]
    assert len(raw["notes"]) == 7


def test_legacy_rankings_have_the_same_stable_fallback_ids_as_browser():
    raw = {"notes": [{"title": str(i), "metrics": {"liked": 1}} for i in range(12)]}
    _, metadata = scope_creator_profile(raw, "most_liked_10")
    assert metadata["selectedNoteIds"] == ["0", "1", "10", "11", "2", "3", "4", "5", "6", "7"]
    assert "noteId" not in raw["notes"][0]


def test_explicit_top_n_selection_keeps_full_set_not_recomputed_ten(app, monkeypatch):
    wid = create_workspace(app)["id"]
    raw = profile()
    for index, note in enumerate(raw["notes"]):
        note["metrics"] = {"liked": index}
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(raw))
    service = app.state.audience_analysis_service
    monkeypatch.setattr(service, "_enqueue", lambda _: None)
    run = service.create(wid, AudienceAnalysisCreate(
        source_material_id=source["id"], scope="selected_notes", selection_scope="most_liked_10",
        selected_note_ids=[str(index) for index in range(12)],
    ))
    snapshot = run.input_snapshot
    assert snapshot["scope"]["scope"] == "custom"
    assert snapshot["scope"]["selectedNoteCount"] == 12
    assert snapshot["scope"]["selectionMethod"] == "explicit_ids"
    assert snapshot["scope"]["ranking"]["basis"] == "recorded_likes"
    assert len(snapshot["notes"]) == 12
    assert "正文14" not in json.dumps(snapshot, ensure_ascii=False)
    assert "全量总结" not in json.dumps(snapshot, ensure_ascii=False)
    assert service.get(run.id).input_snapshot == snapshot


def test_audience_explicit_discriminator_requires_selected_ids():
    for ids in (None, []):
        with pytest.raises(ValueError):
            AudienceAnalysisCreate(source_material_id="p", scope="selected_notes",
                                   selected_note_ids=ids)


@pytest.mark.parametrize("ids", [[], ["foreign"], ["2", "2"]])
def test_audience_api_rejects_invalid_explicit_ids_before_execution(app, monkeypatch, ids):
    wid = create_workspace(app)["id"]
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(profile()))
    called = []
    monkeypatch.setattr(app.state.audience_analysis_service, "_enqueue", called.append)
    response = send(app, "POST", f"/api/workspaces/{wid}/audience-analyses", json={
        "sourceMaterialId": source["id"], "scope": "selected_notes", "selectedNoteIds": ids,
    })
    assert response.status_code == 422
    assert not called


@pytest.mark.parametrize("active_status", ["pending", "running"])
def test_active_audience_only_reuses_the_same_source_and_exact_note_set(
    app, monkeypatch, active_status,
):
    wid = create_workspace(app)["id"]
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(profile()))
    other = create_text_material(app, wid, "xhs_creator_profile", json.dumps(profile()))
    enqueued = []
    service = app.state.audience_analysis_service
    monkeypatch.setattr(service, "_enqueue", enqueued.append)
    path = f"/api/workspaces/{wid}/audience-analyses"
    payload = {"sourceMaterialId": source["id"], "scope": "selected_notes",
               "selectedNoteIds": ["2", "14"]}
    first = send(app, "POST", path, json=payload)
    assert first.status_code == 202
    run_id = first.json()["id"]
    snapshot = first.json()["inputSnapshot"]
    with service.database.transaction() as c:
        c.execute("UPDATE audience_analyses SET status=? WHERE id=?", (active_status, run_id))

    # A second tab choosing different notes must not receive the first tab's run.
    conflict = send(app, "POST", path, json={**payload, "selectedNoteIds": ["1"]})
    assert conflict.status_code == 409
    assert "其他笔记范围" in conflict.json()["detail"]
    assert send(app, "POST", path, json={
        **payload, "sourceMaterialId": other["id"],
    }).status_code == 409
    # Validate the new request even while an old run is active.
    assert send(app, "POST", path, json={
        **payload, "selectedNoteIds": ["foreign"],
    }).status_code == 422
    assert send(app, "POST", path, json={
        **payload, "selectedNoteIds": ["2", "2"],
    }).status_code == 422
    same = send(app, "POST", path, json={**payload, "selectedNoteIds": ["14", "2"]})
    assert same.status_code == 202
    assert same.json()["id"] == run_id
    assert same.json()["inputSnapshot"] == snapshot
    assert enqueued == [run_id]
    with service.database.transaction() as c:
        assert c.execute("SELECT COUNT(*) FROM audience_analyses").fetchone()[0] == 1


@pytest.mark.parametrize("snapshot,can_reuse", [
    ({"scope": {"scope": "recent_10", "selectedNoteCount": 2},
      "notes": [{"noteId": "2"}, {"noteId": "14"}]}, True),
    ({"scope": {"scope": "all", "selectedNoteIds": ["2", "14"]}}, True),
    ({"scope": {"scope": "recent_10", "selectedNoteCount": 2},
      "notes": [{"title": "旧笔记"}]}, False),
    ({"scope": {"selectedNoteIds": ["2", "14"]}, "notes": [{"noteId": "1"}]}, False),
])
def test_legacy_active_audience_reuse_uses_only_frozen_stable_ids(
    app, monkeypatch, snapshot, can_reuse,
):
    wid = create_workspace(app)["id"]
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(profile()))
    service = app.state.audience_analysis_service
    enqueued = []
    monkeypatch.setattr(service, "_enqueue", enqueued.append)
    with service.database.transaction() as c:
        c.execute(
            "INSERT INTO audience_analyses(id,workspace_id,source_material_id,status,"
            "input_snapshot_json,created_at) VALUES('legacy-active',?,?,'running',?,'now')",
            (wid, source["id"], json.dumps(snapshot)),
        )
    result = send(app, "POST", f"/api/workspaces/{wid}/audience-analyses", json={
        "sourceMaterialId": source["id"], "scope": "selected_notes",
        "selectedNoteIds": ["2", "14"],
    })
    assert result.status_code == (202 if can_reuse else 409)
    if can_reuse:
        assert result.json()["id"] == "legacy-active"
        assert result.json()["inputSnapshot"] == snapshot
    assert not enqueued

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, send

from app.errors import ValidationError
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

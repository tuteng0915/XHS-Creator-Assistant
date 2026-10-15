import json

import pytest
from test_analysis_topics_api import create_text_material
from test_creator_analysis_scope import profile
from test_workspace_api import create_workspace, send

from app.services.analysis_runs import AnalysisRunService


@pytest.mark.parametrize(("snapshot", "expected"), [
    ({"analysisRange": {"selectedNoteCount": 2}, "xhsCreatorProfile": {"noteCount": 15}}, 2),
    ({"xhsCreatorProfile": {"notes": [{"noteId": "n1"}, {"noteId": "n2"}], "noteCount": 15}}, 2),
    ({"xhsCreatorProfile": {"noteCount": 8}}, 8),
    ({"xhsCreatorProfile": {"notes": []}}, 0),
    ({"historicalPosts": {"content": "第一篇\n第二篇"}}, None),
    ({}, None),
    ({"analysisRange": {"selectedNoteCount": True}, "xhsCreatorProfile": {"noteCount": -1}}, None),
    ({"analysisRange": {"selectedNoteCount": "3"}, "xhsCreatorProfile": {"notes": "原文"}}, None),
])
def test_note_count_uses_only_explicit_frozen_input(snapshot, expected):
    assert AnalysisRunService._snapshot_note_count(snapshot) == expected


def test_history_count_survives_source_replacement_without_detail_requests(app):
    workspace_id = create_workspace(app)["id"]
    source = create_text_material(app, workspace_id, "xhs_creator_profile", json.dumps(profile()))
    response = send(app, "POST", f"/api/workspaces/{workspace_id}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": source["id"],
        "analysisScope": "all", "selectedNoteIds": ["2", "14"], "mode": "demo",
    })
    assert response.status_code == 201
    created = response.json()
    assert created["noteCount"] == 2
    replacement = profile()
    replacement["notes"] = replacement["notes"][:1]
    updated = send(app, "PATCH", f"/api/source-materials/{source['id']}", json={
        "content": json.dumps(replacement), "expectedUpdatedAt": source["updatedAt"],
    })
    assert updated.status_code == 200
    listed = send(app, "GET", f"/api/workspaces/{workspace_id}/analysis-runs")
    assert listed.status_code == 200
    assert listed.json()[0]["noteCount"] == 2
    assert "inputSnapshot" not in listed.json()[0]
    reopened = send(app, "GET", f"/api/analysis-runs/{created['id']}").json()
    assert reopened["noteCount"] == 2
    assert reopened["inputSnapshot"] == created["inputSnapshot"]


def test_legacy_text_history_does_not_get_the_current_account_note_count(app):
    workspace_id = create_workspace(app)["id"]
    historical = create_text_material(app, workspace_id, "historical_posts", "已有一段旧笔记正文")
    comments = create_text_material(app, workspace_id, "comments", "喜欢这个角度")
    created = send(app, "POST", f"/api/workspaces/{workspace_id}/analysis-runs", json={
        "workflowType": "account_diagnosis", "historicalPostsInputAssetId": historical["id"],
        "commentsInputAssetId": comments["id"], "mode": "demo",
    })
    assert created.status_code == 201
    create_text_material(app, workspace_id, "xhs_creator_profile", json.dumps(profile()))
    assert created.json()["noteCount"] is None
    listed = send(app, "GET", f"/api/workspaces/{workspace_id}/analysis-runs").json()
    assert listed[0]["noteCount"] is None

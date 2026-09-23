import json

from test_workspace_api import create_workspace, send


def test_same_title_notes_keep_distinct_covers_across_reimport(app):
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "creator": {"displayName": "测试账号"},
        "notes": [
            {"noteId": note_id, "title": "本周记录", "desc": f"正文 {note_id}",
             "cover": {"relativePath": f"images/{note_id}.jpg"}}
            for note_id in ("first", "second")
        ],
    }
    files = [("profile", ("profile.json", json.dumps(payload).encode(), "application/json"))]
    for note_id in ("first", "second"):
        files.extend([
            ("files", (f"{note_id}.jpg", note_id.encode(), "image/jpeg")),
            ("relativePaths", (None, f"images/{note_id}.jpg")),
        ])
    path = f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package"
    first = send(app, "POST", path, files=files)
    assert first.status_code == 201
    assets = first.json()["mediaAssets"]
    assert len({asset["id"] for asset in assets}) == 2
    assert [asset["userNotes"] for asset in assets] == ["正文 first", "正文 second"]
    repeated = send(app, "POST", path, files=files)
    assert repeated.status_code == 201
    assert [asset["id"] for asset in repeated.json()["mediaAssets"]] == [
        asset["id"] for asset in assets
    ]

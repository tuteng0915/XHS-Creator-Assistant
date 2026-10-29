import json

from test_workspace_api import create_workspace, send

from app.models import AnalysisRunCreate, WorkflowType


def test_same_title_notes_keep_distinct_covers_across_reimport(app):
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "creator": {"displayName": "测试账号"},
        "notes": [
            {
                "noteId": note_id,
                "title": "本周记录",
                "desc": f"正文 {note_id}",
                "cover": {"relativePath": f"images/{note_id}.jpg"},
            }
            for note_id in ("first", "second")
        ],
    }
    files = [("profile", ("profile.json", json.dumps(payload).encode(), "application/json"))]
    for note_id in ("first", "second"):
        files.extend(
            [
                ("files", (f"{note_id}.jpg", note_id.encode(), "image/jpeg")),
                ("relativePaths", (None, f"images/{note_id}.jpg")),
            ]
        )
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


def test_package_registers_all_pages_and_freezes_only_current_images(app):
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "creator": {"displayName": "图文"},
        "notes": [{"noteId": "n", "title": "多页笔记", "desc": "引言"}],
    }

    def upload(second):
        files = [("profile", ("profile.json", json.dumps(payload).encode(), "application/json"))]
        for index in (0, 1, 10, 2):
            files.extend(
                [
                    (
                        "files",
                        (
                            f"{index}.jpg",
                            second if index == 1 else str(index).encode(),
                            "image/jpeg",
                        ),
                    ),
                    ("relativePaths", (None, f"images/n/{index}.jpg")),
                ]
            )
        response = send(
            app,
            "POST",
            f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
            files=files,
        )
        assert response.status_code == 201
        return response.json()

    first = upload(b"second")
    assert len(first["mediaAssets"]) == 4
    assert [a["metadata"]["relativePath"] for a in first["mediaAssets"]] == [
        "images/n/0.jpg",
        "images/n/1.jpg",
        "images/n/2.jpg",
        "images/n/10.jpg",
    ]
    repeated = upload(b"second")
    assert [a["id"] for a in first["mediaAssets"]] == [a["id"] for a in repeated["mediaAssets"]]
    changed = upload(b"new second")
    assets = changed["mediaAssets"]
    assert assets[1]["id"] != first["mediaAssets"][1]["id"]
    with app.state.analysis_service.database.read() as c:
        material = c.execute(
            "SELECT id FROM source_materials WHERE workspace_id=? AND type='xhs_creator_profile'",
            (workspace["id"],),
        ).fetchone()
    run = app.state.analysis_service.create(
        workspace["id"],
        AnalysisRunCreate(
            workflow_type=WorkflowType.ACCOUNT_DIAGNOSIS,
            xhs_creator_profile_input_asset_id=material["id"],
            mode="demo",
        ),
    )
    assert [image["assetId"] for image in run.input_snapshot["diagnosisImages"]] == [
        a["id"] for a in assets
    ]

import json

import pytest
from fastapi import FastAPI
from test_workspace_api import create_workspace, send


def profile_with_notes(*notes: dict, display_name: str = "评论回归账号") -> dict:
    return {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {"platform": "xiaohongshu"},
        "creator": {"displayName": display_name},
        "notes": list(notes),
    }


def note_with_comments() -> dict:
    return {
        "noteId": "note-original",
        "title": "申请季复盘",
        "desc": "原正文",
        "metrics": {"liked": 10, "comments": 8},
        "comments": [
            {
                "commentId": "comment-original",
                "authorHash": "0123456789abcdef",
                "content": "请展开介绍准备过程。",
                "likeCount": 3,
                "subCommentCount": 2,
                "createTime": 1700000000,
            }
        ],
    }


def import_package(
    app: FastAPI, workspace_id: str, payload: dict, *, data: dict | None = None
) -> dict:
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/input-assets/xhs-import-package",
        data=data,
        files=[
            (
                "profile",
                (
                    "profile.json",
                    json.dumps(payload, ensure_ascii=False).encode(),
                    "application/json",
                ),
            )
        ],
    )
    assert response.status_code == 201, response.text
    return response.json()["inputAsset"]


@pytest.mark.parametrize("comment_state", ["missing", "empty", "null"])
def test_package_refresh_preserves_comments_when_none_were_returned(
    app: FastAPI, comment_state: str
) -> None:
    workspace = create_workspace(app)
    note = note_with_comments()
    first = import_package(app, workspace["id"], profile_with_notes(note))
    old_comments = json.loads(first["content"])["notes"][0]["comments"]

    refreshed_note = {
        "noteId": note["noteId"],
        "title": "申请季复盘（更新）",
        "desc": "更新后的正文",
        "metrics": {"liked": 21, "comments": 12},
    }
    if comment_state != "missing":
        refreshed_note["comments"] = [] if comment_state == "empty" else None
    second = import_package(app, workspace["id"], profile_with_notes(refreshed_note))

    assert second["id"] == first["id"]
    stored_note = json.loads(second["content"])["notes"][0]
    assert stored_note["noteId"] == note["noteId"]
    assert stored_note["title"] == refreshed_note["title"]
    assert stored_note["desc"] == refreshed_note["desc"]
    assert stored_note["metrics"] == {"liked": 21, "comments": 12}
    assert stored_note["comments"] == old_comments
    assert stored_note["comments"][0]["authorHash"] == "0123456789abcdef"

    retrieved = send(app, "GET", f"/api/input-assets/{first['id']}")
    assert retrieved.status_code == 200
    assert json.loads(retrieved.json()["content"])["notes"][0] == stored_note
    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/input-assets?type=xhs_creator_profile",
    )
    assert listed.status_code == 200
    assert [asset["id"] for asset in listed.json()] == [first["id"]]


def test_package_refresh_keeps_nonempty_comment_replacement_semantics(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    note = note_with_comments()
    first = import_package(app, workspace["id"], profile_with_notes(note))
    replacement_comment = {
        "commentId": "comment-new",
        "authorHash": "fedcba9876543210",
        "content": "这是这次实际返回的评论。",
        "likeCount": 5,
        "subCommentCount": 1,
        "createTime": 1700000100,
    }
    note["comments"] = [replacement_comment]

    second = import_package(app, workspace["id"], profile_with_notes(note))

    assert second["id"] == first["id"]
    assert json.loads(second["content"])["notes"][0]["comments"] == [replacement_comment]


def test_package_refresh_does_not_borrow_another_notes_comments(app: FastAPI) -> None:
    workspace = create_workspace(app)
    old_note = note_with_comments()
    first = import_package(app, workspace["id"], profile_with_notes(old_note))
    new_note = {"noteId": "note-new", "title": old_note["title"], "comments": []}
    refreshed_old_note = {"noteId": old_note["noteId"], "title": old_note["title"]}

    second = import_package(
        app, workspace["id"], profile_with_notes(new_note, refreshed_old_note)
    )

    assert second["id"] == first["id"]
    notes = json.loads(second["content"])["notes"]
    assert notes[0]["noteId"] == "note-new"
    assert notes[0]["comments"] == []
    assert notes[1]["comments"] == old_note["comments"]


@pytest.mark.parametrize(
    "data", [{"saveAsNew": "true"}, {"name": "XHS 评论回归账号 创作者主页"}]
)
def test_new_package_material_does_not_inherit_existing_comments(
    app: FastAPI, data: dict
) -> None:
    workspace = create_workspace(app)
    note = note_with_comments()
    first = import_package(app, workspace["id"], profile_with_notes(note))
    note["comments"] = []

    second = import_package(app, workspace["id"], profile_with_notes(note), data=data)

    assert second["id"] != first["id"]
    assert json.loads(second["content"])["notes"][0]["comments"] == []
    retrieved = send(app, "GET", f"/api/input-assets/{first['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["content"] == first["content"]


def test_different_creator_material_does_not_inherit_existing_comments(app: FastAPI) -> None:
    workspace = create_workspace(app)
    note = note_with_comments()
    first = import_package(app, workspace["id"], profile_with_notes(note))
    note["comments"] = []

    second = import_package(
        app, workspace["id"], profile_with_notes(note, display_name="另一账号")
    )

    assert second["id"] != first["id"]
    assert json.loads(second["content"])["notes"][0]["comments"] == []


@pytest.mark.parametrize("url_key", ["profileUrl", "sourceUrl"])
def test_package_refresh_rejects_conflicting_account_urls_without_overwriting(
    app: FastAPI, url_key: str
) -> None:
    workspace = create_workspace(app)
    payload = profile_with_notes(note_with_comments())
    payload["source"][url_key] = "https://www.xiaohongshu.com/user/profile/original"
    first = import_package(app, workspace["id"], payload)
    payload["source"][url_key] = "https://www.xiaohongshu.com/user/profile/different"
    payload["notes"][0]["comments"] = []

    rejected = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        files=[
            ("profile", ("profile.json", json.dumps(payload).encode(), "application/json"))
        ],
    )

    assert rejected.status_code == 422
    assert "另一个账号" in rejected.text
    retrieved = send(app, "GET", f"/api/input-assets/{first['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json() == first


def test_package_refresh_does_not_match_parser_generated_positional_note_ids(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    old_note = note_with_comments()
    old_note.pop("noteId")
    first = import_package(app, workspace["id"], profile_with_notes(old_note))
    assert json.loads(first["content"])["notes"][0]["noteId"] == "note-1"

    second = import_package(
        app, workspace["id"], profile_with_notes({"title": "完全不同的笔记", "comments": []})
    )

    assert second["id"] == first["id"]
    stored_note = json.loads(second["content"])["notes"][0]
    assert stored_note["noteId"] == "note-1"
    assert stored_note["comments"] == []


@pytest.mark.parametrize("old_observed_at", [None, "2026-10-01T08:00:00Z"])
def test_package_refresh_retains_comment_author_context_and_observation_time(
    app: FastAPI, old_observed_at: str | None
) -> None:
    workspace = create_workspace(app)
    old_note = note_with_comments()
    old_note["authorHash"] = "0123456789abcdef"
    if old_observed_at is not None:
        old_note["commentsObservedAt"] = old_observed_at
    first = import_package(app, workspace["id"], profile_with_notes(old_note))
    incoming_note = {
        "noteId": old_note["noteId"],
        "title": old_note["title"],
        "comments": [],
        "commentsObservedAt": "2026-10-10T08:00:00Z",
    }

    second = import_package(app, workspace["id"], profile_with_notes(incoming_note))

    assert second["id"] == first["id"]
    stored_note = json.loads(second["content"])["notes"][0]
    assert stored_note["authorHash"] == old_note["authorHash"]
    assert stored_note["comments"] == old_note["comments"]
    if old_observed_at is None:
        assert "commentsObservedAt" not in stored_note
    else:
        assert stored_note["commentsObservedAt"] == old_observed_at


@pytest.mark.parametrize(
    ("camel_key", "snake_key"),
    [("likeCount", "like_count"), ("subCommentCount", "sub_comment_count")],
)
@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"camel": 0}, 0),
        ({"snake": 0}, 0),
        ({"camel": 0, "snake": 7}, 0),
        ({"camel": None, "snake": 0}, 0),
        ({"camel": None, "snake": 7}, 7),
        ({"camel": 4, "snake": 0}, 4),
    ],
)
def test_package_comment_counts_preserve_zero_and_fall_back_only_from_none(
    app: FastAPI, camel_key: str, snake_key: str, values: dict, expected: int
) -> None:
    workspace = create_workspace(app)
    comment = {"commentId": "count-comment", "content": "评论计数样本"}
    for alias, value in values.items():
        comment[camel_key if alias == "camel" else snake_key] = value
    note = {"noteId": "count-note", "title": "计数回归", "comments": [comment]}

    material = import_package(app, workspace["id"], profile_with_notes(note))

    stored_comment = json.loads(material["content"])["notes"][0]["comments"][0]
    assert stored_comment[camel_key] == expected

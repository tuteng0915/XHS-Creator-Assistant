"""The comment preview selects tags from a library and never writes to the workspace."""
from unittest.mock import AsyncMock

import pytest
from test_creator_experience import profile
from test_workspace_api import create_workspace, send

from app.errors import ValidationError
from app.models import ModelCallResponse, ModelOperation
from app.services.comment_preview import (
    TAG_LIBRARY,
    comment_preview_prompt,
    validated_comments,
)
from app.services.model_calls import ModelCallService


def target(app):
    wid = create_workspace(app)["id"]
    return wid, profile(app, wid)


def url(wid):
    return f"/api/workspaces/{wid}/comment-previews"


def test_library_occasions_only_reference_known_reactions():
    names = {item["name"] for item in TAG_LIBRARY["reactions"]}
    assert 15 <= len(names) <= 20
    for occasion in TAG_LIBRARY["occasions"]:
        assert set(occasion["typicalReactions"]) <= names


def test_demo_preview_reads_the_note_without_model_or_writes(app):
    wid, source = target(app)
    before = send(app, "GET", f"/api/source-materials/{source['id']}").json()
    app.state.comment_preview_service.model_calls.call_operation = AsyncMock()
    response = send(app, "POST", url(wid), json={"sourceMaterialId": source["id"], "noteId": "0"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "demo" and body["comments"][0]["tag"] == "夸赞"
    app.state.comment_preview_service.model_calls.call_operation.assert_not_awaited()
    assert send(app, "GET", f"/api/source-materials/{source['id']}").json() == before


def test_live_preview_sends_one_call_and_marks_on_the_spot_tags(app):
    wid, source = target(app)
    call = AsyncMock(return_value=ModelCallResponse(model_metadata={}, output={"preview": {
        "occasion": "招聘内推", "occasionReason": "在招实习生", "comments": [
            {"tag": "求资源", "detail": "投递方式", "target": "缺失信息", "reader": "陌生人",
             "length": "一句话", "text": "怎么投呀"},
            {"tag": "蹲结果", "detail": "", "target": "乱写", "reader": "陌生人",
             "length": "一个词", "text": "蹲"},
        ]}}))
    app.state.comment_preview_service.model_calls.call_operation = call
    response = send(app, "POST", url(wid), json={
        "sourceMaterialId": source["id"], "noteId": "0", "mode": "live"})
    assert response.status_code == 200, response.text
    comments = response.json()["comments"]
    assert call.await_count == 1
    operation, context = call.await_args.args
    assert operation == ModelOperation.COMMENT_PREVIEW
    assert context["tagLibrary"]["version"] == TAG_LIBRARY["version"]
    assert [c["isNewTag"] for c in comments] == [False, True]
    assert comments[1]["target"] == ""


def test_preview_rejects_other_workspace_note_and_empty_target(app):
    wid, source = target(app)
    other = create_workspace(app)["id"]
    assert send(app, "POST", url(other), json={
        "sourceMaterialId": source["id"], "noteId": "0"}).status_code == 404
    assert send(app, "POST", url(wid), json={}).status_code in {400, 422}


def test_unusable_model_comments_fail_instead_of_showing_blank_cards():
    with pytest.raises(ValidationError):
        validated_comments([{"tag": "", "text": "x"}, {"tag": "夸赞", "text": " "}, "bad"])


def test_prompt_is_routed_and_validated_by_the_model_service():
    system, user = comment_preview_prompt({"post": {"title": "标题"}, "tagLibrary": {}})
    assert "tag" in system and "标题" in user
    assert ModelCallService._validate_model_output(
        ModelOperation.COMMENT_PREVIEW, {"preview": {"comments": []}})

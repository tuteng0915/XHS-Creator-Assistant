import asyncio
import json
from copy import deepcopy

import pytest
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse
from app.services.audience_analyses import AudienceAnalysisCreate
from app.services.audience_evidence import (
    AudienceEvidence,
    audience_context,
    audience_model_context,
    evidence_issues,
    observed_episodes,
)
from app.services.xhs_comment_roles import comment_source_role, reader_comments_text

AUTHOR = "1234567890abcdef"
OTHER = "fedcba0987654321"


@pytest.mark.parametrize(
    ("note_hash", "comment_hash", "role"),
    [
        (AUTHOR, AUTHOR, "author"),
        (AUTHOR, OTHER, "non_author"),
        (AUTHOR.upper(), AUTHOR, "author"),
        ("", AUTHOR, "unknown"),
        (AUTHOR, None, "unknown"),
        ("*", "*", "unknown"),
        ({"unexpected": True}, AUTHOR, "unknown"),
    ],
)
def test_role_requires_comparable_anonymous_hashes(note_hash, comment_hash, role):
    assert (
        comment_source_role(
            {"authorHash": note_hash, "nickname": "相同昵称"},
            {"authorHash": comment_hash, "nickname": "相同昵称", "sourceRole": "author"},
        )
        == role
    )


def payload():
    return {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {"platform": "xiaohongshu"},
        "creator": {"displayName": "临时测试作者"},
        "notes": [
            {
                "noteId": "n",
                "title": "申请步骤",
                "desc": "先准备材料",
                "authorHash": AUTHOR,
                "comments": [
                    {"commentId": "author", "authorHash": AUTHOR, "content": "请发到我的邮箱",
                     "nickname": "相同昵称"},
                    {"commentId": "reader", "authorHash": OTHER, "content": "第一步需要什么材料",
                     "nickname": "相同昵称"},
                    {"commentId": "old", "content": "想知道时间", "sourceRole": "author"},
                ],
            }
        ],
    }


def test_context_marks_roles_without_sending_hashes_and_rejects_author_evidence():
    data = audience_context(payload())
    assert [c["sourceRole"] for c in data["notes"][0]["comments"]] == [
        "non_author",
        "unknown",
    ]
    assert data["notes"][0]["excludedAuthorCommentIds"] == ["author"]
    assert "请发到我的邮箱" not in json.dumps(data, ensure_ascii=False)
    assert AUTHOR not in json.dumps(data) and OTHER not in json.dumps(data)
    assert data["sampling"]["sentAuthorComments"] == 0
    assert data["sampling"]["excludedAuthorComments"] == 1
    assert data["sampling"]["sentUnknownRoleComments"] == 1
    for comment_id, quote, expected in [
        ("author", "请发到我的邮箱", True),
        ("reader", "第一步", False),
        ("old", "时间", False),
    ]:
        refs = [
            AudienceEvidence(note_id="n", comment_id=comment_id, source_type="comment", quote=quote)
        ]
        issues = evidence_issues(refs, data)
        assert bool(issues) is expected
        if expected:
            assert issues[0]["code"] == "author_comment_not_reader_evidence"


def test_import_to_analysis_preserves_hashes_and_only_saves_valid_reader_roles(app):
    wid = create_workspace(app)["id"]
    imported = send(
        app,
        "POST",
        f"/api/workspaces/{wid}/input-assets/xhs-import",
        data={"type": "xhs_creator_profile"},
        files={
            "file": (
                "profile.json",
                json.dumps(payload(), ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )
    assert imported.status_code == 201
    source = imported.json()["inputAsset"]
    stored = json.loads(source["content"])
    assert stored["notes"][0]["authorHash"] == AUTHOR
    assert stored["notes"][0]["comments"][0]["authorHash"] == AUTHOR
    assert stored["notes"][0]["comments"][2]["authorHash"] == ""

    class Model:
        async def call_operation(self, operation, context):
            assert "authorReplies" not in context["notes"][0]
            assert "excludedAuthorCommentIds" not in context["notes"][0]
            assert "请发到我的邮箱" not in json.dumps(context, ensure_ascii=False)
            assert all(c["sourceRole"] != "author" for c in context["notes"][0]["comments"])
            return ModelCallResponse(
                output={
                    "summary": "两个可能读者",
                    "limitations": "仅为模拟设定",
                    "groups": [
                        {
                            "id": cid,
                            "name": cid,
                            "profile": "先找步骤再行动",
                            "evidenceRefs": [
                                {
                                    "noteId": "n",
                                    "commentId": cid,
                                    "sourceType": "comment",
                                    "quote": quote,
                                },
                            ],
                        }
                        for cid, quote in [
                            ("author", "请发到我的邮箱"),
                            ("reader", "第一步需要什么材料"),
                        ]
                    ],
                },
                model_metadata={"model": "fake"},
            )

    service = app.state.audience_analysis_service
    service.model_call_service = Model()

    async def execute():
        run = service.create(wid, AudienceAnalysisCreate(source_material_id=source["id"]))
        await asyncio.gather(*list(service.tasks.values()))
        return service.get(run.id)

    run = asyncio.run(execute())
    assert run.status == "partially_completed"
    assert run.input_snapshot["notes"][0]["authorHash"] == AUTHOR
    assert run.input_snapshot["notes"] == stored["notes"]
    assert [group["id"] for group in run.result["groups"]] == ["reader"]
    assert (
        run.diagnostics["rejectedGroups"][0]["issues"][0]["code"]
        == "author_comment_not_reader_evidence"
    )
    assert send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json() == []
    assert send(app, "POST", f"/api/workspaces/{wid}/simulated-fans", json={
        "sourceAnalysisId": run.id, "sourceGroupId": "reader",
    }).status_code == 201
    fans = send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()
    assert len(fans) == 1
    assert fans[0]["original"]["observedEpisodes"][0]["observedComment"] == "第一步需要什么材料"


def test_exclusion_precedes_reader_limit_and_keeps_positions_and_original_snapshot():
    snapshot = payload()
    snapshot["notes"][0]["comments"] = [
        {
            "content": str(i) + "中" * 1100,
            "createTime": i,
            "authorHash": AUTHOR if i % 3 == 0 else OTHER if i % 3 == 1 else "",
        }
        for i in range(90)
    ]
    snapshot["notes"] = [deepcopy(snapshot["notes"][0]) for _ in range(101)]
    original = deepcopy(snapshot)
    data = audience_context(snapshot)
    assert snapshot == original
    assert len(data["notes"]) == 100
    note = data["notes"][0]
    assert len(note["comments"]) == 50
    assert {c["commentId"] for c in note["comments"]} == {
        f"snapshot-comment-{i}" for i in range(75) if i % 3 != 0
    }
    assert all(len(c["content"]) == 1000 for c in note["comments"])
    assert note["comments"][0]["commentId"] == "snapshot-comment-1"
    assert note["comments"][1]["commentId"] == "snapshot-comment-2"
    assert note["excludedAuthorCommentIds"][0] == "snapshot-comment-0"
    sampling = data["sampling"]
    assert sampling["sentComments"] == 5000
    assert sampling["availableComments"] == 101 * 90
    assert sampling["sentCandidateComments"] == 5000
    assert sampling["sentAuthorComments"] == 0
    assert sampling["excludedAuthorComments"] == 3000
    assert sampling["sentUnknownRoleComments"] == 2500
    model_context = audience_model_context(data)
    assert all("excludedAuthorCommentIds" not in n for n in model_context["notes"])


@pytest.mark.parametrize("legacy_layout", [False, True])
def test_author_evidence_rejected_in_both_layouts_but_reader_episodes_work(legacy_layout):
    data = audience_context(payload())
    author = {"commentId": "author", "content": "请发到我的邮箱", "sourceRole": "author"}
    data["notes"][0].pop("excludedAuthorCommentIds")
    if legacy_layout:
        note = data["notes"][0]
        note["comments"] = [author] + note["comments"]
    else:
        data["notes"][0]["authorReplies"] = [author]
    author_ref = AudienceEvidence(
        note_id="n", comment_id="author", source_type="comment", quote="请发到我的邮箱"
    )
    assert evidence_issues([author_ref], data)[0]["code"] == "author_comment_not_reader_evidence"
    with pytest.raises(ValueError):
        observed_episodes([author_ref], data)
    for cid, quote in [("reader", "第一步"), ("old", "时间")]:
        ref = AudienceEvidence(note_id="n", comment_id=cid, source_type="comment", quote=quote)
        assert len(observed_episodes([ref], data)) == 1


def test_author_background_is_not_a_note_source_and_needs_no_role_flag_to_be_rejected():
    data = audience_context(payload())
    data["notes"][0].pop("excludedAuthorCommentIds")
    data["notes"][0]["authorReplies"] = [{"commentId": "author", "content": "请发到我的邮箱"}]
    wrong_comment = AudienceEvidence(
        note_id="n", comment_id="author", source_type="comment", quote="请发到我的邮箱"
    )
    assert evidence_issues([wrong_comment], data)[0]["code"] == "author_comment_not_reader_evidence"
    wrong_note = AudienceEvidence(note_id="n", source_type="note", quote="请发到我的邮箱")
    assert evidence_issues([wrong_note], data)[0]["code"] == "quote_not_exact"
    valid_note = AudienceEvidence(note_id="n", source_type="note", quote="先准备材料")
    assert evidence_issues([valid_note], data) == []


def test_all_author_comments_are_absent_and_legacy_unknowns_stay_candidates():
    snapshot = payload()
    snapshot["notes"][0]["comments"] = snapshot["notes"][0]["comments"][:1]
    data = audience_context(snapshot)
    assert data["notes"][0]["comments"] == []
    assert "请发到我的邮箱" not in json.dumps(data, ensure_ascii=False)
    assert data["sampling"]["sentComments"] == data["sampling"]["sentAuthorComments"] == 0
    assert data["sampling"]["sentCandidateComments"] == 0
    snapshot["notes"][0].pop("authorHash")
    data = audience_context(snapshot)
    assert data["notes"][0]["excludedAuthorCommentIds"] == []
    assert data["notes"][0]["comments"][0]["sourceRole"] == "unknown"


def test_prompt_excludes_author_background(settings):
    from app.models import ModelOperation
    from app.services.model_calls import ModelCallService

    data = audience_context(payload())
    system, user = ModelCallService(settings)._build_prompt(ModelOperation.AUDIENCE_ANALYSIS, data)
    assert json.loads(user) == audience_model_context(data)
    assert "请发到我的邮箱" not in user
    assert "authorReplies" not in user
    assert "已识别的作者评论已在输入前移除" in system


@pytest.mark.parametrize("legacy_layout", ["authorReplies", "comments"])
def test_legacy_provider_and_review_inputs_are_projected_without_mutating_history(
    settings, legacy_layout,
):
    from app.models import ModelOperation
    from app.services.model_calls import ModelCallService

    context = audience_context(payload())
    context["notes"][0].pop("excludedAuthorCommentIds")
    context["notes"][0].setdefault(legacy_layout, []).append({
        "commentId": "author", "content": "请发到我的邮箱", "sourceRole": "author",
    })
    context["notes"][0]["authorBackground"] = "请发到我的邮箱"
    original = deepcopy(context)
    received = []

    class Model(ModelCallService):
        async def _call_qwen(self, operation, provider_context, **kwargs):
            received.append(deepcopy(provider_context))
            return ModelCallResponse(output={}, model_metadata={})

        async def review_panel_output(self, operation, review_context, response, **kwargs):
            received.append(deepcopy(review_context))
            return response

    asyncio.run(Model(settings).call_operation(ModelOperation.AUDIENCE_ANALYSIS, context))
    assert len(received) == 2
    for projected in received:
        encoded = json.dumps(projected, ensure_ascii=False)
        assert "请发到我的邮箱" not in encoded
        assert "authorReplies" not in encoded
        assert "authorBackground" not in encoded
        assert "excludedAuthorCommentIds" not in encoded
        assert projected["sampling"]["sentAuthorComments"] == 0
        assert projected["sampling"]["excludedAuthorComments"] == 1
        assert [c["sourceRole"] for c in projected["notes"][0]["comments"]] == [
            "non_author", "unknown",
        ]
    assert context == original


@pytest.mark.parametrize("all_authors", [False, True])
def test_account_comment_projection_retains_raw_source_and_unknowns(all_authors):
    snapshot = payload()
    if all_authors:
        snapshot["notes"][0]["comments"] = snapshot["notes"][0]["comments"][:1]
    original = deepcopy(snapshot)
    text = reader_comments_text(snapshot)
    assert "请发到我的邮箱" not in text
    if all_authors:
        assert "没有可用于读者需求推导的评论" in text
    else:
        assert "第一步需要什么材料" in text
        assert "想知道时间" in text
        assert "sourceRole：non_author" in text and "sourceRole：unknown" in text
    assert snapshot == original


def test_legacy_projection_excludes_duplicate_author_ids_and_bounds_note_count():
    note = {
        "noteId": "n", "title": "正文", "content": "正文",
        "comments": [
            {"commentId": "author", "content": "作者正文"},
            {"commentId": "excluded", "content": "作者重复正文", "sourceRole": "unknown"},
            {"commentId": "reader", "content": "读者问题"},
        ],
        "authorReplies": [{"commentId": "author", "content": "作者正文"}],
        "excludedAuthorCommentIds": ["excluded"],
    }
    context = {"notes": [deepcopy(note) for _ in range(101)], "sampling": {"sentNotes": 101}}
    original = deepcopy(context)
    projected = audience_model_context(context)
    assert len(projected["notes"]) == projected["sampling"]["sentNotes"] == 100
    assert projected["sampling"]["excludedAuthorComments"] == 200
    assert projected["notes"][0]["comments"] == [
        {"commentId": "reader", "content": "读者问题", "sourceRole": "unknown"},
    ]
    assert "作者正文" not in json.dumps(projected, ensure_ascii=False)
    assert "作者重复正文" not in json.dumps(projected, ensure_ascii=False)
    assert context == original


def test_legacy_author_comments_without_ids_still_cannot_enter_model_input():
    context = {"notes": [{
        "noteId": "n", "title": "正文", "content": "正文",
        "authorReplies": [{"content": "无 ID 作者回复"}],
        "comments": [
            {"content": "无 ID 已识别作者", "sourceRole": "author"},
            {"content": "无 ID 旧评论"},
        ],
    }]}
    projected = audience_model_context(context)
    assert projected["notes"][0]["comments"] == [
        {"content": "无 ID 旧评论", "sourceRole": "unknown"},
    ]
    assert projected["sampling"]["excludedAuthorComments"] == 2
    assert "无 ID 作者回复" not in json.dumps(projected, ensure_ascii=False)


def test_all_author_input_reaches_audience_model_without_comment_text(app):
    from test_account_langgraph_workflow import create_text_material

    wid = create_workspace(app)["id"]
    raw = payload()
    raw["notes"][0]["comments"] = raw["notes"][0]["comments"][:1]
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(raw))
    seen = []

    class Model:
        async def call_operation(self, operation, context):
            seen.append(context)
            return ModelCallResponse(output={
                "summary": "内容潜在视角", "limitations": "模拟设定",
                "groups": [{"id": "reader", "name": "起步行动派", "profile": "想先找到第一步",
                            "evidenceRefs": [{"noteId": "n", "sourceType": "note",
                                              "quote": "先准备材料"}]}],
            }, model_metadata={})

    service = app.state.audience_analysis_service
    service.model_call_service = Model()

    async def execute():
        run = service.create(wid, AudienceAnalysisCreate(source_material_id=source["id"]))
        await asyncio.gather(*list(service.tasks.values()))
        return service.get(run.id)

    run = asyncio.run(execute())
    assert len(seen) == 1
    assert seen[0]["notes"][0]["comments"] == []
    assert "请发到我的邮箱" not in json.dumps(seen[0], ensure_ascii=False)
    assert run.result["groups"][0]["evidenceBasis"] == "content_inferred"
    assert run.result["groups"][0]["observedEpisodes"] == []
    assert run.input_snapshot["notes"] == raw["notes"]


@pytest.mark.parametrize("legacy_snapshot", [False, True])
def test_account_workflow_provider_never_receives_author_comments(app, legacy_snapshot):
    from test_account_langgraph_workflow import collect, create_text_material

    from app.workflows.account_diagnosis import FakeAccountDiagnosisModelProvider

    wid = create_workspace(app)["id"]
    raw = payload()
    source = create_text_material(app, wid, "xhs_creator_profile", json.dumps(raw))
    response = send(app, "POST", f"/api/workspaces/{wid}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": source["id"],
        "mode": "demo", "analysisScope": "all",
    })
    assert response.status_code == 201
    run = response.json()
    frozen = run["inputSnapshot"]
    assert "请发到我的邮箱" not in frozen["comments"]["content"]
    assert frozen["xhsCreatorProfile"]["notes"] == raw["notes"]
    if legacy_snapshot:
        frozen["comments"]["content"] = "旧版混合派生输入：请发到我的邮箱"
        with app.state.database.transaction() as c:
            c.execute("UPDATE analysis_runs SET input_snapshot_json=? WHERE id=?",
                      (json.dumps(frozen), run["id"]))
    captured = []

    class Provider(FakeAccountDiagnosisModelProvider):
        async def pain_points(self, *, comments):
            captured.append(comments)
            return await super().pain_points(comments=comments)

    app.state.account_workflow_service.fake_provider = Provider()
    collect(app, run["id"])
    assert len(captured) == 1
    assert "请发到我的邮箱" not in captured[0]
    assert "第一步需要什么材料" in captured[0] and "想知道时间" in captured[0]
    saved = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert saved["status"] == "completed"
    assert saved["inputSnapshot"] == frozen

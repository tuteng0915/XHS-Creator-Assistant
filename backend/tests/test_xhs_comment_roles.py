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
    evidence_issues,
    observed_episodes,
)
from app.services.xhs_comment_roles import comment_source_role

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
                    {"commentId": "author", "authorHash": AUTHOR, "content": "请发到我的邮箱"},
                    {"commentId": "reader", "authorHash": OTHER, "content": "第一步需要什么材料"},
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
    assert [c["sourceRole"] for c in data["notes"][0]["authorReplies"]] == ["author"]
    assert AUTHOR not in json.dumps(data) and OTHER not in json.dumps(data)
    assert data["sampling"]["sentAuthorComments"] == 1
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
            assert context["notes"][0]["authorReplies"][0]["sourceRole"] == "author"
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
    assert [group["id"] for group in run.result["groups"]] == ["reader"]
    assert (
        run.diagnostics["rejectedGroups"][0]["issues"][0]["code"]
        == "author_comment_not_reader_evidence"
    )
    fans = send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()
    assert len(fans) == 1
    assert fans[0]["original"]["observedEpisodes"][0]["observedComment"] == "第一步需要什么材料"


def test_partition_keeps_combined_limits_positions_and_original_snapshot():
    snapshot = payload()
    snapshot["notes"][0]["comments"] = [
        {
            "content": str(i) + "中" * 1100,
            "createTime": i,
            "authorHash": AUTHOR if i % 3 == 0 else OTHER if i % 3 == 1 else "",
        }
        for i in range(55)
    ]
    snapshot["notes"] = [deepcopy(snapshot["notes"][0]) for _ in range(101)]
    original = deepcopy(snapshot)
    data = audience_context(snapshot)
    assert snapshot == original
    assert len(data["notes"]) == 100
    note = data["notes"][0]
    combined = note["comments"] + note["authorReplies"]
    assert len(combined) == 50  # Not 50 per bucket; no new source selection.
    assert {c["commentId"] for c in combined} == {f"snapshot-comment-{i}" for i in range(50)}
    assert all(len(c["content"]) == 1000 for c in combined)
    assert note["comments"][0]["commentId"] == "snapshot-comment-1"
    assert note["comments"][1]["commentId"] == "snapshot-comment-2"
    assert note["authorReplies"][0]["commentId"] == "snapshot-comment-0"
    sampling = data["sampling"]
    assert sampling["sentComments"] == 5000
    assert sampling["availableComments"] == 101 * 55
    assert sampling["sentCandidateComments"] == 3300
    assert sampling["sentAuthorComments"] == 1700
    assert sampling["sentUnknownRoleComments"] == 1600


@pytest.mark.parametrize("legacy_layout", [False, True])
def test_author_evidence_rejected_in_both_layouts_but_reader_episodes_work(legacy_layout):
    data = audience_context(payload())
    if legacy_layout:
        note = data["notes"][0]
        note["comments"] = note.pop("authorReplies") + note["comments"]
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
    data["notes"][0]["authorReplies"][0].pop("sourceRole")
    wrong_comment = AudienceEvidence(
        note_id="n", comment_id="author", source_type="comment", quote="请发到我的邮箱"
    )
    assert evidence_issues([wrong_comment], data)[0]["code"] == "author_comment_not_reader_evidence"
    wrong_note = AudienceEvidence(note_id="n", source_type="note", quote="请发到我的邮箱")
    assert evidence_issues([wrong_note], data)[0]["code"] == "quote_not_exact"
    valid_note = AudienceEvidence(note_id="n", source_type="note", quote="先准备材料")
    assert evidence_issues([valid_note], data) == []


def test_all_author_comments_stay_as_background_and_legacy_unknowns_stay_candidates():
    snapshot = payload()
    snapshot["notes"][0]["comments"] = snapshot["notes"][0]["comments"][:1]
    data = audience_context(snapshot)
    assert data["notes"][0]["comments"] == []
    assert data["notes"][0]["authorReplies"][0]["content"] == "请发到我的邮箱"
    assert data["sampling"]["sentComments"] == data["sampling"]["sentAuthorComments"] == 1
    assert data["sampling"]["sentCandidateComments"] == 0
    snapshot["notes"][0].pop("authorHash")
    data = audience_context(snapshot)
    assert data["notes"][0]["authorReplies"] == []
    assert data["notes"][0]["comments"][0]["sourceRole"] == "unknown"


def test_prompt_explains_background_separation_without_hiding_it(settings):
    from app.models import ModelOperation
    from app.services.model_calls import ModelCallService

    data = audience_context(payload())
    system, user = ModelCallService(settings)._build_prompt(ModelOperation.AUDIENCE_ANALYSIS, data)
    assert json.loads(user) == data
    assert "authorReplies 单独保留作者解释背景" in system
    assert "仍需综合笔记正文与作者背景理解内容" in system

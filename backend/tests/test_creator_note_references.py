import asyncio
import json

import pytest
from test_content_collaboration_sessions import create_workspace_and_topic
from test_single_writer_sessions import analysis, payload, send, setup_writer

from app.errors import NotFoundError, ValidationError
from app.models import CreatorContextReference, CreatorContextSelection, TextSourceMaterialCreate
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.creator_context import canonical_selection


def note(note_id="note-a", *, title="旧笔记标题", body="旧笔记完整正文"):
    return {
        "noteId": note_id,
        "title": title,
        "desc": body,
        "metrics": {"likes": 987654},
        "comments": [{"content": "作者回复和读者评论均不进入写作参考"}],
        "coverUrl": "https://example.test/private-cover.jpg",
        "images": [{"url": "https://example.test/private-body.jpg"}],
    }


def material(app, workspace_id, notes, *, kind="xhs_creator_profile", content=None):
    profile = {
        "creator": {"nickname": "账号资料不能带入"},
        "source": {"importedAt": "2026-10-01T00:00:00Z"},
        "notes": notes,
    }
    saved = app.state.source_service.create_text(
        workspace_id,
        TextSourceMaterialCreate(
            type=kind,
            name="原笔记资料",
            content=json.dumps(profile, ensure_ascii=False) if content is None else content,
        ),
    )
    return saved.id, profile


def reference(material_id, note_id="note-a"):
    return {"kind": "imported_note", "id": material_id, "noteId": note_id}


def update_material(app, material_id, profile):
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE source_materials SET text_content=?,updated_at=? WHERE id=?",
            (json.dumps(profile, ensure_ascii=False), "2026-10-10T00:00:00Z", material_id),
        )


def test_exact_note_references_keep_full_text_and_do_not_expand_the_account(app):
    workspace, _, service, provider, session = setup_writer(app)
    full_body = "正文保持完整" * 1_000 + "结尾也必须保留"
    material_id, _ = material(
        app,
        workspace["id"],
        [
            note(body=full_body),
            note("note-b", title="第二篇标题", body="第二篇正文"),
            note("note-unselected", title="未选笔记标题", body="未选笔记正文"),
        ],
    )
    chosen_analysis = analysis(app, workspace["id"])
    result = asyncio.run(
        send(
            service,
            workspace["id"],
            session.id,
            payload(
                "借鉴两篇笔记",
                [reference(material_id, "note-b"), reference(material_id), chosen_analysis],
            ),
        )
    )
    context = provider.calls[0][2]
    encoded = json.dumps(context, ensure_ascii=False)
    assert full_body in encoded
    assert "第二篇正文" in encoded and "选中账号结果" in encoded
    for forbidden in (
        "未选笔记",
        "账号资料不能带入",
        "作者回复",
        "读者评论",
        "987654",
        "private-cover",
        "private-body",
    ):
        assert forbidden not in encoded
    frozen = result.runs[0].input_snapshot["sessionContext"]["creatorContextSnapshot"]["references"]
    notes = [item for item in frozen if item["kind"] == "imported_note"]
    assert len(notes) == 2
    assert all(set(item["content"]) == {"title", "body"} for item in notes)
    assert {item["noteId"] for item in notes} == {"note-a", "note-b"}
    sources = RealContentCollaborationProvider._allowed_sources(context)
    note_sources = [
        item for key, item in sources.items() if key.startswith("reference:imported_note:")
    ]
    assert len(note_sources) == 2  # Same material must not overwrite the first selected note.
    assert all(
        item["label"] == "作者选择的原笔记" and len(item["id"]) <= 160 for item in note_sources
    )
    assert full_body in json.dumps(note_sources, ensure_ascii=False)
    assert "第二篇正文" in json.dumps(note_sources, ensure_ascii=False)


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "imported_note", "id": "material"},
        {"kind": "imported_note", "id": "material", "noteId": "   "},
        {"kind": "imported_note", "id": "material", "noteId": 42},
        {"kind": "account_analysis", "id": "run", "noteId": "note-a"},
        {"kind": "audience_analysis", "id": "run", "noteId": "note-a"},
    ],
)
def test_note_reference_wire_requires_the_exact_note_identity(data):
    with pytest.raises(ValueError):
        CreatorContextReference.model_validate(data)


def test_reference_canonicalization_preserves_legacy_shape_and_note_identity():
    account = {"kind": "account_analysis", "id": "account-run"}
    assert CreatorContextReference.model_validate(account).model_dump(by_alias=True) == account
    assert canonical_selection(CreatorContextSelection(references=[account])) == {
        "schemaVersion": "creator-context-selection/v1",
        "references": [account],
    }
    a, b = reference("material"), reference("material", "note-b")
    selection = canonical_selection(CreatorContextSelection(references=[b, a, b, account]))
    assert selection["references"] == [account, a, b]
    with pytest.raises(ValueError):
        CreatorContextSelection(references=[reference("material", f"id-{i}") for i in range(9)])


@pytest.mark.parametrize(
    "problem",
    [
        "missing_material",
        "other_workspace",
        "wrong_material_type",
        "missing_note",
        "duplicate_note",
        "synthetic_note",
        "missing_identity",
        "numeric_identity",
        "empty_text",
        "invalid_json",
        "invalid_notes",
    ],
)
def test_invalid_imported_note_fails_before_model_or_message_append(app, problem):
    workspace, _, service, provider, session = setup_writer(app)
    owner_id = workspace["id"]
    notes, note_id = [note()], "note-a"
    extra = {}
    if problem == "other_workspace":
        other, _ = create_workspace_and_topic(app)
        owner_id = other["id"]
    elif problem == "wrong_material_type":
        extra["kind"] = "historical_posts"
    elif problem == "missing_note":
        note_id = "not-present"
    elif problem == "duplicate_note":
        notes.append(note(body="相同身份另一份正文"))
    elif problem == "synthetic_note":
        notes, note_id = [note("note-1")], "note-1"
    elif problem == "missing_identity":
        notes[0].pop("noteId")
        note_id = "None"
    elif problem == "numeric_identity":
        notes, note_id = [note(42)], "42"
    elif problem == "empty_text":
        notes = [note(title=" ", body="\n")]
    elif problem == "invalid_json":
        extra["content"] = "{broken"
    elif problem == "invalid_notes":
        extra["content"] = '{"notes": {"note-a": {"desc": "不可推断的资料"}}}'
    material_id, _ = material(app, owner_id, notes, **extra)
    if problem == "missing_material":
        material_id = "missing"
    with pytest.raises((ValidationError, NotFoundError)):
        asyncio.run(
            service.send_message(
                workspace["id"],
                session.id,
                payload(problem, [reference(material_id, note_id)]),
            )
        )
    assert not provider.calls
    assert not service.get(workspace["id"], session.id).messages


@pytest.mark.parametrize(("title", "body"), [("只有标题", ""), ("", "只有正文")])
def test_note_reference_allows_available_text_without_inventing_a_title(app, title, body):
    workspace, _, service, provider, session = setup_writer(app)
    material_id, _ = material(app, workspace["id"], [note(title=title, body=body)])
    asyncio.run(
        send(service, workspace["id"], session.id, payload("参考", [reference(material_id)]))
    )
    frozen = provider.calls[0][2]["sessionContext"]["creatorContextSnapshot"]["references"][0]
    assert frozen["content"] == {"title": title, "body": body}


def test_combined_note_reference_budget_fails_without_silent_truncation(app):
    workspace, _, service, provider, session = setup_writer(app)
    material_id, _ = material(
        app,
        workspace["id"],
        [
            note(body="长" * 25_000),
            note("note-b", body="长" * 25_000),
        ],
    )
    with pytest.raises(ValidationError, match="参考材料过多"):
        asyncio.run(
            service.send_message(
                workspace["id"],
                session.id,
                payload(
                    "超限",
                    [reference(material_id), reference(material_id, "note-b")],
                ),
            )
        )
    assert not provider.calls
    assert not service.get(workspace["id"], session.id).messages


def test_selected_note_text_changes_isolate_context_but_metrics_and_unselected_notes_do_not(app):
    workspace, _, service, provider, session = setup_writer(app)
    material_id, profile = material(app, workspace["id"], [note(), note("note-b")])
    selected = [reference(material_id)]

    async def run():
        first = await send(service, workspace["id"], session.id, payload("第一段", selected))
        original_snapshot = first.runs[0].input_snapshot
        profile["notes"][0]["metrics"]["likes"] = 42
        profile["notes"][0]["comments"] = []
        profile["notes"][1]["desc"] = "未选笔记更新"
        profile["source"]["importedAt"] = "2026-10-10T00:00:00Z"
        update_material(app, material_id, profile)
        await send(service, workspace["id"], session.id, payload("仍在第一段", selected))
        profile["notes"][0]["desc"] = "参考正文已改变"
        update_material(app, material_id, profile)
        await send(service, workspace["id"], session.id, payload("正文变化另起一段", selected))
        profile["notes"][0]["title"] = "参考标题已改变"
        update_material(app, material_id, profile)
        await send(service, workspace["id"], session.id, payload("标题变化再起一段", selected))
        # Same request key still replays the immutable prior result, not today's note.
        replay = await service.send_message(
            workspace["id"], session.id, payload("第一段", selected)
        )
        assert (
            next(item for item in replay.runs if item.request_key == "第一段").input_snapshot
            == original_snapshot
        )
        return replay

    result = asyncio.run(run())
    contexts = [item[2] for item in provider.calls]
    assert len(contexts) == 4
    assert [item["sessionContext"]["contextRevision"] for item in contexts] == [1, 1, 2, 3]
    assert "第一段" in [item["content"] for item in contexts[1]["transcript"]]
    assert [item["content"] for item in contexts[2]["transcript"]] == ["正文变化另起一段"]
    assert [item["content"] for item in contexts[3]["transcript"]] == ["标题变化再起一段"]
    versions = [
        item["sessionContext"]["creatorContextSnapshot"]["references"][0]["sourceVersion"]
        for item in contexts
    ]
    assert versions[0] == versions[1]
    assert len(set(versions)) == 3
    assert len(result.messages) == 8  # Every old segment remains visible.

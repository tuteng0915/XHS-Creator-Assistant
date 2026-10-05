from copy import deepcopy

import pytest

from app.services.audience_evidence import reader_persona_context
from app.services.audience_target import reader_visible_target, reader_visible_texts
from app.workflows.audience_simulation import validate_trigger_quote


def episodes():
    return [{"noteId": str(i), "commentId": str(i), "noteTitle": title,
             "noteExcerpt": title, "observedComment": title, "evidenceQuote": title}
            for i, title in enumerate(["摄影", "运动", "烹饪", "游戏", "住宿保险"])]


@pytest.mark.parametrize("editable", [
    {"structure": {"topicChosen": "新稿", "outline": [{"sec": "核对", "ct": "住宿保险"}]}},
    {"brief": {"corePoint": "住宿保险", "argumentPath": ["先列清单", "再核对"]}},
])
def test_draft_text_retrieves_relevant_history_without_changing_persona_or_snapshot(editable):
    snapshot = {"topic": {"title": "新稿", "body": ""}, "draft": {"editableContent": editable}}
    persona = {"id": "p", "profile": "先核对再行动", "observedEpisodes": episodes()}
    original = deepcopy((snapshot, persona))
    target = reader_visible_target(snapshot)
    chosen = reader_persona_context(persona, target)
    assert chosen["observedEpisodes"][0]["noteId"] == "4"
    assert len(chosen["observedEpisodes"]) == 4
    assert chosen["profile"] == persona["profile"]
    assert (snapshot, persona) == original
    validate_trigger_quote("住宿保险", target)


def test_private_strategy_and_metadata_do_not_rank_episodes_or_validate_quotes():
    snapshot = {"topic": {"title": "新稿", "angle": "住宿保险", "whyItFits": "住宿保险"},
                "draft": {"editableContent": {"brief": {"targetAudience": "住宿保险"}}}}
    target = reader_visible_target(snapshot)
    target.update(limitations="住宿保险", previewLevel="住宿保险", observedEpisodes=episodes())
    chosen = reader_persona_context({"observedEpisodes": episodes()}, target)
    assert [e["noteId"] for e in chosen["observedEpisodes"]] == ["0", "1", "2", "3"]
    assert "住宿保险" not in reader_visible_texts(target)
    with pytest.raises(ValueError, match="不是本次内容"):
        validate_trigger_quote("住宿保险", target)


def test_fragment_boundaries_never_create_a_quote_or_retrieval_term():
    target = reader_visible_target({"topic": {"title": "住", "body": "宿"}})
    persona = {"observedEpisodes": [
        {**episode, "noteTitle": "住宿", "noteExcerpt": "住宿", "observedComment": "住宿"}
        if i == 4 else episode for i, episode in enumerate(episodes())
    ]}
    chosen = reader_persona_context(persona, target)
    assert [e["noteId"] for e in chosen["observedEpisodes"]] == ["0", "1", "2", "3"]
    with pytest.raises(ValueError):
        validate_trigger_quote("住宿", target)


def test_public_topic_and_missing_text_remain_compatible():
    persona = {"observedEpisodes": episodes()}
    chosen = reader_persona_context(persona, {"body": "住宿保险"})
    assert chosen["observedEpisodes"][0]["noteId"] == "4"
    assert len(reader_persona_context(persona, {})["observedEpisodes"]) == 4
    assert reader_persona_context({}, {})["observedEpisodes"] == []
    assert reader_visible_texts({"title": None, "body": 10}) == []
    validate_trigger_quote("", {})
    with pytest.raises(ValueError):
        validate_trigger_quote("历史评论", {"title": "新的正文"})

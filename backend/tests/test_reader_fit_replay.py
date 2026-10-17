"""Frozen replay preserves sources and never overrides reader-fit decisions locally."""
import asyncio
import importlib.util
import json
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

import pytest
from test_panel_quality import selection

from app.config import Settings
from app.services.panel_quality import apply_review, prepare_review


def tool():
    path = Path(__file__).resolve().parents[2] / "scripts" / "replay_reader_fit.py"
    spec = importlib.util.spec_from_file_location("reader_fit_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def saved():
    context, primary = selection()
    plan = prepare_review("reader_selection", context, primary)
    decisions = {"decisions": [{"id": cid, "decision": "exclude", "reason": "旧判断"}
                               for cid in plan.ids]}
    old_context = {k: v for k, v in plan.context.items() if k != "recommendationClaims"}
    return {"inputSnapshot": context, "result": {"proposedReaders": []}, "requests": [
        {"rawContent": json.dumps(primary)},
        {"rawContent": json.dumps(decisions),
         "packet": {"messages": [{"content": "old fit policy"},
                                  {"content": json.dumps(old_context, ensure_ascii=False)}]}}
    ]}


def test_replay_keeps_entire_manuscript_and_people_exact_not_generator_reasons():
    source = saved()
    before = deepcopy(source)
    inputs, primary, plan = tool().prepare(source)
    assert source == before
    assert {k: v for k, v in plan.context.items() if k != "recommendationClaims"} == json.loads(
        source["requests"][1]["packet"]["messages"][-1]["content"])
    assert plan.context["manuscript"]["body"] == inputs.target["body"]
    assert primary == json.loads(source["requests"][0]["rawContent"])
    assert "PERSUASIVE_GENERATOR_REASON" not in plan.prompt[1]
    assert "recommendationClaims" not in plan.context
    assert "ACCOUNT_NOT_EVIDENCE" not in plan.prompt[1]


def test_modified_checker_input_is_refused_before_any_call():
    source = saved()
    source["inputSnapshot"]["target"]["body"] += "新编材料"
    with pytest.raises(ValueError, match="frozen checker input"):
        tool().prepare(source)


def test_adjacent_label_cannot_overrule_exclusion_or_fill_quota_locally():
    context, primary = selection()
    for row in primary["proposedReaders"]:
        row["relation"] = "adjacent"
    before = deepcopy((context, primary))
    plan = prepare_review("reader_selection", context, primary)
    output, _ = apply_review(plan, primary, {"decisions": [
        {"id": cid, "decision": "exclude", "reason": "没有具体用途联系"}
        for cid in plan.ids
    ]})
    assert output["proposedReaders"] == []
    assert output["unmatchedReason"]
    assert (context, primary) == before


def test_adjacent_can_survive_without_adding_an_unrelated_reader():
    context, primary = selection()
    primary["proposedReaders"][0]["relation"] = "adjacent"
    plan = prepare_review("reader_selection", context, primary)
    output, _ = apply_review(plan, primary, {"decisions": [
        {"id": "a", "decision": "include", "reason": "现有论文观点能帮助此人理解问题"},
        {"id": "b", "decision": "exclude", "reason": "不涉及此人的住宿预算需求"},
    ]})
    assert [r["fanId"] for r in output["proposedReaders"]] == ["a"]
    assert output["proposedReaders"][0]["relation"] == "adjacent"


def test_preview_reads_no_credentials_or_network_and_creates_no_output(
    tmp_path, monkeypatch, capsys,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not read credentials")

    monkeypatch.setattr(Settings, "from_environment", forbidden)
    source = tmp_path / "source.json"
    source.write_text(json.dumps(saved()), encoding="utf-8")
    before = source.read_bytes()
    destination = tmp_path / "output"
    asyncio.run(tool().replay(Namespace(
        source_report=source, output=destination, live=False,
        expect_include=[], expect_exclude=[],
    )))
    assert json.loads(capsys.readouterr().out)["modelRequests"] == 0
    assert not destination.exists() and source.read_bytes() == before

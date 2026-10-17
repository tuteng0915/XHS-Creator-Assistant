import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def check(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "revision_eval", scripts / "check_creator_revision.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def frozen(check, tmp_path):
    path = tmp_path / "saved.json"
    path.write_text(json.dumps({"arms": [
        {"account": p[0], "arm": "enhanced", "readerIds": p[3],
         "initial": {"title": "原有标题", "body": "不可重写的首稿" + p[0]},
         "chosenFeedback": {"quote": "原有试读意见"}}
        for p in check.PLAN
    ]}), encoding="utf-8")
    return path


def test_saved_cases_are_exact_independent_copies_never_modify_receipt(check, frozen):
    raw = frozen.read_bytes()
    selected, hash = check.saved_cases(frozen)
    assert len(selected) == 2 and len(hash) == 64
    selected[0]["initial"]["body"] = "changed in memory"
    assert frozen.read_bytes() == raw
    assert check.saved_cases(frozen)[0][0]["initial"]["body"] != "changed in memory"


@pytest.mark.parametrize("change", ["duplicate", "reader_mismatch", "empty_draft"])
def test_cannot_silently_substitute_drafts_or_readers(check, frozen, change):
    report = json.loads(frozen.read_text())
    if change == "duplicate":
        report["arms"].append(report["arms"][0])
    elif change == "reader_mismatch":
        report["arms"][0]["readerIds"] = ["unrelated"]
    else:
        report["arms"][0]["initial"]["body"] = " "
    frozen.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        check.saved_cases(frozen)


def test_preview_never_loads_credentials_writes_outputs_or_calls_model(
    check, frozen, monkeypatch, tmp_path,
):
    def forbidden(*args):
        pytest.fail("Preview must remain offline")

    monkeypatch.setattr(check, "load_env_file_defaults", forbidden)
    monkeypatch.setattr(check.importlib, "import_module", forbidden)
    output = tmp_path / "new"
    asyncio.run(check.run(SimpleNamespace(source_report=frozen, output=output, live=False)))
    assert not output.exists()

import asyncio
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def regression(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "creator_statement_regression", scripts / "check_creator_statement_regression.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def receipts():
    quote = "在去年这个阶段，我和家人长聊了几番"
    bad = {"packet": {"conversation": [{"role": "user", "content": "回应应届生"}]},
           "modelMetadata": {"factEdit": {"originalOutput": {"turn": {
               "candidateSuggestions": [{"body": "很多应届生跟我说。"}],
           }}}}}
    positive = {"packet": {"conversation": [], "evidence": {"allowedSources": [{
        "id": "note", "sourceRole": "source_document",
        "text": json.dumps({"result": {"body": quote + "。后面的内容。"}}),
    }]}}}
    return bad, positive


def test_three_bounded_fixtures_preserve_bad_draft_and_disclose_constructed_positives(
    regression, receipts,
):
    frozen = deepcopy(receipts)
    bad, positive = receipts
    rows = regression.fixtures(bad, positive)
    assert len(rows) == 3
    assert rows[0]["packet"] == bad["packet"]
    assert rows[0]["originalOutput"] == bad["modelMetadata"]["factEdit"]["originalOutput"]
    assert rows[0]["origin"] == "unchanged_saved_generation"
    assert rows[1]["origin"] == "diagnostic_draft_from_real_note"
    assert rows[1]["originalOutput"] == rows[2]["originalOutput"]
    assert rows[2]["packet"]["evidence"]["allowedSources"] == []
    assert rows[1]["sourceQuote"] in rows[2]["packet"]["conversation"][0]["content"]
    assert receipts == frozen


def test_positive_is_not_silently_invented_if_original_does_not_contain_it(regression, receipts):
    bad, positive = receipts
    positive["packet"]["evidence"]["allowedSources"][0]["text"] = '{"result":{"body":"无交流"}}'
    with pytest.raises(ValueError, match="real saved"):
        regression.fixtures(bad, positive)


def test_preview_never_loads_secrets_calls_models_or_writes_outputs(
    regression, receipts, monkeypatch, tmp_path, capsys,
):
    bad_path, positive_path = tmp_path / "bad.json", tmp_path / "positive.json"
    for path, document in zip((bad_path, positive_path), receipts, strict=True):
        path.write_text(json.dumps(document))
    monkeypatch.setattr("sys.argv", ["regression", "--bad-receipt", str(bad_path),
                                     "--positive-receipt", str(positive_path),
                                     "--env-root", str(tmp_path)])

    def forbidden(*args, **kwargs):
        pytest.fail("Preview must not load credentials or instantiate a model service")

    monkeypatch.setattr(regression, "load_env_file_defaults", forbidden)
    monkeypatch.setattr(regression, "ModelCallService", forbidden)
    asyncio.run(regression.main())
    result = json.loads(capsys.readouterr().out)
    assert result["requestCount"] == 0 and result["maxRequestsPlanned"] == 6
    assert len(list(tmp_path.iterdir())) == 2

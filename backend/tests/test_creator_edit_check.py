import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.models import ModelCallResponse, ModelOperation


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_creator_edit.py"
    spec = importlib.util.spec_from_file_location("creator_edit_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(update):
    return {"reply": "先保留你的表达，再调整需要的部分。", "update": update,
            "pendingSuggestions": [],
            "factCheck": {"safeToApply": True, "supportedClaims": []}}


def test_creator_preview_is_free_and_does_not_load_credentials(monkeypatch, capsys):
    check = load_check()
    monkeypatch.setattr(sys, "argv", [check.__file__, "--case", "opening"])
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("preview is free"))
    assert check.main() == 0
    value = json.loads(capsys.readouterr().out)
    assert value["requestAttempts"] == 0
    assert value["context"]["topic"]["body"] == "\n\n".join(check.PARAGRAPHS)


@pytest.mark.parametrize("name", ["discussion", "style", "title", "opening", "draft"])
def test_creator_check_exercises_one_call_and_does_not_claim_semantic_success(name):
    check = load_check()
    context = check.make_case(name)
    update = None
    if name == "title":
        update = {"title": "选项太多时，先明确最在意的事", "body": context["topic"]["body"]}
    elif name == "opening":
        update = {"title": check.TITLE,
                  "body": "选项越多，越难开始。\n\n" + "\n\n".join(check.PARAGRAPHS[1:])}
    elif name == "draft":
        update = {"title": check.TITLE, "body": "先弄清自己最在意的事，再作选择。"}

    class Model:
        calls = 0

        async def call_operation(self, operation, passed):
            self.calls += 1
            assert operation == ModelOperation.CREATOR_EDIT
            assert passed == context
            return ModelCallResponse(output=response(update), model_metadata={"model": "fake"})

    model = Model()
    result = asyncio.run(check.run_check(model, name))
    assert model.calls == 1
    assert result["status"] == "completed"
    assert result["semanticStatus"] == "not_reviewed"
    assert result["modelMetadata"]["model"] == "fake"


@pytest.mark.parametrize("name, update, failed_check", [
    ("discussion", {"title": "擅自改稿", "body": "正文"}, "discussionDoesNotEdit"),
    ("style", {"title": "擅自改稿", "body": "正文"}, "discussionDoesNotEdit"),
    ("title", {"title": "新标题", "body": "擅自改正文"}, "bodyUnchanged"),
    ("opening", {"title": "新标题", "body": "简短开头"}, "remainingParagraphsUnchanged"),
    ("draft", None, "updatePresent"),
])
def test_creator_check_detects_scope_failures_not_just_valid_json(name, update, failed_check):
    check = load_check()

    class Model:
        async def call_operation(self, *_):
            return ModelCallResponse(output=response(update), model_metadata={})

    result = asyncio.run(check.run_check(Model(), name))
    assert result["status"] == "scope_failed"
    assert result["scopeChecks"][failed_check] is False


def test_creator_transport_failure_is_not_retried_or_echoed():
    check = load_check()

    class Model:
        calls = 0

        async def call_operation(self, *_):
            self.calls += 1
            raise RuntimeError("secret transport payload")

    model = Model()
    result = asyncio.run(check.run_check(model, "opening"))
    assert model.calls == 1
    assert result["error"] == {"phase": "model_call", "type": "RuntimeError"}
    assert "secret" not in json.dumps(result)
    assert check.redact({"key": ["key key-long"]}, ["key", "key-long"]) == {
        "[REDACTED]": ["[REDACTED] [REDACTED]"],
    }


def test_live_check_refuses_existing_output_before_model_call(tmp_path, monkeypatch):
    check = load_check()
    monkeypatch.setattr(sys, "argv", [check.__file__, "--live", "--output", str(tmp_path)])
    monkeypatch.setattr(check.Settings, "from_environment", lambda: check.Settings(
        database_path=tmp_path / "unused.db", upload_directory=tmp_path, qwen_api_key="fake",
    ))
    monkeypatch.setattr(check, "run_check", lambda *_: pytest.fail("must not call"))
    with pytest.raises(FileExistsError):
        check.main()
    assert not (tmp_path / "unused.db").exists()

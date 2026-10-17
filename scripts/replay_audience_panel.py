"""Offline replay of saved audience/panel receipts. No provider, server or database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.audience_analyses import validate_audience_output  # noqa: E402
from app.services.editor_feedback import validate_editor_feedback  # noqa: E402
from app.services.panel_quality import PanelReview, apply_review, prepare_review  # noqa: E402


def feedback(output: dict, context: dict) -> dict:
    return validate_editor_feedback(
        output["synthesis"].get("editorFeedback"), topic=context["topic"],
        personas=context["personas"], reactions=context["reactions"],
        replies=context["debateResponses"],
    )


def replay(report: dict) -> dict:
    before = deepcopy(report)
    accounts = []
    for account in report["accounts"]:
        name = account["account"]
        generations = [r for r in report["requests"] if r["account"] == name
                       and r["operation"] == "audience_analysis" and r.get("rawContent")]
        if len(generations) != 1:
            raise ValueError(f"{name}: expected exactly one saved audience generation")
        audience, diagnostics = validate_audience_output(
            json.loads(generations[0]["rawContent"]), account["audienceContext"],
        )
        completed = [c for c in report["calls"] if c["account"] == name
                     and c["operation"] == "simulation_synthesis" and c["status"] == "completed"]
        call = completed[-1]
        packets = [r for r in report["requests"] if r["callIndex"] == call["index"]
                   and r["account"] == name and r.get("rawContent")]
        raw_output = json.loads(packets[0]["rawContent"])
        validated = feedback(raw_output, call["context"])
        current_plan = prepare_review("simulation_synthesis", call["context"], raw_output)
        reviewed, receipt = raw_output, None
        if len(packets) == 2:
            # Reuse the EXACT old reviewer input/verdict, not fabricated decisions
            # for newly recovered cards. New question-only cards need no verdict.
            messages = packets[1]["packet"]["messages"]
            saved_context = json.loads(messages[-1]["content"])
            plan = PanelReview(
                "edit_facts", messages[0]["content"], saved_context,
                [e["id"] for e in saved_context["edits"]],
                {c["id"]: c for c in validated["editorFeedback"]},
            )
            reviewed, receipt = apply_review(plan, raw_output, json.loads(packets[1]["rawContent"]))
        elif len(packets) != 1:
            raise ValueError(f"{name}: unexpected saved synthesis packet count")
        final = feedback(reviewed, call["context"])
        simulation = account.get("recovery", {}).get("simulation", account["simulation"])
        old_cards = simulation["synthesis"].get("editorFeedback", [])
        accepted_ids = {g["id"] for g in account["analysis"]["result"]["groups"]}
        accounts.append({
            "account": name,
            "audience": {"beforeAccepted": len(accepted_ids),
                         "afterAccepted": len(audience["groups"]),
                         "recovered": [g for g in audience["groups"] if g["id"] not in accepted_ids],
                         "diagnostics": diagnostics},
            "feedback": {"before": old_cards, "after": final["editorFeedback"],
                         "contentAdjustments": final["contentAdjustments"],
                         "validation": final["editorFeedbackValidation"],
                         "normalization": validated["editorFeedbackValidation"],
                         "savedReviewReceipt": receipt,
                         "newReviewCopyIds": current_plan.ids if current_plan else []},
            "recommendationReplayed": False,
        })
    if report != before:
        raise AssertionError("offline processing mutated the source receipt")
    return {"mode": "saved_receipt_replay", "modelRequests": 0,
            "sourceUnchanged": True, "accounts": accounts,
            "limitations": ["未重新推荐或讨论，恢复候选不等于已验证会被推荐。",
                            "保留具体反馈不等于认可全部模型判断或证明真实受众代表性。"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source_report.read_bytes()
    result = replay(json.loads(source))
    result["sourceSha256"] = hashlib.sha256(source).hexdigest()
    if args.source_report.read_bytes() != source:
        raise AssertionError("source changed during replay")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({"modelRequests": 0, "sourceUnchanged": True, "accounts": [
        {"account": a["account"], "audience": [a["audience"]["beforeAccepted"],
                                               a["audience"]["afterAccepted"]],
         "feedback": [len(a["feedback"]["before"]), len(a["feedback"]["after"])],
         "newReviewCopyIds": a["feedback"]["newReviewCopyIds"]}
        for a in result["accounts"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

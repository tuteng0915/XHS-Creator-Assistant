"""Prepare an offline temporal holdout, without calling models or the product API.

Run from the repository root with backend/.venv/bin/python. Inputs and held-out
answers are stored separately; pass only inputs.json to a future evaluation runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.creator_analysis_scope import note_published_at  # noqa: E402


def prepare_case(profile: dict, target_id: str) -> tuple[dict, dict]:
    notes = profile.get("notes", [])
    ids = [str(n.get("noteId", "")) for n in notes]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("笔记需要非空且唯一的 noteId")
    target = next((n for n in notes if str(n.get("noteId")) == target_id), None)
    if target is None or (cutoff := note_published_at(target)) is None:
        raise ValueError("目标笔记不存在或缺少有效发布时间")
    answer_texts = {str(c.get("content", "")).strip() for c in target.get("comments", [])}
    history = []
    omitted_comments = 0
    seen = set()
    for note in notes:
        date = note_published_at(note)
        if note is target or date is None or date >= cutoff:
            continue
        comments = []
        for c in note.get("comments", []):
            text = str(c.get("content", "")).strip()
            timestamp = note_published_at({"publishedAt": c.get("createTime")})
            if (timestamp is None or timestamp >= cutoff or not text
                    or text in answer_texts or text in seen):
                omitted_comments += 1
                continue
            seen.add(text)
            comments.append({
                "commentId": c.get("commentId"), "content": text,
                "createTime": c.get("createTime"),
            })
        history.append({
            "noteId": note["noteId"], "publishedAt": note.get("publishedAt"),
            "title": note.get("title", ""), "desc": note.get("desc", ""),
            "comments": comments,
        })
    if not history:
        raise ValueError("没有目标发布前的有效历史笔记，不能构造时序回测")
    # Rebuild from a whitelist: no global profileText, diagnosis, metrics or derived persona.
    inputs = {
        "caseId": target_id, "cutoff": cutoff.isoformat(),
        "stimulus": {"title": target.get("title", ""), "body": target.get("desc", "")},
        "history": {"notes": history},
        "limitations": ["只评估文字；缺失时间、未来或重复评论被排除。",
                        "已有历史文本可能进入模型训练，不能替代前瞻验证。"],
        "omittedComments": omitted_comments,
    }
    answers = {
        "caseId": target_id,
        "observedComments": [
            {"commentId": c.get("commentId"), "content": c.get("content", ""),
             "createTime": c.get("createTime")}
            for c in target.get("comments", [])
        ],
        "limitations": "已采集评论不是全量反应，未出现的问题不一定不存在。",
    }
    return inputs, answers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="xhs-creator-profile/v1 JSON")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="新的独立研究目录")
    args = parser.parse_args()
    inputs, answers = prepare_case(json.loads(args.profile.read_text(encoding="utf-8")), args.target_id)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in [("inputs.json", inputs), ("heldout-answers.json", answers)]:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已创建离线案例；未调用模型。heldout-answers.json 不得作为模型输入。")


if __name__ == "__main__":
    main()

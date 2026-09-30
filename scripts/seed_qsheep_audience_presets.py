"""Explicitly pre-save evidence-linked QSheep reader hypotheses. No network or model calls.

Run with backend/.venv/bin/python scripts/seed_qsheep_audience_presets.py --source-id ID.
The database is backed up before migration; repeated runs preserve existing edits/archives.
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.db.database import SQLiteDatabase  # noqa: E402
from app.services.audience_presets import save_curated_fans  # noqa: E402


# IDs identify the actual saved examples; quotes are loaded from that account, not invented.
PRESETS = [
    {
        "id": "application_planning", "name": "申请规划型",
        "profile": "从申请时间线、DIY 路径和后续职业选择的角度阅读；身份和阶段未知。",
        "coreConcern": "申请如何安排、经历如何转化为下一步行动。",
        "contentPreference": "带适用条件的时间线、决策过程和具体步骤。",
        "expressionStyle": "先问一个具体问题；缺少步骤时追问，不默认赞同。",
        "commentIds": ["691e6e3e00000000390028db", "6949301300000000380113bb"],
    },
    {
        "id": "practical_tools", "name": "工具实用型",
        "profile": "从价格、练习量和方法可操作性的角度阅读工具分享，不推断消费能力。",
        "coreConcern": "是否免费、需要做多少练习、怎样判断适不适合自己。",
        "contentPreference": "工具条件、使用步骤、局限及可复现示例。",
        "expressionStyle": "短句询问成本或操作；有用时可能收藏，也可以不评论。",
        "commentIds": ["68ea75560000000039020c5b", "68eca145000000003902d26c"],
    },
    {
        "id": "experience_resonance", "name": "经历共鸣型",
        "profile": "关注放弃既定路线、内耗和自我探索的叙述；只视为阅读需求，不假定处境相同。",
        "coreConcern": "如何理解选择的代价、下一步如何安排。",
        "contentPreference": "真实取舍、尚未解决的困惑及克制的经验表达。",
        "expressionStyle": "可能表达共鸣再追问，也可能对成功学式结论保持距离。",
        "commentIds": ["668df961000000001b010277", "668dd6e50000000009017570"],
    },
    {
        "id": "detail_checking", "name": "细节求证型",
        "profile": "会核对排名、成绩等具体说法；不推断质疑者的动机或身份。",
        "coreConcern": "表述口径是否一致、关键事实是否有足够解释。",
        "contentPreference": "明确范围、条件和来源，区分事实与个人感受。",
        "expressionStyle": "发现疑点时直接提问；没有疑点不强行制造反对意见。",
        "commentIds": ["668ec70500000000160260cf", "668e26b50000000017001459"],
    },
    {
        "id": "course_discussion", "name": "课程讨论型",
        "profile": "关注专业课程的讨论内容及考试体验；不预设读者学历或就读院校。",
        "coreConcern": "实际学什么、如何讨论、课程要求是什么。",
        "contentPreference": "具体课堂话题、学习体验和制度细节。",
        "expressionStyle": "围绕一个课程细节追问或补充经验，不凭空声称自己修过课。",
        "commentIds": ["691d17d50000000039002c49", "691d1302000000003803ff67"],
    },
]


def build_groups(profile):
    sources = {}
    for note in profile.get("notes", []):
        for comment in note.get("comments", [])[:50]:
            if comment.get("commentId"):
                sources[comment["commentId"]] = (note["noteId"], comment.get("content", ""))
    groups = []
    for preset in PRESETS:
        group = {k: v for k, v in preset.items() if k != "commentIds"}
        refs = []
        for comment_id in preset["commentIds"]:
            if comment_id not in sources or not sources[comment_id][1].strip():
                raise ValueError("当前档案缺少预置所需的 QSheep 评论，未导入")
            note_id, content = sources[comment_id]
            refs.append({"noteId": note_id, "commentId": comment_id,
                         "sourceType": "comment", "quote": content[:1000]})
        group.update(evidenceRefs=refs, unknowns=[
            "角色是否对应真实粉丝及其人数比例未知", "年龄、性别、职业和教育背景不作推断",
            "阅读偏好及表达习惯是待验证的模拟设定",
        ])
        groups.append(group)
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    path = args.database or Settings.from_environment().database_path
    if not path.is_file():
        raise ValueError("数据库不存在")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT text_content FROM source_materials "
                                 "WHERE id=? AND type='xhs_creator_profile'", (args.source_id,)).fetchone()
        if row is None:
            raise ValueError("创作者档案不存在")
        groups = build_groups(json.loads(row[0]))
        backup = path.parent / "backups" / (
            "before-audience-presets-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3"
        )
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as target:
            connection.backup(target)
    finally:
        connection.close()
    database = SQLiteDatabase(path)
    database.migrate()
    fans = save_curated_fans(database, args.source_id, "qsheep-readers-v1", groups)
    print(json.dumps({"backup": str(backup), "count": len(fans),
                      "names": [f.editable.name for f in fans]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

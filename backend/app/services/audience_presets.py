"""Explicit local curation, never an automatic or model-backed analysis fallback."""
import json
from uuid import NAMESPACE_URL, uuid5

from app.errors import ValidationError
from app.services.audience_analyses import validate_audience_output
from app.services.audience_evidence import audience_context
from app.services.common import utc_now
from app.services.simulated_fans import FanDefinition, SimulatedFanService


def save_curated_fans(database, source_material_id: str, preset_key: str, groups: list[dict]):
    """Atomically save an attributed curation record and its fans; repeats never overwrite."""
    run_id = str(uuid5(NAMESPACE_URL, f"sqs:audience-preset:{source_material_id}:{preset_key}"))
    fans = SimulatedFanService(database)
    with database.transaction() as c:
        source = c.execute(
            "SELECT * FROM source_materials WHERE id=? AND type='xhs_creator_profile'",
            (source_material_id,),
        ).fetchone()
        if source is None:
            raise ValidationError("创作者档案不存在")
        existing = c.execute("SELECT * FROM audience_analyses WHERE id=?", (run_id,)).fetchone()
        if existing:
            result = json.loads(existing["result_json"])
            snapshot = json.loads(existing["input_snapshot_json"])
        else:
            profile = json.loads(source["text_content"])
            notes = profile.get("notes", [])
            snapshot = {
                "creator": profile.get("creator", {}), "notes": notes,
                "scope": {"scope": "all", "selectedNoteCount": len(notes)},
                "sourceMaterialId": source_material_id,
            }
            output = {
                "summary": f"预置整理：{len(groups)} 种阅读视角，依据已保存评论。",
                "limitations": "由开发侧基于评论整理的模拟假设，非模型接口分析；"
                "引用只证明该表达曾出现，不证明角色身份、粉丝比例或预测准确性。"
                "表达习惯是创作设定，不是对真实用户的测量。",
                "groups": groups,
            }
            result, diagnostics = validate_audience_output(output, audience_context(snapshot))
            if not result or diagnostics["rejectedGroups"]:
                raise ValidationError("预置角色引用核验失败，未写入任何角色")
            result["origin"] = "curated_preset"
            styles = {g["id"]: g.get("expressionStyle", "") for g in groups}
            for group in result["groups"]:
                group["expressionStyle"] = styles[group["id"]]
                FanDefinition.model_validate(group)
            now = utc_now()
            c.execute(
                "INSERT INTO audience_analyses(id,workspace_id,source_material_id,status,"
                "input_snapshot_json,result_json,model_metadata_json,diagnostics_json,"
                "created_at,completed_at) VALUES(?,?,?,'completed',?,?,?,?,?,?)",
                (run_id, source["workspace_id"], source_material_id,
                 json.dumps(snapshot, ensure_ascii=False), json.dumps(result, ensure_ascii=False),
                 json.dumps({"origin": "curated_preset", "presetKey": preset_key,
                             "modelCalled": False, "author": "developer_assisted_curation"}),
                 json.dumps(diagnostics, ensure_ascii=False), now, now),
            )
        saved = [fans.response(fans._save_group(
            c, source["workspace_id"], run_id, group, result, snapshot,
        )) for group in result["groups"]]
    return saved

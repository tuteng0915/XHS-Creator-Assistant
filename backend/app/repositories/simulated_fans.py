import json
from uuid import uuid4

from app.errors import ConflictError, NotFoundError
from app.services.common import utc_now


class SimulatedFanRepository:
    def list(self, c, workspace_id):
        return [dict(r) for r in c.execute(
            "SELECT * FROM simulated_fans WHERE workspace_id=? ORDER BY created_at,id",
            (workspace_id,),
        )]

    def get(self, c, fan_id):
        row = c.execute("SELECT * FROM simulated_fans WHERE id=?", (fan_id,)).fetchone()
        if row is None:
            raise NotFoundError("模拟粉丝不存在")
        return dict(row)

    def create(self, c, workspace_id, analysis_id, group_id, original, editable):
        existing = c.execute(
            "SELECT id FROM simulated_fans WHERE workspace_id=? AND source_analysis_id=? "
            "AND source_group_id=?", (workspace_id, analysis_id, group_id),
        ).fetchone()
        if existing:
            return self.get(c, existing["id"])
        fan_id, now = str(uuid4()), utc_now()
        c.execute(
            "INSERT INTO simulated_fans(id,workspace_id,source_analysis_id,source_group_id,"
            "original_json,editable_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (fan_id, workspace_id, analysis_id, group_id, json.dumps(original, ensure_ascii=False),
             json.dumps(editable, ensure_ascii=False), now, now),
        )
        return self.get(c, fan_id)

    def update(self, c, fan_id, editable, status, expected_updated_at):
        changed = c.execute(
            "UPDATE simulated_fans SET editable_json=?,status=?,updated_at=? "
            "WHERE id=? AND updated_at=?",
            (json.dumps(editable, ensure_ascii=False), status, utc_now(),
             fan_id, expected_updated_at),
        ).rowcount
        if not changed:
            raise ConflictError("模拟粉丝已被修改，请重新打开后再保存")
        return self.get(c, fan_id)

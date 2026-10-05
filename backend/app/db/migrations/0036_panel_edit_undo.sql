BEGIN IMMEDIATE;
CREATE TABLE panel_edit_proposals_next (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    simulation_id TEXT NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    request_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','applied','rejected','undone')),
    receipt_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    undo_receipt_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(workspace_id, request_key)
);
INSERT INTO panel_edit_proposals_next (
    id, workspace_id, simulation_id, topic_id, request_key, request_json,
    snapshot_json, status, receipt_json, created_at, updated_at
) SELECT id, workspace_id, simulation_id, topic_id, request_key, request_json,
    snapshot_json, status, receipt_json, created_at, updated_at FROM panel_edit_proposals;
DROP TABLE panel_edit_proposals;
ALTER TABLE panel_edit_proposals_next RENAME TO panel_edit_proposals;
CREATE INDEX panel_edit_by_run ON panel_edit_proposals(workspace_id, simulation_id, created_at);
COMMIT;

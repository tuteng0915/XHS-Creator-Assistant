ALTER TABLE topics ADD COLUMN body TEXT NOT NULL DEFAULT '';
ALTER TABLE topics ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
CREATE TABLE audience_analyses (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    source_material_id TEXT NOT NULL REFERENCES source_materials(id),
    status TEXT NOT NULL DEFAULT 'pending',
    input_snapshot_json TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    model_metadata_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX audience_workspace_history ON audience_analyses(workspace_id, created_at DESC);

CREATE TABLE simulated_fans (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    source_analysis_id TEXT NOT NULL REFERENCES audience_analyses(id),
    source_group_id TEXT NOT NULL,
    original_json TEXT NOT NULL,
    editable_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, source_analysis_id, source_group_id)
);
CREATE INDEX idx_simulated_fans_workspace ON simulated_fans(workspace_id, created_at);

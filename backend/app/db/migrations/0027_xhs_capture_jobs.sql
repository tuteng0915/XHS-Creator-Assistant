CREATE TABLE IF NOT EXISTS xhs_capture_jobs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    profile_url TEXT NOT NULL,
    resolved_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (
        status IN (
            'pending',
            'waiting_for_login',
            'running',
            'processing',
            'completed',
            'failed'
        )
    ),
    note_limit INTEGER NOT NULL,
    include_comments INTEGER NOT NULL DEFAULT 1,
    status_message TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    result_input_asset_id TEXT REFERENCES source_materials(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_xhs_capture_jobs_workspace_created
ON xhs_capture_jobs(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_xhs_capture_jobs_status
ON xhs_capture_jobs(status);


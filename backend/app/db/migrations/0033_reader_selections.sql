CREATE TABLE reader_selections (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    request_key TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'running', 'completed', 'partially_completed', 'failed'
    )),
    claim_token TEXT,
    result_json TEXT,
    error_code TEXT,
    model_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(workspace_id, request_key)
);
CREATE INDEX idx_reader_selections_pending ON reader_selections(status, created_at, id);

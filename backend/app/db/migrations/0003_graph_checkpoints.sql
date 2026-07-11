CREATE TABLE graph_checkpoints (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL,
    workflow_type TEXT NOT NULL CHECK(workflow_type IN ('account_diagnosis', 'trend_analysis', 'audience_simulation')),
    node_key TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_graph_checkpoints_run_created
ON graph_checkpoints(analysis_run_id, created_at DESC);

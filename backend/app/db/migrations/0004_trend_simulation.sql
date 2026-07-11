CREATE TABLE graph_checkpoints_next (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL,
    workflow_type TEXT NOT NULL CHECK(workflow_type IN ('account_diagnosis', 'trend_analysis', 'audience_simulation')),
    node_key TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO graph_checkpoints_next(
    id, analysis_run_id, workflow_type, node_key, state_json, created_at
)
SELECT id, analysis_run_id, workflow_type, node_key, state_json, created_at
FROM graph_checkpoints;

DROP TABLE graph_checkpoints;

ALTER TABLE graph_checkpoints_next RENAME TO graph_checkpoints;

CREATE INDEX idx_graph_checkpoints_run_created
ON graph_checkpoints(analysis_run_id, created_at DESC);

CREATE TABLE simulation_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'partially_completed', 'failed')),
    input_snapshot_json TEXT NOT NULL,
    persona_definitions_json TEXT NOT NULL DEFAULT '[]',
    reaction_results_json TEXT NOT NULL DEFAULT '[]',
    debate_results_json TEXT NOT NULL DEFAULT '[]',
    synthesis_json TEXT NOT NULL DEFAULT '{}',
    stage_errors_json TEXT NOT NULL DEFAULT '{}',
    model_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_simulation_runs_workspace_updated
ON simulation_runs(workspace_id, updated_at DESC);

CREATE INDEX idx_simulation_runs_topic
ON simulation_runs(topic_id);

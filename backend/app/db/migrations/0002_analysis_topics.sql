CREATE TABLE analysis_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    workflow_type TEXT NOT NULL CHECK(workflow_type IN ('account_diagnosis', 'trend_analysis')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'partially_completed', 'failed')),
    input_snapshot_json TEXT NOT NULL,
    stage_results_json TEXT NOT NULL DEFAULT '{}',
    stage_errors_json TEXT NOT NULL DEFAULT '{}',
    model_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_analysis_runs_workspace_updated
ON analysis_runs(workspace_id, updated_at DESC);

CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    angle TEXT NOT NULL DEFAULT '',
    associated_pain_point TEXT NOT NULL DEFAULT '',
    why_it_fits TEXT NOT NULL DEFAULT '',
    source_analysis_run_id TEXT REFERENCES analysis_runs(id) ON DELETE SET NULL,
    source_workflow TEXT NOT NULL CHECK(source_workflow IN ('account_diagnosis', 'trend_analysis', 'manual')),
    status TEXT NOT NULL CHECK(status IN ('candidate', 'selected', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_topics_workspace_updated
ON topics(workspace_id, updated_at DESC);

CREATE INDEX idx_topics_source_run
ON topics(source_analysis_run_id);

CREATE TABLE workspace_current_topics (
    workspace_id TEXT PRIMARY KEY REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    updated_at TEXT NOT NULL
);

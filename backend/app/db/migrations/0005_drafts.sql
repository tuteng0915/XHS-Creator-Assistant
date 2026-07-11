CREATE TABLE drafts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    source_analysis_run_id TEXT REFERENCES analysis_runs(id) ON DELETE SET NULL,
    source_workflow TEXT NOT NULL CHECK(source_workflow IN ('account_diagnosis', 'trend_analysis', 'manual')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    generated_snapshot_json TEXT NOT NULL,
    editable_content_json TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    stage_errors_json TEXT NOT NULL DEFAULT '{}',
    model_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_drafts_workspace_updated
ON drafts(workspace_id, updated_at DESC);

CREATE INDEX idx_drafts_topic
ON drafts(topic_id, updated_at DESC);

CREATE INDEX idx_drafts_source_run
ON drafts(source_analysis_run_id);

CREATE TABLE simulation_runs_next (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
    draft_id TEXT REFERENCES drafts(id) ON DELETE SET NULL,
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

INSERT INTO simulation_runs_next(
    id, workspace_id, topic_id, draft_id, status, input_snapshot_json,
    persona_definitions_json, reaction_results_json, debate_results_json,
    synthesis_json, stage_errors_json, model_metadata_json,
    created_at, started_at, completed_at, updated_at
)
SELECT
    id, workspace_id, topic_id, NULL, status, input_snapshot_json,
    persona_definitions_json, reaction_results_json, debate_results_json,
    synthesis_json, stage_errors_json, model_metadata_json,
    created_at, started_at, completed_at, updated_at
FROM simulation_runs;

DROP TABLE simulation_runs;

ALTER TABLE simulation_runs_next RENAME TO simulation_runs;

CREATE INDEX idx_simulation_runs_workspace_updated
ON simulation_runs(workspace_id, updated_at DESC);

CREATE INDEX idx_simulation_runs_topic
ON simulation_runs(topic_id);

CREATE INDEX idx_simulation_runs_draft
ON simulation_runs(draft_id);

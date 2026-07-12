PRAGMA foreign_keys = OFF;

CREATE TABLE source_materials_new (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN (
        'historical_posts',
        'comments',
        'trend_csv',
        'video_creator_samples'
    )),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    text_content TEXT,
    keyword TEXT,
    original_filename TEXT,
    stored_key TEXT,
    media_type TEXT,
    byte_size INTEGER,
    sha256 TEXT,
    row_count INTEGER,
    preview_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    CHECK (
        (type IN ('historical_posts', 'comments', 'video_creator_samples')
            AND text_content IS NOT NULL
            AND stored_key IS NULL)
        OR
        (type = 'trend_csv'
            AND text_content IS NULL
            AND keyword IS NOT NULL
            AND original_filename IS NOT NULL
            AND stored_key IS NOT NULL
            AND media_type IS NOT NULL
            AND byte_size IS NOT NULL
            AND sha256 IS NOT NULL
            AND row_count IS NOT NULL
            AND preview_json IS NOT NULL
            AND json_valid(preview_json))
    )
);

INSERT INTO source_materials_new
SELECT * FROM source_materials;

DROP TABLE source_materials;
ALTER TABLE source_materials_new RENAME TO source_materials;

CREATE INDEX idx_source_materials_workspace_type
    ON source_materials(workspace_id, type, updated_at DESC);

CREATE TABLE analysis_runs_new (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    workflow_type TEXT NOT NULL CHECK(workflow_type IN (
        'account_diagnosis',
        'trend_analysis',
        'video_creator_quality'
    )),
    status TEXT NOT NULL CHECK(status IN (
        'pending',
        'running',
        'completed',
        'partially_completed',
        'failed'
    )),
    input_snapshot_json TEXT NOT NULL,
    stage_results_json TEXT NOT NULL DEFAULT '{}',
    stage_errors_json TEXT NOT NULL DEFAULT '{}',
    model_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

INSERT INTO analysis_runs_new
SELECT * FROM analysis_runs;

DROP TABLE analysis_runs;
ALTER TABLE analysis_runs_new RENAME TO analysis_runs;

CREATE INDEX idx_analysis_runs_workspace_updated
    ON analysis_runs(workspace_id, updated_at DESC);

CREATE TABLE graph_checkpoints_new (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL,
    workflow_type TEXT NOT NULL CHECK(workflow_type IN (
        'account_diagnosis',
        'trend_analysis',
        'audience_simulation',
        'video_creator_quality'
    )),
    node_key TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO graph_checkpoints_new
SELECT * FROM graph_checkpoints;

DROP TABLE graph_checkpoints;
ALTER TABLE graph_checkpoints_new RENAME TO graph_checkpoints;

CREATE INDEX idx_graph_checkpoints_run_created
    ON graph_checkpoints(analysis_run_id, created_at DESC);

PRAGMA foreign_keys = ON;

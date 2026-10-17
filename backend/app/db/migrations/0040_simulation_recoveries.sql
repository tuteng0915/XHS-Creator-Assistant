BEGIN IMMEDIATE;
CREATE TABLE simulation_recoveries (
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    request_key TEXT NOT NULL,
    source_run_id TEXT NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    stage_key TEXT NOT NULL,
    recovery_run_id TEXT NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    PRIMARY KEY (workspace_id, request_key)
);
CREATE INDEX simulation_recovery_unit ON simulation_recoveries(source_run_id, stage_key);
COMMIT;

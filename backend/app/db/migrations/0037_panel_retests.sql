BEGIN IMMEDIATE;
ALTER TABLE simulation_runs ADD COLUMN parent_simulation_id TEXT
    REFERENCES simulation_runs(id);
ALTER TABLE simulation_runs ADD COLUMN retest_request_key TEXT;
ALTER TABLE simulation_runs ADD COLUMN retest_request_hash TEXT;
CREATE UNIQUE INDEX simulation_retest_request
    ON simulation_runs(workspace_id, retest_request_key)
    WHERE retest_request_key IS NOT NULL;
CREATE INDEX simulation_retest_parent ON simulation_runs(parent_simulation_id);
COMMIT;

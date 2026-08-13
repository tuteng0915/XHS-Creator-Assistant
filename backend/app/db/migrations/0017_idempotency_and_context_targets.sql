ALTER TABLE analysis_runs
ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX idx_analysis_runs_workspace_idempotency
ON analysis_runs(workspace_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

ALTER TABLE agent_conversations
ADD COLUMN context_target_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(context_target_json));

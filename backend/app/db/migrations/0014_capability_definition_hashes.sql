ALTER TABLE workspace_skills
ADD COLUMN definition_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE workspace_agents
ADD COLUMN definition_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE workspace_workflows
ADD COLUMN definition_hash TEXT NOT NULL DEFAULT '';

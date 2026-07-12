PRAGMA foreign_keys = OFF;

CREATE TABLE workspace_skills_new (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    category TEXT NOT NULL CHECK(length(trim(category)) > 0),
    purpose TEXT NOT NULL,
    trigger_intents_json TEXT NOT NULL CHECK(json_valid(trigger_intents_json)),
    required_inputs_json TEXT NOT NULL CHECK(json_valid(required_inputs_json)),
    optional_inputs_json TEXT NOT NULL CHECK(json_valid(optional_inputs_json)),
    context_policy_json TEXT NOT NULL CHECK(json_valid(context_policy_json)),
    output_schema_json TEXT NOT NULL CHECK(json_valid(output_schema_json)),
    artifact_effect TEXT NOT NULL,
    side_effects_json TEXT NOT NULL CHECK(json_valid(side_effects_json)),
    failure_mode TEXT NOT NULL,
    composable_with_json TEXT NOT NULL CHECK(json_valid(composable_with_json)),
    implementation_refs_json TEXT NOT NULL CHECK(json_valid(implementation_refs_json)),
    source TEXT NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin', 'generated')),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    version TEXT NOT NULL DEFAULT 'v1',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    UNIQUE(workspace_id, skill_id)
);

INSERT INTO workspace_skills_new
SELECT * FROM workspace_skills;

DROP TABLE workspace_skills;
ALTER TABLE workspace_skills_new RENAME TO workspace_skills;

CREATE INDEX idx_workspace_skills_workspace_category
    ON workspace_skills(workspace_id, category, skill_id);

CREATE TABLE workspace_agents_new (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    purpose TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    skill_ids_json TEXT NOT NULL CHECK(json_valid(skill_ids_json)),
    default_context_policy_json TEXT NOT NULL CHECK(json_valid(default_context_policy_json)),
    source TEXT NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin', 'generated')),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    version TEXT NOT NULL DEFAULT 'v1',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    UNIQUE(workspace_id, agent_id)
);

INSERT INTO workspace_agents_new
SELECT * FROM workspace_agents;

DROP TABLE workspace_agents;
ALTER TABLE workspace_agents_new RENAME TO workspace_agents;

CREATE INDEX idx_workspace_agents_workspace
    ON workspace_agents(workspace_id, agent_id);

CREATE TABLE workspace_workflows_new (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    purpose TEXT NOT NULL,
    entry_agent_ids_json TEXT NOT NULL CHECK(json_valid(entry_agent_ids_json)),
    agent_plan_json TEXT NOT NULL CHECK(json_valid(agent_plan_json)),
    artifact_effect TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin', 'generated')),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    version TEXT NOT NULL DEFAULT 'v1',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    UNIQUE(workspace_id, workflow_id)
);

INSERT INTO workspace_workflows_new
SELECT * FROM workspace_workflows;

DROP TABLE workspace_workflows;
ALTER TABLE workspace_workflows_new RENAME TO workspace_workflows;

CREATE INDEX idx_workspace_workflows_workspace
    ON workspace_workflows(workspace_id, workflow_id);

PRAGMA foreign_keys = ON;

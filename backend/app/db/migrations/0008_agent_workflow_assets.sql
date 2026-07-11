CREATE TABLE workspace_agents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    purpose TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    skill_ids_json TEXT NOT NULL CHECK(json_valid(skill_ids_json)),
    default_context_policy_json TEXT NOT NULL CHECK(json_valid(default_context_policy_json)),
    source TEXT NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin')),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    version TEXT NOT NULL DEFAULT 'v1',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    UNIQUE(workspace_id, agent_id)
);

CREATE INDEX idx_workspace_agents_workspace
    ON workspace_agents(workspace_id, agent_id);

CREATE TABLE workspace_workflows (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    purpose TEXT NOT NULL,
    entry_agent_ids_json TEXT NOT NULL CHECK(json_valid(entry_agent_ids_json)),
    agent_plan_json TEXT NOT NULL CHECK(json_valid(agent_plan_json)),
    artifact_effect TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin')),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    version TEXT NOT NULL DEFAULT 'v1',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    UNIQUE(workspace_id, workflow_id)
);

CREATE INDEX idx_workspace_workflows_workspace
    ON workspace_workflows(workspace_id, workflow_id);

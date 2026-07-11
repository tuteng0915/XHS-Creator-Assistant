CREATE TABLE agent_conversations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_asset_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    FOREIGN KEY(agent_asset_id) REFERENCES workspace_agents(id) ON DELETE RESTRICT
);

CREATE INDEX idx_agent_conversations_workspace
    ON agent_conversations(workspace_id, updated_at DESC);

CREATE INDEX idx_agent_conversations_agent
    ON agent_conversations(agent_asset_id, updated_at DESC);

CREATE TABLE agent_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    context_pack_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(context_pack_json)),
    asset_refs_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(asset_refs_json)),
    proposed_actions_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(proposed_actions_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE
);

CREATE INDEX idx_agent_messages_conversation
    ON agent_messages(conversation_id, created_at, id);

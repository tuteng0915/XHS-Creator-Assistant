CREATE TABLE asset_proposals (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK(length(trim(action_type)) > 0),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'applied', 'rejected', 'failed')),
    proposed_action_json TEXT NOT NULL CHECK(json_valid(proposed_action_json)),
    result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)),
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    applied_at TEXT,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    FOREIGN KEY(conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE,
    FOREIGN KEY(message_id) REFERENCES agent_messages(id) ON DELETE CASCADE
);

CREATE INDEX idx_asset_proposals_workspace
    ON asset_proposals(workspace_id, created_at DESC);

CREATE INDEX idx_asset_proposals_conversation
    ON asset_proposals(conversation_id, created_at DESC);

CREATE INDEX idx_asset_proposals_message
    ON asset_proposals(message_id);

CREATE TABLE agent_conversation_jobs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    assistant_message_id TEXT NOT NULL,
    user_content TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('demo', 'live')),
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE,
    FOREIGN KEY(assistant_message_id) REFERENCES agent_messages(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_agent_conversation_jobs_assistant_message
ON agent_conversation_jobs(assistant_message_id);

CREATE INDEX idx_agent_conversation_jobs_unfinished
ON agent_conversation_jobs(status, created_at, id)
WHERE status IN ('queued', 'running');


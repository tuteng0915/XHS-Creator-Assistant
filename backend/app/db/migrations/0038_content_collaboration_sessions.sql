-- Product records for the bounded creator/research/writing/review collaboration
-- flow.  These are intentionally separate from the legacy single-agent chat
-- tables: a collaboration session has a fixed Topic target, append-only
-- addressed messages, and short-lived execution runs.

CREATE TABLE content_collaboration_sessions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    context_target_type TEXT NOT NULL CHECK(context_target_type IN ('topic')),
    context_target_id TEXT NOT NULL,
    initial_context_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(initial_context_snapshot_json)),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
    execution_status TEXT NOT NULL DEFAULT 'idle' CHECK(execution_status IN (
        'idle', 'queued', 'running', 'waiting_creator', 'completed', 'failed'
    )),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    create_request_key TEXT,
    create_request_fingerprint TEXT,
    failure_code TEXT NOT NULL DEFAULT '',
    failure_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_message_at TEXT,
    completed_at TEXT,
    CHECK(
        (create_request_key IS NULL AND create_request_fingerprint IS NULL)
        OR (
            create_request_key IS NOT NULL
            AND length(trim(create_request_key)) > 0
            AND create_request_fingerprint IS NOT NULL
            AND length(trim(create_request_fingerprint)) > 0
        )
    )
);

CREATE UNIQUE INDEX idx_content_collaboration_sessions_create_request
    ON content_collaboration_sessions(workspace_id, create_request_key)
    WHERE create_request_key IS NOT NULL;

CREATE INDEX idx_content_collaboration_sessions_workspace_updated
    ON content_collaboration_sessions(workspace_id, updated_at DESC, id);

CREATE INDEX idx_content_collaboration_sessions_workspace_target
    ON content_collaboration_sessions(workspace_id, context_target_type, context_target_id, updated_at DESC);

CREATE TABLE content_collaboration_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES content_collaboration_sessions(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK(sequence_no > 0),
    sender_role TEXT NOT NULL CHECK(sender_role IN ('creator', 'research', 'writing', 'review', 'system')),
    recipient_role TEXT CHECK(recipient_role IN ('creator', 'research', 'writing', 'review')),
    content TEXT NOT NULL CHECK(length(trim(content)) > 0),
    reply_to_message_id TEXT REFERENCES content_collaboration_messages(id) ON DELETE CASCADE,
    artifact_refs_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(artifact_refs_json)),
    context_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(context_snapshot_json)),
    model_metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(model_metadata_json)),
    client_request_key TEXT,
    client_request_fingerprint TEXT,
    created_at TEXT NOT NULL,
    CHECK(
        (client_request_key IS NULL AND client_request_fingerprint IS NULL)
        OR (
            sender_role = 'creator'
            AND client_request_key IS NOT NULL
            AND length(trim(client_request_key)) > 0
            AND client_request_fingerprint IS NOT NULL
            AND length(trim(client_request_fingerprint)) > 0
        )
    ),
    UNIQUE(session_id, sequence_no)
);

CREATE UNIQUE INDEX idx_content_collaboration_messages_client_request
    ON content_collaboration_messages(session_id, client_request_key)
    WHERE client_request_key IS NOT NULL;

CREATE INDEX idx_content_collaboration_messages_session_sequence
    ON content_collaboration_messages(session_id, sequence_no);

CREATE TABLE content_collaboration_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES content_collaboration_sessions(id) ON DELETE CASCADE,
    trigger_message_id TEXT REFERENCES content_collaboration_messages(id) ON DELETE RESTRICT,
    request_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL CHECK(json_valid(input_snapshot_json)),
    graph_state_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(graph_state_json)),
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'waiting_creator', 'completed', 'failed')),
    claim_token TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    error_code TEXT NOT NULL DEFAULT '',
    error_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK(length(trim(request_key)) > 0),
    CHECK(length(trim(request_fingerprint)) > 0),
    UNIQUE(session_id, request_key)
);

CREATE UNIQUE INDEX idx_content_collaboration_runs_trigger_message
    ON content_collaboration_runs(trigger_message_id)
    WHERE trigger_message_id IS NOT NULL;

CREATE INDEX idx_content_collaboration_runs_status
    ON content_collaboration_runs(status, created_at, id);

CREATE INDEX idx_content_collaboration_runs_session_updated
    ON content_collaboration_runs(session_id, updated_at DESC, id);

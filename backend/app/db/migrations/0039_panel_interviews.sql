-- Follow-up conversations are separate from the immutable initial reading.
CREATE TABLE panel_interviews (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    simulation_id TEXT NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    request_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    question TEXT NOT NULL,
    recipient_persona_id TEXT,
    recipient_name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('demo', 'live')),
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'running', 'completed', 'partially_completed', 'failed', 'cancelled'
    )),
    context_json TEXT NOT NULL CHECK(json_valid(context_json)),
    failures_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(failures_json)),
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, request_key)
);

CREATE INDEX idx_panel_interviews_simulation
    ON panel_interviews(workspace_id, simulation_id, created_at);
CREATE UNIQUE INDEX idx_panel_interviews_active
    ON panel_interviews(simulation_id) WHERE status IN ('pending', 'running');

CREATE TABLE panel_interview_messages (
    id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES panel_interviews(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('author', 'reader')),
    persona_id TEXT,
    sender_name TEXT NOT NULL,
    recipient_persona_id TEXT,
    recipient_name TEXT NOT NULL,
    reply_to_id TEXT REFERENCES panel_interview_messages(id) ON DELETE CASCADE,
    content TEXT NOT NULL CHECK(length(trim(content)) > 0),
    model_metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(model_metadata_json)),
    created_at TEXT NOT NULL,
    UNIQUE(interview_id, persona_id)
);

CREATE INDEX idx_panel_interview_messages_order
    ON panel_interview_messages(interview_id, created_at);

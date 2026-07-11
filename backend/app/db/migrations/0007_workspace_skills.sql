CREATE TABLE workspace_skills (
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
    source TEXT NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin')),
    status TEXT NOT NULL DEFAULT 'enabled' CHECK(status IN ('enabled', 'disabled')),
    version TEXT NOT NULL DEFAULT 'v1',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    UNIQUE(workspace_id, skill_id)
);

CREATE INDEX idx_workspace_skills_workspace_category
    ON workspace_skills(workspace_id, category, skill_id);

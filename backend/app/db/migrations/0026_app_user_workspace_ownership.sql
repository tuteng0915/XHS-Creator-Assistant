CREATE TABLE IF NOT EXISTS app_users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_user_workspaces (
    user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, workspace_id),
    UNIQUE (workspace_id)
);

INSERT OR IGNORE INTO app_users(id, display_name, created_at, updated_at)
VALUES (
    'local-default-user',
    '本地默认用户',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

INSERT OR IGNORE INTO app_user_workspaces(user_id, workspace_id, created_at)
SELECT
    'local-default-user',
    workspace.id,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM creator_workspaces AS workspace;


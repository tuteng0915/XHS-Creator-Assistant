CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES creator_workspaces(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('image', 'video')),
    name TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL CHECK (source_type IN ('upload', 'url', 'generated', 'extracted_frame')),
    original_filename TEXT NOT NULL,
    stored_key TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    derived_json TEXT NOT NULL DEFAULT '{}',
    user_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_assets_workspace_type_updated
ON media_assets(workspace_id, type, updated_at DESC);

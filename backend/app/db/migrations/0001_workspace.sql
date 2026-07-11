CREATE TABLE creator_workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    platform TEXT NOT NULL DEFAULT 'xiaohongshu' CHECK(platform = 'xiaohongshu'),
    current_positioning_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(current_positioning_version_id) REFERENCES positioning_versions(id)
);

CREATE TABLE positioning_versions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    positioning_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, version_number),
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT
);

CREATE TABLE source_materials (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('historical_posts', 'comments', 'trend_csv')),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    text_content TEXT,
    keyword TEXT,
    original_filename TEXT,
    stored_key TEXT,
    media_type TEXT,
    byte_size INTEGER,
    sha256 TEXT,
    row_count INTEGER,
    preview_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES creator_workspaces(id) ON DELETE RESTRICT,
    CHECK (
        (type IN ('historical_posts', 'comments')
            AND text_content IS NOT NULL
            AND stored_key IS NULL)
        OR
        (type = 'trend_csv'
            AND text_content IS NULL
            AND keyword IS NOT NULL
            AND original_filename IS NOT NULL
            AND stored_key IS NOT NULL
            AND media_type IS NOT NULL
            AND byte_size IS NOT NULL
            AND sha256 IS NOT NULL
            AND row_count IS NOT NULL
            AND preview_json IS NOT NULL
            AND json_valid(preview_json))
    )
);

CREATE INDEX idx_positioning_versions_workspace
    ON positioning_versions(workspace_id, version_number DESC);
CREATE INDEX idx_source_materials_workspace_type
    ON source_materials(workspace_id, type, updated_at DESC);


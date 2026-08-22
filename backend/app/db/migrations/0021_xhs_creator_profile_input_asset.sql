PRAGMA foreign_keys = OFF;

CREATE TABLE source_materials_next (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN (
        'account_profile',
        'historical_posts',
        'comments',
        'trend_csv',
        'video_creator_samples',
        'xhs_creator_profile'
    )),
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
        (type IN (
            'account_profile',
            'historical_posts',
            'comments',
            'video_creator_samples',
            'xhs_creator_profile'
        )
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

INSERT INTO source_materials_next
SELECT * FROM source_materials;

DROP TABLE source_materials;
ALTER TABLE source_materials_next RENAME TO source_materials;

CREATE INDEX idx_source_materials_workspace_type
    ON source_materials(workspace_id, type, updated_at DESC);

PRAGMA foreign_keys = ON;

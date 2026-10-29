CREATE TABLE account_image_text_cache (
    workspace_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, cache_key)
);

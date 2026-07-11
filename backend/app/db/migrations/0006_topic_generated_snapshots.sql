ALTER TABLE topics
ADD COLUMN generated_snapshot_json TEXT NOT NULL DEFAULT '{}';

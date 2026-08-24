ALTER TABLE drafts
ADD COLUMN kind TEXT NOT NULL DEFAULT 'content_structure';

CREATE INDEX idx_drafts_workspace_kind_updated
ON drafts(workspace_id, kind, updated_at DESC);

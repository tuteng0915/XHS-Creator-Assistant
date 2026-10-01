ALTER TABLE xhs_capture_jobs
ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}';

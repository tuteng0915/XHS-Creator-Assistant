ALTER TABLE analysis_runs
ADD COLUMN user_notes TEXT NOT NULL DEFAULT '';

ALTER TABLE analysis_runs
ADD COLUMN review_status TEXT NOT NULL DEFAULT 'unreviewed';

ALTER TABLE simulation_runs
ADD COLUMN user_notes TEXT NOT NULL DEFAULT '';

ALTER TABLE simulation_runs
ADD COLUMN review_status TEXT NOT NULL DEFAULT 'unreviewed';

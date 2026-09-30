ALTER TABLE audience_analyses ADD COLUMN model_output_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE audience_analyses ADD COLUMN diagnostics_json TEXT NOT NULL DEFAULT '{}';

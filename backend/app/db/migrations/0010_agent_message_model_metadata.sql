ALTER TABLE agent_messages
ADD COLUMN model_metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(model_metadata_json));

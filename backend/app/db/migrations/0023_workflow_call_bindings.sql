ALTER TABLE workspace_workflows
ADD COLUMN call_binding TEXT NOT NULL DEFAULT ''
CHECK(call_binding IN ('', 'account', 'trend', 'video'));

UPDATE workspace_workflows
SET call_binding = 'account'
WHERE workflow_id = 'account_diagnosis';

UPDATE workspace_workflows
SET call_binding = 'trend'
WHERE workflow_id = 'trend_analysis';

UPDATE workspace_workflows
SET call_binding = 'video'
WHERE workflow_id = 'video_creator_quality';

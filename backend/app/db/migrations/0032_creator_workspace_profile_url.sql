ALTER TABLE creator_workspaces ADD COLUMN profile_url TEXT;

UPDATE creator_workspaces
SET profile_url = COALESCE(
    (
        SELECT CASE
            WHEN json_valid(material.text_content)
            THEN NULLIF(json_extract(material.text_content, '$.source.profileUrl'), '')
            ELSE NULL
        END
        FROM source_materials AS material
        WHERE material.workspace_id = creator_workspaces.id
          AND material.type = 'xhs_creator_profile'
        ORDER BY material.updated_at DESC
        LIMIT 1
    ),
    (
        SELECT COALESCE(NULLIF(job.resolved_url, ''), job.profile_url)
        FROM xhs_capture_jobs AS job
        WHERE job.workspace_id = creator_workspaces.id
          AND job.status = 'completed'
        ORDER BY job.completed_at DESC, job.created_at DESC
        LIMIT 1
    )
);

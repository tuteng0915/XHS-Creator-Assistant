from fastapi import FastAPI
from test_workspace_api import create_workspace, send


def test_workspace_skills_are_materialized_from_builtin_catalog(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)

    response = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills")

    assert response.status_code == 200
    skills = response.json()
    skill_ids = {skill["skillId"] for skill in skills}
    assert "analysis.profile_from_history" in skill_ids
    assert "topic.generate_from_account_diagnosis" in skill_ids
    assert "simulation.synthesize" in skill_ids
    assert "meta.design_skill_asset" in skill_ids
    assert "meta.design_agent_asset" in skill_ids
    assert "meta.design_workflow_asset" in skill_ids
    assert "input_asset.format_profile" in skill_ids
    assert "input_asset.format_historical_posts" in skill_ids
    assert "input_asset.format_comments" in skill_ids
    assert "input_asset.format_trend_csv_brief" in skill_ids
    assert "input_asset.format_video_creator_samples" in skill_ids
    assert "media.understand_image" in skill_ids
    assert "media.understand_video" in skill_ids
    assert "media.generate_image" in skill_ids
    assert "media.generate_video" in skill_ids
    skill_maker = next(
        skill for skill in skills if skill["skillId"] == "meta.design_skill_asset"
    )
    assert skill_maker["category"] == "meta"
    formatter = next(
        skill for skill in skills if skill["skillId"] == "input_asset.format_comments"
    )
    assert formatter["category"] == "input_asset"
    assert formatter["artifactEffect"] == "Draft InputAsset.comments"
    video_formatter = next(
        skill
        for skill in skills
        if skill["skillId"] == "input_asset.format_video_creator_samples"
    )
    assert video_formatter["displayName"] == (
        "Format Creator Dossier Video Creation Samples"
    )
    media_skill = next(skill for skill in skills if skill["skillId"] == "media.generate_image")
    assert media_skill["category"] == "media"
    assert media_skill["artifactEffect"] == "MediaAsset.image"
    assert all(skill["workspaceId"] == workspace["id"] for skill in skills)
    assert all(skill["source"] == "builtin" for skill in skills)


def test_skill_detail_and_editable_asset_fields(app: FastAPI) -> None:
    workspace = create_workspace(app)
    skills = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
    skill = next(
        item for item in skills if item["skillId"] == "analysis.profile_from_history"
    )

    detail = send(app, "GET", f"/api/skills/{skill['id']}")

    assert detail.status_code == 200
    body = detail.json()
    assert body["skillId"] == "analysis.profile_from_history"
    assert "positioning_snapshot" in body["requiredInputs"]
    assert body["contextPolicy"]["allowed_fields"] == [
        "positioning",
        "historicalPosts",
    ]
    assert body["artifactEffect"] == "AnalysisRun.stageResults.profile"

    updated = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}",
        json={
            "status": "disabled",
            "userNotes": "暂时不用于自动规划。",
            "expectedUpdatedAt": body["updatedAt"],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "disabled"
    assert updated.json()["userNotes"] == "暂时不用于自动规划。"

    stale = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}",
        json={
            "status": "enabled",
            "expectedUpdatedAt": body["updatedAt"],
        },
    )
    assert stale.status_code == 409


def test_builtin_skill_definition_updates_preserve_editable_fields(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    skill = next(
        item for item in send(
            app, "GET", f"/api/workspaces/{workspace['id']}/skills"
        ).json()
        if item["skillId"] == "analysis.profile_from_history"
    )

    with app.state.database.transaction() as connection:
        connection.execute(
            """
            UPDATE workspace_skills
            SET display_name = 'Stale Skill Name',
                definition_hash = 'stale',
                status = 'disabled',
                user_notes = 'keep this note'
            WHERE id = ?
            """,
            (skill["id"],),
        )

    refreshed = next(
        item for item in send(
            app, "GET", f"/api/workspaces/{workspace['id']}/skills"
        ).json()
        if item["skillId"] == "analysis.profile_from_history"
    )

    assert refreshed["displayName"] == "Analyze Account Profile"
    assert refreshed["status"] == "disabled"
    detail = send(app, "GET", f"/api/skills/{skill['id']}").json()
    assert detail["userNotes"] == "keep this note"


def test_input_asset_formatter_skill_can_be_invoked(app: FastAPI) -> None:
    workspace = create_workspace(app)
    skills = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
    formatter = next(
        item for item in skills if item["skillId"] == "input_asset.format_comments"
    )

    response = send(
        app,
        "POST",
        f"/api/skills/{formatter['id']}/invoke",
        json={
            "mode": "live",
            "input": {
                "rawText": '1. “太焦虑了，不知道怎么选校”\n2. 求时间线',
                "targetAssetType": "comments",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skillId"] == "input_asset.format_comments"
    assert body["status"] == "completed"
    assert body["output"]["name"] == "整理后的评论样本合集"
    assert body["output"]["content"] == "太焦虑了，不知道怎么选校\n求时间线"
    assert body["modelMetadata"]["provider"] == "code"


def test_non_callable_skill_returns_clear_error(app: FastAPI) -> None:
    workspace = create_workspace(app)
    skills = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
    analysis_skill = next(
        item for item in skills if item["skillId"] == "analysis.profile_from_history"
    )

    response = send(
        app,
        "POST",
        f"/api/skills/{analysis_skill['id']}/invoke",
        json={"input": {"rawText": "test"}},
    )

    assert response.status_code == 422
    assert "only supports direct invocation" in response.json()["detail"]

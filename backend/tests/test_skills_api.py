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
    skill_maker = next(
        skill for skill in skills if skill["skillId"] == "meta.design_skill_asset"
    )
    assert skill_maker["category"] == "meta"
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

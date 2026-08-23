from fastapi import FastAPI
from test_workspace_api import create_workspace, send


def test_workspace_agents_are_materialized_from_builtin_assets(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)

    response = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents")

    assert response.status_code == 200
    agents = response.json()
    agent_ids = {agent["agentId"] for agent in agents}
    assert "account_diagnosis_strategist" in agent_ids
    assert "audience_simulation_researcher" in agent_ids
    assert "video_creator_quality_analyst" in agent_ids
    assert "media_generation_operator" in agent_ids
    assert "capability_maker" in agent_ids
    assert "input_asset_formatter" in agent_ids
    assert "skill_maker" not in agent_ids
    assert "agent_maker" not in agent_ids
    assert "workflow_maker" not in agent_ids
    account_agent = next(
        agent for agent in agents if agent["agentId"] == "account_diagnosis_strategist"
    )
    assert "analysis.profile_from_history" in account_agent["skillIds"]
    capability_maker = next(agent for agent in agents if agent["agentId"] == "capability_maker")
    assert capability_maker["skillIds"] == [
        "meta.design_skill_asset",
        "meta.design_agent_asset",
        "meta.design_workflow_asset",
    ]
    formatter = next(agent for agent in agents if agent["agentId"] == "input_asset_formatter")
    assert formatter["displayName"] == "Creator Dossier Formatter"
    assert "input_asset.format_profile" in formatter["skillIds"]
    assert "input_asset.format_comments" in formatter["skillIds"]
    curator = next(agent for agent in agents if agent["agentId"] == "creator_material_curator")
    assert curator["displayName"] == "Creator Dossier Curator"
    media_agent = next(agent for agent in agents if agent["agentId"] == "media_generation_operator")
    assert media_agent["skillIds"] == [
        "media.understand_image",
        "media.understand_video",
        "media.generate_image",
        "media.generate_video",
    ]
    assert all(agent["workspaceId"] == workspace["id"] for agent in agents)
    assert all(agent["source"] == "builtin" for agent in agents)


def test_agent_detail_and_editable_asset_fields(app: FastAPI) -> None:
    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(
        item for item in agents if item["agentId"] == "account_diagnosis_strategist"
    )

    detail = send(app, "GET", f"/api/agents/{agent['id']}")

    assert detail.status_code == 200
    body = detail.json()
    assert body["agentId"] == "account_diagnosis_strategist"
    assert "creator account strategist" in body["systemPrompt"]
    assert body["defaultContextPolicy"]["may_read"] == [
        "positioning snapshot",
        "selected historical posts",
        "selected comments",
    ]

    updated = send(
        app,
        "PATCH",
        f"/api/agents/{agent['id']}",
        json={
            "status": "disabled",
            "userNotes": "保留为人工策略角色。",
            "expectedUpdatedAt": body["updatedAt"],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "disabled"
    assert updated.json()["userNotes"] == "保留为人工策略角色。"

    stale = send(
        app,
        "PATCH",
        f"/api/agents/{agent['id']}",
        json={
            "status": "enabled",
            "expectedUpdatedAt": body["updatedAt"],
        },
    )
    assert stale.status_code == 409


def test_builtin_agent_definition_updates_preserve_editable_fields(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    agent = next(
        item for item in send(
            app, "GET", f"/api/workspaces/{workspace['id']}/agents"
        ).json()
        if item["agentId"] == "account_diagnosis_strategist"
    )

    with app.state.database.transaction() as connection:
        connection.execute(
            """
            UPDATE workspace_agents
            SET display_name = 'Stale Agent Name',
                definition_hash = 'stale',
                status = 'disabled',
                user_notes = 'keep agent note'
            WHERE id = ?
            """,
            (agent["id"],),
        )

    refreshed = next(
        item for item in send(
            app, "GET", f"/api/workspaces/{workspace['id']}/agents"
        ).json()
        if item["agentId"] == "account_diagnosis_strategist"
    )

    assert refreshed["displayName"] == "Account Diagnosis Strategist"
    assert refreshed["status"] == "disabled"
    detail = send(app, "GET", f"/api/agents/{agent['id']}").json()
    assert detail["userNotes"] == "keep agent note"


def test_workspace_workflows_are_materialized_from_builtin_assets(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)

    response = send(app, "GET", f"/api/workspaces/{workspace['id']}/workflows")

    assert response.status_code == 200
    workflows = response.json()
    workflow_ids = {workflow["workflowId"] for workflow in workflows}
    assert "account_diagnosis" in workflow_ids
    assert "audience_simulation" in workflow_ids
    assert "video_creator_quality" in workflow_ids
    account_workflow = next(
        workflow for workflow in workflows if workflow["workflowId"] == "account_diagnosis"
    )
    assert account_workflow["entryAgentIds"] == [
        "creator_material_curator",
        "account_diagnosis_strategist",
    ]
    assert account_workflow["artifactEffect"] == "AnalysisRun + Topic candidates"


def test_workflow_detail_and_editable_asset_fields(app: FastAPI) -> None:
    workspace = create_workspace(app)
    workflows = send(
        app, "GET", f"/api/workspaces/{workspace['id']}/workflows"
    ).json()
    workflow = next(
        item for item in workflows if item["workflowId"] == "account_diagnosis"
    )

    detail = send(app, "GET", f"/api/workflows/{workflow['id']}")

    assert detail.status_code == 200
    body = detail.json()
    assert body["workflowId"] == "account_diagnosis"
    task_ids = {task["taskId"] for task in body["agentPlan"]["tasks"]}
    assert "diagnose_account" in task_ids
    diagnose_task = next(
        task for task in body["agentPlan"]["tasks"] if task["taskId"] == "diagnose_account"
    )
    assert diagnose_task["parallel"] is True
    assert diagnose_task["agentId"] == "account_diagnosis_strategist"

    updated = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}",
        json={
            "userNotes": "迁移前保持产品 API 不变。",
            "expectedUpdatedAt": body["updatedAt"],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["userNotes"] == "迁移前保持产品 API 不变。"

    stale = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}",
        json={
            "status": "disabled",
            "expectedUpdatedAt": body["updatedAt"],
        },
    )
    assert stale.status_code == 409


def test_builtin_workflow_definition_updates_preserve_editable_fields(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    workflow = next(
        item for item in send(
            app, "GET", f"/api/workspaces/{workspace['id']}/workflows"
        ).json()
        if item["workflowId"] == "account_diagnosis"
    )

    with app.state.database.transaction() as connection:
        connection.execute(
            """
            UPDATE workspace_workflows
            SET display_name = 'Stale Workflow Name',
                definition_hash = 'stale',
                status = 'disabled',
                user_notes = 'keep workflow note'
            WHERE id = ?
            """,
            (workflow["id"],),
        )

    refreshed = next(
        item for item in send(
            app, "GET", f"/api/workspaces/{workspace['id']}/workflows"
        ).json()
        if item["workflowId"] == "account_diagnosis"
    )

    assert refreshed["displayName"] == "Account Diagnosis Workflow"
    assert refreshed["status"] == "disabled"
    detail = send(app, "GET", f"/api/workflows/{workflow['id']}").json()
    assert detail["userNotes"] == "keep workflow note"

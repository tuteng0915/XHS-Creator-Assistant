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
    account_agent = next(
        agent for agent in agents if agent["agentId"] == "account_diagnosis_strategist"
    )
    assert "analysis.profile_from_history" in account_agent["skillIds"]
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

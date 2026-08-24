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


def test_agent_definition_can_be_updated_as_generated_override(app: FastAPI) -> None:
    workspace = create_workspace(app)
    agent = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
        if item["agentId"] == "account_diagnosis_strategist"
    )
    detail = send(app, "GET", f"/api/agents/{agent['id']}").json()

    response = send(
        app,
        "PATCH",
        f"/api/agents/{agent['id']}/definition",
        json={
            "displayName": "PM Account Diagnosis Agent",
            "purpose": "施琦姗调优后的账号诊断角色。",
            "systemPrompt": detail["systemPrompt"] + "\n额外规则：先指出证据边界。",
            "skillIds": detail["skillIds"] + ["media.understand_image"],
            "defaultContextPolicy": {
                **detail["defaultContextPolicy"],
                "pmNotes": "扩大上下文，但保持证据引用。",
            },
            "version": "pm-v1",
            "userNotes": "PM agent override。",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["displayName"] == "PM Account Diagnosis Agent"
    assert body["source"] == "generated"
    assert body["version"] == "pm-v1"
    assert "media.understand_image" in body["skillIds"]
    assert body["defaultContextPolicy"]["pmNotes"] == "扩大上下文，但保持证据引用。"
    assert body["userNotes"] == "PM agent override。"


def test_agent_definition_diff_and_revert_to_builtin(app: FastAPI) -> None:
    workspace = create_workspace(app)
    agent = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
        if item["agentId"] == "account_diagnosis_strategist"
    )
    detail = send(app, "GET", f"/api/agents/{agent['id']}").json()
    updated = send(
        app,
        "PATCH",
        f"/api/agents/{agent['id']}/definition",
        json={
            "displayName": "PM Agent",
            "purpose": detail["purpose"],
            "systemPrompt": detail["systemPrompt"],
            "skillIds": detail["skillIds"],
            "defaultContextPolicy": detail["defaultContextPolicy"],
            "version": "pm-v1",
            "userNotes": "保留 PM 备注",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    ).json()

    diff = send(app, "GET", f"/api/agents/{agent['id']}/definition-diff")

    assert diff.status_code == 200
    diff_body = diff.json()
    assert diff_body["canRevert"] is True
    assert diff_body["stableId"] == "account_diagnosis_strategist"
    assert set(diff_body["changedFields"]) == {"displayName", "version"}

    reverted = send(
        app,
        "POST",
        f"/api/agents/{agent['id']}/revert-definition",
        json={"expectedUpdatedAt": updated["updatedAt"]},
    )

    assert reverted.status_code == 200
    reverted_body = reverted.json()
    assert reverted_body["source"] == "builtin"
    assert reverted_body["displayName"] == "Account Diagnosis Strategist"
    assert reverted_body["version"] == "v1"
    assert reverted_body["userNotes"] == "保留 PM 备注"


def test_agent_definition_update_validates_skill_references(app: FastAPI) -> None:
    workspace = create_workspace(app)
    agent = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
        if item["agentId"] == "account_diagnosis_strategist"
    )
    detail = send(app, "GET", f"/api/agents/{agent['id']}").json()

    response = send(
        app,
        "PATCH",
        f"/api/agents/{agent['id']}/definition",
        json={
            "displayName": detail["displayName"],
            "purpose": detail["purpose"],
            "systemPrompt": detail["systemPrompt"],
            "skillIds": ["missing.skill"],
            "defaultContextPolicy": detail["defaultContextPolicy"],
            "version": detail["version"],
            "userNotes": detail["userNotes"],
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )

    assert response.status_code == 422
    assert "missing.skill" in response.json()["detail"]


def test_skill_definition_can_be_updated_as_generated_override(app: FastAPI) -> None:
    workspace = create_workspace(app)
    skills = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
    skill = next(item for item in skills if item["skillId"] == "analysis.video_quality")
    detail = send(app, "GET", f"/api/skills/{skill['id']}").json()

    response = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}/definition",
        json={
            "displayName": "Video Quality Rubric",
            "category": detail["category"],
            "purpose": "判断视频创作者质量，并严格记录证据限制。",
            "triggerIntents": detail["triggerIntents"],
            "requiredInputs": detail["requiredInputs"],
            "optionalInputs": detail["optionalInputs"],
            "contextPolicy": {
                **detail["contextPolicy"],
                "rubric": ["剧本驱动", "商单驱动", "技术探索"],
            },
            "outputSchema": {
                **detail["outputSchema"],
                "rubricVersion": "pm-v1",
            },
            "artifactEffect": detail["artifactEffect"],
            "sideEffects": detail["sideEffects"],
            "failureMode": detail["failureMode"],
            "composableWith": detail["composableWith"],
            "implementationRefs": detail["implementationRefs"],
            "version": "pm-v1",
            "userNotes": "施琦姗调整的视频质量 rubric。",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skillId"] == "analysis.video_quality"
    assert body["displayName"] == "Video Quality Rubric"
    assert body["purpose"] == "判断视频创作者质量，并严格记录证据限制。"
    assert body["outputSchema"]["rubricVersion"] == "pm-v1"
    assert body["contextPolicy"]["rubric"] == ["剧本驱动", "商单驱动", "技术探索"]
    assert body["source"] == "generated"
    assert body["version"] == "pm-v1"
    assert body["userNotes"] == "施琦姗调整的视频质量 rubric。"


def test_skill_definition_diff_and_revert_to_builtin(app: FastAPI) -> None:
    workspace = create_workspace(app)
    skill = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
        if item["skillId"] == "analysis.video_quality"
    )
    detail = send(app, "GET", f"/api/skills/{skill['id']}").json()
    updated = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}/definition",
        json={
            **{
                key: detail[key]
                for key in [
                    "displayName",
                    "category",
                    "triggerIntents",
                    "requiredInputs",
                    "optionalInputs",
                    "contextPolicy",
                    "outputSchema",
                    "artifactEffect",
                    "sideEffects",
                    "failureMode",
                    "composableWith",
                    "implementationRefs",
                ]
            },
            "purpose": "PM 改写的视频质量判断说明。",
            "version": "pm-v1",
            "userNotes": "保留 PM 备注",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    ).json()

    diff = send(app, "GET", f"/api/skills/{skill['id']}/definition-diff")

    assert diff.status_code == 200
    diff_body = diff.json()
    assert diff_body["assetType"] == "skill"
    assert diff_body["canRevert"] is True
    assert set(diff_body["changedFields"]) == {"purpose", "version"}

    reverted = send(
        app,
        "POST",
        f"/api/skills/{skill['id']}/revert-definition",
        json={"expectedUpdatedAt": updated["updatedAt"]},
    )

    assert reverted.status_code == 200
    reverted_body = reverted.json()
    assert reverted_body["source"] == "builtin"
    assert reverted_body["purpose"] == diff_body["builtinDefinition"]["purpose"]
    assert reverted_body["version"] == "v1"
    assert reverted_body["userNotes"] == "保留 PM 备注"


def test_video_quality_skill_exposes_default_pm_rubric(app: FastAPI) -> None:
    workspace = create_workspace(app)
    skill = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
        if item["skillId"] == "analysis.video_quality"
    )

    detail = send(app, "GET", f"/api/skills/{skill['id']}").json()

    rubric = detail["contextPolicy"]["pmRubric"]
    assert rubric["qualityDimensions"][0]["dimension"] == "叙事完整度"
    assert any("cannotAssess" in rule for rule in rubric["evidenceRules"])


def test_skill_definition_update_rejects_stale_expected_updated_at(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    skill = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
        if item["skillId"] == "analysis.profile_from_history"
    )
    detail = send(app, "GET", f"/api/skills/{skill['id']}").json()
    first = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}/definition",
        json={
            "displayName": detail["displayName"],
            "category": detail["category"],
            "purpose": "第一次修改。",
            "triggerIntents": detail["triggerIntents"],
            "requiredInputs": detail["requiredInputs"],
            "optionalInputs": detail["optionalInputs"],
            "contextPolicy": detail["contextPolicy"],
            "outputSchema": detail["outputSchema"],
            "artifactEffect": detail["artifactEffect"],
            "sideEffects": detail["sideEffects"],
            "failureMode": detail["failureMode"],
            "composableWith": detail["composableWith"],
            "implementationRefs": detail["implementationRefs"],
            "version": detail["version"],
            "userNotes": detail["userNotes"],
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )
    assert first.status_code == 200

    stale = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}/definition",
        json={
            "displayName": detail["displayName"],
            "category": detail["category"],
            "purpose": "第二次 stale 修改。",
            "triggerIntents": detail["triggerIntents"],
            "requiredInputs": detail["requiredInputs"],
            "optionalInputs": detail["optionalInputs"],
            "contextPolicy": detail["contextPolicy"],
            "outputSchema": detail["outputSchema"],
            "artifactEffect": detail["artifactEffect"],
            "sideEffects": detail["sideEffects"],
            "failureMode": detail["failureMode"],
            "composableWith": detail["composableWith"],
            "implementationRefs": detail["implementationRefs"],
            "version": detail["version"],
            "userNotes": detail["userNotes"],
            "expectedUpdatedAt": detail["updatedAt"],
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
    assert account_workflow["callBinding"] == "account"
    trend_workflow = next(
        workflow for workflow in workflows if workflow["workflowId"] == "trend_analysis"
    )
    assert trend_workflow["callBinding"] == "trend"
    video_workflow = next(
        workflow for workflow in workflows if workflow["workflowId"] == "video_creator_quality"
    )
    assert video_workflow["callBinding"] == "video"
    audience_workflow = next(
        workflow for workflow in workflows if workflow["workflowId"] == "audience_simulation"
    )
    assert audience_workflow["callBinding"] == ""


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


def test_workflow_definition_can_be_updated_as_generated_override(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    workflow = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/workflows").json()
        if item["workflowId"] == "account_diagnosis"
    )
    detail = send(app, "GET", f"/api/workflows/{workflow['id']}").json()
    updated_plan = {
        **detail["agentPlan"],
        "pmReview": "施琦姗调整 task plan 说明。",
    }

    response = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/definition",
        json={
            "displayName": "PM Account Diagnosis Workflow",
            "purpose": "PM 调优后的账号诊断 workflow。",
            "entryAgentIds": detail["entryAgentIds"],
            "agentPlan": updated_plan,
            "artifactEffect": detail["artifactEffect"],
            "callBinding": "account",
            "version": "pm-v1",
            "userNotes": "PM workflow override。",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["displayName"] == "PM Account Diagnosis Workflow"
    assert body["source"] == "generated"
    assert body["version"] == "pm-v1"
    assert body["callBinding"] == "account"
    assert body["agentPlan"]["pmReview"] == "施琦姗调整 task plan 说明。"
    assert body["userNotes"] == "PM workflow override。"


def test_workflow_definition_diff_and_revert_to_builtin(app: FastAPI) -> None:
    workspace = create_workspace(app)
    workflow = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/workflows").json()
        if item["workflowId"] == "account_diagnosis"
    )
    detail = send(app, "GET", f"/api/workflows/{workflow['id']}").json()
    updated = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/definition",
        json={
            "displayName": detail["displayName"],
            "purpose": "PM 调整后的账号诊断链路。",
            "entryAgentIds": detail["entryAgentIds"],
            "agentPlan": detail["agentPlan"],
            "artifactEffect": detail["artifactEffect"],
            "callBinding": "",
            "version": "pm-v1",
            "userNotes": "保留 PM 备注",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    ).json()

    diff = send(app, "GET", f"/api/workflows/{workflow['id']}/definition-diff")

    assert diff.status_code == 200
    diff_body = diff.json()
    assert diff_body["assetType"] == "workflow"
    assert diff_body["canRevert"] is True
    assert set(diff_body["changedFields"]) == {"callBinding", "purpose", "version"}

    reverted = send(
        app,
        "POST",
        f"/api/workflows/{workflow['id']}/revert-definition",
        json={"expectedUpdatedAt": updated["updatedAt"]},
    )

    assert reverted.status_code == 200
    reverted_body = reverted.json()
    assert reverted_body["source"] == "builtin"
    assert reverted_body["purpose"] == diff_body["builtinDefinition"]["purpose"]
    assert reverted_body["callBinding"] == "account"
    assert reverted_body["version"] == "v1"
    assert reverted_body["userNotes"] == "保留 PM 备注"


def test_workflow_definition_update_validates_agent_and_skill_references(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    workflow = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/workflows").json()
        if item["workflowId"] == "account_diagnosis"
    )
    detail = send(app, "GET", f"/api/workflows/{workflow['id']}").json()

    response = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/definition",
        json={
            "displayName": detail["displayName"],
            "purpose": detail["purpose"],
            "entryAgentIds": ["missing_agent"],
            "agentPlan": {
                "tasks": [
                    {
                        "taskId": "bad_task",
                        "agentId": "account_diagnosis_strategist",
                        "skillIds": ["missing.skill"],
                    }
                ]
            },
            "artifactEffect": detail["artifactEffect"],
            "callBinding": "",
            "version": detail["version"],
            "userNotes": detail["userNotes"],
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )

    assert response.status_code == 422
    assert "missing_agent" in response.json()["detail"]


def test_workflow_call_binding_can_register_and_unregister_existing_execution_entry(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    workflows = send(
        app, "GET", f"/api/workspaces/{workspace['id']}/workflows"
    ).json()
    workflow = next(item for item in workflows if item["workflowId"] == "topic_to_draft")
    detail = send(app, "GET", f"/api/workflows/{workflow['id']}").json()
    assert detail["callBinding"] == ""

    registered = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/call-binding",
        json={
            "callBinding": "trend",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )

    assert registered.status_code == 200
    registered_body = registered.json()
    assert registered_body["callBinding"] == "trend"

    stale = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/call-binding",
        json={
            "callBinding": "",
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )
    assert stale.status_code == 409

    unregistered = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/call-binding",
        json={
            "callBinding": "",
            "expectedUpdatedAt": registered_body["updatedAt"],
        },
    )

    assert unregistered.status_code == 200
    assert unregistered.json()["callBinding"] == ""


def test_disabled_workflow_cannot_be_registered_for_calls(app: FastAPI) -> None:
    workspace = create_workspace(app)
    workflow = next(
        item
        for item in send(app, "GET", f"/api/workspaces/{workspace['id']}/workflows").json()
        if item["workflowId"] == "topic_to_draft"
    )
    disabled = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}",
        json={
            "status": "disabled",
            "expectedUpdatedAt": workflow["updatedAt"],
        },
    ).json()

    response = send(
        app,
        "PATCH",
        f"/api/workflows/{workflow['id']}/call-binding",
        json={
            "callBinding": "account",
            "expectedUpdatedAt": disabled["updatedAt"],
        },
    )

    assert response.status_code == 422


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

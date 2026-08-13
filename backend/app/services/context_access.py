from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from app.repositories.agents import AgentRepository
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.drafts import DraftRepository
from app.repositories.media_assets import MediaAssetRepository
from app.repositories.simulation_runs import SimulationRunRepository
from app.repositories.skills import SkillRepository
from app.repositories.source_materials import SourceMaterialRepository
from app.repositories.topics import TopicRepository
from app.repositories.workflow_assets import WorkflowAssetRepository
from app.services.common import utc_now


class ContextAccessService:
    """Build auditable product-scoped workspace context packs.

    This service intentionally favors broad workspace awareness. It does not try
    to starve workflow nodes with tiny field allowlists. The boundary is that all
    context must come from known product assets, carry source refs, and record
    omissions/summarization decisions.
    """

    def __init__(
        self,
        *,
        source_repository: SourceMaterialRepository,
        media_asset_repository: MediaAssetRepository,
        analysis_repository: AnalysisRunRepository,
        topic_repository: TopicRepository,
        draft_repository: DraftRepository,
        simulation_repository: SimulationRunRepository,
        skill_repository: SkillRepository,
        agent_repository: AgentRepository,
        workflow_repository: WorkflowAssetRepository,
    ) -> None:
        self.source_repository = source_repository
        self.media_asset_repository = media_asset_repository
        self.analysis_repository = analysis_repository
        self.topic_repository = topic_repository
        self.draft_repository = draft_repository
        self.simulation_repository = simulation_repository
        self.skill_repository = skill_repository
        self.agent_repository = agent_repository
        self.workflow_repository = workflow_repository

    def build_workspace_pack(
        self,
        connection,
        *,
        workspace: dict,
        requester: dict[str, Any],
        purpose: str,
        selectors: list[str],
        deep_items: list[dict[str, Any]] | None = None,
        max_summary_chars: int = 4_000,
    ) -> dict[str, Any]:
        workspace_id = workspace["id"]
        omitted: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = [
            self._item(
                key="account_profile",
                asset_type="account_profile",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="account_positioning",
                role="account_profile",
                data={
                    "workspaceId": workspace_id,
                    "workspaceName": workspace["name"],
                    "accountPositioning": workspace["account_positioning"],
                    "positioningVersion": workspace["positioning_version"],
                    "updatedAt": workspace["updated_at"],
                },
            )
        ]

        items.append(
            self._item(
                key="input_assets_overview",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="input_assets_overview",
                role="global_context",
                data=[
                    self._summarize_material(row, max_summary_chars, omitted)
                    for row in self.source_repository.list(connection, workspace_id)
                ],
            )
        )
        items.append(
            self._item(
                key="media_assets_overview",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="media_assets_overview",
                role="global_context",
                data=[
                    self._summarize_media_asset(row)
                    for row in self.media_asset_repository.list(
                        connection, workspace_id
                    )
                ],
            )
        )
        items.append(
            self._item(
                key="analysis_history_overview",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="analysis_history_overview",
                role="global_context",
                data=[
                    self._summarize_analysis_run(row)
                    for row in self.analysis_repository.list(connection, workspace_id)[
                        :10
                    ]
                ],
            )
        )
        items.append(
            self._item(
                key="topic_library_overview",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="topic_library_overview",
                role="global_context",
                data=[
                    self._summarize_topic(row)
                    for row in self.topic_repository.list(
                        connection, workspace_id=workspace_id
                    )[:20]
                ],
            )
        )
        items.append(
            self._item(
                key="draft_history_overview",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="draft_history_overview",
                role="global_context",
                data=[
                    self._summarize_draft(row)
                    for row in self.draft_repository.list(connection, workspace_id)[:10]
                ],
            )
        )
        items.append(
            self._item(
                key="simulation_history_overview",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="simulation_history_overview",
                role="global_context",
                data=[
                    self._summarize_simulation(row)
                    for row in self.simulation_repository.list(connection, workspace_id)[
                        :10
                    ]
                ],
            )
        )
        items.append(
            self._item(
                key="capability_catalog",
                asset_type="workspace",
                asset_id=workspace_id,
                workspace_id=workspace_id,
                selector="capability_catalog",
                role="capability_catalog",
                data={
                    "skills": [
                        self._summarize_skill(row)
                        for row in self.skill_repository.list(connection, workspace_id)
                    ],
                    "agents": [
                        self._summarize_agent(row)
                        for row in self.agent_repository.list(connection, workspace_id)
                    ],
                    "workflows": [
                        self._summarize_workflow(row)
                        for row in self.workflow_repository.list(connection, workspace_id)
                    ],
                },
            )
        )

        for item in deep_items or []:
            items.append(self._item(**item))

        source_refs = [item["assetRef"] for item in items]
        content_hash = self._hash({"items": items, "omitted": omitted})
        return {
            "requestId": str(uuid4()),
            "workspaceId": workspace_id,
            "mode": "workspace_pack",
            "scope": "broad",
            "requester": requester,
            "purpose": purpose,
            "selectors": selectors,
            "items": items,
            "citations": [
                {"assetRef": item["assetRef"], "contentHash": item["contentHash"]}
                for item in items
            ],
            "omitted": omitted,
            "snapshot": {
                "createdAt": utc_now(),
                "contentHash": content_hash,
                "sourceRefs": source_refs,
            },
        }

    def deep_item(
        self,
        *,
        key: str,
        asset_type: str,
        asset_id: str,
        selector: str,
        role: str,
        data: Any,
        text: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "asset_type": asset_type,
            "asset_id": asset_id,
            "selector": selector,
            "role": role,
            "data": data,
            "text": text,
        }

    def capability_asset_detail_item(
        self,
        connection,
        *,
        workspace_id: str,
        context_target: dict[str, Any],
    ) -> dict[str, Any] | None:
        asset_type = context_target.get("assetType") or context_target.get("asset_type")
        asset_id = context_target.get("assetId") or context_target.get("asset_id")
        if not isinstance(asset_type, str) or not isinstance(asset_id, str):
            return None
        if asset_type == "skill":
            row = self.skill_repository.get(connection, asset_id)
            if row["workspace_id"] != workspace_id:
                return None
            data = {
                **self._summarize_skill(row),
                "triggerIntents": json.loads(row["trigger_intents_json"]),
                "contextPolicy": json.loads(row["context_policy_json"]),
                "outputSchema": json.loads(row["output_schema_json"]),
                "sideEffects": json.loads(row["side_effects_json"]),
                "implementationRefs": json.loads(row["implementation_refs_json"]),
                "userNotes": row["user_notes"],
            }
            return self.deep_item(
                key="selected_capability_asset",
                asset_type="skill",
                asset_id=asset_id,
                selector="selected_skill_detail",
                role="selected_capability_asset",
                workspace_id=workspace_id,
                data=data,
            )
        if asset_type == "agent":
            row = self.agent_repository.get(connection, asset_id)
            if row["workspace_id"] != workspace_id:
                return None
            data = {
                **self._summarize_agent(row),
                "systemPrompt": row["system_prompt"],
                "userNotes": row["user_notes"],
            }
            return self.deep_item(
                key="selected_capability_asset",
                asset_type="agent",
                asset_id=asset_id,
                selector="selected_agent_detail",
                role="selected_capability_asset",
                workspace_id=workspace_id,
                data=data,
            )
        if asset_type == "workflow":
            row = self.workflow_repository.get(connection, asset_id)
            if row["workspace_id"] != workspace_id:
                return None
            data = {
                **self._summarize_workflow(row),
                "userNotes": row["user_notes"],
            }
            return self.deep_item(
                key="selected_capability_asset",
                asset_type="workflow",
                asset_id=asset_id,
                selector="selected_workflow_detail",
                role="selected_capability_asset",
                workspace_id=workspace_id,
                data=data,
            )
        return None

    def _item(
        self,
        *,
        key: str,
        asset_type: str,
        asset_id: str,
        selector: str,
        role: str,
        data: Any,
        text: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {"data": data, "text": text}
        return {
            "key": key,
            "assetRef": {
                "workspaceId": workspace_id
                or (
                    data.get("workspaceId")
                    if isinstance(data, dict) and data.get("workspaceId")
                    else None
                ),
                "assetType": asset_type,
                "assetId": asset_id,
                "role": role,
            },
            "selector": selector,
            "data": data,
            "text": text,
            "contentHash": self._hash(payload),
        }

    def _summarize_material(
        self, row: dict, max_summary_chars: int, omitted: list[dict[str, Any]]
    ) -> dict[str, Any]:
        summary = {
            "materialId": row["id"],
            "type": row["type"],
            "name": row["name"],
            "updatedAt": row["updated_at"],
        }
        if row["type"] == "trend_csv":
            return {
                **summary,
                "keyword": row["keyword"],
                "originalFilename": row["original_filename"],
                "rowCount": row["row_count"],
                "preview": json.loads(row["preview_json"]),
            }

        text = row["text_content"] or ""
        if len(text) > max_summary_chars:
            omitted.append(
                {
                    "assetRef": {
                        "workspaceId": row["workspace_id"],
                        "assetType": "input_asset",
                        "assetSubType": row["type"],
                        "assetId": row["id"],
                        "role": row["type"],
                    },
                    "reason": "text_summarized_for_workspace_pack",
                    "omittedChars": len(text) - max_summary_chars,
                }
            )
        return {
            **summary,
            "summaryText": text[:max_summary_chars],
            "charCount": len(text),
        }

    def _summarize_media_asset(self, row: dict) -> dict[str, Any]:
        derived = json.loads(row["derived_json"])
        metadata = json.loads(row["metadata_json"])
        compact_derived: dict[str, Any]
        if row["type"] == "image":
            compact_derived = {
                "extractedText": derived.get("extractedText", ""),
                "visualSummary": derived.get("visualSummary", ""),
                "tags": derived.get("tags", []),
            }
            self._copy_if_present(
                compact_derived,
                derived,
                ["imageUnderstanding", "qwenUnderstanding"],
            )
        else:
            compact_derived = {
                "transcript": derived.get("transcript", ""),
                "sceneSummary": derived.get("sceneSummary", ""),
                "visualSummary": derived.get("visualSummary", ""),
                "audioSummary": derived.get("audioSummary", ""),
                "tags": derived.get("tags", []),
                "metrics": derived.get("metrics", {}),
            }
            self._copy_if_present(
                compact_derived,
                derived,
                ["videoUnderstanding", "qwenUnderstanding", "videoPreview"],
            )
        return {
            "mediaAssetId": row["id"],
            "type": row["type"],
            "name": row["name"],
            "purpose": row["purpose"],
            "sourceType": row["source_type"],
            "originalFilename": row["original_filename"],
            "mediaType": row["media_type"],
            "byteSize": row["byte_size"],
            "externalUrl": row.get("external_url", ""),
            "metadata": metadata,
            "derived": compact_derived,
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _copy_if_present(
        target: dict[str, Any], source: dict[str, Any], keys: list[str]
    ) -> None:
        for key in keys:
            value = source.get(key)
            if isinstance(value, (dict, list)):
                target[key] = value

    def _summarize_analysis_run(self, row: dict) -> dict[str, Any]:
        stage_results = json.loads(row["stage_results_json"])
        stage_errors = json.loads(row["stage_errors_json"])
        return {
            "runId": row["id"],
            "workflowType": row["workflow_type"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "completedAt": row["completed_at"],
            "availableStages": list(stage_results.keys()),
            "errorStages": list(stage_errors.keys()),
        }

    def _summarize_topic(self, row: dict) -> dict[str, Any]:
        return {
            "topicId": row["id"],
            "title": row["title"],
            "angle": row["angle"],
            "associatedPainPoint": row["associated_pain_point"],
            "whyItFits": row["why_it_fits"],
            "sourceAnalysisRunId": row["source_analysis_run_id"],
            "sourceWorkflow": row["source_workflow"],
            "status": row["status"],
            "updatedAt": row["updated_at"],
        }

    def _summarize_draft(self, row: dict) -> dict[str, Any]:
        return {
            "draftId": row["id"],
            "topicId": row["topic_id"],
            "sourceAnalysisRunId": row["source_analysis_run_id"],
            "sourceWorkflow": row["source_workflow"],
            "status": row["status"],
            "updatedAt": row["updated_at"],
            "completedAt": row["completed_at"],
        }

    def _summarize_simulation(self, row: dict) -> dict[str, Any]:
        stage_errors = json.loads(row["stage_errors_json"])
        return {
            "simulationRunId": row["id"],
            "topicId": row["topic_id"],
            "draftId": row["draft_id"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "completedAt": row["completed_at"],
            "errorStages": list(stage_errors.keys()),
        }

    def _summarize_skill(self, row: dict) -> dict[str, Any]:
        return {
            "assetId": row["id"],
            "skillId": row["skill_id"],
            "displayName": row["display_name"],
            "category": row["category"],
            "purpose": row["purpose"],
            "requiredInputs": json.loads(row["required_inputs_json"]),
            "optionalInputs": json.loads(row["optional_inputs_json"]),
            "artifactEffect": row["artifact_effect"],
            "failureMode": row["failure_mode"],
            "composableWith": json.loads(row["composable_with_json"]),
            "status": row["status"],
            "source": row["source"],
            "version": row["version"],
        }

    def _summarize_agent(self, row: dict) -> dict[str, Any]:
        return {
            "assetId": row["id"],
            "agentId": row["agent_id"],
            "displayName": row["display_name"],
            "purpose": row["purpose"],
            "skillIds": json.loads(row["skill_ids_json"]),
            "defaultContextPolicy": json.loads(row["default_context_policy_json"]),
            "status": row["status"],
            "source": row["source"],
            "version": row["version"],
        }

    def _summarize_workflow(self, row: dict) -> dict[str, Any]:
        return {
            "assetId": row["id"],
            "workflowId": row["workflow_id"],
            "displayName": row["display_name"],
            "purpose": row["purpose"],
            "entryAgentIds": json.loads(row["entry_agent_ids_json"]),
            "artifactEffect": row["artifact_effect"],
            "agentPlan": json.loads(row["agent_plan_json"]),
            "status": row["status"],
            "source": row["source"],
            "version": row["version"],
        }

    def _hash(self, value: Any) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, default=str
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

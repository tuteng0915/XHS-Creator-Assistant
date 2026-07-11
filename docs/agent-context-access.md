# Agent Context Asset Access Design

This document designs how product agents access creator workspace context assets.

The core decision: agents should not read SQLite, uploaded files, or the whole workspace directly. They should access assets through a small internal Context Access Layer. MCP can be one adapter over that layer later, but the product contract should not depend on MCP terminology.

## 1. Goal

Agents need controlled access to:

- Account Profile
- Source Materials
  - historical posts
  - comment samples
  - uploaded trend CSV data
- AnalysisRun snapshots and stage results
- Topic Library
- Drafts / generated content structures
- SimulationRun results
- Skill, Agent, Workflow asset metadata when needed for planning/debugging

The access layer must support:

- exact asset retrieval when a node needs raw source text;
- compact context packs when a node only needs selected fields;
- immutable input snapshots for runs;
- relationship traversal between assets;
- product-specific permissions and context policies;
- future adapter exposure through MCP or similar tool protocols.

## 2. Non-goals

Do not expose:

- arbitrary SQL;
- arbitrary filesystem paths;
- generic file browsing;
- a generic vector database;
- generic workspace search across everything by default;
- user-editable agent tool permissions in the creator-facing UI;
- direct model access to uploaded file paths.

## 3. Architecture

```text
LangGraph node / product agent
  ↓
Context client
  ↓
Context Access Layer
  ↓
Policy checker
  ↓
Asset repositories / services
  ↓
SQLite + controlled upload storage
```

Optional future adapter:

```text
External or tool-calling agent runtime
  ↓
Product MCP adapter
  ↓
Context Access Layer
```

The MCP adapter is just transport. The important product boundary is the Context Access Layer.

## 4. Core abstraction: ContextAssetRef

Every readable asset should be referenced by a typed reference, not by path or table name.

```ts
type ContextAssetType =
  | "account_profile"
  | "source_material"
  | "analysis_run"
  | "analysis_stage"
  | "topic"
  | "draft"
  | "simulation_run"
  | "skill_asset"
  | "agent_asset"
  | "workflow_asset"

type ContextAssetRef = {
  workspaceId: string
  assetType: ContextAssetType
  assetId: string
  version?: string | number
  role?: string
}
```

Examples:

```json
{
  "workspaceId": "ws_123",
  "assetType": "source_material",
  "assetId": "mat_comments_123",
  "role": "comments"
}
```

```json
{
  "workspaceId": "ws_123",
  "assetType": "analysis_stage",
  "assetId": "run_456:profile",
  "role": "voice_fingerprint"
}
```

## 5. Context request contract

Agents should request context by declaring intent and allowed selectors.

```ts
type ContextRequest = {
  workspaceId: string
  requester: {
    workflowId: string
    agentId: string
    skillId: string
    runId?: string
    nodeKey?: string
  }
  purpose: string
  refs: ContextAssetRef[]
  selectors: ContextSelector[]
  mode: "exact" | "compact" | "summary" | "snapshot"
  maxChars?: number
}
```

`selectors` describe product fields, not arbitrary JSON paths where possible:

```ts
type ContextSelector =
  | "account_positioning"
  | "historical_posts_text"
  | "comment_samples_text"
  | "trend_top_ranked_posts"
  | "analysis_profile"
  | "analysis_pain_points"
  | "analysis_trend_patterns"
  | "topic_core_fields"
  | "draft_generated_snapshot"
  | "draft_editable_content"
  | "simulation_personas"
  | "simulation_reactions"
  | "simulation_synthesis"
```

The response is a structured context pack:

```ts
type ContextPack = {
  requestId: string
  workspaceId: string
  mode: "exact" | "compact" | "summary" | "snapshot"
  items: ContextItem[]
  citations: ContextCitation[]
  omitted: ContextOmission[]
  snapshot: {
    createdAt: string
    contentHash: string
    sourceRefs: ContextAssetRef[]
  }
}
```

Each item is typed:

```ts
type ContextItem = {
  key: string
  assetRef: ContextAssetRef
  selector: ContextSelector
  data: unknown
  text?: string
  contentHash: string
}
```

## 6. Policy model

Access is allowed only when all three layers agree:

1. Workflow plan allows the agent to perform the task.
2. Agent asset allows the skill.
3. Skill context policy allows the requested selectors.

Current assets already contain the required building blocks:

- `WorkflowAsset.agentPlan`
- `Agent.skillIds`
- `Agent.defaultContextPolicy`
- `Skill.contextPolicy`
- `Skill.requiredInputs`
- `Skill.optionalInputs`

The Context Access Layer should enforce these centrally.

Example: account topic generation may read:

- workspace positioning snapshot;
- profile stage result;
- pain-point stage result.

It may not read:

- complete workspace;
- raw uploaded trend CSV;
- unrelated drafts;
- unrelated simulation runs.

## 7. Recommended agent-facing tools

These are product tools, not generic filesystem tools.

### `context.resolve_required_inputs`

Purpose:

- Given workflow/agent/skill/run context, return missing and available asset refs.

Input:

```json
{
  "workspaceId": "ws_123",
  "workflowId": "account_diagnosis",
  "agentId": "account_diagnosis_strategist",
  "skillId": "analysis.profile_from_history"
}
```

Output:

```json
{
  "available": [
    {
      "assetType": "account_profile",
      "assetId": "ws_123",
      "role": "account_profile"
    },
    {
      "assetType": "source_material",
      "assetId": "mat_history_123",
      "role": "historical_posts"
    }
  ],
  "missing": []
}
```

### `context.get_asset`

Purpose:

- Read one asset in an allowed form.

Allowed modes:

- `exact`: raw text or full structured object where policy permits.
- `compact`: selected product fields only.
- `summary`: generated or precomputed summary.

### `context.build_pack`

Purpose:

- Build a multi-asset context pack for one model call.

This is the preferred API for LLM nodes because it produces a stable, logged, hashable input bundle.

### `context.snapshot_for_run`

Purpose:

- Freeze the context pack used to create an AnalysisRun, Draft, or SimulationRun.

The snapshot is immutable execution history and should be saved on the run record.

### `context.trace_relationships`

Purpose:

- Traverse product relationships in a constrained way.

Examples:

- Topic → source AnalysisRun → profile and pain point stage results.
- Draft → Topic → source AnalysisRun.
- SimulationRun → target Topic/Draft → synthesis.

This should not become generic graph traversal. It should expose product-specific relationship names.

## 8. MCP adapter design

If we expose this through MCP, the MCP server should be thin and product-specific.

Suggested MCP tools:

- `creator_context_resolve_required_inputs`
- `creator_context_get_asset`
- `creator_context_build_pack`
- `creator_context_snapshot_for_run`
- `creator_context_trace_relationships`

Do not expose:

- `read_file`;
- `list_directory`;
- `query_sql`;
- `search_everything`;
- `execute_workflow`;
- `edit_agent_prompt`;
- `edit_workflow_graph`.

The MCP server should call the same Context Access Layer used by backend workflows. It should not contain separate permission logic.

## 9. How current workflows should use this

### Account diagnosis

#### `profile_analysis`

Allowed context:

- Account Profile positioning snapshot.
- Historical posts material.

Context pack:

```json
{
  "selectors": ["account_positioning", "historical_posts_text"],
  "mode": "snapshot"
}
```

#### `pain_point_analysis`

Allowed context:

- Account Profile positioning snapshot.
- Comment samples material.

Context pack:

```json
{
  "selectors": ["account_positioning", "comment_samples_text"],
  "mode": "snapshot"
}
```

#### `topic_generation`

Allowed context:

- Account Profile positioning snapshot.
- Profile stage result.
- Pain point stage result.

Not allowed:

- raw historical posts;
- raw comments;
- full workspace.

### Trend analysis

#### deterministic ranking

Allowed context:

- uploaded trend CSV source material ID;
- file content through controlled storage only inside backend service.

Output:

- compact top-50 ranked posts snapshot.

The graph state and agent-facing context should store only the source material ID and ranked compact snapshot, not the complete CSV.

#### `trend_pattern_analysis`

Allowed context:

- Account Profile positioning snapshot.
- top-50 ranked trend posts.

#### `pain_point_analysis`

Allowed context:

- Account Profile positioning snapshot.
- top-50 ranked trend posts.

#### `topic_generation`

Allowed context:

- Account Profile positioning snapshot.
- trend pattern result.
- trend pain point result.

### Draft generation

Allowed context:

- selected Topic core fields;
- relevant compact analysis context:
  - voice fingerprint;
  - viral structure;
  - trend pattern summary if topic came from trend analysis.

Not allowed by default:

- complete source materials;
- complete analysis run JSON;
- unrelated topics.

### Audience simulation

Allowed context:

- target Topic or Draft;
- Account Profile positioning snapshot;
- optional compact analysis context.

Persona reaction nodes receive:

- persona definition;
- target topic/draft;
- only context selected by the simulation workflow.

Debate response nodes receive:

- persona definition;
- topic/draft target;
- other initial reactions.

## 10. Write access

Context access and mutation should be separate.

Read tools:

- `context.get_asset`
- `context.build_pack`
- `context.trace_relationships`

Write tools should map to explicit product operations:

- `workspace.update_profile`
- `source.save_historical_posts`
- `source.save_comments`
- `source.upload_trend_csv`
- `topic.create`
- `topic.update`
- `topic.select`
- `draft.create_from_topic`
- `draft.update_editable_content`
- `simulation.create_run`

Agents should never write arbitrary JSON into arbitrary asset records.

## 11. Audit log

Every context pack used by a model call should be auditable:

- `run_id`
- `workflow_id`
- `agent_id`
- `skill_id`
- `node_key`
- requested selectors
- returned asset refs
- omitted fields and reason
- content hash
- model call metadata

This should extend the current `model_metadata` and `input_snapshot` pattern.

## 12. Failure behavior

If a requested asset is missing:

- return a structured missing-input result;
- do not let the model infer missing source content;
- allow the workflow to pause, fail early, or ask the UI to collect the missing asset.

If a policy denies access:

- fail the node with a policy error;
- include safe debugging information:
  - requester;
  - selector;
  - asset type;
  - policy layer that denied access.

Do not include hidden asset content in the error.

## 13. Implementation slices

### Slice 1: In-process Context Access Layer

Add backend service:

- `ContextAccessService`
- `ContextPolicyService`
- `ContextPackBuilder`

Use existing repositories. No MCP yet.

Acceptance:

- account diagnosis nodes get context through `ContextAccessService`;
- existing visible behavior unchanged;
- tests assert nodes cannot request unrelated context.

### Slice 2: Replace ad hoc input snapshot builders

Move current snapshot construction from individual workflow services into context pack builders where practical.

Acceptance:

- AnalysisRun input snapshots include source refs, selectors, hashes, and compact payloads.

### Slice 3: Add relationship tracing

Support:

- Topic → AnalysisRun → stage results.
- Draft → Topic → AnalysisRun.
- SimulationRun → target Topic/Draft.

Acceptance:

- draft generation uses relationship tracing instead of manually reaching across repositories.

### Slice 4: MCP-compatible adapter

Expose product-specific tools over an internal MCP server or equivalent adapter.

Acceptance:

- tool calls return the same context packs as backend workflows;
- no direct file path, SQL, or generic search tool exists.

### Slice 5: Admin/internal asset authoring

Later, internal tools can create or edit:

- Skill assets;
- Agent assets;
- Workflow assets;
- context policies.

This is not a creator-facing builder.

## 14. Design rule

Agents do not own context.

Agents request context for a declared product skill. The Context Access Layer decides what they can see, returns a bounded context pack, snapshots what was used, and records enough provenance to debug or replay the run.

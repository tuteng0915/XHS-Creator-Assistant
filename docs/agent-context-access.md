# Agent Context Asset Access Design

This document designs how product agents access creator workspace context assets.

The core decision: agents should have broad product-level workspace awareness, but should not read SQLite, uploaded file paths, or arbitrary filesystem content directly. They should access workspace assets through an internal Context Access Layer that builds auditable context packs.

The design bias is **global vision first**:

- prefer giving the agent enough surrounding context to reason well;
- avoid over-isolating nodes into narrow, blind prompt calls;
- keep context product-scoped, provenance-tracked, and budget-aware;
- use summaries/projections only to manage size, not to hide relevant information by default.

MCP can be one adapter over this layer later, but the product contract should not depend on MCP terminology.

## 1. Goal

Agents need controlled access to:

- Input Asset instances:
  - account profiles
  - historical posts
  - comment samples
  - uploaded trend CSV data
  - video creator samples
- AnalysisRun snapshots and stage results
- Topic Library
- generated content structures
- SimulationRun results
- Skill, Agent, Workflow asset metadata when needed for planning/debugging

The access layer must support:

- exact asset retrieval when a node needs raw source text;
- broad workspace context packs when a node benefits from cross-asset awareness;
- compact or summarized views when raw assets are too large;
- immutable input snapshots for runs;
- relationship traversal between assets;
- product-specific asset boundaries and context budgets;
- future adapter exposure through MCP or similar tool protocols.

## 2. Non-goals

Do not expose:

- arbitrary SQL;
- arbitrary filesystem paths;
- generic file browsing;
- a generic vector database;
- unbounded generic search that ignores product asset types and provenance;
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
  | "historical_posts"
  | "comment_samples"
  | "trend_csv"
  | "video_creator_samples"
  | "analysis_run"
  | "analysis_stage"
  | "topic"
  | "generated_structure"
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
  "assetType": "comment_samples",
  "assetId": "mat_comments_123",
  "role": "comments"
}
```

Implementation note: the current backend may still store historical posts,
comments, trend CSV, and video samples through the legacy `source_materials`
repository/table. That name is a storage/API compatibility detail. The product
model and UI should treat them as peer Input Asset categories, not as children
of a user-facing legacy bucket.

```json
{
  "workspaceId": "ws_123",
  "assetType": "analysis_stage",
  "assetId": "run_456:profile",
  "role": "voice_fingerprint"
}
```

## 5. Context request contract

Agents should request context by declaring intent, desired scope, and useful selectors. Selectors are not a hard “only these fields may exist” wall; they are the requested focus inside a broader product context pack.

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
  mode: "workspace_pack" | "exact" | "compact" | "summary" | "snapshot"
  scope: "broad" | "focused" | "deep"
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
  | "video_creator_samples_text"
  | "analysis_profile"
  | "analysis_pain_points"
  | "analysis_trend_patterns"
  | "topic_core_fields"
  | "generated_structure_snapshot"
  | "generated_structure_editable_content"
  | "simulation_personas"
  | "simulation_reactions"
  | "simulation_synthesis"
```

The response is a structured context pack:

```ts
type ContextPack = {
  requestId: string
  workspaceId: string
  mode: "workspace_pack" | "exact" | "compact" | "summary" | "snapshot"
  scope: "broad" | "focused" | "deep"
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

### Default workspace pack

Most workflow nodes should start from a broad workspace pack:

- account profile / positioning snapshot;
- current selected topic if one exists;
- relevant recent analysis summaries;
- relevant Input Asset summaries and IDs;
- topic library highlights;
- available generated-structure/simulation context where relevant;
- capability metadata for the active skill/agent/workflow.

Then the node can request deep exact context for specific assets, such as the selected comments material or top-ranked trend posts.

This gives agents a working mental model of the creator workspace without giving them arbitrary database or filesystem access.

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

The policy model should not be overly restrictive. Its job is to keep context inside the product asset graph, make size/cost predictable, and record what was used.

Context expansion is allowed when all three layers agree:

1. Workflow plan allows the agent to perform the task.
2. Agent asset allows the skill.
3. Skill context policy describes which asset families are normally relevant.

Current assets already contain the required building blocks:

- `WorkflowAsset.agentPlan`
- `Agent.skillIds`
- `Agent.defaultContextPolicy`
- `Skill.contextPolicy`
- `Skill.requiredInputs`
- `Skill.optionalInputs`

The Context Access Layer should enforce these centrally, but the default should be “provide broad relevant workspace context” rather than “deny everything not explicitly listed.”

Example: account topic generation may read:

- workspace positioning snapshot;
- profile stage result;
- pain-point stage result.
- selected/current topic if present;
- recent related topics and generated structures;
- summaries of Input Assets used by the source run.

It should not read:

- arbitrary files;
- arbitrary SQL results;
- raw uploaded CSV bytes unless the workflow asks for the controlled trend projection;
- assets from another workspace.

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
      "assetType": "historical_posts",
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

This is the preferred API for LLM nodes because it produces a stable, logged, hashable input bundle. The default mode should be a broad `workspace_pack`, with deeper exact asset content included when it materially improves the node.

### `context.snapshot_for_run`

Purpose:

- Freeze the context pack used to create an AnalysisRun, generated structure, or SimulationRun.

The snapshot is immutable execution history and should be saved on the run record.

### `context.trace_relationships`

Purpose:

- Traverse product relationships in a constrained way.

Examples:

- Topic → source AnalysisRun → profile and pain point stage results.
- GeneratedStructure → Topic → source AnalysisRun.
- SimulationRun → target Topic/GeneratedStructure → synthesis.

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

Account diagnosis should not be artificially split into blind calls. Each node should understand the broader creator workspace, while still emphasizing the source assets that matter most for that stage.

#### `profile_analysis`

Default broad context:

- Account Profile positioning snapshot.
- Historical posts material or selected summary/projection.
- Topic library highlights.
- Recent analysis summaries for the workspace.
- Current selected topic/generated structure if present.

Deep context:

- full or sampled historical post text.

Context pack:

```json
{
  "selectors": ["account_positioning", "historical_posts_text"],
  "mode": "workspace_pack",
  "scope": "broad"
}
```

#### `pain_point_analysis`

Default broad context:

- Account Profile positioning snapshot.
- Comment samples material.
- Recent topics/generated structures/simulations that reveal audience assumptions.

Deep context:

- full or sampled comment text.

Context pack:

```json
{
  "selectors": ["account_positioning", "comment_samples_text"],
  "mode": "workspace_pack",
  "scope": "broad"
}
```

#### `topic_generation`

Default broad context:

- Account Profile positioning snapshot.
- Profile stage result.
- Pain point stage result.
- Topic library highlights to avoid repetition.
- Prior generated structures and simulations when they help understand what has already been explored.
- Input Asset summaries/provenance from the source run.

Deep context:

- raw historical posts or comments only when the workflow decides the summaries are insufficient.

### Trend analysis

#### deterministic ranking

Allowed context:

- uploaded trend CSV Input Asset ID;
- file content through controlled storage only inside backend service.

Output:

- compact top-50 ranked posts snapshot.

The graph state should store only the trend CSV Input Asset ID and ranked compact snapshot, not the complete CSV. The agent-facing context may include the ranked projection plus workspace-wide creator context.

#### `trend_pattern_analysis`

Default broad context:

- Account Profile positioning snapshot.
- top-50 ranked trend posts.
- Existing account diagnosis summaries if available.
- Topic library highlights to avoid duplicate topics.

#### `pain_point_analysis`

Default broad context:

- Account Profile positioning snapshot.
- top-50 ranked trend posts.
- Comment-source or previous simulation summaries when useful for interpreting audience needs.

#### `topic_generation`

Default broad context:

- Account Profile positioning snapshot.
- trend pattern result.
- trend pain point result.
- current topic library and generated-structure history.

### Generated structure generation

Default broad context:

- selected Topic core fields;
- relevant analysis context:
  - voice fingerprint;
  - viral structure;
  - trend pattern summary if topic came from trend analysis.
- prior generated structures and selected simulation summaries;
- topic library context to avoid duplicating old structures.

Deep context:

- exact source run stage output;
- relevant source excerpts when needed.

### Audience simulation

Default broad context:

- target Topic or GeneratedStructure;
- Account Profile positioning snapshot;
- relevant analysis context;
- relevant prior simulations;
- topic/generated-structure lineage.

Persona reaction nodes receive:

- persona definition;
- target topic/generated structure;
- workspace pack selected by the simulation workflow.

Debate response nodes receive:

- persona definition;
- topic/generated-structure target;
- other initial reactions.

## 10. Write access

Context access and mutation should be separate.

Read tools:

- `context.get_asset`
- `context.build_pack`
- `context.trace_relationships`

Write tools should map to explicit product operations:

- `workspace.update_profile`
- `input_asset.save_account_profile`
- `input_asset.save_historical_posts`
- `input_asset.save_comments`
- `input_asset.upload_trend_csv`
- `input_asset.save_video_creator_samples`
- `topic.create`
- `topic.update`
- `topic.select`
- `generated_structure.create_from_topic`
- `generated_structure.update_editable_content`
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

If a policy or budget excludes content:

- include the omission in the context pack;
- prefer summaries over omission when the asset is relevant but too large;
- fail the node only when the asset is required and no useful representation is available;
- include safe debugging information:
  - requester;
  - selector;
  - asset type;
  - policy or budget layer that excluded access.

Do not include hidden asset content in the error.

## 13. Implementation status and next steps

### Implemented

The backend now has an in-process `ContextAccessService` that builds auditable
workspace context packs.

Implemented behavior:

- account profile is always included;
- Input Asset overview is included;
- analysis history overview is included;
- topic library overview is included;
- generated-structure history overview is included;
- simulation history overview is included;
- deep Input Asset items can be attached by callers;
- context packs include source refs, content hashes, omissions, requester, and
  purpose;
- AnalysisRun input snapshots include broad context packs.

### Current gaps

The current implementation does not yet include:

- Skill catalog overview;
- Agent catalog overview;
- Workflow asset overview;
- selected capability asset detail;
- pack-level token/character budget metadata;
- model-specific budget policy.

This is now the most important Context Access gap because maker agents need the
capability catalog to generate useful Skill/Agent/Workflow proposals.

### Next step 1: Capability context

Extend `ContextAccessService` to include:

- `skill_catalog_overview`;
- `agent_catalog_overview`;
- `workflow_catalog_overview`;
- selected Skill / Agent / Workflow detail when launched from a detail page.

Acceptance:

- maker conversations receive existing capability assets without user copy/paste;
- capability assets are cited with source refs and hashes;
- no arbitrary filesystem or database access is exposed.

### Next step 2: Relationship tracing

Support richer traversal:

- Topic → AnalysisRun → stage results.
- GeneratedStructure → Topic → AnalysisRun.
- SimulationRun → target Topic/GeneratedStructure.
- AssetProposal → source conversation message → applied Skill/Agent/Workflow.

### Later: Adapter exposure

An MCP-compatible or similar adapter can be added later, but it should call this
same Context Access Layer and remain product-specific.

## 14. Design rule

Agents should not be starved of context.

Agents request context for a declared product skill. The Context Access Layer builds a broad product-scoped workspace pack, deepens it where useful, snapshots what was used, and records enough provenance to debug or replay the run.

The constraint is not “minimum necessary information.” The constraint is “no arbitrary external access, no cross-workspace leakage, no untracked context, and no unbounded token growth.”

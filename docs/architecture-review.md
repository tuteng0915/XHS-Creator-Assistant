# Architecture Review: Creator Asset Workspace

Reviewed on 2026-07-12 against the current codebase after commit
`40cca28 Add provider-backed conversations and maker assets`.

This report replaces older review notes. The product direction is now clear:
the app is a creator workspace with context assets and capability assets, not a
generic agent platform.

## Current implementation snapshot

### Context assets

Implemented and product-specific:

- Workspace / account profile
- Source materials:
  - historical posts
  - comment samples
  - uploaded trend CSV
- Analysis runs:
  - account diagnosis
  - trend analysis
- Topic library
- Draft / content structure records
- Audience simulation runs

### Capability assets

Implemented as internal workspace assets:

- Skills
- Agents
- Workflow assets
- Agent conversations

The newest addition is a maker layer:

- `Skill Maker`
- `Agent Maker`
- `Workflow Maker`

These currently generate proposals through the existing conversation surface.
They do not directly mutate Skill, Agent, or Workflow definitions.

### Execution model

Current workflow execution is no longer owned by opening an SSE connection:

- `POST /api/workspaces/{workspace_id}/analysis-runs` creates a persisted run.
- `POST /api/workspaces/{workspace_id}/simulation-runs` creates a persisted run.
- `WorkflowWorkerService` enqueues backend execution independently.
- SSE endpoints observe persisted run state and rebuild progressive events.
- `WorkflowWorkerService.resume_unfinished()` runs during app startup.

This is a substantial correction from the original prototype.

### Model provider boundary

Live model calls now go through backend `ModelCallService`.

Supported providers:

- Anthropic Messages API
- Qwen / DashScope OpenAI-compatible chat completions

The browser no longer receives model API keys.

## What is aligned

- The product is workspace-first and creator-specific.
- Account profile is treated as a reusable workspace input.
- Source materials are constrained to product types, not arbitrary files.
- Analysis, topic, draft, and simulation outputs are persisted.
- Generated draft snapshots are separated from user-editable draft content.
- Topic and draft records carry relationships back to source runs where available.
- Public arbitrary model-call and stage-mutation endpoints are removed.
- LangGraph remains internal; frontend sees product-level runs and stages.
- Demo mode uses the integrated persistence/execution path.
- Capability assets are visible and composable without becoming a generic builder.
- Maker agents reuse the conversation UI instead of adding more forms.
- Qwen provider support reduces live debugging cost without changing workflow code.

## Resolved or improved risks

### Workflow lifecycle

Older risk: opening an SSE connection started execution.

Current status: materially improved.

Execution starts from POST-created runs and the backend worker owns execution.
SSE is now observation-oriented.

Remaining gap: duplicate user POSTs can still create multiple distinct runs.
The worker prevents duplicate execution for the same run ID, but the API does
not yet accept an idempotency key or client request ID.

### Public execution mutation

Older risk: browser endpoints could forge model calls or mutate stage results.

Current status: improved.

Tests verify these routes are not public:

- `PATCH /api/analysis-runs/{run_id}`
- `PUT /api/analysis-runs/{run_id}/stages/{stage_key}`
- `POST /api/model-calls`

Remaining gap: there is no authentication by design, so a local caller with an
object ID can still operate on records. This is acceptable for the current
single-user local product, but it is not a deployable security boundary.

### Provider key handling

Older prototype risk: browser-side Anthropic key.

Current status: fixed for migrated app.

Live generation keys now stay in backend environment variables.

## Recently resolved findings

### Resolved — maker agents receive capability catalog context

`ContextAccessService` now includes a `capability_catalog` item in broad
workspace packs.

The catalog contains:

- Skill summaries;
- Agent summaries;
- Workflow asset summaries and task plans.

`AgentConversationService` also ensures built-in Skills, Agents, and Workflows
are materialized before building the conversation context pack. Maker agents no
longer depend on the user manually opening the capability pages first.

Remaining gap: when a maker is launched from a specific selected
Skill/Agent/Workflow detail page, that selected asset detail is not yet passed
as a first-class conversation context target.

### Resolved — proposed actions have an executable proposal loop

Agent conversation `proposedActions` are now converted into persisted
`AssetProposal` rows.

Implemented:

- proposal source tracking: workspace, conversation, message;
- `apply` and `reject` endpoints;
- frontend review/apply/reject controls in the Agent conversation panel;
- product-specific apply logic for:
  - `workspace.update_profile`;
  - `topic.create_or_update`;
  - `skill.propose_definition`;
  - `agent.propose_definition`;
  - `workflow.propose_definition`.

Capability assets created from maker proposals are stored as `source =
generated`, separate from built-in assets.

Remaining gap: proposal editing before apply is still minimal. The current path
assumes the model returns a valid structured payload and lets the user apply or
reject it.

### Resolved — capability asset seed updates are no longer append-only

Built-in Skills, Agents, and Workflow assets now store `definition_hash`.

On sync:

- missing built-ins are inserted;
- changed built-ins with `source = builtin` are updated in place;
- user-editable `status` and `user_notes` are preserved;
- generated assets are not overwritten by built-in sync.

This resolves stale prompts, skill lists, context policies, and workflow task
plans for existing workspaces after code-defined catalog changes.

### Improved — SSE observation now supports reconnect/poll fallback

SSE endpoints still rebuild events from persisted run snapshots rather than a
durable event log. However:

- event IDs now use stable sequence numbers;
- endpoints accept `Last-Event-ID` and `?after=sequence`;
- frontend falls back to polling the persisted run snapshot after SSE failure.

Remaining gap: this is still observation replay, not a durable event log.

### Improved — conversation provider failure is now auditable

Live conversation model failures now create an assistant failure message instead
of leaving only the user message. The failure is recorded in message
`modelMetadata`.

Remaining gaps:

- conversation calls are still synchronous HTTP requests;
- there is no conversation-level queued/running state;
- retrying can still create another user message.

## Current high-priority findings

### P1 — in-process worker is good for local use but not durable execution

`WorkflowWorkerService` is currently an in-process asyncio task runner.

Strengths:

- prevents duplicate execution for the same in-process run key;
- resumes unfinished runs at app startup;
- is simple and aligned with local SQLite.

Remaining risks:

- process crash during an external model call may repeat the current stage on
  restart;
- no durable job claim/lease is stored in SQLite;
- no per-run idempotency key protects against repeated POSTs;
- no retry policy is stored per stage;
- no structured worker failure record separate from workflow stage failure.

Recommended next step:

- Keep the in-process worker, but add SQLite job claim metadata:
  `claimed_at`, `claim_owner`, `attempt_count`, `last_heartbeat_at`.
- Add API-level idempotency for run creation.

### P1 — SSE observation is reconnectable but not durable replay

SSE endpoints rebuild events from persisted run snapshots.

This is acceptable for progressive rendering, but it is not a durable event log.

Current gaps:

- no stored event IDs;
- sequence IDs are replay-friendly but derived from current snapshot order;
- no event payload is persisted for audit/debug replay.

Recommended fix:

- Keep snapshot-first loading.
- Only add durable event log if debugging or audit requirements justify it.

### P1 — conversations execute live model calls synchronously in request

Agent conversation message sending persists the user message, builds context,
calls the provider, then persists the assistant message.

This is acceptable for a first conversation slice, but differs from workflow
execution.

Risks:

- long live calls hold the HTTP request;
- if the model call fails, the user message remains without an assistant error
- there is no conversation-level `running` or `failed` status;
- retrying from the UI can create repeated user messages.

Recommended fix:

- Add message-level status for assistant generation.
- Consider moving live conversation responses to the same worker/observe pattern
  if conversations become central.

### P1 — context packs favor breadth but need explicit budget policy

The broad Context Access Layer matches the current product philosophy:
give agents enough global workspace vision instead of starving them.

Current gaps:

- budget is per text material (`max_summary_chars`) rather than per full pack;
- `selectors` are recorded but not enforced;
- no model-specific token budget policy;
- no warning when the pack becomes too large for the selected provider/model.

Recommended fix:

- Add pack-level budget metadata:
  - estimated characters/tokens;
  - included exact items;
  - summarized items;
  - omitted items;
  - provider/model budget hint.
- Keep the broad default, but make truncation auditable and deterministic.

### P1 — Qwen provider needs model-specific structured-output hardening

Qwen support is correctly isolated behind `ModelCallService`, but structured
output still relies on prompt-only JSON.

Risks:

- OpenAI-compatible providers may return non-JSON prose or fenced JSON;
- Qwen model variants may differ in tool/JSON support;
- error responses are reduced to status code, which is safe but weak for local
  debugging.

Recommended fix:

- Add provider-specific structured output options where supported.
- Keep current JSON parser fallback.
- Log sanitized provider error body in backend logs, not in frontend responses.
- Add integration fixtures for realistic Qwen responses.

### P1 — `frontend/src/App.tsx` is now a bottleneck

`App.tsx` contains:

- workspace loading;
- source material editing;
- workflow execution;
- SSE state reducers;
- topic/draft/simulation UI;
- skill/agent/workflow inspectors;
- conversation UI;
- maker shortcuts.

The file is still manageable but fragile.

Recommended split:

- `WorkspaceShell`
- `ContextAssetSidebar`
- `CapabilitySidebar`
- `WorkflowCallPanel`
- `AnalysisOutputPanel`
- `TopicLibraryPage`
- `CapabilityAssetsPage`
- `AgentConversationPanel`
- shared hooks:
  - `useWorkspaceData`
  - `useAnalysisRunObserver`
  - `useSimulationRunObserver`
  - `useAgentConversation`

Do this after the next product behavior stabilizes, not before.

## Medium-priority findings

### P2 — Draft generation is synchronous

Draft generation creates a persisted Draft, but the endpoint itself awaits live
model generation.

This is acceptable for now because draft generation is smaller than full
workflows, but if live structure generation becomes slow or expensive, it
should follow the same create-run/observe pattern.

### P2 — no capability asset detail in context-aware UI shortcuts

Maker CTA buttons prefill useful prompts, but they do not pass the selected
Skill/Agent/Workflow ID as structured context.

Recommended fix:

- When starting from a selected capability asset, pass a structured
  `conversationContext` or initial message metadata.
- Let the backend include the selected asset detail in the context pack.

### P2 — proposed action validation is too loose

`RealAgentConversationModelProvider` validates only:

- `type` is a non-empty string;
- `description` is a non-empty string;
- status is forced to `requires_confirmation`.

Recommended fix:

- Define allowed action types.
- Define schema per action type.
- Reject or downgrade unknown action types to plain text recommendations.

### P2 — demo conversation is deterministic but shallow

Demo provider is useful for tests and local UI, but maker demo output is not a
real proposal. It only returns a generic reply plus proposed action hints.

Recommended fix:

- Add richer deterministic demo replies for maker agents.
- Keep them obviously labeled as demo proposals.

## Product model to preserve

### Context assets

These are user-facing creator records:

- Workspace
- Account Profile
- Source Material
- Analysis Run
- Topic
- Draft / Content Structure
- Simulation Run

### Capability assets

These are product-owned capability records:

- Skill
- Agent
- Workflow Asset
- Workflow Call
- Agent Conversation
- Asset Proposal (recommended next)

Capability assets should be inspectable and composable. They should not become:

- a generic filesystem;
- a plugin marketplace;
- a VS Code clone;
- a general workflow editor;
- a generic agent builder.

## Skill, Agent, Workflow semantics

### Skill

A skill should be more than a prompt. It should include:

- stable ID and version;
- product purpose;
- required context asset types;
- input schema;
- output schema;
- prompt/instruction template;
- model policy;
- validation and repair policy;
- allowed downstream artifact writes;
- provenance metadata.

### Agent

An agent is a reusable product role:

- system prompt;
- allowed skill list;
- context access policy;
- output obligations;
- failure behavior.

Audience simulation personas are not the same as configurable platform agents.
They are runtime roles generated inside one simulation workflow.

### Workflow

A workflow is a product-owned task graph:

- workflow key;
- version;
- product purpose;
- entry agents;
- task/node definitions;
- dependencies and parallel sections;
- required input assets;
- generated output assets;
- visible stage mapping.

## Recommended priority order

1. Add idempotency key support for workflow run creation.
2. Add pack-level context budget metadata.
3. Add selected capability asset detail to maker conversation context.
4. Harden Qwen structured-output handling with provider-specific fixtures.
5. Add conversation-level queued/running/failed state if conversations become
   central.
6. Split `frontend/src/App.tsx` after the above behavior stabilizes.

## Acceptance criteria for the next architecture pass

- Retrying a workflow POST with the same client request ID does not create a
  duplicate run.
- Context packs show total size, source refs, exact/summarized/omitted assets,
  and provider/model budget assumptions.
- Maker conversations launched from a selected Skill/Agent/Workflow include that
  selected asset detail explicitly.

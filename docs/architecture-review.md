# Architecture Review: Creator Asset Workspace

Reviewed on 2026-08-13 against the current codebase.

This report replaces older review notes. The product direction is now clear:
the app is a creator workspace with context assets and capability assets, not a
generic agent platform.

## Current implementation snapshot

### 内容资产

Implemented and product-specific:

- Default workspace
- Creator Dossier input assets:
  - 账号概况
  - historical posts
  - comment samples
  - video creation samples
  - XHS creator profile
- Other input/media assets:
  - uploaded trend data
  - image-text assets
  - video assets
- Analysis runs:
  - account diagnosis
  - trend analysis
  - video creator quality diagnosis
- Topic library
- Draft / content structure records
- Audience simulation runs

The frontend now groups InputAsset categories and reusable outputs together as
内容资产. It no longer exposes Input Assets and Reusable Outputs as separate
sidebar section titles.

### Capability assets

Implemented as internal workspace assets:

- Skills
- Agents
- Workflow assets
- Agent conversations

The newest capability additions are:

- one `Capability Maker` agent with Skill / Agent / Workflow design skills;
- one `Creator Dossier Formatter` agent with formatter skills for creator dossier child assets;
- one `Media Generation Operator` agent with Qwen media understanding and
  generation skills.

Capability Maker currently generates proposals through the existing conversation
surface. It does not directly mutate Skill, Agent, or Workflow definitions.

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
- Qwen vision chat completions for controlled image/video understanding skills
- DashScope async media tasks for controlled image/video generation skills
- Local ffmpeg-based preview-frame extraction for uploaded video assets

The browser no longer receives model API keys.

### Frontend API path

Frontend API calls use relative `/api/...` paths. Local Vite development
proxies `/api` to `http://127.0.0.1:8000`; production/VPS sharing must serve
frontend and backend under the same public origin or reverse-proxy `/api` to
FastAPI.

## What is aligned

- The product is workspace-first and creator-specific.
- 账号概况 is treated as a reusable input asset.
- Input assets are constrained to product types, not arbitrary files.
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

Current status: improved.

Analysis run creation now accepts an `idempotencyKey`. Repeating the same
workspace + key returns the existing run instead of creating another one. The
frontend sends a client-generated key for user-triggered single workflow creation.

Remaining gap: the workflow worker still has no durable SQLite claim/lease
metadata. Agent conversation replies now have a lightweight SQLite job table,
but workflow runs still rely on persisted run state plus in-process tasks.

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

Current status: improved.

When a maker conversation is launched from a selected Skill/Agent/Workflow
detail page, the frontend sends a `contextTarget` and the backend injects a
`selected_capability_asset` item into the context pack.

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

### Improved — conversation execution has a lightweight durable job record

Live conversation model failures now create an assistant failure message instead
of leaving only the user message. The failure is recorded in message
`modelMetadata`.

Recent update:

- sending a message now creates the user message and an assistant placeholder;
- sending a message also creates an `agent_conversation_jobs` row that stores
  conversation, assistant message, original user content, mode, status, attempt
  count, error, and timestamps;
- the placeholder records `queued`, `running`, `completed`, or `failed` in
  message metadata;
- the placeholder also records `queuedAt`, `startedAt`, and `completedAt` where
  applicable;
- backend in-process tasks generate the assistant reply after the request
  returns;
- startup recovery resumes queued/running conversation jobs and still supports
  legacy recovery from assistant message metadata;
- frontend observes pending replies by polling the conversation.

Remaining gap: this is still a single-process local worker without cross-process
claim/lease semantics. It is sufficient for the current local product, but it is
not a production distributed queue.

### Improved — input asset formatter is now a backend skill invocation

Older risk: the Creator Dossier Formatter agent existed in the UI, but pasted input
was transformed by local frontend helper logic.

Current status: improved.

The formatter path now uses:

- `Creator Dossier Formatter` agent as the product role;
- `input_asset.format_*` skills as the callable capability contracts;
- `POST /api/skills/{skill_asset_id}/invoke` as the backend invocation path;
- deterministic backend formatter implementations for the current product
  input asset types.
- `Media Generation Operator` agent as the product role for media inspection
  and generation;
- `media.understand_image`, `media.understand_video`,
  `media.generate_image`, and `media.generate_video` as directly callable
  Qwen media skills.

Remaining gap: formatter skills are deterministic code implementations today.
They are real backend skill calls, but not yet model-backed formatters.

### Improved — skills have a controlled invocation surface

Older risk: Skills were only descriptive capability contracts.

Current status: improved.

The backend now exposes a controlled skill invocation endpoint for directly
callable product skills. Current direct invocation is intentionally limited to
input asset formatter skills and Qwen media skills. Analysis, topic, draft,
simulation, and video diagnosis skills support deterministic dry-run, which
validates their output contract without creating product artifacts. Non-callable
skills return a clear 422 response.

Remaining gap: this is not a general code tool runtime. That is intentional for
the current product version.

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
- no retry policy is stored per stage;
- no structured worker failure record separate from workflow stage failure.

Recommended next step:

- Keep the in-process worker, but add SQLite job claim metadata:
  `claimed_at`, `claim_owner`, `attempt_count`, `last_heartbeat_at`.

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

### P1 — conversation execution is durably recorded but not lease-based

Agent conversation message sending now returns before the live model call
finishes. The assistant placeholder carries message-level status, an
`agent_conversation_jobs` row records execution lifecycle, and the frontend
observes persisted state.

Remaining risks:

- process crash during an external model call may repeat the current assistant
  reply on restart;
- no SQLite claim/lease table for cross-process conversation workers;
- per-message client idempotency keys now prevent duplicate user/assistant
  message creation on ordinary frontend retry, but they do not replace a durable
  job queue;
- explicit duplicate sends are still guarded while a queued/running assistant
  message exists.

Recommended fix:

- Keep the current lightweight implementation for local use.
- Add claim/lease only if conversation becomes a central long-running execution
  path or the app moves beyond one local backend process.

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

### P1 — Qwen provider structured-output hardening is improved but incomplete

Qwen support is correctly isolated behind `ModelCallService`, but structured
output still relies on prompt-only JSON.

Implemented:

- Qwen requests include `response_format: {"type": "json_object"}`;
- parser handles fenced JSON;
- parser extracts the first JSON object from responses with surrounding prose;
- parser unwraps conservative `data`, `result`, or `output` wrapper objects when
  the nested object contains the required operation root field;
- parser normalizes common qwen aliases such as `pain_points`,
  `proposed_actions`, and `video_quality` before final operation-level
  validation;
- parser can read OpenAI-compatible `function_call.arguments` or
  `tool_calls[].function.arguments` when message content is blank;
- parsed output is validated against operation-level required root fields and
  basic container types;
- agent chat can still gracefully treat plain text as a reply, but malformed
  JSON that is missing required fields is rejected.
- Qwen media understanding requests require structured `imageUnderstanding` /
  `videoUnderstanding` output;
- local uploaded video understanding derives preview frames first and sends those
  frame images to Qwen instead of uploading the full video file;
- media understanding results are staged as user-confirmed derived JSON before
  being reused by workflows;
- tests cover realistic qwen-compatible response shapes through sanitized
  fixtures.

Remaining risks:

- Qwen model variants may differ in tool/JSON support;
- error responses are reduced to status code, which is safe but weak for local
  debugging.

Recommended fix:

- Log sanitized provider error body in backend logs, not in frontend responses.
- Add more integration fixtures for real qwen edge cases.

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

The file is still large. Several pure or semi-contained pieces have been
extracted, including workspace shell, media assets page, input assets page,
account profile page, workflow output panel, stage/result presentation
components, asset proposals panel, agent conversation panel, agent/workflow/
conversation pages, and pending conversation polling. The main workspace state
machine and several page renderers still live in `App.tsx`.

Recommended split:

- `TopicLibraryPage`
- `DraftsPage`
- `AnalysisHistoryPage`
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
- Creator Dossier
  - 账号概况
  - historical posts
  - comment samples
  - video creation samples
  - XHS creator profile
- Other Input Asset
  - trend data
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

1. Add pack-level context budget metadata.
2. Add durable worker claim/lease metadata if repeated external calls become a
   practical problem.
3. Add durable conversation job records if conversations become central.
4. Add per-action proposal schema validation.
5. Continue splitting `frontend/src/App.tsx` into shell/page/hooks modules.

## Acceptance criteria for the next architecture pass

- Context packs show total size, source refs, exact/summarized/omitted assets,
  and provider/model budget assumptions.
- Proposal payloads are editable before apply and validated per action type.

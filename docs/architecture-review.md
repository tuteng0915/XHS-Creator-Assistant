# Architecture Review: Creator Asset Workspace

## Current direction

The product is no longer just a migrated single-page workflow demo. It is becoming a creator asset workspace with two asset families:

- **Context assets**: account profile, source materials, analysis runs, topics, drafts/structures, audience simulations.
- **Capability assets**: skills, agents, workflows, and workflow calls.

The important boundary is not “users can never edit workflows.” The boundary is:

- these assets are product-specific, not a generic filesystem or generic agent platform;
- skill/agent/workflow definitions are treated by the codebase as composable assets;
- for now, capability assets are inspectable in the UI but not user-editable from the frontend;
- execution remains fixed and controlled by backend product services.

The current layout direction is aligned:

- left column: context/output assets;
- right column: workflow calls and capability assets;
- main panel: focused management or execution surface;
- combining a left-side asset with a right-side call should become the product interaction model.

## What is already aligned

- Workspaces are creator/account scoped.
- Account profile has become a first-class workspace input rather than only a form field.
- Source materials are product-specific: historical posts, comments, trend CSV.
- Analysis runs are persisted and reopenable.
- Topic Library stores reusable topics from account diagnosis, trend analysis, and manual entry.
- Draft/structure records exist and separate generated snapshots from editable content.
- Audience simulations are persisted and reopenable.
- Skill, Agent, and Workflow assets exist as internal product assets.
- The UI no longer presents Content Drafts as a primary navigation destination.
- Workflow Calls are on the right-side capability column.
- Demo mode persists fixture inputs through the same integrated path instead of bypassing storage.
- LangGraph is used as an internal executor, not exposed as a frontend concept.

## Corrections from older review notes

The following older conclusions are no longer valid and should not guide future work:

- “There is no draft/content asset model.” Drafts now exist.
- “Content Drafts is only a placeholder.” It is no longer a primary nav item; drafts remain a backend artifact.
- “Do not add Agents or Workflows to the UI.” Capability assets are now part of the internal product model and right-side inspection surface.
- “Keep the sidebar restricted to only creator objects.” The revised layout intentionally separates creator context assets and capability assets.
- “The repository is untracked.” A baseline commit now exists.
- “README says product functionality is not implemented.” This must be kept current as implementation evolves.

## Current high-priority risks

### P0 — workflow execution lifecycle

Execution must not be owned by an SSE connection.

Target behavior:

- `POST` creates a run.
- Backend worker executes independently.
- Frontend observes status.
- Reconnects and refreshes do not duplicate paid/model calls.
- SSE, if retained, is observation-only.

This remains the most important backend correctness boundary.

### P0 — public mutation/model-call surfaces

Browser-accessible endpoints must not be able to forge run history or call arbitrary model operations.

Product API should expose:

- create run;
- get run;
- list history;
- create/select/edit/archive product artifacts.

Only backend workflow services should mutate stage results or invoke providers.

### P0 — asset relationship integrity

The durable product chain must remain explicit:

```text
Workspace
 -> SourceMaterial / AccountProfile
 -> AnalysisRun
 -> Topic
 -> Draft
 -> SimulationRun
```

Avoid text matching or implicit “current tab” inference when linking artifacts. Use IDs and immutable input snapshots.

### P1 — context access layer

Agents/workflows need broad access to creator context assets, but not arbitrary filesystem access.

The right model is a product-specific context access layer that gives agents a global workspace view:

- lookup account profile by workspace ID;
- retrieve selected source material by product type/ID;
- retrieve analysis run summaries/results;
- retrieve selected topic/draft;
- persist generated artifact through domain services;
- build broad workspace context packs with exact deep asset content where useful;
- record source refs, hashes, omissions, and budget decisions.

This can look MCP-like internally, but it should remain product-scoped and should not become a generic tool marketplace or filesystem bridge.

### P1 — skill/agent/workflow asset semantics

Current skill assets are still close to “prompted capability definitions.” The target model should be stronger:

- **Skill**: a reusable bounded capability with name, purpose, input contract, output contract, prompt/instructions, model policy, context requirements, and validation rules.
- **Agent**: a role with a system prompt plus an allowed skill set.
- **Workflow**: a product-specific multi-agent/multi-skill task graph with fixed code-owned execution semantics.

For now these are editable by developers through code/database seed/migrations, not by end users in the frontend.

### P1 — per-node context minimization

Every model call should declare:

- input fields;
- source asset IDs;
- included global workspace context;
- deep exact asset requests;
- summarization/truncation rule;
- output schema;
- downstream consumers.

The graph state should hold compact structured data and references, not complete workspace state or raw uploaded files. The model-call context pack may be broad; the durable graph state should remain compact.

### P1 — frontend state isolation

The UI must not share one global stage view across account diagnosis, trend analysis, and audience simulation. Each product execution surface needs its own state keyed by workflow/run identity.

This prevents results from one run appearing in the wrong panel after switching pages, reopening history, or running simulations from drafts.

### P1 — demo mode parity

Demo mode should approximate the original prototype’s examples, but it must use the same persistence and execution paths as live mode. Demo fixtures should never masquerade as live generated artifacts.

### P2 — componentization

`frontend/src/App.tsx` is still too large. The next maintainability step is to split by product surface:

- workspace shell/layout;
- account profile/materials;
- workflow calls;
- analysis history;
- topic library;
- capability asset inspectors;
- simulation history;
- shared renderers for profile/pain/topic/structure/simulation outputs.

This is important, but less urgent than execution lifecycle and artifact correctness.

## Product model to preserve

### Context assets

- Workspace
- Account Profile
- Source Material
- Analysis Run
- Topic
- Draft / Content Structure
- Simulation Run

These are user-facing product records.

### Capability assets

- Skill
- Agent
- Workflow Asset
- Workflow Call

These are product-owned capability records. They may be rendered for inspection and internal management, but they are not a generic builder surface.

## Skill interpretation

A prompt alone is not a full skill.

A proper product skill should include:

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

This lets skills be composed by agents and workflows without letting them access arbitrary workspace data.

## Agent interpretation

An agent is not a permanent autonomous user-configured bot. In this product it is a reusable runtime role:

- system prompt/personality/decision frame;
- allowed skill list;
- context access policy;
- output obligations;
- failure behavior.

Audience simulation personas are not the same as configurable platform agents. They are product-specific runtime roles generated inside a simulation run.

## Workflow interpretation

A workflow is a product-owned node graph over agents/skills/tasks.

It should store:

- workflow key;
- version;
- product purpose;
- node definitions;
- fixed edges/routing policy;
- required input assets;
- generated output assets;
- visible stage mapping.

It should not expose arbitrary frontend editing yet.

## Context access design

Preferred direction:

```text
Workflow node
  -> requests broad workspace context + deep asset refs
  -> Context Access service resolves product assets
  -> node receives a global but budget-aware context pack
  -> node returns structured output
  -> Domain service persists product artifact
```

Examples:

- Account profile analysis receives the workspace profile, historical post content/projection, and broader topic/history context.
- Comment pain-point analysis receives comments plus workspace profile and relevant prior audience context.
- Trend analysis receives ranked top-50 CSV projection, keyword, account profile, and related topic/history context.
- Topic generation receives prior structured results plus topic library and draft/simulation history to avoid repetition.
- Draft generation receives selected topic plus relevant voice/structure signals and surrounding topic/draft history.
- Audience reaction receives one persona, the topic/draft target, and a simulation-specific workspace context pack.

## What not to add now

- Generic filesystem
- Generic folder tree
- Arbitrary file editing
- Monaco editor
- Plugin marketplace
- User-editable workflow builder
- Generic MCP exposure to the frontend
- Authentication/multi-tenancy/organization management
- Cloud object storage
- Vector database
- VS Code-like workspace

## Recommended priority order

1. Finish execution lifecycle refactor: create run, worker executes, UI observes.
2. Remove or lock public execution mutation/model-call endpoints.
3. Enforce explicit artifact relationships by ID.
4. Build the product-specific context access layer for broad workspace packs.
5. Strengthen Skill/Agent/Workflow asset schemas and seed/version strategy.
6. Keep demo mode on the same persistence path as live mode.
7. Split the large frontend file after behavior is stable.
8. Add stronger restart, duplicate-run, and context-exclusion tests.

## Acceptance criteria for the next architecture pass

- A browser refresh cannot start duplicate execution.
- Reopening a history item cannot route output to the wrong workflow panel.
- Running simulation from a draft does not require unrelated source material inputs.
- Every generated user-visible artifact has a database record.
- Every model call can prove which context assets it received, which assets were summarized, and which were omitted due to budget or product boundary.
- Skill/Agent/Workflow assets are inspectable and internally composable, without becoming a generic builder.

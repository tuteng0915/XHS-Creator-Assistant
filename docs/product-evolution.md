# Product Evolution Plan

This document organizes the future product direction from the attached Product Evolution Specification and maps it onto the current migrated implementation.

The product direction is: a persistent creator workspace where conversation can trigger fixed creator workflows, and every meaningful generation becomes a reusable artifact.

This is not a generic chatbot, agent builder, workflow editor, filesystem, IDE, or marketplace.

## 1. Product Vision

The application should evolve from a single prototype workflow into a workspace-centric AI product for creators.

Creators should be able to:

- understand audience and content performance;
- discover new content opportunities;
- generate, select, and refine topics;
- generate and edit drafts;
- simulate audience reactions;
- accumulate reusable creative assets over time.

The core product principle is:

```text
The workspace stores long-term value.
Conversation is the interface that drives workflow execution.
```

## 2. Three Product Layers

```text
Workspace Layer
  stores creator assets and relationships

Conversation Layer
  interprets user intent and presents results

Workflow Execution Layer
  runs fixed domain workflows through backend services and LangGraph
```

The layers must stay separate:

- Workspace owns product memory and artifact history.
- Conversation owns interaction.
- LangGraph owns execution control flow and temporary state.

## 3. Workspace Layer

The workspace is the durable product surface.

Current and future workspace artifacts:

- creator profile / account positioning;
- source materials;
- account diagnosis runs;
- trend analysis runs;
- topics;
- drafts;
- audience simulation runs;
- future refinement runs.

The intended artifact chain is:

```text
Source Material
  ↓
AnalysisRun
  ↓
Topic
  ↓
Draft
  ↓
SimulationRun
```

Workspace artifacts should be:

- persistent;
- reusable;
- traceable;
- connected by explicit relationships.

The workspace should not become:

- a generic filesystem;
- a folder manager;
- an arbitrary document editor.

## 4. Conversation Layer

Conversation should be an action interface, not the product memory itself.

The desired pattern is:

```text
User Message
  ↓
Intent / Action Recognition
  ↓
Fixed Domain Workflow or Artifact Action
  ↓
Workspace Artifact Create / Update
  ↓
Conversation Summarizes Result
```

Examples:

```text
User: 帮我分析一下这个账号最近为什么涨不起来
Intent: ACCOUNT_DIAGNOSIS
Action: create AnalysisRun
Artifact: AnalysisRun + generated Topic candidates
```

```text
User: 这个选题换一个更年轻的角度
Intent: MODIFY_TOPIC
Action: topic refinement
Artifact: update Topic editable fields or create Topic revision
```

Conversation should not behave as:

```text
User Message
  ↓
General LLM agent
  ↓
Arbitrary action
```

## 5. Fixed Domain Workflows

Workflows are product capabilities. They are not user-configured agent graphs.

### 5.1 Account Diagnosis

Purpose:

- understand creator positioning;
- analyze historical content performance;
- identify audience pain points;
- generate topic candidates.

Inputs:

- workspace account positioning;
- historical posts source material;
- comment source material.

Process:

```text
Profile Analysis
  +
Pain Point Analysis
  ↓
Topic Generation
```

Outputs:

- AnalysisRun;
- structured stage results;
- Topic candidates.

### 5.2 Trend Analysis

Purpose:

- analyze external trend data;
- discover creator-relevant content opportunities.

Inputs:

- uploaded trend CSV dataset;
- creator positioning.

Process:

```text
Trend Pattern Analysis
  +
Pain Point Analysis
  ↓
Topic Generation
```

Outputs:

- AnalysisRun;
- trend themes;
- pain points;
- Topic candidates.

### 5.3 Draft / Content Structure Generation

Purpose:

- turn a selected Topic into a persistent creator draft.

Inputs:

- selected Topic;
- compact analysis-derived context;
- creator positioning.

Outputs:

- Draft;
- generated snapshot;
- editable content separated from generated snapshot.

### 5.4 Audience Simulation

Purpose:

- evaluate a Topic or Draft from product-specific audience perspectives.

Inputs:

- saved Topic, saved Draft, or manual topic text;
- creator positioning snapshot.

Process:

```text
Persona Generation
  ↓
Parallel Initial Reactions
  ↓
Persona Discussion
  ↓
Synthesis
```

Outputs:

- SimulationRun;
- persona definitions;
- initial reactions;
- debate responses;
- synthesis and improvement suggestions.

### 5.5 Future Refinement Workflows

Likely additions:

- topic refinement;
- draft rewrite;
- title variant generation;
- hook improvement;
- simulation-based draft revision;
- content calendar / topic prioritization.

Each should create or update a product artifact, not return only transient chat text.

## 6. Agent Architecture Principle

Agents are implementation details.

The user-facing product should expose:

- workflows;
- actions;
- artifacts;
- results.

The user-facing product should not expose:

- agents;
- nodes;
- tools;
- graph state;
- checkpoints;
- LangGraph thread IDs.

Users should not configure:

- agent topology;
- workflow graph;
- tool selection rules.

## 7. LangGraph Role

LangGraph should remain an internal execution engine.

LangGraph owns:

- workflow execution state;
- node transitions;
- conditional routing;
- retries;
- interruption and resume mechanics;
- temporary computation state.

LangGraph does not own:

- workspace data;
- product entities;
- creator assets;
- user-visible history.

Architecture boundary:

```text
Product Database
  Workspace
  SourceMaterial
  AnalysisRun
  Topic
  Draft
  SimulationRun

      ↑ persisted inputs/results

LangGraph
  execution
  routing
  retries
  checkpoints
```

## 8. Workflow Configuration

The system should support configurable workflows for developer and product iteration.

This is not an agent builder.

Configuration may include:

- model provider;
- model name;
- temperature;
- token limits;
- prompt version;
- output schema reference;
- context policy;
- retry policy.

Possible structure:

```text
backend/app/workflow_configs/
  account_diagnosis.json
  trend_analysis.json
  audience_simulation.json
  draft_generation.json
```

Example:

```json
{
  "workflow": "topic_generation",
  "model": {
    "provider": "anthropic",
    "name": "claude-sonnet"
  },
  "generation": {
    "temperature": 0.7,
    "max_tokens": 2000
  },
  "prompt_version": "v2",
  "context_policy": "account_topics_v1",
  "output_schema": "topics_v1"
}
```

Configuration boundaries:

- Users may choose product-level preferences such as creativity level, content style, target audience, or preferred goals.
- Users should not edit internal prompts, workflow graphs, agent topology, or tool execution rules.

## 9. Context Management Principle

Every workflow node should have an explicit context contract.

Each node should define:

```text
Input:
  source
  fields
  size limit

Output:
  schema
  downstream usage
```

Avoid passing:

- entire workspace;
- entire conversation history;
- all source materials;
- all previous workflow outputs.

Example:

Topic generation needs:

- creator positioning;
- profile analysis;
- pain points.

It does not need:

- raw comments;
- unrelated simulations;
- full draft history;
- complete chat transcript.

The current project already has `docs/llm-context-audit.md`; future workflow additions should update that document.

## 10. Artifact-First Design

Every meaningful generation should create or update a workspace artifact.

Avoid:

```text
User asks
  ↓
LLM response
  ↓
Nothing saved
```

Prefer:

```text
User action or message
  ↓
Workflow execution
  ↓
Artifact creation/update
  ↓
Conversation summarizes result
```

Examples:

- generating topics creates Topic artifacts;
- generating content creates Draft artifacts;
- running audience simulation creates SimulationRun artifacts;
- refining a topic updates Topic editable fields or creates a topic revision;
- revising a draft updates Draft editable content while preserving generated snapshot.

## 11. Roadmap

### Phase 1: Stabilization

Goal:

- make current workflows reliable and persistent.

Current status:

- mostly implemented.

Covered work:

- workspace persistence;
- source materials;
- analysis history;
- topic library;
- draft entity;
- simulation history;
- LangGraph account diagnosis;
- LangGraph trend analysis;
- LangGraph audience simulation;
- backend worker lifecycle;
- observation-only SSE;
- context audit.

Remaining / follow-up:

- improve demo parity and presentation polish;
- ensure all production paths avoid prototype-only fixtures;
- add more failure recovery UX;
- improve generated artifact browsing.

### Phase 2: Conversation Interface

Goal:

- let users drive fixed product workflows naturally.

Minimum capabilities:

- conversation panel attached to selected workspace;
- intent recognition;
- action confirmation where needed;
- workflow run creation;
- artifact update creation;
- result summary with artifact links.

Initial intents:

- `ACCOUNT_DIAGNOSIS`
- `TREND_ANALYSIS`
- `GENERATE_DRAFT`
- `RUN_SIMULATION`
- `MODIFY_TOPIC`
- `REWRITE_DRAFT`
- `SELECT_TOPIC`
- `SHOW_HISTORY`

Important constraint:

- conversation should call product services, not arbitrary tools.

### Phase 3: Workflow Configuration

Goal:

- enable faster prompt/model iteration without turning the product into an agent builder.

Minimum capabilities:

- config files loaded at backend startup;
- prompt version stored in run metadata;
- model config stored in run metadata;
- output schema validation remains in code or schema registry;
- tests lock current behavior for existing configs.

### Phase 4: Advanced Workflow Capabilities

Possible directions:

- iterative refinement loops;
- self-review nodes;
- human approval points;
- simulation-guided draft rewrite;
- multi-stage content package generation;
- workflow planning within fixed domain boundaries.

These should extend current product workflows rather than replace them with a generic agent platform.

## 12. Implementation Principles

1. Workspace-centric, not chat-centric.
2. Conversation-driven, not conversation-dependent.
3. Fixed-domain workflows, not agent builders.
4. Configurable workflows, not configurable agents.
5. LangGraph for execution, SQLite for product memory.
6. Artifacts over messages.
7. Structured context over unlimited history.
8. Persistent value over one-time generation.

## 13. Current Conversation / Capability Implementation Status

### Implemented

The project now has the first conversation and capability-asset layer:

- workspace-scoped agent conversations;
- persisted user and assistant messages;
- assistant message `proposedActions`;
- provider-backed live replies through `ModelCallService`;
- deterministic demo replies for local testing;
- Skill, Agent, and Workflow assets;
- maker agents:
  - `Skill Maker`;
  - `Agent Maker`;
  - `Workflow Maker`.

Conversation is still not the source of truth for artifacts. It is an interface
for proposing or triggering product actions.

### Current gap: proposals are not yet assets

Maker agents currently produce chat replies and `proposedActions`, but those
actions are not structured proposal records.

Next step:

- add `AssetProposal`;
- store proposal kind: `skill`, `agent`, or `workflow`;
- store source conversation/message ID;
- validate proposal JSON through product-specific schemas;
- allow confirm/apply through domain services.

### Current gap: capability context is incomplete

Maker agents should see the existing capability catalog, but current broad
workspace context packs focus on creator context assets.

Next step:

- add Skill / Agent / Workflow overviews to `ContextAccessService`;
- include selected capability asset details when a maker is launched from a
  detail page;
- cite capability assets with source refs and hashes.

### Still future

Static workflow config files are still future:

- load and validate at startup;
- record config version in AnalysisRun / SimulationRun / Draft metadata;
- keep graph topology in code.

Artifact refinement workflows are also still future:

- refine Topic;
- rewrite Draft from simulation feedback.

These are the first workflows where conversation becomes materially useful.

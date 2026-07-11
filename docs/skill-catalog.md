# Creator Product Skill Catalog

This document reframes the current product capabilities as composable product skills.

The goal is not to create a generic agent platform. A skill is a product-specific capability with a typed contract, explicit context requirements, and clear artifact effects.

Agents are product roles composed from skills.

Workflows are multi-agent, multi-task product plans composed from agents and skills.

Conversation should eventually select and sequence these assets, but users should not configure arbitrary graphs, tools, or filesystem actions.

## 1. Definition

A product skill is:

```text
Typed product capability
  + bounded context contract
  + structured output
  + artifact effect
  + clear composition rules
```

A skill is not:

- a generic tool;
- a plugin;
- a whole agent role by itself;
- a LangGraph node name exposed to users;
- an arbitrary code execution unit;
- a filesystem operation.

## 1.1 Asset Hierarchy

The workspace now has three levels of capability assets:

```text
Skill
  smallest product capability with typed inputs, context policy, output schema, and artifact effect

Agent
  product role with a system prompt, multiple skill IDs, and a default context policy

Workflow
  multi-agent, multi-level task plan with entry agents, task dependencies, and artifact effect
```

These assets are metadata and control surfaces for this creator product. They are not a generic filesystem, agent marketplace, workflow editor, or arbitrary code execution platform.

For the current product stage, these assets have two different surfaces:

- User-facing product UI: read-only inspection. Users can see what capabilities exist, but cannot directly edit skill contracts, agent prompts, agent skill sets, or workflow task plans.
- Engineering/product implementation: composable and editable assets. We should be able to add, edit, disable, and recompose skills, agents, and workflows through code, migrations, seed data, internal tooling, or future admin surfaces.

This distinction is intentional. The product should treat these as real assets internally without turning the creator-facing workspace into a generic agent configuration tool.

### Agent Contract

| Field | Meaning |
| --- | --- |
| `agent_id` | Stable internal identifier |
| `display_name` | Product-facing name if shown in UI |
| `purpose` | Product role this agent plays |
| `system_prompt` | Default role prompt used by implementations |
| `skill_ids` | Skills this agent may use |
| `default_context_policy` | Default context boundary before node-specific filtering |
| `artifact_effect` | Usually inherited from the invoked skill or workflow |
| `status` | Workspace-level enabled / disabled flag |
| `user_notes` | Internal/workspace-local notes; not execution history |

An agent is more than a prompt. It is a role boundary plus an allowed skill set and context policy. The current implementation persists built-in agent assets per workspace, but workflow execution still runs through existing product services. The creator-facing UI should not expose direct editing controls for this asset.

### Workflow Asset Contract

| Field | Meaning |
| --- | --- |
| `workflow_id` | Stable internal identifier |
| `display_name` | Product-facing name |
| `purpose` | Product job completed by the workflow |
| `entry_agent_ids` | Agents that initiate or own top-level tasks |
| `agent_plan` | Product-specific task plan with agent IDs, skill IDs, dependencies, and parallel hints |
| `artifact_effect` | Durable artifacts created or updated |
| `status` | Workspace-level enabled / disabled flag |
| `user_notes` | Internal/workspace-local notes; not execution history |

Workflow assets describe product intent and composition. They do not replace LangGraph graphs, AnalysisRun, Draft, or SimulationRun persistence. The creator-facing UI should not expose direct workflow editing controls.

## 2. Skill Contract

Every skill should eventually be described by this contract:

| Field | Meaning |
| --- | --- |
| `skill_id` | Stable internal identifier |
| `display_name` | Product-facing name if shown in UI |
| `purpose` | What product job this skill performs |
| `trigger_intents` | User intents that may invoke the skill |
| `required_inputs` | Required artifact IDs, snapshots, or text fields |
| `optional_inputs` | Optional context that may improve output |
| `context_policy` | Exact fields allowed into model context |
| `output_schema` | Structured output contract |
| `artifact_effect` | What artifact is created, updated, or read |
| `side_effects` | Persistence, run creation, status transitions |
| `failure_mode` | Whether partial output is allowed |
| `composable_with` | Skills that can safely consume this skill's output |

The context policy is mandatory. A skill should not receive the whole workspace or whole conversation history by default.

The concrete access design is defined in `docs/agent-context-access.md`. In short, agents should request bounded context packs through a Context Access Layer; they should not read SQLite, uploaded files, or whole workspace state directly.

## 3. Skill Granularity Rules

A good skill is small enough to compose, but large enough to be product-meaningful.

Good examples:

- analyze historical content profile;
- extract pain points from comments;
- rank trend CSV posts;
- generate topics from analysis outputs;
- generate draft structure from a selected topic;
- simulate initial audience reactions.

Bad examples:

- "call LLM";
- "run agent";
- "read any file";
- "edit anything";
- "do workflow";
- "think about content".

## 4. Current Skill Inventory

### 4.1 Workspace and Material Skills

#### `workspace.update_profile`

Purpose:

- update workspace name and account positioning.

Inputs:

- workspace ID;
- name;
- account positioning text;
- optimistic concurrency timestamp.

Output:

- updated Workspace.

Artifact effect:

- updates `Workspace`.

Composition:

- should run before analysis or simulation when the user has edited positioning.

Current implementation:

- `WorkspaceService.update`
- frontend auto-save before generation.

#### `source.save_historical_posts`

Purpose:

- persist reusable historical post material.

Inputs:

- workspace ID;
- historical posts text.

Output:

- SourceMaterial of type `historical_posts`.

Artifact effect:

- creates or updates text source material.

Composition:

- consumed by `analysis.profile_from_history`.

Current implementation:

- `SourceMaterialService.create_text`
- `SourceMaterialService.update`.

#### `source.save_comments`

Purpose:

- persist reusable comment sample material.

Inputs:

- workspace ID;
- comment text.

Output:

- SourceMaterial of type `comments`.

Artifact effect:

- creates or updates text source material.

Composition:

- consumed by `analysis.pain_points_from_comments`.

Current implementation:

- `SourceMaterialService.create_text`
- `SourceMaterialService.update`.

#### `source.upload_trend_csv`

Purpose:

- persist uploaded trend CSV / TSV source material.

Inputs:

- workspace ID;
- keyword;
- uploaded CSV / TSV file.

Output:

- SourceMaterial of type `trend_csv` with preview metadata.

Artifact effect:

- stores original upload on disk;
- stores metadata in SQLite.

Composition:

- consumed by `trend.rank_posts`.

Current implementation:

- `SourceMaterialService.create_csv`.

#### `trend.rank_posts`

Purpose:

- deterministically parse and rank trend CSV rows before model execution.

Inputs:

- trend CSV source material ID.

Output:

- compact top-50 ranked post snapshot.

Artifact effect:

- currently embedded into `AnalysisRun.inputSnapshot`.

Composition:

- consumed by `analysis.trend_patterns`;
- consumed by `analysis.pain_points_from_trend_posts`.

Current implementation:

- `AnalysisRunService._rank_trend_posts`.

## 5. Analysis Skills

### `analysis.profile_from_history`

Purpose:

- infer account content pillars, title formulas, hook styles, viral structure, voice fingerprint, and performance contrast from historical posts.

Inputs:

- workspace positioning snapshot;
- historical posts material content.

Output schema:

- `profile`
  - `pillars`
  - `titleFormulas`
  - `hookStyles`
  - `viralStructure`
  - `voiceFingerprint`
  - `contrast`

Artifact effect:

- writes `AnalysisRun.stageResults.profile`.

Composition:

- consumed by `topic.generate_from_account_diagnosis`;
- consumed by `draft.generate_structure` through compact analysis context.

Current implementation:

- `ModelOperation.PROFILE`
- `AccountDiagnosisWorkflowService.profile_analysis`.

### `analysis.pain_points_from_comments`

Purpose:

- extract audience pain points from comment samples.

Inputs:

- comments text.

Output schema:

- `painPoints[]`
  - `theme`
  - `intensity`
  - `count`
  - `evidence`

Artifact effect:

- writes `AnalysisRun.stageResults.pain_points`.

Composition:

- consumed by `topic.generate_from_account_diagnosis`.

Current implementation:

- `ModelOperation.PAIN_POINTS`
- account diagnosis parallel branch.

### `analysis.trend_patterns`

Purpose:

- summarize trend themes, viral patterns, and opportunity windows from ranked trend posts.

Inputs:

- workspace positioning snapshot;
- trend keyword;
- compact top-50 ranked posts text.

Output schema:

- `trendAnalysis`
  - `themes`
  - `viralPatterns`
  - `opportunityWindows`

Artifact effect:

- writes `AnalysisRun.stageResults.trend_analysis`.

Composition:

- consumed by `topic.generate_from_trend_analysis`.

Current implementation:

- `ModelOperation.TREND_ANALYSIS`
- `TrendAnalysisWorkflowService.trend_pattern_analysis`.

### `analysis.pain_points_from_trend_posts`

Purpose:

- infer reader pain points from trend post titles/content snippets.

Inputs:

- trend keyword;
- compact top-50 ranked posts text.

Output schema:

- `painPoints[]`

Artifact effect:

- writes `AnalysisRun.stageResults.pain_points`.

Composition:

- consumed by `topic.generate_from_trend_analysis`.

Current implementation:

- `ModelOperation.PAIN_POINTS`
- trend analysis pain-point branch.

## 6. Topic Skills

### `topic.generate_from_account_diagnosis`

Purpose:

- generate topic candidates from account profile and comment pain points.

Inputs:

- workspace positioning snapshot;
- profile result;
- pain point result.

Output schema:

- `topics[]`
  - `title`
  - `angle`
  - `pain`
  - `whyFit`
- `titles[]`

Artifact effect:

- writes `AnalysisRun.stageResults.topics`;
- topics may later be saved into `Topic` artifacts.

Composition:

- consumed by `topic.save_candidate`;
- consumed by `draft.generate_structure`;
- consumed by `simulation.run_from_topic`.

Current implementation:

- `ModelOperation.TOPICS`.

### `topic.generate_from_trend_analysis`

Purpose:

- generate topic candidates from trend patterns and trend pain points.

Inputs:

- workspace positioning snapshot;
- trend analysis result;
- pain point result.

Output schema:

- `topics[]`
  - `title`
  - `angle`
  - `pain`
  - `whyFit`
  - `whyTrending`
- `titles[]`

Artifact effect:

- writes `AnalysisRun.stageResults.topics`.

Composition:

- consumed by `topic.save_candidate`;
- consumed by `draft.generate_structure`;
- consumed by `simulation.run_from_topic`.

Current implementation:

- `ModelOperation.TREND_TOPICS`.

### `topic.save_candidate`

Purpose:

- convert a generated or manually entered topic into a persistent Topic artifact.

Inputs:

- workspace ID;
- title;
- angle;
- associated pain point;
- why it fits;
- optional source analysis run ID.

Output:

- Topic.

Artifact effect:

- creates Topic with generated snapshot separated from editable fields.

Composition:

- consumed by `topic.select`;
- consumed by `draft.generate_structure`;
- consumed by `simulation.run_from_topic`.

Current implementation:

- `TopicService.create`.

### `topic.select`

Purpose:

- mark a Topic as the current topic for the workspace.

Inputs:

- topic ID.

Output:

- selected Topic.

Artifact effect:

- updates topic status;
- updates workspace current topic.

Composition:

- used as shortcut before draft generation or simulation.

Current implementation:

- `TopicService.select`.

### `topic.refine` future

Purpose:

- modify a Topic according to user instruction.

Inputs:

- Topic current editable fields;
- user instruction;
- optional source analysis summary.

Output:

- updated title / angle / whyItFits.

Artifact effect:

- updates editable Topic fields;
- should preserve generated snapshot.

Composition:

- useful for conversation interface.

Current implementation:

- not implemented.

## 7. Draft Skills

### `draft.generate_structure`

Purpose:

- generate a persistent content structure from a selected Topic.

Inputs:

- topic ID;
- workspace positioning;
- compact analysis-derived context.

Output schema:

- `structure`
  - `topicChosen`
  - `outline`
  - `reuse`

Artifact effect:

- creates Draft;
- stores `generatedSnapshot`;
- initializes `editableContent`.

Composition:

- consumed by `draft.edit`;
- consumed by `simulation.run_from_draft`;
- future input to `draft.rewrite`.

Current implementation:

- `DraftGenerationService.generate_from_topic`
- `ModelOperation.STRUCTURE`.

### `draft.edit`

Purpose:

- persist user edits to current draft content.

Inputs:

- draft ID;
- editable content;
- optimistic concurrency timestamp.

Output:

- updated Draft.

Artifact effect:

- updates `Draft.editableContent`;
- does not modify `generatedSnapshot`.

Composition:

- consumed by `simulation.run_from_draft`.

Current implementation:

- `DraftService.update`.

### `draft.rewrite` future

Purpose:

- rewrite a draft based on user instruction or simulation feedback.

Inputs:

- Draft editable content;
- rewrite instruction;
- optional SimulationRun synthesis.

Output:

- updated draft editable content.

Artifact effect:

- updates Draft editable content;
- should preserve generated snapshot.

Composition:

- ideal first conversation-driven artifact update skill.

Current implementation:

- not implemented.

## 8. Audience Simulation Skills

### `simulation.normalize_target`

Purpose:

- turn Topic, Draft, or manual topic input into compact simulation context.

Inputs:

- topic ID, draft ID, or manual topic text.

Output:

- compact simulation target context.

Artifact effect:

- captured in `SimulationRun.inputSnapshot`.

Composition:

- consumed by all simulation model skills.

Current implementation:

- `SimulationRunService.create`;
- `AudienceSimulationWorkflowService._simulation_target_context`.

### `simulation.derive_personas`

Purpose:

- derive product-specific audience personas for the target topic or draft.

Inputs:

- workspace positioning snapshot;
- compact simulation target.

Output schema:

- `personas[]`.

Artifact effect:

- writes `SimulationRun.personaDefinitions`.

Composition:

- consumed by `simulation.initial_reactions`.

Current implementation:

- `ModelOperation.SIMULATION_PERSONAS`.

### `simulation.initial_reactions`

Purpose:

- simulate independent first reactions from each persona.

Inputs:

- one persona;
- compact simulation target.

Output schema:

- `reaction`.

Artifact effect:

- writes `SimulationRun.reactionResults`.

Composition:

- consumed by `simulation.debate_responses`;
- consumed by `simulation.synthesize`.

Current implementation:

- `ModelOperation.SIMULATION_REACTION`.

### `simulation.debate_responses`

Purpose:

- simulate second-round persona responses after seeing other reactions.

Inputs:

- one persona;
- compact simulation target;
- other initial reactions.

Output schema:

- `debateResponse`.

Artifact effect:

- writes `SimulationRun.debateResults`.

Composition:

- consumed by `simulation.synthesize`.

Current implementation:

- `ModelOperation.SIMULATION_DEBATE`.

### `simulation.synthesize`

Purpose:

- synthesize audience simulation into product guidance.

Inputs:

- compact simulation target;
- personas;
- initial reactions;
- debate responses.

Output schema:

- `synthesis`
  - verdict;
  - main resistance;
  - strongest angle;
  - content adjustments;
  - risk warnings;
  - optional top resonance / controversy / suggestions.

Artifact effect:

- writes `SimulationRun.synthesis`.

Composition:

- consumed by future `draft.rewrite`;
- consumed by conversation summary.

Current implementation:

- `ModelOperation.SIMULATION_SYNTHESIS`.

## 9. Workflow Assets as Agent Task Plans

### Account diagnosis workflow

```text
entry agents:
  creator_material_curator
  account_diagnosis_strategist

tasks:
  prepare_account_sources
    agent: creator_material_curator
    skills:
      workspace.update_profile
      source.save_historical_posts
      source.save_comments

  diagnose_account
    agent: account_diagnosis_strategist
    parallel: true
    skills:
      analysis.profile_from_history
      analysis.pain_points_from_comments

  generate_account_topics
    agent: account_diagnosis_strategist
    skills:
      topic.generate_from_account_diagnosis
```

Current artifact result:

- AnalysisRun;
- optional Topic artifacts when user saves candidates.

### Trend analysis workflow

```text
entry agents:
  creator_material_curator
  trend_opportunity_strategist

tasks:
  prepare_trend_sources
    agent: creator_material_curator
    skills:
      workspace.update_profile
      source.upload_trend_csv
      trend.rank_posts

  analyze_trend
    agent: trend_opportunity_strategist
    parallel: true
    skills:
      analysis.trend_patterns
      analysis.pain_points_from_trend_posts

  generate_trend_topics
    agent: trend_opportunity_strategist
    skills:
      topic.generate_from_trend_analysis
```

Current artifact result:

- AnalysisRun;
- optional Topic artifacts when user saves candidates.

### Topic-to-draft workflow

```text
entry agent:
  topic_draft_editor

tasks:
  select_topic
    skills:
      topic.save_candidate
      topic.select

  generate_draft
    skills:
      draft.generate_structure
```

Current artifact result:

- Draft.

### Audience simulation workflow

```text
entry agent:
  audience_simulation_researcher

tasks:
  normalize_target
    skills:
      simulation.normalize_target

  derive_personas
    skills:
      simulation.derive_personas

  initial_reactions
    parallel: true
    skills:
      simulation.initial_reactions

  debate_responses
    parallel: true
    skills:
      simulation.debate_responses

  synthesis
    skills:
      simulation.synthesize
```

Current artifact result:

- SimulationRun.

### Future simulation-guided rewrite plan

```text
simulation.synthesize
draft.rewrite
simulation.run_from_draft
```

Potential artifact result:

- updated Draft;
- new SimulationRun.

## 10. How Conversation Should Use Skills

Conversation should map user messages to skill plans.

Example:

```text
User: 帮我看看这个账号为什么涨不起来
Plan:
  workspace.update_profile if edited
  source.save_historical_posts if edited
  source.save_comments if edited
  analysis.profile_from_history
  analysis.pain_points_from_comments
  topic.generate_from_account_diagnosis
```

Example:

```text
User: 把这个选题改得更适合年轻人
Plan:
  topic.refine
```

Example:

```text
User: 根据刚才受众模拟的反馈，帮我改一下草稿
Plan:
  draft.rewrite using selected SimulationRun
```

The conversation layer should produce:

- selected skill or skill plan;
- selected agent role when a role boundary matters;
- selected workflow asset for multi-step product jobs;
- required missing inputs;
- artifact IDs created or updated;
- short user-facing summary.

It should not expose:

- LangGraph nodes;
- editable agent topology;
- arbitrary tool calls.

## 11. Skill Composition Rules

1. A skill may read artifacts and snapshots, but should only mutate its declared artifact effect.
2. A skill must not receive the entire workspace unless its contract explicitly needs it.
3. A skill that calls a model must define an output schema.
4. A skill that creates durable value should persist an artifact.
5. A skill output should be reusable by at least one downstream skill.
6. Composite workflows should be defined as product agent plans, not user-edited graphs.
7. Demo skills may use deterministic fixtures, but production paths should use the same artifact interfaces.

## 12. Implementation Direction

### Step 1: Document and stabilize skill contracts

This document is the first version of the product skill catalog.

Next, each existing skill should be reflected in code with stable internal IDs.

### Step 2: Introduce a skill registry

Add a lightweight internal registry such as:

```python
SkillDefinition(
    skill_id="analysis.profile_from_history",
    required_inputs=[...],
    output_schema="ProfileStageResult",
    artifact_effect="AnalysisRun.stageResults.profile",
)
```

This registry should be internal metadata, not a user-facing builder.

### Step 3: Represent agents and workflows as product assets

Current LangGraph workflows can keep their graph implementation, but product-level metadata should describe them as agent task plans.

Example:

```text
account_diagnosis:
  entry_agents:
    - creator_material_curator
    - account_diagnosis_strategist
  tasks:
    - diagnose_account:
        agent: account_diagnosis_strategist
        skills:
          - analysis.profile_from_history
          - analysis.pain_points_from_comments
```

### Step 4: Build conversation action dispatch on top of skills

The conversation layer should identify:

- single skill;
- skill plan;
- missing required inputs;
- artifact target.

Then it should call existing services, not arbitrary tools.

### Step 5: Add refinement skills

The first new skills should be artifact-update skills:

- `topic.refine`
- `draft.rewrite`
- `draft.rewrite_from_simulation`

These will validate whether the skill abstraction is useful beyond the current linear workflows.

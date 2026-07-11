# LLM Context Management Audit

This audit covers the current product LLM calls after the workflow lifecycle
change where POST creates a run, backend workers execute runs, and SSE only
observes persisted state.

The rule for this codebase is product-specific context passing: each model call
receives only the fields needed for that stage. Full source materials remain in
SQLite or uploaded files. Graph state stores IDs, snapshots, compact ranked data,
and structured stage results.

## Account diagnosis

### `PROFILE`

- Caller: account diagnosis `profile_analysis`.
- Prompt: `PROMPT_PROFILE`.
- Input fields:
  - `positioning`: workspace account positioning snapshot.
  - `historicalPosts`: selected historical posts source-material content.
- Unnecessary fields:
  - comments.
  - previous topics.
  - drafts.
  - simulations.
  - full workspace object.
- Token growth risk:
  - high if historical posts are pasted without limits.
  - current state keeps only material ID plus immutable input snapshot; the LLM call still uses full selected text material.
- Structured state dependencies:
  - `run_id`
  - `workspace_id`
  - `positioning_snapshot`
  - `historical_posts_material_id`
- Downstream consumers:
  - account topic generation.
  - topic library generated snapshots.
  - draft generation context via voice fingerprint and viral structure.

### `PAIN_POINTS` for account comments

- Caller: account diagnosis `profile_analysis` parallel branch.
- Prompt: `PROMPT_PAIN_POINTS`.
- Input fields:
  - `sourceText`: selected comment source-material content.
- Unnecessary fields:
  - account profile result.
  - historical posts.
  - topics.
  - drafts.
  - full workspace object.
- Token growth risk:
  - high if comments are pasted as an unbounded corpus.
- Structured state dependencies:
  - `comments_material_id`
- Downstream consumers:
  - account topic generation.
  - topic library generated snapshots.

### `TOPICS` for account diagnosis

- Caller: account diagnosis `topic_generation`.
- Prompt: `PROMPT_TOPICS`.
- Input fields:
  - `positioning`
  - `profile`
  - `painPoints`
- Unnecessary fields:
  - historical post raw text.
  - comment raw text.
  - complete workspace.
  - previous simulations.
- Token growth risk:
  - medium; bounded by structured profile and pain-point outputs.
- Structured state dependencies:
  - `positioning_snapshot`
  - `profile`
  - `pain_points`
- Downstream consumers:
  - topic cards.
  - topic library.
  - selected topic shortcut.
  - draft generation.
  - audience simulation.

## Trend analysis

### `TREND_ANALYSIS`

- Caller: trend analysis `trend_pattern_analysis`.
- Prompt: `PROMPT_TREND_ANALYSIS`.
- Input fields:
  - `positioning`
  - `trendKeyword`
  - `postsText`: deterministic top-50 CSV ranking rendered as compact text.
- Unnecessary fields:
  - complete CSV file contents beyond top-50 ranking.
  - comments source material.
  - historical posts source material.
  - topics.
  - drafts.
- Token growth risk:
  - medium; top-50 ranking is bounded, but each row can still contain long title/content/tag fields.
- Structured state dependencies:
  - `trend_csv_material_id`
  - `trend_keyword`
  - `ranked_posts`
  - `positioning_snapshot`
- Downstream consumers:
  - trend topic generation.
  - analysis history.

### `PAIN_POINTS` for trend posts

- Caller: trend analysis `pain_point_analysis`.
- Prompt: `PROMPT_PAIN_POINTS`.
- Input fields:
  - `sourceText`: short instruction plus the same compact ranked top-50 post text.
- Unnecessary fields:
  - full CSV content.
  - account diagnosis profile.
  - drafts.
  - simulations.
- Token growth risk:
  - medium for the same reason as `TREND_ANALYSIS`.
- Structured state dependencies:
  - `trend_keyword`
  - `ranked_posts`
- Downstream consumers:
  - trend topic generation.
  - topic library generated snapshots.

### `TREND_TOPICS`

- Caller: trend analysis `topic_generation`.
- Prompt: `PROMPT_TOPICS_B`.
- Input fields:
  - `positioning`
  - `trendAnalysis`
  - `painPoints`
- Unnecessary fields:
  - full CSV content.
  - compact ranked post text.
  - account historical posts.
  - comment source material.
  - draft content.
- Token growth risk:
  - medium; bounded by structured trend and pain-point results.
- Structured state dependencies:
  - `positioning_snapshot`
  - `trend_analysis`
  - `pain_points`
- Downstream consumers:
  - trend topic cards.
  - topic library.
  - selected topic shortcut.
  - draft generation.
  - audience simulation.

## Draft / content structure generation

### `STRUCTURE`

- Caller: user-triggered draft generation.
- Prompt: `PROMPT_STRUCTURE`.
- Input fields:
  - `positioning`
  - `topic`: selected topic title.
  - `background`: compact derived context from the source analysis run, currently including relevant voice fingerprint and viral structure when available.
- Unnecessary fields:
  - source material raw text.
  - full analysis run input snapshot.
  - full topic library.
  - simulation results.
- Token growth risk:
  - low to medium; background is structured and compact.
- Structured state dependencies:
  - topic entity fields.
  - draft input snapshot.
  - selected source analysis result fragments.
- Downstream consumers:
  - draft record `generatedSnapshot`.
  - draft record `editableContent`.
  - optional audience simulation from draft.

## Audience simulation

### `SIMULATION_PERSONAS`

- Caller: audience simulation `derive_personas`.
- Prompt: `PROMPT_SIMULATION_PERSONAS`.
- Input fields:
  - `positioning`
  - compact simulation target:
    - `targetType`
    - `topicId`
    - `title`
    - `angle`
    - `associatedPainPoint`
    - `whyItFits`
    - `sourceWorkflow`
    - optional `draft.editableContent`
- Unnecessary fields removed from graph context:
  - `draft.generatedSnapshot`
  - `draft.updatedAt`
  - full simulation input snapshot.
  - full workspace.
  - analysis source-material raw text.
- Token growth risk:
  - medium if edited draft content grows; acceptable because draft-level simulation should evaluate the current user-edited draft.
- Structured state dependencies:
  - `simulation_id`
  - `workspace_id`
  - `topic_id`
  - `positioning_snapshot`
  - compact `topic`
- Downstream consumers:
  - persona definitions persisted in `SimulationRun`.
  - parallel initial reactions.

### `SIMULATION_REACTION`

- Caller: audience simulation `parallel_initial_reactions`.
- Prompt: `PROMPT_SIMULATION_REACTION`.
- Input fields:
  - one `persona`
  - compact simulation target
- Unnecessary fields:
  - other personas.
  - other reactions.
  - debate responses.
  - synthesis.
  - full simulation input snapshot.
- Token growth risk:
  - medium when simulating from long edited draft content.
- Structured state dependencies:
  - `personas`
  - compact `topic`
- Downstream consumers:
  - persisted `reactionResults`.
  - debate response calls.
  - synthesis.

### `SIMULATION_DEBATE`

- Caller: audience simulation `parallel_debate_responses`.
- Prompt: `PROMPT_SIMULATION_DEBATE`.
- Input fields:
  - one `persona`
  - compact simulation target
  - `otherReactions`: initial reactions excluding the current persona.
- Unnecessary fields:
  - current persona's own first reaction.
  - synthesis.
  - full workspace.
  - full analysis source materials.
- Token growth risk:
  - medium; grows with persona count and reaction verbosity. Current product fixes persona count at four.
- Structured state dependencies:
  - `personas`
  - `initial_reactions`
  - compact `topic`
- Downstream consumers:
  - persisted `debateResults`.
  - synthesis.

### `SIMULATION_SYNTHESIS`

- Caller: audience simulation `synthesis`.
- Prompt: `PROMPT_SIMULATION_SYNTHESIS`.
- Input fields:
  - compact simulation target
  - `personas`
  - `reactions`
  - `debateResponses`
- Unnecessary fields:
  - raw source materials.
  - full analysis runs.
  - full topic library.
  - checkpoints.
- Token growth risk:
  - medium; bounded by fixed personas, reactions, and debate responses.
- Structured state dependencies:
  - `personas`
  - `initial_reactions`
  - `debate_responses`
- Downstream consumers:
  - persisted `SimulationRun.synthesis`.
  - simulation history UI.

## Legacy direct model-call endpoint

### `/api/model-calls`

- Caller: retained compatibility/debug API surface.
- Prompt: selected by `operation`.
- Input fields:
  - arbitrary `context` accepted by API model and then read by operation-specific prompt builder.
- Unnecessary fields:
  - any key not consumed by the selected `ModelOperation`.
- Token growth risk:
  - high if clients send large unused fields; the prompt builder ignores unused keys, but the request body still crosses the backend boundary.
- Structured state dependencies:
  - none. This endpoint bypasses persisted workflow state.
- Constraint:
  - product workflows should prefer workflow-specific services and should not use this endpoint as generic execution infrastructure.

## Refactor result

- Workflow POST endpoints now create persisted runs and enqueue backend worker execution.
- SSE endpoints are observation-only and rebuild progressive events from persisted run state.
- Account and trend graph state continue to hold source-material IDs and compact immutable snapshots instead of full workspace objects.
- Trend graph state stores uploaded CSV material ID and ranked top-50 compact rows, not the complete CSV file content.
- Audience simulation graph state now uses a compact simulation target. For draft simulations, immutable `SimulationRun.inputSnapshot` still stores both generated and editable draft snapshots, while graph/model context receives only the editable draft content needed for evaluation.

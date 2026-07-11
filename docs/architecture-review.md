# Architecture Review: Creator Workspace Migration

## Executive summary

The repository is moving in the right product direction, but the implementation has crossed an important boundary too early: it has built workflow infrastructure before completing the creator workspace itself.

The strongest parts are product-specific naming, fixed account/trend/simulation flows, server-side model credentials, persisted input/output snapshots, a topic library, and a workspace sidebar organized around creator work. These choices avoid becoming a chatbot, filesystem, agent builder, or workflow editor.

The main architectural problem is that the durable product chain is incomplete while execution machinery is already elaborate:

- There is no real draft/content asset model or API.
- Generated topics are not transactionally materialized as reusable product assets.
- Topic edits overwrite generated values, so generated output and user edits are not cleanly separated.
- Structure generation is still tied to `topics[0]`; the frontend's later “generate structure” action displays a demo fixture rather than creating a saved result.
- SSE is not merely observing work; opening the stream starts the work. Disconnecting cancels it.
- Graph checkpoints are written but never used to restore execution, and LangGraph is compiled without a persistent checkpointer.
- Model and prompt identity are not saved well enough to audit a historical result.

Recommendation: keep LangGraph as the internal orchestration layer because likely future work includes agent collaboration, self-reflection, iterative refinement, human feedback loops, and dynamic planning. Do not make it the product data layer. Ship a smaller creator workspace built around six core product records—workspace, materials, analysis runs, topics, drafts, and simulations—plus a run/material junction. Product tables own durable artifacts and immutable generation snapshots; LangGraph owns only bounded execution state and control flow. Add version tables and advanced agent behavior only after editing/revision usage proves they are needed.

This review is conservative: preserve LangGraph and the valuable product-specific work, replace the custom infrastructure that currently gives a false impression of durability, and finish the missing creator asset loop.

## 1. Product Alignment Review

### Overall verdict

**Partially aligned, with a good product shell and an execution-heavy core.**

The application is recognizably a creator workspace rather than a chatbot:

- Navigation is organized around source materials, analysis history, topic library, drafts, and audience simulations.
- The backend exposes fixed `account_diagnosis`, `trend_analysis`, and audience simulation operations.
- Source uploads are restricted to product-relevant CSV/TSV material; there is no directory browser or arbitrary path API.
- There is no user-configurable prompt, node, tool, graph, agent persona, or workflow editor.
- Analysis inputs and results are stored under a workspace and can be reopened.

It is also not a generic filesystem. `source_materials.type` is restricted to historical posts, comments, and trend CSV. That is a reasonable MVP compromise even though the table name is broad.

However, the workspace does not yet support the full product promise:

| Product capability | Current state | Verdict |
| --- | --- | --- |
| Store creator materials | Text blobs and trend CSV are saved | Present, but weakly structured |
| Analyze accounts and trends | Implemented as persisted runs | Present |
| Generate topics | Generated inside runs; saved only after a separate user action | Partial |
| Generate content structures | Automatically generated for the first topic; later button shows fixture data | Not product-ready |
| Simulate audience reactions | Persisted runs exist | Present, topic-only |
| Revisit and reuse prior results | Runs and manually saved topics can be reopened | Partial; drafts and revision history absent |

### Preserved behaviors

- The two product entry points—account diagnosis and trend analysis—remain distinct.
- Account diagnosis still derives profile/viral patterns and pain points before topics.
- Trend analysis still parses/ranks uploaded posts, derives patterns/needs, and produces trend-aware topics/title variants.
- Progressive user-visible stages remain meaningful and are rendered incrementally.
- Parallel first-stage analysis and partial-success behavior are preserved.
- Audience simulation preserves persona derivation, independent first reactions, a second response round, and synthesis.
- Demo/live modes share the same result renderers, and generated topics can be sent toward selection/simulation.

### Accidentally removed or weakened behaviors

- The original account simulation used comment context and the trend simulation used at least the trend keyword. The migrated simulation uses only positioning plus the topic snapshot, which weakens audience grounding.
- The original structure output was at least produced by the active workflow model call. The new post-analysis “generate structure” button substitutes fixture data and does not persist it.
- Generated topic batches do not automatically become durable reusable artifacts; title variants and `whyTrending` are lost or flattened when a topic is saved.
- Refresh no longer destroys persisted runs, but it still loses the selected workspace/page/run and can interrupt active execution because execution is tied to SSE.
- The intended explicit “select a topic, then generate structure” behavior from `workspace-model.md` has not been implemented; workflows still choose index zero.

### Progressive-stage decision

Keep product stages because they communicate evidence and partial failure. Do not require one LangGraph node per visible stage, and do not expose internal node names. A visible stage is a stable product contract; graph nodes may later split, merge, loop, or pause without changing the frontend contract.

The current design therefore risks behaving like a “workflow demo with storage” rather than a workspace where outputs become durable creator assets. The correction is not a larger framework. It is to complete the product relationships:

```text
materials -> analysis run -> saved topic -> saved draft/structure -> simulation
```

Each arrow should be an explicit database relationship and a visible user action. No step should depend on array position, copied text, or a frontend fixture.

### Guardrails to retain

- Keep workflows fixed in code. Do not expose nodes, edges, prompts, tools, or agent configuration.
- Keep the sidebar restricted to creator objects. Do not add Files, Documents, Agents, Workflows, Extensions, or a generic Settings surface.
- Treat JSON as an internal persistence format, not as a user-facing document model.
- Keep uploads in a controlled product flow. Never accept a server path from the frontend.
- Describe audience simulation as a content-testing feature, not a multi-agent platform.

## 2. Complexity Review

### Classification by major component

| Component | Classification | Review |
| --- | --- | --- |
| React workspace shell and fixed navigation | **Must implement now** | Correct product frame. It should be split into page/components for maintainability, but not generalized into a UI platform. |
| Workspace persistence | **Must implement now** | A workspace is the root creator/account boundary. One current positioning field is enough for Phase 1 if runs snapshot it. |
| Typed creator materials | **Must implement now** | Named historical-post, comment, and trend inputs are core. Raw text is acceptable initially; structured rows improve reuse later. |
| Controlled CSV upload and parsing | **Must implement now** | Needed for trend analysis. Existing size, extension, UTF-8, and server-generated filename checks are useful. |
| Immutable analysis and simulation runs | **Must implement now** | Required to revisit results and diagnose partial failures. Persist input, output, status, errors, model, and prompt version. |
| Topic library with explicit source run | **Must implement now** | Core reusable artifact. Generated snapshot and editable current copy must be separate. |
| Draft/structure record | **Must implement now** | This is a stated product goal and is currently missing. A structure can be the first draft; a generic document system is unnecessary. |
| Explicit artifact relationships | **Must implement now** | `run -> topic -> draft -> simulation` and `run -> materials` must use IDs/FKs. This is more important than graph checkpoints. |
| JSON for stage outputs and simulation details | **Must implement now** | Good fit when data is displayed as a unit and not independently queried. Add schema validation and JSON constraints. |
| Repository/service separation | **Useful but can wait** | The current separation is acceptable and testable, but it should not grow further. For a small local app, some repositories are thin SQL wrappers. |
| Polling for run status | **Must implement now** | Simpler and more reliable than the current execution-coupled SSE. |
| Durable run claim/lease and startup recovery | **Must implement now** | Minimum safeguard against duplicate execution and permanent `running` rows. Resume only at completed stage boundaries. |
| Per-stage progress stored as JSON | **Must implement now** | A fixed `stage_state_json` on the run is sufficient for the current small recipes. |
| SSE event transport | **Useful but can wait** | It improves perceived latency but should only observe a separately running job. Polling is adequate for MVP. |
| Positioning versions | **Useful but can wait** | Runs already contain positioning snapshots. Add versions when users need comparison/restore, not merely because positioning influences outputs. |
| Topic versions | **Useful but can wait** | Preserve the generated snapshot now; add full edit history when restore/compare becomes a real feature. |
| Draft versions | **Useful but can wait** | Phase 1 can retain immutable generated content plus one editable current copy. Add versions before collaborative or intensive revision workflows. |
| Structured historical post/comment row tables | **Useful but can wait** | Valuable for evidence links, filtering, and incremental imports, but not required to validate the main workflow. |
| Separate structure-generation run table | **Useful but can wait** | A draft can carry generation status and provenance in Phase 1. Split it once multiple regenerations/retries need independent history. |
| Analysis stage table | **Premature abstraction** | The recipes have four or five fixed stages and no cross-run stage queries. A table adds joins/state transitions without solving execution ownership. |
| LangGraph orchestration layer | **Must implement the boundary now; retain the runtime** | The current recipes are simple, but retaining the dependency and graph boundary avoids a later rewrite when collaboration, reflection, refinement, feedback, or planning is explored. The immediate work is ownership isolation and real resume semantics—not more graph features. It must remain an internal executor, not a product schema or API concept. |
| Custom graph checkpoint table | **Premature abstraction** | Current checkpoints duplicate run result data and are not read during restoration. Replace this with a real LangGraph checkpointer when resume is implemented; do not use custom checkpoint rows as product history. |
| Account/trend graph sophistication | **Useful but can wait** | Keep the existing graphs, but do not add generic nodes, routing DSLs, or configuration. Structure generation should leave analysis and become a separate product-triggered graph. |
| Audience simulation graph evolution | **Useful but can wait** | This graph is the most plausible future home for bounded reflection, extra debate rounds, and human review. Current linear behavior should stay explicit and bounded. |
| Generic `/api/model-calls` endpoint | **Premature abstraction and security risk** | It exposes provider spending through a generic operation/context interface and bypasses product authorization and provenance. |
| Generic workflow/event contracts in the frontend | **Premature abstraction** | Product pages should consume run status/results, not know graph node names or use an event stream to start work. |

### Specific complexity conclusions

**Versioning:** full versions for positioning, topics, and drafts are more than Phase 1 needs. Historical runs must be immutable now; editable artifacts can retain an immutable generated snapshot plus current user content. This preserves authorship separation without building three version subsystems.

**Execution history:** run history is essential, but execution internals are not the product. Keep one record per user-visible analysis/simulation. Save enough stage state for recovery and support explicit retry by creating a new run or retry attempt.

**Stage tables:** do not implement `analysis_run_stages` yet. Use a validated `stage_state_json` object whose keys are fixed by workflow type. A stage table becomes justified only when stages need independent querying, scheduling, retry policies, or cost reporting.

**JSON storage:** use JSON for snapshots and nested model output; use relational columns for identity, ownership, lifecycle, filtering, and relationships. Do not place `workspace_id`, status, target IDs, source run IDs, or timestamps only in JSON.

**Artifact relationships:** these are not premature. They are the workspace. Add and enforce them before adding workflow infrastructure.

## 3. Workspace and Data Model Review

### Current strengths

- Every main record has a stable ID and workspace ownership.
- Analysis runs copy the actual positioning and material content into `input_snapshot_json`; later edits do not erase what the model saw.
- Simulation runs snapshot the tested topic content.
- Workspace positioning already has lightweight versions.
- Source material and topic updates use optimistic concurrency through `expected_updated_at`.
- Trend uploads use server-generated storage keys rather than trusting the original filename.

### Boundary and relationship problems

1. **The main content entity is missing.** There is no `drafts` table, draft API, saved structure, or body content. “Content Drafts” is only a navigation placeholder.

2. **Analysis output and reusable topics are disconnected.** Topic generation writes JSON into `analysis_runs`; it does not atomically create topics. The user can save the same generated topic repeatedly, and there is no idempotency key such as `(source_run_id, source_item_id)`.

3. **Generated values and user edits are mixed.** `topics.title` and `topics.angle` are overwritten in place. The original generated candidate remains buried in run JSON, but there is no explicit generated snapshot or stable source item ID connecting the edited topic to the exact candidate.

4. **Important topic fields are lost or merged.** `whyTrending` is appended into `why_it_fits`, and title variants are not persisted on a saved topic. Product semantics should not be flattened for schema convenience.

5. **Current-topic state is duplicated.** Selection exists both as `topics.status='selected'` and `workspace_current_topics`. Transactions currently keep them aligned, but two sources of truth are unnecessary. Keep one workspace `current_topic_id`; topic lifecycle should remain candidate/active/archived.

6. **Historical lineage can be deleted.** Schema FKs use `ON DELETE CASCADE` from workspace and `ON DELETE SET NULL` from topics to analysis runs, which contradicts the design document's immutable-history and `RESTRICT` rules (`0002_analysis_topics.sql:3, 21, 26`).

7. **Run-to-material relationships exist only inside JSON.** The snapshot is necessary, but a small `analysis_run_materials` junction is also needed for navigation and integrity.

8. **Graph checkpoints have no FK.** `graph_checkpoints.analysis_run_id` is also used for simulation IDs, so the database cannot enforce ownership or prevent orphan rows (`0003_graph_checkpoints.sql:1-7`). This is a symptom of a generic execution table crossing product boundaries.

9. **JSON integrity is inconsistent.** Most run JSON columns lack `json_valid()` checks. Application serialization reduces risk but does not make the database self-consistent.

10. **Cross-workspace invariants are enforced only in services.** SQLite cannot guarantee that `current_positioning_version_id` or a current topic belongs to the same workspace. This is tolerable for Phase 1 only if all writes remain behind narrow services and tests cover the invariant.

### Are historical outputs reproducible?

They are partly **reconstructable**, not reproducible.

Good:

- Material content and positioning are copied into analysis input snapshots.
- Trend ranking inputs and the top-50 selection are copied into the run.
- Output JSON survives later source edits.

Missing:

- The actual prompt text or immutable prompt version/hash is not saved.
- Real provider model metadata and token usage are discarded by provider adapters; run metadata generally records only `{"engine":"langgraph"}`.
- Temperature and generation settings are not included in the run snapshot.
- No application/workflow code version is recorded.
- Automatic retries are not recorded as attempts.
- Model calls are nondeterministic, so exact regeneration should never be promised even with complete metadata.

The Phase 1 promise should be: **a historical result remains viewable with the exact input snapshot and generation provenance**. Do not promise bit-for-bit replay.

### Recommended Phase 1 entity set

Keep the schema deliberately small:

1. `creator_workspaces`
   - name, platform, current positioning text, current topic ID, timestamps.
2. `source_materials`
   - product type, name, text/parsed payload, controlled upload metadata, timestamps, archived flag.
3. `analysis_runs`
   - fixed workflow type, status, input snapshot, stage state, output, errors, model, prompt version/hash, generation settings, timestamps, retry-of ID.
4. `analysis_run_materials`
   - run ID, material ID, fixed role.
5. `topics`
   - source run and stable source item key; immutable generated snapshot; editable current title/angle; separate why-fit, why-trending, pain, title variants; status.
6. `drafts`
   - topic ID; generation status/provenance; immutable generated outline snapshot; editable current title/outline/body; timestamps.
7. `simulation_runs`
   - explicit topic ID or draft ID with XOR check; immutable target/context snapshots; stage state/results/errors/provenance/timestamps.

This is seven **product** tables, not the seventeen proposed in `workspace-model.md`. A supported LangGraph checkpointer may maintain separate execution-owned tables; those do not count as creator workspace entities and must not be queried as product history. This model supports the stated product while leaving structured materials and full version history for later.

## 4. Workflow Architecture Review

### Decision: retain LangGraph, narrow its authority

Keeping LangGraph is reasonable because the likely roadmap includes agent collaboration, self-reflection, iterative refinement, human feedback loops, and dynamic planning. Removing it now would trade a small amount of current simplicity for a probable orchestration rewrite later.

The boundary must be explicit:

```text
Product service / product database
  owns Workspace, Material, Run, Topic, Draft, Simulation
                    |
                    | run ID + immutable input snapshot/reference
                    v
LangGraph executor
  owns node order, routing, bounded loops, interrupts, temporary state
                    |
                    | validated node result
                    v
Domain service
  commits product result/status/artifact
```

LangGraph state and checkpoints are disposable execution implementation details. They must never be the only place where a user-visible result, edit, artifact relationship, or audit snapshot exists. The frontend must not receive graph thread IDs, node topology, checkpoint IDs, or routing commands.

### Account diagnosis graph

| Aspect | Current implementation |
| --- | --- |
| Graph | `START -> profile_analysis -> topic_generation -> structure_generation -> finalize -> END` |
| Parallel work | `profile_analysis` internally runs profile analysis and pain-point analysis with `asyncio.gather` |
| Node responsibilities | Profile/pain reasoning; topic reasoning; first-topic structure reasoning; run finalization |
| State | Run/workspace IDs, positioning snapshot, two material IDs, profile, pain points, topics, titles, structure, errors |
| Required inputs | Workspace positioning plus saved historical-post and comment materials |
| Outputs | Profile, pain points, topic batch/title variants, structure, final status |
| Persistence | Each successful stage updates `analysis_runs`; each graph node also writes a custom checkpoint |

Assessment:

- The fan-out/fan-in is deterministic and code-controlled; prompts do not decide routing.
- Nodes have mostly clear responsibilities, but `profile_analysis` hides two independently meaningful stages inside one graph node. This makes graph-level resume/progress coarser than product stage progress.
- Deterministic validation and persistence are mixed into orchestration execution objects. Keep validation near node boundaries, but commit through domain services.
- There are no loops. Future reflection must have explicit iteration and token/cost caps.
- `structure_generation` is semantically misplaced and uses `topics[0]`. Analysis should finish with reusable topic candidates. A separate topic-to-draft graph should start only after the user selects a stable topic ID.
- State contains small structured intermediate outputs, which is acceptable execution state. The material content is not copied into graph state, which is good; it is loaded from the immutable run snapshot.

### Trend analysis graph

| Aspect | Current implementation |
| --- | --- |
| Graph | `START` fans out to `trend_pattern_analysis` and `pain_point_analysis`; both join at `topic_generation`, then `structure_generation -> finalize -> END` |
| Parallel work | LangGraph fan-out executes trend pattern and pain-point analysis in parallel |
| Node responsibilities | Trend reasoning; inferred pain reasoning; topic/title reasoning; first-topic structure; finalization |
| State | Run/workspace IDs, positioning, trend material ID/keyword, ranked posts, trend result, pain points, topics, titles, structure, errors |
| Required inputs | Workspace positioning and one parsed trend CSV material |
| Outputs | Trend themes/patterns/windows, pain points, topics, title variants, structure, final status |
| Persistence | Stage outputs in `analysis_runs` plus a custom checkpoint after graph nodes |

Assessment:

- The graph expresses real parallelism and a clear join, so retaining it is reasonable even though the current recipe is simple.
- `ranked_posts` duplicates up to 50 normalized posts inside graph state/checkpoints. The immutable product run already owns this snapshot. Prefer a run/snapshot reference in graph state and load it only in the two consumer nodes.
- Deterministic CSV parsing, header normalization, numeric parsing, ranking, and top-50 selection correctly happen before LLM reasoning. They should remain outside the graph or in a deterministic preparation node that is never retried as a paid call.
- Pain points are inferred from post titles/snippets, not comments. The product label must distinguish “inferred audience needs” from observed comment pain points.
- Routing is code-controlled and there are no loops.
- Structure has the same `topics[0]` boundary problem as account diagnosis and should move into the separate draft graph.

### Audience simulation graph

| Aspect | Current implementation |
| --- | --- |
| Graph | `derive_personas -> parallel_initial_reactions -> parallel_debate_responses -> synthesis -> finalize` |
| Parallel work | One reaction call per persona in parallel; then one debate-response call per successfully reacting persona in parallel |
| Node responsibilities | Persona derivation; independent first reactions; informed second round; synthesis; finalization |
| State | Simulation/workspace/topic IDs, positioning, topic snapshot, personas, reactions, debate responses, synthesis, errors |
| Required inputs | Saved topic or manual topic plus positioning snapshot; no comment/trend/analysis context is included |
| Outputs | Personas, per-persona reactions, per-persona debate responses, synthesis, partial errors |
| Persistence | Simulation JSON columns are updated after each phase; custom graph checkpoint is also written |

Multi-agent assessment:

- These are independent persona-conditioned model calls, not durable autonomous agents. That is appropriate for the product and should be described as “audience perspectives,” not as a generic agent team.
- First reactions are genuinely parallel and receive only their own persona plus the topic. One persona does not influence another too early.
- The second round intentionally receives other personas' first reactions. It does not receive other debate outputs, so all second-round calls remain peers rather than a hidden sequence.
- Synthesis now receives topic, personas, reactions, and debate responses, which is the correct information flow.
- Persona output allows any number greater than zero, although the prompt asks for four. Persona IDs need uniqueness checks. Reaction/debate `personaId` is not verified against the persona whose call was made; malformed output can be attributed to the wrong perspective.
- Immediate two-attempt retry exists for reaction/debate only. It has no backoff, provider-aware policy, or attempt persistence.
- There are no loops. Future reflection/debate rounds must be bounded by `max_rounds`, total model calls, token budget, and a code-controlled stopping rule. The model must not be allowed to decide to continue indefinitely.

### State design and checkpoint boundary

Good graph state:

- Product run ID and graph execution/thread ID mapping
- Current node/round and bounded counters
- Small validated intermediate outputs needed by the next node
- Error/retry information that controls routing
- References to immutable product snapshots and artifacts

Bad graph state:

- Entire editable workspace or material library
- Raw uploads already stored in product data
- User edits or the canonical Topic/Draft record
- Long conversation history copied at every node
- The only copy of a generated artifact
- Product status used directly by the frontend

The existing custom `graph_checkpoints` table fails this boundary: it duplicates product results, is never read to restore execution, has no FK, and mixes analysis and simulation IDs in a column called `analysis_run_id`. Retain LangGraph, but replace the custom mechanism with a supported persistent LangGraph checkpointer when resume is implemented. Keep it in a separately owned execution schema/table namespace. Product run rows remain authoritative and map one-to-one to a graph thread/attempt.

## 5. Context Management Review

### Context inventory by model call

The application does not pass complete chat histories because it has no chatbot conversation model. That is a strength. Most intermediate results are structured dictionaries/lists rather than prose transcripts. The main risk is instead oversized raw creator material and duplicated snapshot/state payloads.

| Call/node | Context and source | Maximum expected size today | Format | Waste/quality risk |
| --- | --- | --- | --- | --- |
| Account profile | Current positioning from run snapshot + complete historical-post text material | 100,000 + 1,000,000 characters by API limits | Raw text | Critical. Far beyond a sensible prompt budget; later/important posts may be truncated by provider limits, and cost is unpredictable. |
| Account pain points | Complete saved comments material | Up to 1,000,000 characters | Raw text | Critical. No sampling, deduplication, count limit, privacy filtering, or summary hierarchy. |
| Account topics | Positioning + structured profile + structured pain points | Positioning up to 100,000 chars; outputs bounded indirectly by 1,800/1,000 generation-token limits | Mixed raw + JSON | Positioning is repeated. Structured intermediates are appropriate, but only the fields needed for topic decisions should be projected. |
| Account structure | Selected first topic + voice fingerprint + viral structure | Small, bounded by prior model output | Structured values serialized into text | Efficient, but bound to the wrong topic and missing a stable topic artifact ID. |
| Trend pattern | Positioning + keyword + formatted top-50 ranked posts | CSV file max 5 MiB; 50 rows, but title/tags have no per-field truncation and positioning can be 100,000 chars | Raw formatted text | Potentially large. Snippet is truncated, but title/tags and positioning can dominate. |
| Trend pain points | Keyword + the same top-50 formatted posts | Same as trend pattern | Raw formatted text | Duplicates the complete post context in a second paid call. This is justified only if parallel independent reasoning materially improves quality. |
| Trend topics | Positioning + structured trend result + structured inferred pain points | Positioning up to 100,000 chars plus bounded model outputs | Mixed raw + JSON | Mostly appropriate; project only needed trend fields and label inferred needs accurately. |
| Trend structure | First topic + viral pattern list | Small, bounded by prior output | Structured values serialized into text | Efficient but semantically misplaced in the analysis graph. |
| Simulation personas | Positioning + topic snapshot | Positioning up to 100,000 chars; topic/manual text up to 1,000 chars | Raw + JSON | The full positioning is likely excessive. It does not include comments, trend evidence, or chosen analysis context, so personas may be generic. |
| One initial reaction | One persona + topic | Small; bounded by persona/topic output limits | JSON | Good isolation. Validate persona identity and cap persona count. |
| One debate response | One persona + topic + every other successful first reaction | Grows with persona count; persona count has no schema maximum | JSON | Bounded in practice by persona generation tokens, but not structurally bounded. Add `max_personas`. |
| Simulation synthesis | Topic + all personas + all reactions + all debate responses | Grows with persona count and output verbosity | JSON | Correct information, but needs explicit count/size budgets before iterative rounds are added. |

### Context construction findings

1. **Raw material limits are storage limits, not prompt limits.** One megabyte may be acceptable for saved material but not for a single model request. Introduce separate `max_prompt_chars`/token budgets per operation.
2. **Select before summarize.** For historical posts and comments, deterministic parsing, deduplication, recency/performance sampling, and stable record IDs should happen before summarization. Do not send the whole workspace.
3. **Snapshot once, project per node.** The product run should preserve the complete normalized input snapshot for audit. Each node should receive only a typed projection of that snapshot. LangGraph state can hold the projection or a reference, not a second full copy.
4. **Structured intermediates are good.** Profile, pain, trend, topic, reaction, and debate results are validated with Pydantic before downstream use. Continue this pattern and validate semantic invariants, not just shapes.
5. **There is no unbounded conversation history today.** Do not introduce one for refinement. Store each refinement round as a compact structured critique + revision, with a bounded round count, rather than appending full prompts/responses indefinitely.
6. **Summaries need provenance.** A material summary should retain selected source IDs/excerpts so topic rationales can link back to evidence.
7. **Prompt injection currently affects reasoning, not tools.** CSV/text is untrusted content embedded directly in prompts. Because nodes cannot execute arbitrary tools, blast radius is limited, but injected instructions can corrupt JSON/analysis quality. Delimit source content, explicitly label it untrusted, use structured output, and never let material text control graph routing or model permissions.
8. **Model output budgets are defined, input budgets are not.** `MAX_TOKENS` caps generation only. Add preflight token estimation, truncation/sampling metadata, and user-visible disclosure when only a subset was analyzed.

### Recommended context contract

Each node should declare and test:

```text
input schema
source fields / source artifact IDs
selection and truncation rule
maximum records and estimated tokens
prompt version/hash
output schema
downstream consumers
```

Context tests should assert both inclusion and exclusion—for example, account pain analysis receives selected comments but not trend CSV; one persona reaction receives no other persona reaction; synthesis receives both reaction and debate results.

## 6. Workspace Product Experience Review

### Good workspace behavior already present

- A workspace represents a creator/account context.
- Inputs are limited to account positioning, historical posts, comments, and trend data.
- Analysis history is saved and reopenable.
- Topics have a dedicated library and selected/current concept.
- Audience simulations have history.
- Uploaded files are not exposed as a directory tree.

### Gaps that keep it from being a complete creator workspace

- Source materials are presented mostly as the latest textarea value, not as a reusable library of named material sets.
- The UI always selects the latest material automatically; users cannot clearly choose which saved set a new analysis should use.
- Drafts are absent.
- Generated title variants and trend rationale are not reusable after saving a topic.
- The history page displays raw input JSON rather than a creator-oriented evidence summary.
- Current workspace/page/run is not encoded in the URL; refresh selects the first workspace and loses navigation context.
- The main `App.tsx` holds nearly all server state, form state, execution state, routing, and rendering in one component. That recreates the single-file prototype's state-management risk inside React.

### Workspace boundary decision

Retain:

- Creator profile/positioning
- Named material sets
- Analysis history
- Topic library
- Drafts/structures
- Audience simulation history

Reject:

- Arbitrary documents or folders
- User-created entity types
- Agent/persona configuration
- Prompt management UI
- Workflow/node editor
- Generic model-call console

## 7. Agent Reliability Review

### Failure behavior matrix

| Failure | Current behavior | Risk | Required behavior |
| --- | --- | --- | --- |
| Model timeout | HTTP client times out after 90 seconds; error becomes a failed stage | User gets a generic message; account/trend do not retry | Stable timeout code, provider-aware retry policy, persisted attempt, actionable UI |
| Provider 429/5xx | Converted to `ValidationError("Model call failed (status)")` | Incorrectly appears as client validation/422; no retry-after handling | Preserve safe provider category, retry 429/selected 5xx with bounded backoff |
| Malformed JSON | JSON parser raises a safe validation error | Stage fails; raw response is unavailable for diagnosis | Keep safe user error; securely log response hash/excerpt and model metadata |
| Invalid structured output | Pydantic failure becomes “Model response failed structured validation” | Good safe message, but no repair retry for account/trend | One bounded structured-repair retry where cost is acceptable; persist attempt |
| Profile/trend parallel branch fails | Other branch can continue; final run becomes partial | Good product degradation | Preserve missing-context flags so downstream/UI states exactly what was absent |
| One persona reaction/debate fails | Other personas continue; simulation becomes partial | Good partial behavior | Validate identity, persist per-persona attempt/status, allow targeted retry later |
| Node exception | Stored as stage error; unexpected `str(error)` may be shown | Possible information leakage and inconsistent error taxonomy | Stable public error, private structured log with run/node/attempt IDs |
| Browser refresh/page close | EventSource closes and server task is cancelled | Work can stop mid-run; run can remain `running` | Execution must be independent of client connection |
| Reopen/retry | Opening events on a nonterminal run starts execution again | Duplicate paid calls/races | Atomic graph execution claim; explicit retry creates an attempt/new run |
| Workspace switch | Local UI resets; existing EventSource generally remains until function settles | Results/errors can update a now-unrelated screen | Bind UI updates to run/workspace ID and close subscriptions without cancelling work |
| Backend restart | No startup recovery; custom checkpoints are not restored | Stale `running` work and uncertain paid calls | Startup reconciliation plus real graph checkpoint restore at safe boundaries |

### Retry policy

- Do not retry every exception. Validation failures, permission errors, and deterministic bad inputs need user correction.
- Retry transport failures, 429, and selected 5xx statuses with exponential backoff and jitter, honoring `Retry-After`.
- Persist `attempt_number`, provider request ID when available, started/completed timestamps, error category, model, and usage.
- A retry must not mutate a completed immutable result. For a full user retry, create a new run/attempt linked by `retry_of_run_id`; for safe node retry within the same active graph, checkpoint attempt state.
- Paid calls need idempotency/claim protection even if the provider itself offers no idempotency key.
- Reflection/refinement loops must be bounded in code. A prompt may recommend another round, but code decides using `max_rounds`, remaining budget, and allowed transitions.

### User-visible reliability

The UI needs distinct states for queued, running, partially completed, interrupted, retryable failure, non-retryable input failure, completed, and cancelled. It should never leave a spinner based only on an open connection. Partial results remain viewable and reusable, with a warning that names missing evidence. Unsaved editor text should be protected independently from graph execution.

## 8. Persistence and Resume Review

### Crash scenario: long audience simulation

Suppose personas and two reactions have completed and the backend crashes during the remaining reactions.

Current result after restart:

1. `simulation_runs` identifies the run as `running` and contains personas plus whichever reaction batch was last committed.
2. The custom checkpoint may contain similar data, but no startup code or graph code reads it.
3. There is no durable worker/lease to classify the execution as abandoned.
4. Opening the SSE endpoint reconstructs state from the product row and may run missing phases, but there is no atomic claim and no guarantee that an earlier provider request was not already charged/completed.
5. Multiple reconnecting clients can start the same work.

Therefore the system can identify some unfinished data but cannot reliably restore, continue, explain interruption, or avoid duplicate work.

### Target resume architecture with LangGraph retained

1. Product API transaction creates the immutable input snapshot and `SimulationRun(status=queued)`.
2. Executor atomically claims the product run and creates/maps a LangGraph `thread_id` and execution attempt.
3. The graph uses a supported durable checkpointer. Checkpoints contain only execution state, node progress, small intermediates/references, bounded counters, and pending interrupts.
4. After each validated node, a domain service commits user-visible product progress/results. Product commits and graph checkpoints need a documented ordering and reconciliation rule; they cannot be assumed to be one distributed transaction.
5. Startup scans queued and stale-running product runs, checks graph execution/checkpoint state, and either resumes from the last safe boundary or marks the in-flight node `execution_interrupted`.
6. A model request that was in flight at crash time is ambiguous. Do not silently repeat it. Mark the node retryable and require an explicit/system policy decision; record the new attempt.
7. `GET`/polling or passive SSE observes product run state. It never starts or owns the graph.

### Two stores, two responsibilities

| Product persistence | LangGraph persistence |
| --- | --- |
| User-visible run status and timestamps | Current/next node and routing state |
| Immutable input/target snapshots | Temporary validated intermediates or references |
| Analysis/simulation result history | Bounded loop counters and pending interrupt |
| Topic, draft, and artifact relationships | Retry/control metadata needed to resume execution |
| Model/prompt provenance and user-visible errors | Internal checkpoint metadata |
| Long-term source of truth | Replaceable orchestration implementation detail |

If graph checkpoints are deleted after a completed run, the product must still be fully viewable. If product rows are missing, checkpoints must not be promoted into creator artifacts automatically.

### Consistency requirements

- Enforce one active graph attempt per product run with an atomic database claim/lease.
- Map `product_run_id`, `graph_thread_id`, and `attempt_id` explicitly; do not overload `analysis_run_id` with simulation IDs.
- Persist per-stage/per-persona completion so resume does not repeat completed paid calls.
- Define reconciliation for “checkpoint saved, product commit failed” and “product commit saved, checkpoint failed.” Node writes should be idempotent by `(run_id, node_key, logical_item_id, attempt)`.
- Keep completed product runs immutable even if graph execution metadata is pruned.
- Encode workspace/run/page in the URL so browser refresh restores the correct product view independently from graph resume.

## 9. MVP Recommendation

### Phase 1: smallest implementation that can ship

#### Database

Use the seven-table set described above:

- `creator_workspaces`
- `source_materials`
- `analysis_runs`
- `analysis_run_materials`
- `topics`
- `drafts`
- `simulation_runs`

Key rules:

- Completed run snapshots and generated snapshots are immutable.
- User-editable topic/draft fields are separate from generated snapshots.
- All product transitions use explicit IDs.
- `RESTRICT` deletion for referenced history; archive user-facing assets.
- Add `json_valid()` checks and application-level Pydantic validation on read/write.
- Record model ID, prompt version/hash, settings, and app workflow version for every generated result.

#### APIs

Minimum product APIs:

```text
GET/POST          /api/workspaces
GET/PATCH         /api/workspaces/:workspaceId

GET/POST          /api/workspaces/:workspaceId/materials
GET/PATCH         /api/materials/:materialId
POST              /api/workspaces/:workspaceId/trend-materials

GET/POST          /api/workspaces/:workspaceId/analysis-runs
GET               /api/analysis-runs/:runId
POST              /api/analysis-runs/:runId/retry

GET/POST          /api/workspaces/:workspaceId/topics
GET/PATCH         /api/topics/:topicId
POST              /api/topics/:topicId/select
POST              /api/topics/:topicId/archive

GET/POST          /api/workspaces/:workspaceId/drafts
GET/PATCH         /api/drafts/:draftId
POST              /api/topics/:topicId/generate-draft

GET/POST          /api/workspaces/:workspaceId/simulations
GET               /api/simulations/:simulationId
POST              /api/simulations/:simulationId/retry
```

Do not expose run status/stage mutation APIs or `/api/model-calls` to the browser. Only the worker may advance execution state.

#### Frontend pages

Four pages are enough:

1. **Workspace / Materials** — positioning and named saved material sets; upload/preview trend CSV.
2. **Analyze** — fixed Account Diagnosis and Trend Analysis forms, run status, result detail, history.
3. **Topics & Drafts** — topic library, explicit selection, title variants, generate/edit saved structure or body.
4. **Audience Test** — choose a saved topic or draft, start simulation, revisit results.

Use URL routes for workspace and selected record. Split `App.tsx` by these product pages and use a small query/cache layer or page-local request state. Do not introduce a global workflow state machine.

#### Execution

- Retain the three LangGraph workflows as internal, typed, fixed product recipes; do not expose configuration or add generic graph abstractions.
- Remove structure generation from the two analysis graphs and add a small explicit topic-to-draft graph/service operation.
- Replace the custom write-only checkpoint table with a supported LangGraph persistent checkpointer when resume is implemented. Until then, do not claim checkpoint-level resume.
- Create work on `POST`; execute independently through one in-process worker for the local MVP.
- Claim runs atomically and recover queued/stale rows at startup.
- Poll every 1–2 seconds while active, backing off when idle.
- Store user-visible fixed stage progress in product run data; store internal orchestration progress only in LangGraph checkpoints.
- Keep demo fixtures, but persist them through the same run and artifact-writing path and label them as fixtures.

### Phase 2: add after usage validates the need

- Positioning, topic, and draft version tables with compare/restore UI.
- Structured historical posts, comments, and trend rows with evidence backlinks.
- Multiple named material sets and explicit analysis input selection.
- Regenerate/compare draft alternatives.
- Simulation against an exact draft revision and suggestion acceptance tracking.
- Passive SSE/websocket updates if polling is measurably inadequate.
- Search, filtering, tags, archive management, and export.
- Provider cost/usage reporting and per-stage retry records.
- Authentication and tenant isolation before any non-local/shared deployment.

### Phase 3: advanced agent infrastructure

Only introduce these when product requirements demand them:

- A durable external queue/worker fleet.
- Extend the retained LangGraph layer with bounded conditional loops, human interrupts, dynamic planning, and reflection only where a product use case justifies them.
- Durable event log and replay.
- Provider routing, tool calls, evaluation gates, and fallback policies.
- Multi-step research agents with citations.
- Team collaboration, permissions, and audit logs.

Even in Phase 3, do not expose a generic agent or workflow builder unless the product goal explicitly changes.

## 10. Code Review

### High-priority findings

#### P0 — “Generate content structure” returns fabricated UI data

`frontend/src/App.tsx:1085-1098` saves/selects a topic and then marks the structure stage completed using `SAMPLE_RESULT` or `SAMPLE_TREND_RESULT`. It performs no model call and persists no draft. In live mode this can present demo content as a generated result.

Recommendation: remove this behavior from any shippable build. Implement a real topic-ID-based draft generation endpoint, or disable the action until it exists.

#### P0 — execution is owned by an SSE connection

Opening the event endpoint starts a graph task, and disconnect cleanup cancels it. This makes refresh, navigation, proxy timeout, mobile network changes, and multiple tabs correctness hazards. Duplicate stream connections can cause duplicate paid calls.

Recommendation: separate job creation/execution from observation and add atomic run claiming.

#### P0 — client-accessible mutation and model-call endpoints break history integrity

`PATCH /analysis-runs/:id`, `PUT /analysis-runs/:id/stages/:key`, and `POST /model-calls` are public application routes (`api.py:157-170` and the final model-call route). A browser or script can forge completed results, errors, or metadata and can consume the server's Anthropic key through arbitrary supported operations.

Recommendation: remove these routes from the public API. Make state mutation and provider calls internal service methods.

#### P1 — checkpoints do not provide checkpointing

The repository saves checkpoint JSON, but execution reconstructs state from `analysis_runs`/`simulation_runs`; it never loads the checkpoint. LangGraph itself has no persistent checkpointer. The table adds storage and migration cost without the claimed resume semantics.

Recommendation: retain LangGraph but replace the custom write-only table with a supported persistent LangGraph checkpointer. Keep checkpoints execution-only; product runs and artifacts remain the durable business authority.

#### P1 — generated structure uses the first topic, not a selected topic

Both analysis workflows automatically call structure generation with `topics[0]`. This contradicts the workspace design's explicit topic selection and wastes a model call for users who choose another topic.

Recommendation: end analysis after topic generation. Generate a draft only from a saved, explicit `topic_id`.

#### P1 — saved topic relationship is inferred from text

Audience simulation treats a topic as saved when `simulationTopic.includes(selectedTopic.title)` (`App.tsx:840-845`). Substring matching can bind a manually edited text to the wrong topic or lose the relationship after a title edit.

Recommendation: keep `selectedTopicId` and manual text as mutually exclusive typed form state.

#### P1 — deletion policy can erase or detach history

Workspace cascades delete analyses/topics/simulations, while deleting an analysis sets a topic's source to null. This conflicts with immutable execution history and makes provenance disappear.

Recommendation: archive workspaces/assets and use `RESTRICT` for referenced historical records.

## 11. Security Review

Positive controls:

- Provider API key is server-side.
- Upload size and extension are limited.
- Original filenames are sanitized and not used as storage filenames.
- Files are parsed as text and are not executed.
- React rendering avoids the original prototype's direct `innerHTML` XSS class.

Issues:

1. **The legacy `index.html` remains dangerous if deployed.** It holds the Anthropic key in the browser, enables `anthropic-dangerous-direct-browser-access`, tries to fetch `./key`, and inserts model/provider errors through `innerHTML` (`index.html:220, 865, 887, 1159-1162`). Keeping it as reference is reasonable, but it must be excluded from production assets and clearly marked non-deployable.
2. **No authentication or authorization.** Acceptable only if the server is explicitly local and bound to loopback. Any shared deployment exposes all creator materials and model spending.
3. **Generic model-call endpoint.** This is the most immediate spend-abuse surface.
4. **No rate limit, quota, or per-workspace execution lock.** Repeated live runs and persona calls can create unbounded provider cost.
5. **Client can mutate run history.** Stored results cannot be trusted as system-generated.
6. **Sensitive data disclosure is not surfaced.** Comments, account positioning, and trend content are sent to Anthropic in live mode. The UI needs clear disclosure and retention/privacy guidance.
7. **Upload ordering and containment should be hardened.** `SourceMaterialService.create_csv` writes the file before validating that the workspace exists (`source_materials.py:89-100`) and does not resolve/assert the final path is beneath the upload root before writing. Validate ownership first, generate path components internally, then assert containment and atomically persist metadata/file.
8. **Raw internal errors may be persisted and shown.** Workflow `error_message()` returns `str(error)` for unexpected exceptions. Map unknown failures to a stable public error and log details server-side with a request/run ID.
9. **Prompt inputs are very large.** Limits of up to 1 MB/100k characters can cause cost spikes or provider rejection. Add product-specific record/count/token limits before the model call.
10. **No production security posture is documented.** There is no explicit bind-address restriction, auth requirement, data directory permission guidance, secret rotation guidance, or backup policy.

## 12. Frontend / Backend Boundary Review

The desired contract is:

| Frontend may know | Frontend must not know |
| --- | --- |
| Workspace, material, analysis, topic, draft, simulation IDs | LangGraph thread/checkpoint IDs |
| Product workflow type | Graph class, node names, or edge topology |
| Queued/running/partial/completed/failed/interrupted | Which internal node is scheduled next |
| User-visible stages such as “痛点分析” | Internal routing or retry commands |
| Product results, provenance, and safe errors | Provider secrets, raw exceptions, execution leases |

Current SSE payloads expose `stageKey` and graph-like event types, and opening the stream starts execution. A product stage key can remain a stable presentation contract, but it should be produced from product run state—not from graph topology. Renaming or splitting a graph node must not require a frontend release.

Recommended boundary:

- `POST` creates a product action and returns its product run ID.
- The backend maps that run to a LangGraph execution internally.
- `GET` returns a product DTO with user-visible progress/results.
- Optional SSE emits product DTO changes and is passive.
- Only internal worker/domain services may mutate run state or call the model.
- The frontend never sends node transitions, checkpoint data, thread IDs, or arbitrary model operations.

### Architecture and state-management issues

- `App.tsx` is approximately 1,700 lines and owns navigation, five categories of server records, forms, optimistic concurrency, workflow events, rendering, and modal state. Split by product page and extract reusable result views.
- The frontend uses one global `running` flag for analysis and simulation. This prevents some local duplication but cannot represent server-side runs across refresh or multiple workspaces.
- Workspace/page/run selection is not in the URL. Refresh does not return the user to the selected workspace or historical result.
- `EventSource.onerror` immediately fails and closes; native reconnection and `Last-Event-ID` are not used. Since events are not durable, robust reconnect is impossible anyway.
- Analysis stage state is represented as result/error dictionaries without authoritative per-stage status. `AnalysisStageUpdate.status` is accepted but the repository does not persist stage status; it only ensures the run becomes `running`.
- Run finalization declares success whenever there are no recorded errors, even if required stages were skipped because upstream data was empty. Completion should validate the recipe's required result contract.
- Simulation persona reactions retry immediately with no backoff and no persisted attempt record.
- Real model provider adapters discard response metadata, including actual model and usage.
- `README.md` says diagnosis, topics, audience simulation, and LangGraph are intentionally not implemented, although all are present. This can mislead maintainers and reviewers about migration state.
- SQLite enables foreign keys and busy timeout but not the WAL mode promised by the design document.
- Several JSON columns and status relationships rely solely on application correctness; schema checks are inconsistent.
- Demo providers are long-lived mutable singleton instances with accumulated `calls`; currently harmless for output, but test instrumentation should not be production service state.

## 13. Migration Risks

1. **Schema/design divergence:** `workspace-model.md` specifies roughly seventeen entities and immutable/restrict rules; migrations implement a much smaller but behaviorally different schema. Continuing both paths will create expensive data migrations.
2. **False durability:** tests named “restart resumes” instantiate another provider but remain in the same process/database and resume from run results, not graph checkpoints or a restarted worker. This can overstate operational readiness.
3. **Original prototype parity versus corrected product behavior:** automatic structure for topic zero and demo fixtures are legacy behaviors that should be intentionally removed, not preserved accidentally.
4. **Uncommitted repository baseline:** the entire repository is currently untracked in Git. Before real migrations, establish a reviewed baseline and backup strategy so schema changes can be audited and rolled back.
5. **SQLite concurrency:** multiple SSE executions update whole JSON blobs using read-modify-write transactions. Without run ownership, later writes can overwrite sibling updates.
6. **Data portability:** uploaded CSV files and SQLite rows must be backed up/restored together; no consistency or orphan cleanup procedure is documented.

## 14. Testing Review

Current automated status at review time:

- Backend: 23 tests passed; Ruff passed.
- Frontend: 6 tests passed; ESLint passed; production TypeScript/Vite build passed.
- One LangGraph dependency deprecation warning is present.

The suite provides useful coverage for CRUD, optimistic concurrency, CSV upload, happy-path graph output, structured model validation, partial failures, and resume from persisted stage results.

### Workflow tests

Covered: successful execution of all three graphs, account/trend parallel partial failure, simulation per-persona partial failure, malformed structured output, and bounded retry for simulation calls.

Missing high-value cases:

- Explicit graph branching/routing assertions rather than only final outputs.
- Bounded-loop and human-interrupt tests before those capabilities are introduced.
- Required-stage completion validation when no error is recorded but a stage is skipped.
- Persona ID uniqueness and reaction/debate identity matching.
- Provider timeout, 429, 5xx, retry/backoff, and exhausted-attempt behavior.
- Verification that deterministic selection/ranking is not repeated during node retry.

### Persistence tests

The current “restart resumes” tests recreate a provider but do not stop/restart the application process or restore a LangGraph checkpoint. Add:

- Real application restart with the same SQLite/checkpoint stores.
- Crash after graph checkpoint but before product commit, and the inverse ordering.
- Recovery of queued/stale-running work.
- One active claim when two workers/clients target the same run.
- Ambiguous in-flight model call marked interrupted instead of silently duplicated.
- Completed product history remains viewable after graph checkpoints are pruned.
- Save/reload of source, topic, draft, simulation, and all explicit relationships.

### Context tests

- Assert exact fields included in every model operation.
- Assert unrelated workspace materials and other persona reactions are excluded.
- Enforce record/character/token budgets and persist truncation/selection metadata.
- Verify top-50 selection, snippet truncation, ordering, and source IDs.
- Verify structured summaries preserve evidence references.
- Test prompt-injection-like CSV/comment strings cannot affect routing or invoke extra permissions.

### Integration journey tests

The highest-value missing integration test is the complete product journey:

```text
create workspace
-> save/upload materials
-> run account or trend graph
-> reopen analysis after refresh
-> save one generated topic exactly once
-> select/edit topic without losing generated snapshot
-> generate and persist a draft from that topic ID
-> run simulation against that exact topic/draft
-> restart backend
-> revisit every artifact and relationship
```

Also test duplicate clicks, workspace switching during execution, browser refresh, archive behavior preserving history, cross-workspace isolation, unsafe uploads, and authentication/rate limits before shared deployment.

## 15. Prioritized Action Plan

Difficulty: **S** is localized, **M** crosses a few modules/schema contracts, and **L** changes execution/persistence architecture.

| Priority | Problem | Why it matters | Affected files/modules | Recommended fix | Difficulty |
| --- | --- | --- | --- | --- | --- |
| P0 | Structure button fabricates a completed result from demo fixtures | Broken workflow semantics; live users can mistake sample output for their result | `frontend/src/App.tsx`, draft API absent | Disable until real, or implement explicit topic-ID-to-draft generation and persistence | M |
| P0 | SSE connection starts and owns graph execution | Refresh/close can cancel work; reconnect/multiple tabs can duplicate paid calls | `backend/app/api.py`, all workflow services, `frontend/src/App.tsx` | Decouple execution from observation; atomically claim runs; use polling/passive SSE | L |
| P0 | Public run/stage mutation and generic model-call APIs | Clients can forge history and spend the server key outside product actions | `backend/app/api.py`, `frontend/src/api.ts`, model-call service boundary | Remove public routes; permit only internal executor/domain service calls | M |
| P0 | Legacy `index.html` can expose browser keys and unsafe HTML if deployed | Direct secret/XSS risk survives migration | `index.html`, deployment/build docs | Exclude from production assets; label reference-only; never serve `./key` | S |
| P1 | LangGraph checkpoint is custom, duplicated, and never restored | Resume claims are false; backend restart loses execution control | `graph_checkpoints` migration/repository, all workflows | Keep LangGraph; adopt supported durable checkpointer with execution-only state and explicit product-run mapping | L |
| P1 | LangGraph can drift into the product data layer | Future reflection/planning could make checkpoints canonical and couple UI/schema to graph | workflows, services, API DTOs, migrations | Document/enforce ownership boundary; domain services alone persist artifacts; frontend sees product DTOs | M |
| P1 | No durable run claim/attempt/reconciliation | Duplicate requests and restarts race or repeat model calls | run repositories/services, worker startup | Add lease/attempt identity, idempotent node commits, startup recovery and ambiguity handling | L |
| P1 | Draft/content artifact is missing | Product chain stops before reusable content creation | migrations, models, repositories, services, API, frontend | Add minimal `drafts`; move structure out of analysis into topic-to-draft action/graph | L |
| P1 | Generated topic and user edit are mixed | Editing loses explicit authorship/provenance; duplicate saves are possible | `topics` schema/service, frontend topic actions | Store immutable generated snapshot/source item key plus editable current fields; add idempotency | M |
| P1 | Artifact relationships are incomplete or inferred from text | Reuse/history can point to the wrong topic/draft | run/material schema, simulation creation, `App.tsx` | Add FKs/junction; use typed mutually exclusive IDs, never substring matching | M |
| P1 | Input context can reach 100k/1M characters | Token waste, truncation, latency, high cost, degraded reasoning | models, analysis snapshot builder, model providers/prompts | Separate storage limits from per-node token budgets; select/dedupe/summarize with audit metadata | M |
| P1 | Provider failure/retry metadata is weak | 429/timeout appear as validation errors; recovery and cost audit are poor | `model_calls.py`, workflows, run schemas | Typed errors, bounded provider-aware backoff, persisted attempts/request IDs/usage | M |
| P1 | Persona identity/count invariants are missing | Responses can be misattributed and context can grow unpredictably | `audience_simulation.py` | Enforce exact/max count, unique IDs, and returned ID equality per call | S |
| P1 | Historical deletion rules can detach lineage | Revisited topics/results lose provenance | migrations for workspaces/runs/topics/simulations | Prefer archive and `RESTRICT`; test preservation invariants | M |
| P1 | Frontend exposes execution details and does not restore routes | Graph refactors leak into UI; refresh loses navigation context | `frontend/src/App.tsx`, `api.ts`, backend DTOs | Product progress DTOs, passive updates, URL routes by workspace/artifact/run | M |
| P1 | Full process resume and context boundaries are untested | Existing passing tests overstate readiness | backend workflow/integration tests | Add crash/restart, dual claimant, checkpoint/product reconciliation, inclusion/exclusion tests | L |
| P2 | Full positioning/topic/draft version tables | Useful for compare/restore, not needed to establish the first durable chain | future migrations/services/UI | Add after actual revision-history demand; snapshots suffice initially | L |
| P2 | Structured post/comment entities and evidence backlinks | Improves analysis quality/search but expands ingestion scope | materials schema/import/UI | Introduce incrementally after raw material workflow ships | L |
| P2 | `App.tsx` is monolithic | Slows safe UI changes but is not the primary correctness blocker | `frontend/src/App.tsx` | Split by four product pages and reusable result components | M |
| P2 | Advanced collaboration/reflection/planning | Strategic capability, but premature without reliability/budgets | retained LangGraph layer | Add bounded, product-specific nodes/loops after P0/P1 execution boundaries are sound | L |

### Recommended decision sequence

1. Keep LangGraph and write down its execution-only ownership contract.
2. Fix fabricated structure behavior and public execution mutation surfaces.
3. Decouple graph execution from SSE; add claim/attempt/restart semantics.
4. Replace custom checkpoints with a real LangGraph checkpointer mapped to product runs.
5. Complete `material -> analysis -> topic -> draft -> simulation` with explicit IDs and immutable snapshots.
6. Add context budgets and the crash/context/integration tests that enforce the architecture.
7. Only then explore bounded collaboration, reflection, refinement, feedback, and planning.

This preserves the strategic orchestration investment without allowing LangGraph to become the creator workspace's product model.

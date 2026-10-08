# Agent Runtime and Context Architecture

## Decision

This product is a creator workspace with several specialized AI steps, not a general-purpose agent platform. Keep the current FastAPI, React, SQLite, explicit product flows, and user-confirmed editing model.

Continue using LangGraph as the orchestration layer for the existing account diagnosis, trend analysis, video quality, and audience simulation flows. Use it as the execution engine for the new content-collaboration parent graph as well. Do not add PydanticAI as a second runtime now. The application already uses Pydantic models to validate inputs and structured model outputs; adding a second agent loop would duplicate provider calls, retries, cost records, and confirmation boundaries without solving a current product problem.

Use ordinary application code to choose the workflow. A user clicking “run audience simulation” should not first ask an LLM which agent to invoke. Inside an explicitly started content-collaboration session, a bounded specialist may address another specialist through the parent graph. The dispatcher validates and routes that message; it never uses an LLM to decide routing on its own.

This follows the distinction in the official framework documentation: LangGraph is a low-level runtime for deterministic and model-driven steps, persistence, and human-in-the-loop control, while PydanticAI supports programmatic hand-offs and structured agent outputs. The product does not currently need autonomous delegation or a general planner. Sources: [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview), [PydanticAI multi-agent applications](https://pydantic.dev/docs/ai/guides/multi-agent-applications/), [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

## What remains application-owned

The database remains the authoritative record for workspaces, selected assets, content versions, runs, simulation snapshots, user confirmations, and externally visible progress. LangGraph state is an execution aid, not the source of truth for creator content.

Each model call receives a purpose-built context object rather than a global conversation dump. Context should identify:

- the task and allowed operation;
- the selected asset ID and its frozen version;
- source evidence that supports factual claims;
- the smallest relevant upstream structured result;
- only the recent messages needed for the current turn; and
- explicit omissions or uncertainty when source material is incomplete.

The product stores the resulting context snapshot with the run or message. Later edits, framework upgrades, and model changes must not reinterpret an old request against live workspace state.

## Runtime boundaries

| Layer | Responsibility | Technology |
| --- | --- | --- |
| Product API and run worker | Create work, enforce idempotency, recover unfinished work, emit progress | FastAPI, asyncio, SQLite |
| Flow orchestration | Fixed sequence, bounded parallelism, pause and resume points | LangGraph plus application workflow services |
| Context Builder | Resolve selected product objects into a frozen, auditable input | Application code and Pydantic contracts |
| Model adapter | Provider request, output parsing, structured validation, usage record | Existing `ModelCallService` |
| Product safeguards | Evidence gates, selected-reader checks, user confirmation, version conflict handling | Application code |

The recent `build_agent_conversation_context` boundary is the first direct implementation of this design. It makes the selected topic, the version timestamp, any source analysis evidence, and the workspace-scoped selected asset explicit before the creator assistant is called. The conversation service no longer assembles those pieces ad hoc.

`services/content_collaboration.py` contains the serial LangGraph kernel, and
`services/content_collaboration_sessions.py` connects it to durable product
records. Its Pydantic message and specialist-output contracts, fixed recipient
allowlist, deterministic dispatch, bounded turn count, and creator wait state
are covered by local tests. Qwen is the default specialist provider; an
explicit `mode=demo` message uses the local deterministic provider instead.
The Qwen-only
`RealContentCollaborationProvider`: it receives a projection of the frozen
session snapshot, validates a role-specific structured handoff, and stores the
safe model receipt alongside the resulting message. It intentionally has
neither SSE nor a creator-canvas control yet.

## 2026-10-06 implementation update

The refactor now has three shared, deliberately small product contracts. They reduce repeated runtime mechanics without replacing the product's workflow-specific meanings.

- **Frozen context envelope.** `services/context_contract.py` defines `ContextEnvelope`, its evidence source references, typed omissions, and snapshot metadata. `ContextAccessService.build_workspace_pack` now attaches the additive envelope to a workspace pack; `build_agent_conversation_context` uses the same contract for the current Topic, its version, selected sources, and omissions. Omission records now travel inside the envelope rather than living only beside it, so a later reader can distinguish absent material from an empty source. The builder keeps the workspace identity on deep capability evidence and fails closed for a Topic source-analysis run owned by another workspace: it is not injected as creator evidence. The original workflow payload remains intact, and the exact frozen pack is still stored with the creator message. This is not yet a mandate that every reader-retrieval or simulation prompt uses an identical payload.
- **Run event envelope.** `services/run_events.py` gives the existing account diagnosis, trend analysis, video creator quality, and audience simulation graphs one ordered lifecycle vocabulary: run created/started/terminal and stage started/succeeded/failed. It is an in-memory transport contract with a local sequence number, not a new universal run table. Existing durable run records and checkpoint records remain the source of truth, and a public SSE endpoint is not implied by this change.
- **Proposal lifecycle.** `services/proposal_lifecycle.py` decides whether an apply, reject, or undo is allowed *before* a handler writes its target. Asset proposals and Panel edit proposals use it so a repeated completed action returns its stored receipt rather than repeating a side effect. The contract is intentionally storage-agnostic; it does not collapse the different product proposal schemas into one generic artifact system.

The creator canvas now uses that last boundary for AI text edits. A fact-checked `canvasUpdate` is frozen as a `creator-edit/v1` before/suggested snapshot, recorded as `pending_confirmation`, and emitted as an explicit `topic.apply_canvas_edit` asset proposal. This reserved action is server-derived and immutable: generic agent output cannot mint it, the proposed payload cannot later be edited through the generic proposal editor, and the target Topic must match the conversation's canvas context. Preview compares it with the current Topic; apply checks the original `expectedUpdatedAt` and refuses to overwrite a later manual edit. The Topic changes only after the creator applies the proposal. Historical messages that were automatically applied before this change retain their recorded `after` snapshot and remain readable as historical receipts; they are not rewritten as pending proposals.

This is intentionally not the whole collaboration launch. The serial graph now
has durable collaboration session/message/run persistence and a default,
validated Qwen specialist provider. Its read-only discussion candidates are
persisted with messages and handed to the next role with stable candidate IDs,
but it still lacks creator-confirmable candidate-artifact persistence, SSE/event
transport, and canvas collaboration controls. The shared context envelope has
not yet been deliberately extended to the broader reader-retrieval and
audience-simulation prompt contracts. No LangGraph SQLite checkpointer has been
added: product records already save the next pending message and bounded graph
state; a native checkpointer becomes useful only once a durable in-node creator
interruption is actually wired.

## Content collaboration parent graph

Content generation is the one place where a fixed pipeline is too restrictive: a research-oriented role may need a writing role to revise an explanation, while a writing role may ask a reviewer to inspect a specific claim. This does not make the whole product a generic multi-agent platform.

The first collaboration graph has a fixed set of product roles: **research**, **writing**, **review**, and the **creator**. The creator is the human authority, not an LLM agent. The graph stores an append-only discussion envelope and routes one pending message at a time:

```text
creator message or approved action
  -> deterministic dispatcher
  -> addressed specialist completes one turn
  -> validated outbound message with read-only discussion candidates
  -> dispatcher
  -> idle, wait-for-creator, or next addressed specialist
```

The dispatcher only validates recipient IDs, budgets, reply references, artifact access, and terminal states. It does not synthesize instructions, infer a recipient from prose, or turn every public message into a task for every specialist. An agent can address an allowed specialist in structured output; the backend supplies sender identity, message ID, and timestamps. A visible `@name` in free text is presentation only.

Each turn receives a role-specific task packet, one addressed message, the smallest relevant upstream structured result, explicitly referenced asset versions, and the current frozen topic. It does not receive every specialist’s raw model history. In live mode, a Qwen adapter projects those frozen fields to a role-filtered `allowedSources` catalogue rather than giving the model repositories or live workspace reads. Research hands off evidence and evidence gaps; writing must name the research candidate IDs it uses before producing a structure; review must name the writing candidate it evaluates before returning a revision priority. Its only accepted wire output is a role-bound handoff plus at most three read-only candidates; source IDs and quoted evidence are validated by the server. New creative copy or facts absent from supplied sources remain inference / creator-confirmation material rather than evidence. Writing to the Topic remains subject to the existing evidence, version, and creator-confirmation rules.

The graph uses one LangGraph `thread_id` per collaboration session. The first
durable protocol uses three product tables instead of a framework checkpointer:
`content_collaboration_sessions` freezes the Topic-targeted workspace context,
`content_collaboration_messages` is append-only and addressed, and
`content_collaboration_runs` stores the pending message ID, remaining budget,
claim token, and terminal receipt. Each specialist turn is invoked one at a
time: its outbound message and the next graph state are committed before the
next specialist call starts. The product database remains the source of truth
for messages, artifacts, creator decisions, and content versions.

Session APIs are entirely workspace-scoped:

- `POST` / `GET` `/api/workspaces/{workspaceId}/content-collaboration-sessions`
- `GET` / `PATCH` `/api/workspaces/{workspaceId}/content-collaboration-sessions/{sessionId}`
- `POST` `/api/workspaces/{workspaceId}/content-collaboration-sessions/{sessionId}/messages`

The server, not the client, supplies sender identity, message ID, timestamps,
context snapshots, model metadata, and graph state. A creator message request
key is bound to a content-and-recipient fingerprint, so a replay returns the
same run while key reuse for different input conflicts. A queued run may resume
after restart; an in-flight run is marked `failed/interrupted` rather than
silently calling a potentially billable provider again. `interrupt()` is still
reserved for a later explicit creator-choice design; handlers must remain
idempotent because an interrupted node is re-entered on resume.

## Why not migrate all persistence to a framework checkpointer

LangGraph checkpointers are useful for thread-scoped graph state, interruptions, and fault recovery. This project already persists product state and stage results in SQLite, then reconstructs safe workflow state on resume. Replacing that immediately would create two competing histories: framework checkpoints and product versions.

Keep the existing product run tables and checkpoint audit records for now. Consider a native persistent LangGraph checkpointer only when a flow genuinely needs one of these capabilities beyond the current recovery model:

- pausing inside a model/tool loop and resuming the exact loop state;
- several conditional branches sharing a long-lived conversational state; or
- operator inspection and edit of a graph state before continuation.

If adopted, the checkpointer would store short-lived execution state only. Assets, author material, proposals, and final results would remain in product tables.

## Incremental refactor plan

1. **Context Builder contract — implemented for workspace packs and creator conversations.** `ContextEnvelope` records selected evidence, versions, omissions, and a frozen snapshot alongside the existing payload. Next, make a narrow, separately tested adoption decision for reader retrieval and audience simulation rather than forcing a generic prompt shape on them.
2. **Message protocol — implemented for sessions, messages, and runs.** The collaboration kernel now has Pydantic contracts for addressed messages, reply references, artifact references, budgets, and creator waiting; SQLite records the frozen session context, append-only messages, idempotent run requests, and claim-token state. Candidate artifacts deliberately remain a separate next slice.
3. **Serial collaboration graph — default Qwen provider and role packets implemented.** The LangGraph parent graph has a deterministic dispatcher and three fixed specialist nodes. The product runner advances one specialist at a time and commits its output before continuing. Qwen is the default; `demo` never makes a model call and is explicit. The live provider cannot read/write repositories, accepts only the role-specific structured turn contract, carries persisted candidate IDs and source refs into the next role, rejects out-of-contract routing and unsupported quotes, and persists provider/model/prompt-hash/usage receipt data. Keep it serial; do not introduce parallel `Send` fan-out or agent self-planning in the first release.
4. **Durable interruption — deferred by design.** The product run table already preserves restart semantics. Add a SQLite LangGraph checkpointer only when the serial graph needs an in-node creator-choice pause, keeping product writes outside the re-entered node or idempotent.
5. **Operational evaluation — next.** Reuse frozen four-account and panel cases as a product eval suite for the real specialist provider. Record model, prompt hash, input snapshot, request count, validation result, candidate handoff chain, and human review outcome. A synthetic Qwen three-role run now demonstrated evidence → outline → review-candidate handoff; it also caught a review that presented a suggested time anchor as fact. The revised prompt makes such new copy inference / creator-confirmation material. Re-run only against a defined evaluation set, not as a background cost loop. Use PydanticAI or another framework only if a concrete missing capability remains after this seam exists.

## Acceptance criteria

The refactor is successful when an operator can answer, for every model call: what task it served, which frozen product objects it read, why those objects were selected, what was omitted, which model and prompt version produced the result, and whether a human had to confirm the result before it changed content.

It is not successful merely because several agents can call one another, a graph renders visually, or a framework owns more application state.

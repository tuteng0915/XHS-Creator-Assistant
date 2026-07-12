# Documentation Index

This directory now keeps only active product and architecture documents at the
top level. Historical migration notes and prototype audits live in
`docs/backup/`.

## Active documents

- `architecture-review.md` — current architecture review and priority risks.
- `agent-context-access.md` — current Context Access Layer design.
- `input-asset-model.md` — controlled InputAsset abstraction and registry model.
- `llm-context-audit.md` — current LLM call context audit.
- `skill-catalog.md` — current Skill / Agent / Workflow capability model.
- `product-evolution.md` — forward-looking product direction and roadmap.

## Historical reference

- `backup/current-prototype.md` — audit of the original single-file
  `index.html` prototype.
- `backup/migration-plan.md` — old incremental migration plan from prototype to
  React/FastAPI/SQLite/LangGraph.
- `backup/workspace-model.md` — early minimum workspace model before capability
  assets and maker agents were added.

When a document describes completed migration slices or an earlier model that no
longer matches the code, move it to `docs/backup/` instead of deleting it.

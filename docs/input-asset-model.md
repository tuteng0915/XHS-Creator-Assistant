# Input Asset Model

This document defines the current product-specific input asset abstraction.

## Decision

Keep one compatibility storage abstraction, but rename the product model from
`SourceMaterial` to `InputAsset`.

The important model is:

```text
InputAsset = controlled product asset instance
InputAssetType = built-in template / schema / contract
Workspace = owner of asset instances
```

This keeps the system extensible without becoming a generic filesystem.

## Current implementation boundary

The backend still stores these records through the legacy `source_materials`
table, repository, service, and API paths.

That is an implementation compatibility layer. Product code, UI language,
workflow contracts, and context packs should use `InputAsset` terminology.

Do not split these into many tables yet. We expect more product-specific input
asset types later, so a typed asset table plus registry is the better direction.

## Built-in input asset types

| Type | Label | Content kind | Primary workflow roles |
| --- | --- | --- | --- |
| `account_profile` | Account Profiles | text | account profile snapshot |
| `historical_posts` | Historical Posts | text | account diagnosis profile analysis |
| `comments` | Comment Samples | text | account diagnosis pain-point analysis |
| `trend_csv` | Trend CSV Data | file + metadata | trend analysis deterministic ranking |
| `video_creator_samples` | Video Creator Samples | text | video creator quality diagnosis |

## Registry contract

Each input asset type should be registered with:

- stable `type`;
- display label;
- content kind: `text`, `file`, `structured`, or `hybrid`;
- editable fields;
- validation rules;
- workflow roles;
- context selectors;
- default editor behavior;
- whether it supports batch import;
- whether it can be used in batch workflow runs.

The frontend now has a lightweight registry in
`frontend/src/inputAssets.ts`. Backend registry extraction should follow when
API naming is migrated.

## Relationship to workflows

Workflows should declare required input asset types, not generic materials.

```text
account_diagnosis
  requires account_profile
  requires historical_posts
  requires comments

trend_analysis
  requires account_profile
  requires trend_csv

video_creator_quality
  requires account_profile
  requires video_creator_samples
```

Each workflow call should bind concrete asset instance IDs or explicitly choose
manual input that will be saved into an input asset before execution.

## Relationship to skills

Skills should describe inputs and outputs using `InputAsset` semantics.

Stable legacy skill IDs such as `source.save_historical_posts` may remain until
a migration removes old built-in records safely. Their visible contract should
still say that they create or update `InputAsset` records.

Skill context policy should refer to:

- `input_assets_overview`;
- specific selectors such as `historical_posts_text`;
- concrete selected input asset IDs;
- capability catalog context where maker agents need it.

It should not refer to an untyped `source material` bucket.

## Relationship to Context Access Layer

Context packs should use:

```json
{
  "assetType": "input_asset",
  "assetSubType": "historical_posts",
  "assetId": "..."
}
```

The workspace pack should expose:

- `input_assets_overview`;
- `analysis_history_overview`;
- `topic_library_overview`;
- `generated_structure_history_overview`;
- `simulation_history_overview`;
- capability catalog overviews for Skills, Agents, and Workflows.

The compatibility repository can still read from `source_materials`.

## UI model

Input Assets are shown as peer categories in the left sidebar.

Opening a category shows:

- a list of instances for that asset type;
- a new/upload action;
- a detail editor or preview for the selected instance;
- the type contract so the relationship to workflows and context is visible.

This mirrors `Analysis Results`: list first, detail second.

## Non-goals

Do not add:

- arbitrary file trees;
- user-defined generic schemas;
- a plugin marketplace;
- arbitrary filesystem access;
- separate tables for every input asset type;
- user-editable asset type definitions in the creator-facing UI.

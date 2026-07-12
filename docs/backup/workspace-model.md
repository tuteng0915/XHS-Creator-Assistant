# Minimum Creator Workspace Model

本文基于 `index.html` 和 `docs/backup/current-prototype.md`，定义早期产品迁移所需的最小 workspace。目标是把账号诊断、热点分析、选题、内容结构和受众模拟从浏览器临时状态变成可保存、可恢复、可追溯的产品流程。

这不是文件系统。workspace 只包含创作者业务对象，不提供目录树、任意文件编辑或任意路径访问。

## 1. 设计结论

最小实现采用：

- 一个本地应用服务；模型调用由服务端执行，不再由浏览器直接执行。
- 一个 SQLite 数据库，保存所有结构化业务数据、运行状态和版本历史。
- 一个受控上传目录，只保存用户上传的原始 CSV/TSV 文件。
- 两种固定分析流程：`account_diagnosis` 和 `trend_analysis`。
- 一个显式的当前选题；用户确认后才生成结构。
- 内容结构作为 draft 的第一个版本；以后可继续扩展成正文草稿。
- 每次分析和受众模拟都是不可变的 execution history；用户编辑产生业务对象的新版本，不改写历史输出。

不为 profile、痛点和热点主题分别建立大量业务表。它们在第一版中作为 analysis stage 的结构化 JSON 保存。只有需要独立浏览、编辑或进入下一条流程的对象才成为独立实体。

## 2. 产品对象总览

```text
CreatorWorkspace
├── PositioningVersion
├── SourceSet
│   ├── HistoricalPost
│   ├── CommentSample
│   └── TrendDataset ── TrendPost
├── AnalysisRun ── AnalysisRunStage
│   └── uses SourceSet(s)
│   └── creates Topic(s)
├── Topic ── TopicVersion
│   └── selected by CreatorWorkspace
├── StructureGenerationRun
│   └── TopicVersion → DraftVersion
├── Draft ── DraftVersion
│   └── created from TopicVersion
└── AudienceSimulationRun
    └── targets TopicVersion or DraftVersion
    └── may use AnalysisRun(s) as context
```

所有对象都属于一个 `CreatorWorkspace`。跨 workspace 复用不在最小范围内。

## 3. 实体与字段

字段类型使用 SQLite 语义：`TEXT`、`INTEGER`、ISO 8601 时间字符串，以及以 `TEXT` 保存并用 `json_valid()` 校验的 JSON。

### 3.1 `creator_workspaces`

代表一个创作者账号的内容工作区。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | UUID/ULID |
| `name` | TEXT NOT NULL | 用户可编辑的 workspace 名称 |
| `platform` | TEXT NOT NULL | 第一版固定为 `xiaohongshu` |
| `current_positioning_version_id` | TEXT FK | 当前生效的账号定位版本 |
| `selected_topic_id` | TEXT FK NULL | 当前选中的选题；用于结构生成入口 |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 最近业务修改时间 |
| `archived_at` | TEXT NULL | 软归档；第一版可不在 UI 提供永久删除 |

约束：`selected_topic_id` 必须指向同一 workspace 中未归档的 topic。

### 3.2 `positioning_versions`

账号定位需要轻量版本历史，因为它影响后续所有分析，但不需要拆成复杂 profile 表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | 版本 ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `version_number` | INTEGER NOT NULL | workspace 内递增 |
| `positioning_text` | TEXT NOT NULL | 与当前原型一致的完整自由文本 |
| `created_at` | TEXT NOT NULL | 创建时间 |

`UNIQUE(workspace_id, version_number)`。

编辑账号定位时创建新版本，并更新 `current_positioning_version_id`；旧版本不修改。第一版不强制解析“核心人群、内容主张、作者优势”等子字段，避免过早建模。

### 3.3 `source_sets`

`SourceSet` 是一批可复用创作材料的产品集合，不是文件夹。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | 集合 ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `kind` | TEXT NOT NULL | `historical_posts`、`comment_samples`、`trend_csv` |
| `name` | TEXT NOT NULL | 如“2026 Q2 历史笔记”“数字游民 7 月样本” |
| `description` | TEXT NULL | 简短来源说明 |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 最近修改时间 |
| `archived_at` | TEXT NULL | 从新分析选择器隐藏，但保留历史引用 |

一个 source set 只能容纳其 `kind` 对应的记录。分析 run 选择 source set，而不是依赖页面上某个临时 textarea。

### 3.4 `historical_posts`

历史笔记可手工录入、批量粘贴或后续通过受控导入增加。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | 笔记 ID |
| `source_set_id` | TEXT FK NOT NULL | 必须属于 `historical_posts` 集合 |
| `title` | TEXT NOT NULL | 笔记标题 |
| `content_snippet` | TEXT NULL | 可选正文或摘要 |
| `likes` | INTEGER NULL | 点赞数 |
| `collects` | INTEGER NULL | 收藏数 |
| `comments_count` | INTEGER NULL | 评论数 |
| `performance_label` | TEXT NULL | `viral`、`average`、`poor` 或空 |
| `tags_json` | TEXT JSON NOT NULL | 字符串数组，默认 `[]` |
| `published_at` | TEXT NULL | 发布时间 |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 修改时间 |
| `archived_at` | TEXT NULL | 软删除 |

当前原型的「标题｜数据｜爆/平/差」文本在导入时解析为这些字段。

### 3.5 `comment_samples`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | 评论 ID |
| `source_set_id` | TEXT FK NOT NULL | 必须属于 `comment_samples` 集合 |
| `historical_post_id` | TEXT FK NULL | 若知道评论来自哪篇历史笔记则关联 |
| `text` | TEXT NOT NULL | 评论原文 |
| `collected_at` | TEXT NULL | 采集时间 |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 修改时间 |
| `archived_at` | TEXT NULL | 软删除 |

痛点分析的 evidence 应在输出 JSON 中保存 `comment_sample_id + excerpt`。无法匹配 ID 时仍可保存 excerpt，但 UI 应标记为“无来源回链”。

### 3.6 `trend_datasets`

每次上传形成一个不可变 dataset。修正原始文件时上传新 dataset，不覆盖旧文件。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | dataset ID |
| `source_set_id` | TEXT FK NOT NULL UNIQUE | 对应一个 `trend_csv` source set |
| `keyword` | TEXT NOT NULL | 热点话题关键词 |
| `original_filename` | TEXT NOT NULL | 仅用于显示，不作为实际磁盘路径 |
| `stored_relative_path` | TEXT NOT NULL | 服务端生成的受控相对路径 |
| `sha256` | TEXT NOT NULL | 完整性与重复上传检测 |
| `media_type` | TEXT NOT NULL | `text/csv` 或 `text/tab-separated-values` |
| `byte_size` | INTEGER NOT NULL | 文件大小 |
| `parse_status` | TEXT NOT NULL | `pending`、`parsed`、`failed` |
| `parse_error` | TEXT NULL | 安全、截断后的解析错误 |
| `field_mapping_json` | TEXT JSON NOT NULL | 原始表头到产品字段的映射 |
| `row_count` | INTEGER NOT NULL | 成功解析条数，初值 0 |
| `created_at` | TEXT NOT NULL | 上传时间 |
| `archived_at` | TEXT NULL | 归档时间 |

### 3.7 `trend_posts`

上传成功后，把可分析的行解析进 SQLite。原始 CSV 留在磁盘用于复查和重新解析。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | 热帖记录 ID |
| `trend_dataset_id` | TEXT FK NOT NULL | 所属 dataset |
| `source_row_number` | INTEGER NOT NULL | 原 CSV 行号 |
| `title` | TEXT NOT NULL | 标题 |
| `likes` | INTEGER NULL | 点赞数 |
| `collects` | INTEGER NULL | 收藏数 |
| `comments_count` | INTEGER NULL | 评论数 |
| `tags_json` | TEXT JSON NOT NULL | 标签数组 |
| `content_snippet` | TEXT NULL | 内容片段 |
| `published_at` | TEXT NULL | 发布时间 |

`UNIQUE(trend_dataset_id, source_row_number)`。解析后的 trend post 不单独编辑；需要更正时生成一个新 dataset，保证上传材料与分析快照一致。

### 3.8 `analysis_runs`

只支持两种固定分析，不支持用户自定义流程。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | run ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `type` | TEXT NOT NULL | `account_diagnosis` 或 `trend_analysis` |
| `status` | TEXT NOT NULL | `queued`、`running`、`partial`、`succeeded`、`failed`、`cancelled` |
| `positioning_version_id` | TEXT FK NOT NULL | 本次运行使用的定位版本 |
| `keyword_snapshot` | TEXT NULL | 热点分析关键词快照 |
| `model` | TEXT NOT NULL | 实际模型 ID |
| `prompt_version` | TEXT NOT NULL | 固定 prompt 套件版本 |
| `input_snapshot_json` | TEXT JSON NOT NULL | 模型实际看到的规范化输入；与可编辑材料隔离 |
| `error_code` | TEXT NULL | 稳定的产品错误码 |
| `error_message` | TEXT NULL | 安全、截断后的用户可见错误 |
| `retry_of_run_id` | TEXT FK NULL | 若由失败 run 重试创建，指向原 run |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `started_at` | TEXT NULL | 开始时间 |
| `completed_at` | TEXT NULL | 完成时间 |

`input_snapshot_json` 至少包含：定位文本、被选择的 source set 及记录 ID、实际送模文本、热点 top 50 排序规则和被选中的 trend post ID。它在 run 创建后不可修改。

### 3.9 `analysis_run_sources`

保存分析与材料的多对多关系。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `analysis_run_id` | TEXT FK | run |
| `source_set_id` | TEXT FK | 被使用的 source set |
| `role` | TEXT NOT NULL | `historical_posts`、`comments` 或 `trend_posts` |

主键为 `(analysis_run_id, source_set_id, role)`。应用层验证 source set kind 与 role 匹配。

### 3.10 `analysis_run_stages`

固定 stage 记录让工作流调用可控，并支持刷新后恢复进度。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | stage ID |
| `analysis_run_id` | TEXT FK NOT NULL | 所属 run |
| `stage_key` | TEXT NOT NULL | 见下方固定列表 |
| `sequence` | INTEGER NOT NULL | 显示与执行顺序 |
| `status` | TEXT NOT NULL | `pending`、`running`、`succeeded`、`failed`、`skipped` |
| `attempt_count` | INTEGER NOT NULL | 调用尝试次数 |
| `model` | TEXT NULL | 本 stage 实际模型 |
| `prompt_version` | TEXT NOT NULL | stage prompt 版本 |
| `input_json` | TEXT JSON NOT NULL | stage 的不可变输入快照 |
| `output_json` | TEXT JSON NULL | 成功后的结构化输出 |
| `reused_from_stage_id` | TEXT FK NULL | retry run 复用旧成功结果时的来源 stage |
| `error_code` | TEXT NULL | 稳定错误码 |
| `error_message` | TEXT NULL | 安全错误信息 |
| `started_at` | TEXT NULL | 开始时间 |
| `completed_at` | TEXT NULL | 完成时间 |

`UNIQUE(analysis_run_id, stage_key)`。

固定 stage：

- Account diagnosis：`account_profile`、`pain_points`、`topic_generation`。
- Trend analysis：`trend_summary`、`pain_points`、`topic_generation`。

结构生成不再隐式绑定 `topics[0]`，而是在用户选择 topic 后单独创建 structure run，并在成功后创建 draft version。这样保留当前产品链路，同时把最重要的模型调用控制点交给用户。

profile、pain points、trend analysis 和模型返回的 topic batch 原文均保存在 `output_json`。第一版不把 pain point cluster、profile pillar、trend theme 分拆为独立表。

### 3.11 `topics`

Topic 是选题库中的稳定业务对象。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | topic ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `origin` | TEXT NOT NULL | `generated` 或 `manual` |
| `source_analysis_run_id` | TEXT FK NULL | 生成选题的分析；手工选题为空 |
| `current_version_id` | TEXT FK NOT NULL | 当前版本 |
| `status` | TEXT NOT NULL | `active`、`developing`、`archived` |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 修改时间 |

分析的 `topic_generation` stage 成功后，在同一事务中为每个生成选题创建 `Topic + TopicVersion`。stage output 保留完整原始批次；Topic 是可编辑副本。

### 3.12 `topic_versions`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | 版本 ID |
| `topic_id` | TEXT FK NOT NULL | 所属 topic |
| `version_number` | INTEGER NOT NULL | topic 内递增 |
| `title` | TEXT NOT NULL | 选题标题 |
| `angle` | TEXT NULL | 切入角度 |
| `pain_label` | TEXT NULL | 对应痛点的显示快照 |
| `why_fit` | TEXT NULL | 为什么适合账号 |
| `why_trending` | TEXT NULL | 热点选题的时机理由 |
| `title_variants_json` | TEXT JSON NOT NULL | 标题变体数组 |
| `source_stage_id` | TEXT FK NULL | 初始生成来源；手工或后续编辑版本可为空 |
| `created_at` | TEXT NOT NULL | 创建时间 |

`UNIQUE(topic_id, version_number)`。编辑选题创建新版本并更新 `topics.current_version_id`。选中状态放在 workspace，而不是写进版本。

### 3.13 `drafts`

Draft 表示围绕一个 topic 持续发展的内容。只有结构也算一个 draft。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | draft ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `topic_id` | TEXT FK NOT NULL | 来源选题 |
| `current_version_id` | TEXT FK NOT NULL | 当前版本 |
| `status` | TEXT NOT NULL | `outline`、`drafting`、`ready_for_simulation`、`archived` |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 修改时间 |

第一版允许一个 topic 有多个 draft，但默认复用该 topic 最近的未归档 draft。

### 3.14 `draft_versions`

每次结构生成或保存编辑都创建新版本。版本本身不可修改。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | draft version ID |
| `draft_id` | TEXT FK NOT NULL | 所属 draft |
| `version_number` | INTEGER NOT NULL | draft 内递增 |
| `source_topic_version_id` | TEXT FK NOT NULL | 生成/编辑时使用的 topic 版本 |
| `selected_title` | TEXT NOT NULL | 本版本采用的标题 |
| `outline_json` | TEXT JSON NOT NULL | `[{section, content}]` |
| `reusable_structure` | TEXT NULL | 当前原型的 `reuse` |
| `body_text` | TEXT NULL | 后续正文；第一版允许为空 |
| `creation_kind` | TEXT NOT NULL | `model_generated` 或 `user_edit` |
| `model` | TEXT NULL | 模型生成时记录 |
| `prompt_version` | TEXT NULL | 模型生成时记录 |
| `input_snapshot_json` | TEXT JSON NOT NULL | 定位、topic 和分析上下文的快照 |
| `created_at` | TEXT NOT NULL | 创建时间 |

`UNIQUE(draft_id, version_number)`。模型生成失败时不创建 draft version；错误和输入保存在对应的 `StructureGenerationRun`。

### 3.15 `structure_generation_runs`

结构生成也需要刷新恢复，但它是固定的产品操作，不需要通用 job 表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | structure run ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `topic_version_id` | TEXT FK NOT NULL | 被选中并实际送模的选题版本 |
| `context_analysis_run_id` | TEXT FK NULL | 用户选用的分析上下文 |
| `status` | TEXT NOT NULL | `queued`、`running`、`succeeded`、`failed`、`cancelled` |
| `model` | TEXT NOT NULL | 实际模型 |
| `prompt_version` | TEXT NOT NULL | 结构 prompt 版本 |
| `input_snapshot_json` | TEXT JSON NOT NULL | 定位、topic 与分析上下文快照 |
| `output_json` | TEXT JSON NULL | 模型返回的 structure 原始结构化结果 |
| `created_draft_version_id` | TEXT FK NULL | 成功后创建的 DraftVersion |
| `error_code` | TEXT NULL | 稳定错误码 |
| `error_message` | TEXT NULL | 安全错误信息 |
| `retry_of_run_id` | TEXT FK NULL | 重试时指向原 structure run |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `started_at` | TEXT NULL | 开始时间 |
| `completed_at` | TEXT NULL | 完成时间 |

run 创建后输入不可修改。成功时在同一事务中写 `output_json`、创建 Draft/DraftVersion、设置 `created_draft_version_id` 并完成 run。retry 创建新的 structure run 并设置 `retry_of_run_id`，不改变原 run。

### 3.16 `audience_simulation_runs`

受众模拟是一条不可变的发布前测试记录。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PK | simulation run ID |
| `workspace_id` | TEXT FK NOT NULL | 所属 workspace |
| `target_topic_version_id` | TEXT FK NULL | 直接测试选题时设置 |
| `target_draft_version_id` | TEXT FK NULL | 测试结构/草稿时设置 |
| `status` | TEXT NOT NULL | `queued`、`running`、`partial`、`succeeded`、`failed`、`cancelled` |
| `target_snapshot_json` | TEXT JSON NOT NULL | 被测试内容的不可变快照 |
| `context_snapshot_json` | TEXT JSON NOT NULL | 定位、评论/关键词、相关分析结论的实际输入 |
| `model` | TEXT NOT NULL | 实际模型 |
| `prompt_version` | TEXT NOT NULL | 模拟 prompt 套件版本 |
| `stage_status_json` | TEXT JSON NOT NULL | persona/reaction/debate/synthesis 的细分状态 |
| `personas_json` | TEXT JSON NULL | persona snapshots |
| `reactions_json` | TEXT JSON NULL | 每个 persona 的 reaction 与失败状态 |
| `debate_json` | TEXT JSON NULL | 每个 persona 的讨论与失败状态 |
| `synthesis_json` | TEXT JSON NULL | 综合评估 |
| `error_code` | TEXT NULL | run 级错误码 |
| `error_message` | TEXT NULL | 安全错误信息 |
| `retry_of_run_id` | TEXT FK NULL | 重试时指向原 simulation run |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `started_at` | TEXT NULL | 开始时间 |
| `completed_at` | TEXT NULL | 完成时间 |

约束：`target_topic_version_id` 与 `target_draft_version_id` 必须且只能有一个非空，并且目标属于同一 workspace。

模拟内部数据当前只需整体展示，不需要跨 run 查询 persona，因此保存在 JSON 中比拆成四组表更小。每条 JSON item 仍应有稳定 ID 和 `status`，支持 partial result。

### 3.17 `simulation_analysis_contexts`

可选的多对多关系，记录模拟使用了哪些已保存分析。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `simulation_run_id` | TEXT FK | simulation |
| `analysis_run_id` | TEXT FK | 提供上下文的 analysis |

主键为 `(simulation_run_id, analysis_run_id)`。即使以后 analysis 被归档，simulation 仍保留关系和 `context_snapshot_json`。

## 4. 关系与删除规则

```text
Workspace 1 ── N PositioningVersion
Workspace 1 ── N SourceSet
SourceSet(historical_posts) 1 ── N HistoricalPost
SourceSet(comment_samples)  1 ── N CommentSample
SourceSet(trend_csv)         1 ── 1 TrendDataset 1 ── N TrendPost

Workspace 1 ── N AnalysisRun
AnalysisRun N ── N SourceSet           through AnalysisRunSource
AnalysisRun 1 ── N AnalysisRunStage
AnalysisRun 1 ── N generated Topic

Workspace 1 ── N Topic 1 ── N TopicVersion
Workspace 1 ── 0..1 selected Topic
Topic 1 ── N Draft 1 ── N DraftVersion
DraftVersion N ── 1 source TopicVersion
TopicVersion 1 ── N StructureGenerationRun ── 0..1 DraftVersion

Workspace 1 ── N AudienceSimulationRun
AudienceSimulationRun N ── 1 TopicVersion XOR DraftVersion
AudienceSimulationRun N ── N AnalysisRun
```

删除策略：

- workspace、source set、材料、topic 和 draft 默认软归档。
- 已被 run 引用的 source set 不做硬删除；归档后不再出现在新运行的默认选择器中。
- 已完成的 analysis run、stage、structure run、draft version 和 simulation run 不允许修改或删除。
- trend dataset 归档时默认保留原文件，因为历史详情仍需复查；只有显式“永久删除未引用数据集”操作才删除文件，且第一版可以不提供该操作。
- 外键使用 `RESTRICT` 保护执行历史；不做级联删除历史数据。

## 5. 生命周期

### 5.1 创建 workspace

1. 用户输入 workspace 名称和账号定位。
2. 事务中创建 `creator_workspaces` 和 `positioning_versions` v1。
3. 设置 `current_positioning_version_id`。
4. 返回 workspace 概览，浏览器将当前 workspace ID 写入 URL。

### 5.2 添加可复用材料

#### 历史笔记和评论

1. 用户新建或选择相应 source set。
2. 手工输入、粘贴或批量提交记录。
3. 服务端校验并写入 SQLite。
4. 后续修改更新源记录；过去 run 不受影响，因为 run 已保存输入快照。

#### 热点 CSV

1. 服务端先创建 `source_set + trend_dataset(parse_status=pending)`。
2. 以服务端生成的文件名把上传内容写入受控磁盘路径。
3. 计算 SHA-256，解析表头和行。
4. 在事务中写入 `trend_posts`、field mapping 和 row count。
5. 成功置为 `parsed`；失败置为 `failed` 并保留原文件供用户重新映射或重新上传。

### 5.3 运行账号诊断

1. 用户选择历史笔记集合和评论集合。
2. 服务端创建 `analysis_run`、source 关系、三个固定 stage 和完整 input snapshot。
3. `account_profile` 与 `pain_points` 可并行；每个 stage 的开始、成功或失败立即提交 SQLite。
4. 至少一个前置 stage 成功时执行 `topic_generation`，并把缺失上下文标为 partial。
5. 生成选题在事务中写入 topic library。
6. run 最终状态为 `succeeded`、`partial` 或 `failed`。

### 5.4 运行热点分析

1. 用户选择一个已解析 trend dataset，并确认关键词和账号定位版本。
2. 服务端按固定规则计算互动排序并选 top 50，将记录 ID 和规范化文本写入 snapshot。
3. `trend_summary` 与 `pain_points` 并行。
4. 至少一个成功时执行 `topic_generation`。
5. 生成 topic 写入 topic library，并保留 `why_trending` 和标题变体。

### 5.5 手工选题与选择选题

- 手工添加 topic 时创建 `origin=manual` 的 Topic 和 v1 TopicVersion。
- 编辑任何选题时创建新 TopicVersion。
- “设为当前选题”只更新 `creator_workspaces.selected_topic_id`。
- 当前选题卡展示来源、当前版本和“生成内容结构”操作。
- 选择另一选题不会删除已有 draft 或模拟。

### 5.6 生成结构和编辑草稿

1. 用户从当前选题发起结构生成，并可选择一个相关 analysis run 作为上下文。
2. 服务端读取当前 PositioningVersion、TopicVersion 和 analysis stage 结果，形成不可变输入 snapshot。
3. 服务端先持久化 `StructureGenerationRun(status=queued)` 并返回 run ID；浏览器不等待单个长 HTTP 请求。
4. 执行器调用模型。成功后创建 Draft（若尚无）及新的 model-generated DraftVersion，并关联回 structure run。
5. 用户编辑结构、标题或正文时创建新的 user-edit DraftVersion。
6. `drafts.current_version_id` 总是指向最新保存版本；旧版本可查看和恢复，恢复也通过创建新版本完成。

### 5.7 运行受众模拟

1. 用户选择当前 topic 或某个 draft version。
2. 创建 simulation run，保存 target 和 context snapshot 后立即返回 run ID。
3. 后台依次执行 persona、并行 reactions、并行 debate、synthesis；每个阶段完成后更新 `stage_status_json` 和相应结果列。
4. 某个 persona 调用失败时保留其他结果，run 可为 `partial`，界面不永久显示 loading。
5. 运行完成后不可修改；对修改后的 topic/draft 重新运行会创建新 simulation run。

## 6. 可编辑信息与不可变历史

| 数据 | 用户行为 | 历史规则 |
| --- | --- | --- |
| Workspace 名称 | 原地编辑 | 不需要版本历史 |
| 账号定位 | 编辑 | 每次保存创建 PositioningVersion |
| SourceSet 名称/描述 | 原地编辑 | 只影响材料组织，不改变 run snapshot |
| HistoricalPost | 编辑或归档 | 过去 run 保留输入 snapshot |
| CommentSample | 编辑或归档 | 过去 run 保留输入 snapshot |
| TrendDataset 原始文件和解析行 | 不编辑；可归档 | 修正时上传新 dataset |
| AnalysisRun 与 stages | 不编辑 | 完整不可变 execution history；只允许系统推进 status |
| Topic | 编辑、归档、设为当前 | 内容编辑创建 TopicVersion |
| TopicVersion | 不编辑 | 不可变；可被 draft/simulation 精确引用 |
| StructureGenerationRun | 不编辑 | 不可变 execution history；运行状态只由服务端推进 |
| Draft | 改状态、归档 | 内容不直接写在 Draft 行 |
| DraftVersion | 不编辑 | 每次保存创建新版本 |
| AudienceSimulationRun | 不编辑 | 不可变 execution history |

“不可变”指完成后的业务规则。运行中的 status、stage 结果和时间字段只能由服务端执行器按状态机更新，客户端不能任意 PATCH。

## 7. SQLite 与磁盘边界

### 7.1 SQLite 保存

SQLite 保存：

- workspace 名称、当前定位版本和当前选题。
- 定位版本。
- source set 元数据。
- 历史笔记和评论样本。
- trend dataset 元数据与所有解析后的 trend post 行。
- analysis run、材料关系、每个 stage 状态、输入快照、输出和错误。
- topic library、topic versions 和标题变体。
- structure generation run 的状态、输入、输出、错误与生成版本关系。
- draft、结构/正文版本和生成快照。
- audience simulation run 的状态、persona、reaction、debate 和 synthesis JSON。
- 所有实体关系和时间戳。

SQLite 应启用：

- foreign keys；
- WAL mode；
- 事务写入；
- 对 workspace foreign key、run status、topic status、created_at 建索引；
- JSON 列的 `json_valid()` check；
- 单进程写队列或短事务，避免模型调用期间持有数据库事务。

模型请求在事务外执行：调用前把 stage 标为 running 并提交；调用后用新事务写成功/失败结果。

### 7.2 磁盘保存

磁盘只保存用户上传的原始 `.csv` 或 `.tsv`：

```text
data/
├── app.sqlite3
└── uploads/
    └── trends/
        └── {workspace_id}/
            └── {trend_dataset_id}/
                └── source.csv
```

实际文件名由服务端决定，扩展名按验证后的媒体类型选择。`original_filename` 只存 SQLite 并用于显示。

不把以下内容写成用户可浏览文件：账号定位、历史笔记、评论、模型 prompts、分析 JSON、topics、drafts 或 simulations。它们都在 SQLite 中。应用不提供目录浏览、路径输入或任意文件读写 API。

上传要求：限制大小和扩展名；拒绝路径片段；在目标目录内原子写入；计算 hash；解析时不执行任何单元格内容。

## 8. Workspace sidebar

sidebar 只显示固定产品导航：

```text
[Workspace name]

概览
材料
  历史笔记          {count}
  评论样本          {count}
  热点数据          {dataset count}
分析
  账号诊断          {latest status}
  热点分析          {latest status}
选题库              {active count}
草稿                {active count}
受众模拟            {run count}

[当前选题]
{selected topic title or “尚未选择”}
[生成内容结构]
```

行为：

- 顶部 workspace 名称可进入概览编辑名称和账号定位。
- “材料”是三个固定类型的聚合入口，不展开成目录树。
- 分析条目显示运行中/部分成功/失败 badge；点击进入 run 列表和详情。
- 当前选题固定在 sidebar 底部，保证从分析或选题库切换页面后仍可继续生成结构。
- 有运行中的 analysis/simulation 时显示状态，但刷新后状态来自服务端，不依赖浏览器内存。
- 有运行中的 structure generation 时，当前选题卡显示“结构生成中”，点击可返回 run 详情。

第一版不需要单独的“设置”“文件”“成员”或“扩展”入口。

## 9. Resume after refresh

### 9.1 浏览器恢复

- workspace ID 和当前页面写入 URL，例如 `/workspaces/{id}/analysis/{runId}`，不只放在 JavaScript 变量中。
- 页面启动先请求 workspace summary，再请求当前资源详情。
- 输入表单的已保存内容来自 SQLite。定位、topic 和 draft 使用明确的“保存”动作创建版本；刷新恢复到最后一次保存。分析配置在点击运行时一次提交，并在任何模型调用前持久化。
- analysis、structure generation 和 simulation 创建后立即返回持久化的 run ID。前端通过轮询 `GET run` 或服务端事件更新状态；第一版只实现轮询即可。
- 刷新页面后，前端根据 stage status 重建 loading、成功、partial 和失败 UI，不重发已完成模型调用。

### 9.2 服务端恢复

- 服务启动时扫描 analysis、structure 和 simulation 中 `queued` 与超时的 `running` run/stage。
- `queued` stage 可以继续执行。
- 进程在外部模型请求中途崩溃时，无法确认请求是否已产生结果；对应 analysis stage、structure run 或 simulation stage 标为 `failed` 且 `error_code=execution_interrupted`，由用户显式 retry，避免无边界重复调用。
- retry 创建一个带 `retry_of_run_id` 的新 run。analysis retry 可通过 `reused_from_stage_id` 引用原 run 已成功 stage 的输出，只执行失败 stage 及其下游；structure 和 simulation retry 也创建新 run。原 run 不改变。
- 每个 stage 完成后先把结果和状态在一个事务中提交，再调度下游。
- 同一 run 同一 stage 在任一时刻只允许一个 active attempt。

### 9.3 用户看到的恢复结果

- 已保存材料、选题、草稿和当前选题完整恢复。
- 已完成 run 直接显示结果。
- 仍在运行的 stage 继续显示准确进度。
- 中断的 stage 显示“执行中断，可重试”，而不是永久 spinner。
- partial 结果继续可查看；基于 partial run 生成结构时明确提示缺失的分析依据。

## 10. 最小 API

API 全部是产品对象接口，不接受服务器路径或任意文件名读取。

### 10.1 Workspaces

| Method | Endpoint | 用途 |
| --- | --- | --- |
| `GET` | `/api/workspaces` | 列出 workspace，用于启动页 |
| `POST` | `/api/workspaces` | 创建 workspace；body 含 `name`, `positioningText` |
| `GET` | `/api/workspaces/:workspaceId` | 返回概览、当前定位、当前选题、计数和运行状态 |
| `PATCH` | `/api/workspaces/:workspaceId` | 修改名称；传 `positioningText` 时创建定位新版本 |

### 10.2 Materials

| Method | Endpoint | 用途 |
| --- | --- | --- |
| `GET` | `/api/workspaces/:workspaceId/materials?kind=...` | 列出固定类型 source sets 及记录摘要 |
| `PATCH` | `/api/source-sets/:sourceSetId` | 修改材料集合名称/说明或软归档 |
| `POST` | `/api/workspaces/:workspaceId/historical-posts` | 新建/批量导入历史笔记，可同时新建 source set |
| `PATCH` | `/api/historical-posts/:postId` | 编辑或归档历史笔记 |
| `POST` | `/api/workspaces/:workspaceId/comment-samples` | 新建/批量导入评论样本 |
| `PATCH` | `/api/comment-samples/:commentId` | 编辑或归档评论 |
| `POST` | `/api/workspaces/:workspaceId/trend-datasets` | multipart 上传 CSV/TSV 并解析 |
| `GET` | `/api/trend-datasets/:datasetId` | 查看解析状态、字段映射、条数和热帖分页 |
| `DELETE` | `/api/trend-datasets/:datasetId` | 软归档 dataset，不删除被历史引用的文件 |

`source_set` 只提供 rename/description/archive，不提供目录层级或任意 kind。

### 10.3 Analysis runs

| Method | Endpoint | 用途 |
| --- | --- | --- |
| `GET` | `/api/workspaces/:workspaceId/analysis-runs?type=...` | 列出账号诊断或热点分析历史 |
| `POST` | `/api/workspaces/:workspaceId/analysis-runs` | 创建固定类型 run；body 含 `type`, `sourceSetIds`, 可选 `keyword` |
| `GET` | `/api/analysis-runs/:runId` | 返回 run、stage 状态与结构化结果，供详情和刷新恢复 |
| `POST` | `/api/analysis-runs/:runId/retry` | 基于原快照创建 retry run，复用成功 stage，只执行失败/中断 stage 及下游 |

取消按钮不是第一版必需；若上线时保留长运行取消，再增加 `POST /api/analysis-runs/:runId/cancel`，而不是让客户端直接改 status。

### 10.4 Topics and drafts

| Method | Endpoint | 用途 |
| --- | --- | --- |
| `GET` | `/api/workspaces/:workspaceId/topics` | 列出 generated/manual topics |
| `POST` | `/api/workspaces/:workspaceId/topics` | 手工创建 topic |
| `GET` | `/api/topics/:topicId` | 返回当前内容、版本历史、来源分析和关联 drafts |
| `PATCH` | `/api/topics/:topicId` | 编辑时创建 TopicVersion，或修改 status |
| `PUT` | `/api/workspaces/:workspaceId/selected-topic` | body `{topicId}` 或 `{topicId:null}` |
| `GET` | `/api/workspaces/:workspaceId/drafts` | 列出 drafts 及当前版本摘要 |
| `POST` | `/api/topics/:topicId/structure-runs` | 对指定 topic 当前版本创建异步结构生成 run，返回 run ID |
| `GET` | `/api/structure-runs/:runId` | 返回结构生成状态、错误和生成的 DraftVersion ID |
| `POST` | `/api/structure-runs/:runId/retry` | 基于原快照创建新的 structure run |
| `GET` | `/api/drafts/:draftId` | 返回 draft 和版本历史 |
| `POST` | `/api/drafts/:draftId/versions` | 保存用户编辑为新 DraftVersion |

`POST /structure-runs` 必须使用路径中的明确 topic，不允许服务端隐式取“第一个生成选题”。sidebar 的当前选题只是快捷入口。

### 10.5 Audience simulations

| Method | Endpoint | 用途 |
| --- | --- | --- |
| `GET` | `/api/workspaces/:workspaceId/audience-simulations` | 列出模拟历史 |
| `POST` | `/api/workspaces/:workspaceId/audience-simulations` | 创建模拟；body 指定 `topicVersionId` 或 `draftVersionId` 及上下文 analysis IDs |
| `GET` | `/api/audience-simulations/:simulationId` | 返回 stage 状态与全部结果，供详情和刷新恢复 |
| `POST` | `/api/audience-simulations/:simulationId/retry` | 基于原目标和上下文快照创建新的 simulation run |

这组 API 已覆盖创建 workspace、导入材料、两种分析、选题库、选择选题、结构/草稿版本、受众模拟和刷新恢复。第一版不增加通用 CRUD 网关、通用任务编排接口或文件下载路径接口。

## 11. 最小实现顺序

1. 建立 SQLite schema、受控 CSV 上传目录和 workspace 概览。
2. 把三类输入迁移为 source sets 和结构化材料。
3. 把账号诊断、热点分析改成服务端 `AnalysisRun + Stage`，实现刷新恢复。
4. 将生成选题落入 topic library，并实现手工选题和当前选题。
5. 将结构生成从“自动取 topics[0]”改为针对选定 TopicVersion，保存为 DraftVersion。
6. 保存受众模拟 run，并让综合评估真正读取 reaction 和 debate 的完整结果。
7. 最后迁移 demo fixture，使 demo 和 live 继续共用相同 workspace 数据与结果组件。

做到第 6 步时，当前原型的核心价值链已经稳定落地；后续功能可以围绕材料、分析、选题、草稿和模拟增加，而不需要扩大成通用平台。

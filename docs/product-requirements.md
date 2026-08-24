# 创作者工作区 PRD（Reverse PRD）

更新日期：2026-08-24

本文档是基于当前代码与已迁移产品形态反向整理的 PRD。它描述的是当前产品应该被如何理解、使用和继续演进，而不是一个通用 agent 平台规格。

如果只想快速理解产品功能和设计思想，先读 `docs/product-design.md`。本文档保留更细的资产字段、用户流程、模型调用要求、非目标和验收清单。

## 1. 产品定位

创作者工作区是一个面向创作者运营、内容策划和账号增长分析的内部共创工具。

它的核心目标是把分散的创作者材料、账号分析、热点分析、选题、内容结构和受众模拟沉淀成可复用资产，并通过一组产品内置的 skill、agent、workflow 帮助用户反复调用这些资产。

当前产品不是：

- 通用 agent builder；
- 通用 workflow editor；
- 文件系统或 VS Code clone；
- plugin marketplace；
- 多租户 SaaS；
- 任意代码执行平台。

## 2. 目标用户

### 2.1 创作者运营

典型场景：

- 判断一个账号或视频博主是否值得重点运营；
- 判断创作者是否适合某个激励计划；
- 将单个创作者的材料、诊断结果、选题和模拟沉淀为可复盘资产。

### 2.2 内容策略 / 选题策划

典型场景：

- 基于历史笔记和评论区提炼账号定位；
- 基于热点 CSV 找内容机会；
- 将分析结果转化为选题库；
- 对选题生成内容结构；
- 用受众模拟判断选题是否有传播和转化潜力。

### 2.3 产品 / 研发维护者

典型场景：

- 维护内置 skills、agents、workflows；
- 通过 Capability Maker 生成能力资产 proposal；
- 检查 prompt、上下文输入和 workflow 输出是否符合产品语义；
- 后续把更多固定能力转成可组合资产。

## 3. 核心问题

当前产品解决的问题：

1. 创作者相关材料分散，难以沉淀为可复用资产。
2. 账号诊断、热点分析、视频质量判断、受众模拟之间缺少统一的资产连接。
3. LLM workflow 如果只靠前端临时输入，刷新后难以恢复，也难以复盘。
4. 后续新增能力时，如果所有逻辑都写死在单个页面里，功能会越来越难维护。
5. 用户不应该被迫填写复杂表单；更适合通过 agent 帮用户把自然语言材料整理成结构化资产草稿。

## 4. 产品原则

### 4.1 资产优先

所有重要输入和输出都应该成为资产，而不是只存在于一次页面状态中。

内容资产包括：

- 用户输入类资产；
- workflow 输出后可复用的结果资产。

能力资产包括：

- skills；
- agents；
- workflows；
- conversations；
- proposals。

创作类对象的划分原则：

- Topic、Content Brief、Content Structure、Draft、SimulationRun 是内容资产；
- 生成 Brief、生成结构、改写、润色、基于模拟反馈修订，是能力资产；
- 前端按钮可以直接触发这些能力，但按钮不是资产本身；
- 能力资产 catalog 必须能解释这些按钮背后调用的是哪个 skill / agent / workflow。

### 4.2 产品特定，而非通用平台

资产类型、workflow、agent 和 skill 都围绕创作者内容运营场景设计。

例如：

- 账号概况；
- 历史笔记；
- 评论样本；
- 趋势数据；
- 视频创作样本；
- 账号诊断；
- 热点分析；
- 视频博主质量诊断；
- 受众模拟。

不设计用户自定义任意 asset schema，不设计通用文件树。

### 4.3 广义上下文视野

Context Access Layer 的默认理念是给 agent 尽可能完整的产品视野，而不是过度保守切分。

约束不是“少给信息”，而是：

- 只从已知产品资产读取；
- 每段 context 都有 asset ref；
- 记录 snapshot 和 content hash；
- 对过长内容做 summary/omitted 记录；
- 不读取任意文件路径或 secret。

### 4.4 用户确认写入

用户编辑和模型生成必须分开：

- 模型生成的是 generated snapshot 或 proposal；
- 用户编辑的是 editable content；
- agent 自动整理输入时只填草稿，不静默覆盖已有资产；
- proposal 需要用户确认 apply/reject。

### 4.5 刷新安全

workflow 执行不应依赖前端连接。

当前约定：

- POST 创建 run；
- 后端 worker 执行；
- 前端观察状态；
- SSE / polling 只负责观察，不负责启动执行；
- run、stage result、stage error、input snapshot 必须持久化。

## 5. 信息架构

当前 UI 采用三列结构。

### 5.1 左侧：内容资产

左侧用于管理和选择创作者内容资产。

当前入口：

- 创作者档案；
  - 小红书主页；
  - 账号概况；
  - 历史笔记；
  - 评论样本；
  - 视频创作样本；
- 趋势数据；
- 图文素材；
- 视频素材；
- 分析结果；
- 选题库；
- 创作输出；
- 受众模拟。

### 5.2 中间：当前页面

中间展示当前资产或 workflow 的具体内容。

包括：

- 资产实例列表与详情；
- workflow 输入选择与输出；
- 分析历史详情；
- 选题详情；
- agent conversation；
- 帮助内容。

### 5.3 右侧：能力资产

右侧用于发起 workflow 调用和查看能力资产。workflow 调用入口由 enabled workflow asset 的 `callBinding` 生成；当工作区能力资产尚未加载完成时，前端显示内置主 workflow 入口作为保底。

当前入口：

- 账号诊断；
- 热点分析；
- 视频博主质量诊断；
- Skills；
- Agents；
- Workflows。

内置调用入口显示为账号诊断、热点分析和视频博主质量诊断。新设计或手动修改的 workflow 如果设置了 `callBinding`，也会作为额外入口出现在这里；它绑定的是现有产品执行类型，不是任意图执行器。

## 6. 核心资产模型

### 6.1 Workspace

当前前端隐藏 workspace 创建和切换，系统自动使用默认 workspace。

字段：

- `id`
- `name`
- `accountPositioning`
- `positioningVersion`
- `currentTopicId`
- `createdAt`
- `updatedAt`

产品含义：

- 当前顶层数据容器；
- 暂时不是正式用户管理机制；
- 后续仍可作为本地项目或创作者集合容器。

### 6.2 输入内容资产

输入内容资产是 workflow 的主要输入来源。

当前类型：

| 类型 | 用途 | 存储 |
| --- | --- | --- |
| 创作者档案 | UI 上层入口，不是单独数据库表；聚合小红书主页、账号概况、历史笔记、评论样本和视频创作样本 | 由下列 input asset 组合 |
| 小红书创作者主页 | 本地爬取后解析出的主页、笔记、评论、互动和封面引用 | SQLite JSON text + 关联 MediaAsset |
| 账号概况 | 创作者档案子类；账号/创作者定位，可用于多个 workflow | SQLite text |
| 历史笔记 | 创作者档案子类；账号历史内容、标题、数据表现 | SQLite text |
| 评论样本 | 创作者档案子类；评论区痛点和用户表达 | SQLite text |
| 视频创作样本 | 创作者档案子类；视频创作者背景、视频样本、运营备注 | SQLite text |
| 趋势数据 | 热点内容数据，当前通过 CSV/TSV 上传 | 文件落盘 + SQLite metadata/preview |
| 图文素材 | 主页截图、封面图、评论区截图、视觉参考 | 文件落盘 + SQLite metadata/derived JSON |
| 视频素材 | 样本视频、视频参考、后续视频诊断输入 | 文件落盘 + SQLite metadata/derived JSON |

创作者档案页需要展示一个组合概览，聚合当前选中的小红书主页、账号概况、历史笔记、评论样本和视频创作样本，并展示 ready/missing 状态。当前这是前端组合视图，不创建新的 `creator_dossier` 表，也不改变现有 input asset API。

能力：

- 列表；
- 详情查看；
- 新建；
- 显式保存；
- 另存为；
- 趋势数据上传和 preview；
- 小红书离线导入包上传，生成结构化主页资产和封面图文资产；
- workflow 运行前自动保存当前必要输入；
- 输入素材整理 agent 生成草稿。

资源管理页的选择规则：

- 左侧进入“创作者档案”或任意 input asset 子类时，不自动打开 workflow 当前默认选中的实例；
- 右侧详情区先显示空态，要求用户从左侧实例列表中显式选择，或点击新建；
- workflow 页面仍可以保留默认输入选择，用于直接运行；
- 资源管理页的显式选择和 workflow 输入默认值是两个不同概念，避免用户以为进入资源页就已经在编辑某个资产。

媒体资产当前实现：

- 上传；
- 列表；
- 详情预览；
- metadata JSON 编辑；
- derived JSON 编辑；
- 用户备注；
- Context Access Layer overview；
- 本地视频预览抽帧；
- Qwen 图片理解；
- Qwen 视频理解；
- Qwen 图片生成；
- Qwen 视频生成。

图文素材和视频素材页采用“左侧列表选择，右侧展开详情”的交互：

- 上传图片 / 上传视频是列表中的动作项，点击后在右侧展开上传表单；
- 生成图文素材 / 生成视频素材是列表中的动作项，点击后在右侧展开生成表单；
- 选择已有素材时，右侧展示该素材详情、预览、理解草稿和保存入口；
- 不在右侧默认平铺上传和生成表单，避免管理页信息过载。

Qwen 理解结果先展示为草稿，用户确认后才写入 `MediaAsset.derived`。生成类 media skills 会把远程结果下载到本地受控 media storage，并登记为 `MediaAsset`。Demo 模式下媒体理解/生成必须明确标识为 demo；Live 模式才调用 Qwen。

当前仍不做：

- 独立 OCR / ASR 流水线；
- 本地上传视频文件直传给 Qwen；
- 视频平台链接抓取、平台数据抓取或长视频语义切片。

### 6.3 分析结果资产

由 workflow 生成并持久化。

当前 workflow type：

- `account_diagnosis`
- `trend_analysis`
- `video_creator_quality`

AnalysisRun 生命周期：

- `pending`
- `running`
- `completed`
- `partially_completed`
- `failed`

保存内容：

- workspace ID；
- workflow type；
- immutable input snapshot；
- stage results；
- stage errors；
- model metadata；
- review status：unreviewed / useful / rejected；
- user notes；
- timestamps。

编辑边界：

- `reviewStatus` 和 `userNotes` 是人工复盘元数据，可以通过 optimistic lock 显式保存；
- `inputSnapshot`、`stageResults`、`stageErrors` 和 `modelMetadata` 是不可变执行历史，前端只读展示。

### 6.4 选题资产

Topic 来源：

- 账号诊断；
- 热点分析；
- 手动创建。

字段：

- title；
- angle；
- associated pain point；
- why it fits；
- source analysis run；
- source workflow；
- status：candidate / selected / archived；
- timestamps。

能力：

- 保存到选题库；
- 设为当前选题；
- 编辑标题和角度；
- archive；
- 生成创作 Brief；
- 发送到受众模拟；
- 生成内容结构。

### 6.5 Draft / 创作 Brief / 内容结构资产

当前 Draft 表示由选题生成的创作 Brief、内容结构或用户继续编辑的草稿。系统通过 `kind` 区分：

- `content_brief`：选题对齐后的创作任务说明；
- `content_structure`：可继续编辑的内容结构。

Content Brief 字段包括：

- topicTitle；
- refinedAngle；
- targetReader；
- readerPain；
- contentPromise；
- corePoint；
- formatRecommendation；
- openingHook；
- argumentPath；
- materialNeeds；
- titleDirections；
- cta；
- risks；
- revisionSuggestions。

关键原则：

- generated snapshot 和 user editable content 分离；
- 每次生成都必须有数据库记录；
- 从 Brief 继续生成内容结构时，结构 Draft 的 input snapshot 必须保存 sourceBrief draft ID 和 Brief editable content；
- 不引入版本表；
- 不把 Draft 做成通用文档系统。

### 6.6 SimulationRun

受众模拟从一个 Topic 或手动输入 topic 开始。

保存内容：

- persona definitions；
- initial reactions；
- debate responses；
- synthesis；
- stage errors；
- input snapshot；
- review status：unreviewed / useful / rejected；
- user notes；
- timestamps。

要求：

- persona 是产品内置 runtime role，不是用户可配置 platform agent；
- 单个 persona 失败时保留部分结果；
- 可重新打开历史 simulation；
- `reviewStatus` 和 `userNotes` 可编辑，原始模拟结果和 model metadata 保持只读。

### 6.7 能力资产

能力资产是研发和产品维护者视角下可组合、可编辑、可新增的资产。

#### Skill

当前 skill 是产品内受控能力 contract + 可选后端 invoke 实现。

它不是任意代码工具沙箱。

字段包括：

- skill id；
- display name；
- category；
- purpose；
- trigger intents；
- required inputs；
- optional inputs；
- context policy；
- output schema；
- artifact effect；
- side effects；
- failure mode；
- composable with；
- implementation refs；
- status；
- version。

当前 skills 分两类调用入口：

- 可通过 `POST /api/skills/{id}/invoke` 直接调用：输入素材整理类 skills、Qwen 图片/视频理解与生成类 media skills；
- 通过产品入口调用并落库：`topic.refine_to_brief`、`draft.generate_structure`、`draft.generate_structure_from_brief`。

创作输出类 skill 不需要先开放成通用 invoke API。当前更重要的是保持 Topic / Draft 的产品语义：用户从选题触发 Brief 或结构生成，后端创建持久 Draft，generated snapshot 和 editable content 分离。

#### Agent

Agent = system prompt + 多个 skills + 默认 context policy。

当前内置 agent：

- Creator Dossier Curator；
- Account Diagnosis Strategist；
- Trend Opportunity Strategist；
- Video Creator Quality Analyst；
- Topic and Creative Output Editor；
- Audience Simulation Researcher；
- Capability Maker；
- Creator Dossier Formatter。

#### Workflow

Workflow = 多 agent、多 task 的产品任务计划。

当前 workflow asset 是能力目录和调用说明，不是前端可编辑 nodegraph。

核心字段：

- `workflowId`：稳定 ID；
- `displayName`：展示名称；
- `purpose`：用途；
- `entryAgentIds`：入口 agent；
- `agentPlan`：多级 task plan；
- `artifactEffect`：会产生或更新的产品资产；
- `callBinding`：可选调用注册，允许值为 `account`、`trend`、`video` 或空字符串；
- `status`、`version`、`source`、`updatedAt`。

`callBinding` 的含义是：把该 workflow asset 显示到右侧 workflow 调用区，并绑定到已有产品执行入口。它不代表前端可以编辑任意 nodegraph，也不代表后端会按任意 generated workflow plan 自动执行。

当前内置 workflow：

- Account Diagnosis Workflow；
- Trend Analysis Workflow；
- Video Creator Quality Workflow；
- Topic to Creative Output Workflow；
- Audience Simulation Workflow。

#### Conversation

Agent conversation 用于直接和某个 agent 对话。

当前能力：

- 创建 conversation；
- 发送 user message；
- 后端生成 assistant message；
- 支持 demo/live；
- 支持 queued/running/completed/failed 状态；
- 可携带当前选中的 Skill / Agent / Workflow 作为 context target；
- 可产生 AssetProposal。
- conversation 会作为内容资产出现在左侧“对话记录”入口，支持按 workspace 复盘消息、引用资产、model metadata 和 proposed actions；
- 重新打开 conversation 只读取已保存记录，不重新执行模型。
- conversation title 和 status 可编辑，用于重命名、归档和恢复；message content、context pack、model metadata 和 proposed actions 原始记录保持只读。

#### AssetProposal

Capability Maker 产生的变更建议。

当前能力：

- 保存 proposal；
- pending proposal 可编辑 title、description 和 proposed action JSON；
- Agent / Workflow proposal 的常见字段可用结构化表单编辑，并同步回 proposed action JSON；
- apply 前展示 diff preview，包括 operation、target asset、changed fields 和 validation errors；
- apply；
- reject。

Apply 规则：

- `skill.propose_definition` 创建或更新 Skill；
- `agent.propose_definition` 创建或更新 Agent；
- `workflow.propose_definition` 创建或更新 Workflow；
- payload 可用 `targetAssetId` 指向已有能力资产；
- 如果没有 `targetAssetId`，后端会用 `skillId` / `agentId` / `workflowId` 在当前 workspace 内查找已有资产，命中则更新，未命中则创建；
- stable id 不可通过 proposal 修改；
- 更新已有 builtin asset 时，该 workspace 内的资产会转为 generated override，避免后续 builtin seed 覆盖已经确认的修改；
- Agent proposal 的 `skillIds` 必须引用当前 workspace 已存在的 Skill；
- Workflow proposal 的 `entryAgentIds`、task `agentId` 和 task `skillIds` 必须引用当前 workspace 已存在的 Agent / Skill。

待增强：

- 前端已有 Agent skill checklist 和 Workflow task 表格作为辅助编辑；更复杂字段仍以 JSON editor 为主。

## 7. 关键用户流程

### 7.1 管理输入内容资产

目标：把创作者材料沉淀为可复用输入资产。

流程：

1. 用户在左侧选择资产类型。
2. 页面展示该类型的资产实例列表。
3. 用户选择已有实例或新建实例。
4. 用户直接编辑字段，或把原始文本粘贴给输入素材整理 agent。
5. agent 返回结构化草稿。
6. 用户确认后显式保存。

验收标准：

- 不应静默覆盖已有资产；
- 保存时显示 saving/saved/error；
- 中文内容必须 UTF-8 原样保存；
- 新建资产必须有名称字段；
- 保存后的每条资产实例都可被 workflow 显式选择；
- 进入资源管理页不应自动打开 workflow 当前默认选择的实例；
- 必须点击实例或新建按钮后，才显示对应详情/编辑器。

### 7.2 小红书创作者主页离线导入

目标：把本地获取的小红书主页数据整理为主平台可复用的结构化输入资产，同时保留笔记封面作为媒体资产。

边界：

- 小红书数据获取在主平台外部完成；
- 主平台不访问小红书、不抓取页面、不保存客户端提供的任意本地路径；
- 推荐使用 MediaCrawler 本地输出，经 `scripts/export_xhs_import_package.py` 整理成离线导入包；
- 旧 `xhs-profile-import/v1` JSON / Markdown 仍作为兼容导入路径。

离线导入包结构：

```text
xhs_import_package/
  xhs_creator_profile.json
  images/
    <note_id>/
      0.jpg
```

`xhs_creator_profile.json` schema 为 `xhs-creator-profile/v1`，至少应包含：

- `creator.displayName`；
- `creator.profileText`；
- `notes[].noteId`；
- `notes[].title`；
- `notes[].desc`；
- `notes[].metrics`；
- `notes[].comments[]`；
- `notes[].cover.relativePath`；
- `notes[].cover.caption`。

前端流程：

1. 用户进入内容资产 → 小红书创作者主页。
2. 用户选择离线导入包文件夹。
3. 前端本地读取 `xhs_creator_profile.json` 做导入前预览，不上传文件、不调用模型。
4. 预览展示账号名、笔记数、评论数、图片文件数、匹配封面数和缺失封面数。
5. 如果当前 workspace 已存在同名 `XHS {账号名} 创作者主页`，前端提示默认会更新已有资产。
6. 用户点击更新 / 导入，或选择另存为新主页。
7. 后端接收 profile JSON、图片文件和浏览器提供的相对路径，保存主页资产和封面媒体资产。
8. 导入完成后，前端选中新资产或更新后的资产，并完整展示后端 warning 列表。

后端要求：

- 只接受包内相对路径；
- 拒绝绝对路径和包含 `../` 的路径；
- 浏览器目录上传产生的公共顶层目录前缀应在前端剥离，使路径与 JSON 中的 `images/...` 匹配；
- 主页资产默认命名为 `XHS {小红书账号名} 创作者主页`；
- 封面媒体资产命名为 `笔记标题_封面`；
- 封面 caption 和 user notes 优先使用笔记正文；
- 重复导入同名主页时，默认更新同 workspace 下的已有 `xhs_creator_profile`；
- `saveAsNew=true` 时强制创建新主页资产；
- 封面媒体资产按名称复用，不重复创建同一封面。

详情页要求：

- 优先展示结构化摘要：账号名、笔记数、评论数、封面引用数和高互动前 5 条；
- 保留原始 JSON 编辑区，用于检查和必要的人工修正；
- warning 必须完整展示，不只展示第一条。

验收标准：

- `_tt` 导入包可生成 `XHS 秀***冰 创作者主页`；
- `QSheep` 导入包可生成 `XHS QSheep 创作者主页` 或脱敏 nickname 对应名称；
- 选择文件夹后无需上传即可看到本地预览；
- 导入后能看到结构化摘要和完整 warning；
- 重复导入默认更新已有主页资产，不增加重复列表项；
- 选择“另存为新主页”时会创建新资产；
- 封面媒体资产保留 `笔记标题_封面` 命名和正文 caption；
- 后端测试覆盖创建、默认更新、另存为新、路径逃逸拒绝；
- 前端测试覆盖本地预览、同名提示和 warning 列表。

### 7.3 账号诊断 workflow

目标：基于账号概况、历史笔记、评论样本生成账号诊断和选题。

输入：

- 账号概况实例；
- 历史笔记实例；
- 评论样本实例；
- demo/live mode。

执行：

1. 用户在右侧选择账号诊断。
2. 中间页按输入源逐项展示选择器和预览。
3. 用户点击生成。
4. 前端自动保存当前必要输入。
5. 后端创建 AnalysisRun。
6. 后端 worker 执行 workflow。
7. 前端观察 progressive stage results。
8. 结果进入分析结果历史。
9. 生成的 topic candidates 可保存到选题库。

输出：

- profile analysis；
- pain points；
- topics；
- stage errors；
- persisted AnalysisRun。

验收标准：

- 刷新后 run 不重复执行；
- 同一 idempotency key 不产生重复 run；
- stage result 成功后立即持久化；
- 保留当前可见的渐进渲染体验。

### 7.4 热点分析 workflow

目标：基于账号概况和趋势数据识别热点机会并生成选题。

输入：

- 账号概况实例；
- 趋势数据实例；
- demo/live mode。

执行要求：

- CSV 在模型调用前确定性解析和排序；
- 保留 top-50 engagement ranking 行为；
- graph state 不存完整 CSV；
- input snapshot 只保存 compact ranking 和 source material ID。

输出：

- trend pattern analysis；
- pain point analysis；
- topic generation；
- title variants；
- AnalysisRun。

### 7.5 视频博主质量诊断 workflow

目标：帮助创作者运营判断 AIGC 视频创作者质量和激励计划适配度。

输入：

- 账号概况实例；
- 小红书创作者主页实例，后端确定性派生 video creator evidence pack；
- 或兼容路径：视频创作样本实例；
- 可选图文/视频素材实例，用于提供已保存的 compact media understanding。

注意：

- XHS evidence pack 应包含 video note 数量、高互动内容、评论反馈、封面媒体引用、商业/剧本/技术探索信号和证据限制；
- 如果没有已确认的 video understanding，模型不得声称看过完整视频、镜头、剪辑、口型或音频；
- 文本化视频创作样本仍作为兼容输入；
- 如果用户先保存 Qwen 图片/视频理解结果，workflow 可以读取 compact media understanding；
- workflow graph state 只保存输入资产 ID、媒体资产 ID 和阶段结果，不保存完整 XHS JSON、完整媒体文件或完整 derived JSON；
- 本地上传视频可通过 ffmpeg 抽取预览帧，再由 Qwen 图片/视频理解 skill 生成结构化理解草稿；
- 当前不做真实视频链接抓取、平台数据抓取或完整本地视频直传；
- 因此诊断必须显式受 evidence pack 的证据限制约束，并在每个 stage result 中持久化 evidenceScope、evidenceConfidence、evidenceLimitations 和 recommendedNextEvidence；
- video quality stage 还必须持久化 cannotAssess，用于说明因为缺少视频/图片理解而不能可靠判断的维度。

输出：

- creator profile；
- video quality diagnosis；
- incentive fit judgement。

产品判断示例：

- 剧本驱动型：通常更适合激励计划；
- 商单驱动型：激励计划较难改变其行为；
- 技术探索驱动型：需要结合内容稳定性、受众反馈和创作动机分类讨论。

补充规则：右侧 workflow 调用区的“下期选题”不是账号诊断、热点分析或视频质量诊断的必填项。它只作为受众模拟的测试内容：用户可以手动输入，也可以从选题卡或选题库填入；demo 模式只在用户实际发起受众模拟时自动补样例。

### 7.6 选题库流程

目标：把 workflow 生成的候选选题沉淀为可复用 Topic。

流程：

1. 用户在分析结果中看到 topic cards。
2. 用户保存到选题库。
3. 用户可设为当前选题。
4. 用户可编辑 title 和 angle。
5. 用户可 archive。
6. 用户可调用 Brief 生成、结构生成或发送到受众模拟。

验收标准：

- topic 记录应保留 source workflow 和 source analysis run；
- 手动创建 topic 也应进入同一 Topic 模型；
- 当前选题可以被后续 workflow 引用。

### 7.7 创作输出流程

目标：从选题生成可执行的创作 Brief，再从 Brief 或 Topic 生成可继续编辑的内容结构。

流程：

1. 用户选择 Topic。
2. 用户点击生成创作 Brief。
3. 后端生成 `Draft(kind=content_brief)`。
4. 用户检查或编辑 Brief。
5. 用户从 Brief 继续生成内容结构。
6. 后端生成 `Draft(kind=content_structure)`，并在 input snapshot 中记录 sourceBrief。
7. generated snapshot 持久化。
8. 用户编辑内容时写入 editable content。

兼容行为：

- 用户仍可从 Topic 直接生成内容结构；
- 但推荐链路是 Topic → Content Brief → Content Structure。

验收标准：

- 不再存在 production fake structure；
- 每个生成结果必须有 Draft record；
- 用户编辑不覆盖 generated snapshot；
- Brief 和 Structure 通过 Draft.kind 区分；
- 从 Brief 生成结构时，结构生成应使用 Brief 的 editable content，而不是只使用 Topic 标题。

### 7.8 受众模拟 workflow

目标：对选题或草稿进行多 persona 反应模拟。

输入：

- saved Topic；
- 或手动输入 topic；
- 可选 Draft。

执行：

1. derive personas；
2. parallel initial reactions；
3. parallel debate responses；
4. synthesis；
5. finalize。

输出：

- persona definitions；
- initial reactions；
- debate responses；
- synthesis；
- SimulationRun。

验收标准：

- 单个 persona 失败不应导致全部结果丢失；
- previous simulation 可以重新打开；
- simulation history 出现在 workspace 内。

### 7.9 Agent conversation / Capability Maker

目标：通过对话生成 Skill / Agent / Workflow 或资产修改 proposal。

流程：

1. 用户进入 Skills / Agents / Workflows。
2. 用户点击 Capability Maker。
3. 对话自动携带 workspace broad context 和当前选中的 capability asset detail。
4. agent 返回解释和 proposed actions。
5. proposed actions 持久化为 AssetProposal。
6. 用户可以编辑 pending proposal。
7. 用户 apply 或 reject。

验收标准：

- Maker 必须看到 capability catalog；
- 如果用户从具体资产进入，必须带上当前资产 detail；
- capability proposal 必须给出可应用的完整 definition；
- apply 支持创建新能力资产和更新已有能力资产；
- 引用不存在的 skill / agent 时必须失败并持久化错误；
- apply/reject 状态必须持久化；
- 不应直接静默修改资产。

## 8. 非目标：批量能力

批量导入和批量 workflow 暂时不是产品目标。当前判断是：批量会显著增加输入校验、进度展示、错误恢复、结果对齐和测试维护成本，但现阶段真正需要验证的是单个创作者档案、单次 workflow 和 agent-assisted 资产整理是否足够顺滑。

当前产品应优先支持：

- 单个输入资产实例的新建、编辑、保存和另存为；
- 单个小红书创作者主页离线导入包上传；
- 单次 workflow 对当前选择资产运行；
- 历史结果重新打开和复盘；
- agent 帮用户整理输入资产草稿。

后端遗留 batch endpoint 可以暂时保留为兼容路径，但不在前端暴露，不进入近期路线，也不新增验收要求。

## 9. 模型调用要求

### 9.1 Provider

当前支持：

- Anthropic-compatible path；
- Qwen OpenAI-compatible path。

自动化测试默认使用 fake provider。

### 9.2 结构化输出

要求：

- 尽量使用 JSON response format；
- 支持 fenced JSON；
- 支持响应前后带说明文字时提取 JSON object；
- 对缺字段做 validation；
- 失败时生成 stage error 或 assistant failure message。

### 9.3 Context 控制

虽然 Context Access Layer 倾向 broad context，但 workflow node 仍应避免把完整 workspace 无脑传给每个模型调用。

要求：

- workflow node 只接收该 stage 必要上下文；
- maker/conversation 可以接收 broad workspace context；
- 每次 context pack 应可审计；
- full source material 不放入 graph state，只通过 ID 和 snapshot 连接。

## 10. 数据持久化要求

SQLite 保存：

- workspace；
- input asset metadata/text；
- analysis runs；
- stage results/errors；
- topics；
- drafts；
- simulation runs；
- skills；
- agents；
- workflows；
- conversations/messages；
- asset proposals；
- graph checkpoints；
- idempotency keys / execution mapping。

磁盘保存：

- uploaded trend CSV 文件。

不保存：

- 客户端传入的任意文件系统路径；
- 模型 API key 到前端；
- 任意用户上传文件树；
- 通用代码执行结果。

## 11. API 产品要求

API 应保持产品语义，不暴露 LangGraph 内部术语。

前端不应看到：

- graph node；
- thread；
- checkpoint；
- LangGraph run。

前端应看到：

- AnalysisRun；
- SimulationRun；
- ActivityEvent；
- stage result；
- status；
- asset；
- proposal。

当前 API 请求使用相对路径 `/api/...`，便于后续 VPS 反代。

## 12. Demo / Live 模式

### Demo 模式

要求：

- 提供接近原始 HTML 原型的默认样例；
- 不依赖真实模型；
- 适合快速演示完整链路；
- 不应出现 production fake 资产污染真实路径。

### Live 模式

要求：

- 通过后端 provider 调用模型；
- API key 只存在后端环境；
- 失败有明确错误状态；
- conversation / workflow 结果持久化。

## 13. 非目标

当前明确不做：

- 用户账号系统；
- 多租户和组织管理；
- 权限系统；
- sharing/collaboration；
- cloud object storage；
- arbitrary file editing；
- generic file tree；
- vector database；
- plugin marketplace；
- MCP；
- VS Code clone；
- 用户侧 workflow nodegraph editor；
- 任意代码工具调用。

## 14. 当前已知限制

1. 视频博主质量诊断优先使用小红书创作者主页派生的 compact evidence pack，兼容文本样本；可读取已保存的 compact media understanding，但不自动抓取或解析视频链接。
2. 图文/视频素材已经接入 Qwen 理解、生成和本地视频预览抽帧；仍没有独立 OCR、ASR、平台抓取或长视频语义切片。
3. Skills 是受控产品能力，不是任意代码工具；formatter skills 与 media skills 可直接 invoke。
4. Workflow assets 不是可视化 nodegraph editor。
5. Conversation 后端执行是 in-process task，不是完整 durable job queue。
6. SSE 是 observation replay，不是完整 durable event log。
7. AssetProposal 已支持 pending 状态下编辑后 apply，并对 skill / agent / workflow proposal 做基础字段和引用校验；apply 前已有后端 diff preview，但前端仍主要是 JSON editor，不是表单化编辑器。
8. qwen 结构化输出已有 operation-level 根字段校验，仍需要更多真实响应 fixture 加固。
9. 批量能力已从当前产品目标移除；后端遗留 batch endpoint 暂时只作为兼容路径。

## 15. 成功指标

当前阶段建议用内部产品指标，而不是商业指标。

### 15.1 资产沉淀指标

- 每次 workflow 运行前必要输入均有持久资产；
- 每次生成结果均有 AnalysisRun / Topic / Draft / SimulationRun 记录；
- 刷新后可以恢复历史结果。

### 15.2 workflow 稳定性指标

- 重复提交不产生重复 run；
- 中断连接不影响后端执行；
- stage failure 可被持久化和重新查看；
- fake provider 自动化测试稳定通过。

### 15.3 可维护性指标

- App.tsx 继续拆分；
- 新增 workflow 时复用产品资产模型；
- 新增 skill/agent/workflow 时进入能力资产 catalog；
- 上下文输入有可审计 context pack。

## 16. 近期优先级

### P0：当前版本 close 前

- 保持前后端测试通过；
- 保持 README、PRD、产品设计和 XHS 导入文档一致；
- 继续拆分前端页面组件，降低 `App.tsx` 复杂度；
- 明确所有 fake / demo / live 边界。

### P1：真正接入 API 后的稳定化

- qwen live workflow smoke test；
- 更多真实模型响应 fixture；
- AssetProposal diff 预览和更细前端校验；
- conversation message 显式 idempotency key；
- workflow 输入区更清晰地展示 XHS 创作者主页摘要和派生输入关系。

### P2：下一阶段产品能力

- 更强的输入素材整理 agent；
- 更多真实视频理解样本和脱敏 fixture；
- 更多产品特定 workflow；
- capability assets 的内部编辑工具。

## 17. 验收清单

一个版本可以认为符合本 PRD，当且仅当：

- 默认 workspace 可自动进入；
- 左侧内容资产可管理；
- 内容资产页进入后不自动打开默认实例，用户必须显式选择或新建；
- 小红书创作者主页可通过离线导入包导入、预览、更新和另存为新资产；
- 图文/视频素材页的上传和生成入口从左侧列表进入，并在右侧展开；
- 右侧 workflow 可运行；
- 账号诊断、热点分析、视频质量诊断、受众模拟结果可持久化；
- 生成 topic 可进入选题库；
- topic 可进入 Draft 和 Simulation；
- capability catalog 可查看；
- maker conversation 可携带 catalog 和当前资产详情；
- proposal 可保存并 apply/reject；
- demo 模式不依赖模型；
- live 模式不暴露 API key 给前端；
- 刷新不会导致重复执行；
- 前后端测试通过。

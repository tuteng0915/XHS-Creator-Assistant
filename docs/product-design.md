# 创作者工作区产品设计说明

> 当前公开产品采用创作者聚焦版：单一左栏、账号档案切换和一条连续创作链路。原有左右两列“内容资产 + 能力资产”工作台被保留为 `?internal=1` 内部调试界面，不再作为普通用户的信息架构。热点分析、视频质量诊断、能力资产编辑和多模态实验入口均从公开导航撤下，但实现未删除。完整迁移设计见 `docs/creator-focused-v2-execution-manual.md`。

更新日期：2026-08-24

本文档说明当前产品的功能、设计思想和核心抽象。它不是迁移计划，也不是通用 agent 平台规格。

## 1. 产品定位

创作者工作区是一个面向创作者运营和内容策划的内部共创工具。它用来管理创作者材料，运行产品化分析 workflow，沉淀选题、草稿和受众模拟结果，并通过一组可组合的 skill / agent / workflow 资产扩展能力。

这个产品的重点不是让用户搭建通用 agent，而是把创作者运营中反复出现的工作沉淀为可复用资产和可控 workflow。换句话说，我们不是在做一个“通用自动化平台”，而是在做一个围绕创作者材料、分析、选题和模拟的专用工作区。

当前它主要解决五类问题：创作者材料分散难复用；账号诊断、热点分析、视频质量判断、选题和受众模拟之间缺少资产连接；原型时代的前端临时状态刷新后丢失；LLM 调用需要更可控的输入、输出、持久化和失败记录；后续新增能力不能继续堆在单个页面里，需要用内容资产和能力资产组织。

## 2. 关键设计思想

### 2.1 资产优先

所有重要输入和输出都应该成为资产，而不是只存在于一次页面状态中。小红书创作者主页、账号概况、历史笔记、评论样本、视频创作样本、趋势数据、图文/视频素材、分析结果、选题、草稿和受众模拟，都应该有数据库记录或受控文件记录。当前 UI 把小红书创作者主页作为“创作者档案”的上层结构化入口，账号概况、历史笔记、评论样本和视频创作样本作为它的子视图或兼容输入资产；底层数据库类型暂保持独立，便于兼容已有 workflow 逻辑。

这个设计带来的直接收益是：刷新后可以恢复，历史分析可以重新打开，选题和草稿可以复用，后续 agent 也可以读取已有 context，而不是依赖用户反复粘贴。

### 2.2 内容资产和能力资产分离

产品里有两类资产。内容资产是用户的创作者材料、workflow 输出和可复盘的生成记录，包括创作者档案（小红书主页、账号概况、历史笔记、评论样本、视频创作样本）、趋势数据、图文素材、视频素材、分析结果、选题库、创作输出、受众模拟和对话记录。能力资产则是我们维护产品能力的方式，包括 Skills、Agents、Workflows 和 Asset proposals。Agent conversations 由能力资产触发，但保存后在左侧作为内容资产入口复盘。

用户主要管理内容资产；产品内部逻辑和研发维护者把能力资产视为可组合、可新增、可修改的产品能力目录。当前不会把能力资产开放成通用 workflow editor，也不会把用户界面做成通用 agent builder。

创作相关对象需要明确分层：生成 Brief、生成结构、改写、润色、基于模拟反馈修订，这些“会创作、判断或改写”的动作属于能力资产；生成出来的 Brief、内容结构和后续正文草稿属于内容资产。前端可以在 Topic 页面提供快捷按钮，但这些按钮本质上是在调用能力资产。

### 2.3 产品特定，不做通用平台

所有抽象都应该围绕创作者运营和内容生产，比如账号诊断、热点分析、视频博主质量诊断、选题生成、内容结构生成、受众模拟、输入素材整理，以及图文/视频素材理解与生成。

因此当前系统明确不是通用文件系统、VS Code clone、plugin marketplace、通用 agent builder、用户侧 workflow nodegraph editor 或任意代码执行平台。这些边界很重要，因为它们防止产品抽象被拉向过宽的平台方向。

### 2.4 Broad context，但要可审计

Context Access Layer 的默认理念不是过度保守地少给信息，而是让 agent 对话和 maker 类 agent 获得尽可能完整的 workspace 视野。我们宁可提供更全局的产品上下文，也不希望 agent 因为缺少关键材料而做出狭窄判断。

但 broad context 不等于无边界。系统只读取产品内登记过的资产，每个 context item 都要有 asset ref，长文本需要记录 summary / omitted 信息，workflow graph state 不保存完整源材料，也不能读取任意本地路径或把 secret 放进 context。更具体地说，maker / conversation 可以拿 broad workspace context，而 workflow node 只拿当前 stage 需要的输入；graph state 保存 ID 和 compact snapshot，而不是完整 workspace。

### 2.5 用户编辑和模型生成分离

模型输出不应该静默覆盖用户内容。模型生成的是 generated snapshot、draft 或 proposal，用户编辑的是 editable content。Qwen 图片/视频理解结果先作为草稿展示，用户确认后才写入 `MediaAsset.derived`；Capability Maker 生成的是 AssetProposal，用户 apply/reject 后才生效；Draft 的 generated snapshot 和用户 editable content 也分开保存。

资产编辑遵守同一边界：用户可编辑标题、名称、备注、editable content、proposal JSON、对话 title/status 等管理字段；AnalysisRun 和 SimulationRun 还提供 `reviewStatus` 与 `userNotes` 作为人工复盘元数据。AnalysisRun input snapshot、stage results、SimulationRun 原始结果、conversation messages、context pack 和 model metadata 是执行历史，保持只读。

### 2.6 workflow 执行必须 refresh-safe

workflow 不由 SSE 连接启动。当前执行模型是：前端 POST 创建 run，后端 worker 独立执行，前端通过 SSE / polling 观察，run、stage result、stage error 和 input snapshot 都持久化。这样可以解决原始 HTML 原型里“页面连接即执行、刷新难恢复”的问题。

## 3. 当前功能地图

### 3.1 内容资产管理

当前左侧内容资产包括这些入口。创作者相关输入不再完全平铺，而是先进入“创作者档案”，再在页面内切换小红书主页、账号概况、历史笔记、评论样本和视频创作样本。

| 资产 | 当前能力 | 主要用途 |
| --- | --- | --- |
| 创作者档案 | 上层入口；内含小红书主页、账号概况、历史笔记、评论样本、视频创作样本五个子类 | 管理同一创作者的结构化主页和兼容输入 |
| 小红书创作者主页 | 列表、详情、编辑、本地 fixture 导入 | 账号诊断和视频质量诊断的结构化主页输入 |
| 账号概况 | 创作者档案子类；列表、详情、新建、编辑 | workflow 的账号/创作者定位输入 |
| 历史笔记 | 创作者档案子类；列表、详情、新建、编辑 | 账号诊断、声音指纹、内容结构判断 |
| 评论样本 | 创作者档案子类；列表、详情、新建、编辑 | 受众痛点提取 |
| 视频创作样本 | 创作者档案子类；列表、详情、新建、编辑 | 视频博主质量诊断 |
| 趋势数据 | 上传 CSV/TSV、preview、确定性 top-50 ranking | 热点分析 |
| 图文素材 | 上传、预览、metadata/derived 编辑、Qwen 理解/生成 | 主页截图、封面、视觉参考 |
| 视频素材 | 上传、预览、抽帧、Qwen 理解/生成 | 视频质量诊断补充材料 |
| 分析结果 | 历史列表、重新打开、查看 input snapshot / stage results、编辑人工复盘状态和备注 | 持久化 workflow 输出 |
| 选题库 | 保存、编辑、选择、归档、查看来源与 generated snapshot、调用 Brief/结构生成能力、发送到受众模拟 | 复用选题资产 |
| 创作输出 | 查看和编辑创作 Brief、内容结构；区分 editable content、generated snapshot 与 input snapshot；从 Brief 继续生成结构；发送到受众模拟 | 保存创作类能力的产物 |
| 受众模拟 | 历史列表、重新打开、查看 personas / reactions / synthesis、编辑人工复盘状态和备注 | 复盘受众反馈和内容策略 |
| 对话记录 | 列表、重新打开、重命名、归档/恢复、查看消息、引用资产、model metadata 和 proposed actions | 复盘 Agent / Maker / formatter 对话生成历史 |

创作者档案页面现在提供一个组合概览，用显式打开的资产实例生成 loose / structured dossier 视图。这里要区分两个状态：workflow 可以保留默认输入选择，方便直接运行；资源管理页不能因此自动打开某个实例，否则用户会误以为自己正在编辑 QSheep 或其它默认样例。进入创作者档案或任意子类时，右侧先显示空态；用户必须点击左侧实例或点击新建后，才进入详情和编辑。这个概览只是前端聚合，不是新的数据库实体；底层 input asset type 和 API 仍保持独立，等产品验证后再决定是否增加真正的 `creator_dossier_id`。

输入素材整理已经从纯前端逻辑迁到后端 skill invocation。用户可以直接粘贴材料，由 Creator Dossier Formatter agent / formatter skills 整理成对应的创作者档案子资产草稿。当前 formatter 是确定性代码实现，适合稳定生成字段；如果后续需要更强理解能力，可以把 formatter skills 切到模型调用，但仍然保持“返回草稿，用户确认后保存”的原则。

### 3.2 媒体资产和 Qwen 多模态

媒体资产当前支持上传图片和视频，文件由后端受控落盘，SQLite 保存 metadata、derived JSON、用户备注和文件引用。图文/视频素材页提供预览、metadata/derived 编辑、Qwen 图片理解、Qwen 视频理解、Qwen 图片生成和 Qwen 视频生成。交互上，上传和生成不是右侧默认平铺表单，而是左侧列表中的动作项；点击“上传图片 / 上传视频”或“生成图文素材 / 生成视频素材”后，右侧才展开对应表单。点击已有素材时，右侧展示素材详情、理解草稿和保存入口。

本地上传视频不会被完整发送给 Qwen。当前做法是通过 ffmpeg 抽取少量预览帧，把帧保存为 `MediaAsset(type=image, sourceType=extracted_frame)`，再把这些帧作为图片输入发送给 Qwen。媒体理解结果进入 `MediaAsset.derived` 后，会通过 compact media context 被视频质量 workflow 复用。

当前仍不做独立 OCR pipeline、独立 ASR pipeline、平台抓取、长视频语义切片，也不做本地完整视频直传 Qwen。

## 4. 当前 workflow

### 4.1 账号诊断

账号诊断支持两种输入路径。优先路径是使用创作者档案里的结构化小红书主页资产，它保留笔记、评论、互动数据和封面引用；后端会从该资产派生账号定位、历史笔记摘要和评论样本快照。兼容路径仍然是创作者档案里的账号概况、历史笔记和评论样本。每次运行只处理当前选择的一组输入资产。账号诊断已经接入 LangGraph，并保留账号画像分析和评论痛点分析的并行执行。前端仍能看到 progressive rendering，后端会持久化 stage result 和 stage error，最终结果进入 AnalysisRun 历史。

右侧 workflow 调用区的“下期选题”是可选输入，只用于受众模拟。运行账号诊断、热点分析或视频质量诊断时不会要求填写，也不会在 demo 运行时隐式补入；只有用户点击受众模拟时才会读取或在 demo 模式下补入样例。

### 4.2 热点分析

热点分析基于账号概况和趋势数据，识别热点机会并生成选题。CSV/TSV 会在模型调用前确定性解析和排序，并保留 top-50 engagement ranking 行为。graph state 不保存完整文件，input snapshot 只保存 compact ranking 和 source material ID。它已经接入 LangGraph，并与账号诊断共享产品级 execution / persistence 接口，但不会被强行合并成一个 oversized generic graph。

### 4.3 视频博主质量诊断

视频博主质量诊断用于帮助创作者运营判断 AIGC 视频创作者质量和激励计划适配度。输入包括账号概况实例，以及一个视频作者来源：优先使用小红书创作者主页实例，由后端确定性派生 video creator evidence pack；兼容路径是手动维护的视频创作样本实例。可选图文/视频素材实例用于补充已保存的 compact media understanding。判断重点包括创作者画像、视频质量、内容动机和激励计划适配度。

一个典型判断框架是：剧本驱动型通常更适合激励计划；商单驱动型较难通过激励计划改变行为；技术探索驱动型需要结合内容稳定性、受众反馈和创作动机判断。XHS evidence pack 会记录 video note 数量、高互动内容、评论反馈、封面媒体引用、商业/剧本/技术探索信号、evidenceScope、evidenceLimitations 和 recommendedNextEvidence。如果没有已确认的视频理解结果，模型必须按标题、正文、评论和封面等间接证据保守判断，不得声称看过完整视频。每个 stage result 都会持久化证据范围、证据置信度和证据限制；video quality 还会持久化 cannotAssess，明确哪些维度不能可靠评估。graph state 只保存输入资产 ID、媒体资产 ID 和阶段结果，不做平台抓取或完整视频直传。

### 4.4 创作 Brief / 内容结构 / Draft

选题后续不直接等同于“润色标题”或“写正文”。推荐链路是 Topic → 创作 Brief → 内容结构。创作 Brief 用来把选题转成可执行任务，明确目标读者、读者痛点、内容承诺、核心观点、开头钩子、论证路径、素材需求、标题方向、CTA 和风险。内容结构再从 Topic 或已确认的 Brief 生成，产出可继续编辑的结构化 Draft。

实现上，Brief 和内容结构都复用 Draft 表，通过 `kind` 区分：`content_brief` 和 `content_structure`。这里的 Draft 是内容资产的存储实现，不代表“生成 Brief / 生成结构”的能力本身。每次生成都必须产生 Draft record，generated snapshot 和 editable content 分离，并且不把 Draft 扩展成通用文档系统。从 Brief 继续生成结构时，新的结构 Draft 会在 input snapshot 中记录 sourceBrief draft ID 和 Brief editable content，避免丢失用户已经确认或修改过的创作意图。当前 Draft generation 仍是同步 endpoint；如果后续 live 结构生成变慢，可以迁移到 create-run/observe 模式。

### 4.5 受众模拟

受众模拟对 Topic 或 Draft 进行多 persona 反应模拟。流程是 derive personas、parallel initial reactions、parallel debate responses、synthesis、finalize。persona 是产品特定 runtime role，不是用户可配置 platform agent；单个 persona 失败时应保留部分结果；SimulationRun 会持久化并可重新打开。

## 5. Skill / Agent / Workflow 的含义

Skill 不应该只是 prompt 文本。当前产品里的 skill 是受控能力 contract，可选带后端 invoke 实现。一个 skill 应该描述稳定 ID、版本、产品目的、输入 schema、输出 schema、context policy、artifact effect、side effects、failure mode、可组合对象和 implementation refs。当前通过 `POST /api/skills/{id}/invoke` 直接调用的是 `input_asset.format_*` formatter skills 和 `media.understand_image`、`media.understand_video`、`media.generate_image`、`media.generate_video`。创作输出类 skills，例如 `topic.refine_to_brief`、`draft.generate_structure`、`draft.generate_structure_from_brief`，目前通过 Topic / Draft 的产品入口调用，生成物落到 Draft 内容资产。系统不支持任意代码工具调用。

Agent 是 system prompt、多个 skills 和默认 context policy 的组合。当前 agent 是产品角色，不是用户任意配置的 autonomous agent。典型 agent 包括 Creator Dossier Curator、Account Diagnosis Strategist、Trend Opportunity Strategist、Video Creator Quality Analyst、Topic and Creative Output Editor、Audience Simulation Researcher、Capability Maker、Creator Dossier Formatter 和 Media Generation Operator。

Workflow 是产品拥有的任务计划，可以理解为 multi-agent / multi-task 的产品流程，但当前不是用户可编辑 nodegraph。代码层可以用 LangGraph 实现 workflow 执行；前端只看到产品级 run、stage 和结果，不暴露 LangGraph thread、checkpoint、node 等术语。

PM 调优界面允许对 Agent 和 Workflow 做有限的结构化辅助编辑：Agent 可以通过 checklist 组合已有 Skills，同时保留手动 stable id 文本输入；Workflow 可以用 task 表格编辑 `agentPlan.tasks` 的 taskId、agentId、skillIds、dependsOn 和 parallel 标记，同时保留 JSON editor 作为高级入口。Agent 详情里的 skill 引用、Workflow 详情里的 entry agent、task agent 和 task skill 引用可以点击跳转到对应能力资产，便于检查组合关系。这个能力是为了调产品内置资产，不是通用 nodegraph builder。

Workflow asset 可以通过 `callBinding` 注册到右侧 workflow 调用区。当前允许的绑定只有 `account`、`trend`、`video`，分别对应已有的账号诊断、热点分析和视频博主质量诊断产品执行入口。这个绑定只表示“把某个 workflow asset 作为入口展示，并复用对应产品执行路径”，不表示系统已经能执行任意用户生成的 workflow graph。内置三个主 workflow 默认注册；新生成或手动修改的 workflow 如果设置了 `callBinding`，也会出现在右侧调用区。

Capability Maker 是当前维护能力资产的最小闭环。用户在 Skill / Agent / Workflow 页面描述需求，Maker conversation 会读取 capability catalog 和可选的当前资产详情，生成 AssetProposal。Proposal 在 pending 状态下可编辑 title、description 和 action JSON；Agent / Workflow proposal 还提供结构化表单，用于修改常见 definition 字段和 workflow tasks。apply 前由后端生成 diff preview，显示将创建或更新的目标资产、变更字段和 validation errors；apply 后可以创建新的 generated capability asset，也可以用 targetAssetId 或 stable id 命中已有资产并更新为 workspace-level generated override。内置 builtin 定义仍由代码 seed，但被 proposal 覆盖后的 workspace asset 会转为 generated，避免后续 seed 静默覆盖用户确认过的修改。

## 6. Context Access Layer

Context Access Layer 的职责是把 workspace 中的资产整理成模型可读 context pack。当前理念是：conversation / maker 需要 broad context，workflow node 需要 stage-specific context；context 要有 source refs，compact snapshot 要足够有用，同时不能把完整文件、本地路径或 secret 暴露给模型。

当前 context pack 覆盖 workspace profile、input assets overview、media assets overview、analysis history、topics、drafts、simulations、capability catalog 和 selected capability asset detail。媒体 context 会携带 compact `imageUnderstanding`、`videoUnderstanding`、`qwenUnderstanding` 和 `videoPreview`。

后续需要补的是 pack-level token/字符预算、included / summarized / omitted 的审计信息、provider/model budget hint，以及更稳定的截断策略。

## 7. Demo / Live 模式

Demo 用于无 API key 的本地演示和自动化测试。它不调用外部模型，但仍使用集成 persistence path，避免形成一条完全独立的假路径。Demo output 应该明显是 demo，不能污染真实 live 逻辑。

Live 通过后端模型 provider 调用，不在浏览器持有 API key。当前支持 Anthropic-compatible path、Qwen OpenAI-compatible path，以及 Qwen / DashScope media APIs。Qwen 文本模型会请求 JSON response format，并能从 fenced JSON、解释文字包裹 JSON、`data/result/output` 包裹和 OpenAI-compatible tool/function arguments 中提取结构化结果；随后仍按 operation 做必要根字段校验。

## 8. 当前可靠性设计

当前已经完成 POST 创建 AnalysisRun / SimulationRun、后端 worker 执行、SSE / polling 观察、idempotency key 防重复创建、stage result / error 持久化、startup resume unfinished runs、conversation assistant placeholder 状态记录、conversation message client key 去重，以及 provider failure 留下 assistant failure message。Conversation assistant message metadata 会记录 queuedAt、startedAt 和 completedAt，方便刷新后复盘单条回复的执行生命周期。

仍需增强的是 workflow worker SQLite claim / lease 和 conversation durable job。是否需要 durable event log 可以后续根据调试和审计需求再判断。

## 9. 非目标

当前明确不做认证、多租户、权限系统、分享协作、通用文件树、arbitrary file editing、cloud object storage、vector database、plugin marketplace、MCP、VS Code clone、用户侧 workflow nodegraph editor、任意代码执行平台、批量导入和批量 workflow。

## 10. 当前优先级

下一阶段建议先做真实 Qwen / workflow smoke test，然后继续补真实响应 fixture 和 action-type 级 proposal schema，并继续拆 `App.tsx`。OCR、ASR 和长视频切片是否值得做，应该等真实视频样本跑过当前抽帧方案后再决定。

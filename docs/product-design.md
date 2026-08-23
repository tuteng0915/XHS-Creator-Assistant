# 创作者工作区产品设计说明

更新日期：2026-08-13

本文档说明当前产品的功能、设计思想和核心抽象。它不是迁移计划，也不是通用 agent 平台规格。

## 1. 产品定位

创作者工作区是一个面向创作者运营和内容策划的内部共创工具。它用来管理创作者材料，运行产品化分析 workflow，沉淀选题、草稿和受众模拟结果，并通过一组可组合的 skill / agent / workflow 资产扩展能力。

这个产品的重点不是让用户搭建通用 agent，而是把创作者运营中反复出现的工作沉淀为可复用资产和可控 workflow。换句话说，我们不是在做一个“通用自动化平台”，而是在做一个围绕创作者材料、分析、选题和模拟的专用工作区。

当前它主要解决五类问题：创作者材料分散难复用；账号诊断、热点分析、视频质量判断、选题和受众模拟之间缺少资产连接；原型时代的前端临时状态刷新后丢失，也难以批量运行；LLM 调用需要更可控的输入、输出、持久化和失败记录；后续新增能力不能继续堆在单个页面里，需要用内容资产和能力资产组织。

## 2. 关键设计思想

### 2.1 资产优先

所有重要输入和输出都应该成为资产，而不是只存在于一次页面状态中。小红书创作者主页、账号概况、历史笔记、评论样本、视频创作样本、趋势 CSV、图片/视频素材、分析结果、选题、草稿和受众模拟，都应该有数据库记录或受控文件记录。当前 UI 把小红书创作者主页作为“创作者档案”的上层结构化入口，账号概况、历史笔记、评论样本和视频创作样本作为它的子视图或兼容输入资产；底层数据库类型暂保持独立，便于兼容已有 workflow 和批量导入逻辑。

这个设计带来的直接收益是：刷新后可以恢复，历史分析可以重新打开，选题和草稿可以复用，同一个 workflow 可以批量跑多组输入，后续 agent 也可以读取已有 context，而不是依赖用户反复粘贴。

### 2.2 内容资产和能力资产分离

产品里有两类资产。内容资产是用户的创作者材料和 workflow 输出，包括创作者档案（小红书主页、账号概况、历史笔记、评论样本、视频创作样本）、趋势 CSV 数据、图片素材、视频素材、分析结果、选题库、受众模拟和草稿 / 内容结构。能力资产则是我们维护产品能力的方式，包括 Skills、Agents、Workflows、Agent conversations 和 Asset proposals。

用户主要管理内容资产；产品内部逻辑和研发维护者把能力资产视为可组合、可新增、可修改的产品能力目录。当前不会把能力资产开放成通用 workflow editor，也不会把用户界面做成通用 agent builder。

### 2.3 产品特定，不做通用平台

所有抽象都应该围绕创作者运营和内容生产，比如账号诊断、热点分析、视频博主质量诊断、选题生成、内容结构生成、受众模拟、输入素材整理，以及图片/视频素材理解与生成。

因此当前系统明确不是通用文件系统、VS Code clone、plugin marketplace、通用 agent builder、用户侧 workflow nodegraph editor 或任意代码执行平台。这些边界很重要，因为它们防止产品抽象被拉向过宽的平台方向。

### 2.4 Broad context，但要可审计

Context Access Layer 的默认理念不是过度保守地少给信息，而是让 agent 对话和 maker 类 agent 获得尽可能完整的 workspace 视野。我们宁可提供更全局的产品上下文，也不希望 agent 因为缺少关键材料而做出狭窄判断。

但 broad context 不等于无边界。系统只读取产品内登记过的资产，每个 context item 都要有 asset ref，长文本需要记录 summary / omitted 信息，workflow graph state 不保存完整源材料，也不能读取任意本地路径或把 secret 放进 context。更具体地说，maker / conversation 可以拿 broad workspace context，而 workflow node 只拿当前 stage 需要的输入；graph state 保存 ID 和 compact snapshot，而不是完整 workspace。

### 2.5 用户编辑和模型生成分离

模型输出不应该静默覆盖用户内容。模型生成的是 generated snapshot、draft 或 proposal，用户编辑的是 editable content。Qwen 图片/视频理解结果先作为草稿展示，用户确认后才写入 `MediaAsset.derived`；Capability Maker 生成的是 AssetProposal，用户 apply/reject 后才生效；Draft 的 generated snapshot 和用户 editable content 也分开保存。

### 2.6 workflow 执行必须 refresh-safe

workflow 不由 SSE 连接启动。当前执行模型是：前端 POST 创建 run，后端 worker 独立执行，前端通过 SSE / polling 观察，run、stage result、stage error 和 input snapshot 都持久化。这样可以解决原始 HTML 原型里“页面连接即执行、刷新难恢复”的问题。

## 3. 当前功能地图

### 3.1 内容资产管理

当前左侧内容资产包括这些入口。创作者相关输入不再完全平铺，而是先进入“创作者档案”，再在页面内切换小红书主页、账号概况、历史笔记、评论样本和视频创作样本。

| 资产 | 当前能力 | 主要用途 |
| --- | --- | --- |
| 创作者档案 | 上层入口；内含小红书主页、账号概况、历史笔记、评论样本、视频创作样本五个子类 | 管理同一创作者的结构化主页和兼容输入 |
| 小红书创作者主页 | 列表、详情、编辑、批量导入、本地 fixture 导入 | 账号诊断和视频质量诊断的结构化主页输入 |
| 账号概况 | 创作者档案子类；列表、详情、新建、编辑、批量导入 | workflow 的账号/创作者定位输入 |
| 历史笔记 | 创作者档案子类；列表、详情、新建、编辑、批量导入 | 账号诊断、声音指纹、内容结构判断 |
| 评论样本 | 创作者档案子类；列表、详情、新建、编辑、批量导入 | 受众痛点提取 |
| 视频创作样本 | 创作者档案子类；列表、详情、新建、编辑、批量导入 | 视频博主质量诊断 |
| 趋势 CSV 数据 | 上传、preview、确定性 top-50 ranking | 热点分析 |
| 图片素材 | 上传、预览、metadata/derived 编辑、Qwen 理解/生成 | 主页截图、封面、视觉参考 |
| 视频素材 | 上传、预览、抽帧、Qwen 理解/生成 | 视频质量诊断补充材料 |
| 分析结果 | 历史列表、重新打开、查看 input snapshot / stage results | 持久化 workflow 输出 |
| 选题库 | 保存、编辑、选择、归档、发送到结构生成/受众模拟 | 复用选题资产 |
| 受众模拟 | 历史列表、重新打开 | 复用模拟结果 |

输入素材整理已经从纯前端逻辑迁到后端 skill invocation。用户可以直接粘贴材料，由 Input Asset Formatter agent / formatter skills 整理成对应资产草稿。当前 formatter 是确定性代码实现，适合稳定生成字段；如果后续需要更强理解能力，可以把 formatter skills 切到模型调用，但仍然保持“返回草稿，用户确认后保存”的原则。

### 3.2 媒体资产和 Qwen 多模态

媒体资产当前支持上传图片和视频，文件由后端受控落盘，SQLite 保存 metadata、derived JSON、用户备注和文件引用。图片/视频素材页提供预览、metadata/derived 编辑、Qwen 图片理解、Qwen 视频理解、Qwen 图片生成和 Qwen 视频生成。

本地上传视频不会被完整发送给 Qwen。当前做法是通过 ffmpeg 抽取少量预览帧，把帧保存为 `MediaAsset(type=image, sourceType=extracted_frame)`，再把这些帧作为图片输入发送给 Qwen。媒体理解结果进入 `MediaAsset.derived` 后，会通过 compact media context 被视频质量 workflow 复用。

当前仍不做独立 OCR pipeline、独立 ASR pipeline、平台抓取、长视频语义切片，也不做本地完整视频直传 Qwen。

## 4. 当前 workflow

### 4.1 账号诊断

账号诊断支持两种输入路径。优先路径是使用创作者档案里的结构化小红书主页资产，它保留笔记、评论、互动数据和封面引用；后端会从该资产派生账号定位、历史笔记摘要和评论样本快照。兼容路径仍然是创作者档案里的账号概况、历史笔记和评论样本。单次运行可以选择一个小红书主页，批量运行可以按多个小红书主页各创建一条账号诊断 run。账号诊断已经接入 LangGraph，并保留账号画像分析和评论痛点分析的并行执行。前端仍能看到 progressive rendering，后端会持久化 stage result 和 stage error，最终结果进入 AnalysisRun 历史。

### 4.2 热点分析

热点分析基于账号概况和趋势 CSV，识别热点机会并生成选题。CSV 会在模型调用前确定性解析和排序，并保留 top-50 engagement ranking 行为。graph state 不保存完整 CSV，input snapshot 只保存 compact ranking 和 source material ID。它已经接入 LangGraph，并与账号诊断共享产品级 execution / persistence 接口，但不会被强行合并成一个 oversized generic graph。

### 4.3 视频博主质量诊断

视频博主质量诊断用于帮助创作者运营判断 AIGC 视频创作者质量和激励计划适配度。输入包括账号概况实例，以及一个视频作者来源：优先使用小红书创作者主页实例，由后端确定性派生 video creator evidence pack；兼容路径是手动维护的视频创作样本实例。可选图片/视频素材实例用于补充已保存的 compact media understanding。判断重点包括创作者画像、视频质量、内容动机和激励计划适配度。

一个典型判断框架是：剧本驱动型通常更适合激励计划；商单驱动型较难通过激励计划改变行为；技术探索驱动型需要结合内容稳定性、受众反馈和创作动机判断。XHS evidence pack 会记录 video note 数量、高互动内容、评论反馈、封面媒体引用、商业/剧本/技术探索信号和证据限制。如果没有已确认的视频理解结果，模型必须按标题、正文、评论和封面等间接证据保守判断，不得声称看过完整视频。graph state 只保存输入资产 ID、媒体资产 ID 和阶段结果，不做平台抓取或完整视频直传。

### 4.4 内容结构 / Draft

内容结构生成从 Topic 开始，产出可继续编辑的 Draft。当前原则是每次生成都必须产生 Draft record，generated snapshot 和 editable content 分离，并且不把 Draft 扩展成通用文档系统。当前 Draft generation 仍是同步 endpoint；如果后续 live 结构生成变慢，可以迁移到 create-run/observe 模式。

### 4.5 受众模拟

受众模拟对 Topic 或 Draft 进行多 persona 反应模拟。流程是 derive personas、parallel initial reactions、parallel debate responses、synthesis、finalize。persona 是产品特定 runtime role，不是用户可配置 platform agent；单个 persona 失败时应保留部分结果；SimulationRun 会持久化并可重新打开。

## 5. Skill / Agent / Workflow 的含义

Skill 不应该只是 prompt 文本。当前产品里的 skill 是受控能力 contract，可选带后端 invoke 实现。一个 skill 应该描述稳定 ID、版本、产品目的、输入 schema、输出 schema、context policy、artifact effect、side effects、failure mode、可组合对象和 implementation refs。当前可直接 invoke 的主要是 `input_asset.format_*` formatter skills，以及 `media.understand_image`、`media.understand_video`、`media.generate_image`、`media.generate_video`。系统不支持任意代码工具调用。

Agent 是 system prompt、多个 skills 和默认 context policy 的组合。当前 agent 是产品角色，不是用户任意配置的 autonomous agent。典型 agent 包括 Account Diagnosis Strategist、Trend Opportunity Strategist、Video Creator Quality Analyst、Topic and Draft Editor、Audience Simulation Researcher、Capability Maker、Input Asset Formatter 和 Media Generation Operator。

Workflow 是产品拥有的任务计划，可以理解为 multi-agent / multi-task 的产品流程，但当前不是用户可编辑 nodegraph。代码层可以用 LangGraph 实现 workflow 执行；前端只看到产品级 run、stage 和结果，不暴露 LangGraph thread、checkpoint、node 等术语。

## 6. Context Access Layer

Context Access Layer 的职责是把 workspace 中的资产整理成模型可读 context pack。当前理念是：conversation / maker 需要 broad context，workflow node 需要 stage-specific context；context 要有 source refs，compact snapshot 要足够有用，同时不能把完整文件、本地路径或 secret 暴露给模型。

当前 context pack 覆盖 workspace profile、input assets overview、media assets overview、analysis history、topics、drafts、simulations、capability catalog 和 selected capability asset detail。媒体 context 会携带 compact `imageUnderstanding`、`videoUnderstanding`、`qwenUnderstanding` 和 `videoPreview`。

后续需要补的是 pack-level token/字符预算、included / summarized / omitted 的审计信息、provider/model budget hint，以及更稳定的截断策略。

## 7. Demo / Live 模式

Demo 用于无 API key 的本地演示和自动化测试。它不调用外部模型，但仍使用集成 persistence path，避免形成一条完全独立的假路径。Demo output 应该明显是 demo，不能污染真实 live 逻辑。

Live 通过后端模型 provider 调用，不在浏览器持有 API key。当前支持 Anthropic-compatible path、Qwen OpenAI-compatible path，以及 Qwen / DashScope media APIs。

## 8. 当前可靠性设计

当前已经完成 POST 创建 AnalysisRun / SimulationRun、后端 worker 执行、SSE / polling 观察、idempotency key 防重复创建、stage result / error 持久化、startup resume unfinished runs、conversation assistant placeholder 状态记录，以及 provider failure 留下 assistant failure message。

仍需增强的是 workflow worker SQLite claim / lease、conversation durable job、per-message idempotency key。是否需要 durable event log 可以后续根据调试和审计需求再判断。

## 9. 非目标

当前明确不做认证、多租户、权限系统、分享协作、通用文件树、arbitrary file editing、cloud object storage、vector database、plugin marketplace、MCP、VS Code clone、用户侧 workflow nodegraph editor 和任意代码执行平台。

## 10. 当前优先级

下一阶段建议先做真实 Qwen / workflow smoke test，然后加固 Qwen 结构化输出和真实响应 fixture；之后再处理批量导入 / 批量 workflow 体验、AssetProposal 编辑和 per-action schema validation，以及继续拆 `App.tsx`。OCR、ASR 和长视频切片是否值得做，应该等真实视频样本跑过当前抽帧方案后再决定。

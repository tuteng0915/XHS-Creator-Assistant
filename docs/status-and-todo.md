# 当前状态与 TODO

## 2026-09-25：受众模拟证据化

新受众分析改为可重叠的阅读视角，不再要求模型编造合计 100% 的受众比例。来源 ID 和原文引用会在本次模型输入中核验，并继续传入模拟；历史结果保持只读兼容。读者不再收到“为什么适合该选题”等创作策略，可以划走或不评论；第二轮只看到公开模拟评论，不足两条则跳过。总结定位为发布前预演，不承诺真实流量预测。

新增离线时序回测案例准备脚本及引用、防答案泄漏、沉默、重开和部分失败测试。实验设计、使用方式和待验证假设见 [受众模拟研究](audience-simulation-research.md)。真实模型对照尚未执行；角色数量、证据排序、交流轮次的增益仍待验证。本条替代下方旧记录中的“分群必须合计 100%”“按主观比例 Top 3 作为模拟依据”等描述。

后续方法研究已整理为 [few-shot 与评论互动设计](audience-simulation-methods.md)，以 Proxona 等原始文献为依据。待做：冻结教学示例和旧版基线，比较需求编码、内容—反应案例及选择策略，再验证包含自身上一轮状态的条件性交流。这些是候选优化，尚未实施，也没有效果提升结论。

本轮检查：后端 206 项、前端 98 项测试通过；两端 lint、前端 build 和 diff 检查通过。未执行付费模型调用或真实抓取，也未重新部署服务。

## 2026-09-23：第二轮体验迭代

已完成四组父子导航、左栏收窄、添加账号延迟创建和重复提交复用、粉丝/获赞指标适配、选题正文与置顶、独立受众分析及 Top 3 模拟来源、持久化对话式 AI 创作画布。6 个误创建的空档案已备份后清理；包含历史数据的档案保留。实现细节见 `creator-experience-iteration.md`。

待人工验收：真实抓取的账号统计字段、基于真实模型的受众分群质量、多轮创作体验。页面更新不会为旧离线包补造粉丝数，不自动发起抓取或付费模型调用。

当前检查结果：后端 183 项测试、前端 93 项测试通过；两端代码检查、前端构建通过。完整命令及页面检查记录见本轮执行文档。

## 2026-09-23：首轮创作者聚焦版 V2（以下为首轮记录）

当前正在把产品从开发者工作台收口为面向创作者的公开界面。已完成执行手册、单一左栏公开产品壳、账号档案选择/新建、默认用户到账号空间的数据库所有权关系，以及主页 URL 导入任务的前后端骨架与真实 MediaCrawler runner。公开入口只保留账号材料、账号诊断、分析历史、选题库、AI 创作和受众模拟；旧热点分析、视频质量诊断、Skills、Agents、Workflows 和多模态实验仍可通过 `?internal=1` 回归，不删除代码。

公开页面已增加账号概览、按笔记组织的封面卡片和正文/评论弹窗。导入默认 10 条，可调整为 20/50/100 条或全部可见笔记；诊断默认最近 10 条，可改为最近 7/30/90 天或全部已导入内容。范围由后端实际筛选并写入运行快照；日期缺失不纳入日期筛选。公开模式使用真实模型，选题新建和范围设置按需弹窗，创作输出使用文本字段编辑。旧 JSON/文件夹导入仍在内部工作台。

剩余验收：用本机真实浏览器完成一次主页 URL 导入（含扫码），验证平台返回数据、封面和完整创作链路。自动化测试覆盖任务持久化、重复提交、重启中断、导入包、范围筛选和笔记交互，不代表已经完成真实平台抓取。远程用户在网页内扫码、旧混合账号 Workspace 的自动拆分暂未实现；历史空间不自动搬迁，新增账号使用独立空间。

本轮验证：后端 174 项测试、前端 88 项测试、两端 lint、前端 build 和 diff 检查通过。浏览器使用临时数据库加载 `_tt` 离线包，确认 4 条笔记、4 张封面及正文/评论弹窗正常；完整命令见 V2 执行手册。只读检查当前 4 个历史 Workspace，未发现单个空间混有多个小红书昵称。

以下为上一版内部工作台基线（更新日期：2026-08-26），功能存在不代表有公开入口。

本文档只记录当前实现状态、明确限制和 TODO。产品设计思想和功能全貌见 `docs/product-design.md`；更细的 PRD 和验收标准见 `docs/product-requirements.md`。

## API 路径与 VPS 分享结论

前端业务请求已经使用相对路径：

```text
/api/...
```

也就是说，前端代码不会直接请求 `localhost:8000`。本地开发时，`frontend/vite.config.ts` 只把开发服务器里的 `/api` 代理到 `http://127.0.0.1:8000`。

如果要通过 VPS 分享给别人看，需要保证浏览器访问的同一个域名可以同时提供：

- 前端页面；
- `/api/...` 后端接口。

推荐部署形态：

```text
https://your-domain/
  -> 前端静态页面

https://your-domain/api/...
  -> FastAPI 后端
```

可以用 Nginx/Caddy 做反向代理，也可以后续让 FastAPI 直接挂载构建后的前端静态文件。当前仓库还没有加入部署基础设施。

## 已完成的主要实现

### 产品结构

- 已从单文件 HTML 原型迁移到 React + TypeScript + FastAPI + SQLite。
- 原始 `index.html` 保留为行为参考。
- 工作区目前前端隐藏创建/切换入口，自动使用默认 workspace。
- 左侧是内容资产；右侧是能力资产和 workflow 调用。
- 右侧 workflow 调用入口已经由 workflow asset 的 `callBinding` 生成，内置账号诊断、热点分析、视频博主质量诊断默认注册；新生成或手动修改的 workflow 可注册为额外入口，但仍绑定到已有产品执行类型。

### 内容资产

当前内容资产包括：

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
- 对话记录。

已实现：

- 资产实例列表；
- 资产详情编辑；
- 创作者档案组合概览，聚合用户显式打开的小红书主页、账号概况、历史笔记、评论样本和视频创作样本；
- 内容资产管理页进入后先显示空态，不自动打开 workflow 当前默认选择的 QSheep 或其它示例实例；
- 显式保存；
- workflow 运行前自动保存必要输入；
- Agent conversation / Maker conversation 会自动持久化，并在左侧“对话记录”作为内容资产入口复盘；
- 对话记录支持重命名、归档和恢复；消息、context pack、model metadata 作为执行历史保持只读；
- 分析结果和受众模拟支持人工复盘状态 `unreviewed/useful/rejected` 与备注编辑；input snapshot、stage results、模拟结果和 model metadata 继续只读；
- 小红书创作者主页在后端仍是独立 input asset type，但前端归入“创作者档案”；它可由本地 MediaCrawler fixture 导入，并可直接作为账号诊断输入；
- 历史分析结果 CSV 导出；
- 选题可调用创作 Brief 生成能力；Brief 和内容结构作为创作输出复用 Draft 表，通过 `kind` 区分；
- 选题和创作输出详情已按资产编辑体验拆分：用户可编辑字段独立展示，generated snapshot、input snapshot、来源和 model metadata 保持只读；
- 已支持从 Brief 继续生成内容结构，并在结构 Draft 的 input snapshot 中记录 sourceBrief；
- 输入素材整理 agent 草稿入口；
- 输入素材整理通过后端 `input_asset.format_*` skills 调用，不再是纯前端假整理。
- 图文/视频媒体资产基础层：
  - 上传图片/视频；
  - 文件由后端受控落盘；
  - SQLite 保存 metadata、derived JSON、用户备注和文件引用；
  - 前端支持列表、详情预览和显式保存；
  - Context Access Layer 已包含 `media_assets_overview`，并会携带 compact `imageUnderstanding` / `videoUnderstanding` / `videoPreview`；
  - Qwen 图片理解和视频理解可作为受控 media skills 调用；
  - Qwen 图片生成和视频生成可作为受控 media skills 调用；
  - 本地上传视频可通过 ffmpeg 抽取预览帧，帧会作为 `extracted_frame` 图文素材保存；
  - Qwen 理解结果会先作为草稿展示，用户确认后写入 `MediaAsset.derived`；
  - 生成类 media skills 会把远程结果下载到本地受控 media storage，并登记为 `MediaAsset`。
  - 图文/视频素材页中，上传和生成入口位于左侧列表，点击后在右侧展开；右侧不默认平铺所有操作表单。

当前媒体资产仍不包含：

- OCR / ASR 的独立流水线；
- 本地上传视频文件直传给 Qwen；
- 视频链接抓取、平台数据抓取或长视频语义切片。

### 示例数据

已命名的示例：

- `Qsheep 留学账号`
- `数字游民生活方式账号`
- `留学帖子数据合集`
- `留学评论区合集`
- `数字游民趋势.csv`
- `AIGC视频创作者激励计划`
- `AI短剧创作者样本`

其中数字游民账号概况来自原始 HTML 原型的默认输入。

### workflow

当前主要 workflow：

- 账号诊断；
- 热点分析；
- 视频博主质量诊断；
- 受众模拟。

已完成：

- workflow 创建 run 后由后端 worker 执行；
- workflow 创建支持 `idempotencyKey`，同一 workspace 下重复提交同一个 key 会返回同一个 run；
- SSE 只作为观察通道；
- 刷新后可重新打开历史 run；
- 账号诊断、热点分析、受众模拟已经接入 LangGraph；
- 视频博主质量诊断已按同一产品接口实现，支持小红书创作者主页派生 evidence pack，也兼容视频创作样本文本，并可选择已保存的图文/视频素材 compact understanding 作为补充上下文；
- 视频博主质量诊断结果页已强化证据边界展示：当缺少真实视频理解、图片理解或评论证据时，质量判断和激励适配会明确显示不可可靠评估项与建议补充证据；
- 视频博主质量诊断已用真实 Qwen live 路径回归 `_tt` 和 `QSheep` 两个小红书导入 fixture：两者均能完成 `creator_profile`、`video_quality`、`incentive_fit` 三个 stage；`_tt` 因没有 video 类型笔记，会保守保留 evidenceLimitations 和 cannotAssess；
- 视频博主质量诊断已新增不消耗 API 的 workflow fixture 回归测试：直接读取 `data/xhs-fixtures/_tt` 和 `data/xhs-fixtures/QSheep`，使用脱敏 Qwen stage output fixture 跑完整三阶段 workflow，覆盖真实 XHS 输入快照、证据边界、枚举/分数归一和 no-video 保守判断；
- 视频诊断 input snapshot 中的 XHS source 已做白名单清洗，只保留 `platform / fixtureCode / importedAt / crawler`，不把本地 `baseDir` 这类路径写入运行历史；
- 运行结果、stage 结果、错误和 input snapshot 会持久化。
- “下期选题”只用于受众模拟，不是账号诊断、热点分析或视频质量诊断的必填输入。
- 选题后的推荐链路已经从“直接生成结构”扩展为 Topic → Content Brief → Content Structure；Topic 直接生成结构仍保留为快捷兼容路径。

### 能力资产

当前能力资产包括：

- Skills；
- Agents；
- Workflows；
- agent conversation；
- Capability Maker agent；
- Creator Dossier Formatter agent；
- Topic and Creative Output Editor agent；
- AssetProposal apply/reject 流程。

当前定位：

- 用户侧主要查看和通过对话生成 proposal；
- 前后端和后端 seed 逻辑把它们当成可组合、可编辑、可新增的产品资产；
- Maker conversation 可以携带当前选中的 Skill / Agent / Workflow 详情作为 context target；
- Skills 已有受控的后端调用入口：`POST /api/skills/{skill_asset_id}/invoke`；
- 当前可直接调用或产品内调用的是产品内置输入素材整理类 skills、创作输出类 skills，以及 Qwen 图片/视频理解与生成类 media skills；
- 创作类生成动作属于能力资产，例如 `topic.refine_to_brief`、`draft.generate_structure`、`draft.generate_structure_from_brief`；生成出的 Brief 和内容结构属于内容资产；
- Capability Maker 生成的 Skill / Agent / Workflow proposal 已可 apply 为 generated capability asset；命中已有 asset 时会更新为 workspace-level generated override；
- Agent / Workflow proposal 会校验引用的 skill / agent 是否存在；
- media skills 不是通用代码沙箱，也不是任意工具运行时；
- 不把用户界面做成通用 workflow 编辑器或通用 agent 平台。
- PM 已可以在 Skills 详情页直接编辑 Skill contract，并保存为 workspace-level generated override；
- 视频诊断相关 Skill 已有结构化 Rubric 编辑区，保存后会进入视频博主质量诊断 workflow 的真实模型调用上下文；
- 视频诊断 stage metadata 会保存当次使用的 `skillContext`，用于复盘 skillId、版本和 pmRubric。
- PM 已可以在 Agents 详情页直接编辑 Agent definition，包括 system prompt、skillIds、default context policy、version 和 notes；后端会校验引用的 skill 是否存在。
- PM 已可以在 Workflows 详情页直接编辑 Workflow definition，包括 entryAgentIds、agentPlan、artifactEffect、callBinding、version 和 notes；后端会校验引用的 agent / skill 是否存在。
- PM 已可以在 Skill / Agent / Workflow 详情页查看 workspace generated override 与 builtin definition 的差异，并用乐观并发保护恢复内置版本；恢复时保留 workspace 备注和启用状态。
- Agent 详情页的 skill 引用、Workflow 详情页的 entry agent / task agent / task skill 引用已经可点击跳转到对应能力资产，便于 PM 调试组合关系。
- Skill 详情页已经支持两类测试：`input_asset.format_*` 和 `media.*` 走受控 invoke；analysis/topic/draft/simulation/video 诊断类 Skill 走 dry-run，返回结构化样例输出，不写业务资产。

### 模型调用

当前后端模型 provider：

- Anthropic；
- Qwen / DashScope OpenAI-compatible API。

浏览器不再直接持有模型 API key。

当前 qwen 接入状态：

- 后端已支持通过 `.env.local` 配置 qwen OpenAI-compatible endpoint；
- agent conversation 的 live 路径已经走后端模型 provider；
- qwen 请求会尽量使用 JSON response format；解析器可从 fenced JSON、前后带解释文字的 JSON、`data/result/output` 外层包裹，以及 OpenAI-compatible `function_call/tool_calls.arguments` 中提取结构化 JSON；
- qwen 结构化解析会归一部分常见字段别名，例如 `pain_points -> painPoints`、`proposed_actions -> proposedActions`、`video_quality -> videoQuality`，归一后仍按 operation 校验产品 root schema；
- 图片理解和视频理解已通过 Qwen vision chat completions 接入为受控 skills；
- 本地上传视频理解会先抽取预览帧，再把帧作为图片输入发送给 Qwen；完整视频文件不会直接发送；
- 图片生成和视频生成已通过 DashScope async task 接入为受控 skills；
- 生成类 media skills 会下载返回的远程结果到本地 media storage，并登记为 `MediaAsset`；远程 URL 只作为 `externalUrl` 来源记录；
- 图文/视频素材页面已经提供 Qwen 理解与生成入口；
- 视频质量诊断 live 路径不会把完整媒体文件放入 graph state，只保存媒体资产 ID 和 compact immutable snapshot；
- 理解结果先展示为草稿，用户确认后才写回 `MediaAsset.derived`；
- `scripts/smoke_qwen_media.py` 可用于真实 API smoke test，不进入常规自动化测试；
- 自动化测试仍默认使用 fake provider，避免 CI 或本地测试消耗模型额度；
- 完整 workflow smoke test 可用 `scripts/smoke_live_workflows.py` 在不打开前端的情况下跑账号诊断、热点分析和视频博主质量诊断；默认 demo，不作为常规测试前置条件，`--mode live` 才会消耗模型额度。

最近一次真实 smoke 结果：

- `scripts/smoke_model_api.py --operation pain_points` 通过；
- `scripts/smoke_model_api.py --operation agent_chat` 通过；
- `scripts/smoke_qwen_media.py image-understand` 通过；
- 当前 `backend/.env.local` 已补齐 `ANTHROPIC_*` 与 `QWEN_*`，文本模型和 media skills 都可用；该文件已被 git ignore，不会提交。

## 当前 TODO

### 已完成：资产 proposal 编辑、校验与 Skill dry-run

- Capability Maker 已经可以拿到 capability catalog。
- Maker conversation 已经可以携带当前正在查看的具体 Skill / Agent / Workflow 作为 context target。
- Asset proposal 已支持 pending 状态下编辑 title、description 和 proposed action JSON 后再 apply。
- Agent / Workflow proposal 已支持结构化辅助编辑，并同步 proposed action JSON。
- Asset proposal 已支持 apply 前 diff preview；用户需要先查看将创建/更新的目标资产字段，再确认应用。
- Apply / reject 会持久化状态、结果和错误；非 pending proposal 不可重复编辑或应用。
- Skill / Agent / Workflow proposal 已有基础字段校验、stable id 不可变校验和引用存在性校验。
- Skill 详情页已经支持直接编辑 contract；视频诊断 Skill 已支持 Rubric 表单化编辑。
- Agent 详情页已经支持用 checklist 组合 Skills；Workflow 详情页已经支持用 task 表格编辑 agentPlan.tasks。
- Skill 详情页已经有最小 Skill Test 面板，可直接测试 `input_asset.format_*` 和 `media.*` 这类已有 invoke 实现的受控 Skill，也可 dry-run 分析/选题/草稿/模拟/视频诊断类 Skill。
- Skill dry-run 不会创建 AnalysisRun、Topic、Draft、SimulationRun 或 MediaAsset；它只验证当前 Skill contract 的输出形状。

仍需增强：

- 更细粒度的 proposal schema diff，例如按 nested field 展示 agentPlan.tasks 的变化。

### P1：输入素材整理继续模型化

当前已经有 Creator Dossier Formatter agent、formatter skills 和后端 invoke API。当前实现是确定性 formatter，适合稳定生成草稿字段。

后续如果需要更强整理能力，可以把这些 formatter skills 的实现从确定性代码切到模型调用：

- 接收目标资产类型；
- 接收用户粘贴的原始文本；
- 返回结构化草稿和置信说明；
- 用户确认后保存为对应内容资产。

### 非目标：批量导入与批量 workflow

批量能力暂时从产品路线中移除。当前产品优先做好单个创作者、单组输入资产的诊断质量、证据检查、可复盘历史和 agent-assisted 资产整理。后端遗留 batch endpoint 暂保留为兼容路径，但前端不暴露，也不继续扩展。

### 已完成：conversation 执行持久化增强

agent conversation 现在已经不是同步等待模型完成：

- 发送消息会先创建用户消息和 assistant 占位消息；
- 后端 in-process task 生成回复；
- 前端轮询观察 queued/running/completed/failed 状态；
- conversation summary 已包含派生 `executionStatus`；
- 同一 conversation 存在 queued/running assistant message 时，重复发送不会创建新的 user message 或重复执行；
- 每条前端发送的用户消息已携带 `clientMessageKey`；同一 conversation 下同一个 key 的重试会返回已有对话，不会重复创建 user/assistant message；
- provider 失败会留下 assistant failure message；
- assistant 占位消息会持久化 `queuedAt / startedAt / completedAt`，刷新后可以复盘单条回复的执行时间线；
- 每次 assistant 生成现在都有 `agent_conversation_jobs` 记录，保存 conversation、assistant message、用户输入、mode、status、attempt count 和错误；
- 应用启动时会恢复 queued/running conversation job；旧数据仍可按 assistant metadata 兼容恢复。

剩余问题：

- 这仍是单进程本地 worker，没有跨进程 claim/lease，因此不适合多进程部署或长时间任务队列。

### P1：qwen 结构化输出继续加固

- 继续保持 fake provider 作为默认自动化测试路径。
- 已支持 JSON response format、fenced JSON 和前后带解释文字的 JSON 提取。
- 已支持 `data/result/output` 外层包裹解包，以及 OpenAI-compatible `function_call/tool_calls.arguments` 提取。
- 已按 model operation 校验必要根字段和基本字段类型，例如 `painPoints` 必须是 list，`creatorProfile` 必须是 object。
- 图片/视频理解已要求结构化 JSON，并把 `imageUnderstanding` / `videoUnderstanding` 保存到 media asset derived JSON。
- 已加入脱敏 qwen fixture 测试，覆盖 wrapper、fenced JSON 和 snake_case/camelCase root alias 归一。
- 视频诊断 score 字段已加固：Qwen 偶尔把 0-100 分数输出为 `0~1` 小数时，会在视频 workflow schema 层归一为百分制整数，例如 `0.55 -> 55`。
- 视频诊断关键枚举字段已加固：`creatorType`、质量 `level`、`typeConfidence` 和 `recommendation` 会兼容常见中英文标签并归一到产品内部值；真正未知的 recommendation 会失败并进入 stage-level error，避免脏判断进入历史。
- 后续仍可增加 action-type 级 schema、字段级 repair 和真实响应 fixture。

### P1：前端结构继续拆分

- 已将 stage/result 纯展示组件从 `App.tsx` 拆到 `frontend/src/components/StageResultViews.tsx`。
- 已拆出 `WorkspaceShell`、媒体资产页、输入资产页、账号概况页、workflow 调用面板、workflow 输出面板和 conversation pending polling hook。
- 已拆出帮助内容模块、workflow stage view 纯工具、AssetProposalsPanel、AgentConversationPanel、AgentsPage、WorkflowsPage、ConversationsPage 和 AnalysisHistoryPage。
- 已拆出 TopicLibraryPage、DraftsPage、SimulationHistoryPage，并沉淀 CommonUi 的 EmptyState、ErrorBanner、JsonPreview。
- 已拆出 workspace 输入资产派生选择 hook、保存状态 hook 和 agent conversation 自动聚焦 hook；`App.tsx` 继续保留顶层 orchestration 和业务 action。
- 下一步继续拆：
  - workspace 初始加载 / 刷新 hook；
  - workflow 执行 action hook；
  - topic/draft action hook。

### P2：文案继续中文化

已完成主要导航、帮助和 workflow 输入区中文化。仍可逐步清理：

- 能力资产详情里的技术字段名；
- 测试 fixture 中的英文 demo 名称；
- 文档中历史英文术语。

保留术语：

- skill；
- agent；
- workflow；
- CSV；
- LangGraph；
- API。

### P3：VPS 分享与部署

当前暂不考虑部署。需要分享时再决定反向代理或 FastAPI 静态挂载。

## 当前明确限制

- Workflow assets 是产品能力目录和调用说明，不是前端可编辑的任意 nodegraph；`callBinding` 只负责把 workflow asset 注册到右侧调用入口，并复用现有产品执行路径。
- Skills 当前是产品内受控能力；formatter skills 与 media skills 支持直接 invoke，不支持任意代码工具调用。
- 视频博主质量诊断优先使用小红书创作者主页派生的 compact evidence pack，兼容文本化视频创作样本；如果用户先保存 Qwen 图片/视频理解结果，workflow 可以读取 compact media understanding，但不做自动视频抓取或本地视频直传。
- 视频诊断 stage result 已持久化 evidenceScope、evidenceConfidence、evidenceLimitations、recommendedNextEvidence；video quality 还会保存 cannotAssess，避免在缺少真实视频理解时假装评估镜头、剪辑、口型或音频。
- 图文/视频素材已经可以作为媒体资产保存；Qwen media skills 可理解图片、基于公开视频/帧 URL 或本地视频抽帧理解视频，并可生成图片/视频资产。
- 本地上传的视频文件不会直接发送给 Qwen；当前本地视频理解入口依赖 ffmpeg 抽帧。
- SSE 是可重连观察 replay，不是完整 durable event log。
- 安全边界、认证、权限、多用户部署暂不作为当前版本目标。

### 暂不考虑

- 认证；
- 多租户；
- 权限系统；
- 通用安全边界设计。

# PM 能力资产调优计划

本文档定义下一阶段的主线目标：把产品交给施琦姗作为产品经理使用时，她可以在前端调优 creator workspace 里的 skill、agent、workflow 细节，而不需要直接改代码。

这里的“调优”不是做通用 agent builder，也不是做任意 nodegraph 编辑器。目标是给产品内部维护者提供一条清晰、安全、可测试的前端路径，用来修改创作者运营产品里的能力资产，例如视频博主质量诊断 rubric、账号诊断 prompt、选题生成策略、agent system prompt，以及 workflow 的产品步骤说明。

## 1. 当前判断

当前系统已经具备基础能力资产模型：

- Skill 是受控能力 contract，包含输入、输出、context policy、artifact effect、failure mode、implementation refs 等字段。
- Agent 是 system prompt + 多个 skills + 默认 context policy 的组合。
- Workflow 是多 agent、多 task 的产品任务计划。
- Capability Maker 可以通过 conversation 生成 Skill / Agent / Workflow proposal，并在确认后 apply 为 generated workspace override。
- 部分 skills 已有直接 invoke 能力，包括输入素材整理 skills 和 Qwen 图文/视频理解与生成 skills。

当前缺口已经从“完全不能直接编辑能力资产”缩小为“还缺少更完整的 dry-run、diff、revert 和更友好的结构化控件”。PM 现在已经可以在前端打开 Skill、Agent、Workflow 并保存 workspace-level generated override；视频诊断相关 Skill 还提供了更友好的 Rubric 编辑区。保存后的 Rubric 会被视频博主质量诊断 workflow 的真实模型调用读取。

## 2. 产品原则

第一，能力资产必须可调，但不能变成通用平台。编辑界面应该围绕创作者材料、分析、选题、创作输出、受众模拟这些产品对象组织，而不是暴露任意文件、任意工具或任意代码执行。

第二，PM 修改的是 workspace-level override，不直接改 builtin seed。内置能力仍由代码维护；一旦 PM 在前端保存某个 builtin skill / agent / workflow，它在当前 workspace 中变成 generated override，后续 builtin seed 不再静默覆盖这份已确认修改。

第三，所有高风险内容都要结构化。视频评价 rubric、证据限制、输出 schema、context policy 等字段不能只藏在一段大 prompt 里。前端可以保留 JSON 高级编辑区，但核心字段必须能被 PM 看懂、修改和测试。

第四，测试要跟编辑靠近。PM 改完 rubric 或 prompt 后，应该能立刻用当前 workspace 里的内容资产跑一次 dry run，看到输入 context、模型输出、结构化解析结果和 validation error。第一阶段先做 Skill 级调试，再扩展到 Agent 和 Workflow。

第五，生成和编辑分离。Maker 生成 proposal，PM apply；模型输出保存为 generated snapshot，PM 编辑 editable content。能力资产调优也遵守这个原则：草稿、保存、应用、测试状态必须清楚。

## 3. 目标使用路径

### 3.1 修改视频质量诊断 rubric

PM 打开 Skills，选择 `analysis.video_quality` 或相关视频诊断 skill。右侧展示它的目的、输入、输出 schema、failure mode、context policy、implementation refs，以及一个专门的 rubric 编辑区。

她可以修改：

- 评价维度；
- 每个维度的判断标准；
- 剧本驱动型、商单驱动型、技术探索型等创作者类型的判定规则；
- 激励计划适配判断；
- 缺少真实视频理解时必须保守表达的规则；
- 输出 JSON 结构。

保存后，该 skill 变成当前 workspace 的 generated override。随后她可以选择一个小红书创作者主页、图文素材、视频素材或已有分析 run，执行 Skill test，检查输出是否符合预期。

### 3.2 调整 Agent

PM 打开 Agents，选择 Video Creator Quality Analyst。她可以看到该 agent 的 system prompt、绑定的 skills、默认 context policy 和最近 conversation。

她可以：

- 修改 system prompt；
- 添加或移除已有 skill；
- 调整默认 context policy；
- 从当前 agent 发起测试 conversation；
- 通过 Capability Maker 生成一个 agent 修改 proposal。

### 3.3 调整 Workflow

PM 打开 Workflows，选择 Video Creator Quality Workflow。她可以看到产品步骤：

```text
prepare_video_creator_evidence
-> profile_video_creator
-> diagnose_video_quality
-> assess_incentive_fit
```

她可以编辑每一步的：

- step name；
- agent；
- skill IDs；
- dependsOn；
- 是否 parallel；
- 输出资产说明；
- 是否注册为右侧 workflow 调用入口。

第一阶段不做拖拽画布，不做 loop，不做任意 DAG 运行时，只做结构化 task plan 编辑和保存。

## 4. 分阶段实施

### Slice 1：Skill 详情页可编辑

目标：PM 可以在前端编辑一个 Skill 的 contract，并保存为 workspace-level generated override。

范围：

- 后端新增 Skill definition update API；
- 前端 Skill 详情页增加“编辑 contract”模式；
- 支持编辑 display name、category、purpose、artifact effect、failure mode、version、trigger intents、required inputs、optional inputs、side effects、composable with、implementation refs、context policy JSON、output schema JSON、user notes；
- 保存时使用 expectedUpdatedAt，避免静默覆盖；
- 保存后刷新列表和详情；
- builtin skill 保存后变成 generated source。

不做：

- 不执行模型；
- 不做 rubric 专用 UI；
- 不做 diff/revert；
- 不做 workflow 执行变化。

验收：

- 打开 Skills，选择一个 skill，进入编辑，修改 purpose 或 output schema，保存后详情更新；
- stale expectedUpdatedAt 返回 conflict；
- 前端测试覆盖编辑并保存；
- 后端测试覆盖保存、source 转 generated、并发冲突。

### Slice 2：视频诊断 rubric 结构化编辑器

目标：让视频博主质量诊断相关 skills 不必只改 JSON，而是可以通过 PM 友好的 rubric 表单编辑。

范围：

- 为 `analysis.video_creator_profile`、`analysis.video_quality`、`analysis.incentive_fit` 识别 rubric schema；
- 在 Skill 详情页展示 rubric cards；
- 支持增删维度、编辑评分标准、证据限制和保守表达规则；
- 保存时仍写入 skill output schema / context policy / user notes 或 dedicated rubric 字段。

验收：

- PM 可以不用理解完整 JSON，也能修改视频评价规则；
- 保存后的结构仍能被模型 prompt 组装和测试读取。

### Slice 3：Skill test panel

目标：PM 修改 skill 后可以立即用 workspace 资产测试。

范围：

- Skill 详情页增加 Test 面板；
- 可选择输入资产、分析 run、topic、draft、media asset；
- 展示实际 context pack；
- 调用受控 `POST /api/skills/{id}/invoke` 或新增 dry-run endpoint；
- 展示 raw output、structured output、validation error、model metadata。

约束：

- 只测试产品内受控 skills；
- 不执行任意代码工具；
- live mode 失败必须清晰展示错误。

### Slice 4：Agent 可编辑

目标：PM 可以调整 agent system prompt、skill 组合和默认 context policy。

范围：

- 后端新增 Agent definition update API；
- 前端 Agent 详情页增加编辑模式；
- skill 组合从当前 workspace skill catalog 中选择；
- 保存为 generated override；
- 保留 Maker conversation 入口。

### Slice 5：Workflow task plan 可编辑

目标：PM 可以调整 workflow 的产品步骤和调用注册关系。

范围：

- 后端新增 Workflow definition update API；
- 前端 Workflow 详情页增加 task plan 编辑；
- 支持 task list、agent、skills、dependsOn、parallel；
- 继续支持 `callBinding`；
- 保存为 generated override。

不做：

- 不做拖拽 nodegraph；
- 不做任意 loop；
- 不做通用 executor。

### Slice 6：Diff / Revert / Version comfort

目标：降低 PM 调优风险。

范围：

- 显示当前 generated override 与 builtin/default 的差异；
- 支持恢复内置版本；
- 保存前显示关键字段 diff；
- 后续如果必要，再补轻量 version history。

## 5. 当前优先级

当前先做 Slice 1。原因是它能最快打通 PM 从前端调 Skill 的基础路径，并且复用现有数据库字段、repository replace_definition、AssetProposal 的 generated override 语义，不需要重做执行系统。

Slice 1 已完成。Slice 2 已完成第一版：视频诊断 Rubric 可以在 Skill 详情页编辑，并已经接入视频博主质量诊断 workflow 的真实执行上下文。Slice 3 已完成最小版：对当前后端支持直接 invoke 的 formatter / media skills，PM 可以在 Skill 详情页输入 JSON，选择 demo/live 并查看输出和 metadata。Slice 4 和 Slice 5 已完成第一版：Agent 和 Workflow 详情页可以直接编辑 definition，并保存为 workspace-level generated override。Slice 6 已完成第一版：Skill、Agent、Workflow 详情页可以查看当前 workspace override 与 builtin definition 的差异，并一键恢复内置版本。分析类 Skill 还不能单独 dry-run，仍需通过 workflow 测试。

## 6. 已完成落地

### Skill contract 编辑

后端已经提供 `PATCH /api/skills/{skill_asset_id}/definition`。它使用 `expectedUpdatedAt` 做乐观并发控制，保存后把当前 workspace 中的 Skill 标记为 `generated`，避免后续 builtin seed 静默覆盖 PM 调整。

前端 Skills 详情页已经支持编辑：

- display name；
- category；
- purpose；
- trigger intents；
- required / optional inputs；
- context policy JSON；
- output schema JSON；
- artifact effect；
- side effects；
- failure mode；
- composable with；
- implementation refs；
- version；
- user notes。

### 视频诊断 Rubric 编辑

对于以下 Skill，前端会额外显示“视频诊断 Rubric”编辑区：

- `analysis.video_creator_profile`；
- `analysis.video_quality`；
- `analysis.incentive_fit`。

当前 Rubric 存放在 Skill 的 `contextPolicy.pmRubric` 中，支持编辑：

- 创作者类型规则；
- 质量评价维度；
- 证据限制规则；
- 激励适配规则。

视频博主质量诊断 LangGraph workflow 在执行每个节点时，会按 stable skillId 读取当前 workspace 的 Skill 定义，把对应 `pmRubric` 放入该节点的模型输入。stage metadata 中也会保存 `skillContext`，包含 skillId、skillAssetId、skillVersion 和 pmRubric，方便复盘当次执行到底用了哪套规则。

### Skill Test 最小面板

Skill 详情页现在包含 `Skill Test` 面板。当前只覆盖后端已经有受控 invoke 实现的 Skill：

- `input_asset.format_*`；
- `media.*`。

PM 可以编辑 Input JSON，选择 demo 或 live，然后运行 `POST /api/skills/{skill_asset_id}/invoke`。结果会展示结构化 output 和 model metadata。对于 `analysis.*`、`topic.*`、`draft.*` 等暂时不能独立 invoke 的 Skill，前端明确显示 `workflow-only`，提示需要通过绑定 workflow 测试。

后续增强方向是补一个真正的 dry-run endpoint：它不写业务资产，只构造当前 Skill 所需 context，调用对应模型或确定性实现，并返回 raw output、structured output、validation error 与 context pack。

### Agent definition 编辑

后端已经提供 `PATCH /api/agents/{agent_asset_id}/definition`。它会校验 `skillIds` 必须来自当前 workspace 已存在的 Skill catalog；保存后把当前 Agent 标记为 `generated`。

前端 Agents 详情页已经支持编辑：

- display name；
- purpose；
- system prompt；
- skill IDs；
- default context policy JSON；
- version；
- user notes。

这个编辑器不是通用 agent builder，只是给 PM 调整产品内 Agent role、system prompt 和能力组合的受控入口。Capability Maker 对话入口仍然保留，用于通过自然语言生成修改 proposal。

### Workflow definition 编辑

后端已经提供 `PATCH /api/workflows/{workflow_asset_id}/definition`。它会校验：

- `entryAgentIds` 必须来自当前 workspace 已存在的 Agent catalog；
- `agentPlan.tasks[].agentId` 必须存在；
- `agentPlan.tasks[].skillIds[]` 必须存在；
- disabled workflow 不能注册 `callBinding`。

前端 Workflows 详情页已经支持编辑：

- display name；
- purpose；
- entry agent IDs；
- agent task plan JSON；
- artifact effect；
- call binding；
- version；
- user notes。

第一版仍然用 JSON 编辑 task plan，不做拖拽图、不做 loop、不做任意 executor。它的作用是让 PM 能调整当前产品 workflow 的结构说明和调用注册关系。

### Definition Diff / Revert

后端已经为三类能力资产提供对比和恢复接口：

- `GET /api/skills/{skill_asset_id}/definition-diff`
- `POST /api/skills/{skill_asset_id}/revert-definition`
- `GET /api/agents/{agent_asset_id}/definition-diff`
- `POST /api/agents/{agent_asset_id}/revert-definition`
- `GET /api/workflows/{workflow_asset_id}/definition-diff`
- `POST /api/workflows/{workflow_asset_id}/revert-definition`

diff 只比较能力定义字段，不把 `status`、`userNotes` 等 workspace 运营字段算作 builtin 差异。revert 使用 `expectedUpdatedAt` 做乐观并发控制，恢复 builtin definition，但保留当前 workspace 的用户备注和启用状态。Workflow revert 会同时恢复 builtin `callBinding`，因为它决定该 workflow 是否出现在右侧调用入口。

前端 Skill、Agent、Workflow 详情页已经增加 `Definition Diff` 面板。PM 可以按需加载差异，查看 changed fields、当前 definition 和 builtin definition，然后执行“恢复内置版本”。第一版不做完整 version history；后续如果 PM 调优频率变高，再补轻量版本快照。

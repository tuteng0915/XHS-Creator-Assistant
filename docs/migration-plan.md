# Incremental Migration Plan

本文给出把现有单文件 `index.html` 迁移到 React、TypeScript、FastAPI、SQLite、LangGraph 和 Server-Sent Events（SSE）的增量计划。

目标不是借迁移重新设计产品，而是在每个切片结束时都保持应用可运行，并逐步获得类型安全、服务端模型调用、workspace 持久化、可控工作流和失败恢复能力。

LangGraph graph 作为普通 Python 代码维护。需要调整工作流时直接修改和测试代码；本计划不围绕工作流是否可编辑增加额外产品层。

## 1. 迁移原则

### 1.1 行为基线

迁移期间，以下内容构成兼容性基线：

- 账号诊断和热点分析两个入口。
- demo/live 两种模式。
- 账号诊断的 profile、pain points、topics、structure 数据形状与显示内容。
- 热点分析的 trend analysis、pain points、topics、titles、structure 数据形状。
- CSV 粘贴与上传、按 `likes + collects` 排序并取 top 50 的当前规则。
- 从选题填入受众模拟的操作。
- 受众 persona、reaction、debate、synthesis 的阶段和字段。
- 逐阶段 loading、成功和错误反馈。
- 当前 prompts、模型参数、tool schemas、demo fixtures 和中文文案。

`docs/current-prototype.md` 已记录的已知不一致也属于基准证据。迁移切片不顺手修复它们；是否修复应作为独立产品变更，有单独验收。这样可以区分“架构迁移造成的回归”和“主动改变产品行为”。

### 1.2 原型永久保留

- 根目录 `index.html` 在全部迁移切片中保持只读，不作为 React 入口复用。
- React 项目使用自己的 `frontend/index.html`，避免覆盖原型。
- 开发与验收期间同时提供：

  ```text
  /legacy/  -> 原始 index.html
  /app/     -> React 应用
  ```

- 保存 `index.html` 的 SHA-256、关键 demo JSON fixture、DOM 语义断言和关键页面截图。
- 每个切片的端到端验收同时运行 legacy smoke test 和新应用测试。
- 最终切换默认入口后，`/legacy/` 仍保留为开发参考，不承接正式数据。

### 1.3 垂直切片规则

每个切片必须满足：

1. 合并后 legacy 和当时的新应用路径都能启动。
2. 只有通过该切片所需的层才改动；例如纯渲染迁移不同时引入数据库。
3. 新能力先通过独立 route、adapter 或 feature flag 接入，验证后再移除旧路径。
4. 所有跨层数据都有显式 schema；不把后端 JSON 当作无类型对象长期传递。
5. 同一切片先建立 characterization test，再改变实现。
6. 验收失败时可以回退 feature flag，而不需要恢复数据库或修改原型。

### 1.4 建议的代码边界

```text
index.html                         # 原型，只读参考
docs/
frontend/
  src/
    app/
    components/
    features/
      diagnosis/
      trends/
      topics/
      drafts/
      simulation/
      workspace/
    api/
    types/
    fixtures/
backend/
  app/
    main.py
    api/
    models/                        # Pydantic API contracts
    db/                            # SQLite schema/repositories
    services/                      # model client, CSV parser
    workflows/                     # ordinary Python + LangGraph graphs/nodes
    prompts/                       # versioned existing prompts
    sse/
  tests/
data/                              # runtime data; not committed
  app.sqlite3
  uploads/trends/
```

这只是代码组织，不是用户可见文件树。

## 2. 跨切片测试策略

### 2.1 测试层级

- **Legacy characterization**：Playwright 驱动 `index.html`，记录 demo 输入、按钮、阶段顺序和可见文本。
- **Frontend unit/component**：Vitest + React Testing Library 验证类型化 renderer 对同一 fixture 的输出。
- **Backend unit**：Pytest 验证 prompt context、CSV 解析、状态机和 repository。
- **API contract**：FastAPI/Pydantic response 与 TypeScript 类型 fixture 双向校验；字段增加可兼容，字段删除必须显式评审。
- **Workflow contract**：给固定输入和 fake model response，断言调用顺序、并行边界、prompt、schema 和下游输入。
- **E2E**：Playwright 验证 workspace → materials → analysis → topic → structure → simulation。
- **Recovery**：终止并重启后端进程，验证持久化状态和 SSE 重连。

### 2.2 固定 fixture

至少固定以下 fixture，内容直接来自原型：

- `SAMPLE`、`SAMPLE_RESULT`。
- `SAMPLE_TREND_POSITIONING`、`SAMPLE_TREND_POSTS`、`SAMPLE_TREND_RESULT`。
- `SAMPLE_SIMULATION`、`SAMPLE_SIMULATION_B`。
- 四个账号 prompts、两个热点 prompts、persona/reaction/debate/synthesis 动态 prompt 模板。
- 有效 CSV、TSV、中文表头 CSV、空 CSV、格式错误 CSV。
- 每个模型调用的有效响应、缺字段响应、HTTP 错误和 malformed JSON 响应。

fixture 可从原型复制到测试目录，但原型本身不改。

### 2.3 SSE 事件契约

从引入后台工作流开始，统一使用：

```text
run.created
stage.started
stage.succeeded
stage.failed
run.partial
run.succeeded
run.failed
heartbeat
```

每个事件至少包含：

```json
{
  "eventId": "...",
  "runId": "...",
  "runType": "account_diagnosis | trend_analysis | structure_generation | audience_simulation",
  "stageKey": "... or null",
  "status": "...",
  "sequence": 1,
  "occurredAt": "...",
  "data": {}
}
```

早期可以只在内存中发送；最后一个切片再保证断线重放和服务重启恢复。事件字段从首次发布后保持向后兼容。

## 3. Slice 1 — 冻结并记录原型

**主要改动层：测试与文档。** 不改变产品运行代码。

### 用户可见行为

- 用户继续直接运行现有 `index.html`。
- demo/live 切换、两条分析流程和受众模拟完全不变。
- 新增的只是开发用 `/legacy/` 启动方式和基准测试，不改变页面。

### Backend changes

- 无业务 backend。
- 可增加最小静态文件测试服务器，仅用于自动化打开原型。

### Frontend changes

- 不修改 `index.html`。
- 建立 Playwright characterization tests。
- 把 demo 常量复制成只读测试 fixtures，并记录来源行或 source hash。
- 记录关键 DOM selector、按钮文案、阶段顺序和截图。

### Storage changes

- 无运行时存储。
- 测试目录保存 fixture、截图和 `index.html` hash。

### Tests

- 账号 demo：载入样例 → 生成诊断 → 等待四段结果。
- 热点 demo：载入样例 → 热点分析 → 记录当前实际 stage 行为。
- 两种 demo 受众模拟：等待 personas、reactions、debate、synthesis。
- workflow/mode 切换与一键填入 `simTopic`。
- CSV 文件上传后的条数提示。
- 校验 `index.html` SHA-256，防止迁移中被意外编辑。

### Acceptance criteria

- 在干净环境中，一个命令可运行 legacy smoke suite。
- 所有当前 demo 场景通过，并产出稳定截图/语义快照。
- `index.html` 与切片开始前字节一致。
- 已知异常被测试记录，而不是在本切片修复。

### 必须明确保持不变

- 所有用户文案、样式、延时、demo 数据和 live 调用方式。
- 当前浏览器 API key 行为，包括其已知风险；本切片只记录，不修复。
- 热点 stages 与标题渲染的当前实际行为。

## 4. Slice 2 — 提取 TypeScript 类型和 React 渲染组件

**主要改动层：frontend。** 不引入 FastAPI、SQLite 或工作流重写。

### 用户可见行为

- `/legacy/` 继续显示原页面。
- `/app/` 提供 React 版 demo 页面，视觉和操作与 legacy 对齐。
- React 版只运行 demo fixtures；live 按钮可显示“仍由 legacy 提供”或通过 feature flag 隐藏，默认入口仍是 legacy。

### Backend changes

- 无。

### Frontend changes

- 建立 React + TypeScript 应用。
- 从当前 JSON shape 提取领域类型：
  - `AccountProfile`、`PainPoint`、`Topic`、`TitleGroup`、`ContentStructure`；
  - `TrendAnalysis`；
  - `Persona`、`Reaction`、`DebateTurn`、`SimulationSynthesis`；
  - `WorkflowMode`、`WorkflowKind`、`StageState`。
- 将现有 builder 函数逐个转换为纯 React component：
  - `ProfileResult`、`PainPointList`、`TopicList`、`TitleVariants`、`StructureResult`；
  - `TrendAnalysisResult`；
  - `PersonaGrid`、`ReactionList`、`DebateList`、`SynthesisResult`。
- 创建与当前左侧输入区等价的 controlled form。
- demo orchestration 仍在前端，用相同 fixture 和延时。
- CSS 先按原样迁入 scoped stylesheet；不同时更换设计系统。

### Storage changes

- 无。React state 刷新后仍会丢失，与当前原型一致。

### Tests

- 每个 component 使用原型 fixture 做渲染测试。
- 断言缺省数组、可选 contrast、可选 `whyTrending` 和未知 enum 的容错。
- React demo 的 Playwright 流程与 legacy characterization test 使用相同断言。
- screenshot diff 允许字体/浏览器抗锯齿阈值，但不允许内容或布局块缺失。

### Acceptance criteria

- `/legacy/` 与 `/app/` 可同时运行。
- React 版账号 demo、热点 demo 和两种模拟 demo 可完成。
- 相同 fixture 在 legacy 与 React 中产生相同业务文本和阶段顺序。
- TypeScript strict mode 通过，component 中没有 `any` 作为领域数据逃生口。
- 默认产品入口仍指向 legacy。

### 必须明确保持不变

- demo 数据、阶段延时、按钮含义和结果顺序。
- 不修复原型已知 stage/标题不一致。
- 不改变 prompt、API、CSV 解析或持久化行为。

## 5. Slice 3 — 引入 FastAPI 模型代理

**主要改动层：模型调用边界。** 前端只替换 live transport；不引入数据库或 LangGraph。

### 用户可见行为

- React `/app/` 的 live 模式开始可用。
- 两条分析和受众模拟仍由 React 按当前顺序 orchestration，结果逐阶段显示。
- API key 改由后端环境配置；用户不再需要把长期 key 交给浏览器。除此之外，live 结果和错误位置保持一致。
- legacy 仍保留原浏览器直连行为，仅作为参考，不成为正式入口。

### Backend changes

- 建立 FastAPI 应用、health endpoint 和 Anthropic client adapter。
- 通过产品 operation enum 暴露临时代理，例如：

  ```text
  POST /api/prototype/model-calls/{operation}
  operation = account_profile | pain_points | topics_a | structure |
              trend_analysis | topics_b | personas | reaction | debate | synthesis
  ```

- 后端持有从原型逐字复制并加版本号的 prompts、max token 和 tool schema。
- API 只接收 operation 所需业务输入，不允许客户端提交任意 system prompt 或 endpoint。
- API key 从进程环境读取；不记录 key，不把第三方原始错误完整回传。
- 保留 `callChunk` 的文本 JSON fallback 和 tool-use 行为，封装为可测试 adapter。

### Frontend changes

- 新增类型化 API client。
- React live orchestration 仍复现：
  - account：profile/pain 并行 → topics → first-topic structure；
  - trend：trend/pain 并行 → topics → first-topic structure；
  - simulation：personas → reactions 并行 → debates 并行 → synthesis。
- 用 FastAPI error envelope 映射到现有阶段错误卡。
- 不再读取 `./key`；React API key 输入不进入正式 live 流程。

### Storage changes

- 无数据库。
- 只增加后端环境配置；密钥不写入仓库和浏览器存储。

### Tests

- FastAPI TestClient/HTTP client：每个 operation 请求和响应 schema。
- fake Anthropic adapter：断言完整 system prompt、user context、max tokens 和 tool schema。
- HTTP 4xx/5xx、无 tool_use、malformed JSON、timeout 的错误映射。
- React live integration 使用 mock FastAPI，断言并行和串行边界不变。
- legacy 和 React 对相同录制模型响应的最终 DOM 语义一致。

### Acceptance criteria

- 浏览器 network 中不出现 Anthropic endpoint 或 API key。
- React live 的全部当前模型调用都经过 FastAPI。
- 使用录制响应时，React 结果与原型完全相同。
- 后端不可接受任意 prompt 代理请求。
- FastAPI 不可用时，React 显示明确错误，legacy 与 demo 仍可运行。

### 必须明确保持不变

- prompts、上下文拼接、调用数量、并行顺序、模型 ID 和输出 schema。
- demo 模式仍完全离线。
- 不保存输入或输出，不引入 workspace。
- 本切片不把流程 orchestration 搬到后端。

## 6. Slice 4 — 引入最小 workspace 持久化

**主要改动层：workspace shell + 最小 SQLite。** 不迁移材料和分析结果。

### 用户可见行为

- React 进入时显示 workspace 列表或打开最近 workspace。
- 用户可创建 workspace，填写名称和账号定位。
- sidebar 出现固定入口，但尚未完成的模块显示为空状态。
- 刷新后 workspace 名称和已保存账号定位恢复。
- 原有诊断输入区读取当前 workspace 的定位；其他文本仍是临时表单状态。

### Backend changes

- 增加 SQLite connection/repository 和 migration mechanism。
- 只建立：
  - `creator_workspaces`；
  - `positioning_versions`。
- 增加 workspace list/create/get/patch endpoints。
- 启用 foreign keys、WAL 和短事务。
- workspace response 返回当前 positioning 和空的模块计数。

### Frontend changes

- 增加 workspace picker、workspace layout 和 sidebar。
- URL 使用 `/app/workspaces/:workspaceId/...`。
- 账号定位改成显式保存；保存产生新版本。
- 原有分析表单与结果 component 嵌入 workspace 主区域，不重做 UI。
- 保留“载入样例”，它只填表单，除非用户点击保存，不自动污染 workspace。

### Storage changes

- 新增 `data/app.sqlite3`。
- 只保存 workspace 和 positioning version；不保存 API key、模型结果或其他输入。

### Tests

- repository migration、workspace CRUD、positioning version increment。
- 外键和跨 workspace 引用校验。
- React 刷新后恢复当前 workspace 和定位。
- 空数据库首次启动和已有数据库重复启动。
- legacy smoke 与 React demo/live regression。

### Acceptance criteria

- 创建 workspace、保存定位、刷新后内容一致。
- 修改定位创建新版本，旧版本仍可由 API 读取。
- React 原有 demo/live 流程仍能使用当前 positioning 运行。
- 删除 `data/app.sqlite3` 后应用可重新初始化，不影响 legacy。

### 必须明确保持不变

- 分析仍由 React orchestration 和模型代理执行。
- notes、comments、CSV、结果、topics 和 simulation 仍不持久化。
- 现有结果 renderer、prompt 和调用顺序不变。
- 不同时实现完整 workspace model。

## 7. Slice 5 — 保存和加载 source materials

**主要改动层：材料存储。** 分析执行方式不变。

### 用户可见行为

- 用户可在 workspace 中保存并重复选择：
  - 历史笔记集合；
  - 评论样本集合；
  - 热点 CSV dataset。
- 账号诊断表单可从已保存集合载入 notes/comments。
- 热点分析可选择已保存 dataset，也继续支持粘贴和上传。
- 刷新后材料和 CSV 解析状态保留。

### Backend changes

- 增加 `source_sets`、`historical_posts`、`comment_samples`、`trend_datasets`、`trend_posts` repositories 和 endpoints。
- 把当前 CSV header mapping、字段提取、排序准备逻辑移植为 Python service，但分析仍由 React 发起。
- 上传采用受控 multipart endpoint；生成 dataset ID、受控路径和 hash。
- 返回规范化的 notes/comments 文本和 trend rows，供当前 React orchestration 使用。
- 旧 JS CSV parser 保留在 feature flag 后，用于对照测试，不在同切片删除。

### Frontend changes

- sidebar“材料”页面增加三种固定材料 UI。
- 账号输入区增加“从材料库选择”和“保存为材料集合”。
- 热点输入区显示 dataset 名、关键词、行数、parse status。
- 上传后使用后端解析结果；解析失败显示可行动错误。
- 未保存的粘贴文本仍可直接运行，保持原型快速试用路径。

### Storage changes

- SQLite 保存材料元数据和解析后的行。
- 原始 CSV/TSV 保存到 `data/uploads/trends/{workspaceId}/{datasetId}/source.csv|tsv`。
- 其他材料不写成磁盘文件。

### Tests

- 历史笔记的「标题｜数据｜爆/平/差」导入与回读。
- 一行一条评论的导入、编辑、归档与回读。
- CSV/TSV、中文表头、quoted comma、quoted newline、BOM、无效数字和空文件。
- Python parser 与 legacy parser 在 legacy 可正确处理的 fixture 上结果一致。
- 上传路径 traversal、超限文件、错误扩展名。
- 选择材料后发给模型代理的上下文与原表单文本一致。

### Acceptance criteria

- 三类材料保存后刷新可重新选择。
- 同一材料可用于多次分析，不会因一次运行被修改。
- 有效 prototype CSV 的 top 50 输入文本与原算法一致。
- 原始上传文件只出现在受控 dataset 目录。
- 用户仍可不保存材料直接完成一次分析。

### 必须明确保持不变

- 模型调用仍是 React → FastAPI operation proxy。
- prompt、stage 顺序、结果显示和 demo fixture 不变。
- 不保存 analysis run。
- 不引入 topic library 或 LangGraph。

## 8. Slice 6 — 保存 analysis results

**主要改动层：运行历史持久化。** 暂不搬迁 orchestration。

### 用户可见行为

- live 分析成功或部分成功后出现在“分析”历史中。
- 用户可刷新并重新打开账号诊断或热点分析结果。
- 历史详情显示输入快照、各 stage 状态和当时结果。
- 当前页面的渐进生成体验不变。

### Backend changes

- 增加 `analysis_runs`、`analysis_run_sources`、`analysis_run_stages`。
- 提供临时的“前端协调运行”API：
  - 创建 run/input snapshot；
  - 前端报告 stage started/succeeded/failed；
  - 后端校验 stage transition 和 output schema；
  - 完成 run。
- 只有 React 应用可使用这组过渡 endpoint；切片 8 后删除客户端写 stage 的能力。
- 保存 prompt version、model、source refs 和实际输入 snapshot。

### Frontend changes

- 用户点击 live 分析时先创建 persisted run，再执行现有 proxy orchestration。
- 每个 stage 完成后把类型化结果写回 run。
- 新增 analysis list/detail；detail 复用 Slice 2 的结果 components。
- demo 默认不写历史，避免固定 fixture 混入真实 workspace；可明确标为 demo 后再选择“保存样例”。

### Storage changes

- SQLite 保存 run、source relations、stage status/input/output/error。
- 不将 analysis JSON 写到磁盘文件。

### Tests

- 合法与非法 stage transition。
- account/trend 完整成功、单个 Phase 1 失败的 partial、全部失败。
- 保存后刷新，detail DOM 与运行完成时 DOM 一致。
- source 后续被编辑时，旧 run input snapshot 不变。
- 恶意客户端提交不符合 schema 的 output 被拒绝。

### Acceptance criteria

- 一次 live 分析在刷新后可从历史完整重建。
- partial run 明确展示成功与失败 stage。
- run 详情能追溯定位版本和材料集合。
- 关闭“保存运行”feature flag 时仍可按 Slice 5 路径运行。

### 必须明确保持不变

- orchestration 仍在 React；并行和串行调用边界不变。
- 后端还不运行完整 workflow，也不使用 LangGraph/SSE。
- 页面正在生成时的 UI 和当前错误卡位置不变。
- 不自动把 topics 提升为独立业务对象。

## 9. Slice 7 — 添加 topic library 和 selected topic

**主要改动层：topic 业务对象。** 不搬迁 workflow execution。

### 用户可见行为

- 分析生成的选题自动进入 workspace 选题库。
- 用户可手工添加、编辑、归档选题。
- 用户可把某条选题设为当前选题。
- 当前选题显示在 sidebar，并可触发结构生成。
- 原分析结果中的“一键填入下期选题”继续存在，并改为选择稳定 topic 后复制其当前文本。
- 为保持原型行为，分析流程仍自动显示基于第一条生成选题的结构；显式选择 topic 是新增的可复用路径。

### Backend changes

- 增加 `topics`、`topic_versions` 和 workspace `selected_topic_id`。
- analysis 的 topic stage 写入成功时，在同一事务中 materialize Topic/TopicVersion。
- 手工 topic `origin=manual`；生成 topic 关联 source run/stage。
- 增加 list/create/get/patch/select endpoints。
- 增加临时 structure operation endpoint，内部仍直接调用现有 structure proxy，并保存返回结果的输入引用；完整异步化留到后续切片。

### Frontend changes

- 增加 topic library、manual topic form、版本历史和 selected state。
- `TopicList` 支持“加入/查看选题库”“设为当前选题”。
- sidebar 当前选题按钮进入结构生成。
- selected topic 使用 ID，不再依赖 `_lastTopics[workflow][index]`。
- 保留原分析页面的 topics 和自动 structure 区域。

### Storage changes

- SQLite 保存 Topic、TopicVersion、title variants、来源 run 和 selected topic pointer。
- 本切片建立最小 `drafts`、`draft_versions`，保存显式生成的结构；完整异步 structure run 在 Slice 8 增加。

### Tests

- generated topics 的字段、顺序和来源关系。
- manual topic 创建与编辑产生新版本。
- 选择 topic、刷新、切换 workspace 后 selected state 正确。
- 不允许选择其他 workspace 的 topic。
- 原分析页第一条结构输出与新增 selected-topic 结构输出使用相同 renderer/schema。

### Acceptance criteria

- generated/manual topics 都可在选题库查看。
- 选中 topic 后刷新仍保持选中。
- 任意已保存 topic 可生成并保存 structure，而不要求重新分析。
- 原有分析结果和模拟填入按钮仍能工作。

### 必须明确保持不变

- 分析 workflow 仍由 React orchestration。
- 现有自动选择 `topics[0]` 生成结构的行为暂时保留。
- structure prompt 和输出 schema 不变。
- 不引入 LangGraph 或 SSE。

## 10. Slice 8 — 把 analysis workflow execution 移到后端

**主要改动层：orchestration ownership。** 使用普通 Python async service，暂不引入 LangGraph。

### 用户可见行为

- 用户点击账号诊断或热点分析后立即获得 run 页面。
- stage 仍按当前顺序渐进出现；Phase 1 仍并行。
- 用户从 sidebar 当前选题发起的独立结构生成也立即获得 structure run 页面。
- 刷新详情可读取已持久化的完成 stage；完整恢复放在 Slice 12。
- demo 仍由前端 fixture 运行，live 改为后端 workflow。

### Backend changes

- 为 account/trend 写普通 Python orchestration functions：
  - 创建 run/stages；
  - snapshot positioning/materials；
  - 并行 profile+pain 或 trend+pain；
  - 处理 partial success；
  - 生成 topics；
  - 保持原型兼容路径时继续为第一条 topic 生成 structure。
- 为 selected TopicVersion 写普通 Python structure generation service，复用同一个 structure operation、prompt 和 output schema。
- 复用 Slice 3 的 operation/model adapter，不改 prompts。
- 增加：
  - `POST /analysis-runs` 启动后台执行；
  - `GET /analysis-runs/:id` 读取状态；
  - `GET /analysis-runs/:id/events` SSE。
- 增加 `structure_generation_runs` 及对应 start/get/events endpoints；成功后创建 DraftVersion。
- 服务端成为唯一可更新 run/stage 状态的主体，删除 Slice 6 的客户端 stage-write endpoint。
- SSE 先使用进程内 publish/subscribe；SQLite stage rows 是当前状态的事实来源。

### Frontend changes

- 删除 React live orchestration；改为 start run + subscribe SSE。
- selected-topic structure 从同步临时 endpoint 切换为 structure run + SSE。
- reducer 按统一 event contract 更新 `StageState`。
- SSE 断开时退化为定时 GET run polling，不重复创建 run。
- result components 不改，只改变数据来源。
- 保留 operation proxy 供 simulation 和过渡回退使用。

### Storage changes

- 沿用 analysis tables，并增加 `structure_generation_runs`；成功的结构仍保存为 DraftVersion。
- 每个 stage 在模型调用前后提交状态和结果。
- 不保存完整 SSE event log；Slice 12 再增加可重放事件。

### Tests

- Python orchestration 对 fake adapter 的调用顺序和并行屏障。
- account/trend success、partial、failure 状态机。
- selected TopicVersion → structure run → DraftVersion 的成功和失败路径。
- SSE 事件顺序、run ID、stage key 和 terminal event。
- 前端 SSE reducer 对重复事件和乱序 terminal event 的容错。
- 设置 `workflow_engine=client_proxy` 后可回退到 Slice 7 路径。

### Acceptance criteria

- React 不再决定 live analysis 的下一模型调用。
- 一个 start request 只创建一个 run。
- SSE 驱动的可见 stage 顺序与迁移前一致。
- 独立结构生成在返回 HTTP 响应后继续执行，并可通过 run ID 读取进度。
- FastAPI 重启前已完成的 run 可正常读取；运行中恢复暂不承诺。
- operation proxy 仍可用于回退，但正式 analysis UI 不调用它。

### 必须明确保持不变

- prompts、模型、tool schemas、top 50 算法和 partial 规则。
- renderer、stage 文案、demo 模式和第一条选题 structure 行为。
- 本切片不同时引入 LangGraph。
- simulation 仍走前端 orchestration + proxy；analysis 与 structure 已在后端。

## 11. Slice 9 — 用 fake nodes 引入 LangGraph

**主要改动层：backend workflow engine。** 首先只切换 deterministic demo/test path。

### 用户可见行为

- React demo 输出与此前完全一致。
- live analysis 默认仍使用 Slice 8 的普通 Python orchestration。
- 可通过开发 feature flag 将某个 run 路由到 fake LangGraph，用于内部验收；fake graph 不消耗模型额度。

### Backend changes

- 定义类型化 graph state，至少包含：
  - run/workspace/source snapshot；
  - profile/trend result；
  - pain points；
  - topics/titles；
  - structure；
  - stage errors/status。
- 建立 account diagnosis、trend analysis 和单节点 structure generation graph。
- 节点使用 deterministic fake implementations，直接返回原型 fixtures。
- 图的 fan-out/fan-in 与当前流程一致：两个 Phase 1 nodes 并行，topic node 等待，structure node 最后执行。
- graph node 通过同一 run repository 和 SSE publisher 写 stage events。
- 加 `workflow_engine=python|langgraph_fake` 配置；不删除 Python orchestrator。

### Frontend changes

- 无业务 component 修改。
- 可在开发配置或测试请求 header 中选择 fake engine；业务组件无需随 engine 改动。
- 继续消费同一 SSE contract。

### Storage changes

- 沿用现有 run/stage 表。
- fake graph output 与普通 run 使用相同 schema；用 `engine`/`prompt_version` 元数据标识。
- 暂不启用 durable graph checkpoint。

### Tests

- graph topology：节点和边符合 account/trend 数据依赖。
- fake graph 与普通 Python fake adapter 对相同 fixture 产生相同 stage outputs。
- fake structure graph 产生相同 DraftVersion payload。
- graph 并行节点不会互相覆盖 state。
- SSE contract test 对两种 engine 完全相同。
- 运行 fake graph 后 topic materialization 与普通路径一致。

### Acceptance criteria

- `langgraph_fake` 能完成两条分析和独立结构生成，并通过全部 E2E demo 测试。
- frontend 不需要知道 run 使用哪个 engine。
- Python live path 仍可用，切换 graph 不影响 legacy。
- fake node 没有外部模型调用。

### 必须明确保持不变

- 所有用户可见 fixture、阶段顺序和结果 schema。
- live 默认路径和现有 prompts。
- 不在本切片同时迁移真实模型 nodes、simulation 或 recovery。
- LangGraph graph 只是一组 Python 模块，不增加新的产品概念。

## 12. Slice 10 — 用现有 prompts 替换 fake nodes

**主要改动层：LangGraph node implementation。** Frontend 和 storage contract 不变。

### 用户可见行为

- live account/trend runs 开始由 LangGraph 执行。
- stage 顺序、逐步结果、错误显示和最终内容与 Slice 8 live path 一致。
- demo 仍使用 deterministic fixture，不消耗模型额度。

### Backend changes

- 为每个 fake node 接入 Slice 3 的 model adapter 和现有 prompt：
  - account profile；
  - pain points；
  - account topics/titles；
  - trend summary；
  - trend topics/titles；
  - structure。
- prompts 保持逐字内容，移动到版本化 Python modules/resources。
- 保留现有 max token、tool-use schema、文本 JSON fallback 和 context 拼接。
- graph routing 实现当前 partial behavior。
- 使用 `workflow_engine=langgraph_live` feature flag 灰度；保留 Python orchestrator 作为一个切片的回退。

### Frontend changes

- 无组件改动。
- 继续 start run + SSE；不根据 engine 分支。

### Storage changes

- run/stage 记录 `engine=langgraph`、model 和准确 prompt version。
- output schema 与已有 SQLite JSON 完全一致，无 migration。

### Tests

- 每个 node 的 prompt golden test：system、user context、max tokens、tool schema。
- fake model response 的 schema parsing 和错误映射。
- Graph contract 与 Slice 8 Python orchestrator 对相同录制响应的深度相等比较。
- Phase 1 单点失败、topics 失败、structure 失败。
- live smoke 可用受控测试模型/录制 adapter，避免 CI 调真实 API。

### Acceptance criteria

- account/trend 和独立 structure generation 的正式 live UI 使用 `langgraph_live` 完成。
- 对录制响应，LangGraph 与旧 Python orchestration 的 stage output、topic rows 和最终 DOM 一致。
- prompt golden files 与 `index.html`/审计文档记录一致。
- feature flag 可以无数据迁移回退到 Python engine。

### 必须明确保持不变

- prompts 和输出 schema，不在迁移中“优化 prompt”。
- CSV 采样、并行边界、partial 规则和自动 first-topic structure。
- frontend/SSE/storage contract。
- simulation 暂不进入 LangGraph。

## 13. Slice 11 — 后端化并保存 audience simulation

**主要改动层：simulation workflow。** 复用既有 LangGraph、SSE 和 SQLite 基础设施。

### 用户可见行为

- 用户可对当前 topic 或已保存 draft/structure 发起受众模拟。
- personas、reactions、debate 和 synthesis 仍按原顺序出现。
- 每次模拟保存到 workspace，刷新后可重新打开。
- demo account/trend simulation 仍显示原固定样例。

### Backend changes

- 增加 audience simulation graph/state：
  - persona node；
  - per-persona reaction fan-out；
  - reaction join；
  - per-persona debate fan-out；
  - debate join；
  - synthesis node。
- 使用现有动态 prompt 模板和 tool schemas，不改 persona 字段 fallback。
- 为兼容原型，synthesis 的输入先保持当前实际内容；是否加入完整 debate 是后续产品变更。
- 增加 simulation start/get/events endpoints。
- 某个 persona 失败时记录 item status，并按当前可用结果继续，run 可为 partial。
- 正式 simulation UI 不再调用临时 operation proxy；proxy 可在切片验收后删除。

### Frontend changes

- `runSimulation` 改为创建 persisted run + SSE subscription。
- 从 selected TopicVersion 或 DraftVersion 传稳定 target ID，不再只依赖 textarea。
- 保留自由文本快速模拟作为兼容入口时，后端创建一个不可变 target snapshot，而不强制先建 topic。
- simulation list/detail 复用已有 persona/reaction/debate/synthesis components。
- failure item 替换永久 spinner，显示局部失败。

### Storage changes

- 增加 `audience_simulation_runs` 和 analysis context relations。
- 保存 target/context snapshot、stage status、personas、reactions、debate、synthesis 和错误。
- JSON item 使用稳定 persona ID 和 item status。

### Tests

- account-context 与 trend-context persona 输入保持原型分支行为。
- 三 persona reaction/debate fan-out 与 join。
- 单 persona 失败、全部 reaction 失败、synthesis 失败。
- topic version/draft version target snapshot 不随后续编辑改变。
- SSE 事件驱动的 React DOM 与 demo/录制 live fixture 一致。
- 刷新后 simulation detail 完整重建。

### Acceptance criteria

- 正式 simulation 不再由浏览器决定下一模型调用。
- 每次运行在调用模型前已有持久 run ID 和 target snapshot。
- 成功和 partial 结果都能在刷新后查看。
- 原两套 demo simulation 继续通过 characterization tests。
- Slice 3 临时 proxy 不再被正式 UI 使用。

### 必须明确保持不变

- persona/reaction/debate/synthesis prompts、调用数量、并行结构和 schemas。
- 情绪与立场 enum、三种 persona 颜色、可见阶段顺序。
- demo 固定结果和自由文本模拟入口。
- 不在本切片同时改变 synthesis 的产品逻辑。

## 14. Slice 12 — Resume、SSE 重连和失败恢复

**主要改动层：durability。** 不改变正常成功路径的业务输出。

### 用户可见行为

- analysis、structure generation 或 simulation 运行中刷新页面后，用户回到同一 run 并看到已完成阶段。
- SSE 暂时断开后自动重连，不会重复创建 run 或重复显示结果。
- 后端重启后，未开始的任务继续；无法确认的中断调用显示明确失败并可重试。
- 用户可以重试失败 run；原失败历史保留，新 retry run 单独显示。

### Backend changes

- 增加 durable event rows 或等价的可重放事件存储：`event_id/run_id/sequence/type/payload/created_at`。
- SSE endpoint 支持 `Last-Event-ID`；先重放缺失事件，再订阅 live stream。
- 为 LangGraph 配置 SQLite-backed checkpoint，checkpoint 与产品 run/stage rows 使用同一个 run ID 关联；具体 adapter 隔离在 workflow infrastructure 中。
- 服务启动时扫描 queued 和过期 running 状态：
  - 未发起外部调用的 queued node 可继续；
  - 已提交外部调用但没有结果的 node 标记 `execution_interrupted`；
  - 不自动无限重试不确定调用。
- retry 创建带 `retry_of_run_id` 的新 run：
  - analysis 可引用原 run 成功 stage 并只执行失败及下游；
  - structure/simulation 使用原 input snapshots 创建新 run；
  - 原 run 不修改。
- stage 完成、业务 output、event 和 graph checkpoint 的写入顺序必须可恢复；用短事务和幂等写约束防止重复 materialize topics/drafts。
- 增加 heartbeat 和连接清理。

### Frontend changes

- run route 成为刷新恢复的唯一定位：
  - `/analysis/:runId`；
  - `/structures/:runId`；
  - `/simulations/:runId`。
- 页面先 GET snapshot，再以最后 event ID 建 SSE。
- reducer 按 `(runId, sequence/eventId)` 去重。
- SSE 失败时指数退避重连，并短暂 fallback 到 GET polling。
- 显示 `queued/running/partial/succeeded/failed/interrupted` 的清晰状态和 retry 操作。

### Storage changes

- SQLite 增加 run events、retry links、必要的 LangGraph checkpoint tables。
- 对 `(run_id, sequence)`、materialized source stage、retry parent 建唯一约束/索引。
- checkpoint 是执行基础设施数据；业务详情仍读取 analysis/stage/topic/draft/simulation tables，不直接解释 checkpoint blob。

### Tests

- 在每个 node 前后强制终止 worker，再启动并验证状态。
- 浏览器刷新、断网/重连、重复 `Last-Event-ID`、乱序/重复 event。
- 后端重启后 queued node 恢复。
- 外部调用中断被标记失败而不是盲目重复。
- retry 产生新 run，原 run 与 outputs 不变。
- topic/draft materialization 在事件重放和 worker 重启后不重复。
- SQLite locked/busy 的受控重试和最终错误。
- 完整 E2E：保存材料 → 分析 → 刷新 → 选题 → 结构 → 重启 → 模拟 → 重连。

### Acceptance criteria

- 三类长任务都能在刷新后恢复到同一 run。
- SSE 重连不会丢 stage，也不会重复渲染或重复写业务对象。
- 服务重启后没有永久 `running` 状态。
- retry 保留原历史并使用相同 input snapshot。
- 全部 legacy characterization、React component、API、workflow 和 E2E tests 通过。
- React 可成为默认入口；legacy 仍可在 `/legacy/` 打开。

### 必须明确保持不变

- 正常成功运行的 prompts、节点依赖、输出和页面内容。
- workspace 实体关系、选题/草稿版本语义和 demo behavior。
- 不借 recovery 切片改变模型、重试模型回答、合并历史或自动覆盖用户内容。

## 15. 切片依赖和可回退点

| Slice | 默认正式路径 | 新能力 | 回退方式 |
| --- | --- | --- | --- |
| 1 | Legacy | 行为基线 | 直接运行 `index.html` |
| 2 | Legacy | React demo/renderers | 关闭 React route |
| 3 | Legacy 或 React | FastAPI proxy/live | React 回 demo；legacy 参考仍在 |
| 4 | React 可灰度 | Workspace/positioning | 使用临时 workspace；legacy 不受影响 |
| 5 | React | Saved materials | 使用未保存文本输入 |
| 6 | React | Saved analysis history | 关闭 run persistence flag |
| 7 | React | Topic library | 分析页内 topics 仍可用 |
| 8 | React | Backend orchestration + SSE | `workflow_engine=client_proxy` |
| 9 | React | LangGraph fake | `workflow_engine=python` |
| 10 | React | LangGraph live | `workflow_engine=python` |
| 11 | React | Saved backend simulation | `simulation_engine=client_proxy` |
| 12 | React 默认候选 | Durable resume/retry | GET polling；不删除旧 run |

feature flags 只服务迁移和回退。稳定后应删除已失去用途的客户端 orchestration 和临时 proxy 路径，避免永久维护两套实现。

## 16. 完成标准

迁移完成不是“技术栈已经出现”，而是以下条件同时成立：

1. React/TypeScript 覆盖现有账号诊断、热点分析、结构和受众模拟 UI。
2. 浏览器不再直接持有模型 API key，也不直接决定 live workflow 的下一调用。
3. FastAPI 提供 workspace、材料、run、topic、draft 和 simulation API。
4. SQLite 保存业务对象、版本、运行状态、结果、events 和 checkpoints；磁盘只保存上传的原始 CSV/TSV。
5. LangGraph 执行 account、trend 和 simulation workflows，节点使用原型现有 prompts。
6. SSE 提供逐阶段体验，并支持断线重放。
7. 刷新和服务重启后能够恢复或明确终止，不存在永久 spinner。
8. 每个结果都能追溯到定位版本、source materials、prompt version 和 model。
9. 原型 characterization suite 与新应用 E2E suite 全部通过。
10. `index.html` 保持未修改，并继续作为产品行为参考。

完成这些条件后，再单独规划已知行为修复、prompt 优化和新功能。它们不应混入架构迁移切片。

# 当前状态与 TODO

更新日期：2026-08-13

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

### 内容资产

当前内容资产包括：

- 创作者档案；
  - 小红书主页；
  - 账号概况；
  - 历史笔记；
  - 评论样本；
  - 视频创作样本；
- 趋势 CSV 数据；
- 图片素材；
- 视频素材；
- 分析结果；
- 选题库；
- 受众模拟。

已实现：

- 资产实例列表；
- 资产详情编辑；
- 创作者档案组合概览，聚合当前小红书主页、账号概况、历史笔记、评论样本和视频创作样本；
- 显式保存；
- workflow 运行前自动保存必要输入；
- 账号概况批量 CSV/TSV 导入；
- 历史笔记、评论样本、视频创作样本的通用 CSV/TSV 批量导入 API 和前端入口；
- 小红书创作者主页在后端仍是独立 input asset type，但前端归入“创作者档案”；它可由本地 MediaCrawler fixture 导入，并可直接作为账号诊断输入，也支持按主页资产批量运行账号诊断；
- workflow 批量运行：账号概况批量、以及小红书创作者主页批量账号诊断；
- 批量结果 CSV 导出；
- 输入素材整理 agent 草稿入口；
- 输入素材整理通过后端 `input_asset.format_*` skills 调用，不再是纯前端假整理。
- 图片/视频媒体资产基础层：
  - 上传图片/视频；
  - 文件由后端受控落盘；
  - SQLite 保存 metadata、derived JSON、用户备注和文件引用；
  - 前端支持列表、详情预览和显式保存；
  - Context Access Layer 已包含 `media_assets_overview`，并会携带 compact `imageUnderstanding` / `videoUnderstanding` / `videoPreview`；
  - Qwen 图片理解和视频理解可作为受控 media skills 调用；
  - Qwen 图片生成和视频生成可作为受控 media skills 调用；
  - 本地上传视频可通过 ffmpeg 抽取预览帧，帧会作为 `extracted_frame` 图片素材保存；
  - Qwen 理解结果会先作为草稿展示，用户确认后写入 `MediaAsset.derived`；
  - 生成类 media skills 会把远程结果下载到本地受控 media storage，并登记为 `MediaAsset`。

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
- 视频博主质量诊断已按同一产品接口实现，支持小红书创作者主页派生 evidence pack，也兼容视频创作样本文本，并可选择已保存的图片/视频素材 compact understanding 作为补充上下文；
- 运行结果、stage 结果、错误和 input snapshot 会持久化。
- “下期选题”只用于受众模拟，不是账号诊断、热点分析或视频质量诊断的必填输入。

### 能力资产

当前能力资产包括：

- Skills；
- Agents；
- Workflows；
- agent conversation；
- Capability Maker agent；
- Creator Dossier Formatter agent；
- AssetProposal apply/reject 流程。

当前定位：

- 用户侧主要查看和通过对话生成 proposal；
- 前后端和后端 seed 逻辑把它们当成可组合、可编辑、可新增的产品资产；
- Maker conversation 可以携带当前选中的 Skill / Agent / Workflow 详情作为 context target；
- Skills 已有受控的后端调用入口：`POST /api/skills/{skill_asset_id}/invoke`；
- 当前可直接调用的是产品内置输入素材整理类 skills，以及 Qwen 图片/视频理解与生成类 media skills；
- media skills 不是通用代码沙箱，也不是任意工具运行时；
- 不把用户界面做成通用 workflow 编辑器或通用 agent 平台。

### 模型调用

当前后端模型 provider：

- Anthropic；
- Qwen / DashScope OpenAI-compatible API。

浏览器不再直接持有模型 API key。

当前 qwen 接入状态：

- 后端已支持通过 `.env.local` 配置 qwen OpenAI-compatible endpoint；
- agent conversation 的 live 路径已经走后端模型 provider；
- qwen 请求会尽量使用 JSON response format；解析器可从 fenced JSON 或前后带解释文字的响应中提取 JSON object；
- 图片理解和视频理解已通过 Qwen vision chat completions 接入为受控 skills；
- 本地上传视频理解会先抽取预览帧，再把帧作为图片输入发送给 Qwen；完整视频文件不会直接发送；
- 图片生成和视频生成已通过 DashScope async task 接入为受控 skills；
- 生成类 media skills 会下载返回的远程结果到本地 media storage，并登记为 `MediaAsset`；远程 URL 只作为 `externalUrl` 来源记录；
- 图片/视频素材页面已经提供 Qwen 理解与生成入口；
- 视频质量诊断 live 路径不会把完整媒体文件放入 graph state，只保存媒体资产 ID 和 compact immutable snapshot；
- 理解结果先展示为草稿，用户确认后才写回 `MediaAsset.derived`；
- `scripts/smoke_qwen_media.py` 可用于真实 API smoke test，不进入常规自动化测试；
- 自动化测试仍默认使用 fake provider，避免 CI 或本地测试消耗模型额度；
- 完整 workflow live smoke test 可以按需手动执行，不作为常规测试前置条件。

## 当前 TODO

### P1：资产 proposal 编辑与校验

- Capability Maker 已经可以拿到 capability catalog。
- Maker conversation 已经可以携带当前正在查看的具体 Skill / Agent / Workflow 作为 context target。
- 下一步是让资产 proposal 支持编辑后再 apply。
- proposed action validation 还需要按 action type 定义 schema。

### P1：输入素材整理继续模型化

当前已经有 Creator Dossier Formatter agent、formatter skills 和后端 invoke API。当前实现是确定性 formatter，适合稳定生成草稿字段。

后续如果需要更强整理能力，可以把这些 formatter skills 的实现从确定性代码切到模型调用：

- 接收目标资产类型；
- 接收用户粘贴的原始文本；
- 返回结构化草稿和置信说明；
- 用户确认后保存为对应内容资产。

### P1：批量导入与批量 workflow 体验

- 账号概况批量导入后应更清晰地展示每个实例的状态。
- 历史笔记、评论样本、视频创作样本、小红书创作者主页批量导入已接入，后续需要更好的导入结果预览和错误行展示。
- 批量运行进度需要更明确。
- 批量导出 CSV 字段需要稳定成产品 contract。

### P1：conversation 执行持久化继续增强

agent conversation 现在已经不是同步等待模型完成：

- 发送消息会先创建用户消息和 assistant 占位消息；
- 后端 in-process task 生成回复；
- 前端轮询观察 queued/running/completed/failed 状态；
- provider 失败会留下 assistant failure message。

剩余问题：

- 这仍是进程内任务，不是 SQLite durable job；
- 进程崩溃时只能按 queued/running message 尝试恢复；
- 没有 conversation message 级 idempotency key。

### P1：qwen 结构化输出继续加固

- 继续保持 fake provider 作为默认自动化测试路径。
- 已支持 JSON response format、fenced JSON 和前后带解释文字的 JSON 提取。
- 图片/视频理解已要求结构化 JSON，并把 `imageUnderstanding` / `videoUnderstanding` 保存到 media asset derived JSON。
- 后续为更多 qwen 真实响应补充脱敏 fixture。
- 对部分 schema 缺失做更明确的 repair/validation。

### P1：前端结构继续拆分

- 已将 stage/result 纯展示组件从 `App.tsx` 拆到 `frontend/src/components/StageResultViews.tsx`。
- 已拆出 `WorkspaceShell`、媒体资产页、输入资产页、账号概况页、workflow 调用面板、workflow 输出面板和 conversation pending polling hook。
- 下一步继续拆：
  - TopicLibraryPage；
  - AgentConversationPanel；
  - shared workspace data hooks。

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

- Workflow assets 是产品能力目录和调用说明，不是前端可编辑的任意 nodegraph。
- Skills 当前是产品内受控能力；formatter skills 与 media skills 支持直接 invoke，不支持任意代码工具调用。
- 视频博主质量诊断优先使用小红书创作者主页派生的 compact evidence pack，兼容文本化视频创作样本；如果用户先保存 Qwen 图片/视频理解结果，workflow 可以读取 compact media understanding，但不做自动视频抓取或本地视频直传。
- 图片/视频素材已经可以作为媒体资产保存；Qwen media skills 可理解图片、基于公开视频/帧 URL 或本地视频抽帧理解视频，并可生成图片/视频资产。
- 本地上传的视频文件不会直接发送给 Qwen；当前本地视频理解入口依赖 ffmpeg 抽帧。
- SSE 是可重连观察 replay，不是完整 durable event log。
- 安全边界、认证、权限、多用户部署暂不作为当前版本目标。

### 暂不考虑

- 认证；
- 多租户；
- 权限系统；
- 通用安全边界设计。

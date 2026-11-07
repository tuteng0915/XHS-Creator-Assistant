# 项目总览：当前状态

核对日期：2026-11-07，代码基线`ea5b22d`（2026-10-31）。本文是**当前状态的唯一汇总**：产品决定、架构、数据流、完成度和测试基线。每轮的详细记录在[状态记录](status-and-todo.md)，决定的来龙去脉在[PRD](product-requirements.md)，下一步在[路线图](roadmap.md)。文中与旧文档冲突时，以本文和最新日期条目为准；本文过时时，随功能变化一起更新。

## 1. 产品定位

“小红书创作助手”是本机运行的创作者工作区。`SqsAgent`只是目录名。

主流程是：导入自己的笔记 → 认识账号（账号诊断）→ 找到不同的读者（受众分析、手动收录为模拟粉丝）→ 让读者讨论（受众模拟）→ 单助手创作，由作者采用、保存。分析、试读都是可选辅助，作者随时可以直接创作。

模型负责建议，所有结论和稿件由作者决定是否采用。用户反复强调的优先级是：先解决交付失败、事实可靠性和实际等待时间，再考虑新功能；不靠增加串行校验、字段门槛或提示词禁令来提高质量。

## 2. 当前产品决定

| 领域 | 当前决定 |
| --- | --- |
| 账号诊断 | 先选笔记范围，再生成报告。先认识账号与作品，积极、具体地呈现优势，用原句、原标题和结构支撑判断。客观表现紧跟账号印象：较高和较低的历史表现左右并排，高用红、低用绿。之后展开优势与建议。 |
| 受众分析 | 从所选笔记和评论生成候选，**作者逐个收录**，不自动收录。已知作者本人的评论不当作读者需求。 |
| 受众模拟 | 独立的一级入口，分三类：账号级（多篇，讨论内容方向）、已发布笔记级（单篇，为下一篇同类内容提建议）、创作级（选题或稿件的修改反馈）。共用选人、独立试读、互相回应和作者追问。准备界面默认三个空槽，可以增加，**不是三人上限**。推荐只是辅助，实际名单才参与。 |
| 创作 | 公开界面只有单助手（`single_writer`），左边对话、右边稿件，窄屏用标签切换。作者自选同账号的原笔记、账号分析、受众分析作参考；**不选时不会自动读取整个账号**。选题库在创作模块内。旧的多角色协作历史只读保留。 |
| 人工采用 | AI建议先预览。首稿“采用并保存”；已有稿的改写放进画布后另行保存。发送消息会先保存当前稿。“复制全部”复制当前标题和正文，含未保存修改，复制本身不保存。 |
| 界面 | 单左栏、红色主色、字号层级克制。帮助是品牌标题右侧的小按钮，菜单只有“看看当前页怎么用”“了解完整流程”两个并排按钮。页面说明用标题或字段旁的内联圈i，不设独立帮助栏。引导只读：高亮、上一步／下一步／Esc，不切页、不跑模型、不保存。 |
| 长任务 | 已完成的部分先展示，失败部分可以单独恢复；不要求逐字流式。异步结果不得覆盖用户之后的修改。 |

## 3. 模型

| 用途 | 默认 | 说明 |
| --- | --- | --- |
| 全部文字生成（诊断、受众、模拟、访谈、创作） | DeepSeek，`deepseek-flash`，非思考 | `MODEL_PROVIDER`、`ACCOUNT_DIAGNOSIS_PROVIDER`、`CREATOR_WRITING_PROVIDER`都默认`deepseek`。缺密钥或请求失败时不会自动换模型。 |
| 账号诊断的图片文字 | DeepSeek | `services/account_image_text.py`直接调用DeepSeek接口，不经过`ModelCallService`。 |
| 独立图像／视频理解与生成 | Qwen（`qwen_media.py`） | 只在内部工作台使用，普通流程不需要Qwen密钥。 |
| 回退 | 显式设置为`qwen`／`dashscope` | 回退规则见[开发与验证](development.md#模型配置)。 |

Claude Code只是开发工具，不改变产品的模型选型。未经明确要求，不调用Anthropic官方API，不做视频生成。

## 4. 架构

技术栈：React／TypeScript／Vite前端；FastAPI、SQLite、LangGraph后端；长任务用SSE推送。

### 后端（`backend/app/`）

- **组装**：`main.py`在`create_app()`中手动装配仓储、服务和工作流。启动时恢复未完成的受众分析、抓取任务、协作会话、工作流运行、读者推荐和作者访谈。
- **接口**：`api.py`（约100条路由，前缀`/api`）覆盖导入、媒体、诊断、模拟、选题与稿件、协作会话和内部能力层。`reader_selection_api.py`、`panel_interview_api.py`、`simulation_review_api.py`是独立业务API。模拟粉丝和受众分析的路由直接写在`main.py`里。
- **工作流**（`workflows/`，LangGraph，均用`compile()`，不使用AsyncSqliteSaver）：
  - `account_diagnosis.py`：画像（含反馈）→ 选题 → 收尾
  - `audience_simulation.py`：人物 → 并行初读 → 互相回应 → 汇总 → 收尾
  - `trend_analysis.py`、`video_creator_quality.py`：旧流程，只在内部模式使用

  `services/workflow_worker.py`负责调度和恢复。
- **模型调用**：`services/model_calls.py`的`ModelCallService`按provider选择DeepSeek、Qwen或Anthropic兼容路径。`main.py`为诊断和创作各建一个独立配置的服务实例。分阶段账号报告走`call_account_report_step`。
- **持久化**：`repositories/`共18个模块；`db/migrations/`有42个SQL文件（0001–0041，编号0024有两个文件）。表按领域分组：

  | 领域 | 表 |
  | --- | --- |
  | 核心 | `creator_workspaces` 等 |
  | 导入 | `source_materials`、`media_assets`、`xhs_capture_jobs` |
  | 诊断 | `analysis_runs`、`graph_checkpoints`、`account_image_text_cache` |
  | 受众 | `audience_analyses`、`simulated_fans` |
  | 模拟 | `simulation_runs`、`simulation_recoveries`、`reader_selections`、`panel_*` |
  | 创作 | `topics`、`drafts`、`content_collaboration_*` |
  | 内部能力层 | `workspace_skills` 等 |

**执行状态与产品内容分开**：LangGraph负责执行图；产品表保存会话、消息、运行记录、输入快照、稿件版本和采用状态。

### 前端（`frontend/src/`）

- `App.tsx`（约3700行）承担大部分页面状态与切换。`components/WorkspaceShell.tsx`定义导航，公开入口是：

  | 分组 | 入口 |
  | --- | --- |
  | 账号 | 账号概览、我的笔记、账号诊断 |
  | 读者 | 受众分析、模拟粉丝、受众模拟 |
  | 创作 | AI创作助手 |
- 其他页面（素材、趋势、视频质量、Skills／Agents／Workflows等）只在`?internal=1`的开发者工作台中出现。这个参数只切换界面，不是权限控制。
- API客户端：`api.ts`，以及`contentCollaboration.ts`、`readerSelection.ts`、`panelInterview.ts`、`creatorReferences.ts`等按业务拆分的模块。
- 长任务：诊断和模拟用`EventSource`接收SSE，并有轮询兜底；受众分析、读者推荐、访谈、协作会话用202加轮询。

### 业务到代码

前端文件都在`frontend/src/components/`，后端路径相对`backend/app/`。

| 业务 | 前端入口 | 后端入口 |
| --- | --- | --- |
| 导航、帮助、页面说明 | `WorkspaceShell.tsx`、`GuidedTour.tsx`、`guideSteps.ts`、`InfoHint.tsx` | 无模型调用 |
| 导入与笔记 | `CreatorStartPage.tsx`、`CreatorMaterialsPage.tsx`、`CreatorNoteBrowser.tsx`、`CreatorNoteSelectionDialog.tsx` | `services/xhs_imports.py`、`xhs_capture_jobs.py`、`xhs_comment_roles.py`、`xhs_comment_refresh.py` |
| 账号诊断 | `CreatorDiagnosisPage.tsx`、`AccountPortraitView.tsx`、`AccountPerformanceView.tsx`、`AccountDiagnosisRecovery.tsx` | `workflows/account_diagnosis.py`、`services/analysis_runs.py`、`account_report_pipeline.py`、`account_report_prompt.py`、`reader_feedback_pipeline.py`、`account_recovery.py`、`account_image_text.py` |
| 受众与读者档案 | `AudienceAnalysisPage.tsx`、`AudienceGroups.tsx`、`SimulatedFansPage.tsx` | `services/audience_analyses.py`、`audience_evidence.py`、`simulated_fans.py` |
| 选人、试读、讨论 | `CreatorSimulationSetup.tsx`、`SimulationCategoryTabs.tsx`、`SimulationChat.tsx`、`SimulationReviewSummary.tsx` | `services/reader_selection*.py`、`panel_*.py`、`simulation_runs.py`、`workflows/audience_simulation.py` |
| 创作与参考 | `CreatorCanvasPage.tsx`、`ContentCollaborationChat.tsx`、`CreatorReferencePicker.tsx`、`TopicLibraryPage.tsx` | `services/content_collaboration_sessions.py`、`content_collaboration.py`、`creator_context.py`、`creator_writing_context.py`、`creator_fact_edit.py` |

## 5. 数据流

1. **导入 → 笔记**：主页链接经`xhs_capture_jobs.py`以子进程运行MediaCrawler；离线包上传到`input-assets/xhs-import-package`。两条路径都由`xhs_imports.py`写入`source_materials`（笔记、评论）和`media_assets`（图片）。重复导入保留已有评论，评论角色按作者哈希判断。历史采集主要下载封面，旧数据没有完整后续页时，不能假定有全文图片。
2. **笔记 → 账号诊断**：创建运行时冻结所选笔记和本地图片，最多识别24张，单张不超过10MB，3张并发，结果按哈希缓存。然后依次运行：
   1. 画像：分阶段报告“整体认识 → 逐篇精读 → 汇总”，检查点存入运行元数据
   2. 读者反馈：两阶段
   3. 选题

   进度通过SSE推送。`POST /api/analysis-runs/{run_id}/recover/{stage}`可以恢复`profile`、`pain_points`或`topics`阶段：新建一条带来源的记录，只补缺失部分，原报告和人工备注保留。识别出的文字只加入诊断输入，不改原笔记。
3. **笔记与评论 → 受众 → 模拟**：
   1. 受众分析生成候选，作者逐个收录为模拟粉丝。
   2. 准备模拟时手动选人，也可以先请求推荐、采用后再调整。
   3. 创建模拟时冻结目标和名单，然后依次运行人物、独立初读、互相回应、汇总。
   4. 作者追问由`panel_interviews.py`处理。局部失败用`panel_recovery.py`单项恢复，旧汇总可以标为待更新。
   5. 等待上限：每位读者的初读、互相回应各30秒，汇总90秒，不自动重试。失败原因分为“没有收到模型回复”“等待超时”“回复格式不符合要求”“模型服务返回错误”，用中文显示；每个环节的耗时和失败类型写进运行元数据的`stepRecords`。
4. **参考 → 单助手创作 → 人工采用**：前端以`single_writer`创建会话。后端每轮调用一次创作服务，上下文来自所选参考和当前稿件（导入笔记参考只含标题和正文，不含评论、图片）。助手返回候选（证据、开放问题、提纲、文案、审读意见）。提纲和文案先在画布中预览，作者采用或保存后才写入`drafts`／`topics`。`creator_fact_edit.py`是可显式调用的定点工具，默认不在每轮执行。

## 6. 完成度

| 模块 | 状态 | 尚待验证 |
| --- | --- | --- |
| 导入与笔记 | 可用；多页图片包、自然页序、重复导入复用 | 字段级合并、非空评论增量合并、采集端观察时间 |
| 账号诊断 | 可用；分阶段报告、检查点、阶段恢复、图片文字（10-30） | 真实逐页识别图片文字、报告引用，以及“成功部分不重复调用、失败部分可恢复”的验收；报告仍有过度概括和关系误读 |
| 受众分析与模拟 | 可用；逐人展示和保存、单项恢复、作者追问 | 相近的读者仍可能被排除；用户已停止继续优化选人，不要主动重启这个方向 |
| 创作 | 主流程可用；已去除重复上下文，回到单次生成 | 历史上出现过把读者处境、推断写成作者亲历，以及模板化标题和文风问题；要看完整成稿 |
| 引导与帮助 | 已完成；2026-11-07在1280、1024、375三个宽度做过实屏回归 | 375宽下“我的笔记”引导第2步的说明卡遮住笔记卡片底部的互动数据 |

## 7. 测试基线（2026-11-07重跑）

- 前端：75个文件、828项通过（`--maxWorkers=2`），lint、build通过。
- 后端：全量2368项通过（2026-11-07受众模拟失败原因修复后）。此前1项失败，原因是`862cadc`改了提示词而测试断言没有同步，已修正断言。ruff通过；LangGraph的弃用提示仍在。
- 实屏回归：见[状态记录](status-and-todo.md)2026-11-07条目。保存和发送没有实际点击。

自动测试、界面验收和模型内容质量是三个层面的检查，分别报告。命令见[开发与验证](development.md#自动检查与真实调用)。

## 8. 本机数据与配置

| 路径 | 用途 |
| --- | --- |
| `data/app.sqlite3` | 主库，默认启动命令会用它，不要覆盖 |
| `data/development-runtime/20261016-f767f21/data/` | 用户演示用的开发库和媒体目录，成套使用；`backups/`下有10-30、10-31、11-07的备份 |
| `data/submission-demo/`、`data/releases/` | 冻结的提交演示和发布包，保持不变 |
| `data/evals/` | 历次模型实验的原文、回放输入和耗时 |
| `docs/assets/promo/`、`output/` | 用户材料，未纳入Git，不要删除或提交 |

开发库在2026-11-07的快照：3个工作区、9条诊断、5条模拟、136个媒体资产，部分结果是人工整理的示例。DeepSeek凭据目前只在`/Users/tut/.codex/worktrees/account-reading-quality/SqsAgent/.env.local`里，仓库的`backend/.env.local`只有Qwen和Anthropic的配置，所以开发实例要用[开发与验证](development.md#使用开发库启动演示实例)中的启动片段。

## 9. 遗留与内部代码

| 遗留项 | 位置与处理 |
| --- | --- |
| 旧多角色创作 | `content_collaboration.py`、`content_collaboration_provider.py`。接口模型`assistant_mode`的默认值仍是`legacy_team`（`models.py:428,599`），公开前端总是显式传`single_writer`。不要重新接回界面。 |
| 内部工作台 | `?internal=1`进入：Skills／Agents／Workflows、素材、能力提案、趋势分析、视频质量、Qwen图像／视频。只供回归。 |
| 早期原型 | 根目录`index.html`是早期单文件原型，Vite应用不使用。 |
| 脚本 | `scripts/`下的check／compare／smoke脚本大多会调用付费模型，一般需要`--live`；seed／cleanup／repair／backfill和部分导入脚本会写数据。运行前先读`--help`，不要为了“准备环境”运行写数据的脚本。 |

## 10. 文档怎么用

[文档索引](README.md)按“当前／操作／设计／历史／回归记录”分组。设计文档和历史文档保留当时的方案与实验，文首注明了状态。

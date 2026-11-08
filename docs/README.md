# 文档导航

[返回项目首页](../README.md)

先按你要完成的事情选择文档，不必从头读完。**当前状态以[项目总览](project-overview.md)为准**，每轮完成情况与验证限制见[状态记录](status-and-todo.md)，决定的来历见[PRD](product-requirements.md)的日期条目。设计文档中的计划不等于已经上线；标为历史的文档只用于了解演变。

## 当前

| 文档 | 内容 |
| --- | --- |
| [项目总览](project-overview.md) | 当前产品决定、模型、架构、数据流、完成度、测试基线、本机数据与遗留代码 |
| [路线图](roadmap.md) | 按优先级排列的下一步和待用户决定的事项 |
| [状态记录](status-and-todo.md) | 每轮完成项、测试、已知限制和下一步，按日期倒序 |
| [产品需求](product-requirements.md) | 按日期记录的产品与交互决定；文末的 2026-08 基线已不维护 |
| [Claude Code 开发交接](claude-code-handoff.md) | 2026-11-07 接手时的阅读顺序与注意事项 |

## 安装与操作

| 文档 | 内容 |
| --- | --- |
| [开发与验证](development.md) | 启动（含开发库演示实例）、模型配置、测试命令的统一出处、真实调用脚本、内部入口 |
| [本地安装](local-installation.md) | 主应用、固定版本 MediaCrawler、补丁、扫码登录与常见故障 |
| [数据交接](data-handoff.md) | 轻量数据包、可信配置交付、恢复与验收 |
| [离线导入](offline-import.md) | 旧浏览器脚本、JSON schema、MediaCrawler 输出与离线封面包 |
| [档案内预写示例](oracle-showcases.md) | 四份真实档案的账号认识、读者候选和笔记讨论；查看不调用模型 |
| [发布检查](release-checklist.md) | 提交或发布前的检查步骤（2026-08 编写，带日期的旧结论不是当前结果） |

## 业务设计

这些文档记录各模块的设计取舍与演变，文首注明了哪些部分已被后续决定取代。

| 文档 | 内容 |
| --- | --- |
| [账号诊断](account-diagnosis-design.md) | 账号认识、关键词、优势与内容表现复盘 |
| [人机共创](creator-writing-collaboration-design.md) | 单助手、作者自选参考、局部改写与人工采用；旧多角色方案保留为历史 |
| [笔记选择与单助手创作改造](creator-workspace-refinement-plan.md) | 单助手、统一笔记选择、数据时间展示与分阶段账号报告 |
| [模拟读者](simulated-fan-model-design.md) | 人物候选、手动收录、画像编辑和冻结快照 |
| [受众 Panel 四阶段计划](audience-panel-four-stage-plan.md) | 建立画像、检索组队、试读与回应、反馈改稿 |
| [Agent Runtime 与上下文架构](agent-runtime-architecture.md) | 业务模块、任务包、消息、状态和持久化边界 |
| [本地导入集成](xhs-local-import-integration.md) | 主页导入与 MediaCrawler 适配链路 |
| [模拟方法](audience-simulation-methods.md) | 人物发现、行为案例和状态化互动的方法借鉴 |

## 回归与实验记录

带日期的同稿回放和模型对照，保留原始失败、对照和取舍。处理创作质量前先读。

| 文档 | 内容 |
| --- | --- |
| [读者模拟回测](reader-simulation-backtest-20261108.md) | 2026-11-08 用已发布笔记的真实评论检验读者模拟，并与直接预测评论对照 |
| [等待与失败统计](wait-and-failure-stats-20261107.md) | 2026-11-07 用已保存记录统计诊断、模拟、创作各阶段耗时与失败类型，并给出优化顺序 |
| [DeepSeek 创作回归](deepseek-writer-regression-20261016.md) | 2026-10-16 切换 DeepSeek 后的创作回归与格式兼容 |
| [作者要求变成经历](creator-author-request-boundary-20261017.md) | 作者要求被写成亲历的同稿回放 |
| [两账号完整创作路径](creator-end-to-end-review-20261017.md) | 完整创作路径实测与增强取舍 |
| [推断事实化回归](creator-inference-facts-regression-20261017.md) | 推断被写成事实的回放与局部事实编辑 |
| [改稿去重回归](creator-revision-dedup-20261017.md) | 第二轮改稿的上下文去重与单次生成 |
| [事实来源回归](creator-source-attribution-regression-20261017.md) | 读者处境被写成作者亲历的归属问题 |
| [四账号回归](four-account-regression.md) | 2026-10-09 跨账号 Panel 样例（Qwen 时期） |
| [创作者链路验收](creator-journey-acceptance.md) | 2026-09-27 真实 Qwen 与公开界面验收 |

## 历史

以下文档描述的是早期方案，已被后续实现取代，不作为当前依据。

| 文档 | 内容 |
| --- | --- |
| [产品设计基线](product-design.md) | 2026-09 的资产、能力、工作流与内部工作台设计 |
| [创作者聚焦版执行手册](creator-focused-v2-execution-manual.md) | 2026-09 公开产品改造范围与阶段验收 |
| [创作者体验迭代](creator-experience-iteration.md) | 2026-09 导航、账号、选题和创作体验的阶段记录 |
| [架构审查](architecture-review.md) | 2026-08 的架构问题与工程优先级 |
| [能力调优计划](pm-capability-tuning-plan.md) | 2026-08 内部能力调优工具规划 |
| [模拟研究](audience-simulation-research.md) | 2026-10-01 文献来源、上下文审计与研究方案 |
| [归档索引](backup/README.md) | 原型审计、早期迁移、资产模型、Context Access Layer 与能力目录 |

根目录 `index.html` 是早期单文件原型，打开方法见[开发与验证](development.md)。

## 维护约定

- 当前状态变化时更新[项目总览](project-overview.md)；新的待办或优先级变化写进[路线图](roadmap.md)；每轮过程写进[状态记录](status-and-todo.md)。
- 安装与复现步骤放操作文档，测试命令只在[开发与验证](development.md#免费自动检查)维护一份，其他文档链接过去。
- 业务取舍放设计文档；方案被取代时在文首标注，不删除历史。
- 新增文档补到本索引的对应分组。自动化测试、界面验收和模型内容质量分别报告。

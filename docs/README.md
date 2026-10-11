# 文档导航

[返回项目首页](../README.md)

先按你要完成的事情选择文档，不必从头读完。**当前产品口径以 PRD 中最新决定为准，完成情况与验证限制以状态记录为准**；设计文档中的计划不等于已经上线。

## 安装、交接与复现

| 文档 | 内容 |
| --- | --- |
| [本地安装](local-installation.md) | 主应用、固定版本 MediaCrawler、补丁、扫码登录与常见故障 |
| [数据交接](data-handoff.md) | 轻量数据包、可信配置交付、恢复与验收 |
| [开发与验证](development.md) | 启动、模型配置、测试、付费验证、内部入口与旧原型 |
| [档案内预写示例](oracle-showcases.md) | 四份真实档案的账号认识、读者候选和笔记讨论；查看不调用模型 |
| [离线导入](offline-import.md) | 旧浏览器脚本、JSON schema、MediaCrawler 输出与离线封面包 |
| [发布检查](release-checklist.md) | 提交或发布前检查；其中带日期的旧验收结论不是本轮验证结果 |

## 产品与当前进展

| 文档 | 内容 |
| --- | --- |
| [产品需求](product-requirements.md) | 当前功能与交互决定，优先看文首最新更新 |
| [笔记选择与单助手创作改造](creator-workspace-refinement-plan.md) | 单助手、自选原笔记／分析参考、统一笔记选择、数据时间展示与分阶段账号报告；同时列明数据合并和内容质量的剩余限制 |
| [状态与待办](status-and-todo.md) | 每轮完成项、测试、已知限制和下一步交接 |
| [创作者聚焦版执行手册](creator-focused-v2-execution-manual.md) | 公开产品的改造范围、流程与阶段验收 |
| [产品设计基线](product-design.md) | 资产、能力、工作流及保留的内部工作台设计 |
| [创作者体验迭代](creator-experience-iteration.md) | 导航、账号、选题和创作体验的阶段记录 |

## 业务设计

| 文档 | 内容 |
| --- | --- |
| [账号诊断](account-diagnosis-design.md) | 账号认识、关键词、优势与内容表现复盘 |
| [人机共创](creator-writing-collaboration-design.md) | 单助手、作者自选原笔记／分析参考、局部改写与人工采用；旧多角色方案保留为历史 |
| [模拟读者](simulated-fan-model-design.md) | 人物候选、手动收录、画像编辑和冻结快照 |
| [受众 Panel 四阶段计划](audience-panel-four-stage-plan.md) | 建立画像、检索组队、试读与回应、反馈改稿 |
| [模拟方法](audience-simulation-methods.md) | 人物发现、行为案例和状态化互动的方法借鉴 |
| [模拟研究](audience-simulation-research.md) | 文献来源、上下文审计与研究性方案 |

早期文档保留过 Top 3、自动收录和多角色创作等方案，不能据此覆盖最新决定：模拟默认三个空槽且可增加，候选由作者手动收录；公开创作的新会话使用单助手与左聊右稿，作者可添加同账号的原笔记、账号分析和受众分析记录，默认不添加额外参考，也不自动读取全账号历史。旧多角色历史只读保留。账号／已发布笔记／创作共用一级受众模拟入口，结论用途各不相同。

当前状态（2026-10-11）：统一笔记选择已覆盖分析、模拟和创作参考；页面显示已有观察时间，缺少时回退为导入时间，不冒称最新采集时间。重复导入已修复空评论保留和合法零值，但字段级合并、非空评论增量合并及采集端观察时间仍待完善。账号报告已默认使用“整体认识 → 代表作精读 → 汇总”的增强流程，主要结论直接可读，原文按需查看。

功能可用不等于模型质量全部通过。账号报告仍有过度概括和关系误读，单助手的写作自然度与事实保持也需继续验证；详见[最新状态](status-and-todo.md)与[创作限制](creator-workspace-refinement-plan.md#55-当前限制与验收结论)。

## 工程与质量验证

- [Agent Runtime 与上下文架构](agent-runtime-architecture.md)：业务模块、任务包、消息、状态和持久化边界。
- [架构审查](architecture-review.md)：架构问题、已解决事项与工程优先级。
- [本地导入集成](xhs-local-import-integration.md)：主页导入与 MediaCrawler 适配链路。
- [四账号回归](four-account-regression.md)：跨账号样例、真实模型观察及尚未通过的质量问题。
- [创作者链路验收](creator-journey-acceptance.md)：带日期的真实 Qwen 与公开界面验收记录。
- [能力调优计划](pm-capability-tuning-plan.md)：内部能力调优工具的阶段规划。

自动化测试、界面验收和模型内容质量是不同层面的检查；请以各记录注明的样本、日期和限制理解结果。

## 历史资料

[归档索引](backup/README.md)保留原型审计、早期迁移、资产模型、Context Access Layer 与能力目录的演变，不作为当前实现依据。根目录 `index.html` 是早期单文件原型，打开方法见[开发与验证](development.md)。

维护约定：安装与复现步骤放操作指南，业务取舍放设计文档，每轮进展放状态记录。README 保持简洁；新增文档补到本索引，过期方案明确标注历史状态。

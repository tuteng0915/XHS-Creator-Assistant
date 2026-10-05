# 文档索引

最新实施进展与限制先读 [status-and-todo.md](status-and-todo.md)，功能口径读 [product-requirements.md](product-requirements.md)。[creator-experience-iteration.md](creator-experience-iteration.md) 保留四组导航、账号创建、选题与创作助手的阶段设计；其中早期 Top 3 不是当前人数上限：现在默认三个槽位、可继续增加。按选题推荐读者已接通后端、真实 Qwen、过期／采用校验及公开入口的统一确认页；历史页已展示冻结的推荐／实际名单，旧记录缺姓名时不从当前资产补造。公开创作助手编辑 Topic 正文，独立 Draft 仍是内部兼容功能，不在本轮重新开放。

当前产品已经进入“创作者聚焦版 V2”改造。公开产品范围、账号空间模型、URL 导入链路和分阶段验收以 [creator-focused-v2-execution-manual.md](creator-focused-v2-execution-manual.md) 为准；旧的开发者工作台说明只用于理解保留代码和内部调试能力。

顶层只保留当前仍然有效的产品、设计、架构和实现文档。已经完成或明显过时的迁移文档统一放在 `docs/backup/`，作为历史参考，不再作为当前实现依据。

## 推荐阅读顺序

1. `creator-focused-v2-execution-manual.md` — 当前公开版的产品范围、交互原则、默认值和实施状态。
2. `product-design.md`、`product-requirements.md` — 原有内部工作台的功能基线及保留实现；公开版差异以 V2 手册为准。
3. `pm-capability-tuning-plan.md` — 内部能力调优界面的历史规划。
4. `status-and-todo.md` — 查看当前完成状态、明确限制和下一步 TODO。
5. `architecture-review.md` — 查看当前架构风险、已解决问题和工程优先级。
6. `release-checklist.md` — 准备提交 GitHub 或打 tag 前做发布检查。

## 当前有效文档

- `audience-panel-four-stage-plan.md` — 画像、检索组队、独立试读与回应、创作反馈四阶段改造计划；含字段、Prompt 分工、来源借鉴程度及验收。可选任务协议、快照和关闭讨论的执行底座已完成，页面模式选择、改稿反馈及同组复测待实现。
- `creator-writing-collaboration-design.md` — 账号复盘如何用于人机共创的待实施设计，涵盖外部 Skill 借鉴、经验与偏好、改稿确认、字段及分阶段验收；不代表当前功能已上线。
- `creator-journey-acceptance.md` — 09-27 真实 Qwen 与公开页面链路验收、工程修复及尚未解决的内容质量问题。
- `account-diagnosis-design.md` — 账号诊断的设计与首轮实施记录：先帮助创作者认识账号，再进入选题；明确字段、证据边界和后续验证方法。
- `audience-simulation-methods.md` — few-shot 受众发现、行为案例、状态化评论互动的文献借鉴与轻量实现记录；当前不要求效果实验。
- `simulated-fan-model-design.md` — 当前简短人物字段、资产编辑、模拟快照和按选题推荐读者的实现及剩余切片；后半部分保留未启用的原型匹配和多维画像备选设计。
- `audience-simulation-research.md` — 受众模拟的文献依据、改动前审计及首轮证据化实现；保留的效果实验提案暂不执行。
- `local-installation.md` — 从 Git 克隆后的本地安装、固定版本 MediaCrawler、封面补丁、浏览器登录及故障排查。
- `product-design.md` — 当前产品的主设计说明，集中解释功能全貌、设计思想、内容资产、能力资产、workflow、Context Access Layer、Demo/Live、多模态和设计边界。
- `product-requirements.md` — 基于当前实现反向整理的产品 PRD，描述产品定位、资产模型、核心流程、非目标和验收清单。
- `status-and-todo.md` — 当前实现状态、已完成事项、明确限制、部署/API 路径说明和 TODO。
- `pm-capability-tuning-plan.md` — 面向施琦姗实际调优 Skill / Agent / Workflow 的前端能力建设计划。
- `architecture-review.md` — 当前架构 review 与优先风险。
- `release-checklist.md` — GitHub 发布前检查清单，包括敏感信息、自动化测试、真实 API smoke 和建议 tag。

## 历史参考

- `backup/current-prototype.md` — 原始单文件 `index.html` 原型审计。
- `backup/migration-plan.md` — 从原型迁移到 React/FastAPI/SQLite/LangGraph 的早期计划。
- `backup/workspace-model.md` — 引入能力资产之前的早期 workspace 模型。
- `backup/agent-context-access.md` — Context Access Layer 的早期设计。
- `backup/input-asset-model.md` — 内容输入资产抽象的早期设计。
- `backup/llm-context-audit.md` — 早期 LLM 调用上下文审计。
- `backup/skill-catalog.md` — Skill / Agent / Workflow 能力资产早期模型。
- `backup/product-evolution.md` — 后续产品方向和路线的历史整理。

维护规则：如果某个文档描述的是已经完成的迁移切片，或模型已经不再符合当前代码，就移动到 `docs/backup/`，不要继续放在顶层误导后续实现。

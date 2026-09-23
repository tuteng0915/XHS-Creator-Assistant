# 文档索引

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

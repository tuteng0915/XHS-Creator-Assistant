# 文档索引

顶层只保留当前仍然有效的产品、架构和实现文档。已经完成或明显过时的迁移文档放在 `docs/backup/`，作为历史参考。

## 当前有效文档

- `product-requirements.md` — 基于当前实现反向整理的产品 PRD，描述产品定位、资产模型、核心流程、非目标和验收清单。
- `status-and-todo.md` — 当前实现状态、已完成事项、部署/API 路径说明和 TODO。
- `architecture-review.md` — 当前架构 review 与优先风险。

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

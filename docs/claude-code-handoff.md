# Claude Code 开发交接

2026-11-07 从 Codex 交给 Claude Code。交接时写的长文档已拆进长期维护的文档里，本文只保留阅读顺序和接手时容易踩的坑。

## 读什么

1. [项目总览](project-overview.md)：当前产品决定、模型、架构、数据流、完成度、测试基线、本机数据与遗留代码。
2. [路线图](roadmap.md)：按优先级列出的下一步，以及需要用户决定的事项。
3. [开发与验证](development.md)：启动（含[开发库演示实例](development.md#使用开发库启动演示实例)）、模型配置、测试命令、真实调用脚本。
4. 改某个模块前，再读对应的设计文档和[状态记录](status-and-todo.md)中最新的相关条目。

优先级：最新用户消息 → 当前代码与 PRD 最新条目 → 总览与状态记录 → 设计文档。旧文档中的 Qwen 默认、自动收录、三专家创作等内容都属于历史方案。

## 接手注意

- DeepSeek 凭据只在 `/Users/tut/.codex/worktrees/account-reading-quality/SqsAgent/.env.local` 里，不要清理那个旧工作树，也不要输出、复制凭据。
- 主库 `data/app.sqlite3` 与开发库分开；开发库有迁移或数据整理之前先备份。
- `docs/assets/promo/`、`output/` 是用户材料，未纳入 Git，保留原样。
- 提交署名 `littlelittlesheep <shiqishan319@gmail.com>`，新分支用 `codex/` 前缀。提交、推送、部署和重启都要等用户本轮明确要求。
- 2026-11-07 接手核对的结果（后端一项断言修正、三视口实屏回归）记在状态记录当天的条目中。

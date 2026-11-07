# 小红书创作助手：开发接手入口

先读[项目总览](docs/project-overview.md)（当前状态的唯一汇总）和[路线图](docs/roadmap.md)，再按本次任务阅读相关代码。启动、配置和测试命令以[开发与验证](docs/development.md)为准；接手时的注意事项见[Claude Code 开发交接](docs/claude-code-handoff.md)。

## 开始工作

1. 查看最新用户消息、`git status --short`、`git diff`。
2. 阅读 `docs/status-and-todo.md` 文首与 `docs/product-requirements.md` 的相关最新条目。两者有大量历史记录，按日期区分；最新用户决定优先。
3. 选择一项明确任务，说明问题、验收和测试方式，再修改。
4. 完成后若改变了当前状态（产品决定、完成度、测试基线、路线图条目），同步更新总览或路线图。

## 当前约定

- 产品正式名称是“小红书创作助手”；`SqsAgent`仅为已有目录名。
- 默认文字、账号诊断、创作模型均为DeepSeek，配置模型ID为`deepseek-flash`，非思考模式。Claude Code是开发工具，不因此把产品模型切成Claude。
- 公开创作是单助手、作者自选参考、人工采用与保存；历史多人协作保持可读。
- 受众候选由作者手动收录；受众模拟是独立一级入口，包含账号、已发布笔记、创作三个类别。
- 帮助在品牌标题右侧，菜单只有两个并排按钮；页面说明用标题或字段旁的内联i。避免恢复独立帮助顶栏和常驻小字。
- 保留用户未提交文件、原笔记、已编辑人物、稿件和历史。模型调用使用冻结输入，异步返回不得覆盖用户后来修改。
- 改动优先用临时数据库验证。主库、开发库和冻结提交包分开；启动前确认路径、端口和已有任务。部署／重启、commit／push按用户本轮要求执行。
- 凭据只从本地忽略配置读取，不输出或提交。未经明确要求不抓新数据、不扩大付费实验、不调用Anthropic官方API或视频生成。
- 提交前核对署名`littlelittlesheep <shiqishan319@gmail.com>`；新分支沿用`codex/`前缀。署名不代表推送认证账号。

## 验证与交付

- 前端：`npm --prefix frontend test -- --maxWorkers=2`、`npm --prefix frontend run lint`、`npm --prefix frontend run build -- --outDir /private/tmp/xhs-check-build`。
- 后端：在`backend/`运行`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -m pytest -o addopts='' -q -p no:cacheprovider`，先选相关测试，再按风险跑全量；`.venv/bin/ruff check --no-cache app tests`（`tests`中有4处既有E501）。与[免费自动检查](docs/development.md#免费自动检查)保持一致。
- 自查`git diff --check`；界面变化补浏览器检查，记录实际覆盖的页面／视口。测试通过、视觉体验和模型质量分别报告。
- 在`docs/status-and-todo.md`补完成项、测试命令与结果、限制和下一步；改变产品决定时同步PRD。
- 反馈简洁、具体。模型质量比较保留原始输出、等待时间、调用次数和得失，让用户参与判断。

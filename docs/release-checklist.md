# GitHub 发布前检查清单

更新日期：2026-08-24

本文档用于把当前版本提交到 GitHub 前做最后确认。它不是产品路线图，路线图见 `product-requirements.md` 和 `status-and-todo.md`。

## 当前版本结论

当前版本可以作为一个稳定 checkpoint：

- 主应用已经从单文件 HTML 原型迁移到 React + TypeScript + FastAPI + SQLite + LangGraph；
- 内容资产、能力资产、workflow 调用、conversation、AssetProposal、媒体资产和小红书离线导入链路已经形成闭环；
- Qwen 文本模型、agent conversation schema 和图片理解 media skill 已通过真实 smoke test；
- API key 保存在本地 `backend/.env.local`，该文件已被 git ignore；
- 当前不包含 Docker、认证、多租户、Redis、Postgres 或部署基础设施。

## 发布前必须做

### 1. 确认工作区干净

```bash
git status --short
```

期望没有未提交变更；如果有，只能是明确准备提交的文档或代码。

### 2. 确认本地 env 不会提交

```bash
git check-ignore -v .env.local backend/.env.local
```

期望命中 `.gitignore`。

### 3. 扫描明显密钥

```bash
rg -n 'sk-[A-Za-z0-9_.-]|ANTHROPIC_API_KEY|QWEN_API_KEY|DASHSCOPE_API_KEY' \
  . \
  --glob '!frontend/node_modules/**' \
  --glob '!backend/.venv/**' \
  --glob '!backend/.env.local' \
  --glob '!.env.local'
```

文档里的占位符和变量名可以保留；真实 key 不应出现在任何 tracked 文件里。

### 4. 处理历史敏感文件

当前树已经删除 `backup/key`，并在 `.gitignore` 中显式忽略 `backup/key`。

但这个文件曾经在 git 历史里出现过。如果它曾经包含真实有效 key，公开推送到 GitHub 前必须至少做一项：

- 轮换/作废对应 key；
- 或用 `git filter-repo` / BFG 重写历史后再推送到公开仓库。

如果只是推送到私有仓库，也建议轮换旧 key，避免后续误转公开。

### 5. 跑自动化检查

前端：

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

后端：

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
PYTHONPATH=backend backend/.venv/bin/python -m ruff check backend/app backend/tests
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend/app
```

### 6. 按需跑真实 API smoke

这些命令会消耗真实模型额度，不进入常规 CI：

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/smoke_model_api.py \
  --env-file backend/.env.local \
  --operation pain_points

PYTHONPATH=backend backend/.venv/bin/python scripts/smoke_model_api.py \
  --env-file backend/.env.local \
  --operation agent_chat

PYTHONPATH=backend backend/.venv/bin/python scripts/smoke_qwen_media.py image-understand \
  --env-file backend/.env.local \
  --image-url https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg
```

当前最近一次结果：三项均通过。

## 发布后仍然不是目标

当前版本仍不承诺：

- 认证和权限；
- 多租户；
- 部署基础设施；
- 通用 workflow/nodegraph editor；
- 任意代码工具调用；
- OCR / ASR / 长视频语义切片；
- 自动抓取视频平台内容。

## 建议 tag

如果要打版本 tag，可以使用：

```bash
git tag v0.1-creator-workspace-checkpoint
```

打 tag 前应先完成上述敏感信息检查。

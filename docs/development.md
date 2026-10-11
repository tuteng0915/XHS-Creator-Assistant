# 本地开发、模型配置与验证

本文面向开发与回归测试。首次安装、MediaCrawler 固定版本及补丁、真人扫码和数据恢复见[本地安装指南](local-installation.md)；产品入口见[项目 README](../README.md)。以下命令面向 macOS/Linux，所有标为“仓库根目录”的命令都从包含 `backend/`、`frontend/` 和 `scripts/` 的目录运行。

主应用使用 React、TypeScript、FastAPI、SQLite、LangGraph 和 Server-Sent Events。数据库、上传文件、模型配置、浏览器登录态及本地样本不随 Git 分发。普通开发和查看已有资产不需要 MediaCrawler；主页 URL 抓取才需要额外安装。

## 本地运行

### 后端与 ffmpeg

主应用要求 Python 3.11+。首次安装主应用依赖，在仓库根目录执行：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install './backend[dev]'
```

这不安装 MediaCrawler。需要主页 URL 导入时，另按[抓取依赖安装](local-installation.md#2-安装抓取依赖)安装 `xhs` extra、浏览器和独立 MediaCrawler 环境。

在终端一中，从仓库根目录启动后端：

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端会读取本地配置并初始化或迁移 SQLite 数据库。默认数据库是仓库下的 `data/app.sqlite3`，上传目录是 `data/uploads/trends`；已有数据不要随意删除或用另一份数据库覆盖。

本地上传视频的预览抽帧需要后端所在机器安装 `ffmpeg`。在任意目录检查：

```bash
ffmpeg -version
```

若不在后端进程的 PATH 中，在启动后端的 shell 或本地 env 文件设置：

```bash
export FFMPEG_PATH=/absolute/path/to/ffmpeg
```

### 前端与内部工作台

前端需要 Node.js 和 npm，建议 Node.js 22.12 或更新的 22.x。在终端二中，从仓库根目录运行：

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

打开 `http://127.0.0.1:5173/`。前端业务请求使用相对路径 `/api/...`，开发时由 Vite 代理到 `http://127.0.0.1:8000`，因此前后端需要同时运行。

旧开发者工作台和三个分析流程仍可用于内部回归：`http://127.0.0.1:5173/?internal=1`。这个参数只切换界面，不是权限控制。

### 健康检查

| 地址 | 能验证什么 |
| --- | --- |
| `http://127.0.0.1:5173/health` | 前端健康页面能否加载；不主动验证后端或模型 |
| `http://127.0.0.1:8000/api/health` | 后端能否返回健康响应；不验证模型或抓取服务 |
| `http://127.0.0.1:8000/docs` | 后端 OpenAPI 交互文档 |

模型连通性需单独运行下文的真实模型 smoke；抓取可用性需完成真人登录验收，不能由 health 返回正常来推断。

## 模型配置

主应用的 live generation 统一经后端模型代理调用，浏览器不持有模型 API key。默认 provider 是 Qwen / DashScope 的 OpenAI-compatible API。

### Qwen 默认配置与本地文件

在启动后端的 shell 设置，或写入仓库根目录 `.env.local`：

```bash
export MODEL_PROVIDER=qwen
export QWEN_API_KEY=替换为自己的密钥
export QWEN_MODEL=qwen-plus
export QWEN_PROFILE_MODEL=qwen3.8-max
# 可选；以下是默认地址
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

也支持 `backend/.env.local`。后端和下文 smoke 脚本会读取本地文件，不必手动 `source`；`KEY=value` 与 `export KEY=value` 均可。优先级为：已有进程环境变量 → 根目录 `.env.local` → `backend/.env.local`，后读取的值不会覆盖已有值。修改后重启后端。

两个本地文件均被 Git 忽略，不要提交、公开分享或把完整密钥贴进日志。若 shell 中残留旧配置，修改文件也不会覆盖该环境变量。

兼容别名如下；设置了对应 `QWEN_*` 变量时以它为准：

| 主要变量 | 兼容别名 |
| --- | --- |
| `QWEN_API_KEY` | `DASHSCOPE_API_KEY` |
| `QWEN_BASE_URL` | `DASHSCOPE_BASE_URL` |
| `QWEN_DASHSCOPE_BASE_URL` | `DASHSCOPE_API_BASE_URL` |

`MODEL_PROVIDER=dashscope` 也进入 Qwen 文本调用路径；通常保持默认 `qwen` 即可。

`QWEN_PROFILE_MODEL` 默认 `qwen3.8-max`，只影响账号报告的 PROFILE 操作，其他文本操作仍用 `QWEN_MODEL`。设为空字符串可显式继承总模型。PROFILE 使用 Qwen3.8 系列时发送 `enable_thinking=false`，与本轮非思考验证一致（[官方参数说明](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)）；不额外增加模型调用或自动降级。端点不支持所选模型时会明确报错，应检查配置，而不是悄悄换模型。Anthropic 兼容路径不受这一变量影响。

### 三阶段账号报告候选

`ACCOUNT_REPORT_MODE` 默认为 `source_led`。在隔离测试服务中显式设为 `staged`，结构化所选笔记会走“整体阅读 → 最多三篇并行精读 → 汇总”，至多五次 Qwen 请求，仍使用 `QWEN_PROFILE_MODEL`。普通旧文本输入保持原路径；该候选仅支持 Qwen/dashscope，无自动回退。此设置不会迁移旧报告；不要为试验自动重启用户正在使用或已关闭的服务。

前端以阶段摘要显示进度，最终报告保留代码绑定的原标题与原句。v3.1 精读以本篇片段 ID 选择原文，一组最多 6 个片段并分别保存位置，不把不连续原句拼接；允许同一原文支撑不同判断。失败停止本次 PROFILE、不自动重试，恢复粒度仍是整个 PROFILE，不能接着某篇精读续跑。分析 SSE 重连发送最新快照，序号接在客户端游标之后，不是历史事件的逐条重放。质量状态与已知限制见 [状态记录](status-and-todo.md)。

复现使用已有检查报告的冻结样本，不读取当前业务库、不抓取：

```bash
backend/.venv/bin/python scripts/check_staged_account_report.py \
  --input-from /path/to/previous/report.json --read-note-ids n1,n3
```

默认只预览范围，零模型请求、零文件写入。明确加 `--live --output data/evals/staged-check/new-case` 才执行；输出目录必须不存在。`--read-note-ids` 可固定 1～3 篇代表作做对照，省略时由整体阅读选择。报告保留每步输入、原响应、耗时、用量和错误，成败都保存；诊断含私人笔记，放在被忽略的私有目录，不提交。被取消请求可能已在服务端执行，没有返回用量时不可按零费用计算。

### 账号画像读取超时

Qwen 账号画像的单次网络读取超时默认是 180 秒，可在本地 env 文件调整：

```bash
export QWEN_PROFILE_READ_TIMEOUT_SECONDS=180
```

值必须是 1～300 的整数。此设置只影响 Qwen 路径（`MODEL_PROVIDER=qwen` 或 `dashscope`）的账号画像操作；其他文本操作以及连接、写入、连接池等待仍是 90 秒，不因此增加自动重试。它不是整个 workflow 的总时限。

旧验证曾观察到完整画像响应约需 99 秒，这只是历史样本，不是响应时间保证。只读画像检查脚本 `scripts/check_account_profile.py` 使用独立的 `--read-timeout-seconds` 参数，默认仍为 90 秒，方便复现旧设置；详见下文[画像输入复现](#画像输入复现)。

### Anthropic-compatible 文本端点

这是显式兼容配置，不是默认路径。在启动后端的 shell 或本地 env 文件设置：

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=替换为自己的密钥
export ANTHROPIC_MODEL=替换为端点支持的模型
export ANTHROPIC_BASE_URL=https://your-qwen-host/apps/anthropic
# 仅在需要指定精确 messages 地址时设置
export ANTHROPIC_MESSAGES_URL=https://your-qwen-host/apps/anthropic/v1/messages
```

未设置 `ANTHROPIC_MESSAGES_URL` 时，后端会将以 `/apps/anthropic` 结尾的 base URL 推导为 `/apps/anthropic/v1/messages`；其他 base URL 则追加 `/messages`。这些自定义域名是占位符，需替换为自己有权限使用的服务。

### Qwen 多模态配置

`ANTHROPIC_*` 只供文本模型的 Anthropic-compatible 路径使用。图片/视频理解与生成始终走 Qwen / DashScope media skills；即使共用同一密钥，也要额外设置 Qwen 变量。例如自定义兼容服务：

```bash
export QWEN_API_KEY=替换为自己的密钥
export QWEN_BASE_URL=https://your-qwen-host/compatible-mode/v1
export QWEN_DASHSCOPE_BASE_URL=https://your-qwen-host/api/v1
```

使用默认 DashScope 服务时，可省略两个地址变量；`QWEN_DASHSCOPE_BASE_URL` 默认是 `https://dashscope.aliyuncs.com/api/v1`。文本兼容端点可用不代表该服务同时支持多模态接口。

## 自动检查与真实调用

先做不请求真实模型的自动检查，再按需要运行 live 检查。`smoke_model_api.py` 和 `smoke_qwen_media.py` 没有免费预览模式，直接运行就会尝试真实请求，可能产生费用。报告中的请求次数不等同于已核实的账单；失败或超时也不能视为免费。

### 免费自动检查

前端检查，从仓库根目录执行：

```bash
cd frontend
npm run lint
npm run test
npm run build
```

后端检查，在另一个终端从仓库根目录执行：

```bash
cd backend
.venv/bin/python -m ruff check app tests
.venv/bin/python -m pytest
```

自动测试使用假响应或 mock，不需要真实模型密钥。后端 pytest 会将应用导入时的默认初始化及各项测试数据隔离到临时目录；不要用真实模型 smoke 替代这组测试。

### 文本模型 smoke（实际调用）

无需启动前端或后端服务。从仓库根目录执行，默认检查 `pain_points` 操作：

```bash
backend/.venv/bin/python scripts/smoke_model_api.py
```

也可检查 `agent_chat`；这是另一条真实请求，按需选择，不必每次全部运行：

```bash
backend/.venv/bin/python scripts/smoke_model_api.py --operation agent_chat
```

脚本使用与工作流、Agent 对话相同的模型适配器。支持 `--env-file /absolute/path/to/local.env`；已有 shell 变量仍优先，后端配置加载仍会补充默认本地 env 文件中尚未设置的变量。输出会包含模型元数据、生成结果以及掩码后的密钥片段，分享日志前仍需检查敏感信息。

### 多模态 smoke（实际调用）

例如图片理解，在仓库根目录执行以下完整子 shell：

```bash
(
  smoke_runtime="$(mktemp -d)" || exit 1
  trap 'rm -rf -- "$smoke_runtime"' EXIT
  DATABASE_PATH="$smoke_runtime/bootstrap.sqlite3" \
  UPLOAD_DIRECTORY="$smoke_runtime/bootstrap-uploads" \
    backend/.venv/bin/python scripts/smoke_qwen_media.py image-understand \
      --image-url https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg
)
```

脚本的实际测试 workspace、数据库及上传目录默认是临时的；上述环境变量还隔离了导入 `app.main` 时创建默认应用的初始化，避免碰到正式数据库。临时测试产物会清理。除非确实需要保留输出并已选定独立路径，不要指定 `--database-path` 或 `--upload-directory`。

脚本还支持 `video-understand`、`image-generate`、`video-generate`。视频理解需 `--video-url` 或一个/多个 `--frame-url`；生成操作会调用实际生成服务。可用模型、权限、用量及费用需自行确认，图片理解成功不代表其他操作也可用。

### 工作流 API smoke

`scripts/smoke_live_workflows.py` 默认 `--mode demo`，通过进程内 FastAPI 路由检查分析工作流，不需要另启服务。它同样需要隔离导入阶段的默认应用。在仓库根目录运行免费 demo：

```bash
(
  smoke_runtime="$(mktemp -d)" || exit 1
  trap 'rm -rf -- "$smoke_runtime"' EXIT
  DATABASE_PATH="$smoke_runtime/bootstrap.sqlite3" \
  UPLOAD_DIRECTORY="$smoke_runtime/bootstrap-uploads" \
    backend/.venv/bin/python scripts/smoke_live_workflows.py --mode demo
)
```

`--workflow` 可选 `all`、`account`、`trend`、`video`，默认 `all`。将 `--mode demo` 改成 `--mode live` 会对配置的 provider 发起多阶段真实调用，可能产生费用；`--timeout` 是等待工作流空闲的时间，默认 30 秒，真实模型检查需按需要显式增大，它不是模型读取超时。此脚本目前重新构造 Settings，未传递 `QWEN_PROFILE_READ_TIMEOUT_SECONDS` 的自定义值，画像读取使用 Settings 默认的 180 秒；精确复现读取超时请使用下文画像检查。

## 受众反应复现

`scripts/check_audience_reactions.py` 用同一文本检查不同模拟角色的反应，不是对真实粉丝行为或比例的预测验证。以下命令均从仓库根目录运行，不需要启动后端。

### 免费预览

```bash
backend/.venv/bin/python scripts/check_audience_reactions.py
```

默认只展示测试文本、人工编写的角色和人工检查问题，不调用模型，也不初始化正式数据库。

### 完整流程检查（实际调用）

```bash
backend/.venv/bin/python scripts/check_audience_reactions.py \
  --live --output data/evals/reactions-run-01
```

只有显式加 `--live --output <新的报告目录>` 才会调用 Qwen。输出目录必须尚不存在，脚本拒绝覆盖。完整图检查的应用初始化与运行数据库均自动隔离到临时目录，正常结束或异常时清理，无需额外包裹环境变量。

### 复用已有角色与报名条件对照

已有受众分析检查报告需包含有效结果及角色 ID。以下命令免费预览所选角色，替换示例报告路径和 `GROUP_ID`：

```bash
backend/.venv/bin/python scripts/check_audience_reactions.py \
  --audience-from data/evals/audience-run-01/report.json \
  --group-ids GROUP_ID
```

`--audience-from` 和 `--group-ids` 必须一起提供；可选择 1～3 个不同的有效角色 ID。加 `--live --output data/evals/selected-reactions-run-01` 后，只检查这些角色的独立反应，不创建数据库、不运行讨论或汇总。

报名条件对照使用 `--task-pair`，必须恰好选择一位角色；不加 `--live` 仍是免费预览：

```bash
backend/.venv/bin/python scripts/check_audience_reactions.py \
  --audience-from data/evals/audience-run-01/report.json \
  --group-ids GROUP_ID --task-pair
```

加 `--live --output data/evals/task-pair-run-01` 后，固定这位角色的阅读经历，对比两种报名条件，最多两次独立反应调用；第一种未取得结构化响应时不会继续第二种。

报告建议保存在被 Git 忽略的 `data/evals/`，其中可能包含私人来源文本。结构校验通过不等于人物反应质量通过：仍需人工检查人物判断是否真的不同、是否追问正文已回答的问题、是否编造经历，以及沉默角色能否不强行留言。

## 画像输入复现

`scripts/check_account_profile.py` 可从已保存的 MediaCrawler 数据、已有检查报告、当前工作区或历史分析快照复现画像输入，不抓取、不创建数据库、不生成选题，也不重试。以下从仓库根目录执行，用已有报告免费预览：

```bash
backend/.venv/bin/python scripts/check_account_profile.py \
  --input-from data/evals/profile-run-01/report.json
```

真实检查仅调用一次 Qwen，需要新输出目录，并可明确设置本次读取超时：

```bash
backend/.venv/bin/python scripts/check_account_profile.py \
  --input-from data/evals/profile-run-01/report.json \
  --live --read-timeout-seconds 180 \
  --output data/evals/profile-recheck-01
```

也可用一个位置参数提供已保存的 MediaCrawler 原始数据目录。当前档案用 `--workspace-id WORKSPACE_ID --database data/app.sqlite3 --limit 5`；也可用 `--note-ids ID1,ID2` 指定所选篇目。要与旧好报告公平比较，使用 `--analysis-run-id RUN_ID --database data/app.sqlite3` 读取当时冻结的完整笔记；这一路不接受 limit/note-ids，不偷换成当前材料。四种来源模式只能选一，不加 `--live` 均为零模型调用。

报告分别保存配置模型、响应模型、提示版本/哈希、实际请求数、原始输出和编译结果；失败不重试。`--input-from` 会按当前输入契约重建请求，来源快照仍保持不变。报告包含私有原文，应留在被忽略的 `data/evals`；结构、引用身份和字面引用验证不能替代语义人工验收。

## 同源部署边界

前端构建继续请求相对路径 `/api/...`。若要在受控远程环境共享，应将页面和 API 放在同一个公开 origin，例如 `https://your-domain/` 与 `https://your-domain/api/...`，并由自己的部署层提供路由和访问保护。不要让访问者的页面依赖其本机 `localhost:8000`。

当前仓库没有 authentication、多租户、Docker、Redis、Postgres 或部署基础设施；`?internal=1` 也不提供鉴权。不要将包含账号、笔记和历史记录的服务直接无保护地暴露到公网。本节只说明部署约束，不是已验证的生产部署方案。发布前另读[发布检查清单](release-checklist.md)。

## 原始 HTML 原型

仓库根目录的 [`index.html`](../index.html) 是迁移前的单文件行为参考，不是当前 React 主应用，不需要构建。只将这个文件复制到临时隔离目录提供服务，避免把数据库、上传文件或本地配置所在的整个仓库暴露给静态服务器。

从仓库根目录执行以下完整子 shell；端口 8001 与默认后端端口错开：

```bash
(
  prototype_dir="$(mktemp -d)" || exit 1
  trap 'rm -rf -- "$prototype_dir"' EXIT
  cp index.html "$prototype_dir/index.html"
  python3 -m http.server 8001 --bind 127.0.0.1 --directory "$prototype_dir"
)
```

打开 `http://127.0.0.1:8001/index.html`，按 Ctrl+C 停止后会清理临时副本。原型 demo mode 不依赖外部服务；其 live mode 是浏览器直连 Anthropic、要求输入 API key 的历史行为，不要在原型中使用生产或共享密钥。当前主应用应使用上文的后端模型代理。

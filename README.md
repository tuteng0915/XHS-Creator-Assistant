# 创作者内容工作区

当前默认界面正在迁移为面向小红书创作者的聚焦版：导入主页 → 浏览笔记 → 账号诊断 → 选题 → AI 创作 → 受众模拟。公开界面采用单一左侧导航，账号之间分别保存材料和结果；不需要登录。

新版设计与验收标准见 [V2 执行手册](docs/creator-focused-v2-execution-manual.md)。旧开发者工作台和三个分析流程的代码、API、测试均保留，可用 `http://127.0.0.1:5173/?internal=1` 进行内部回归；这个参数只是界面模式，不是权限控制。

主页 URL 导入默认读取 10 条笔记，更多数量或全部读取在弹窗中设置。需要后端所在机器安装 MediaCrawler 及其浏览器依赖；可通过 `XHS_MEDIACRAWLER_DIRECTORY` 指定已有目录，默认 `data/external/MediaCrawler`。首次登录会在该机器打开浏览器，用户按提示扫码。本地导入任务已接入，远程扫码转发尚未实现；真正的平台读取需要单独做一次真人登录验收。

这个仓库包含两部分：原始的单文件 HTML 产品原型，以及已经迁移出来的创作者工作区应用。当前主应用使用 React、TypeScript、FastAPI、SQLite、LangGraph 和 Server-Sent Events；原始 `index.html` 只作为行为参考保留。

## 从 Git 安装

首次使用请按 [本地安装与 MediaCrawler 配置](docs/local-installation.md) 操作，包含主应用、模型配置、抓取依赖、浏览器登录和验收步骤。

如果要在另一台受信任电脑上还原**现有账号、笔记、图片及分析历史**，按下面的“把现有数据交给协作者”操作。Git 只还原代码，不还原这些被忽略的本地内容；模型配置要单独处理，小红书登录态不迁移。

**直接 clone 不会安装 MediaCrawler。** 它是 `data/external/MediaCrawler` 下被忽略的独立仓库，不是 Git 子模块，也不会由后端 pip 自动安装。我们固定上游提交并提供封面下载补丁；依赖环境、登录态、数据库和样本不放进 Git。无需把庞大的本地 `data/` 目录提交进来。

## 把现有数据交给协作者（推荐）

**代码走 Git，数据包私下发送。** 当前 `data/app.sqlite3` 是账号、笔记正文、选题、分析及对话等记录；`data/uploads/` 是已导入的封面、其他媒体及上传文件。两者要一起传：只传数据库会出现“文字在、图片打不开”。此方案不包含约 1 GB 的 MediaCrawler 环境、浏览器登录态、抓取原始缓存或旧备份。协作者只是浏览和继续使用现有资产时，**不必先安装 MediaCrawler，也不必重新爬这几个账号**；只有想从主页 URL 继续抓取时，才按[安装指南](docs/local-installation.md#2-安装抓取依赖)另行安装并在自己的电脑扫码。

原电脑先等正在进行的抓取、分析和生成完成，**停止后端**，再在仓库根目录执行：

```bash
tar -czf ../SqsAgent-creator-data.tar.gz data/app.sqlite3 data/uploads
tar -tzf ../SqsAgent-creator-data.tar.gz | head
```

将仓库上一级目录的 `SqsAgent-creator-data.tar.gz` 通过仅对协作者开放的渠道发送；微信传文件或私密网盘都可以，不要发到公开链接、Git 或聊天群。压缩包含笔记、评论及创作历史等私人数据，请按敏感资料对待。代码版本也告诉对方，可在仓库根目录用 `git rev-parse HEAD` 查看。

协作者按[本地安装指南](docs/local-installation.md#1-获取主应用)克隆并安装**主应用**后，先不要启动后端。将收到的压缩包放在仓库上一级目录，在新仓库根目录执行：

```bash
tar -tzf ../SqsAgent-creator-data.tar.gz | head
tar -xzf ../SqsAgent-creator-data.tar.gz
```

然后按上文分别启动后端和前端，检查账号列表、笔记正文与封面、分析历史是否能打开。解压会写入 `data/app.sqlite3` 和 `data/uploads/`；**如果对方已经有自己的数据，先备份，不能直接覆盖，也不能靠解压合并两个数据库。** 接收方的程序版本应与打包时相同或更新，后端启动时会应用缺失的数据库迁移。

上述命令默认不包含模型 API key，协作者可配置自己的 `.env.local`。双方明确约定共用密钥时，也可以将原电脑实际使用的 `.env.local` 或 `backend/.env.local` 按原相对位置加入私下交付包；接收方解压后程序会自动读取，整个包仅交给约定的可信协作者。若原电脑在 `.env.local` 里自定义了 `DATABASE_PATH`、`UPLOAD_DIRECTORY` 或 `DEFAULT_USER_ID`，默认命令不够用：需按[完整恢复说明](docs/local-installation.md#4-恢复现有现场而不只是空白安装)核对路径，并在新机器保持同一 `DEFAULT_USER_ID`。浏览器 Cookie 不随包转移，新的抓取登录要在协作者电脑上重新完成。

## 打开原始 HTML 原型

原始产品原型位于 [`index.html`](./index.html)，不需要构建步骤。

在仓库根目录启动一个本地静态服务：

```bash
python3 -m http.server 8000
```

然后打开：

```text
http://localhost:8000/index.html
```

原型的 demo mode 不依赖外部服务。原型里的 live mode 是历史参考行为，会在浏览器里请求 Anthropic API key，不要在这里使用生产 key 或共享 key。

## 运行前端工作区

前端需要 Node.js 和 npm；建议 Node.js 22.12 或更新的 22.x。

```bash
cd frontend
npm ci
npm run dev
```

打开：

```text
http://localhost:5173
```

前端 health page 仍然可用：

```text
http://localhost:5173/health
```

运行前端时需要同时运行 FastAPI 后端。前端业务请求使用相对路径 `/api/...`，本地开发时由 Vite 代理到：

```text
http://127.0.0.1:8000
```

如果之后要通过 VPS 分享给别人看，需要让前端页面和后端 `/api/...` 在同一个公开 origin 下提供，例如：

```text
https://your-domain/
https://your-domain/api/...
```

不要让别人访问一个仍然依赖观看者本机 `localhost:8000` 的前端构建。

前端检查命令：

```bash
npm run lint
npm run test
npm run build
```

## 运行后端

后端需要 Python 3.11 或更新版本。

本地上传视频的预览抽帧功能还需要后端机器安装 `ffmpeg`：

```bash
ffmpeg -version
```

如果 `ffmpeg` 不在默认 PATH 中，可以设置：

```bash
export FFMPEG_PATH=/absolute/path/to/ffmpeg
```

启动后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
uvicorn app.main:app --reload
```

以上仅安装主应用。需要主页 URL 导入时，还要按[安装指南](docs/local-installation.md)安装 `xhs` extra、浏览器和独立 MediaCrawler 环境。

后端 health endpoint 和 OpenAPI 文档：

```text
http://localhost:8000/api/health
http://localhost:8000/docs
```

后端检查命令：

```bash
.venv/bin/python -m ruff check app tests
.venv/bin/python -m pytest
```

受众反应检查可在仓库根目录运行 `backend/.venv/bin/python scripts/check_audience_reactions.py`，默认只免费预览，不需要启动后端，也不初始化正式数据库。只有显式加 `--live --output <新的报告目录>` 才会调用 Qwen；完整图检查的应用初始化和运行数据库均自动隔离到临时目录，结束或异常时清理，无需额外包裹环境变量。`--audience-from <已有报告> --group-ids <角色ID>` 仅检查所选角色的独立反应，不创建数据库；加 `--task-pair` 则要求恰好一位角色，最多两次调用对比报名条件。报告建议存入被 Git 忽略的 `data/evals/`；结构校验通过不等于人物反应质量已经通过人工验收。

## 模型配置

live generation 统一通过后端模型代理调用，浏览器不持有模型 API key。默认 provider 是 Qwen / DashScope 的 OpenAI-compatible API：

```bash
export MODEL_PROVIDER=qwen
export QWEN_API_KEY=...
export QWEN_MODEL=qwen-plus
# 可选；这是默认值：
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

如果你通过编辑器插件使用 Codex，不能方便地给后端 shell 注入环境变量，可以在仓库根目录或 `backend/` 下创建本地 env 文件：

```text
.env.local
backend/.env.local
```

这些文件已被 git ignore。文件里使用同样的 `export KEY=value` 格式，例如：

```bash
export MODEL_PROVIDER=qwen
export QWEN_API_KEY=...
export QWEN_MODEL=qwen-plus
```

smoke script 会自动依次读取 `.env.local` 和 `backend/.env.local`：

```bash
backend/.venv/bin/python scripts/smoke_model_api.py
```

如果需要显式重申 Qwen / DashScope 配置：

```bash
export MODEL_PROVIDER=qwen
export QWEN_API_KEY=...
export QWEN_MODEL=qwen-plus
# 可选；这是默认值：
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

Qwen 账号画像的单次读取等待默认是 180 秒（已观察到完整响应需要约 99 秒）。可在 `.env.local` 设置 `QWEN_PROFILE_READ_TIMEOUT_SECONDS=180`，范围为 1～300 的整数；只影响 `MODEL_PROVIDER=qwen` 的账号画像，其他文本操作及连接／写入等待仍为 90 秒，不增加自动重试。这是单次网络读取上限，不是整个 workflow 的总时限。只读画像检查脚本使用独立的 `--read-timeout-seconds` 参数，默认 90 秒，便于重现旧设置。

也支持这些 alias：

```text
DASHSCOPE_API_KEY
DASHSCOPE_BASE_URL
```

也支持 Anthropic-compatible endpoint，作为显式兼容配置而非默认路径：

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=...
export ANTHROPIC_BASE_URL=https://your-qwen-host/apps/anthropic
# 如果部署要求精确 messages endpoint，再设置：
export ANTHROPIC_MESSAGES_URL=https://your-qwen-host/apps/anthropic/v1/messages
```

对于 Qwen 的 `/apps/anthropic` endpoint，如果没有设置 `ANTHROPIC_MESSAGES_URL`，后端会自动推导 `/apps/anthropic/v1/messages`。

注意：`ANTHROPIC_*` 只供文本模型的 Anthropic-compatible path 使用。图文/视频理解与生成走 Qwen / DashScope media skills，需要额外提供 Qwen 变量。即使使用同一个 API key，也要显式配置：

```bash
export QWEN_API_KEY=...
export QWEN_BASE_URL=https://your-qwen-host/compatible-mode/v1
export QWEN_DASHSCOPE_BASE_URL=https://your-qwen-host/api/v1
```

media smoke test：

```bash
backend/.venv/bin/python scripts/smoke_qwen_media.py image-understand \
  --image-url https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg
```

## 当前功能范围

迁移后的应用目前包含：

- 内容资产和能力资产；
- workspace persistence；
- workflow execution；
- LangGraph-backed workflows；
- 分析结果、选题库、创作输出和受众模拟历史；
- Qwen / Anthropic 后端模型 provider；
- Qwen 图片/视频理解与生成；
- 本地视频 ffmpeg 抽帧后再进入视频理解。

当前仍然有意不包含 Docker、authentication、多租户、Redis、Postgres 或部署基础设施。

建议先读 [`docs/product-design.md`](./docs/product-design.md) 理解产品设计、能力模型和当前功能地图，再读 [`docs/status-and-todo.md`](./docs/status-and-todo.md) 查看当前实现状态和 TODO。如果准备提交 GitHub 或打版本 tag，先按 [`docs/release-checklist.md`](./docs/release-checklist.md) 做发布前检查。

## 旧版独立导入脚本（兼容保留）

以下 `xhs_profile_importer.py` 是早期浏览器可见页面导入器，不是现在前端“添加账号”的实现。当前前端已通过后端调用 MediaCrawler，安装方式见上方指南。旧脚本仅供兼容使用，不绕过验证码、注入 cookie 或进行批量抓取。

安装可选依赖：

```bash
cd backend
source .venv/bin/activate
python -m pip install '.[xhs]'
python -m playwright install chromium
```

运行：

```bash
cd ..
backend/.venv/bin/python scripts/xhs_profile_importer.py "https://www.xiaohongshu.com/user/profile/..."
```

脚本会打开本地 Chromium。首次运行时需要在浏览器中手动登录小红书，确认目标主页正常显示后回到终端按 Enter。脚本会滚动主页并读取当前浏览器可见的笔记卡片。默认不会打开详情页，因为详情页更容易受推荐流、弹窗和页面跳转影响；如果确实需要尝试读取详情正文，可以显式加 `--open-details`。

默认输出到：

```text
data/xhs-imports/*.json
data/xhs-imports/*.md
```

JSON 导出使用版本化 schema。v1 只记录本地浏览器可见页面里相对稳定能拿到的信息：

```json
{
  "schemaVersion": "xhs-profile-import/v1",
  "platform": "xiaohongshu",
  "sourceUrl": "https://www.xiaohongshu.com/user/profile/...",
  "importedAt": "2026-08-22T00:00:00+00:00",
  "importMethod": "browser_assisted_visible_page",
  "creator": {
    "profileText": "主页当前可见文本"
  },
  "notes": [
    {
      "title": "笔记标题",
      "url": "https://www.xiaohongshu.com/explore/...",
      "cardText": "主页卡片可见文本",
      "detailText": "详情页可见正文；读取失败时为空",
      "coverUrl": "卡片封面 URL；可能为空",
      "engagementText": "可见互动信息；可能为空"
    }
  ],
  "warnings": ["导入提示"]
}
```

常用参数：

```bash
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL" --limit 10 --scrolls 3
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL" --open-details
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL" --skip-login-prompt
```

登录态保存在本地：

```text
data/browser-profiles/xhs-importer/
```

如果需要重新登录，删除这个目录即可。导出的 Markdown 可以人工检查后作为历史笔记、视频创作样本或小红书创作者主页输入资产导入主应用。

离线文件导入只解析文件，不访问小红书；这与当前的在线 URL 导入是两条路径。内部工作台（`?internal=1`）的“创作者档案 → 小红书主页”页面可上传旧 importer 生成的 JSON；旧 `xhs-profile-import/v1` 会转换成 workflow 可使用的 `xhs-creator-profile/v1`。以下离线资源管理入口均指内部工作台。

如果需要同时导入封面，推荐整理成离线导入包并在“创作者档案 → 小红书主页”页选择整个文件夹：

```text
xhs_import_package/
  xhs_creator_profile.json
  images/
    <note_id>/
      0.jpg
```

`xhs_creator_profile.json` 里的笔记可写入 `cover.relativePath`，例如 `images/<note_id>/0.jpg`。导入后会创建小红书创作者主页 input asset，并把封面保存为图文资产；主页资产默认命名为 `XHS {小红书账号名} 创作者主页`，封面命名为 `笔记标题_封面`，caption 使用笔记正文。

### MediaCrawler 本地抓取入口

MediaCrawler 既供当前后端的主页 URL 导入调用，也可单独用于离线导出。先完成[固定版本及补丁安装](docs/local-installation.md#2-安装抓取依赖)，再从主应用根目录运行下面的命令。不要仅克隆上游最新版：本机曾有未进入主 Git 的封面配置调整，现在已整理为仓库内补丁。

本仓库提供了一个包装脚本，解决 `xhslink.cn` 短链不能被 MediaCrawler 直接解析的问题。它会先用本地浏览器打开短链，拿到最终的小红书用户主页 URL，再调用 MediaCrawler。

```bash
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py \
  "https://xhslink.cn/m/9mS715le7Ha" \
  --limit 20 \
  --comments \
  --save-data-path data/xhslink-20-comment-cover-test
```

常用参数：

```bash
# 只解析短链，不启动抓取
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py "URL" --resolve-only

# 只抓笔记，不抓评论
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py "URL" --limit 20

# 抓一级评论；二级评论默认关闭
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py "URL" --limit 20 --comments
```

MediaCrawler 输出会落在：

```text
data/external/MediaCrawler/<save-data-path>/xhs/jsonl/
data/external/MediaCrawler/<save-data-path>/xhs/images/
```

补丁会开启媒体下载，并限定每篇首图、不下载视频。媒体开关仍在上游 `config/base_config.py` 中。保持低频、低数量；当前调用并发 1、只抓一级评论、不开二级评论。

以下命令仅在本机已有固定样本时可用；`_tt` 和 QSheep 样本在被忽略的 `data/` 中，不随 Git 分发。若已有样本，可导入主应用 SQLite：

```bash
backend/.venv/bin/python scripts/import_xhs_fixture_to_workspace.py _tt
backend/.venv/bin/python scripts/import_xhs_fixture_to_workspace.py QSheep
```

导入后会创建或更新 `XHS _tt 工作区`、`XHS QSheep 工作区`，并生成账号概况、历史笔记、评论样本和封面图片媒体资产。Agent 通过现有 Context Access Layer 读取这些资产，不直接读取 MediaCrawler 原始目录。

如果要把任意 MediaCrawler 输出整理成前端可上传的离线导入包：

```bash
backend/.venv/bin/python scripts/export_xhs_import_package.py \
  --input data/external/MediaCrawler/data/xhslink-20-comment-cover-test/xhs \
  --output data/xhs-import-packages/my_creator
```

输出目录会包含 `xhs_creator_profile.json` 和 `images/<note_id>/0.jpg`。之后在前端“内容资产 → 创作者档案 → 小红书主页 → 小红书离线文件夹导入”中选择整个输出目录即可。

选择目录后，前端会先在本地预览账号名、笔记数、评论数、图片文件数、匹配封面数和缺失封面数。导入成功后，小红书创作者主页详情页会显示结构化摘要，并完整展示后端返回的导入提示。

重复导入同名主页时，默认会更新已有 `XHS {账号名} 创作者主页`，避免资产列表膨胀；如果确实要保留多个版本，可以在前端选择“另存为新主页”。

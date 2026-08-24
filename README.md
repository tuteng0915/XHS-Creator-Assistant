# 创作者内容工作区

这个仓库包含两部分：原始的单文件 HTML 产品原型，以及已经迁移出来的创作者工作区应用。当前主应用使用 React、TypeScript、FastAPI、SQLite、LangGraph 和 Server-Sent Events；原始 `index.html` 只作为行为参考保留。

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

前端需要 Node.js 和 npm。

```bash
cd frontend
npm install
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

## 模型配置

live generation 统一通过后端模型代理调用，浏览器不持有模型 API key。默认 provider 是 Anthropic-compatible path：

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

如果你通过编辑器插件使用 Codex，不能方便地给后端 shell 注入环境变量，可以在仓库根目录或 `backend/` 下创建本地 env 文件：

```text
.env.local
backend/.env.local
```

这些文件已被 git ignore。文件里使用同样的 `export KEY=value` 格式，例如：

```bash
export MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...
export ANTHROPIC_BASE_URL=https://your-qwen-host/apps/anthropic
export ANTHROPIC_MODEL=qwen-plus
```

smoke script 会自动依次读取 `.env.local` 和 `backend/.env.local`：

```bash
backend/.venv/bin/python scripts/smoke_model_api.py
```

如果使用 Qwen / DashScope 的 OpenAI-compatible API：

```bash
export MODEL_PROVIDER=qwen
export QWEN_API_KEY=...
export QWEN_MODEL=qwen-plus
# 可选；这是默认值：
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

也支持这些 alias：

```text
DASHSCOPE_API_KEY
DASHSCOPE_BASE_URL
```

部分 Qwen 部署也提供 Anthropic-compatible endpoint，可以通过同一个后端代理接入：

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

## 本地小红书主页导入 Demo

仓库提供一个独立脚本，用于本地 demo 场景下从用户可见的小红书主页导入有限数量笔记。它不会接入前端，也不会绕过验证码、逆向签名、注入 cookie 或进行批量抓取。

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

主平台不会访问小红书。如果要把离线导入结果放进主应用，可以在内容资产里的“创作者档案 → 小红书主页”页面上传本地 importer 生成的 JSON；旧 `xhs-profile-import/v1` JSON 会转换成 workflow 可直接使用的 `xhs-creator-profile/v1`。兼容路径仍支持把 JSON / Markdown 导入历史笔记或视频创作样本。后端只解析上传文件，并保存为受控 input asset。

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

如果需要更稳定地读取笔记详情、一级评论和封面，可以使用独立的 MediaCrawler 本地克隆。这个入口仍然只作为离线工具存在，不接入主平台后端。

准备 MediaCrawler：

```bash
git clone https://github.com/NanmiCoder/MediaCrawler.git data/external/MediaCrawler
cd data/external/MediaCrawler
python3.11 -m venv .venv313
.venv313/bin/python -m pip install -r requirements.txt
```

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

注意：MediaCrawler 的媒体下载开关在它自己的 `config/base_config.py` 里。demo 场景建议保持低频、低数量，并只抓必要字段。当前推荐配置是并发 1、只抓一级评论、不开二级评论。

如果要把已经固定的本地样本导入主应用 SQLite：

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

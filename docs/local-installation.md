# 本地安装与 MediaCrawler 配置

从 Git 克隆得到的是主应用源码和抓取适配脚本，不包含 Python/Node 依赖、数据库、API key、浏览器登录态或抓取样本。MediaCrawler 是运行时使用的独立 Git 克隆，不是本仓库的 submodule，也不属于后端 pip 依赖；它有自己的 upstream remote。主应用通过子进程调用它，默认放在被忽略的 `data/external/MediaCrawler`。

不安装 MediaCrawler 也能运行主应用、查看已有资产及使用模型功能，但不能通过主页 URL 抓取笔记。下面分开安装两个 Python 环境，避免 MediaCrawler 的 FastAPI 等依赖版本与主应用冲突。

## 1. 获取主应用

以下命令面向 macOS/Linux 本地开发。需要 Git、Python 和 Node.js；推荐 Python 3.13（当前抓取环境为 3.13.5）及 Node.js 22.12 或更新的 22.x。主应用支持 Python 3.11+，但不代表 MediaCrawler 的所有浮动依赖都支持同样的版本。Windows 原生安装路径尚未验证。

```bash
git clone https://github.com/tuteng0915/XHS-Creator-Assistant.git
cd XHS-Creator-Assistant
python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install './backend[dev,xhs]'
backend/.venv/bin/python -m playwright install chromium
npm --prefix frontend ci
```

`xhs` extra 和 Chromium 用于我们的短链解析器；它们不能替代下一步的 MediaCrawler 环境。Linux 如提示缺少系统浏览器库，可使用该环境的 `python -m playwright install --with-deps chromium`，这可能需要管理员权限。

按 [README 的模型配置](../README.md#模型配置) 在仓库根目录创建 `.env.local`。文件被忽略，不要把 key 或登录态提交到 Git。已有账号、`_tt` / QSheep 抓取样本都不会随 clone 自动出现，首次启动是空数据库。

## 2. 安装抓取依赖

先阅读 MediaCrawler 自带的 `LICENSE`：本次固定版本使用 **NON-COMMERCIAL LEARNING LICENSE 1.1**，限制为非商业学习研究用途；不要因为源码公开就认为可直接用于商业产品。上游项目为 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)。

在主应用根目录执行（仅用于首次安装，已有目录不要覆盖）：

```bash
git clone https://github.com/NanmiCoder/MediaCrawler.git data/external/MediaCrawler
git -C data/external/MediaCrawler checkout --detach d6f7c5bb906b6dac40ddf343ef9e26438a3de092
git -C data/external/MediaCrawler apply --check ../../../scripts/patches/mediacrawler-local-demo.patch
git -C data/external/MediaCrawler apply ../../../scripts/patches/mediacrawler-local-demo.patch
python3.13 -m venv data/external/MediaCrawler/.venv313
data/external/MediaCrawler/.venv313/bin/python -m pip install --upgrade pip
data/external/MediaCrawler/.venv313/bin/python -m pip install -r data/external/MediaCrawler/requirements.txt
data/external/MediaCrawler/.venv313/bin/python -m playwright install chromium
```

`.venv313` 是现有适配器自动查找的目录名，请保持这个名称。上游源码固定到当前已用过的提交，但 requirements 中仍有浮动版本，因此这不是完整依赖锁定，也不保证未来所有环境都能一次安装成功。

补丁由本机实际配置整理而来，保留上游源码及其许可：自动启动独立浏览器、启用封面下载、每篇只下载第一张图、不下载视频，并将随机等待上限设为 3 秒。本机 CDP 调试端口是本地控制连接，补丁还要求这一次 `httpx` 请求不继承系统或环境代理，以免访问 `localhost` 时收到代理返回的 502。补丁还修复主页状态中已验证的非 JSON 空值、创作者笔记缺失的 `xsec_source` 和笔记链接来源；2026-10-01 已用一条真实笔记的正文与封面验证。单独运行上游时默认读取 4 条且不读评论；通过我们的应用运行时，数量和评论开关由调用参数覆盖（公开界面默认 10 条，并发 1，只取一级评论）。这些限制不能保证平台不触发验证或限制。

**不要重复应用补丁，也不要直接更新上游 main。** 已有环境可先运行下面的只读检查；成功表示补丁已经存在：

```bash
git -C data/external/MediaCrawler apply --reverse --check ../../../scripts/patches/mediacrawler-local-demo.patch
```

另外在后端所在电脑安装 Chrome 或 Edge。当前 CDP 抓取配置会启动本机浏览器；Playwright 下载的 Chromium 主要供短链解析和备用模式使用。自动找不到浏览器时，在 MediaCrawler 的 `config/base_config.py` 中设置 `CUSTOM_BROWSER_PATH`，不要在主项目 API 中提交任意文件路径。

如果已有另一份兼容克隆，可在主应用 `.env.local` 指定绝对路径：

```bash
XHS_MEDIACRAWLER_DIRECTORY=/absolute/path/to/MediaCrawler
```

那份克隆同样需要固定版本、补丁和 `.venv313`。环境变量修改后重启后端。

## 3. 启动与验证

两个终端分别从主应用根目录执行：

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

打开 `http://127.0.0.1:5173/`；`http://127.0.0.1:8000/api/health` 可验证后端启动，但不能证明抓取已可用。前端通过相对路径 `/api` 访问后端。

在“添加账号”填写自己的小红书主页 URL，先使用默认 10 条。浏览器会在**运行后端的电脑**打开，按提示扫码；需要额外验证时由用户完成。当前没有把远程后端的扫码窗口转发到前端，所以这套步骤主要用于本地带桌面的机器，不能当成无头 VPS 的完整登录方案。

完成后检查账号名、笔记正文、封面和一级评论；粉丝量等字段以平台实际返回为准，没有返回不能视作零。运行任务及资产保存到本地 `data/`，刷新网页不会重新执行已有抓取。遇到平台验证、访问限制或登录失败时先停止并检查浏览器，不要连续重试。成功安装依赖不代表平台一定允许读取。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| 找不到 MediaCrawler | 默认目录是否存在，或环境变量是否指向正确克隆；修改配置后重启后端 |
| 缺少 Python 模块 | 两个虚拟环境分别安装；不要把上游 requirements 安装进主应用环境 |
| 短链无法打开 | 后端环境是否装了 `xhs` extra 和 Chromium；可先试完整主页 URL |
| 浏览器无法启动 | 后端机器是否有桌面、Chrome/Edge；检查上游 `CUSTOM_BROWSER_PATH` |
| CDP 已启动却收到 HTTP 502 | 检查是否应用了本仓库补丁；本机调试端口不应走系统或环境代理。此修复只验证浏览器连接，不代表小红书页面一定能加载 |
| 登录后提示主页状态解析失败 | 补丁会区分主页数据解析错误与 URL 格式错误，并只对已确认的裸 `undefined`、空 `new Set([])` 做保守转换；若一个主页也没处理成功，抓取进程会以失败退出。2026-10-01 已用一条真实主页及一条笔记验证该修复；网页格式以后仍可能变化，遇到新错误时保留脱敏日志，不要连续重试。 |
| 有正文但无封面 | 检查补丁、上游媒体开关及下载错误；部分笔记可能确实取不到封面 |
| 补丁应用失败 | 核对固定提交和已有修改，先尝试 reverse check；不要强行覆盖本机改动 |

## 4. 恢复现有现场，而不只是空白安装

“能运行同样的程序”和“看到同一批账号、笔记、图片及历史记录”是两件事。上面的安装步骤完成前者；后者还需要原电脑的本地数据。以下步骤针对默认目录，接收方必须是受信任环境。

### 原电脑准备

先等待分析、对话和抓取任务结束，再停止后端及其抓取进程，避免备份过程中数据库与上传文件继续变化。**不要在运行中只复制 `app.sqlite3`**；SQLite 可能还有配套 WAL 文件。以下命令不会帮你停止进程。

从主应用根目录执行，将数据包放到仓库之外：

```bash
git rev-parse HEAD
tar \
  --exclude='data/external' \
  --exclude='data/browser-profiles' \
  --exclude='data/backups' \
  -czf ../SqsAgent-local-data.tar.gz data
```

记录第一条命令输出的主仓库提交号，与数据包一同转交。代码和安装文档必须先提交并推送；未提交文件不会由接收方的 clone 自动获取。数据包包含账号、创作内容和历史记录，不要上传到公开 Git 仓库。

这个包保留整个主应用 `data/`（包括数据库及其配套文件、`uploads/`、抓取任务输出、已有离线样本和导入包），但排除独立 MediaCrawler 环境、浏览器登录态和旧备份。已导入主应用的封面在 `data/uploads/` 中，无需搬运整个上游仓库；如果还需要**尚未导入**的上游抓取原始结果，另行复制 MediaCrawler 的输出目录，或先导出为离线导入包，不要夹带 `browser_data/`。

通过安全渠道另行提供实际使用的 `.env.local` 和（如存在）`backend/.env.local`，不要贴到公开文档。检查其中的 `DATABASE_PATH`、`UPLOAD_DIRECTORY`、`XHS_CAPTURE_DIRECTORY`、`XHS_MEDIACRAWLER_DIRECTORY`、`FFMPEG_PATH`：如果指向旧机器的绝对路径，恢复时必须调整。若数据库或上传文件被配置在默认 `data/` 之外，上面的压缩包**不包含它们**，需要单独备份。

如果配置了 `DEFAULT_USER_ID`，保留原值，否则已有数据可能不属于新环境的默认用户。配置优先级为进程环境变量、根目录 `.env.local`、`backend/.env.local`；已有环境变量不会被文件覆盖。

### 新电脑恢复

1. 按本指南安装主应用与固定版本 MediaCrawler，并切换到原电脑记录的主仓库提交。先不要启动后端；Python 环境和 `node_modules` 应重新安装，不直接跨机器复制。
2. 将数据包放在主仓库的上一级目录。在没有旧业务数据的全新目录里，从主仓库根目录执行：

   ```bash
   tar -tzf ../SqsAgent-local-data.tar.gz
   tar -xzf ../SqsAgent-local-data.tar.gz
   ```

   第一条先查看内容，第二条恢复。若目标已有数据库或上传文件，先停止服务并另行备份，不要直接覆盖或把两份数据库混在一起。刚安装的 `data/external/MediaCrawler` 不在包内，不会被这次恢复替换。
3. 放置本地模型配置，调整旧机器的绝对路径；默认路径无需保持相同的用户名或仓库位置。数据库中的媒体使用存储 key，相对于上传目录定位。历史抓取记录中的旧原始路径只是来源记录，不应作为新机器可以访问的文件地址。
4. 启动后端与前端。后端会检查并应用未执行的数据库迁移；不要用比备份时更旧的程序打开较新的数据库。原先未结束的任务不保证能跨机器继续，因此应在原电脑任务结束后备份。
5. 在新机器重新完成小红书浏览器登录；模型 API key 可复用与否取决于对应服务及网络条件，登录 Cookie 不通过本方案迁移。

### 恢复后的验收

- `/api/health` 返回正常，前端能加载账号选择列表。
- 原账号的已抓取笔记、正文和封面可打开，切换账号不会混入其他账号的数据。
- 选题、创作内容、对话、分析历史和受众模拟历史能重新打开；仅有数据库而缺少上传目录时，文字可能正常但图片会失败。
- 先运行无需付费的自动检查：

  ```bash
  (cd backend && .venv/bin/python -m pytest tests)
  npm --prefix frontend run lint
  npm --prefix frontend test
  npm --prefix frontend run build
  ```

- 再按需验证真实模型及抓取：`backend/.venv/bin/python scripts/smoke_model_api.py` 会实际请求配置的模型，可能产生费用；主页抓取需人工扫码，先用少量笔记，不需要为了确认数据恢复而重新抓取所有账号。

目前固定了 MediaCrawler 源码版本及补丁，前端由 `package-lock.json` 配合 `npm ci` 还原；两个 Python 环境还不是完整锁版本安装。因此这是可按步骤恢复的开发环境说明，不是已在所有系统验证的逐字节环境镜像。网络可达性、浏览器验证和模型权限仍需在目标电脑验收。

## 文件归属与迁移

我们的 Git 保存主应用、适配器、安装说明和小补丁；`data/`、虚拟环境、`node_modules`、`.env.local` 都应继续忽略。另一个人 clone 后重新安装即可，无需把数百 MB 的环境打进代码仓库。

`data/external/MediaCrawler/browser_data/` 内的登录态属于敏感本地数据，不随代码分享。换电脑需要重新登录。若要迁移自己的已有资产，需另行安全备份数据库和上传文件，单纯 clone 不会迁移数据。内部工作台仍支持离线导入，旧的独立脚本是兼容入口，不是当前主页 URL 导入的默认实现。

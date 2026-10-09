# 离线文件与兼容导入脚本

当前默认入口是公开界面的“添加账号”：输入主页 URL，由后端调用 MediaCrawler 在线读取笔记，默认读取 10 条。首次登录需要在后端所在电脑打开的浏览器中扫码；安装与登录步骤见[本地安装与 MediaCrawler 配置](local-installation.md)。

本文记录的是兼容入口：旧版浏览器可见页面导出、单独运行 MediaCrawler、导出离线包，以及内部工作台的文件导入。**生成抓取文件会访问小红书；将已有文件导入主应用只解析本地文件，不访问小红书。** 不要将这两步混为一谈。

离线导入界面位于 `http://127.0.0.1:5173/?internal=1` 的“内容资产 → 创作者档案 → 小红书主页”。`?internal=1` 只是界面模式，不是权限控制。以下命令均从主仓库根目录执行；将 `"URL"` 替换成自己有权读取的主页 URL 或相应脚本支持的主页短链。

## 1. 旧版独立导入脚本（兼容保留）

[`xhs_profile_importer.py`](../scripts/xhs_profile_importer.py) 是早期浏览器可见页面导入器，**不是当前“添加账号”的实现**。它仅读取用户控制的本地浏览器中已呈现的页面，不绕过验证码、注入 Cookie 或进行高频批量抓取。

依赖主应用 Python 环境、`xhs` extra 和 Playwright Chromium；按[安装指南第 1 节](local-installation.md#1-获取主应用)准备即可，运行这个旧脚本本身不需要 MediaCrawler。

```bash
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL"
```

脚本会打开本地 Chromium。首次运行时在浏览器中手动登录，确认目标主页正常显示后回到终端按 Enter。脚本会滚动主页并读取当前可见的笔记卡片；默认最多读取 12 条、滚动 4 次。

默认不会打开详情页，因为详情页更容易受推荐流、弹窗和页面跳转影响。需要尝试读取详情正文时，显式加 `--open-details`；读取失败时仍会保留卡片快照和提示，不应把空正文理解为笔记本身没有正文。

```bash
# 限制读取数量和滚动次数
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL" --limit 10 --scrolls 3

# 尝试读取详情正文
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL" --open-details

# 已登录的本地 profile 可跳过终端确认；不会替代平台登录或验证
backend/.venv/bin/python scripts/xhs_profile_importer.py "URL" --skip-login-prompt
```

默认输出与登录态目录：

```text
data/xhs-imports/*.json
data/xhs-imports/*.md
data/browser-profiles/xhs-importer/
```

可用 `--out` 指定 JSON 路径，`--markdown-out` 指定 Markdown 路径，`--profile-dir` 指定浏览器 profile 目录。默认 Markdown 与 JSON 同名。首次登录不要使用 `--headless`。

如需重新登录，先退出脚本并关闭使用该 profile 的浏览器，再将 `data/browser-profiles/xhs-importer/` 重命名为一个尚不存在的备份目录；确认旧目录已移走后重新运行，脚本会创建新的 profile。备份仍含敏感登录态，不要提交 Git 或随导入包分享。不要在浏览器运行时删除目录。

### 旧版 JSON schema

JSON 使用版本化 schema。`xhs-profile-import/v1` 记录本地浏览器可见页面里相对稳定能取得的信息；下面是字段示例，不是真实账号数据：

```json
{
  "schemaVersion": "xhs-profile-import/v1",
  "platform": "xiaohongshu",
  "sourceUrl": "https://www.xiaohongshu.com/user/profile/PROFILE_ID",
  "importedAt": "2026-08-22T00:00:00+00:00",
  "importMethod": "browser_assisted_visible_page",
  "creator": {
    "profileText": "主页当前可见文本"
  },
  "notes": [
    {
      "title": "笔记标题",
      "url": "https://www.xiaohongshu.com/explore/NOTE_ID",
      "cardText": "主页卡片可见文本",
      "detailText": "详情页可见正文；读取失败时为空",
      "coverUrl": "卡片封面 URL；可能为空",
      "engagementText": "可见互动信息；可能为空"
    }
  ],
  "warnings": ["导入提示"]
}
```

导出的 Markdown 可人工检查后，作为历史笔记、视频创作样本或小红书创作者主页输入资产导入。内部工作台的“小红书主页”页也可上传 JSON；旧 `xhs-profile-import/v1` 会转换成 workflow 可使用的 `xhs-creator-profile/v1`。单文件入口支持 UTF-8 的 `.json`、`.md`、`.markdown` 和 `.txt`；单独上传 JSON 不会把远程封面 URL 自动下载成媒体资产，需要封面时使用下文的文件夹导入。

## 2. MediaCrawler 本地抓取包装脚本

MediaCrawler 既供当前后端的主页 URL 导入调用，也可单独用于生成离线数据。先完成[固定版本、补丁及独立环境安装](local-installation.md#2-安装抓取依赖)，不要仅克隆上游最新版或把上游依赖混入主应用环境。上游许可、浏览器要求和安装故障排查也以该指南为准。

[`xhs_mediacrawler_profile_importer.py`](../scripts/xhs_mediacrawler_profile_importer.py) 支持完整小红书主页 URL 和 `xhslink.cn` 主页短链。短链会先在本地浏览器中解析成完整主页 URL，再交给 MediaCrawler；因此 `--resolve-only` 虽然不启动抓取，解析短链时仍会打开浏览器并访问网络。

```bash
# 将 URL 替换为自己的完整主页 URL 或 xhslink.cn 主页短链
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py \
  "URL" \
  --mediacrawler-dir "$PWD/data/external/MediaCrawler" \
  --limit 20 \
  --comments \
  --save-data-path data/my-creator-capture
```

常用命令：

```bash
# 只解析 URL，不启动 MediaCrawler
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py "URL" --resolve-only

# 只抓笔记，不抓评论
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py "URL" \
  --mediacrawler-dir "$PWD/data/external/MediaCrawler" --limit 20

# 抓一级评论；二级评论默认关闭
backend/.venv/bin/python scripts/xhs_mediacrawler_profile_importer.py "URL" \
  --mediacrawler-dir "$PWD/data/external/MediaCrawler" --limit 20 --comments
```

示例显式传入 MediaCrawler 的绝对目录：脚本会在该目录中启动子进程，避免默认相对路径连同自动选择的 Python 路径在切换工作目录后被再次解析。若使用其他克隆，将该参数替换成它的绝对路径。

参数与路径约定：

| 参数 | 当前行为 |
| --- | --- |
| `--limit` | 默认 10；`0` 表示尝试读取全部可见笔记，不保证平台返回全部内容 |
| `--comments` | 默认关闭；开启一级评论，每篇评论数量仍由上游配置控制 |
| `--sub-comments` | 默认关闭；兼容参数，本文示例不启用 |
| `--save-data-path` | 默认 `data/mediacrawler-xhs-<时间戳>`；相对路径以 **MediaCrawler 仓库**为基准，不是主仓库 |
| `--save-data-option` | 默认 `jsonl`；脚本也支持 `json`、`csv`、`sqlite`、`excel`，但本文离线包导出器读取的是 JSONL |
| `--mediacrawler-dir` | 默认 `data/external/MediaCrawler`；单独运行脚本时用此参数指定其他克隆，不会自动读取主应用的 `XHS_MEDIACRAWLER_DIRECTORY` |
| `--mediacrawler-python` | 默认优先选择该克隆中的 `.venv313/bin/python`，不存在时回退到当前 Python；应按安装指南准备独立环境 |
| `--resolver-profile-dir` | 短链解析默认使用 `data/external/MediaCrawler/browser_data/cdp_xhs_user_data_dir`；含登录态，不随数据包分享 |

示例命令的输出位置是：

```text
data/external/MediaCrawler/data/my-creator-capture/
  creator_metrics.json
  xhs/
    jsonl/
    images/
```

通用形式为 `data/external/MediaCrawler/<save-data-path>/xhs/jsonl/` 和 `.../xhs/images/`。指定不同 MediaCrawler 目录或绝对保存路径时，按实际配置查找。`creator_metrics.json` 保存本次取得的账号指标；未返回的字段不能按零处理。

仓库补丁开启媒体下载，每篇只下载第一张图、不下载视频；媒体开关位于上游 `config/base_config.py`。包装脚本固定并发 1，评论默认不读取，上面的 `--comments` 示例只读取一级评论。保持低频、低数量；遇到登录失败、平台验证或访问限制时停止并人工检查，不要连续重试。安装成功和退出码正常都不能代替对笔记正文、封面及账号信息的验收。

## 3. 导出离线包并在内部工作台导入

要同时导入正文和封面，推荐把已有 MediaCrawler JSONL 输出整理成离线包。下面只读取已有文件，不启动抓取或模型调用：

```bash
backend/.venv/bin/python scripts/export_xhs_import_package.py \
  --input data/external/MediaCrawler/data/my-creator-capture \
  --output data/xhs-import-packages/my_creator \
  --no-overwrite
```

`--input` 可以是含 `xhs/` 的上级目录，也可以直接指向 `xhs/`。**推荐上面的上级目录形式**：导出器还会从输入目录读取同级 `creator_metrics.json`；直接传 `.../xhs` 会遗漏其上一级的账号指标。读取文件要求如下：

- 必需：`xhs/jsonl/creator_contents_*.jsonl`。
- 可选：`xhs/jsonl/creator_comments_*.jsonl` 和对应封面图片。
- 同类 JSONL 有多份时，按文件名排序选择最后一份，不会合并所有历史抓取；建议每次抓取使用独立输出目录。

不传 `--output` 时，默认写入 `data/xhs-import-packages/<账号名或输入目录名>`。`--code` 可指定写入 `source.fixtureCode` 的内部代号。默认允许覆盖目标 JSON 和同路径图片；示例加了 `--no-overwrite`，如果目录已存在且非空就停止，避免误写已有包。需要再次导出时换一个新目录，或在确认备份后自行决定是否覆盖。

输出结构示例：

```text
xhs_import_package/
  xhs_creator_profile.json
  images/
    <note_id>/
      0.jpg
```

`xhs_creator_profile.json` 使用 `xhs-creator-profile/v1`，笔记的 `cover.relativePath` 指向包内图片，例如 `images/<note_id>/0.jpg`。当前导出器读取每篇 `images/<note_id>/0.jpg` 并保留该文件名；若源图片使用其他名称，需先整理成这个约定，或自行准备与 JSON 相对路径匹配的导入包。没有取到封面时会报告缺失提示，不会补造图片。

在内部工作台的“内容资产 → 创作者档案 → 小红书主页 → 小红书离线文件夹导入”中选择**整个输出目录**，不要只选 JSON。此入口也识别名为 `profile.json` 的主页文件。

选择目录后，前端先在本地预览账号名、笔记数、评论数、图片文件数、匹配封面数和缺失封面数。检查预览和导入提示后，再点击上传保存。导入会创建小红书创作者主页 input asset，并把匹配的封面保存为图文资产：主页默认名为 `XHS {小红书账号名} 创作者主页`，封面名为 `笔记标题_封面`，caption 使用笔记正文（正文为空时回退到标题）。详情页提供结构化摘要，并展示后端返回的导入提示。

**文件夹导入**重复遇到同名主页时，默认更新已有资产；需要保留版本时选择“另存为新主页”。这一更新行为不适用于旧版单文件上传入口，后者会创建新资产。Agent 通过现有 Context Access Layer 读取导入后的资产，不直接读取 MediaCrawler 原始目录。

## 4. 将已有固定 fixture 直接导入 SQLite

[`import_xhs_fixture_to_workspace.py`](../scripts/import_xhs_fixture_to_workspace.py) 只接受 `_tt` 和 `QSheep` 两个固定样本代号，默认读取 `data/xhs-fixtures/<code>/`。这些样本在被忽略的 `data/` 中，**不随 Git 分发**；没有样本时不能直接运行下面的命令。任意其他创作者输出请使用上一节的离线包流程。

此脚本不访问小红书，也不调用模型，但会初始化主应用并写入当前配置的 SQLite 和上传目录；运行前确认目标数据位置并做好备份。它不需要先启动后端服务。

```bash
backend/.venv/bin/python scripts/import_xhs_fixture_to_workspace.py _tt
backend/.venv/bin/python scripts/import_xhs_fixture_to_workspace.py QSheep
```

默认按名称查找或创建 `XHS _tt 工作区`、`XHS QSheep 工作区`，并创建或更新结构化创作者主页、账号概况、历史笔记、评论样本及封面图片媒体资产。重复运行会更新匹配名称的资产，不是仅追加一次性的只读预览。

可用 `--workspace-id` 指定已有工作区，或用 `--workspace-name` 指定查找/新建名称；`--fixture-root` 更换样本根目录，`--skip-images` 仅导入文本资产。账号材料和历史的跨电脑交付，另见[本地数据恢复说明](local-installation.md#4-恢复现有现场而不只是空白安装)。

## 数据与登录态边界

导入包、原始抓取文件、fixture 和数据库可能含笔记、评论及账号资料，只通过授权的私密渠道转交；不要提交到公开 Git。浏览器 profile、`browser_data/`、Cookie 和模型密钥都不应装进离线导入包。接收方只导入已有文件时不需要重新抓取，也不需要接收原电脑的登录态。

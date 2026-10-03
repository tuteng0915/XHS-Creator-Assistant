# 小红书本地导入与主 Agent 接入设计

## 评论来源字段（2026-10-03）

`xhs-creator-profile/v1` 增加可选的笔记及评论 `authorHash`，保留 MediaCrawler 的 `creator_hash`（16 位匿名哈希）。导入时缺失或格式不符置空，不反解真实 ID，也不以昵称匹配。受众分析本地比较同篇笔记和评论的哈希，向模型仅发送 `sourceRole=author/non_author/unknown`；作者回复仅作背景，不能作为读者需求证据。新导出后再导入才获得来源字段，旧业务数据不自动回填；不升级 schema、不新增表、不重写历史分析。只有匿名标识可比较时才确定来源，非作者不意味着已确认粉丝。

## 固定样本

当前已有两组本地 MediaCrawler 输出，作为离线 fixture 使用。原始数据保留在 `data/` 下，不纳入 git。

| 代号 | 路径 | 笔记 | 一级评论 | 封面图 | 备注 |
| --- | --- | ---: | ---: | ---: | --- |
| `_tt` | `data/xhs-fixtures/_tt/xhs/` | 4 | 26 | 4 | 用户主页实际只有 4 条图文笔记，本地固定为 4 条。 |
| `QSheep` | `data/xhs-fixtures/QSheep/xhs/` | 20 | 137 | 20 | 来源于小红书短链解析后的 QSheep 主页；包含 1 条视频笔记，但本轮只保存封面，不保存视频文件。 |

每组目录结构与 MediaCrawler 保持一致：

```text
xhs/jsonl/creator_contents_2026-08-22.jsonl
xhs/jsonl/creator_comments_2026-08-22.jsonl
xhs/images/<note_id>/0.jpg
```

## 为什么不直接把爬虫放进主平台

小红书数据获取依赖本地浏览器、手动登录、国内网络环境和低频访问控制。主平台当前运行环境主要服务于 LLM workflow，不适合作为爬虫运行环境。更稳妥的边界是：

```text
XHS local importer
-> 离线导入包
-> 主平台内容资产
-> Agent / Workflow 读取内容资产
```

主平台只消费已经落盘或上传的离线导入包，不直接访问小红书，也不保存用户提供的任意外部路径。

## 接入主 Agent 的推荐模型

小红书主页数据进入主平台后，不应该只是一个“文件”，也不应该只被压扁成历史笔记和评论样本。当前采用一个独立 input asset type：

- `xhs_creator_profile`：结构化保存主页、笔记、评论、互动数据和封面 `MediaAsset` 引用，schema 为 `xhs-creator-profile/v1`；
- 账号概况、历史笔记、评论样本：作为兼容旧 workflow 和人工检查的 legacy 派生资产继续生成；
- 图片资产：封面图作为笔记关联媒体；
- 可选的视频创作样本：如果后续抓视频文件或视频链接，再进入视频质量诊断链路。

主平台上传入口兼容两种 JSON：

- `xhs-profile-import/v1`：旧本地浏览器 importer 的可见页面导出；上传为 `xhs_creator_profile` 时会转换成 `xhs-creator-profile/v1`。
- `xhs-creator-profile/v1`：当前推荐的结构化主页资产 schema，可直接保存并用于账号诊断。

如果要同时导入封面，推荐把本地抓取结果整理成一个离线导入包，然后在前端选择整个文件夹：

```text
xhs_import_package/
  xhs_creator_profile.json
  images/
    <note_id>/
      0.jpg
```

`xhs_creator_profile.json` 中每条笔记可以显式写入：

```json
{
  "noteId": "note-1",
  "title": "笔记标题",
  "desc": "笔记正文",
  "cover": {
    "relativePath": "images/note-1/0.jpg",
    "caption": "笔记正文"
  }
}
```

后端只接受包内相对路径，不接受绝对路径或 `../`。导入时会创建 `xhs_creator_profile` input asset，并为每张封面创建或复用 `MediaAsset.image`。主页资产默认命名为 `XHS {小红书账号名} 创作者主页`；MediaCrawler fixture 会从笔记里的 `nickname` 推断账号名。封面命名规则是 `笔记标题_封面`，caption 和 user notes 优先使用笔记正文。

前端选择文件夹后会先在本地读取 `xhs_creator_profile.json` 做预览，不上传文件也不调用模型。预览会显示账号名、笔记数、评论数、图片文件数、匹配封面数和缺失封面数。浏览器目录上传通常会给文件路径加上顶层文件夹名前缀，例如 `_tt/images/...`；前端会在上传前剥掉公共顶层目录，使它与 JSON 里的 `images/...` 匹配。

重复导入同一个账号时，后端默认按同一 workspace 内的同名主页资产更新已有 `xhs_creator_profile`，避免列表膨胀。前端会在预览阶段提示“已存在，默认会更新已有资产”，并提供“另存为新主页”；该按钮通过 `saveAsNew=true` 强制创建新资产。封面媒体资产继续按 `笔记标题_封面` 复用。

主 Agent 读取时应通过 Context Access Layer 获取全局视野，而不是只拿单个文件。推荐 context pack：

```text
creator profile summary
+ top / recent historical posts
+ comments grouped by note
+ cover image references
+ existing analysis / topics / drafts / simulations
+ available skills / agents / workflows catalog
```

## 最小实现步骤

1. 增加 MediaCrawler JSONL converter。已完成。
   - 输入：`creator_contents_*.jsonl`、`creator_comments_*.jsonl`、`images/<note_id>/0.jpg`。
   - 当前实现：`scripts/xhs_mediacrawler_fixture.py`。
   - 输出：`xhs-creator-profile/v1` 结构化 payload、账号概况 Markdown、历史笔记 Markdown、评论样本 Markdown，并保留封面文件引用。

2. 增加一个本地 fixture 导入入口。已完成。
   - 当前实现：`scripts/import_xhs_fixture_to_workspace.py`。
   - 它直接写入本地 SQLite，不经过前端。
   - 导入时创建四个 input assets：小红书创作者主页、账号概况、历史笔记、评论样本。
   - 封面图片复制到主平台受控 upload 目录，并创建 `MediaAsset.image` 记录。
   - 重复导入同一个 fixture 时，文本资产按名称更新，图片资产按名称复用。

3. 增加主平台离线上传入口。已完成。
   - 前端位置：内容资产 → 小红书创作者主页 → 小红书离线导入。
   - 后端只接收上传文件，不访问小红书。
   - 上传旧 `xhs-profile-import/v1` JSON 时会转换成 workflow 可直接读取的 `xhs-creator-profile/v1`。
   - 推荐路径支持选择一个离线导入包文件夹；后端接收 profile JSON、图片文件和浏览器提供的相对路径，生成 XHS profile asset 与封面 media assets。
   - 前端导入前会展示本地预览；导入后完整展示 warning 列表。

4. 复用现有 Agent context adapter。已验证。
   - 主 Agent 不直接读取 MediaCrawler 原始文件。
   - Agent 通过 Context Access Layer 读取已经入库的 input assets 和 media assets。

5. 增加样本导入脚本。已完成。
   - 支持从 `data/xhs-fixtures/_tt` 和 `data/xhs-fixtures/QSheep` 一键导入本地 SQLite。
   - 用于 demo 和回归测试。

6. 增加通用导入包导出脚本。已完成。
   - 当前实现：`scripts/export_xhs_import_package.py`。
   - 输入任意 MediaCrawler `xhs/` 输出目录，生成前端可上传的 `xhs_creator_profile.json` 与 `images/<note_id>/0.jpg`。
   - 输出 summary：账号名、笔记数、评论数、封面数、缺失封面 warning。

7. 增加测试。已完成基础覆盖。
   - 已完成 converter 单元测试；
   - 已完成 UTF-8 中文保真测试；
   - 已完成短链解析 runner 单元测试；
   - 已完成 media asset 相关回归测试；
   - 已完成从 API 上传离线导入包并创建封面资产的回归测试。

## 本地导入命令

导入 `_tt`：

```bash
backend/.venv/bin/python scripts/import_xhs_fixture_to_workspace.py _tt
```

导入 `QSheep`：

```bash
backend/.venv/bin/python scripts/import_xhs_fixture_to_workspace.py QSheep
```

导入后会创建或更新两个工作区：

```text
XHS _tt 工作区
XHS QSheep 工作区
```

每个工作区包含：

- `XHS <code> 账号概况`
- `XHS <code> 历史笔记`
- `XHS <code> 评论样本`
- 每条笔记一张封面 `MediaAsset.image`

当前默认 SQLite 中已导入：

| 代号 | workspace | input assets | media assets |
| --- | --- | ---: | ---: |
| `_tt` | `XHS _tt 工作区` | 4 | 4 |
| `QSheep` | `XHS QSheep 工作区` | 4 | 20 |

如果要把任意 MediaCrawler 输出整理成前端可上传导入包：

```bash
backend/.venv/bin/python scripts/export_xhs_import_package.py \
  --input data/external/MediaCrawler/data/xhslink-20-comment-cover-test/xhs \
  --output data/xhs-import-packages/my_creator
```

然后在前端选择整个 `data/xhs-import-packages/my_creator` 文件夹。

小红书创作者主页详情页会优先展示结构化摘要，包括账号名、笔记数、评论数、封面引用数和高互动前 5 条；原始 JSON 仍保留在下方用于检查。

## 不做的事情

- 不把小红书爬虫变成主平台后端服务；
- 不在前端直接访问小红书；
- 不把 MediaCrawler 原始目录暴露给 Agent；
- 不允许用户提交任意本地文件路径；
- 不在这一阶段抓取二级评论、下载完整图片集或下载视频文件。

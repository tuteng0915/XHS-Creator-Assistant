<div align="center">

![SqsAgent：认识账号，听见读者，打磨下一篇](docs/assets/readme/cover.svg)

**面向小红书创作者的 AI 内容工作区**

从已有笔记认识账号，与不同读者对话，把想法打磨成作品。

[看看界面](#界面一览) · [本地运行](#快速开始) · [体验预写示例](docs/oracle-showcases.md) · [阅读文档](docs/README.md)

<sub>本地保存 · 默认 Qwen · 自选创作参考 · 人工确认采用</sub>

</div>

---

## 从账号积累，到下一篇作品

好内容不只从一个提示词开始。SqsAgent 把你的笔记、账号认识、模拟读者和创作历史留在同一个工作区，帮助你看见已经形成的表达特点，也听见下一篇可能遇到的不同声音。

**AI 提供分析和建议，你决定收录谁、写什么、采用哪些修改。**

| 从这里开始 | 你能得到什么 |
| --- | --- |
| **认识账号** | 导入笔记，梳理关键词、具体优势与内容表现，回看分析依据 |
| **认识读者** | 比较不同阅读需求与判断方式的人物候选，逐位收录，用固定头像记住不同声音 |
| **邀请试读** | 围绕账号、已发布笔记或当前创作，推荐或手选读者，进入群聊并追问 |
| **一起创作** | 自选账号／受众分析作为参考，左边与一个助手讨论，右边编辑稿件，预览后再采用建议 |
| **留下下一步** | 将账号与旧笔记的复盘转为后续选题，或用创作试读反馈修改当前稿件 |

每个账号有独立的材料与历史。推导读者需求时排除已识别的作者评论，原始记录仍保留；模拟读者用于启发创作，不代表真实粉丝意见或流量预测。

## 界面一览

红色点缀、轻量卡片，把注意力留给内容。以下截图使用现有组件与虚构演示内容，不含真实账号数据，也不是模型效果样本；点击可查看原图。

### 01 · 先看见账号的特点

先看到账号的概要、关键词与具体优势，再回看支撑判断的笔记。

[![账号分析：概要、关键词与具体优势](docs/assets/readme/account-analysis.jpg)](docs/assets/readme/account-analysis.jpg)

### 02 · 认识不同的读者

同样的话题，有人想找方法，有人更在意代价，也有人想看见另一种选择。比较候选后，再收录你想继续了解的读者。

[![模拟读者候选：四种不同的阅读需要与表达方式](docs/assets/readme/audience-readers.jpg)](docs/assets/readme/audience-readers.jpg)

### 03 · 把试读变成一场对话

听每位读者的独立意见，再看彼此回应；作者也可以下场追问。

[![读者群聊：独立意见、互相回应与作者追问](docs/assets/readme/reader-panel.jpg)](docs/assets/readme/reader-panel.jpg)

### 04 · 左边讨论，右边成稿

一个创作助手，陪你聊角度、起草正文或精修片段。只想写某个垂类，就只添加对应的分析记录；也可以不选额外参考，直接从当前稿件和对话出发。

[![创作助手：左侧对话与自选参考，右侧稿件编辑和保存](docs/assets/readme/writing-assistant.jpg)](docs/assets/readme/writing-assistant.jpg)

- **参考由你选**：添加、预览或移除具体的账号分析与受众分析，可同时使用多份记录。
- **建议由你采用**：先预览，也能继续编辑；放入稿件后，再由你保存。选中一段文字即可发起局部改写。
- **随时换个方向**：更换参考后，下一条消息开启新的对话段；旧对话仍能查看。手机端在“对话／稿件”之间切换，输入保留。

> **想亲自点一遍？** 已有 QSheep、秀才加点冰、Ag、一粒鱼四份档案时，可安装 [12 条预写示例](docs/oracle-showcases.md#打开方式)，在正常分析与模拟历史里体验。查看不调用模型；示例不随 Git 附带账号数据，也不是模型效果评测。

---

## 快速开始

以下为 macOS / Linux 的主应用启动方式。需要 **Python 3.11+**、**Node.js 22.12+（22.x）** 和 Git；完整安装及抓取环境见[本地安装指南](docs/local-installation.md)。

### 1. 获取代码，安装依赖

```bash
git clone https://github.com/tuteng0915/XHS-Creator-Assistant.git
cd XHS-Creator-Assistant
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install './backend[dev]'
npm --prefix frontend ci
```

### 2. 配置模型

在仓库根目录新建 `.env.local`，填入自己的密钥：

```dotenv
MODEL_PROVIDER=qwen
QWEN_API_KEY=你的密钥
QWEN_MODEL=qwen-plus
QWEN_PROFILE_MODEL=qwen3.8-max
```

默认使用 Qwen / DashScope，账号报告单独使用 Qwen3.8-Max，其余功能沿用 QWEN_MODEL。密钥由后端读取，不放进前端；`.env.local` 已被 Git 忽略。自定义端点、超时及兼容配置见[模型配置](docs/development.md#模型配置)。

### 3. 启动应用

终端一，从仓库根目录启动后端：

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二，从仓库根目录启动前端：

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

打开 **[http://127.0.0.1:5173](http://127.0.0.1:5173)**。

首次启动是空工作区。你可以[恢复协作者交付的数据包](docs/data-handoff.md)，或安装抓取依赖后从自己的主页开始导入。

> [!NOTE]
> **主页导入是可选安装项。** Git clone 不包含 MediaCrawler、账号数据或登录态。需要在线导入时，按[抓取依赖安装步骤](docs/local-installation.md#2-安装抓取依赖)配置固定版本及补丁；扫码窗口在运行后端的电脑打开。查看已有数据无需安装它。

## 把现有数据交给协作者

**代码走 Git，数据包私下发送。** 轻量交付只需数据库和上传文件，不搬运庞大的爬虫环境，也不必重新抓取已有账号。

[数据交接指南](docs/data-handoff.md)包含打包、恢复、可选的可信密钥交付和恢复检查。已有数据不要直接覆盖；小红书登录态不随包迁移。

## 面向本地使用的轻量架构

`React + TypeScript`　`FastAPI`　`LangGraph`　`SQLite`　`Qwen`

前后端通过 HTTP 与 SSE 交换数据，模型调用统一从后端发起。内容与历史保存在本地，界面、业务数据与执行流程各自独立。账号诊断、读者群聊各有自己的流程；创作助手使用单次写作回合，只读取当前稿件、当前对话段及作者选择的参考。

```text
frontend/   React + TypeScript：创作者界面与结果呈现
backend/    FastAPI + SQLite + LangGraph：数据、模型调用与协作流程
scripts/    导入适配、离线工具与验证脚本
docs/       安装、设计、架构与迭代记录
data/       本地数据库、上传文件与运行数据（不进入 Git）
index.html  早期单文件原型，仅作历史参考
```

> [!IMPORTANT]
> 当前面向本地单用户使用，没有登录认证和多租户隔离，不应直接暴露到公网。生成分析或内容时，相关材料会发往配置的模型服务；本地保存不等于离线推理。MediaCrawler 的使用范围需另行遵守其许可与平台规则。

## 深入阅读

| 文档 | 适合什么时候看 |
| --- | --- |
| [本地安装与排障](docs/local-installation.md) | 第一次运行，或配置主页导入、浏览器登录 |
| [数据交接](docs/data-handoff.md) | 把现有账号、笔记、作品与历史交给协作者 |
| [开发与验证](docs/development.md) | 调整模型配置、运行测试、做小规模复现 |
| [离线导入与兼容脚本](docs/offline-import.md) | 使用旧 JSON、MediaCrawler 输出或带封面的离线包 |
| [产品需求](docs/product-requirements.md) | 了解当前功能、交互决定与边界 |
| [人机共创设计](docs/creator-writing-collaboration-design.md) | 了解单助手、自选参考、局部改写与人工采用 |
| [Agent 与上下文架构](docs/agent-runtime-architecture.md) | 理解协作、任务上下文和持久化方式 |
| [当前进展与待办](docs/status-and-todo.md) | 区分已实现、已验证和仍待改进的部分 |

更多专题设计与历史资料见[完整文档导航](docs/README.md)。

<div align="center">

<sub>认识账号 · 听见读者 · 保留自己的表达</sub>

</div>

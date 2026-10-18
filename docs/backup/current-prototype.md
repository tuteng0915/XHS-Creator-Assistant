# 当前产品原型审计

本文只描述 `index.html` 当前实现的「小红书创作助手」，并给出面向创作者材料、分析、选题、草稿和受众模拟的迁移模型。它不是通用 Agent 平台设计。

## 0. 原型边界与执行模型

- 形态：单页、单文件 HTML/CSS/JavaScript 原型，没有后端、数据库或持久化层。
- 核心对象：账号定位、历史笔记、评论原文、热点帖子 CSV、诊断结果、痛点、选题、内容结构、受众原型、模拟反应与综合建议。
- 两条主工作流：A「账号诊断」与 B「热点分析」。受众模拟是可从任一主工作流进入的独立发布前测试流程。
- 两种运行模式：`demo` 使用内置固定样例并用延时模拟渐进生成；`live` 从浏览器直接调用 Anthropic Messages API，模型固定为 `claude-sonnet-4-6`。
- 当前没有保存、打开历史记录、恢复任务、编辑生成结果、导出或版本管理能力。刷新页面后，除源码内置样例外，所有用户输入和生成结果都会丢失。
- 页面顶部把产品主链路概括为「主页诊断 → 痛点归类 → 选题生成 → 结构复盘」，另有「受众模拟 · 多智能体讨论」。热点分析在代码中是另一条输入与分析路径。

## 1. 所有用户可见工作流

### 1.1 页面进入与基础操作

1. 用户进入页面，看到左侧输入面板和右侧空状态。
2. 用户在「账号诊断 / 热点分析」间切换。
3. 用户可以点击「载入样例」填充当前工作流的示例输入。
4. 用户可以在「演示模式 / 实时生成」间切换；实时模式显示 API Key 输入框。
5. 用户可以点击主按钮执行当前工作流，或点击「受众模拟」直接测试「下期选题」。

当前实际行为中的重要细节：

- 初始界面文案称左侧“已预置”样例，但输入框实际为空；必须点击「载入样例」才会填入。
- 切换工作流不会清空另一工作流的输入，也不会清空右侧结果。
- 切换模式只改变 API Key 区域和按钮文案，不转换或重跑已有结果。
- 所有结果共用右侧 `#out`，开始任一诊断或模拟都会覆盖之前的结果。

### 1.2 账号诊断工作流

用户输入：

- 账号定位 `positioning`：账号、核心人群、内容主张、作者优势与目标等自由文本。
- 主页/历史笔记与表现数据 `notes`：约定格式为「标题｜数据｜爆/平/差」。
- 评论区原文 `comments`：一行一条。
- 可选的下期选题 `simTopic`：不参与账号诊断，只供后续受众模拟。

入口：选择「账号诊断」，选择 demo/live，点击「生成诊断」或「调用 Claude 生成」。

#### Demo

- 不读取用户当前填写的账号定位、笔记或评论。
- 固定使用 `SAMPLE_RESULT`，依次显示主页诊断、痛点归类、选题生成、结构复盘。
- 通过 700ms、500ms、700ms、600ms 延时制造逐段生成效果。

#### Live

1. 初始化四个 loading stage。
2. 并行执行账号画像/爆款基因分析和评论痛点归类。
3. 至少一个并行结果成功后，用可用结果生成选题及标题变体。
4. 取 `topics[0].title` 作为唯一选中选题，生成内容结构。
5. 右侧逐阶段替换 loading；阶段失败时就地显示错误。

### 1.3 从生成选题填入受众模拟

1. 账号诊断或热点分析生成选题后，每张选题卡显示「填入下期选题」。
2. 点击后，从 `_lastTopics[activeWorkflow][index]` 取出选题。
3. 把以下文本写入 `simTopic`：

   ```text
   {title}
   切入角度：{angle}
   ```

4. 此操作不自动开始模拟，也不保存“已选中选题”的独立 ID；它只是复制文本。

### 1.4 热点分析工作流

用户输入：

- 账号定位 `positioning`：与账号诊断共用同一输入框。
- 话题关键词 `trendKeyword`。
- 热帖数据 `csvText`：粘贴 CSV/TSV，或通过 `csvFile` 上传；界面期望至少含标题、点赞、收藏字段，并提示可含 `comments`、`tags`、`content_snippet`、`date`。
- 可选的下期选题 `simTopic`：只供受众模拟。

#### 文件上传

1. 浏览器 `FileReader` 以 UTF-8 读取本地 `.csv`/`.tsv`。
2. 原文写入 `csvText`。
3. `parseCSVText` 解析行数，在 `csvStat` 显示「已载入 N 条」。
4. 文件本身不会上传到应用服务器，但实时分析时，压缩后的前 50 条会发送给 Anthropic。

#### Demo

- 「载入样例」会填入数字游民账号定位、关键词和一段“预览文本”，并显示 15 条演示数据状态；真正的演示输出来自固定 `SAMPLE_TREND_RESULT`，不是对预览文本重新分析。
- 逐步显示热点归纳、痛点归类、选题生成、结构复盘。
- 代码声明了五个 stage（第四是标题变体、第五是结构复盘），但 demo 只填 1–4，并把结构写入第四 stage；第五 stage 永久 loading。

#### Live

1. 要求 `csvText` 非空；关键词和账号定位可为空。
2. 解析 CSV/TSV。
3. 以 `likes + collects` 降序，最多取前 50 条。
4. 把每条压缩为序号、点赞、收藏、标题、标签和最多 60 字内容片段。
5. 并行执行热点归纳和痛点归类。
6. 至少一个结果成功后生成选题和标题变体。
7. 取 `topics[0].title`，结合热点爆款规律生成结构。
8. 与 demo 相同，五阶段 UI 实际只填 1–4；标题变体虽已由模型返回，却没有渲染，结构被写入第四 stage，第五 stage 留在 loading。

### 1.5 受众模拟工作流

入口：可在账号诊断或热点分析任一 tab 中填写/带入 `simTopic`，选择模式，点击「受众模拟」。

#### Demo

- 根据 `activeWorkflow` 选择 `SAMPLE_SIMULATION` 或 `SAMPLE_SIMULATION_B`。
- 不读取用户当前 `simTopic`；即使用户改了题目，仍模拟固定样例题目。
- 先显示受众原型，再逐个显示初读反应，再逐个显示互动讨论，最后显示综合评估。
- 受众原型为 3 个，反应和讨论均为预置固定文本。

#### Live

1. 校验 `simTopic` 非空。
2. 读取账号定位；账号诊断上下文使用评论原文，热点上下文只使用话题关键词。
3. 生成 3 个典型受众原型。
4. 为每个原型并行生成一次第一人称初读反应。
5. 为每个原型并行生成一次针对其他人的互动回应。
6. 生成综合评估。
7. 渲染受众卡、初读反应、互动讨论、最有共鸣受众、争议点和优化建议。

注意：热点 tab 的 persona 生成只用「账号定位 + 关键词」，并没有把 CSV 内容传给 persona 调用。代码虽然构造了 CSV 作为 `comments` fallback，但热点分支不会使用这个变量。

### 1.6 Demo / Live 模式工作流

#### Demo 模式

- 默认模式。
- 完全离线，使用源码内置数据。
- 通过延时和 loading 态模拟生成。
- 诊断输出与用户输入解耦；主要用途是展示既定产品故事和统一渲染器。

#### Live 模式

- 显示 API Key 输入框。
- 用户没有填写 Key 时，主诊断或受众模拟直接显示提示。
- 浏览器向 `https://api.anthropic.com/v1/messages` 发起请求。
- 所有调用使用 `claude-sonnet-4-6`；代码注释中的“Haiku Phase 1”与实际模型不符。
- 页面加载时会尝试 `fetch('./key')` 并把成功读取的文本自动填入 API Key 输入框。

## 2. 每个工作流阶段及输入/输出

### 2.1 账号诊断

| 阶段 | 输入 | 处理 | 输出 | 下一阶段 |
| --- | --- | --- | --- | --- |
| ① 主页诊断 | `positioning`, `notes` | 分析内容支柱、标题公式、钩子、爆款结构、风格指纹；若有表现数据则做高低表现对比 | `profile` | 选题生成、结构生成、主页诊断 UI |
| ② 痛点归类 | `comments` | 聚合 3–5 个痛点，按强度和数量排序，并保留证据 | `painPoints[]` | 选题生成、痛点 UI |
| ③ 选题生成 | `positioning`, `{profile}`, `{painPoints}` | 生成 3–4 个选题和 2 组标题变体 | `topics[]`, `titles[]` | 选题 UI、`_lastTopics.a`、结构生成；`titles` 当前被丢弃 |
| ④ 结构复盘 | `positioning`, `profile.voiceFingerprint`, `profile.viralStructure.name`, `topics[0].title` | 为第一条选题生成骨架和可复用表达结构 | `structure` | 结构 UI |

降级逻辑：阶段 ① 或 ② 单独失败时，阶段 ③仍用另一个结果继续；两者都失败则停止。阶段 ③失败会同时终止阶段 ④。阶段 ④失败只影响自身。

### 2.2 热点分析

| 阶段 | 输入 | 处理 | 输出 | 下一阶段 |
| --- | --- | --- | --- | --- |
| 0 数据准备 | `csvText` | 解析字段、按点赞+收藏排序、取 top 50、压缩文本 | `rows[]`, `postsStr` | 阶段 ①、② |
| ① 热点归纳 | `trendKeyword`, `positioning`, `postsStr` | 归纳高频主题、爆款规律、供需机会 | `trendAnalysis` | 选题生成、热点 UI、结构上下文 |
| ② 痛点归类 | `trendKeyword`, `postsStr` | 复用评论分析 prompt，从帖子标题/片段推断痛点 | `painPoints[]` | 选题生成、痛点 UI |
| ③ 选题生成 | `positioning`, `{trendAnalysis}`, `{painPoints}` | 生成适配账号且有热度依据的选题和标题变体 | `topics[]`, `titles[]` | 选题 UI、`_lastTopics.b`、结构生成；`titles` 当前未渲染 |
| ④ 标题变体（声明） | `titles[]` | 当前没有执行渲染 | 应显示标题变体 | 无；当前 stage 被结构结果占用 |
| ⑤ 结构复盘（声明） | `positioning`, `trendAnalysis.viralPatterns`, `topics[0].title` | 实际模型调用存在，但结果写入 stage ④ | `structure` | 应进入 stage ⑤；当前 stage ⑤保持 loading |

### 2.3 受众模拟

| 阶段 | 输入 | 处理 | 输出 | 下一阶段 |
| --- | --- | --- | --- | --- |
| 0 内容选择 | `simTopic` 或选题卡复制出的标题+角度 | 校验非空 | `topic` 文本 | 全部模拟阶段 |
| 人设归纳 | A：`positioning + comments`；B：`positioning + trendKeyword` | 生成 3 个受众原型并归一化字段别名 | `personas[]` | 初读反应、互动讨论、受众 UI |
| ① 初读反应 | 单个 persona + `topic` | 每个 persona 一次并行调用 | `reactions[]`，含 `text`, `sentiment`，本地补 `personaId`, `personaArchetype` | 讨论 prompt、综合评估、反应 UI |
| ② 互动讨论 | 单个 persona + 其他 persona 的初读反应 + `topic` | 每个 persona 一次并行调用，要求 @ 具体对象 | `debate[]`，含 `text`, `stance` | 讨论 UI；当前不进入综合评估输入 |
| ③ 综合评估 | `topic` + 所有初读反应 | 预测共鸣人群、争议和优化建议 | `synthesis` | 综合评估 UI |

当前综合评估没有读取互动讨论输出，尽管系统 prompt 称“基于受众模拟讨论”。

## 3. 全局应用状态

### 3.1 可变 JavaScript 全局状态

| 状态 | 初值 | 作用 | 生命周期/问题 |
| --- | --- | --- | --- |
| `mode` | `'demo'` | 当前运行模式 | 仅内存；刷新重置 |
| `activeWorkflow` | `'a'` | 当前工作流：`a` 账号、`b` 热点 | 仅内存；切换不取消运行中的任务 |
| `_lastTopics` | `{a:[], b:[]}` | 保存每条工作流最近一次生成的选题，供一键填入模拟 | 仅内存；没有 run/version 元数据 |
| `_gen` | `0` | 账号/热点实时生成计数，尝试丢弃旧异步成功回调 | 只保护部分 `.then`，不保护 catch、demo、simulation 或后续阶段 |
| `titles` | 未声明 | 热点 live 中 `titles = d.titles` 意外创建的隐式全局 | 非 strict 模式才可用；从未消费，是 bug |

函数内部但贯穿某次运行的重要临时状态包括 `profile`、`painPoints`、`trendAnalysis`、`topics`、`personas`、`reactions`、persona map `pm`、解析后的 `rows` 和压缩后的 `postsStr`。这些都不会在运行结束后作为完整运行对象保留。

### 3.2 全局常量与内置产品数据

- 工具：`delay`。
- 账号 demo 输入与输出：`SAMPLE`、`SAMPLE_RESULT`。
- 账号受众模拟：`SAMPLE_SIMULATION`。
- 热点受众模拟：`SAMPLE_SIMULATION_B`。
- 账号 prompts：`PROMPT_PROFILE`、`PROMPT_PAIN_POINTS`、`PROMPT_TOPICS`、`PROMPT_STRUCTURE`。
- 热点 prompts：`PROMPT_TREND_ANALYSIS`、`PROMPT_TOPICS_B`，并复用 `PROMPT_PAIN_POINTS`、`PROMPT_STRUCTURE`。
- 阶段定义：`STAGE_META`、`STAGE_META_B`。
- 热点 demo：`SAMPLE_TREND_POSITIONING`、`SAMPLE_TREND_KEYWORD`、`SAMPLE_TREND_POSTS`、`SAMPLE_TREND_RESULT`。

### 3.3 DOM 承载的全局状态

当前大部分“应用状态”实际保存在 DOM 中：

| DOM ID | 数据 |
| --- | --- |
| `positioning` | 两条工作流共用的账号定位文本 |
| `notes` | 历史/对标笔记与表现数据 |
| `comments` | 评论原文 |
| `trendKeyword` | 热点关键词 |
| `csvText` | CSV/TSV 原文或 demo 预览文本 |
| `csvFile` | 当前选择的本地文件句柄（浏览器控件状态） |
| `csvStat` | 载入/分析条数提示 |
| `simTopic` | 待模拟的标题、角度或草稿文本 |
| `apiKey` | Anthropic API Key 明文值（password input 只遮罩显示） |
| `out` | 当前唯一结果视图；也是 loading/error/阶段进度状态 |
| `m-demo`, `m-live`, `apiBox` | 模式的视觉状态 |
| `wf-a`, `wf-b`, `tab-a`, `tab-b`, `runBtn` | 工作流选择和按钮文案状态 |

### 3.4 没有被保存的状态

- 当前输入内容和上传文件原文。
- 任一次模型调用的请求、响应、错误、耗时、token 使用和模型版本快照。
- 账号诊断、热点分析、选题、标题变体、结构、模拟结果。
- 用户从哪条分析中选择了哪条选题。
- 选题或草稿的编辑历史及发布状态。

## 4. 所有模型调用

### 4.0 统一传输与解析

所有 live 调用都经过：

```js
callChunk(key, model, system, user, maxTokens, tool?)
```

请求：

- Endpoint：`POST https://api.anthropic.com/v1/messages`
- Headers：`content-type: application/json`、`x-api-key`、`anthropic-version: 2023-06-01`、`anthropic-dangerous-direct-browser-access: true`
- Body：`model`、`max_tokens`、单条 user message、可选 `system`。
- 有 `tool` 时：发送单个 tool 与强制 `tool_choice`，直接使用返回的 `tool_use.input`。
- 无 `tool` 时：拼接所有 text block，移除 Markdown fence，截取第一个 JSON object/array 到最后一个闭合符；失败后用 `fixJsonNewlines` 修复裸换行、制表符和部分裸引号再解析。

下述每个调用的 `model` 均为 `claude-sonnet-4-6`。

### 4.1 账号画像 / 爆款基因

调用位置：`runLiveChunked` Phase 1，与痛点归类并行；`max_tokens = 2000`；文本 JSON 模式。

System prompt（完整）：

```text
你是创作者账号分析师。基于历史笔记和账号定位，分析这个账号的爆款基因。
规则：
- pillars 每条 10 字以内，概括性词组，不加冒号或括号展开
- 若笔记含数据（格式「标题｜数据｜爆/平/差」），必须提供 contrast 对比诊断
- winFactors/loseFactors/takeaways 落到选题类型/标题变量/内容形态，不泛泛而谈
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"profile":{"pillars":[],"titleFormulas":[{"formula":"","examples":[]}],"hookStyles":[],"viralStructure":{"name":"","steps":[]},"voiceFingerprint":[],"contrast":{"winners":[{"title":"","metric":""}],"losers":[{"title":"","metric":""}],"winFactors":[],"loseFactors":[],"takeaways":[]}}}
```

输入上下文：

```text
【账号定位】
{positioning}

【历史/对标笔记】
{notes}
```

输出 schema：prompt 中的 `profile` object；字段为 `pillars[]`、`titleFormulas[{formula,examples[]}]`、`hookStyles[]`、`viralStructure{name,steps[]}`、`voiceFingerprint[]`、`contrast{winners[],losers[],winFactors[],loseFactors[],takeaways[]}`。文本模式没有 API 层强校验。

下游：`buildProfileHtml`；选题调用的 `{profile}`；结构调用的 `voiceFingerprint` 和 `viralStructure.name`。应持久化为一次账号分析快照。

### 4.2 账号评论痛点归类

调用位置：`runLiveChunked` Phase 1；`max_tokens = 800`；强制 tool use。

System prompt（完整）：

```text
你是评论区分析师。聚合评论区原文，提炼 3~5 个读者痛点主题，每个带原文证据。
排序规则：intensity 高→中，同级按 count 降序。
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"painPoints":[{"theme":"","intensity":"高/中","count":0,"evidence":[]}]}
```

输入上下文：

```text
【评论区原文】
{comments}
```

Tool/output schema：

```json
{
  "type": "object",
  "required": ["painPoints"],
  "properties": {
    "painPoints": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["theme", "intensity", "count", "evidence"],
        "properties": {
          "theme": {"type": "string"},
          "intensity": {"type": "string", "enum": ["高", "中"]},
          "count": {"type": "integer"},
          "evidence": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

下游：`buildPainPointsHtml`；账号选题生成。应把 cluster 与其引用的原评论建立可追溯关系，而不只保存截断证据文本。

### 4.3 账号选题与标题变体

调用位置：`runLiveChunked` Phase 2；`max_tokens = 2000`；文本 JSON 模式。

System prompt（完整）：

```text
你是内容选题策略师。基于账号定位、爆款基因诊断和评论区痛点，生成 3~4 个选题 + 2 组标题变体。
重要约束：
① topics[0] 必须对应 painPoints[0]（最高频/最高强度痛点），直接命中它
② 每个 whyFit 必须结合账号的惯用结构和风格指纹，不能是通用表述
③ titles 选 topics[0] 和 topics[1] 各给 3 条变体，贴合已归纳的标题公式，不贩卖焦虑
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"topics":[{"title":"","angle":"","pain":"","whyFit":""}],"titles":[{"topic":"","variants":[]}]}
```

输入上下文：

```text
【账号定位】
{positioning}

【爆款基因】
{JSON.stringify({profile})}

【痛点】
{JSON.stringify({painPoints})}
```

输出 schema：`topics[{title,angle,pain,whyFit}]`、`titles[{topic,variants[]}]`；无 API 层强校验。

下游：`topics` 进入 `buildTopicsHtml`、`_lastTopics.a`、一键填入受众模拟、第一条选题进入结构调用。`titles` 当前被读取但没有赋值给局部变量，也没有渲染或保存，实际丢失。

### 4.4 账号内容结构

调用位置：`runLiveChunked` Phase 3；`max_tokens = 1500`；文本 JSON 模式。

System prompt（完整）：

```text
你是内容结构师。为指定选题写完整笔记骨架，并提炼可跨选题复用的表达结构。
重要：topicChosen 必须与输入的「选题」原文完全一致。
只输出 JSON，不要任何解释或 markdown 代码块。schema:
{"structure":{"topicChosen":"","outline":[{"sec":"","ct":""}],"reuse":""}}
```

输入上下文：

```text
【账号定位】
{positioning}

【风格指纹】
{profile.voiceFingerprint 以“；”连接，profile 缺失则为空}

【爆款结构】
{profile.viralStructure.name，profile 缺失则为空}

【选题】
{topics[0].title}
```

输出 schema：`structure{topicChosen,outline[{sec,ct}],reuse}`；无强校验。

下游：`buildStructureHtml`。`topicChosen` 当前不显示，只有 `outline` 与 `reuse` 被消费。

### 4.5 热点归纳

调用位置：`runTrendLiveChunked` Phase 1，与热点痛点并行；`max_tokens = 2000`；文本 JSON 模式。

System prompt（完整）：

```text
你是内容趋势分析师。基于一批小红书热帖数据（标题+互动数+标签+内容片段），分析该话题下的内容热点规律。
分析维度：
- themes：识别3~5个高频内容主题，每个给 count（相关帖子数）、topPost（代表帖标题）、engagement（高/中/低）、summary（一句话总结）
- viralPatterns：总结2~4个让内容高互动的共性规律，要落到可操作的创作建议上
- opportunityWindows：指出2~3个「需求强但供给少」的内容机会角度
只输出 JSON，不要解释。schema:
{"trendAnalysis":{"themes":[{"theme":"","count":0,"topPost":"","engagement":"高/中/低","summary":""}],"viralPatterns":[""],"opportunityWindows":[""]}}
```

输入上下文：

```text
话题关键词：{trendKeyword 或“（未指定）”}
账号定位：{positioning}

热帖数据（按互动量排序）：
{postsStr}
```

其中每行 `postsStr` 为：

```text
{序号}. [赞{likes或0}/藏{collects或0}] {title} {可选“标签:”+tags} {content_snippet 前60字符}
```

输出 schema：`trendAnalysis{themes[{theme,count,topPost,engagement,summary}],viralPatterns[],opportunityWindows[]}`；无强校验。

下游：`buildTrendAnalysisHtml`；热点选题生成；`viralPatterns` 进入结构调用。应与输入热点数据集及采集时间一起持久化。

### 4.6 热点内容痛点归类

调用位置：`runTrendLiveChunked` Phase 1；`max_tokens = 1000`；强制 tool use。

System prompt：与 4.2 的 `PROMPT_PAIN_POINTS` 完全相同。

输入上下文：

```text
以下是小红书「{trendKeyword 或“该话题”}」相关热帖的标题和内容，请从中归纳读者高频痛点：
{postsStr}
```

输出 schema：与 4.2 的 `pain_points` tool 完全相同。

下游：`buildPainPointsHtml`；热点选题生成。这里的 evidence 来源其实是帖子标题/内容片段，不一定是评论原文，语义与账号诊断中的“评论痛点”不同。

### 4.7 热点选题与标题变体

调用位置：`runTrendLiveChunked` Phase 2；`max_tokens = 2000`；文本 JSON 模式。

System prompt（完整）：

```text
你是内容选题策略师。基于账号定位、热点趋势分析和评论区痛点，生成3~4个选题 + 2组标题变体。
重要约束：
① 每个选题必须同时满足：「话题热度高」AND「与账号定位匹配」
② topics[0] 必须对应 painPoints[0]（最高频痛点）
③ 每个选题带两个维度：whyFit（为什么适合这个账号）+ whyTrending（为什么现在是好时机）
④ titles 选 topics[0] 和 topics[1] 各给3条变体，利用热帖中验证过的标题模式
只输出 JSON，不要解释。schema:
{"topics":[{"title":"","angle":"","pain":"","whyFit":"","whyTrending":""}],"titles":[{"topic":"","variants":[]}]}
```

输入上下文：

```text
账号定位：{positioning}

热点趋势分析：
{JSON.stringify({trendAnalysis})}

读者痛点：
{JSON.stringify({painPoints})}
```

输出 schema：`topics[{title,angle,pain,whyFit,whyTrending}]`、`titles[{topic,variants[]}]`；无强校验。

下游：`topics` 进入通用 `buildTopicsHtml`、`_lastTopics.b`、模拟填入与结构生成。`whyTrending` 不被通用渲染器读取。`titles` 被赋给未声明的全局 `titles`，但没有渲染或保存。

### 4.8 热点选题结构

调用位置：`runTrendLiveChunked` Phase 3；`max_tokens = 1500`；文本 JSON 模式。

System prompt：与 4.4 的 `PROMPT_STRUCTURE` 完全相同。

输入上下文：

```text
账号定位：{positioning}

热点背景：该话题下的爆款内容规律——{trendAnalysis.viralPatterns 以“；”连接；缺失则为空}

选题：{topics[0].title}
```

输出 schema：与 4.4 相同。

下游：`buildStructureHtml`，但错误地写入 stage ④而非声明的 stage ⑤。

### 4.9 受众原型归纳

调用位置：`runSimulationLive`；每次模拟一次；`max_tokens = 1200`；强制 tool use。

System prompt（完整）：

```text
你是受众分析专家。归纳3个典型受众原型（用 archetype 描述类型，不需要虚构名字）。color 三个分别用 #4f46e5/#16a34a/#d97706。
```

输入上下文按工作流分支：

```text
# 账号诊断
账号定位：{positioning}

评论区：
{comments；若 comments 为空，代码可构造 csvText 前800字 fallback，但账号 tab 正常使用 comments}

# 热点分析
账号定位：{positioning}

话题关键词：{trendKeyword}
```

前置校验存在逻辑缺口：账号分支只在 `positioning` 为空时才报错，即定位非空、评论为空也会继续；热点分支只在定位为空且关键词为空时才报错，任一非空即可继续，与错误文案“定位和关键词”不一致。

Tool/output schema：

```json
{
  "type": "object",
  "required": ["personas"],
  "properties": {
    "personas": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["archetype"],
        "properties": {
          "id": {"type": "string"},
          "archetype": {"type": "string"},
          "background": {"type": "string"},
          "personality": {"type": "string"},
          "concerns": {"type": "string"},
          "color": {"type": "string"}
        }
      }
    }
  }
}
```

返回后进行兼容归一化：`archetype/type/role/name`、`background/desc`、`personality/character`、`concerns/focus/interest` 可互相 fallback；缺失 ID 用原型文字或随机数；缺失 color 用固定三色。

下游：`buildPersonaCards`；每个 persona 的反应与讨论 prompt；persona ID map；模拟结果 UI。应持久化为该模拟运行的 persona snapshot，而不是覆盖全局受众定义。

### 4.10 单个受众的初读反应

调用位置：`runSimulationLive`，每个 persona 一次、并行；`max_tokens = 300`；强制 tool use。若有 3 个 persona，即 3 次模型调用。

动态 System prompt（完整模板）：

```text
你是{persona.archetype}。背景：{persona.background}。性格：{persona.personality}。关注：{persona.concerns}。你刚看了这篇小红书内容，给出真实第一反应，用第一人称，2-3句。
```

输入上下文：

```text
内容：{simTopic}
```

Tool/output schema：

```json
{
  "type": "object",
  "required": ["text", "sentiment"],
  "properties": {
    "text": {"type": "string"},
    "sentiment": {"type": "string", "enum": ["positive", "mixed", "negative"]}
  }
}
```

下游：本地补充 `personaId` 和 `personaArchetype` 后进入 `reactions[]`；`buildReactionItem`；所有其他 persona 的讨论上下文；综合评估。失败时静默降级为 `（获取失败）/mixed`，但 loading DOM 未被替换，界面可能一直转圈。

### 4.11 单个受众的互动讨论

调用位置：`runSimulationLive`，每个 persona 一次、并行；`max_tokens = 300`；强制 tool use。

动态 System prompt（完整模板）：

```text
你是{persona.archetype}。背景：{persona.background}。性格：{persona.personality}。你看完内容，也看到了其他受众（{otherTypes，以“、”连接}）的反应，现在轮到你回应，必须用@{otherTypes 中第一个类型}这样的格式@具体的人，可认同/反驳/补充，体现你的性格，2-3句。
```

输入上下文：

```text
原内容：{simTopic}

其他人反应：
{每行“{personaArchetype}说：\"{reaction.text}\"”}
```

Tool/output schema：

```json
{
  "type": "object",
  "required": ["text", "stance"],
  "properties": {
    "text": {"type": "string"},
    "stance": {"type": "string", "enum": ["agree", "disagree", "nuanced"]}
  }
}
```

下游：仅 `buildDebateItem`。结果没有收集进数组，也没有传给综合评估；失败被完全吞掉，loading 永久保留。

### 4.12 综合评估

调用位置：`runSimulationLive`；每次模拟一次；`max_tokens = 1200`；强制 tool use。

System prompt（完整）：

```text
你是内容策略分析师。基于受众模拟讨论，给出内容发布前的综合评估。
```

输入上下文：

```text
内容：{simTopic}

讨论记录：
{每行“[初读] {persona.archetype}: {reaction.text}”}
```

实际没有包含互动讨论内容。

Tool/output schema：

```json
{
  "type": "object",
  "required": ["topResonance", "controversyPoints", "suggestions"],
  "properties": {
    "topResonance": {
      "type": "object",
      "required": ["persona", "reason", "expectedBehavior"],
      "properties": {
        "persona": {"type": "string"},
        "reason": {"type": "string"},
        "expectedBehavior": {"type": "string"}
      }
    },
    "controversyPoints": {"type": "array", "items": {"type": "string"}},
    "suggestions": {"type": "array", "items": {"type": "string"}}
  }
}
```

下游：`buildSynthesisHtml`。应与被测试的 draft/topic 版本、persona snapshot、全部 reaction/debate 一起保存。

## 5. 应考虑持久化的全部生成数据

持久化不等于所有数据永远保留；这里列出需要可追溯、可复用或可比较的数据。

### 5.1 创作者材料

- 账号定位原文及版本：核心人群、内容主张、作者优势、目标。
- 历史笔记原文与结构化条目：标题、正文/摘要、点赞、收藏、评论、表现标签、发布时间、来源。
- 评论原文：每条评论、来源笔记、采集时间；痛点证据应引用 comment ID。
- 热点关键词。
- 上传的热点数据集：原文件元数据、字段映射、解析后的帖子、采集时间、排序规则；是否保留原文件可按隐私策略决定。
- 热点帖子结构化字段：标题、赞、藏、评、标签、片段、日期和来源行。

### 5.2 分析结果

- 账号 profile：内容支柱、标题公式及例子、钩子风格、爆款结构、风格指纹、赢家/输家、成功/失败因素、可执行结论。
- 痛点 cluster：主题、强度、数量、证据引用，以及来源类型（评论或热点帖子）。
- 热点分析：themes、代表帖、热度、summary、viralPatterns、opportunityWindows。
- 每次分析的输入快照、prompt 版本、模型、输出原文/结构化结果、运行状态、错误与创建时间。

### 5.3 选题与内容资产

- 每条生成选题：标题、角度、对应痛点、账号匹配理由、热点时机理由、来源分析 run。
- 标题变体及其关联的选题。
- 用户选中、收藏、淘汰或编辑后的选题状态。
- 内容结构：`topicChosen`、outline sections、可复用表达结构、来源 topic 版本。
- 从选题结构继续发展的草稿正文；虽然当前原型只到结构，但 workspace 必须允许结构成为 draft 的一个版本。
- 选题/结构/草稿的版本链，避免模拟结果与后续改稿错配。

### 5.4 受众模拟数据

- 被测试内容的精确快照，而不只是可变的 `simTopic` 文本。
- persona snapshots：ID、原型、背景、性格、关注点、颜色及生成依据。
- 每个 persona 的 reaction：文本、sentiment、失败状态。
- 每个 persona 的 debate：文本、stance、目标对象、失败状态。
- synthesis：topResonance、controversyPoints、suggestions。
- 模拟 run 的输入来源（topic/draft/version）、所用账号/热点上下文、模型与 prompt 版本、时间和状态。

### 5.5 不应作为普通内容资产持久化的数据

- API Key 不应进入 workspace、运行记录、日志或导出。
- 未经需要不保存完整第三方 API 错误响应，因为其中可能回显敏感上下文。
- UI loading DOM、spinner 状态不属于产品数据；应转换为明确的 run/stage status。

## 6. UI 渲染函数及其数据契约

| 函数 | 期望数据 | 输出/副作用 | 当前缺口 |
| --- | --- | --- | --- |
| `esc(x)` | 任意可字符串化值 | 转义 `& < >` | 不转义引号；用于 HTML 文本通常足够，但不能保护属性上下文 |
| `buildProfileHtml(pr)` | `profile`；数组字段可缺省；`contrast` 可选 | 账号诊断 HTML | 不显示 `voiceFingerprint`；依赖多层字段形状但无完整校验 |
| `buildPainPointsHtml(pp)` | `painPoints[]`，每项 `{theme,intensity,count,evidence[]}` | 痛点卡 HTML | 非“高”一律按“中”样式；count 未转义/校验 |
| `buildTopicsHtml(topics)` | `{title,angle,pain,whyFit}[]` | 选题卡和 fill 按钮 | 不显示热点专属 `whyTrending`；不显示标题变体 |
| `fillSimTopic(i)` | `_lastTopics[activeWorkflow][i]` | 写入 `simTopic` | 用数组索引而非稳定 topic ID；异步/切换时可能错配 |
| `buildTitlesHtml(titles)` | `{topic,variants[]}[]` | 标题变体卡 HTML | 已实现但任何流程都未调用 |
| `buildStructureHtml(s)` | `{outline:[{sec,ct}],reuse}` | 结构与复用模板 HTML | 不显示/核对 `topicChosen` |
| `initDiagnosisStages()` | `STAGE_META` | 重建四阶段 loading UI | 覆盖所有已有输出 |
| `fillStage(n,html,desc?)` | stage 编号、已构造 HTML、可选描述 | 替换 stage body | `html` 被直接写入 `innerHTML`，调用者必须保证安全 |
| `buildPersonaCards(personas)` | `{id,archetype,background,personality,concerns,color}[]` | persona card HTML | `color` 进入 style、原型首字进入 HTML，首字未 `esc`；颜色无白名单 |
| `buildReactionItem(p,r)` | persona + `{text,sentiment}` | 反应消息 HTML | `p.id`、`p.color` 未按属性上下文处理 |
| `buildDebateItem(p,d)` | persona + `{text,stance}` | 讨论消息 HTML | 同上；不显示明确 targetedAt |
| `buildSynthesisHtml(s)` | `{topResonance,controversyPoints[],suggestions[]}` | 综合评估 HTML | 对缺省字段较宽容 |
| `initTrendStages()` | `STAGE_META_B` | 重建五阶段 loading UI | 当前执行只填四阶段，编号契约已失配 |
| `buildTrendAnalysisHtml(ta)` | `{themes[],viralPatterns[],opportunityWindows[]}` | 热点主题、规律与机会 HTML | engagement 仅“高”有 high，其余均 mid；count 未校验 |
| `showErr(m)` | 错误字符串 | 用错误卡覆盖 `#out` | `m` 未转义，存在 DOM XSS 风险 |

不纯粹是渲染器、但直接控制 UI 的函数：

- `setMode(m)`：更新 mode 按钮、API box 和主按钮文案。
- `setWorkflow(w)`：更新 tab、active button 和主按钮文案。
- `loadSample()`：按当前 workflow 写入输入 DOM。
- `handleFileUpload(input)`：读取文件、写 `csvText` 与 `csvStat`。
- `runDemoProgressive` / `runTrendDemoProgressive` / `runSimulationDemo`：把预置数据按延时送入渲染器。
- `runLiveChunked` / `runTrendLiveChunked` / `runSimulationLive`：同时承担 orchestration、状态管理、API 调用和 DOM 更新。

## 7. 账号诊断与热点分析的重复逻辑

| 重复点 | 账号诊断 | 热点分析 | 迁移建议 |
| --- | --- | --- | --- |
| 四段主链路 | profile → pain → topics → structure | trends → pain → topics → structure | 保留两种产品 recipe，但共用 run/stage 基础设施 |
| Phase 1 并行 | profile + pain | trend + pain | 共用并行 stage runner、取消与错误状态 |
| 痛点模型 | 评论原文 + `PROMPT_PAIN_POINTS` | 热帖压缩文本 + 同一 prompt/schema | 共用输出类型，明确 `sourceKind`，不要混称评论痛点 |
| 选题输出 | title/angle/pain/whyFit/titles | 同字段 + whyTrending/titles | 统一 topic schema，热点字段可选；共用保存/渲染 |
| 结构生成 | positioning + style + topic[0] | positioning + viral patterns + topic[0] | 共用结构生成器，以不同 context refs 注入依据 |
| stage UI | `initDiagnosisStages` | `initTrendStages` | 共用 stage component，但 recipe 保持产品固定，不做任意编辑器 |
| stage 写入 | `fillStage` | `fillStage` | 用 run/stage state 驱动，避免编号错位 |
| 选题缓存 | `_lastTopics[activeWorkflow]` | 同左 | 用持久 topic ID 和来源 run 替代数组缓存 |
| 选题渲染 | `buildTopicsHtml` | 同左 | 扩展为显示 `whyTrending`，仍是同一产品组件 |
| 结构渲染 | `buildStructureHtml` | 同左 | 显示 topic/version 关联 |
| demo 渐进延时 | 700/500/700/600 | 相同 | 把 demo 视为固定 fixture run |
| live key/model 校验 | `run()` | `run()` 分支 | 统一调用服务；API Key 不应由内容 workspace 管理 |
| 失败降级 | Phase 1 任一成功可继续 | 同左 | 明确定义 partial success 与缺失依赖告警 |

重复逻辑应抽成产品内部的固定能力（analysis run、stage、topic、structure），而不是暴露成通用工作流编辑器。

## 8. 可靠性与安全问题

### 8.1 高优先级安全问题

1. **浏览器持有并直传长期 API Key。** 任意页面脚本、浏览器扩展、XSS 或共享设备都可能读取它；password input 只遮罩显示，不加密。
2. **页面自动读取 `./key`。** 若部署目录存在该文件，它会成为可公开请求的静态资源，任何访问者都可能下载。源码仓库里即使当前 key 位于其他目录，这个行为也必须在迁移时移除。
3. **启用了 `anthropic-dangerous-direct-browser-access`。** 这是显式允许浏览器直连的高风险原型做法，不应进入迁移后的正式架构。
4. **错误 HTML 注入。** `showErr(m)` 不转义；部分 catch 直接把第三方错误消息写进 `innerHTML`。恶意/异常 API 响应可造成 DOM XSS。
5. **模型字段进入 HTML 属性。** persona `id` 和 `color` 未做白名单/属性转义，被用于 DOM id 和 style；模型输出可破坏 DOM/CSS，结合不安全路径可能注入。
6. **内容数据外发不透明。** 评论、账号资料和热点样本在 live 模式发送给第三方模型；界面只说 Key“不上传”，没有清楚说明内容会发送到 Anthropic。

### 8.2 运行与数据可靠性

1. 热点流程声明五阶段，实际只填四个；标题变体消失，结构占错 stage，第五 stage 永久 loading。
2. 账号选题调用也生成 `titles`，但结果完全丢弃；`buildTitlesHtml` 是死代码。
3. 热点选题的 `whyTrending` 被生成但不渲染。
4. 综合评估不包含 debate，和“基于讨论”的产品文案不一致。
5. demo 忽略用户输入和 `simTopic`，容易让用户误以为展示结果来自刚输入的数据。
6. 初始空状态称样例已预置，但实际上未自动执行 `loadSample()`。
7. 注释称 Phase 1 使用 Haiku，实际所有调用都使用 Sonnet 4.6。
8. `_gen` 只在账号/热点 live 开头增加，只保护部分成功回调；旧请求的错误、后续 topic/structure、simulation 和 demo 仍可能覆盖新运行。
9. 切换 tab、切换模式或再次点击按钮不会取消旧请求；按钮也不禁用，重复提交会竞争同一个 `#out`。
10. simulation 的 reaction/debate 失败被吞掉；对应 loading 可能永久存在；综合评估仍可能基于“获取失败”生成看似正常的结论。
11. persona 校验条件与错误文案不一致，且热点 persona 没使用热点数据本身。
12. persona 数量只由 prompt 要求 3 个，schema 没有 `minItems/maxItems`；模型可返回任意数量。
13. persona ID 可能重复、包含空格或 CSS selector 特殊字符；`getElementById`/DOM id 替换可能错位。
14. 文本 JSON 模式依赖启发式截取与 `fixJsonNewlines`，可能把合法 JSON 修坏，也可能在无 `{`/`[` 时产生难懂错误。
15. 文本模式 schema 只写在 prompt 中，没有结构化输出约束；渲染器虽有部分空数组 fallback，但嵌套对象仍可能形状错误。
16. `titles = d.titles` 未声明，在 strict mode 或模块化迁移后会直接抛错。
17. API 没有 timeout、retry、退避、限流处理、请求 ID、token/成本提示或可恢复状态。
18. API 错误只截前 180 字，且没有按状态码给可行动建议。
19. 所有结果只在 DOM 中；刷新、误点另一流程、开始模拟都会不可逆丢失。

### 8.3 CSV 与分析可信度

1. 手写 CSV parser 只按物理行拆分，不支持引号字段中的换行。
2. 不检测未闭合引号、列数不一致、编码、BOM、空表头或重复表头。
3. 中文表头用连续 `.replace` 做部分映射，字段覆盖有限；例如日期没有规范化。
4. `parseInt` 对 `1.4k`、`1万`、带逗号数字等会误算；排序只用赞+藏，忽略评论，也没有收藏权重。
5. 空或解析失败的 CSV 只要原文本非空仍会继续，可能向模型发送空 `postsStr`。
6. top 50 策略会丢失长尾主题，且没有记录被排除的数据或取样依据。
7. 热点痛点实际上从帖子标题/摘要推断，不是从评论区观测；产品当前可能把“内容供给主题”误称为“读者痛点”。
8. demo 的 `csvText` 是编号预览而不是合法 CSV；如果在 live 模式复用，会得到错误解析结果。
9. 内置热点结果中的 count 可大于内置样本总量，说明 demo 是叙事 fixture，不是可复算证据；迁移后需明确标记。

### 8.4 输出质量与产品一致性

1. 结构总是选择 `topics[0]`，用户不能先选择另一选题再生成结构。
2. `topicChosen` 不渲染，无法直观看出结构属于哪个题目。
3. 账号 profile 的 `voiceFingerprint` 参与下游但不显示，用户无法核对关键依据。
4. 痛点 count 和证据没有对应关系校验，也没有回链到原材料。
5. 没有事实核验、引用、置信度、人工确认或编辑节点；模型推断看起来像确定事实。
6. 对用户输入没有长度、必填、格式或隐私检查；超长评论/CSV 可能导致成本、上下文截断或请求失败。

## 9. 迁移期间必须保留的行为

这里的“保留”指产品价值和用户心智，不要求保留现有 bug。

1. 保留两条明确、产品化的入口：账号诊断与热点分析；不要抽象成任意工作流。
2. 保留账号诊断的核心链路：历史表现与账号定位 → 爆款基因 → 评论痛点 → 账号适配选题 → 第一条/用户选中选题的内容结构。
3. 保留热点分析的核心链路：CSV/TSV 热帖材料 → 互动排序与压缩 → 热点主题/爆款规律/机会窗口 → 痛点 → 同时满足热度和账号适配的选题 → 结构。
4. 保留高表现 vs 低表现对比、具体证据、可执行结论，而不是只给抽象画像。
5. 保留痛点按强度和数量排序，并展示原文证据；迁移后增强为可回链证据。
6. 保留选题的 `title`、`angle`、`pain`、`whyFit`；热点选题还要保留并展示 `whyTrending`。
7. 保留标题变体这一模型产物，并修复当前不显示的问题。
8. 保留内容结构中的分段 outline 和跨选题可复用表达结构。
9. 保留从任一选题一键带入受众模拟的短路径，但用稳定 topic/draft version 关联替代纯文本复制。
10. 保留受众模拟的三层体验：受众原型 → 各自初读反应 → 相互讨论 → 综合评估。
11. 保留 persona 的背景、性格、关注点，以及 reaction 的情绪、debate 的立场、synthesis 的共鸣/争议/建议。
12. 保留三位受众“并行发言、逐步出现”的感受；实现上应有可靠状态和失败提示。
13. 保留 demo 和 live 共用同一套结果组件；demo 应明确标记“固定样例结果”，不能暗示分析了用户输入。
14. 保留工作流切换时各自的材料草稿，不让用户来回切换后丢输入。
15. 保留 CSV 粘贴与本地上传两种方式、载入条数反馈以及 top 50 取样规则；迁移后把规则显式化并可审计。
16. 保留 partial success：并行的两个分析中一个失败时，可基于另一个继续，但必须清楚标注缺失依据和结果降级。
17. 保留“不贩卖焦虑、结合账号风格和已验证模式”的 prompts 约束及产品语气。
18. 保留中文、小红书创作语境与现有信息密度，而不是迁移成通用 AI 对话框。

不应保留：浏览器 API Key、`./key` 自动读取、标题/阶段错位、demo 假装使用当前输入、结果只存在 DOM、无取消的并发覆盖、未转义错误消息。

## 10. 产品专用 workspace 模型

### 10.1 workspace 定义

一个 workspace 对应一个创作者内容经营空间，围绕一个账号/内容定位积累长期材料与产出。它不是文件系统，也不是可编排 Agent 容器。

```text
Creator Workspace
├── Creator Profile（账号定位与风格基线）
├── Materials（创作材料）
│   ├── Historical Posts（历史笔记与表现）
│   ├── Comments（评论原文）
│   └── Trend Datasets（关键词、CSV 数据集、热点帖子）
├── Analyses（分析运行与可追溯结论）
│   ├── Account Diagnosis Runs
│   ├── Pain-point Analyses
│   └── Trend Analysis Runs
├── Topics（选题池与标题变体）
├── Drafts（结构和正文版本）
└── Audience Simulations（针对选题/草稿版本的模拟）
```

workspace 首页应直接回答：目前账号定位是什么、最近导入了什么材料、有哪些最新分析、哪些选题待选择、哪些草稿待完善、哪些模拟建议尚未处理。

### 10.2 核心实体

#### `CreatorWorkspace`

```text
id
name
platform = "xiaohongshu"
currentProfileVersionId
createdAt / updatedAt
```

单用户本地/单空间实现即可；不引入认证或多租户概念。

#### `CreatorProfileVersion`

```text
id, workspaceId, version
positioningText
audienceDescription
contentPromise
creatorAdvantages
contentGoals
createdAt
```

保留原始自由文本，同时允许把常用维度结构化；分析 run 必须引用一个确定版本。

#### `MaterialCollection`

材料集合用于表达“这次分析用了哪些材料”，不是任意文件目录。

```text
id, workspaceId
name
kind = historical_posts | comments | trend_dataset
sourceLabel
collectedAt
createdAt
```

其子实体：

- `HistoricalPost`：`title, contentSnippet, likes, collects, commentsCount, performanceLabel, publishedAt, tags`。
- `AudienceComment`：`text, historicalPostId?, collectedAt`。
- `TrendDataset`：`keyword, originalFilename?, rowCount, parsedAt, fieldMapping, sampleRule`。
- `TrendPost`：`trendDatasetId, title, likes, collects, commentsCount, tags, contentSnippet, publishedAt, sourceRow`。

原始上传内容可以作为受控 source blob 关联到 dataset，但不向用户暴露任意路径或任意文件操作。

#### `AnalysisRun`

```text
id, workspaceId
type = account_diagnosis | trend_analysis
status = queued | running | partial | succeeded | failed | cancelled
profileVersionId
materialCollectionIds[]
keyword?
model
promptVersion
startedAt / completedAt
stageStatuses[]
```

固定两种产品 run 类型。每个 stage 保存输入引用、结构化输出、错误和状态；不允许用户自由拼装 stage。

#### `AccountDiagnosisSnapshot`

```text
analysisRunId
pillars[]
titleFormulas[]
hookStyles[]
viralStructure
voiceFingerprint[]
contrast
```

#### `TrendAnalysisSnapshot`

```text
analysisRunId
themes[]
viralPatterns[]
opportunityWindows[]
rankingRule
selectedTrendPostIds[]
```

#### `PainPointCluster`

```text
id, analysisRunId
theme
intensity
count
sourceKind = audience_comment | trend_post
evidenceRefs[]
rank
```

`evidenceRefs` 指向真实材料 ID；同时可保存模型引用的 excerpt，保证材料后续更新时仍能复现当时证据。

#### `Topic`

```text
id, workspaceId
sourceAnalysisRunId
title
angle
painPointClusterId?
whyFit
whyTrending?
status = proposed | shortlisted | developing | archived
createdAt / updatedAt
```

#### `TitleVariant`

```text
id, topicId
text
rank?
sourceAnalysisRunId
```

#### `Draft`

```text
id, workspaceId, topicId
status = outline | drafting | ready_for_simulation | revised | published
currentVersionId
```

#### `DraftVersion`

```text
id, draftId, version
selectedTitle
topicSnapshot
outline[{section, content}]
reusableStructure
body?
createdAt
```

当前原型的 `structure` 首先落成一个 outline 版本；后续正文仍属于同一 Draft，不需要新建通用文档系统。

#### `AudienceSimulationRun`

```text
id, workspaceId
targetType = topic | draft_version
targetId
targetSnapshot
contextAnalysisRunIds[]
status
model / promptVersion
startedAt / completedAt
```

子实体：

- `SimulationPersonaSnapshot`：`id, runId, archetype, background, personality, concerns, color`。
- `SimulationReaction`：`personaSnapshotId, text, sentiment, status`。
- `SimulationDebateTurn`：`personaSnapshotId, targetPersonaSnapshotIds[], text, stance, sequence, status`。
- `SimulationSynthesis`：`topResonance, controversyPoints[], suggestions[]`。

综合评估必须引用完整 reactions 和 debate turns；target snapshot 确保后续改稿不会让旧模拟失去语义。

### 10.3 关键关系与产品流转

```text
CreatorProfileVersion + Materials
          │
          ├── AccountDiagnosisRun ── profile + pain points ──┐
          │                                                  │
          └── TrendAnalysisRun ── trends + pain points ──────┤
                                                             ▼
                                                        Topic Pool
                                                             │
                                                  title variants / shortlist
                                                             ▼
                                                      Draft + Versions
                                                             │
                                                             ▼
                                                 AudienceSimulationRun
                                                             │
                                             reactions + debate + synthesis
                                                             │
                                                             ▼
                                                   revised DraftVersion
```

推荐的固定产品操作：

1. 导入/整理创作者材料。
2. 运行账号诊断或热点分析。
3. 查看证据，收藏/淘汰选题，比较标题变体。
4. 为明确选题生成结构并形成 Draft。
5. 对某个 DraftVersion 运行受众模拟。
6. 把优化建议逐条标为“采纳/忽略”，生成新 DraftVersion。

### 10.4 运行状态与版本原则

- 输入按引用 + snapshot 保存：既知道来源材料，也能复现当时模型实际看到的内容。
- 每次生成创建新 run，不覆盖旧分析。
- Topic、Draft、Simulation 通过稳定 ID 关联，不使用数组下标或文本相等判断。
- 账号定位、结构和草稿都版本化；模拟永远绑定具体版本。
- partial run 可产生选题，但 UI 必须展示缺失了 profile、pain points 或 trend analysis 中的哪一项。
- demo 作为只读 fixture workspace/run 提供，明确标记固定样例；live run 使用同一实体和渲染组件。
- workspace 只管理创作者业务对象；不提供任意目录浏览、任意文件写入、通用节点编排或扩展市场。

### 10.5 建议的 workspace 主要视图

1. **概览**：账号定位摘要、材料新鲜度、最近分析、待推进选题、草稿和模拟提醒。
2. **材料库**：历史笔记、评论、热点数据集；支持查看解析状态和证据回链。
3. **分析**：账号诊断与热点分析的运行历史、阶段状态、输入快照和对比结果。
4. **选题池**：按痛点、来源分析、状态筛选；展示 whyFit/whyTrending、标题变体和来源证据。
5. **草稿**：选题结构、正文和版本；从选题进入，不做通用文件编辑器。
6. **受众模拟**：选择 Topic 或 DraftVersion，查看 personas、reactions、debate、synthesis，并把建议回写为修订任务。

这六个视图覆盖当前原型的全部价值链，同时为持久化、可追溯、版本化和可靠运行留出空间，且始终限定在创作者内容工作场景内。

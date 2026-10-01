# 当前状态与 TODO

## 2026-10-01：账号画像更面向创作者

账号诊断新增账号关键词、具体优势和鼓励语，并把这些放在结果页前面；模型提示强调先看到创作者已有的价值，不写成审稿意见。笔记表现的数据口径改为可展开说明，条件不足的前后变化不再占一整块提醒。新字段可选，老分析历史继续显示原结果；每条新结论仍能打开对应笔记。后端全套测试及 lint、前端 133 项测试及 lint/build 通过。下一步要用真实账号结果检查“夸得具体、有辨识度、不像模板文案”，并由用户判断语气是否合适；本次未重新诊断或覆盖现有历史。

## 2026-10-01：同一关注点的多种人物声音

模拟粉丝可从一位已保存粉丝派生 12 种内置声音：行动派、共鸣派、查证派、质疑派、沉默收藏者等。粉丝资产页可勾选后批量加入，角色继承原关注点和依据，但拥有不同的判断方式、表达语气及参与倾向，并继续允许显式编辑。重复选择同一来源和模板复用原角色，不覆盖用户改动；源资产和旧历史不变。模拟提示词开始明确使用这些人物差异，避免把每位都写成相同的内容策划。更多角色的独立反应和讨论请求采用四路并发，不设人数上限也不瞬间发出所有调用。此扩充是确定性的 demo 角色设定，不是新的受众分析模型调用；真实模型的人物适配仍是下一阶段。后端全套测试及相关 lint、前端 132 项测试及 lint/build、`git diff --check` 均通过；未调用真实模型、抓取或提交。

## 2026-10-01：受众模拟改为可扩展选择槽

公开模拟默认显示三个下拉槽位，可按需点「＋ 新增」继续选择当前账号的未归档模拟粉丝；额外槽位可移除，空槽位不参与执行，同一粉丝不能重复选择。后端创建请求及粉丝快照不再限制三位，四位粉丝按选择顺序完成运行的集成测试通过。自动从受众分析保存前三位仍只是初始资产数量，不是模拟人数上限；其他视角可从分析结果继续保存。旧历史快照不改。后端完整测试与相关 lint、前端 131 项测试与 lint/build 均通过。下文旧记录提到的“每次最多三位”仅是当时实现，已由本节取代。本轮未抓取、调用真实模型或提交。

## 2026-10-01：主页抓取的本机 CDP 连接诊断

以下按发生顺序记录；本节最后一段是当前结论，前面“尚未复测”等表述只描述当时的状态。

用户授权独立 MediaCrawler 限量实测（每次最多 1 条、不抓评论、不自动重试）。首次与后端此前两次任务一样，在读取创作者笔记前失败：Chrome 已启动，但本机 CDP `/json/version` 经 `httpx` 返回 502；备用浏览器打开小红书首页又在 30 秒后超时，未产生笔记或评论。这个结果不支持把故障归因于主应用简化了抓取逻辑。随后仅用临时 Chrome 空白页做本机诊断：直连本地调试端口返回 200，`httpx` 默认代理路径返回 502，`trust_env=False` 返回 200。已将 CDP 本地发现请求改为不继承系统或环境代理，写入可复用的 MediaCrawler 补丁；独立调用该方法的本机测试及补丁反向检查通过。用户再次授权后同样限量复测一次：**CDP 已成功连接，不再出现 502；但独立 Chrome 的小红书首页仍在 30 秒后加载超时**，仍未读取笔记或评论。另用临时 Chrome 档案打开公开测试页 `example.com` 也在 20 秒内未完成，普通命令行 HTTP 请求则得到 200；这提示独立浏览器的网络路径整体有问题，但不能由此断言小红书站点的具体失败原因。下一步应确认普通 Chrome 与抓取专用档案的代理/扩展差异，不能继续盲目重试抓取。

用户调整代理后又授权一次限量实测。Playwright 临时 Chrome 对普通测试页取得 200（此前 Chrome `--dump-dom` 仍超时，因此不能把该命令当作可靠的联网判断）。独立 MediaCrawler 这次成功打开小红书首页并由用户扫码登录，进入 `get_creators_and_notes`；随后主页 HTML 的 `window.__INITIAL_STATE__` 在 JSON 解码时失败，日志为 `Expecting value`，没有生成笔记或评论。实际 URL 已成功解析。随后已修复上游适配补丁：区分主页状态解析失败与 URL 错误，安全地归一化裸 `undefined`，避免在日志中回显分享 token，并在没有处理成功的主页时以非零状态退出。独立框架 7 项相关离线测试、后端 9 项抓取任务测试及补丁反向检查通过；**尚未对真实小红书页面复测**，不能把这次运行称为抓取成功。后续如经用户同意，再做一次限量验证；若仍失败，优先采集脱敏的状态格式诊断，不自动重试。

用户随后允许一次同边界实测：独立框架设置最多 1 条笔记、不抓评论或媒体、无自动重试，并将输出隔离到临时目录。本次进程在浏览器启动阶段即失败：CDP 无可用调试端口，备用 Playwright Chromium 因系统权限错误退出；未请求目标主页，临时目录没有产物。因此**没有验证到主页解析修复**，也不能把这次失败归因于小红书或目标账号。按约定没有再次启动抓取；若要验证真实页面，需要先在允许本地浏览器启动的执行环境中排查权限，再取得新的一次性实测授权。

用户再次授权后，在允许启动本地浏览器的环境中按同一边界运行一次：CDP 正常连接、现有登录态有效，目标主页请求成功进入解析，但 `window.__INITIAL_STATE__` 仍在位置 62376 报 JSON 错误；修复后的独立框架明确以非零状态退出，隔离输出目录为空，实际读取 0 条笔记、0 条评论。对比上次，误报 URL 错误和退出码 0 的问题已修复，真实页面的序列化差异尚未解决。后端现可将该错误显示为专门的“主页数据格式暂无法解析”，不回显分享 token；抓取任务测试 10 项通过。按一次性授权边界没有重试或另行请求站点。后续需取得脱敏的错误位置上下文或页面状态结构证据，不能仅凭位置盲目放宽解析器。

用户进一步授权持续排查。已从 GitHub 拉取 MediaCrawler 最新 `origin/main`（2026-09-19 的 `380b426`）供比较；它没有修改小红书 `extract_creator_info_from_html`，故不直接覆盖当前有本地补丁的固定版本。一次受控诊断把失败页面临时留在本机，离线确认错误位置是 JavaScript 的空 `new Set([])`，并非合法 JSON；只将这一明确写法转换为空列表后，真实主页能解析出创作者对象。该保守转换已写入可复用补丁，合成样例和真实页面离线回归通过。限量在线复测：主页解析成功，笔记列表返回；首次单条详情未落盘，不能算成功。再做单条诊断发现主页笔记列表没有 `xsec_source`，旧代码将空值传到详情请求；已在创作者主页路径填入 `pc_user`，保存链接也沿用实际来源。此后直接框架读取到一条完整正文（981 字符）。主应用实际调用的导入脚本在隔离目录读取 1 条笔记、1 张封面及创作者名称/互动计数，未抓评论；离线导出包包含 1 条笔记和 1 张封面，在临时 SQLite 工作区通过真实 FastAPI 导入接口（201），正文与封面关系均保存。正式数据库未写入，也未做更多笔记或评论的验收；平台返回、登录状态及未来页面格式仍可能变化。

最终检查：MediaCrawler 相关测试 10 项、后端完整测试 279 项与后端 lint 通过，补丁反向检查通过；前端未改。诊断时保存的原始主页与此次所有临时抓取/导入产物已清理，没有把真实页面、Cookie 或 token 加入 Git。此结果证明当前固定版本加本地补丁在这一账号的单条链路可用，不等于任意账号、更多笔记或评论抓取都已验证。

## 2026-10-01：用户发起的多篇读取与去重

用户从运行中的前端先读取最近 10 条，再自行选择读取全部；后端只观察任务，没有代用户发起抓取。10 条任务成功，资产内 10 个不同笔记 ID、55 条评论和 10 张封面。全部任务约 17 分钟后完成，原始文件有 94 行笔记、622 行评论，其中两个笔记 ID 各重复一次，19 个评论 ID 各重复一次。旧导出器没有去重，最初写入 94 条笔记和 662 条评论；重复笔记又放大了其下评论数。前 10 条笔记均包含在全部结果里。

现在 MediaCrawler 导出器按笔记 ID、同一笔记下的评论 ID 保留首次记录；无稳定评论 ID 的记录不猜测合并。新增回归测试覆盖重复行与跨笔记同名评论 ID。对本次资产先只读预演，再用 SQLite 在线备份并仅修复该资产的完全相同重复项；内容不同的同 ID 条目会拒绝自动修复。最终为 **92 条唯一笔记、603 条唯一评论、92 张不同封面**，正文与发布时间均非空，历史分析快照没有被改写。备份在被 Git 忽略的 `data/backups/`。后端全套测试及 lint 通过，前端当时未改；没有再次抓取。当时页面仅显示笼统的“正在读取笔记和评论”；全部加评论耗时较长且存在 20 分钟上限，不能把这次成功外推到其他账号。

进度展示随后补齐：抓取任务保存独立的结构化进度快照，后端从实际落盘的笔记／评论 JSONL 去重计数，并从框架现有日志读取逐个评论任务的完成数。前端轮询同一任务，刷新后可恢复计数；读取笔记、登录和整理阶段因总工作量未知使用不标百分比的动态进度条，评论阶段只有识别出实际任务总数时才显示该阶段的比例。重复笔记可能在框架内部产生重复读取任务，因此界面称“评论读取任务”，不误称唯一笔记数。旧任务的进度字段默认空值，不补造历史计数。此进度代表抓取过程，不代表评论覆盖率或剩余时间预测。后端全套测试、前端 128 项测试、前端构建与相关 lint 通过；未因验证再次请求小红书。全仓 `scripts/` lint 仍有与本轮无关的既有格式错误，相关改动文件及 `backend/app`、`backend/tests` 检查通过。

## 2026-10-01：内置阅读需求原型目录（未接入运行）

新增 12 项固定、可组合的阅读任务参考目录，每项只有稳定 ID、名称、任务描述和匹配问题。它们不是已发现的粉丝类型，不带身份、阶层、MBTI 或比例，也不设默认语气。当前目录尚未传给模型、前端或模拟运行；旧分析、粉丝和历史模拟不变。后续顺序是用本次笔记正文与评论做有引用的少量候选匹配，允许多项或零匹配，再做一次定向适配并经用户确认后保存模拟粉丝。详见 [画像设计稿](simulated-fan-model-design.md)。后端完整测试 271 项通过，相关 lint 与 diff 检查通过。本轮不抓取、不调用模型、不修改正式数据。

随后补充了**未接入运行的离线候选校验**：允许零至三个不重复的原型，每个候选需给出本次分析输入中的逐字引用、匹配理由和不确定性；反证引用如提供也需核验。未知 ID、重复、无引用、无效引用和额外人格字段被拒绝；输出统一标记为待确认，不能直接保存成粉丝。逐字核验仍不能证明匹配理由成立，模型匹配、一次适配、人工确认及模拟接入均未完成。后端完整测试 278 项、相关 lint 通过；未调用模型、抓取或修改数据库。

本轮补齐了阅读需求匹配的确定性输入包：仅包含本次分析范围、已选笔记正文及其评论、采样说明和固定目录；不把作者资料、图片或工作区其他资产混入候选匹配。候选引用对同一输入包校验，超出实际发送截取长度的原文不被接受。尚未将目录送入受众分析模型、保存候选或改变模拟。后端完整测试 281 项、相关 lint 通过；未调用模型、抓取或修改数据库。

再补充候选的来源边界：后端只按支持性引用派生 `note_only`、`comment_only`、`mixed`，反证不抬高支持来源，模型也不能自行宣称“评论证实”。这不是语义核验，候选仍是待确认提议；旧分析、粉丝和模拟不变。后端完整测试 283 项、相关 lint 通过；未调用模型、抓取或修改数据库。

本轮再收紧离线候选证据：同一候选不能重复使用完全相同的引文，也不能把它同时列为支持和反证；同一笔记中的不同片段仍可引用。此校验尚未接入模型匹配和前端确认流程，不改变既有运行或资产；逐字不同仍不代表语义上没有冲突。

## 2026-10-01：受众画像纳入笔记内容线索

受众分析继续只使用已选笔记的标题、正文和已采集评论，不调用图片理解。提示词先识别笔记可能服务的阅读任务，再与评论中实际表达的需求和异议交叉；允许没有评论佐证的潜在阅读视角，但不能称其为真实粉丝。后端依据已核验引用确定每组来源为评论表达、笔记内容推断或两者兼有。纯笔记推断的汇总与模拟粉丝证据状态明确保留“假设”边界，排序不再只以评论数量为先。旧结果兼容；图文内容在此指标题和正文，不含图片像素。

真实 `_tt` 样本检查：四条笔记、26 条已采集评论经 Qwen `qwen-plus` 返回 6 个分组；3 个通过原文核验（含 1 个纯笔记内容推断），3 个因引文不精确被拒。通过核验的文案仍出现身份／决策阶段过度推断，因此又收紧分组命名和 profile 提示，并强化页面边界文案。真实模型输出没有写入数据库；复测结果见下段。补充的集成测试覆盖无评论、仅笔记证据、持久化重开、模拟粉丝保留假设状态、模拟快照及不传图片字段。

提示收紧后同一 `_tt` 输入复测：6 组里 4 组引用通过、2 组失败；有纯笔记与笔记加评论的视角，但仍有将提问过度推为身份或决策阶段的句子。因而新生成的所有受众组转模拟粉丝时均标为假设，附加“原文存在不等于解释成立”的限制。旧保存结果不回写；真实模型效果仍需人工审阅。两次检查均绕过当前环境中失效的代理直连 Qwen，没有修改产品的模型连接默认值。

## 2026-10-01：账号诊断引用强度加固

新版账号画像中的“主要内容方向”现在至少需要两条不同的已选笔记作为依据；同一篇的多段原文不再伪装成反复出现。模型提示和后端核验一致，旧版结果仍可在分析历史中打开。结果页对早期新版运行也采用同一展示边界，并在笔记表现处显示发布日期及样本内点赞名次，提示累计互动不可直接解释为质量或趋势。下一步仍需人工审阅引用与结论是否真的匹配；字面校验不能替代语义核验。

## 2026-09-30：账号诊断首轮证据化

公开账号诊断开始以“认识账号”为主：新运行保存本次所选笔记的覆盖数、发布时间和互动数缺失情况，以及逐条原始指标；模型输出可附带引用 `noteId` 与原文短句的账号画像，服务端只展示身份与字面匹配的引用。结果页能从画像依据打开原笔记；按所选样本展示点赞数观察，不称为点击率或内容质量。画像可附带其他笔记构成的可能例外；笔记日期足够时，后端确定性分出前后时期，模型仅比较内容方向，并必须引用两组原文。条件不足则说明原因，不生成趋势。旧版模型归纳折叠保留，历史运行可继续打开；选题生成仍存在，界面标为“下一步 · 选题建议”。完整设计和剩余边界见 [账号诊断设计稿](account-diagnosis-design.md)。

本轮后端 264 项测试通过，前端 25 个文件、125 项测试通过；两端 lint、前端 build、`git diff --check` 通过。另用 `_tt` 四条和 QSheep 二十条笔记分别做真实 Qwen 结构冒烟测试。二十条样本返回可回溯画像与一条可能的例外，未返回通过核验的前后变化；程序没有补造它。尚未人工审阅引用是否真正支持结论，也未实现逐条语义标注及选题与画像的证据关联。未改正式数据库、未部署或提交。

## 2026-09-30：近期增量健壮性自查

本轮聚焦笔记选择、受众分析和模拟粉丝，没有扩大产品功能。修复受众历史和粉丝列表的响应乱序：手动刷新与轮询交错、账号 A→B→A 切换时，迟到结果或旧错误不能覆盖新状态；组件卸载后使旧请求失效。模拟粉丝选择额外拒绝不存在或已归档的 ID。受众历史请求失败现在有明确提示，已有结果保留，不再像空历史。

受众分组与粉丝资产共用名称、画像等字段长度和非空校验，过长或空白内容在分组核验阶段被拒绝，不再到自动保存粉丝时导致全部有效结果丢失。引用核验新增重复来源检查：笔记 ID 或同一笔记下评论 ID 重复时，拒绝该引用，避免“引用匹配第二条记录、历史案例却取第一条记录”的对应错误；不猜测、不自动合并来源，也不放宽原文标准。

新增 10 项回归测试。完整检查：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 256 项通过；`npm --prefix frontend run test -- --run` 25 个文件、123 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts`、`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 均通过。仍有既有 LangChain 弃用和 Node localstorage 参数提示。本轮未操作正式数据库、未调用外部模型、未部署或提交；这些检查不代替真实模型质量与人工交互验收。

## 2026-09-29：账号诊断逐条选择笔记

“调整范围”复用“我的笔记”的卡片和正文／评论详情，保留最近 10 条、日期范围和全部笔记快捷选择，并支持逐条勾选、全选、清空。弹窗内部先暂存选择，“完成”应用，“取消”或关闭不改变原范围；零选中不能确认。切换账号清空手动选择，选择绑定档案 ID，不串入其他账号。

分析创建接口新增可选 `selectedNoteIds`，只支持创作者档案的账号诊断。后端校验空值、重复、缺失和歧义 ID，按实际选中笔记派生正文、评论及上下文，并移除全量总结；快照中的 `analysisRange.scope=custom` 保存确切 ID 和数量。旧范围参数与调用保持兼容，无数据库迁移、不改提示词。手动选择属于本次页面状态，刷新后仍回到默认范围，已运行的选择则永久保存在分析快照。

验证：后端 251 项、前端 24 个文件 118 项测试通过；两端 lint、前端 build、diff 检查通过。浏览器使用隔离数据库验证 20 张笔记卡片、两条自选后的计数、正文与评论详情；未调用模型或写入正式运行。临时预览服务检查后关闭。

## 2026-09-29：预存 QSheep 模拟粉丝

按用户要求，为 QSheep 账号预存申请规划、工具实用、经历共鸣、细节求证和课程讨论五类角色。每类关联两条现有评论，引用由程序从对应 ID 提取并重新核验，不重新抓取或调用外部模型。正式库此前只有失败的受众分析，因此此次明确标注为“预置整理”，不声称复用了成功的模型分析，也不引入 Demo 模型回复。

整理记录沿用受众分析的来源关系，`result.origin=curated_preset`，模型元数据记录 `modelCalled=false`；角色保持 `evidenceStatus=hypothesis`，真实引文不等于人物画像得到证明。页面区分预置与模型分析；五个资产可编辑/归档，每次模拟仍选 1–3 个。仅写入 QSheep 账号，旧失败、其他账号和已有编辑保持不变。

可重复运行 `backend/.venv/bin/python scripts/seed_qsheep_audience_presets.py --source-id 18892280-ceba-444b-b2e8-52b57aa17996`。脚本要求本账号拥有全部指定评论，缺失即停止；先备份 SQLite，再执行迁移与事务保存。相同档案/预置版本复用原分析和角色，不自动恢复归档或覆盖编辑。本次已备份正式库并应用 `0030` 迁移，下方“未迁移”是此前调试阶段记录。

本轮验证：后端完整测试 244 项、前端 23 个文件 115 项通过；两端 lint、前端 build、`git diff --check` 通过。数据库只读复核五个角色各有两条引用，来源均为 `curated_preset`、证据状态为 `hypothesis`，原失败记录未改。正式库与备份均被 Git 忽略；未启动服务、未发起模拟或付费调用。

## 2026-09-29：受众分析引用失败诊断

针对正式库一次“受众证据引用与本次输入不符”的失败，新增模型结构化原始输出和核验诊断持久化：区分来源 ID 不匹配、引文不是连续原文、缺少引用、分组格式和重复 ID。模型输出先落库再校验，原始响应不在列表接口返回；页面可展开查看被拒绝的分组及引用序号。旧失败记录没有保存原始响应，无法追溯其具体错误，不回写或伪造诊断。

引用标准不放宽。有错误引用的整个分组被排除，独立有效的分组保存为 `partially_completed`；全部无效才失败。部分完成的有效视角可以成为模拟粉丝并用于模拟，未经核验的分组不能流入下游。部分结果用中性计数摘要替换模型总体摘要，避免保留已被排除分组的概括。新增本地迁移 `0030_audience_diagnostics.sql`，不修改历史分析或已有粉丝编辑。

真实复测涉及将保存的笔记、评论发往阿里云 Qwen，权限检查要求用户明确确认；当前未发起调用，计划确认后仅做一次隔离数据库复测，不重新抓取、不覆盖原失败记录。正式数据库未执行本轮迁移，未重启服务、未提交。

本轮检查：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 241 项通过；`npm --prefix frontend run test -- --run` 23 个文件、114 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts`、`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 均通过。仍有既有 LangChain 弃用和 Node localstorage 参数提示。

## 2026-09-28：模拟粉丝资产

新增独立 `SimulatedFan` 内容资产和左栏入口。账号尚无粉丝档案时，新完成的受众分析自动保存最多前三个视角；已有分析不自动回填，可逐项“保存为模拟粉丝”。同一分析/视角重复保存复用原记录，后续分析不覆盖已有编辑，其他视角可按需新增。名称、阅读视角、关注点、内容偏好和表达习惯可显式编辑，并支持归档/恢复及保存冲突提示。

公开版模拟改为选取当前账号 1–3 位未归档粉丝；默认选择前三位。每次运行冻结所选档案、原始依据、来源分析和更新时间，后续编辑不改历史。人工调整会标为假设，不被称为已核验画像；模拟反应不回灌真实评论证据。旧 audienceAnalysisId API 和历史运行保持兼容；不增加 Agent 配置、团队、版本表或跨账号复用。

本轮检查：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 232 项通过；`npm --prefix frontend run test -- --run` 23 个文件、113 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts`、`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。模拟链路用注入模型响应测试，无新增真实模型调用。已按用户要求启动本地前后端，并在迁移前备份数据库。

下一步是用户验收档案编辑与选择体验，再做少量真实模型检查。档案的独立持久化不会自动解决受众身份过度推断或评论照抄问题，相关质量 TODO 仍保留。

## 2026-09-27：创作事实边界

选题与 AI 创作已将未经证实的个人经历改为独立的“待确认建议”：新选题使用中性角度，待确认素材进入生成快照，选题卡、详情及画布可见；对话中的建议保存在消息元数据，不会自动并入正文。账号全局背景仍然保留，但模型分析、旧选题角度和旧 AI 回复不作为事实来源。新增个人事实需提供原文引用，来源限于关联分析的历史笔记快照和用户陈述。

创作更新增加结构化核验：缺少核验字段、明确不安全、引用 ID/原文不符，或整条待确认建议混入正文时，不改原稿，保留建议和错误信息。旧记录仍可读，无新表、不回写历史。该机制不能检测模型遗漏申报的事实，也不能证明引用在语义上支持结论；仍需真实模型复验，不能称为消除幻觉。

本轮检查：后端 229 项、前端 108 项测试通过，两端 lint、前端 build 及 diff 检查通过。未调用真实付费模型、未修改正式数据库、未部署。本轮处理的是下方验收记录的第一项风险；下一步先少量真实 Qwen 复验，再处理受众身份过度推断与模拟评论照抄正文。

## 2026-09-27：真实 Qwen 与公开页面验收

在独立测试库完成账号诊断、选题保存、两轮 AI 创作、受众分析和受众模拟，验证运行中刷新及账号切换隔离，没有写入正式数据或重新抓取。修复历史卡来源丢失、选题选择后的旧版本冲突、改名后重复保存、创作画布更新竞态和模拟历史列表状态滞后。最终后端 220 项、前端 106 项测试通过，两端 lint、前端 build 通过；过程、命令和边界见 [链路验收记录](creator-journey-acceptance.md)。

下一步优先级：先约束选题及创作的事实边界，再处理受众身份过度推断与评论照抄正文，之后改善引用失败诊断。此次真实接口通过不等于内容质量通过，也不证明模拟准确率；不扩建数据集或效果实验。受众分析第一次引用错误被校验拒绝，有限重试成功，该可靠性限制仍保留。真实扫码抓取仍待人工验收。

## 2026-09-26：文献技巧轻量落地

受众分析和独立反应已加入少量人工编写的教学示例，新增未知属性；真实历史案例由代码从核验过的引用组织为笔记—评论配对，不采信模型编造的案例。每组最多六条，模拟角色按内容相关性及跨笔记覆盖选最多四条。旧分析可从自身快照为新模拟补案例，不改写原始结果。

交流接入自己的第一反应、可见公开消息和回复目标；第一轮未评论者可以在看到一条公开评论后加入。回复目标和改变观点说明有结构校验，成功结果与角色级失败分别保留；历史/SSE 兼容新旧跳过规则。没有重写图、增加数据库表或改变主要界面。具体来源与落地边界见 [方法文档](audience-simulation-methods.md)。

本阶段不建设数据集，不开展效果对照；普通工程测试与注入响应的链路测试不能证明模拟准确率提升。后续以实际使用反馈微调即可，逐评论独立编码、复杂受众排序和更多交流轮次不作为当前必做项。

本轮验证：`cd backend && .venv/bin/python -m pytest -q -o addopts=''`：220 项通过；`npm --prefix frontend run test -- --run`：20 个文件、101 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts`、`npm --prefix frontend run lint`、`npm --prefix frontend run build` 和 `git diff --check` 通过。仍有既有 LangChain 弃用和本机 Node localstorage 参数提示。未调用真实付费模型、未重新抓取数据或部署服务。

## 2026-09-25：受众模拟证据化

新受众分析改为可重叠的阅读视角，不再要求模型编造合计 100% 的受众比例。来源 ID 和原文引用会在本次模型输入中核验，并继续传入模拟；历史结果保持只读兼容。读者不再收到“为什么适合该选题”等创作策略，可以划走或不评论；第二轮只看到公开模拟评论，不足两条则跳过。总结定位为发布前预演，不承诺真实流量预测。

新增离线时序回测案例准备脚本及引用、防答案泄漏、沉默、重开和部分失败测试。实验设计、使用方式和待验证假设见 [受众模拟研究](audience-simulation-research.md)。真实模型对照尚未执行；角色数量、证据排序、交流轮次的增益仍待验证。本条替代下方旧记录中的“分群必须合计 100%”“按主观比例 Top 3 作为模拟依据”等描述。

后续方法研究已整理为 [few-shot 与评论互动设计](audience-simulation-methods.md)，以 Proxona 等原始文献为依据。产品方已明确采用文献借鉴路线，不将数据集、人工标注或对照实验作为前置条件。当时计划的轻量技巧已于 09-26 落地，见上方增量；没有效果提升结论，研究脚本不继续扩建。

本轮检查：后端 206 项、前端 98 项测试通过；两端 lint、前端 build 和 diff 检查通过。未执行付费模型调用或真实抓取，也未重新部署服务。

## 2026-09-23：第二轮体验迭代

已完成四组父子导航、左栏收窄、添加账号延迟创建和重复提交复用、粉丝/获赞指标适配、选题正文与置顶、独立受众分析及 Top 3 模拟来源、持久化对话式 AI 创作画布。6 个误创建的空档案已备份后清理；包含历史数据的档案保留。实现细节见 `creator-experience-iteration.md`。

待人工验收：真实抓取的账号统计字段、基于真实模型的受众分群质量、多轮创作体验。页面更新不会为旧离线包补造粉丝数，不自动发起抓取或付费模型调用。

当前检查结果：后端 183 项测试、前端 93 项测试通过；两端代码检查、前端构建通过。完整命令及页面检查记录见本轮执行文档。

## 2026-09-23：首轮创作者聚焦版 V2（以下为首轮记录）

当前正在把产品从开发者工作台收口为面向创作者的公开界面。已完成执行手册、单一左栏公开产品壳、账号档案选择/新建、默认用户到账号空间的数据库所有权关系，以及主页 URL 导入任务的前后端骨架与真实 MediaCrawler runner。公开入口只保留账号材料、账号诊断、分析历史、选题库、AI 创作和受众模拟；旧热点分析、视频质量诊断、Skills、Agents、Workflows 和多模态实验仍可通过 `?internal=1` 回归，不删除代码。

公开页面已增加账号概览、按笔记组织的封面卡片和正文/评论弹窗。导入默认 10 条，可调整为 20/50/100 条或全部可见笔记；诊断默认最近 10 条，可改为最近 7/30/90 天或全部已导入内容。范围由后端实际筛选并写入运行快照；日期缺失不纳入日期筛选。公开模式使用真实模型，选题新建和范围设置按需弹窗，创作输出使用文本字段编辑。旧 JSON/文件夹导入仍在内部工作台。

剩余验收：用本机真实浏览器完成一次主页 URL 导入（含扫码），验证平台返回数据、封面和完整创作链路。自动化测试覆盖任务持久化、重复提交、重启中断、导入包、范围筛选和笔记交互，不代表已经完成真实平台抓取。远程用户在网页内扫码、旧混合账号 Workspace 的自动拆分暂未实现；历史空间不自动搬迁，新增账号使用独立空间。

本轮验证：后端 174 项测试、前端 88 项测试、两端 lint、前端 build 和 diff 检查通过。浏览器使用临时数据库加载 `_tt` 离线包，确认 4 条笔记、4 张封面及正文/评论弹窗正常；完整命令见 V2 执行手册。只读检查当前 4 个历史 Workspace，未发现单个空间混有多个小红书昵称。

以下为上一版内部工作台基线（更新日期：2026-08-26），功能存在不代表有公开入口。

本文档只记录当前实现状态、明确限制和 TODO。产品设计思想和功能全貌见 `docs/product-design.md`；更细的 PRD 和验收标准见 `docs/product-requirements.md`。

## API 路径与 VPS 分享结论

前端业务请求已经使用相对路径：

```text
/api/...
```

也就是说，前端代码不会直接请求 `localhost:8000`。本地开发时，`frontend/vite.config.ts` 只把开发服务器里的 `/api` 代理到 `http://127.0.0.1:8000`。

如果要通过 VPS 分享给别人看，需要保证浏览器访问的同一个域名可以同时提供：

- 前端页面；
- `/api/...` 后端接口。

推荐部署形态：

```text
https://your-domain/
  -> 前端静态页面

https://your-domain/api/...
  -> FastAPI 后端
```

可以用 Nginx/Caddy 做反向代理，也可以后续让 FastAPI 直接挂载构建后的前端静态文件。当前仓库还没有加入部署基础设施。

## 已完成的主要实现

### 产品结构

- 已从单文件 HTML 原型迁移到 React + TypeScript + FastAPI + SQLite。
- 原始 `index.html` 保留为行为参考。
- 工作区目前前端隐藏创建/切换入口，自动使用默认 workspace。
- 左侧是内容资产；右侧是能力资产和 workflow 调用。
- 右侧 workflow 调用入口已经由 workflow asset 的 `callBinding` 生成，内置账号诊断、热点分析、视频博主质量诊断默认注册；新生成或手动修改的 workflow 可注册为额外入口，但仍绑定到已有产品执行类型。

### 内容资产

当前内容资产包括：

- 创作者档案；
  - 小红书主页；
  - 账号概况；
  - 历史笔记；
  - 评论样本；
  - 视频创作样本；
- 趋势数据；
- 图文素材；
- 视频素材；
- 分析结果；
- 选题库；
- 创作输出；
- 受众模拟。
- 对话记录。

已实现：

- 资产实例列表；
- 资产详情编辑；
- 创作者档案组合概览，聚合用户显式打开的小红书主页、账号概况、历史笔记、评论样本和视频创作样本；
- 内容资产管理页进入后先显示空态，不自动打开 workflow 当前默认选择的 QSheep 或其它示例实例；
- 显式保存；
- workflow 运行前自动保存必要输入；
- Agent conversation / Maker conversation 会自动持久化，并在左侧“对话记录”作为内容资产入口复盘；
- 对话记录支持重命名、归档和恢复；消息、context pack、model metadata 作为执行历史保持只读；
- 分析结果和受众模拟支持人工复盘状态 `unreviewed/useful/rejected` 与备注编辑；input snapshot、stage results、模拟结果和 model metadata 继续只读；
- 小红书创作者主页在后端仍是独立 input asset type，但前端归入“创作者档案”；它可由本地 MediaCrawler fixture 导入，并可直接作为账号诊断输入；
- 历史分析结果 CSV 导出；
- 选题可调用创作 Brief 生成能力；Brief 和内容结构作为创作输出复用 Draft 表，通过 `kind` 区分；
- 选题和创作输出详情已按资产编辑体验拆分：用户可编辑字段独立展示，generated snapshot、input snapshot、来源和 model metadata 保持只读；
- 已支持从 Brief 继续生成内容结构，并在结构 Draft 的 input snapshot 中记录 sourceBrief；
- 输入素材整理 agent 草稿入口；
- 输入素材整理通过后端 `input_asset.format_*` skills 调用，不再是纯前端假整理。
- 图文/视频媒体资产基础层：
  - 上传图片/视频；
  - 文件由后端受控落盘；
  - SQLite 保存 metadata、derived JSON、用户备注和文件引用；
  - 前端支持列表、详情预览和显式保存；
  - Context Access Layer 已包含 `media_assets_overview`，并会携带 compact `imageUnderstanding` / `videoUnderstanding` / `videoPreview`；
  - Qwen 图片理解和视频理解可作为受控 media skills 调用；
  - Qwen 图片生成和视频生成可作为受控 media skills 调用；
  - 本地上传视频可通过 ffmpeg 抽取预览帧，帧会作为 `extracted_frame` 图文素材保存；
  - Qwen 理解结果会先作为草稿展示，用户确认后写入 `MediaAsset.derived`；
  - 生成类 media skills 会把远程结果下载到本地受控 media storage，并登记为 `MediaAsset`。
  - 图文/视频素材页中，上传和生成入口位于左侧列表，点击后在右侧展开；右侧不默认平铺所有操作表单。

当前媒体资产仍不包含：

- OCR / ASR 的独立流水线；
- 本地上传视频文件直传给 Qwen；
- 视频链接抓取、平台数据抓取或长视频语义切片。

### 示例数据

已命名的示例：

- `Qsheep 留学账号`
- `数字游民生活方式账号`
- `留学帖子数据合集`
- `留学评论区合集`
- `数字游民趋势.csv`
- `AIGC视频创作者激励计划`
- `AI短剧创作者样本`

其中数字游民账号概况来自原始 HTML 原型的默认输入。

### workflow

当前主要 workflow：

- 账号诊断；
- 热点分析；
- 视频博主质量诊断；
- 受众模拟。

已完成：

- workflow 创建 run 后由后端 worker 执行；
- workflow 创建支持 `idempotencyKey`，同一 workspace 下重复提交同一个 key 会返回同一个 run；
- SSE 只作为观察通道；
- 刷新后可重新打开历史 run；
- 账号诊断、热点分析、受众模拟已经接入 LangGraph；
- 视频博主质量诊断已按同一产品接口实现，支持小红书创作者主页派生 evidence pack，也兼容视频创作样本文本，并可选择已保存的图文/视频素材 compact understanding 作为补充上下文；
- 视频博主质量诊断结果页已强化证据边界展示：当缺少真实视频理解、图片理解或评论证据时，质量判断和激励适配会明确显示不可可靠评估项与建议补充证据；
- 视频博主质量诊断已用真实 Qwen live 路径回归 `_tt` 和 `QSheep` 两个小红书导入 fixture：两者均能完成 `creator_profile`、`video_quality`、`incentive_fit` 三个 stage；`_tt` 因没有 video 类型笔记，会保守保留 evidenceLimitations 和 cannotAssess；
- 视频博主质量诊断已新增不消耗 API 的 workflow fixture 回归测试：直接读取 `data/xhs-fixtures/_tt` 和 `data/xhs-fixtures/QSheep`，使用脱敏 Qwen stage output fixture 跑完整三阶段 workflow，覆盖真实 XHS 输入快照、证据边界、枚举/分数归一和 no-video 保守判断；
- 视频诊断 input snapshot 中的 XHS source 已做白名单清洗，只保留 `platform / fixtureCode / importedAt / crawler`，不把本地 `baseDir` 这类路径写入运行历史；
- 运行结果、stage 结果、错误和 input snapshot 会持久化。
- “下期选题”只用于受众模拟，不是账号诊断、热点分析或视频质量诊断的必填输入。
- 选题后的推荐链路已经从“直接生成结构”扩展为 Topic → Content Brief → Content Structure；Topic 直接生成结构仍保留为快捷兼容路径。

### 能力资产

当前能力资产包括：

- Skills；
- Agents；
- Workflows；
- agent conversation；
- Capability Maker agent；
- Creator Dossier Formatter agent；
- Topic and Creative Output Editor agent；
- AssetProposal apply/reject 流程。

当前定位：

- 用户侧主要查看和通过对话生成 proposal；
- 前后端和后端 seed 逻辑把它们当成可组合、可编辑、可新增的产品资产；
- Maker conversation 可以携带当前选中的 Skill / Agent / Workflow 详情作为 context target；
- Skills 已有受控的后端调用入口：`POST /api/skills/{skill_asset_id}/invoke`；
- 当前可直接调用或产品内调用的是产品内置输入素材整理类 skills、创作输出类 skills，以及 Qwen 图片/视频理解与生成类 media skills；
- 创作类生成动作属于能力资产，例如 `topic.refine_to_brief`、`draft.generate_structure`、`draft.generate_structure_from_brief`；生成出的 Brief 和内容结构属于内容资产；
- Capability Maker 生成的 Skill / Agent / Workflow proposal 已可 apply 为 generated capability asset；命中已有 asset 时会更新为 workspace-level generated override；
- Agent / Workflow proposal 会校验引用的 skill / agent 是否存在；
- media skills 不是通用代码沙箱，也不是任意工具运行时；
- 不把用户界面做成通用 workflow 编辑器或通用 agent 平台。
- PM 已可以在 Skills 详情页直接编辑 Skill contract，并保存为 workspace-level generated override；
- 视频诊断相关 Skill 已有结构化 Rubric 编辑区，保存后会进入视频博主质量诊断 workflow 的真实模型调用上下文；
- 视频诊断 stage metadata 会保存当次使用的 `skillContext`，用于复盘 skillId、版本和 pmRubric。
- PM 已可以在 Agents 详情页直接编辑 Agent definition，包括 system prompt、skillIds、default context policy、version 和 notes；后端会校验引用的 skill 是否存在。
- PM 已可以在 Workflows 详情页直接编辑 Workflow definition，包括 entryAgentIds、agentPlan、artifactEffect、callBinding、version 和 notes；后端会校验引用的 agent / skill 是否存在。
- PM 已可以在 Skill / Agent / Workflow 详情页查看 workspace generated override 与 builtin definition 的差异，并用乐观并发保护恢复内置版本；恢复时保留 workspace 备注和启用状态。
- Agent 详情页的 skill 引用、Workflow 详情页的 entry agent / task agent / task skill 引用已经可点击跳转到对应能力资产，便于 PM 调试组合关系。
- Skill 详情页已经支持两类测试：`input_asset.format_*` 和 `media.*` 走受控 invoke；analysis/topic/draft/simulation/video 诊断类 Skill 走 dry-run，返回结构化样例输出，不写业务资产。

### 模型调用

当前后端模型 provider：

- Anthropic；
- Qwen / DashScope OpenAI-compatible API。

浏览器不再直接持有模型 API key。

当前 qwen 接入状态：

- 后端已支持通过 `.env.local` 配置 qwen OpenAI-compatible endpoint；
- agent conversation 的 live 路径已经走后端模型 provider；
- qwen 请求会尽量使用 JSON response format；解析器可从 fenced JSON、前后带解释文字的 JSON、`data/result/output` 外层包裹，以及 OpenAI-compatible `function_call/tool_calls.arguments` 中提取结构化 JSON；
- qwen 结构化解析会归一部分常见字段别名，例如 `pain_points -> painPoints`、`proposed_actions -> proposedActions`、`video_quality -> videoQuality`，归一后仍按 operation 校验产品 root schema；
- 图片理解和视频理解已通过 Qwen vision chat completions 接入为受控 skills；
- 本地上传视频理解会先抽取预览帧，再把帧作为图片输入发送给 Qwen；完整视频文件不会直接发送；
- 图片生成和视频生成已通过 DashScope async task 接入为受控 skills；
- 生成类 media skills 会下载返回的远程结果到本地 media storage，并登记为 `MediaAsset`；远程 URL 只作为 `externalUrl` 来源记录；
- 图文/视频素材页面已经提供 Qwen 理解与生成入口；
- 视频质量诊断 live 路径不会把完整媒体文件放入 graph state，只保存媒体资产 ID 和 compact immutable snapshot；
- 理解结果先展示为草稿，用户确认后才写回 `MediaAsset.derived`；
- `scripts/smoke_qwen_media.py` 可用于真实 API smoke test，不进入常规自动化测试；
- 自动化测试仍默认使用 fake provider，避免 CI 或本地测试消耗模型额度；
- 完整 workflow smoke test 可用 `scripts/smoke_live_workflows.py` 在不打开前端的情况下跑账号诊断、热点分析和视频博主质量诊断；默认 demo，不作为常规测试前置条件，`--mode live` 才会消耗模型额度。

最近一次真实 smoke 结果：

- `scripts/smoke_model_api.py --operation pain_points` 通过；
- `scripts/smoke_model_api.py --operation agent_chat` 通过；
- `scripts/smoke_qwen_media.py image-understand` 通过；
- 当前 `backend/.env.local` 已补齐 `ANTHROPIC_*` 与 `QWEN_*`，文本模型和 media skills 都可用；该文件已被 git ignore，不会提交。

## 当前 TODO

### 已完成：资产 proposal 编辑、校验与 Skill dry-run

- Capability Maker 已经可以拿到 capability catalog。
- Maker conversation 已经可以携带当前正在查看的具体 Skill / Agent / Workflow 作为 context target。
- Asset proposal 已支持 pending 状态下编辑 title、description 和 proposed action JSON 后再 apply。
- Agent / Workflow proposal 已支持结构化辅助编辑，并同步 proposed action JSON。
- Asset proposal 已支持 apply 前 diff preview；用户需要先查看将创建/更新的目标资产字段，再确认应用。
- Apply / reject 会持久化状态、结果和错误；非 pending proposal 不可重复编辑或应用。
- Skill / Agent / Workflow proposal 已有基础字段校验、stable id 不可变校验和引用存在性校验。
- Skill 详情页已经支持直接编辑 contract；视频诊断 Skill 已支持 Rubric 表单化编辑。
- Agent 详情页已经支持用 checklist 组合 Skills；Workflow 详情页已经支持用 task 表格编辑 agentPlan.tasks。
- Skill 详情页已经有最小 Skill Test 面板，可直接测试 `input_asset.format_*` 和 `media.*` 这类已有 invoke 实现的受控 Skill，也可 dry-run 分析/选题/草稿/模拟/视频诊断类 Skill。
- Skill dry-run 不会创建 AnalysisRun、Topic、Draft、SimulationRun 或 MediaAsset；它只验证当前 Skill contract 的输出形状。

仍需增强：

- 更细粒度的 proposal schema diff，例如按 nested field 展示 agentPlan.tasks 的变化。

### P1：输入素材整理继续模型化

当前已经有 Creator Dossier Formatter agent、formatter skills 和后端 invoke API。当前实现是确定性 formatter，适合稳定生成草稿字段。

后续如果需要更强整理能力，可以把这些 formatter skills 的实现从确定性代码切到模型调用：

- 接收目标资产类型；
- 接收用户粘贴的原始文本；
- 返回结构化草稿和置信说明；
- 用户确认后保存为对应内容资产。

### 非目标：批量导入与批量 workflow

批量能力暂时从产品路线中移除。当前产品优先做好单个创作者、单组输入资产的诊断质量、证据检查、可复盘历史和 agent-assisted 资产整理。后端遗留 batch endpoint 暂保留为兼容路径，但前端不暴露，也不继续扩展。

### 已完成：conversation 执行持久化增强

agent conversation 现在已经不是同步等待模型完成：

- 发送消息会先创建用户消息和 assistant 占位消息；
- 后端 in-process task 生成回复；
- 前端轮询观察 queued/running/completed/failed 状态；
- conversation summary 已包含派生 `executionStatus`；
- 同一 conversation 存在 queued/running assistant message 时，重复发送不会创建新的 user message 或重复执行；
- 每条前端发送的用户消息已携带 `clientMessageKey`；同一 conversation 下同一个 key 的重试会返回已有对话，不会重复创建 user/assistant message；
- provider 失败会留下 assistant failure message；
- assistant 占位消息会持久化 `queuedAt / startedAt / completedAt`，刷新后可以复盘单条回复的执行时间线；
- 每次 assistant 生成现在都有 `agent_conversation_jobs` 记录，保存 conversation、assistant message、用户输入、mode、status、attempt count 和错误；
- 应用启动时会恢复 queued/running conversation job；旧数据仍可按 assistant metadata 兼容恢复。

剩余问题：

- 这仍是单进程本地 worker，没有跨进程 claim/lease，因此不适合多进程部署或长时间任务队列。

### P1：qwen 结构化输出继续加固

- 继续保持 fake provider 作为默认自动化测试路径。
- 已支持 JSON response format、fenced JSON 和前后带解释文字的 JSON 提取。
- 已支持 `data/result/output` 外层包裹解包，以及 OpenAI-compatible `function_call/tool_calls.arguments` 提取。
- 已按 model operation 校验必要根字段和基本字段类型，例如 `painPoints` 必须是 list，`creatorProfile` 必须是 object。
- 图片/视频理解已要求结构化 JSON，并把 `imageUnderstanding` / `videoUnderstanding` 保存到 media asset derived JSON。
- 已加入脱敏 qwen fixture 测试，覆盖 wrapper、fenced JSON 和 snake_case/camelCase root alias 归一。
- 视频诊断 score 字段已加固：Qwen 偶尔把 0-100 分数输出为 `0~1` 小数时，会在视频 workflow schema 层归一为百分制整数，例如 `0.55 -> 55`。
- 视频诊断关键枚举字段已加固：`creatorType`、质量 `level`、`typeConfidence` 和 `recommendation` 会兼容常见中英文标签并归一到产品内部值；真正未知的 recommendation 会失败并进入 stage-level error，避免脏判断进入历史。
- 后续仍可增加 action-type 级 schema、字段级 repair 和真实响应 fixture。

### P1：前端结构继续拆分

- 已将 stage/result 纯展示组件从 `App.tsx` 拆到 `frontend/src/components/StageResultViews.tsx`。
- 已拆出 `WorkspaceShell`、媒体资产页、输入资产页、账号概况页、workflow 调用面板、workflow 输出面板和 conversation pending polling hook。
- 已拆出帮助内容模块、workflow stage view 纯工具、AssetProposalsPanel、AgentConversationPanel、AgentsPage、WorkflowsPage、ConversationsPage 和 AnalysisHistoryPage。
- 已拆出 TopicLibraryPage、DraftsPage、SimulationHistoryPage，并沉淀 CommonUi 的 EmptyState、ErrorBanner、JsonPreview。
- 已拆出 workspace 输入资产派生选择 hook、保存状态 hook 和 agent conversation 自动聚焦 hook；`App.tsx` 继续保留顶层 orchestration 和业务 action。
- 下一步继续拆：
  - workspace 初始加载 / 刷新 hook；
  - workflow 执行 action hook；
  - topic/draft action hook。

### P2：文案继续中文化

已完成主要导航、帮助和 workflow 输入区中文化。仍可逐步清理：

- 能力资产详情里的技术字段名；
- 测试 fixture 中的英文 demo 名称；
- 文档中历史英文术语。

保留术语：

- skill；
- agent；
- workflow；
- CSV；
- LangGraph；
- API。

### P3：VPS 分享与部署

当前暂不考虑部署。需要分享时再决定反向代理或 FastAPI 静态挂载。

## 当前明确限制

- Workflow assets 是产品能力目录和调用说明，不是前端可编辑的任意 nodegraph；`callBinding` 只负责把 workflow asset 注册到右侧调用入口，并复用现有产品执行路径。
- Skills 当前是产品内受控能力；formatter skills 与 media skills 支持直接 invoke，不支持任意代码工具调用。
- 视频博主质量诊断优先使用小红书创作者主页派生的 compact evidence pack，兼容文本化视频创作样本；如果用户先保存 Qwen 图片/视频理解结果，workflow 可以读取 compact media understanding，但不做自动视频抓取或本地视频直传。
- 视频诊断 stage result 已持久化 evidenceScope、evidenceConfidence、evidenceLimitations、recommendedNextEvidence；video quality 还会保存 cannotAssess，避免在缺少真实视频理解时假装评估镜头、剪辑、口型或音频。
- 图文/视频素材已经可以作为媒体资产保存；Qwen media skills 可理解图片、基于公开视频/帧 URL 或本地视频抽帧理解视频，并可生成图片/视频资产。
- 本地上传的视频文件不会直接发送给 Qwen；当前本地视频理解入口依赖 ffmpeg 抽帧。
- SSE 是可重连观察 replay，不是完整 durable event log。
- 安全边界、认证、权限、多用户部署暂不作为当前版本目标。

### 暂不考虑

- 认证；
- 多租户；
- 权限系统；
- 通用安全边界设计。

# 当前状态与 TODO

## 2026-10-03：多指标复盘接入结果页与超时记录核对

本轮承接页面待办，验收点为四指标独立切换、缺点赞仍可看其他互动、缺失不当零、并列不被分成高低两类，以及旧历史按冻结数据回看。新增 AccountPerformanceView 与 7 项测试，从 AccountPortraitView 提取表现区域，补局部样式和可选汇总类型。保留账号画像优先顺序，没有修改后端、模型提示或正式数据。

“笔记表现”可切换点赞／收藏／评论／分享，显示有效数量、中位数、缺失数量和当前指标名次。列表按各指标独立排列，最多各展示两条；全同值明确显示相同，低组只纳入严格低于上组末项的值。小样本不强凑对照，标题用“按某指标排序”，不把零值第二名包装成高表现。旧历史无汇总时由原快照原始数值补算展示；保存汇总与原始值不一致则以冻结原始值为准。不读取当前资产替代历史，不写回旧结果。切指标关闭旧展开笔记，缺正文时禁用回看，原 StageResultRenderer 的运行 key 继续隔离不同历史。

超时只做离线记录核对，无新付费调用：相同约 27,176 字节的 context 在较早两次 qwen-plus 画像检查中分别用 74.37／67.56 秒完成，输出 3310／2986 tokens；最近新旧提示各一次在约 90 秒 ReadTimeout，未收到可保存响应。短创作请求 context 约 756 字节且输出 145 tokens，曾成功。以上 contextBytes 是 JSON 对象尺寸，不等于 HTTP 总体积或 token 数。这支持进一步检查长请求耗时，但不能定位是网络、服务排队或生成延迟；本轮不改全局超时或重试策略。

验证：`cd frontend && npm test -- src/components/AccountPerformanceView.test.tsx src/components/AccountPortraitView.test.tsx src/components/ArtifactRenderers.test.tsx` **24 项通过**；最终完整 `npm test` **223 项通过**，`npm run build`、`npm run lint`、`git diff --check` 通过。初次构建暴露测试里的 nullable 指标与 CreatorNote 类型不符，修正后重跑全部检查；既有 Node localStorage 和约 503 KB 构建提醒仍在。后端未修改，未重跑此前 531 项测试。

实际组件用隔离 Vite 5189 的临时页面验证：`backend/.venv/bin/python /tmp/sqs_performance_review.py` 在 1000／375／320 像素通过指标切换、Enter 打开冻结笔记、展开数据说明、无横向溢出与无页面错误检查，320 像素截图已查看。原生下拉的方向键在无头浏览器中未改变选项，因此最终测试用 select_option 切换，键盘验证限于笔记按钮，不声称已完成原生菜单的人工键盘验收。临时页面已删除、临时服务已关闭；未启动正式后端、部署、抓取、提交或推送。

需要用户决定：无。下一次需要测试：画像长请求的阶段耗时与同来源短子集，或旧模拟历史的推荐／实际名单回看，避免重复只改 prompt。拟改代码优先是只读检查脚本补请求尺寸和阶段时间，不改正式业务超时；下一项可见改进仍为 SimulationHistoryPage 的冻结推荐名单摘要，验收是能看清“建议谁／实际参与谁”，旧历史不补造关联。独立经验卡、创作采用／撤销以及完整画像新提示的内容验收仍待完成。

## 2026-10-03：创作助手四种合作模式与真实检查

本轮继续把 Skill 的长处落实到 Agent prompt，而不是只加软件字段。验收范围为区分讨论／起草／定向改稿／风格检查，用户只要求局部修改时保留其他文字，以及不改变原保存和冲突处理机制。修改 CREATOR_EDIT 提示，新增 `scripts/check_creator_edit.py`、对应测试，补创作旅程 API 回归和产品说明；不改前端布局、输出 schema、数据库结构或后台执行机制。

提示要求讨论提供实质不同的方向而不改稿，明确起草可以直接写，不强制填表；定向修改返回完整 title/body 但逐字保留范围之外内容，定位不明先问。风格检查参考本篇要求和账号表达，不自动重写或把一次采用升级为长期偏好。新增脚本使用明确构造的中文稿，默认免费预览；live 每次仅一次 Qwen，不自动重试、不建业务资产、拒绝覆盖报告，校验修改范围和原事实引用规则。它只对固定样例做逐字检查，不是生产侧自然语言范围校验器。现有自动应用仍保留，采用／撤销未实现。

本轮 3 次真实 qwen-plus 请求：`backend/.venv/bin/python scripts/check_creator_edit.py --case opening --live --output data/evals/creator-edit-opening-20261003` 成功，1260 tokens；只将第一段压成“选项越多，越难开始。”，原标题、后两段和换行保留。`--case discussion --live --output data/evals/creator-edit-discussion-20261003` 成功，1360 tokens；update=null，给出分阶段决策与通过选择认识自己两个不同角度，没有虚构个人经历，但回复稍长。两份结果已人工查看，不能据此保证所有主题或长稿都遵循范围。已知用量合计 2620 tokens，报告无正式资产写入。

在短请求可用后补测画像：`backend/.venv/bin/python scripts/check_account_profile.py --input-from data/evals/account-profile-short-quotes-20261003/report.json --live --output data/evals/account-review-skills-after-20261003`，同一 QSheep 十篇冻结输入、新 PROFILE 提示，91.05 秒 ReadTimeout。没有 HTTP 状态、正文或用量，不清楚是否计费；未重试。此前旧提示也超时，现在只能确认这次两个短创作请求可用、完整画像检查仍受阻，不能认定模型整体不可用，也不能判定新提示优劣或根因一定是代理／超时配置。账号复盘仍无有效前后对照。

验证：`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_creator_experience.py tests/test_creator_edit_check.py tests/test_creator_grounding.py tests/test_model_calls.py` **54 项通过**；完整 `.venv/bin/python -m pytest -q -o addopts=''` **531 项通过**（新增 17 项）；`.venv/bin/ruff check app tests ../scripts/check_creator_edit.py`、`git diff --check` 通过。`cd frontend && npm test -- src/components/CreatorCanvasPage.test.tsx src/CreatorJourney.test.tsx` **15 项通过**。API 回归使用注入响应与临时库，检查讨论不改更新时间、局部结果保存、原生成快照不变及同请求重发只执行一次；这不意味着后台会自动识别并拒绝模型的所有越界修改。旧 LangChain 提醒仍在，未改 UI、无新增视觉验收；未启动正式后端、部署、抓取、提交或推送。

需要用户决定：无。下一次需要测试：完整画像超时的范围，用同一来源的短笔记子集与调用诊断定位输入／输出耗时因素，最多小规模受控请求，不盲目增加重试或修改全局超时。拟改代码：优先补只读画像检查的尺寸／耗时诊断；同时保留前端多指标切换和历史回退待办。下一项新改进：把已计算的赞／藏／评／分享比较用于可见复盘，验收是能按指标查看不同笔记的特点、回看冻结原文且兼容旧历史。创作对照与采用、独立经验卡、推荐名单与实际名单历史摘要仍未完成，不把 prompt 改进当作这些功能已上线。

## 2026-10-03：复盘 prompt 增量与迭代检查

本轮响应“迭代检验新更改”。先核对发现，上一轮四指标统计已保存，但刚讨论的 Skill 方法还未写入 Agent prompt。先跑现有相关回归，再为 PROFILE 补充先认识账号、分指标对照具体笔记、拆解观点／论据／标题／开头／推进／语气，以及“来源写法 → 适用场景 → 具体调整”的复盘步骤。沿用 strengths、expressionPatterns、voiceFingerprint 和 contrast.takeaways，不新增输出字段或强制模板；示例明确为假设，不可抄成账号事实。仍保持积极、具体的反馈，不改历史。创作助手 CREATOR_EDIT 本轮未改，多指标计算汇总也仍未注入模型，模型读取历史笔记中已有原始指标。

修改 model_calls、其回归测试、只读画像检查脚本的人工审阅清单及相关设计文档。新增测试检查方法与边界进入真实构建的提示词、非画像上下文不进入请求，以及注入 HTTP 响应时只有一次请求、额度仍 6000、原字符串结果与模型元数据兼容；这些测试不是对模型语义的证明。检查脚本同时修正了扩展 lint 范围后发现的既有 import 顺序和预览长行问题。

真实对照未完成：执行 `backend/.venv/bin/python scripts/check_account_profile.py --input-from data/evals/account-profile-short-quotes-20261003/report.json --live --output data/evals/account-review-skills-before-20261003`，对 QSheep 已保存十篇笔记的冻结画像输入调用 **1 次 qwen-plus**。该次为改 prompt 前的基线，90.58 秒 ReadTimeout，没有 HTTP 状态、模型正文或 token 用量，不能判定已计费情况或推断模型质量。未重试，原计划的新 prompt 第二次调用取消，避免对外部阻塞盲目重发。失败报告与人工说明保存在被忽略的上述目录，没有正式 AnalysisRun 或新选题。新提示未做真实效果验收；不是“新提示生成失败”，也不是“效果已经改善”。

本地验证最终结果：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` **514 项通过**；定向 `tests/test_model_calls.py tests/test_account_diagnosis_evidence.py tests/test_account_profile_check.py` **68 项通过**；`.venv/bin/ruff check app tests ../scripts/check_account_profile.py` 通过。`cd frontend && npm test -- src/components/AccountPortraitView.test.tsx src/components/ArtifactRenderers.test.tsx` **17 项通过**，`git diff --check` 通过。免费 CLI 以同一 `--input-from`、不带 `--live` 再运行成功，requestAttempts 为 0。首次完整集在新增第二个测试前为 513 项，补齐并修正 lint 后重跑为 514；既有 LangChain 提醒仍在。未改 UI，所以没有新截图或浏览器视觉验收，未启动正式后端、部署、抓取、提交或推送。

需要用户决定：无。下一次需要测试：新提示在同一冻结样本上是否能给出不同指标的合理解释、实际可复用的经验，且不拼接经历或复制假设示例；一次连通恢复后的小规模验证即可，不例行重复计费。下一次拟改代码：按实际输出再调整画像提示／核验，或继续 AccountPortraitView 的指标切换及旧历史回退。下一项新改进：为 CREATOR_EDIT 加入角度拆解、定向修改与本人风格检查的方法，先用假模型测试讨论不改稿、只改指定部分的契约，再用真实输出验证；不同时改变自动采用机制。既有多指标展示、经验卡和模拟历史推荐摘要仍未完成。

## 2026-10-03：吸收复盘 Skill 的分指标分析方法

用户确认继续吸收四个 Skill 的优势，本轮优先实现内容复盘的确定性计算底座，而不同时改写提示词和画布。验收点是四指标独立计算、缺失不当零、并列同名次、只使用本次所选快照、旧点赞字段兼容和新结果能随原运行保存。修改 `account_diagnosis_evidence.py`、对应测试及三份设计／产品说明；保留全部已有未提交改动，模拟历史摘要待办没有关闭。

新 observations 增加 `metricSummaries`，分别保存赞、收藏、评论、分享的有效数、缺失数、中位数与 dense_descending 排名方式；逐条增加 `metricRanksInSelection`，原 `likesRankInSelection` 与其中点赞名次一致。仅在内存中的派生结果添加字段，不改输入快照；不把无效类型转成数字，不以已抓取评论条数替代评论互动数，不依据账号所有笔记数扩大分母，不计算统一质量分或曝光率。新增字段沿用原 profile 结果保存路径，不迁移或重写旧历史。当前前端和模型上下文保持原样，尚未产生经验卡或新的复盘结论。

验证：`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_account_diagnosis_evidence.py tests/test_account_profile_check.py` **47 项通过**；完整 `.venv/bin/python -m pytest -q -o addopts=''` **512 项通过**（本轮新增 16 项）。覆盖四指标排名差异、并列、缺失、零、空样本、单篇、偶数中位数、极端高值、非法类型、原输入不变、顺序变换及新运行 API 读取保存汇总。完整集期间补充了顺序不影响汇总的断言，随后定向集再次通过。`.venv/bin/ruff check app tests`、`git diff --check` 通过；首次 lint 发现一个测试函数定义超长，已修正。既有 LangChain 弃用提醒仍在。测试使用隔离数据库及注入响应，没有调用模型或启动正式后端；本轮未改前端，无新增浏览器／模型效果验收。

需要用户决定：本切片无。创作助手的改稿确认方案继续按设计分阶段推进，本次不改变自动应用行为。下一次需要测试的功能：四指标切换时能看到相应笔记及原始数值，缺指标和旧历史有明确回退，不将收藏高直接称为质量高。拟修改 AccountPortraitView、可选类型与组件回归，继续保持紧凑布局；下一项改进验收是可从赞／收藏／评论／分享分别发现账号已有长处，并打开冻结原文。之后再接可追溯的模型经验提炼，小规模验证建议是否具体可用。推荐名单与实际名单的历史摘要仍待完成，不遗忘原交接。

## 2026-10-03：账号复盘与人机共创设计交接

本轮根据最新关于内容生成及 content-performance-analysis 的讨论，暂时把原交接的模拟历史摘要后移，先明确设计。问题是现有画像、风格指纹和画布尚未形成可选择的复盘经验，AI 改稿也没有对照／采用／撤销。验收点是明确当前与拟议行为、字段归属、用户控制点和可分步验证的实施顺序，不改代码或宣称设计已上线。新增 `docs/creator-writing-collaboration-design.md`，同步 PRD、账号诊断设计和索引；修正模拟粉丝设计稿中仍称公开页“先选人再选题、快捷入口直接执行”的旧段落，当前已是统一确认页。

设计借鉴四个外部 Skill 的观点拆解、账号人格与流程分离、基于本人风格检查、分指标表现复盘；不套用固定人格、行业互动阈值或金句规则。多指标统计由程序计算，模型解释具体笔记差异并提出写作经验，用户决定本篇采用还是记为账号偏好。生成快照与用户决策分开。公开创作继续围绕 Topic，拟使用现有对话记录保存改稿提案和应用状态，以版本核验实现采用与有限撤销，不新增版本表、通用 Agent 平台或公开侧栏。brand-voice-guard 仅参考 tonecheck 的公开说明，未验证其运行代码，不混用同名项目。

验证：`git diff --check` 通过；`node --input-type=module` 执行内联文档链接检查（读取本轮五份设计／索引文件，提取 Markdown 链接，排除外部地址并核验相对文件存在），检查 **11 个本地链接，0 个缺失**。逐项对照 CreatorCanvasPage、agent_conversations、creator_grounding 和账号结果的当前边界，未把目标契约写成现有响应。本轮仅文档变化，未重跑单元测试、构建或浏览器；上轮前端 216 项与此前后端 496 项仅是先前结果，不是本轮验证。没有模型请求、抓取、正式数据写入、部署、提交或推送。

需要用户决定：建议“空稿首次起草直接填入并可撤销，已有正文的 AI 修改先看对照再采用”，是否采用这个默认交互；它不同于当前合法修改自动应用，确认前不更改。其余设计可先进行不改变交互的计算与契约准备。限制：所有新增经验、偏好、改稿提案与撤销设计尚未实施，不能据本文认为人机共创已完成；模拟历史摘要仍保留待办。

下一次需要测试的功能：模拟历史按冻结快照展示当时建议与实际参与名单，覆盖纯手选、采用后调整、旧记录缺字段、人物之后改名／归档，以及窄屏。下一次拟改代码：SimulationHistoryPage、相关类型和紧凑只读摘要及测试，不从当前粉丝列表替换历史定义。下一项新改进：完成这一已接通链路的历史可解释性，验收是能回答“当时建议谁、实际选了谁”，不新增模型调用。随后开始复盘的多指标确定性底座，测试缺失、零值、并列、单篇极值和手选子集；画布默认行为等用户确认后再实施。

## 2026-10-03：公开模拟入口统一到读者确认页

本轮承接上一轮交接，解决选题快捷入口直接运行、绕过推荐与人物确认的问题。验收点是入口不创建模拟、不自动推荐，保留同账号手选读者，创作正文先保存再预览，以及保存失败／迟到回调不切错页面。修改 App、CreatorCanvasPage、局部按钮样式和公开旅程／画布测试，未改变后端、推荐 hook 或模型提示。

分析结果的选题卡、选题库和 AI 创作助手现在都进入同一个模拟确认页；只有“开始模拟”创建 SimulationRun。创作助手增加“选择模拟读者”，有修改时先按 expectedUpdatedAt 保存当前标题和正文，未修改时直接使用已保存版本。保存失败保留编辑并显示错误，不跳转；等待保存期间禁用正文编辑、重复提交和发送，AI 正在回复时也暂不可进入确认。切换选题／账号后旧保存回调不会覆盖新目标或跳回模拟页。跨页面导航保留同账号粉丝槽位，切换账号清除旧目标；公开入口不要求先调用推荐。

实施前核对发现，上轮交接把公开创作内容笼统称为 Draft，但当前公开 AI 创作助手实际编辑的是 Topic 的 title／body。独立 Draft 页只在内部工作台中。因此本轮没有新增公开草稿选择器，也没有修改内部 Draft／旧 workflow 的兼容模拟路径；公开路径统一已经完成，内部 Draft 推荐确认不作为当前阻塞。这一边界已同步 PRD、模拟粉丝设计稿及文档索引。

验证：`cd frontend && npm test -- src/CreatorJourney.test.tsx src/components/CreatorCanvasPage.test.tsx` **15 项通过**；完整 `npm test` **216 项通过**（新增 6 项）；`npm run build`、`npm run lint`、`git diff --check` 通过。回归覆盖选题库入口不 POST、换题保留手选、最终提交准确的 topicId／人物顺序、画布保存后预览新正文、保存冲突保留输入、不重复保存、AI 运行中禁用、切题后忽略旧保存及账号隔离。原分析选题卡的已保存版本回调和内部 App 测试仍通过。初次构建发现新测试使用了 Testing Library 不支持的 exact 参数，已移除并重跑；既有 Node localStorage 和约 502 KB 构建体积提醒仍在。

浏览器检查使用实际 App、隔离 Vite 5178 和明确构造的接口响应：`backend/.venv/bin/python /tmp/sqs_canvas_confirmation_check.py` 在 1000／375／320 像素均通过。键盘进入确认、当前正文展开、手选读者保留、保存按钮换行及页面无横向溢出通过，320 像素画布和确认页截图已检查。每组只有一次正文 PATCH，没有推荐或模拟 POST，无页面错误。临时服务已关闭；未新增生产 fixture。这不是正式后端端到端或模型语义验收，后端未修改，本轮未重跑其 496 项测试。

需要用户决定：无。未付费调用模型、抓取、写正式资产、启动正式后端、部署、提交或推送。限制仍包括：未提交槽位和已采用标记不跨刷新恢复，历史尚无专门的推荐摘要，已完成推荐不会持续后台检查外部编辑；最终创建仍由后端事务校验。

下一次测试：打开使用推荐、手动调整推荐和纯手选的模拟历史，展示本次建议与实际参与名单；人物后来改名、归档或删除时仍使用冻结快照，旧历史缺该字段时不误报来源或补造推荐。拟修改 SimulationHistoryPage、相关类型及一个紧凑只读摘要组件，复用 personaDefinitions 和 inputSnapshot.readerSelection，不请求当前人物替代历史快照。下一项新改进的验收标准是用户能清楚看到“当时建议谁、实际选了谁”，默认收起长理由，兼容旧历史，320／375 像素无溢出；不把推荐理由注入角色模拟，不需要重新调用 Qwen。

## 2026-10-03：主模拟页接入“推荐读者／使用这组”

本轮承接推荐接口，解决用户仍只能手选、看不到按选题推荐的问题。验收范围是先看选题和正文、显式发起推荐、显式采用、手选不被迟到结果覆盖，以及刷新不重复付费。新增 readerSelection 类型、useReaderSelection、CreatorSimulationSetup 及测试，扩展 api、useSimulatedFans 的原子采用和 App 模拟参数，局部补充布局样式；没有修改后端或模型提示。

主模拟页已按“目标 → 推荐 → 人物槽位”排列。推荐返回后只展示组合，点击“使用这组”时再 GET 核验并整体替换槽位；少于三位保留空槽，也支持超过三位。核验期间暂时禁用目标和人物编辑，避免等待中覆盖新选择。采用后可以换人或加人，创建模拟携带原推荐 ID／指纹与最终名单，服务端保留 recommended／adjusted 区别。失败、无匹配、来源不可核验和过期都有对应状态，不补造推荐，手动模拟仍可用；已采用者可显式解除推荐关联。旧快捷入口和内部工作台尚未改动。

浏览器回执按账号／选题隔离，只存请求标识、人数及返回 ID。POST 前先记回执，响应丢失后由用户重试原 key／人数；已有 ID 时恢复只 GET，观察 pending／running 使用轮询，终态及卸载停止。切换选题、账号或输入版本后，旧响应不能覆盖当前展示；晚到的创建响应只补原目标回执。当前刷新恢复的是推荐记录，不保存未提交的槽位及“已采用”状态，刷新后需重新采用或手选。正式创建模拟仍以服务端事务核验为最终准则。

验证：`cd frontend && npm test` 最终 **210 项通过**（新增 18 项）；`npm run build` 和 `npm run lint` 通过，`git diff --check` 通过。定向命令 `npm test -- src/hooks/useReaderSelection.test.tsx src/components/CreatorSimulationSetup.test.tsx src/hooks/useSimulatedFans.test.tsx` 初版 22 项通过，之后增加卸载轮询测试及 API 接线断言进入完整集。覆盖响应丢失重放、重复点击、切题／版本迟到、GET 失败恢复、观察停止、跨账号响应拒绝、显式采用、采用后二次调整、过期不覆盖、部分／失败／无匹配和关联字段。初次运行暴露 Node 实验性 localStorage 与浏览器测试环境不一致，新增测试独立 Storage 替身；也修正了测试等待渲染和重复读取同一 Response 的问题。既有 Node 提醒仍在；构建产物约 501.46 KB，新增超过 500 KB 的体积提醒，后续可做页面按需加载，本轮没有扩展拆包范围。

实际组件在隔离 Vite 5178 配合 Playwright、构造的四位读者和推荐响应完成 1000／375／320 像素检查：每组仅一次推荐 POST，刷新不新增 POST，原手选不自动改变，键盘可展开理由并采用，空槽保留、主按钮蓝色且无横向溢出或页面错误；320 像素截图已检查。执行命令为 `backend/.venv/bin/python /tmp/sqs_reader_selection_ui_check.py`，三组通过。临时预览页面已移除、服务已关闭。这是实际组件与观察契约的界面验证，不是正式服务端到端或真实推荐效果验收。后端未改，本轮未重跑其 496 项测试。

需要用户决定：无。未调用真实模型、抓取、写正式资产、启动正式后端、部署、提交或推送。限制：快捷模拟入口尚未统一；草稿推荐及历史推荐摘要尚未在页面开放；未提交名单不跨刷新恢复；外部编辑后页面不会后台持续检查已完成推荐，但采用时和创建模拟时会重新核验。

下一次测试：选题卡和创作助手发起模拟应先进入同一确认区，不直接创建运行；草稿与选题分别使用正确目标，切换目标不串用推荐回执或关联，也不清空已手选人物，旧内部入口不回归。拟修改 App 的公开模拟导航、CreatorSimulationSetup 的目标表示和 readerSelectionApi／hook 的 topicId／draftId 支持，补入口与最终载荷集成测试。下一项新改进是统一确认路径，验收标准为所有公开模拟入口都能先看实际待测内容、选人、再手动开始；随后展示模拟历史的建议名单与实际名单。无需下一轮例行重复付费测同两题。

## 2026-10-03：推荐过期检查与模拟采用校验

本轮解决旧推荐可能混入新正文或已编辑人物的问题。验收点为只读过期状态、历史不改写、创建模拟时再次核验、允许手动调整及不把推荐理由送入角色上下文。提取 reader_selection_requests.resolve_input，新增 freshness／观察响应和 reader_selection_adoption，在 SimulationRunCreate 增加可选 readerSelectionId／readerSelectionInputHash，并把采用摘要放入现有模拟 inputSnapshot；无需新表或图重构。

GET 在同一只读快照比较目标内容、账号定位、完整候选池及人物版本，返回 current／stale／unavailable 和具体原因，原 status、输入、结果不变。未选中人物的编辑、新增或归档也会过期，因为模型看到过完整池；置顶、内部 angle、草稿 reuse 不影响推荐。来源缺失或旧记录无请求来源仍可读，但不能判为有效。POST 重放仍返回原记录，不自动重新推荐。创建模拟在同一写事务重新核验，不相信之前的 GET；过期、错账号、错目标实例、错指纹、未完成／失败／无匹配的推荐均不创建或入队。

有效推荐可以采用或手动换成其他候选，也可增加超过推荐人数的读者，保留既有重复／归档校验。新模拟保存建议和实际有序名单、校验警告及 recommended／adjusted 来源；明确手选已保存人物的新运行标 manual，旧兼容自动派生与旧历史不补造来源。去掉推荐 ID／指纹即可按当前手选名单继续。快照保持不可变；图初始状态及实际注入的独立反应／汇总调用验证没有推荐理由，模型上下文白名单未改。本轮假反应选择不评论，未触发交流调用，不将其表述为交流效果验收。

测试全部使用隔离临时库与假模型。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_reader_selection_adoption.py tests/test_reader_selection_api.py` 最终 42 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 496 项通过（新增 24 项）。`backend/.venv/bin/ruff check backend/app backend/tests`、`git diff --check` 通过。新增 GET 的动态 freshness 与 POST 的原记录有意不同，旧测试的整包等同断言已明确拆分。首次单文件收集触发既有包循环导入，conftest 改为先隔离默认数据路径，再按正常 main 入口初始化，避免测试收集顺序决定成败；没有扩大为包结构重写。既有 LangChain 提醒仍在。前端未改，192 项仍为此前结果，无视觉验收。

需要用户决定：无。未真实调用模型、抓取、启动正式后端、写正式资产、部署、提交或推送。限制：后端可查询并安全采用，但页面尚无推荐入口、过期提示或历史专门展示；本轮不评价 Qwen 推荐语义，上一轮简短理由提示仍待定向复测。

下一次测试：前端推荐区的请求重放与刷新恢复、换账号／选题的迟到响应、手动名单不被覆盖、采用后再手动换人、过期／失败／无匹配，以及最终请求正确携带原推荐 ID／指纹。拟新增推荐 API 类型、useReaderSelection 和紧凑确认区域，复用现有人物槽位；首先做按钮触发和显式“使用这组”，不页面加载即付费。下一项改进验收是选题预览在前、推荐与人物选择在后，用户可继续手动模拟，冲突保留名单；再统一选题／草稿快捷入口并展示历史建议与实际名单。界面接线后用隔离服务验证 320／375 像素与键盘，不启动正式后端。

## 2026-10-03：真实 Qwen 选人、输入预算与两题检查

本轮验收是完整读者池进入、空池不付费、超预算不截池、仅一次模型请求、无效项沿用部分结果校验，并观察同池不同题目的实际推荐。新增 reader_selection_prompt／reader_selection_model、reader_selection operation、只读检查脚本和测试，扩展 worker 的 input_too_large 错误；main 仅在 qwen／dashscope 且有 Qwen 密钥时接真实 provider，测试仍可注入。其他提供方不自动接此能力，配置缺失继续 503，不造假推荐。

输入为定位、读者可见内容、目标人数与全部当前角色卡；内部账号 ID 和版本留在快照，不发给模型，原始定义、历史反应、营销策略不进入。system＋user UTF-8 合计预算 64,000 bytes，超限记录尺寸并失败，没有模型调用或裁池；这是操作性限制，不是精确 token 计数。输出额度 4,000，检测截断，失败不重试。空池直接保存有说明的无匹配，modelCalled=false。完整 8 人、请求 6 人、Qwen HTTP 载荷、超限后继续下个任务及未知 ID 部分完成均有回归。

真实命令为 `backend/.venv/bin/python scripts/check_reader_selection.py --database data/app.sqlite3 --workspace-id a81ff1af-8b0d-4999-a9a2-d73f48a53c0d --live --output data/evals/reader-selection-two-topics-20261003`，先运行不带 --live／--output 的免费预检。输入为 QSheep 当前保存的 5 位早期角色及两篇人工编写正文，非新抓笔记、非新版 8 人画像。两次 qwen-plus 均结构完成，11.04／10.19 秒；输入各 4,663／4,705 bytes，tokens 输入 2,326、输出 767、合计 3,093。脚本以 SQLite mode=ro 读取一致快照，不加载 main、不建应用、不写正式记录；检查报告与 review.json 在上述 Git 忽略目录。

两题都选中工具实用、申请规划、经历共鸣三位，排序与理由改变：口语练习优先操作门槛，保研选择优先申请路径与取舍，大体有实际关联。相同人物跨题复用合理，但这不是组合多样性提升证据；第一题部分理由将一周练习拔高为长期申请行动链，contribution 出现“会追问”，第二题还加入套磁周期等正文未提供环节。检查后仅加一条短正反例，建议每项 30～60 字、写可观察试读角度而非预设动作，不补正文不存在的具体环节；没有追加付费复测，不能说已消除此问题。旧粉丝未改，推荐理由仍未送入模拟节点。

验证：`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_reader_selection_model.py tests/test_reader_selection_api.py tests/test_model_calls.py` 46 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 472 项通过（新增 12 项）。最后提示调整后，`.venv/bin/python -m pytest -q -o addopts='' tests/test_reader_selection_model.py tests/test_reader_selection_check.py tests/test_reader_selection_api.py tests/test_reader_selection_persistence.py tests/test_reader_selection.py` 79 项通过。`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_reader_selection.py`、`git diff --check` 通过。免费脚本首次遇到仓储／服务包初始化循环导入，已把仓储导入延后到只读加载函数，补独立子进程预检、数据库文件哈希不变、默认应用未创建和失败不发第二请求的测试；既有 LangChain 提醒不变。前端未改，192 项仍为此前结果。

需要用户决定：无。未启动正式后端、抓取、部署、提交或推送，没有写正式推荐／人物资产；只读实测不触发迁移。限制：后端能真实推荐，页面尚不能操作，过期判断与采用校验仍缺；当前结果只能说明这两题和早期 5 人池表现，不能代表更复杂读者池或评论模拟效果。

下一次测试：目标正文、账号定位或人物池变更后，读取旧推荐应返回独立的过期状态，保留原输入／结果；跨账号、归档、旧记录缺请求来源要明确处理，GET 绝不触发模型。拟从请求解析服务提取同事务输入重建方法，并补推荐采用时校验及 SimulationRun 可选关联的分步测试，先不改 UI。下一项新改进验收是推荐不能把新正文和旧理由悄悄混在一起，用户仍可按当前手选名单独立模拟；随后接统一“推荐读者／使用这组”的前端确认区。无需在下一轮例行重复付费测这两题，提示效果复测留待明确回归目标。

## 2026-10-03：推荐创建／查询接口与独立后台执行

本轮承接持久化记录，验收重点是响应丢失、重复提交或观察断开不重复调用，人物编辑后重放原任务，以及启动恢复不误伤活跃执行者。新增 reader_selection_requests、reader_selection_worker、reader_selection_api、0034 请求身份迁移和接口测试；在 main 的 lifespan 接线。没有改现有模拟图、前端或模型提示。公开请求只包含 requestKey、目标和人数，拒绝客户端自行传人物池；首次在单一事务读取目标、定位和本账号 active 卡片。同 key／同请求直接返回原快照，不重新读取已变更资产；改目标或人数则冲突。

POST `/api/workspaces/{workspaceId}/reader-selections` 返回持久化任务，GET 同路径加 `/{id}` 只观察，跨账号返回 404。后台串行扫描 pending，不依赖请求或 SSE 活着，超时和异常保存失败但不自动重试；成功／部分／无匹配结果沿用前轮校验。生命周期启动先取得数据库旁的 OS 独占锁再恢复中断，另一工作者不能改写活跃任务；关闭时先取消并保存 interrupted 再释放锁。锁目前支持 macOS／Linux，不是多机调度；没有 provider 或不支持锁时不开工作者。默认尚未接真实推荐 provider，新任务明确返回 503；已保存任务仍可查询、重放，生产不会返回假推荐。

发现并修正一处测试隔离漏洞：conftest 顶层导入 main 时，main 会创建默认 app 并先迁移正式数据库，早于临时 fixture。本轮早期定向测试因此把 0034 加到了默认库；只读核对也看到上轮的 0033 已落在那里，reader_selections 实际记录数为 0。此前“临时数据库验证”的表述遗漏了这次初始化副作用，现明确更正，不回滚已应用迁移。conftest 现在在测试收集前将默认 DB／上传路径强制指向临时目录，结束清理并还原环境；新增断言验证默认 app 也使用临时库。没有生成正式推荐结果，也没有启动正式服务。

验证：初次 `cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_reader_selection_api.py tests/test_reader_selection_persistence.py` 32 项通过；补响应丢失、部分结果和草稿后，`tests/test_reader_selection_api.py tests/test_reader_selection_persistence.py tests/test_reader_selection.py tests/test_workflow_lifecycle.py` 定向命令 71 项通过。修正初始化隔离并补活跃工作者竞争测试后，完整 `.venv/bin/python -m pytest -q -o addopts=''` 460 项通过（本轮新增 18 项），全部使用注入响应，不调用真实模型；`backend/.venv/bin/ruff check backend/app backend/tests`、`git diff --check` 通过。长行和 import 排序已修正，既有 LangChain 提醒不变。未改前端，192 项仍为此前结果，无视觉或推荐语义效果验收。

需要用户决定：无。未抓取、调用模型、部署、提交或推送。限制：只验证了工程执行路径，真实推荐 provider、输入预算、当前内容过期判断、采用推荐与模拟快照关联、前端确认区仍未实现；接口 completed 不表示推荐仍适用于当前已编辑正文。重启不承诺网络层严格一次计费，未知调用结果会失败并等待新请求。正式配置目前没有启用推荐工作者，不会在下次启动时自动生成推荐。

下一次测试：新增可注入的真实选人 provider 和输入预算检查，用假模型验证完整 6～8 人卡片、超预算明确拒绝而不裁池、未知 ID／部分无效结果、空池不付费，以及只调用一次、不携带历史反应和内部营销字段。拟修改 model_calls 的产品特定 operation、推荐 provider 与受控接线，保持现有请求身份和冻结输入；先确认预算与失败处理，再用保存读者池对两个题目做最多两次 Qwen 检查，记录相关性和人物差异，不能以名单不同当作成功。下一项新改进验收是推荐理由确实贴合当前内容和人物、默认生产不再依赖测试注入；此后做过期校验与统一前端“推荐／采用”确认，不自动覆盖手选名单。

## 2026-10-03：读者推荐记录持久化与中断保护

本轮承接选人契约，问题是推荐尚无可恢复的执行记录。验收点为同一请求只建一条、观察不执行、并发仅一次领取、冻结输入不随粉丝编辑变化、结果与失败落库、重启不盲目重发未知模型请求。新增 0033_reader_selections.sql、repositories/reader_selections.py、services/reader_selections.py 和 test_reader_selection_persistence.py；没有改主应用接线或现有模拟行为。

同账号 requestKey 唯一，同 key／同冻结输入返回已有状态（包括终态），不同输入明确冲突。pending 只能领取一次；结束操作要求当前内部凭证，验证用数据库原快照而不是执行者传回的副本，拒绝未领取、错误凭证、重复结束与中断后的迟到写入。合法无匹配正常完成；部分有效项保留且附警告；全无效或畸形输出失败，保留模型元数据和时间。没有人物改写接口，也没有自动重试。显式中断恢复只处理 running，保留 pending 和终态；构造服务或读取都不会触发恢复或执行。恢复必须在旧工作者确认停止后的独占启动阶段调用，当前未接生命周期。

验证全部使用临时 SQLite 和本地假输出。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_reader_selection_persistence.py tests/test_reader_selection.py` 最终 49 项通过，其中新增持久化测试 18 项；完整 `.venv/bin/python -m pytest -q -o addopts=''` 442 项通过，之后补充中断不改变已完成结果的断言并再次通过上述定向集。测试包括 12 次并发创建与领取、中文与 emoji 原样保存、跨账号隔离、重复迁移、观察后状态不变、重建服务恢复、输入版本冲突、真实临时资产编辑前后快照，以及非法／部分／无匹配结果。`backend/.venv/bin/ruff check backend/app backend/tests`、`git diff --check` 通过；新增测试两处超长行已修正，既有 LangChain 提醒不变。未改前端，192 项仍为此前结果，本轮无浏览器或模型效果验收。

需要用户决定：无。未调用真实模型、写正式资产、启动正式后端、抓取、部署、提交或推送。当前只是内部持久化服务，页面仍不能推荐；还没有 HTTP 请求去重、后台分发、断线观察集成、过期判断或采用推荐。内部创建以已冻结输入判断重放，未来 API 必须先识别同一请求，避免重发时读取已变化人物并错误构造新任务；不能把本轮数据库幂等直接说成完整网络生命周期已完成。

下一次测试：接入只创建／观察的 API 和后台执行，用假模型验证同 key 重发且人物已编辑时仍返回原记录、不同载荷冲突、GET／断线不重复执行、跨账号访问拒绝、启动恢复与迟到完成。拟新增请求载荷身份校验和 worker 适配，复用当前持久化服务，不接真实模型或公开 UI；明确 recovery 的唯一调用点及工作者停止顺序。下一项改进验收是一次 POST 能独立完成假推荐、刷新仅观察、终态可重开且没有第二次调用；随后再接有预算约束的真实选人 operation 与统一前端确认区。

## 2026-10-03：选人输入与结果契约落地

本轮落实上次设计的第一步，验收范围是当前账号读者池完整进入、当前编辑字段生效、不同选题不重写人物、无匹配与部分失败可区分，并保证原模拟目标内容不变。新增 services/reader_selection.py、services/audience_target.py 和 test_reader_selection.py；原 AudienceSimulationWorkflowService 的目标方法保留，只委托共享纯函数。没有新增 API、迁移、模型 operation 或界面入口，既有手动模拟不需要先跑选人。

输入接收现有 FanResponse，遇到混入其他账号、重复身份或缺版本时明确拒绝，归档者不进入候选；active 卡片全部保留，不因为默认推荐 3 位就先截掉后面的角色。所有当前编辑字段与兴趣原样保留，原始定义和历史评论不挤进候选卡。目标沿用原读者可见标题／正文／结构内容，内部策略与推荐理由排除；深复制防止共享嵌套对象被修改。指纹包括账号、目标、候选版本、人数及规则版本，不把它当作模型确定性保证。

输出契约允许 direct／adjacent 和短理由，不允许模型新增姓名、性格等人物字段。未知／归档 ID、重复 ID、空白或超长理由被拒；重复 ID 全部拒绝，不任意保留一份解释。有有效项则部分完成，全无效则失败；空列表且有无匹配原因可以正常完成。超过本次请求人数明确报错，不静默取前三位；请求人数没有 3 位上限。两种选题的假响应可选择同池中不同组合，人物定义不变；这只验证契约，不证明实际推荐相关性。

验证：`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_reader_selection.py tests/test_audience_simulation_workflow.py tests/test_audience_evidence.py` 78 项通过，其中新增选人测试 31 项；完整 `.venv/bin/python -m pytest -q -o addopts=''` 424 项通过。新增回归包含 8 位完整候选、6 位请求、同兴趣不同判断、两题指纹、深复制、存量数据库资产只读适配，以及旧草稿目标白名单兼容。`backend/.venv/bin/ruff check backend/app backend/tests`、`git diff --check` 通过；新增 import 排序及测试长行已修正，既有 LangChain 提醒不变。前端未改未跑，192 项为此前结果，无需浏览器检查本轮纯后端函数。

需要用户决定：无。无真实模型调用、抓取、正式数据写入、服务启动、部署、提交或推送。数据测试使用临时数据库和注入响应；语义相关性、推荐多样性、输入调用预算、持久化、异步执行和页面采用均还未完成。没有把假推荐写入正式资产，也没有修改任何人物或模拟快照。

下一次测试：推荐任务的持久化与请求幂等，确认创建后刷新只读取，同 requestKey／同载荷返回同一记录，不同载荷冲突，输入和成功结果不可被后续人物编辑覆盖。拟新增 reader_selections 的 SQLite 迁移、repository 和 service 及临时数据库测试，复用本轮纯契约；先不接付费模型或前端入口。下一项改进验收是可独立创建、领取和结束推荐记录，失败与中断有明确状态，未知外部调用结果不自动重复发送；随后再接工作者、API 与界面。按题选人仍不能从现有页面触发。

## 2026-10-03：按选题挑选读者的落地设计

最新讨论转向“不同选题先 retrieval 对应读者”，本轮据此先明确接入设计，不沿用上一交接继续付费测画像，也不将对话中的建议直接当成已实现功能。验收是核实当前选人机制，写清字段、持久化、推荐采用、过期与快捷入口，并保证不改人物、不预写反应、不静默替换手选名单。实际只修改 simulated-fan-model-design、PRD、文档索引和本状态记录。

代码核对确认：useSimulatedFans 首次按列表取前三位 active 角色，没有题目输入或相关性排序；App 的模拟页先选粉丝再选题，选题卡和草稿还可直接进入运行。后端已经支持当前账号校验、归档／重复限制及编辑定义快照，应该复用。设计明确从同账号已有卡片池选人，兼顾兴趣、需求、判断和表达差异；推荐理由供创作者查看，不送给反应／交流模型充当必须执行的行为。无匹配可以返回空，不为了凑数生成角色或强制反对派。

拟采用独立 ReaderSelection 记录及两条创建／读取 API，后台单次执行、观察不触发模型；不增加向量库或重写模拟图。推荐与最终选择分开保存，旧手动请求继续可用。当前建议是“推荐读者 → 使用这组”，自动生成建议但由用户采用；是否将首次推荐改成进入页面自动触发，属于后续体验选择，本轮不更改默认行为。页面改题、换账号、人物编辑／归档、请求迟到和刷新恢复均写了边界，快捷入口也必须汇聚到同一确认区。

文档索引原来仍把早期 Top 3 当成最新方案，并把整个粉丝设计描述成未实施；已区分当前默认三个可加槽位、已实现简短人物资产与未启用的推荐／原型／多维设计。验证当前基线：`npm --prefix frontend test -- --run src/hooks/useSimulatedFans.test.tsx` 6 项通过；`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_simulated_fans.py tests/test_audience_simulation_workflow.py` 22 项通过；`git diff --check` 通过。只是现有选择与快照行为回归，不是新推荐测试。未改运行代码，所以未重跑全量或 build，393 项后端／192 项前端仍为之前结果；既有 LangChain 提醒不变。

需要用户决定：无阻塞项；首次自动触发推荐还是按钮触发，保留为体验阶段可调整项，建议首版按钮触发并显式采用。未调用模型、抓取、启动服务、写正式资产、部署、提交或推送。限制：这轮是可执行设计，不代表现在已支持按题推荐，亦未验证选人模型效果。

下一次测试：用同一个已保存卡片池、两个不同选题和假响应验证选人输入／输出契约：当前编辑值完整进入、没有跨账号或归档人物、未知／重复 ID 拒绝、无匹配合法、推荐理由不改人物，也不进入模拟上下文。拟新增 `backend/app/services/reader_selection.py` 的纯输入构造与输出校验及单测，先提取并复用读者可见目标函数，不接 API、数据库迁移或付费模型。下一项改进验收是选择服务可独立验证且不改变现有手动模拟、旧快照与既有目标输入；持久化和 UI 留给后续切片。此前账号画像跨场景提示复测保留为后续待办，不宣称已通过。

## 2026-10-03：账号画像同输入复测与跨场景归纳

本轮按交接检查关键词、优势、概览和鼓励的实际效果。免费核对发现早期 data/xhs-fixtures/QSheep/xhs 只有 20 篇，前次检查用的是后续 30 篇资料；两者最近 10 篇及互动数都不同，不能直接作为同输入比较。因此 check_account_profile 新增 --input-from，复用既有报告的 snapshot、context、observations，不重新派生素材、不把旧输出传给模型。入口二选一，缺必要输入先失败，默认仍免费，报告记录来源哈希；补冻结输入预览、畸形报告和假 HTTP 的命令行回归。没有改正式导入路径。

真实命令：`backend/.venv/bin/python scripts/check_account_profile.py --input-from data/evals/account-profile-6000-20261003/report.json --live --output data/evals/account-profile-short-quotes-20261003`。实际一次 qwen-plus，67.56 秒，输入 8,402、输出 2,986、合计 11,388 tokens，finishReason=stop，6000 额度和 temperature 0.3 不变；返回后再次确认冻结的三份输入及 inputHash 与基线完全相同。只请求画像，不生成受众、选题或模拟，不写正式历史。原始报告与人工 review.json 位于被 Git 忽略的输出目录。

结果可用但不能算全面通过。概览与鼓励各 1 条保留，前次二者均被过滤；关键词 4 留 2、优势 3 留 2、反复方向 2 留 1、读者价值 2 留 1、表达特点 2 留 2、近期变化 1 留 0。仍有引用删空格或加省略号，说明短引用提示没有稳定解决问题，也不能用两项字段恢复宣称整体改善。语义上，“文科生转 AI”“人类学式思考”与材料有关，亲身比较工具、记录反馈和成长过程确实有可展开的价值；但一条保留的优势把学校导师关心伦敦适应归进实习团队特点，另一条把 gender 课堂理论说成作者重释 AI 的方法，原文并未连接这两个场景。鼓励的方向相关，但“稀缺”“当下最需要”仍显空泛；旧版对比还凭缺少完整内容的视频文本判断形式不匹配。

本轮只针对跨场景问题给 PROFILE 增加简短正反例：可以正面归纳“擅长写清支持与成长的具体过程”，但分别保留求学与实习的主体和场景；课堂理论与技术实践可以并列，不虚构作者已经建立的方法联系。没有删除上下文、放宽引用校验、改模型或预算，也不重写这次结果。该提示在实测之后修改，尚未真实复测，不宣称已消除混淆。回归锁定正面表达与完整输入仍保留。

检查命令：`backend/.venv/bin/python scripts/check_account_profile.py --input-from data/evals/account-profile-6000-20261003/report.json` 免费预览通过；`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_model_calls.py tests/test_account_profile_check.py` 最终 44 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 393 项通过。`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_account_profile.py scripts/account_profile_diagnostics.py`、`git diff --check` 通过。首次从仓库根运行 pytest 导入了错误路径，改从 backend 执行后通过；新增测试超长行已修正，既有 LangChain 提醒不变。前端未改未重跑，192 项为上一轮结果。

需要用户决定：无。未启动正式后端、抓取、部署、提交或推送。剩余限制是画像跨场景归纳、原文引用稳定性，以及凭文字不足的视频材料判断内容原因；本轮不引入图片／视频理解，也不以确定性关键词过滤冒充语义修复。

下一次测试：仍复用相同冻结输入，对新增主体／场景规则至多做一次画像检查，人工核对学校导师与实习带教是否分开、是否仍把课堂理论接到 AI 方法、积极具体的优势是否保留；不要求模型复述固定答案。拟修改代码：优先使用 --input-from 与已有验证；如观察无改善，记录并撤回无效例子，不连续堆叠提示。下一项改进验收是有原始输出、实际保留字段、具体引文语义和用量可比较；若连接失败不重复请求，转向已有账号结果的本地兼容检查。

## 2026-10-03：模拟部分失败、沉默与缺失分别展示

本轮承接结果页状态检查。原实现保存了角色级错误，但公共 SSE 将原因合并为一段文字；前端把有成功结果的阶段整体标成失败，历史页又没有阶段状态。验收要求是成功反应保持可读，no_comment／skip 不计失败，失败者能与本轮姓名对应，实时与历史一致，不改变执行或重试规则。修改范围为 simulationStageStatus、SimulationStageNotice、workflowStageViews、WorkflowOutputPanel、SimulationHistoryPage、App 的模拟事件处理，以及后端 api 的观察事件数据。

现在每轮反应显示已返回、评论及不评论数量，交流区相应区分回应与不追加回应。成功项与错误并存时显示蓝色“部分完成”，原因默认收起，展开后按本轮保存的角色名字列出。仅有沉默也是完成；初始反应缺记录时说明“未记录反应”，不猜成主动沉默或编造失败原因。旧数据未注明行为单独标识；交流不要求每个角色都有结果，因为只有符合条件者需要参与。已结束运行的无结果阶段显示“未完成”，不继续显示等待。历史仅有合并错误时仍能显示，不猜错误归属。

公共 SSE 的 stage.failed 数据新增可选 stageErrors 字典，保留原 eventType、status 和 error。前端的模拟事件合并提取成小函数，先成功后失败或先失败后成功均保留已返回结果及错误，兼容旧的子角色 stageKey。阶段成功不再抹掉同阶段其他角色错误，下一运行重新初始化。后端和历史重建均避免将已有交流错误又标成成功跳过；没有执行新模型请求、自动重试或改变数据库／生命周期。

测试：`npm --prefix frontend test -- --run src/components/SimulationStageNotice.test.tsx src/components/AudiencePreview.test.tsx src/components/WorkflowOutputPanel.test.tsx` 21 项通过；新增 8 项回归，覆盖实际历史组件、两种 SSE 次序、旧错误、全沉默、未完成及切换运行。完整 `npm --prefix frontend test -- --run --reporter=dot` 192 项通过。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_audience_simulation_workflow.py` 15 项通过（新增 1 项并增强原部分失败用例），完整 `.venv/bin/python -m pytest -q -o addopts=''` 386 项通过。`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`backend/.venv/bin/ruff check backend/app backend/tests`、`git diff --check` 通过；既有 Node localstorage／LangChain 提醒不变。

隔离 Vite 5178／Playwright 使用明确的人工构造结果检查部分失败、全沉默、缺记录和全失败四种情况，输出区与实际历史页各自覆盖 1000／375／320 像素，共 24 组通过。已核对阶段状态、计数、角色错误、键盘展开，无页面错误或横向溢出，320 像素截图已检查。临时服务与页面清理；正式后端未启动，正式资产未写入。此次是展示与观察数据契约的验证，不是模型效果或正式服务端到端验收。

需要用户决定：无。未调用模型、抓取、部署、提交或推送。剩余限制：旧记录缺少角色级错误时只能展示合并原因；未保存执行明细的旧交流记录不能据此还原每位是否收到任务，不把没有交流输出一概当失败。原始模型理解与人物质量问题仍按此前真实报告保留。

下一次测试：轮换回账号认识，复用已保存 QSheep 样本，对当前短连续引用提示做至多一次画像调用，检查关键词、具体优势、概览和鼓励语是否既保留有效内容又贴合原文；先免费核对样本范围及上下文与 account-profile-6000 报告的差异，记录实际模型、用量和限制。拟修改代码：优先使用现有 check_account_profile 与回归；仅在发现可复现的字段或展示缺陷时补对应验证，不预先堆叠提示。下一项改进验收是给出原始生成／实际保留字段对比及具体语义判断，不能用结构通过率宣称了解账号；若外部连接失败，不追加付费重试，转为本地字段兼容检查。

## 2026-10-03：模拟结果显示人物名称与回应对象

本轮承接上次页面任务：独立反应原来显示 Persona 加内部 ID，讨论对象也直接暴露 ID，创作者难以对应人物。验收要求是实时输出、历史重开都使用本次运行的角色定义；同名可区分、缺姓名可回退，切换运行不残留旧名称，不改生成内容或已编辑资产。新增 simulationPersonaLabels 映射，接入 WorkflowOutputPanel、workflowStageViews、ArtifactRenderers 和 StageResultViews，并补组件及历史集成回归。

反应标题和“回应”现在显示保存的姓名，旧角色可使用 archetype；同名加本轮受众序号，缺定义时按本轮角色／反应次序显示“受众 1”等。明确的 initial 回复标识优先于旧 targetedAt 字段，两者均兼容。映射每次由当前阶段数据重建，不查询当前粉丝资产，也不把上一次映射带入下一次运行。角色介绍与反应卡片允许长名称换行，原文不截断、不回写数据库。

验证：`npm --prefix frontend test -- --run src/simulationPersonaLabels.test.ts src/components/AudiencePreview.test.tsx` 15 项通过；完整 `npm --prefix frontend test -- --run --reporter=dot` 184 项通过（新增 8 项）。首次完整回归发现历史集成测试仍假定名字只出现一次，已改成确认人物介绍和反应均有名称；另一处旧粉丝弹窗测试偶发在可访问按钮出现前点击，改为等待按钮可见，没有修改业务逻辑。`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过，既有 Node localstorage 提醒不变。

隔离 Vite 5178／Playwright 使用上轮保存的真实人物与反应报告，补一条明确为测试构造的回应验证目标名称。真实样本、缺定义、同名、超长英文名四种场景在 1000／375／320 像素共 12 组复查通过，人物和回应名称一致、无横向溢出、无运行错误，键盘切换与展开依据可用。首次检查发现角色介绍的长名称溢出，扩展同一局部换行规则后重跑全部场景，截图已检查；临时页面和服务已清理。浏览器验证的是实际展示组件，不是启动正式后端的端到端验收；实时阶段更新和跨运行隔离另由组件测试覆盖。

本轮无模型调用、正式后端启动、抓取、业务数据写入、部署、提交或推送。后端未修改、未重跑，385 项为上一轮结果。需要用户决定：无。限制：此次只改善人物对应关系，不修复此前真实模型误解正文的问题；汇总正文仍是当次保存的生成文字，不做名称替换或改写历史。

下一次测试：同一模拟中部分角色调用失败、部分选择沉默、部分正常评论时，历史和实时页面是否清楚区分三种情况，而不是让创作者误以为沉默就是失败。拟修改代码：workflowStageViews、WorkflowOutputPanel 及历史页的阶段状态展示和相应测试，只使用已有结果与 stageErrors。下一项改进验收是保留成功反应、标明未完成角色，不把 no_comment／skip 计入失败，不把部分结果展示成全体完成；旧历史缺明细时如实显示现有信息，不添加付费重试或更改生命周期。

## 2026-10-03：同题示例复测未改善理解，撤回行为示例

本轮验收只关注上次新增示例的实际作用：同一三位角色、同一正文，是否不再索要无关报名入口、是否正确理解任务，以及触发引用是否连续。调用前逐项核对 case 和完整上下文与 connected 基线一致，模型与参数不改。实际发出三次 qwen-plus 独立反应请求，均返回并通过引用校验；耗时 4.93／6.77／4.13 秒，输入 8,341、输出 549 tokens。没有额外重试、重生成人物、讨论或汇总。

语义验收仍失败。行动派知道是自主练习，却继续追问报名／投递，并补出担心“隐藏 HC 通道”；方法派追问如何迁移到用户反馈摘要有意义，却把半小时练习说成“四步、每步十分钟”；收藏派引用恢复为连续原文，但仍将使用免费模型概括成“不依赖外部资源”。三项都公开评论，收藏短句与既有表达设定相同；单次常用短语相同不能证明复制，也不能用三项全过 JSON 宣称人物读懂了内容。

决定撤回上一轮“公开菜单／报名”行为教学示例，仅保留连续短原文的格式提醒。撤回的是本次候选片段，不回滚此前其他改动，不改角色、源案例或已保存资产。完整候选片段及提示哈希留在本地 review.json，避免以后重复试验或将失败写成改善。更新一项回归确认候选片段不再进入生产提示，原有“已回答的问题不重复追问”、允许不评论、完整上下文及严格引用校验继续保留。剩下的引用格式提示组合尚未实测，这轮不继续付费寻找通过样本。

真实命令：`backend/.venv/bin/python scripts/check_audience_reactions.py --audience-from data/evals/audience-partition-20261003/report.json --group-ids 1 5 4 --live --output data/evals/analysis-role-reactions-20261003-task-example`，结构完成退出 0，但人工结论 needs_revision；报告和复核在该 Git 忽略目录。撤回前 `cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_audience_reaction_check.py tests/test_audience_simulation_workflow.py` 32 项通过；撤回后完整 `.venv/bin/python -m pytest -q -o addopts=''` 385 项通过。`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_reactions.py`、`git diff --check` 通过。既有 LangChain 提醒不变。前端未改，176 项为此前结果；未启动正式后端、抓取、写正式数据、部署、提交或推送。需要用户决定：无。

下一次测试：轮换到模拟结果页的可读性。目前 ReactionListView 的卡片标题直接显示 Persona 加内部 ID，交流对象也显示 ID，不易与已选人物对应。拟修改代码：StageResultViews、ArtifactRenderers 与必要的阶段展示接线，使用本次运行冻结的角色名称映射，而非当前已编辑粉丝；补历史重开、缺少人物定义、同名角色和跨账号切换回归。下一项改进验收是创作者能看懂谁在说话、回应谁，旧历史缺名称时有稳定回退，不串入其他运行的名字，320／375 像素与键盘操作可用。该轮不继续调用模型或叠加受众提示。

## 2026-10-03：连接恢复，同题反应暴露人物习惯覆盖正文

本轮先排除上轮连接阻塞，再按原计划测试已有三位角色。无密钥 HEAD 请求沿用现有网络设置，DNS 成功，跟踪显示经过代理并完成 TLS／HTTP，0.78 秒收到 404；这只证明当前链路可达，不证明鉴权或还原旧 ConnectError 根因。没有代理环境变量，但跟踪确实存在代理连接，因此不能说没有代理。没有改网络配置，也未制作额外通用诊断系统。

随后用同一 QSheep 分区受众报告中的 1／5／4、同一“半小时 AI 产品小练习”正文，发出三次 qwen-plus 独立反应请求。已逐项核对与上轮失败报告的 case、角色上下文及提示哈希完全一致。三次均返回结构化输出，耗时 5.69／6.83／5.57 秒，合计输入 7,759、输出 630 tokens；两项通过，收藏派因触发原文拼接被拒，状态部分完成。没有重新生成受众、讨论、汇总或额外重试，未写正式模拟记录。

人工观察不能算效果通过：行动入口派在理解中已承认非招聘，却仍索要投递／报名链接，并建议外部表单平台；这说明人物习惯压过了正文给出的自助入口。方法拆解派追问可复用 checklist 和修改模式，与其需求有实际关联，但又把三处修改等内容概括为未定义的“检查三要素”，称“不追求产出”也不准确。收藏派使用与历史和表达设定相同的“收藏！！！”；常用短语相同不能单凭一次断言复制，但存在复读风险，其“无需外部资源”归纳也忽略了免费模型。三种反应不同不等于三种反应都读懂了正文。

本轮只在 REACTION_EXAMPLES 增加一组短教学示例：原来习惯找报名入口的角色，面对明确自助任务，应把需求落实为已给出的第一步，而不是强行要求报名；仍保留真正需要报名却缺链接时追问的合理性，也允许不公开评论。补充 triggerQuote 取连续短原文，不自行用省略号拼接。没有裁掉历史、改人物设定、改变模型配额、放宽校验或重写旧结果。新增两项回归锁定当前任务优先、保留全部上下文，以及拒绝拼接但允许原文本来有省略号。这一提示修改发生在实测之后，尚未验证效果，不宣称问题已解决。

实际推理命令：`backend/.venv/bin/python scripts/check_audience_reactions.py --audience-from data/evals/audience-partition-20261003/report.json --group-ids 1 5 4 --live --output data/evals/analysis-role-reactions-20261003-connected`，按部分完成退出 1。报告和人工 review.json 在该 Git 忽略目录。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_audience_reaction_check.py` 18 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 385 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_reactions.py`、`git diff --check` 通过。首次定向命令带了不存在的图测试文件名，已改为实际存在的检查测试并运行完整集。既有 LangChain 提醒不变。前端未修改、未重跑；未启动正式后端、抓取、部署、提交或推送。需要用户决定：无。

下一次测试：复用完全相同三位角色与正文，对新增教学示例做一次最多三请求的定向复测，重点看是否还索要无关报名入口、是否能正确概括当前任务、触发引用是否连续；不以 JSON 通过代替内容判断。拟修改代码：必要时补只读报告的人工对比摘要或针对新失败的回归，不继续堆叠人物限制。下一项改进验收是给出可对比的实际变化与剩余失败；不要求所有人认同或沉默，保留合理追问，未改善则如实记录并轮换到其他本地任务，不同轮盲目追加调用。

## 2026-10-03：已有受众同题检查入口，真实请求连接失败

本轮从上次已生成的受众出发，不重新生成或先改写人物。验收目标是保留角色定义及历史案例，对同一选题观察需求、判断和参与方式是否有差别，区分复述旧评论与针对新正文的反应。修改范围为 scripts/check_audience_reactions.py 和对应测试；增加 --audience-from 与显式 --group-ids，最多三位、只请求独立反应，不启整图、不创建数据库、不调用讨论或汇总。默认免费预览，检查角色 ID 唯一且属于有效结果，不从被拒绝的原始输出选角色。

新路径复用正式流程的角色定义校验、嵌套字段别名、历史案例选择、读者可见正文、反应 schema 和触发原文校验。报告保留来源文件哈希、选中 ID、原始人物定义、实际调用上下文、原始响应及核验结果；失败角色不自动重试，其他成功项仍保留，完成状态不等于语义通过。新增 requestAttempts、receivedStructuredResponses 与 billingStatus，终端不再把请求尝试数称为已付费数；旧 paidRequests 保留兼容，但只是尝试计数。首次预检遗漏 observedEpisodes 的嵌套别名，在发请求前报错；现已修正并补含历史案例测试，正式生产实现本来有 by_alias，没有修改它。

实际选择 QSheep 报告 audience-partition-20261003 中的 1／5／4：行动入口派、方法拆解派、安静收藏派，共享 AI 应用与职业发展兴趣。原样保留需求、表达习惯、每位两条案例，以及收藏派“高频复访”等已知问题；正文沿用“半小时 AI 产品小练习”，含明确步骤、免费模型、无需代码和不是招聘等条件。配置 qwen-plus，三次并行请求均约 5.4 秒后 ConnectError，没有拿到模型输出或用量，无法判断本次反应效果或确认计费；没有追加请求、改代理或绕过网络设置。

真实命令为 `backend/.venv/bin/python scripts/check_audience_reactions.py --audience-from data/evals/audience-partition-20261003/report.json --group-ids 1 5 4 --live --output data/evals/analysis-role-reactions-20261003-v2`，按失败约定退出 1。报告及人工失败记录位于该 Git 忽略目录；此前无后缀目录仅是模型调用前失败留下的空目录，未覆盖。移除 --live 和 --output 的同输入命令免费预检通过。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_audience_reaction_check.py` 定向 16 项通过，新增 9 项；完整 `.venv/bin/python -m pytest -q -o addopts=''` 383 项通过。`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_reactions.py`、`git diff --check` 通过。初次导入路径及 lint 的超长测试函数名已修正；既有 LangChain 提醒不变。

本轮未改生产提示、前端或正式数据，未启动正式后端、抓取、部署、提交或推送。前端 176 项是上一轮结果，本轮未重跑。需要用户决定：无。限制是当前只取得连接失败，人物差异、历史评论复述与无依据经历尚未获得新观察，不能把离线检查通过当成模型效果改善。

下一次测试：先用无密钥、无付费的连通性检查区分当前代理不可达与 API 主机连接问题，不反复提交推理请求；可达后才复用同一报告和同一正文，最多三次独立反应。拟修改代码：如有必要为检查脚本补不回显敏感地址／认证内容的连接阶段诊断，保持生产网络配置不变。下一项改进验收是取得可解释的连接证据，或得到可人工比较的三个反应；若仍受外部网络阻塞，记录原因后转到本地历史案例输入的稳定性回归，不盲目重跑付费验证。

## 2026-10-03：不同声音创建后的刷新恢复

本轮问题是“添加不同声音”把创建与列表刷新放在同一个失败分支里：角色已经入库但刷新失败时，界面仍让用户再次创建，还可能误显示原角色保存失败。验收要求是保存创建接口返回的全部角色与 ID，明确区分两类失败，刷新重试只读列表，关闭弹窗后可继续恢复，不丢原角色后续编辑。主要修改 SimulatedFansPage 及其组件测试，另补 CreatorDialog 的可选焦点返回引用和局部操作行样式；不改后端、模板或去重规则。

创建成功后弹窗展示已加入角色，刷新失败只提供“重试刷新”。关闭后入口变为“查看加入结果”，重新打开仍保留这次返回的角色，不重新加载模板或发送创建请求。刷新成功且原角色没有新编辑时打开第一位返回角色；若用户关闭弹窗后编辑了原角色，则保留编辑、不强行跳转。创建请求本身失败保留模板选择，错误与原角色保存状态分开；空响应也不会读取不存在的首个 ID。请求中禁止重复提交、改选和关闭。浏览器还发现异步加载模板时入口禁用会导致关闭后焦点丢失，现显式返回同一入口，其他弹窗保留原有默认行为。窄屏操作行允许整组按钮换行。

验证：`npm --prefix frontend test -- --run src/components/SimulatedFansPage.test.tsx` 28 项通过，新增 5 项回归；`npm --prefix frontend test -- --run` 最终完整 176 项通过；`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过，既有 Node localstorage 提醒不变。测试覆盖真实列表 hook、连续刷新失败、延迟恢复、只提交一次、关闭后重开、保留后续编辑、创建失败、空结果与焦点返回。隔离 Vite 5178／Playwright 在 1000／375／320 像素模拟两次 503 后恢复，每组仅 1 次创建 POST 和 4 次列表 GET（含初次加载），弹窗／页面无横向溢出，Escape 和焦点返回通过，截图已检查。首次浏览器检查发现焦点问题后修正并完整重跑；临时服务和页面已清理。

本轮没有模型调用、正式后端启动、抓取、业务数据写入、部署、提交或推送。后端未修改、未重跑，374 项仍是此前结果。需要用户决定：无。边界：创建回执保留在当前编辑器中，离开页面或刷新后靠数据库列表重新读取；本次不持久化前端恢复状态。网络中断而未收到创建响应的情况不能确定是否入库，仍依赖既有服务端来源／模板去重，不宣称实现网络层的严格一次提交。

下一次测试：轮换回实际模拟质量，使用已保存受众分析报告中的三位有效角色，对同一选题检查是否体现不同需求与判断，还是复述历史评论／只换语气。拟修改代码：只读 check_audience_reactions 检查入口，必要时增加从既有分析报告构建角色快照的路径及离线回归，避免重新生成受众。下一项改进验收是输入完整保留这三位原始人物设定、同题可对比并分别记录参与行为与具体理由；先免费验证输入，再按明确目标最多三次独立反应调用，不启动整图或写正式模拟记录，不将人物差异自动判定为真实受众代表性。

## 2026-10-03：账号画像缺字段与窄屏回看

本轮承接上次真实画像的页面验收，不再付费重跑。问题是：概要可能被引用校验过滤，但关键词和优势仍有效；空画像文案却将原因暗示为笔记不足，仅有优势或近期变化时也可能留下空白介绍卡。验收要求是保留有效结果和原始引用，不引导无依据的补抓，不改历史快照，且在 320／375 像素正常查看依据和笔记详情。修改范围为 AccountPortraitView、其回归及 ArtifactRenderers 的文案断言，样式仅作用于账号画像与表现卡片。

现在介绍卡只在有概要、关键词或鼓励语时出现；单独的优势和有效近期变化也被识别为可展示结果，缺失栏目不占位。完全没有画像时提示“本次暂无可展示的账号画像，已保留的内容归纳与笔记数据不受影响”，不声称补充笔记就能解决。时期可比较这一要求保留。实际 QSheep 画像在窄屏下原本没有横向溢出，但长链接引用压力样本把 320 像素页面撑到了 2886 像素；已用可收缩的网格和换行修正，原文没有截断或改写。

验证：`npm --prefix frontend test -- --run src/components/AccountPortraitView.test.tsx` 9 项通过；`npm --prefix frontend test -- --run` 最终完整 171 项通过，新增 5 项画像测试。首次完整回归暴露旧文案断言，另有两处粉丝测试在父层禁用状态尚未解除时点击；已更新文案断言，让测试等待按钮实际可用，没有放宽保存状态断言或修改粉丝生产代码。`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。既有 Node localstorage 提醒不变。

浏览器使用隔离 Vite 5178、实际组件和 account-profile-6000-20261003/report.json，检查真实结果、长引用、仅有优势、空画像、仅有近期变化共 5 类数据，在 1000／375／320 像素的 15 组场景全部通过。逐个展开依据、打开笔记、Escape 关闭和焦点返回均检查，页面及弹窗无横向溢出、无运行错误，窄屏截图已复核。最初测试路由回调签名写错，修正后完整重跑；这是测试装置错误，不是产品接口错误。临时页面和服务已清理。本轮未调用模型、启动正式后端、抓取、写业务数据、部署、提交或推送；后端未修改，374 项是上一轮结果而非本轮重跑。需要用户决定：无。

限制：本轮只是已有结果的展示修复，不会恢复被过滤的概要，也不代表短引用提示和画像内容质量已经验收。下一次测试：模拟“添加不同声音”已经创建成功、随后列表刷新失败，检查能否恢复而不重复创建或误报保存失败。拟修改代码：SimulatedFansPage 的创建结果与刷新恢复逻辑及组件测试，复用现有保存后刷新机制。下一项改进验收是保留服务端返回的新角色 ID，明确显示已创建但列表暂未刷新，只重试读取；刷新成功后可查看新增角色，不覆盖原角色或用户编辑。

## 2026-10-03：画像完整返回，发现引用拼接导致首屏信息缺失

本轮使用相同 QSheep 最近 10 篇，仅一次 `qwen-plus` 请求检验 6000 输出额度；与上轮报告的 context、输入及提示哈希一致。HTTP 200、finishReason=stop，74.37 秒，输入 8,289 tokens、输出 3,310 tokens，结构完整且通过生产画像校验。本次未截断，但实际输出低于旧 3400 额度，不能由一次随机生成独立证明预算调整的因果效果。没有继续增大额度或改变超时。

人工复核的具体收益：“把抽象理论转为日常行动”这条优势及声音表达、写作、健身的原文例子相互对应，并非空泛夸奖。主要问题则是模型在 quote 中用省略号拼接原文，另有删掉原空格：生成的概要、鼓励语、2 条主要方向与读者价值全部被过滤；4 个关键词保留 3 个，3 条优势保留 2 条。材料充分却丢失首屏结论，不能解释成需要再导入更多笔记。保留下来的关键词仍偏主题／经历，“LSE人类学在读”把历史经历当成当前状态；部分复杂结论仅有局部依据。旧 contrast 还把点赞／收藏／分享说成愿意付费，并凭仅标签的毕业视频判断信息价值和形式适配，语义审阅结论仍为需要修改。

本轮最小提示修正只针对明确的引用格式问题：建议抄 10～40 字连续片段，保留空格和标点，多处依据分开为 evidence，不自行用省略号拼接；给出一组短正反例，并允许原文已有的省略号。statement 仍自然归纳，画像语气仍积极；未放宽现有校验、自动修补引用或覆盖历史。新增两项回归锁定提示边界、拒绝拼接及允许原始省略号。提示是在真实调用之后修改，尚未再次实测，不能宣称首屏缺失已解决。其他语义问题保留待办，不在本轮继续堆叠提示。

真实命令：`backend/.venv/bin/python scripts/check_account_profile.py data/xhs-captures/659db724-b474-4614-b1de-4530b6291124/raw --live --output data/evals/account-profile-6000-20261003`，退出 0；原报告和人工 review.json 在该 Git 忽略目录。修改前账号相关定向回归 46 项通过；修改后 `cd backend && .venv/bin/python -m pytest -q -o addopts=''` 完整 374 项通过，`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_account_profile.py scripts/account_profile_diagnostics.py`、`git diff --check` 通过。既有 LangChain 提醒不变。本轮没有第二次模型调用、正式后端启动、抓取、业务数据写入、部署、提交或推送，前端未改。需要用户决定：无。

下一次测试：轮换到账号结果页，用本次实际返回的画像和快照检查没有概要但有关键词／优势、长段特点、缺失方向及窄屏回看依据的体验，不继续付费重跑。拟修改代码：AccountPortraitView 与组件测试，必要时调整卡片样式和空态文案，不把引用失败说成笔记不足。下一项改进验收是保留所有有效优势和依据，首屏层次清楚，320／375 像素不横向溢出，缺字段不误导用户补抓或覆盖旧结果。短引用提示的模型效果及旧 contrast 的语义问题待后续明确验证，不以此次工程通过代替内容验收。

## 2026-10-03：确认画像输出截断，调整单阶段预算

本轮验收是用一次带诊断的真实画像请求，把上轮不明 ValidationError 缩小到有证据的原因，再按实际问题做最小修正。调用前免费重建 QSheep 最近 10 条输入，与旧 account-profile-20261003 报告核对：context、输入哈希及提示哈希均相同。唯一真实请求为 `qwen-plus`，76.87 秒，HTTP 200，输入 8,289 tokens、输出正好 3,400 tokens，finishReason=length。记录器未裁剪正文；原文在 contrast.takeaways 字符串中结束，外层 JSON 尚未闭合。因此本次失败确认是输出长度限制下的不完整 JSON，不是网络或账号素材为空；上一轮缺原响应，不能声称已还原它的细节。

最小修正：PROFILE 的共享输出预算从 3400 调整为 6000，仅影响账号画像操作，其他操作预算不变；提示词、schema、温度、超时和工作流顺序不改。Qwen PROFILE 收到 length 时明确报“账号画像输出达到长度上限，未取得完整结果”，即使片段恰好可解析也不当完整结果接受；不拼补 JSON、不自动重试。检查适配器将该分支记作 output_length，之后报告同时记录 requestedMaxTokens，便于区分不同预算。新增两项模型回归，更新诊断测试中的阶段及预算断言。已有历史与用户资产不改写。

实际命令：`backend/.venv/bin/python scripts/check_account_profile.py data/xhs-captures/659db724-b474-4614-b1de-4530b6291124/raw --live --output data/evals/account-profile-diagnostic-20261003`，这是修正前的唯一真实调用，按失败约定退出 1；报告及人工复核均在此 Git 忽略目录。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_account_profile_check.py tests/test_model_calls.py tests/test_account_diagnosis_evidence.py tests/test_account_langgraph_workflow.py` 46 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 372 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_account_profile.py scripts/account_profile_diagnostics.py`、`git diff --check` 通过。既有 LangChain 提醒不变。没有第二次真实调用、正式后端启动、业务数据写入、抓取、部署、提交或推送；前端未改。需要用户决定：无。

限制：6000 是有上限的容量修正，尚未通过真实请求验证，不保证每次完整；已截断的输出不作为画像内容质量验收。现有 90 秒客户端超时保持原值，是否足够须看后续实际响应，不能先把本次错误说成超时。

下一次测试：以同一组笔记、相同提示做一次 6000 额度的检查，核对结束原因、耗时、完整 schema 和关键词／优势／鼓励在引用过滤前后的数量。拟修改代码：仅针对新证据补最小回归；若输出完整，优先人工审阅“具体做对了什么”和建议是否自洽，不再追加容量或提示改动。下一项改进验收是确认长度问题是否解除并取得可审阅画像；若仍失败，记录明确原因并停止同轮追加调用，不为了通过而重试。未确认的新容量效果和画像语义质量仍留在待办中。

## 2026-10-03：账号画像检查的响应诊断

本轮承接上次只有 ValidationError 的失败记录。验收是用假 HTTP 响应区分接口状态错误、外层响应非 JSON、内容提取失败、模型 JSON 解析和顶层字段校验；保留结束原因、用量及解析前正文，同时不记录请求头、URL、错误响应正文或异常消息，也不因失败自动重试。仅修改只读检查脚本、新增 account_profile_diagnostics.py 及回归测试；生产 ModelCallService 只增加一个可覆盖的 Qwen client 工厂，默认仍是原有 90 秒 HTTP 客户端，没有开启生产响应日志。

检查脚本现在使用 DiagnosticProfileCalls，复用生产请求构建、文本提取及 JSON／字段校验，固定只支持 Qwen 的 PROFILE。报告新增 responseDiagnostic：阶段、已知 HTTP 状态、实际模型、三项数值 token 用量、首个候选的 finishReason，以及最多 100,000 字符的解析前正文和裁剪标记。finishReason=length 只表示接口报告长度限制，不直接把所有格式失败判为截断。错误状态只留状态码，非 JSON HTTP 正文不落盘；配置中的 Qwen／Anthropic 密钥和 Bearer 字符串在报告中脱敏，正文先脱敏再裁剪，避免边界泄漏。终端仍只输出报告位置与执行状态，原文仅进入本地报告。其他未识别的敏感源内容不会自动去除，报告仍必须放 Git 忽略目录，不公开分享。

验证：新增 12 项测试覆盖普通文本、文本块、function_call 参数、截断／无效 JSON、结构不符、缺失内容、HTML 响应、429、网络超时、脱敏边界、终端安全摘要和报告落盘；每种 HTTP 场景确认只有一次请求，并核对原有模型、配额、temperature 和 response_format 不变。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_account_profile_check.py tests/test_model_calls.py` 34 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 370 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_account_profile.py scripts/account_profile_diagnostics.py` 和 `git diff --check` 通过。初次 lint 的导入排序和两处超长行已修复。既有 LangChain 提醒不变；前端未修改。没有真实模型调用、正式后端启动、数据库写入、抓取、部署、提交或推送。需要用户决定：无。

已知限制：旧 account-profile-20261003 报告没有原响应，无法补回或据此确认原因；本轮只是用假响应验证诊断可用。原始模型正文即使能保存，也不表示解析成功或画像质量通过；生产历史暂不新增该诊断字段。

下一次测试：对上轮同一组已保存笔记做一次带诊断的 Qwen 画像验证，先核对输入与提示哈希；仍失败时按实际状态／结束原因定位，不盲目增大配额或追加请求，成功则审阅关键词、优势与建议是否具体自洽。拟修改代码：只针对已确认问题补检查脚本或模型参数的定向回归；若没有明确代码问题，就保留报告而不制造改动。下一项改进验收是把上轮无法解释的失败缩小到有证据的阶段，并在可解析时完成账号画像的内容审阅；保持一次请求、不写正式资产，未取得依据则明确保留未知。

## 2026-10-03：账号画像只读检查入口与一次失败记录

本轮轮换到“了解我的账号”，验收关注关键词、具体优势与鼓励是否贴合笔记、改进建议是否自洽，而非只检查 JSON。新增 `scripts/check_account_profile.py`，从已保存 MediaCrawler 数据经过生产导入归一化、最近 10 条范围及派生文本构建输入；不连接数据库或启动图，不生成痛点／选题。默认只预览范围；显式 live 强制 Qwen、仅一次调用、不重试，拒绝覆盖已有报告目录。报告保存输入快照、模型上下文、结构化原始输出（若已成功解析）、生产校验后的结果、保留前后结论数量及人工复核项，自动完成始终不等于语义验收。

为避免脚本与真实诊断采用不同输入，将现有画像阶段的文本拼接抽为 account_diagnosis_evidence.profile_stage_input，并由图节点和脚本共同调用。对有／无可比较时期的输入逐字回归确认与旧实现相同；未更改 prompt、token 配额、图顺序、数据保存或前端展示。新增 7 项测试覆盖免费预览、原快照不变、单次画像调用、过滤前后结果保留、空画像、格式失败、错误脱敏及拒绝覆盖。

真实验证仅一次：已保存 QSheep 最近 10 篇（可用 30 篇），配置 `qwen-plus`，78.95 秒后调用层抛出 ValidationError，未得到结构化输出或模型用量。检查报告只有阶段和异常类型，不能区分 HTTP 错误、内容校验或输出截断；当前画像配额虽为 3400 tokens，不能凭此认定原因。没有追加调用或改 prompt，本轮画像内容质量尚未审阅。报告与失败复核位于 Git 忽略的 `data/evals/account-profile-20261003/`；没有写正式分析或选题。导出转换中的 importedAt 为本次转换时间，现有 observations.sourceFetchedAt 沿用它，不应将它读成真实抓取时间。

验证命令：`backend/.venv/bin/python scripts/check_account_profile.py data/xhs-captures/659db724-b474-4614-b1de-4530b6291124/raw` 免费预览；加 `--live --output data/evals/account-profile-20261003` 为上述唯一请求，退出 1。`cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_account_profile_check.py tests/test_account_diagnosis_evidence.py` 12 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 358 项通过，包括现有图回归。`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_account_profile.py`、`git diff --check` 通过。首次定向命令使用了不存在的 test_account_diagnosis_graph.py，已更正并完整重跑；初次 lint 的未用导入和超长测试行已修复。既有 LangChain 弃用提醒不变。前端未修改、未重跑浏览器；未启动正式后端、抓取、部署、提交或推送。需要用户决定：无。

下一次测试：用假 HTTP 响应覆盖接口错误、合法 JSON、结构不符及 finish_reason=length 的截断，确保错误诊断能区分阶段、保留允许记录的响应信息且不回显密钥。拟修改代码：优先在只读账号检查脚本增加诊断适配器及测试，不为了日志大改生产模型接口。下一项改进验收是即使 JSON 解析失败，也能在被忽略的本地报告里检查状态码、结束原因、用量和模型正文，终端仅输出安全摘要；不重复付费、不向报告复制请求头或环境变量。诊断验证完成前不追加同类真实请求；账号画像语义审阅仍是待完成目标。

## 2026-10-03：分区输入的一次真实受众复核

本轮验收是检查作者／读者分区后的真实人物输出：宽兴趣可跨笔记复用，同兴趣下需求与判断有区别，引用支持需求，不将模拟性格写成已观测行为。使用已有 QSheep 原始导出，最近 10 篇／85 条评论，分为 78 条候选和 7 条作者背景；与旧 audience-roles 报告逐条核对，标题、正文及合并分区后的评论完全相同。范围 asOf 时间变化，不是完全同输入的控制实验。

仅一次 `qwen-plus` 调用，63.09 秒，输入 14,893 tokens、输出 2,772 tokens。生成 8 位，6 位通过自动校验；本次没有引用作者回复，但不能由一次输出断言分区带来了稳定改善。两位因自行附加省略号而被拒，保留原始输出，不剪掉标点后放行。人工复核发现：找入口、核对条件、拆解方法有可理解的需求差别，同属 AI应用／职业发展的几位不是只换语气；但“安静收藏派”的“极少评论但高频复访”没有行为依据，若干简介仍绑定具体术语和学校，表达习惯复述原评论。被拒的“价值确认派”还把雅思写作提分评论当成人文能力获行业认可的依据，格式修正也不能解决这一错配。结论为仍需修改，不是人物质量全部通过；没有做同题模拟或继续重试。

代码改进仅在检查脚本及测试：新增 reviewSummary，分别列出生成数、校验通过／拒绝数、拒绝错误码和五项人物人工检查点；semanticStatus 始终初始为 not_reviewed，即使自动状态 completed 也不冒充语义验收。模型调用／格式校验失败时未知计数使用 null，不以 0 冒充已经检查。新增两个测试，包含“配色需求引用询问第一步”的机械校验通过反例；补充分区字段与部分成功断言。生产提示词、校验规则和正式资产均未修改。此次请求在新增摘要前已发出，原 report.json 不补写；人工结论单独保存 review.json，两者位于 Git 忽略的 `data/evals/audience-partition-20261003/`。

实际命令：`backend/.venv/bin/python scripts/check_audience_analysis.py data/xhs-captures/659db724-b474-4614-b1de-4530b6291124/raw` 免费预览；同命令加 `--live --output data/evals/audience-partition-20261003` 为上述唯一请求，因部分成功按脚本约定退出 1。`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 完整 351 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_analysis.py`、`git diff --check` 通过。既有 LangChain 弃用提醒不变。前端未改，166 项为上轮记录，未再跑浏览器。没有启动正式后端、抓取、写业务数据库、部署、提交或推送。需要用户决定：无。

下一次测试：轮换到账号分析，检查关键词、具体优势与改进建议是否对应原笔记，而非通用夸奖或互相矛盾。拟新增只读账号画像检查脚本及假响应测试，复用现有样本归一化、范围选择和模型操作；默认免费预览，显式 live 最多一次，不启动服务或创建正式运行。下一项改进验收是能完整保存输入、输出、模型信息和人工复核项，调用失败可检查且不自动重试；用真实输出定位一项最影响“了解我的账号”的问题后，再决定最小产品改动，不直接扩大重写诊断流程。受众的省略号引用与行为频率问题仍保留为后续生成质量任务。

## 2026-10-03：保存成功与刷新失败分开恢复

本轮承接粉丝编辑保护，解决更新成功后列表刷新失败被误报为保存失败的问题。进一步发现实际 useSimulatedFans 会吞掉刷新异常，编辑器还可能误判刷新成功并切换。验收是保留服务器确认的内容和版本、明确反馈已保存、恢复时仅 GET 列表而不重复 PATCH，刷新成功后再完成待定切换；后续新编辑不被刷新覆盖。

已将 FanEditor 的写入与刷新结果分开，增加“上次修改已保存，列表暂未刷新”和仅刷新恢复入口。成功写入后即更新本地版本，失败刷新不退回旧草稿；用户继续编辑时独立显示后续修改未保存。归档同样保留已确认状态。列表恢复前不直接切换到旧列表中的角色，不再提供含义错误的放弃已保存修改按钮；仍可关闭弹窗继续编辑。useSimulatedFans 新增 refreshAfterSave，显式刷新会传播错误，被新请求替代也不冒充成功；自动加载仍使用原有捕获错误的路径，避免未处理拒绝。App 已接入这一严格刷新入口。修改范围为该组件、hook、App 一处接线、对应测试及弹窗按钮不拆字样式；后端与历史数据不变。

验证命令：`npm --prefix frontend test -- --run src/components/SimulatedFansPage.test.tsx src/hooks/useSimulatedFans.test.tsx` 29 项通过；`npm --prefix frontend test -- --run` 完整 166 项通过（本轮新增 6 项），`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。测试包含真实 hook 与页面组合、连续刷新失败、延迟恢复、保留后续编辑、使用已确认版本再次保存、归档与请求被替代。隔离 Vite／Playwright 检查 1000／375／320 像素弹窗、Escape、焦点返回和重新打开保存内容：模拟两次 503 后恢复，共 4 次 GET（含初次加载）和 1 次 PATCH，无重复写入，截图已检查。临时页面与服务已清理；既有 Node localstorage 警告不变。本轮未调用模型、启动正式后端、抓取、部署、提交或推送。需要用户决定：无。

边界：全局页面／账号切换及浏览器刷新仍不保护未保存编辑；“添加不同声音”的创建成功后刷新失败尚未纳入这次恢复界面。320 像素编辑页底部普通保存操作行仍较拥挤，弹窗已无溢出，后续统一整理操作行。

下一次测试：轮换回受众生成质量，用已保存 QSheep 最近 10 篇样本检验作者／读者分区后的实际人物输出，关注宽兴趣、具体需求、同兴趣不同判断以及引用与需求语义是否匹配；最多一次有目标 Qwen 调用，不写正式资产。拟修改代码：必要时补 check_audience_analysis 的分区上下文与人工复核报告回归，不先堆叠提示词。下一项改进及验收是让检查报告区分结构通过、作者误引拒绝和人物语义问题，真实观察失败也保留，不把引用逐字匹配当成角色成立；记录模型、调用数、样本和剩余缺陷，再决定生成侧最小修改。

## 2026-10-03：模拟粉丝未保存切换保护

本轮解决粉丝列表切换会丢失正在编辑内容的问题。验收要求是未修改时直接切换，修改后可以继续编辑、明确放弃或保存后切换；保存中不重复提交，冲突和失败不离开当前角色，非法字段不能通过弹窗绕过校验。修改范围为 SimulatedFansPage、其组件测试和弹窗按钮样式，沿用现有 CreatorDialog，不改变 API、数据库或角色生成规则。

列表切换现在由编辑器检查未保存状态；名称、兴趣和需求等编辑均受保护。保存并切换携带当前 expectedUpdatedAt，等待更新及列表刷新完成；期间禁用输入、列表和弹窗操作。取消或 Escape 保留输入，明确放弃才卸载当前编辑器。新增 7 项回归覆盖三类字段、未修改／当前角色、延迟保存、冲突和无效兴趣。浏览器检查还发现多行字段的可访问名称包含已有正文，已补齐明确的 aria-label。

验证：`npm --prefix frontend test -- --run` 160 项通过；`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。隔离 Vite 页面与 Playwright 使用两个临时角色和模拟 409 响应，在 1000／375／320 像素检查弹窗、按钮可见性、横向溢出、Escape、焦点返回、冲突保留输入和明确放弃；结果通过并检查截图。临时页面及服务已清理，正式后端未启动。本轮无真实模型调用、抓取、业务数据修改、部署、提交或推送；后端未改，349 项为上轮结果而非本轮重跑。既有 Node localstorage 参数警告仍在。需要用户决定：无。

已知边界：本次仅保护粉丝列表内部切换，不覆盖离开页面、切换账号或浏览器刷新。另发现已有保存逻辑把更新与刷新放在同一异常处理里：数据库更新成功但列表刷新失败时，会笼统显示保存失败；本轮未声称修复这一分支。

下一次测试：模拟更新成功、随后列表刷新失败，确认不会把已保存内容误报为未保存，也不会因重试重复 PATCH。拟修改代码：FanEditor 的保存结果与列表刷新反馈、对应组件测试。下一项改进验收是明确区分写入失败与列表暂未刷新，保留已保存版本及输入，提供仅重试刷新的恢复动作，待刷新成功再完成待定切换；继续不覆盖旧历史或已编辑角色。

## 2026-10-03：作者背景与读者候选分区

本轮问题是模型虽看到 sourceRole，仍会从混合评论列表取作者回复作受众证据。验收要求是在输入结构中分区而不丢背景，不扩大原有截取预算，不变更引用 ID；新旧布局的作者误引均拒绝，非作者／未知评论与部分成功保存照常。已修改 audience_context：先按原顺序截取每篇前 50 条、分配稳定 ID，再把已确认作者回复放入 authorReplies，非作者及未知评论留在 comments。两区合计仍最多 50 条，每条仍最多 1000 字，笔记仍最多 100 篇；不把未知角色当作者删掉，也不额外补采样。sentComments 保持两区合计，新增 sentCandidateComments 和 commentLayout，避免前端总评论数变义。

作者解释仍随完整笔记上下文发送，提示说明它可作理解背景但不可当读者需求引用。evidence_issues 同时识别新 authorReplies 与旧 comments 中的 author 标记，保留原错误码；把仅出现在作者回复中的文字改称 note 来源同样无法通过正文匹配。正常与未知评论仍可提取历史读者案例，作者回复不能进入；全是作者回复时保留背景，允许基于笔记正文推断潜在需求。原始快照、旧粉丝、旧分析与报告不改写，上轮撤回的教学示例没有恢复。本轮没有付费模型调用，不能声称已解决模型的语义错配。

验证：定向命令 `cd backend && .venv/bin/python -m pytest -q -o addopts='' tests/test_xhs_comment_roles.py tests/test_audience_evidence.py tests/test_audience_prototypes.py tests/test_audience_analysis_check.py tests/test_audience_diagnostics.py` 84 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 349 项通过（本轮新增 6 项）。`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_analysis.py`、`git diff --check` 通过，仍有既有 LangChain 弃用提醒。只读重建 QSheep 保存样本并与旧报告逐条对比，笔记标题／正文、评论 ID／内容／时间／角色完全一致：仍为最近 10 篇、85 条，分成 78 条候选和 7 条作者背景，未知为 0。前端未改，沿用 153 项记录；无抓取、正式后端启动、部署、提交、推送或业务数据写入。需要用户决定：无。

下一次测试：轮换到模拟粉丝编辑体验，检查编辑名称／兴趣／需求后切换角色是否丢失未保存内容，以及保存冲突、失败时是否仍留在当前编辑器。拟修改代码：SimulatedFansPage／FanEditor 的角色切换保护及组件测试，使用现有确认弹窗，不引入自动覆盖。下一项改进验收是未保存时可取消切换继续编辑，明确放弃才离开，保存失败不跳走，已保存状态不额外打扰；浏览器检查键盘和窄屏。分区输入的真实模型效果仍待后续有明确目标时验证，不在每轮自动调用。

## 2026-10-03：语义对齐示例试验未通过，已撤回

本轮尝试用三个简短正反示例区分需求证据与模拟性格：无关报名评论不能支持视觉需求，留存意愿不能证明已动手，作者经历不能移给读者；同时保持鲜明人物，不要求满篇不确定措辞。验收要求是同输入下一次输出不误引作者、需求有对应依据、判断习惯不变成虚构生活。新增检查脚本 `--context-from`，可从既有报告完整重放输入，保留 scope 时间及采样信息，不重新选样或改动基线文件；默认仍免费预览，live 仅一次 Qwen，不覆盖报告、不访问数据库。

执行 `backend/.venv/bin/python scripts/check_audience_analysis.py --context-from data/evals/audience-roles-20261003/report.json --live --output data/evals/audience-alignment-20261003`，输入哈希与基线完全相同，仅提示哈希变化。`qwen-plus` 一次调用耗时 49.4 秒，输入 15,052 tokens、输出 2,150 tokens。生成 8 位，但两位引用作者回复，被现有校验拒绝，剩余 6 位有效；还出现“犹豫超过 3 分钟会焦虑”、高频点赞、反复截图转发等不理想表述。虽然没有复现此前招聘评论配审美需求的特定错误，整体仍未达到验收。一次随机输出不能判断改动因果，但没有证据支持保留候选，已只撤回本轮生产示例改动，此前未提交工作全部保留；生产提示哈希核对恢复到上轮基线。没有追加模型请求。

保留成果是可复用的精确输入重放及 4 项回归测试（原样重放／不改基线、三类残缺报告拒绝）。失败的候选提示、输出及 review.json 保存在 Git 忽略的 `data/evals/audience-alignment-20261003/`，归档提示哈希与该次请求一致。最终验证：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 343 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_analysis.py`、`git diff --check` 通过。既有 LangChain 弃用提醒仍在，前端未改（上轮 153 项通过）。没有写正式分析或资产，未启动正式后端、抓取、部署、提交或推送。需要用户决定：无。

下一次测试：输入结构能否把作者解释背景与可引用读者评论区分，同时保留全局信息；覆盖作者／非作者／未知、截取上限、原引用错误码及旧上下文。拟修改代码：audience_context 与 evidence_issues，用独立背景字段保留作者回复，不让它与读者候选混在同一列表，补来源计数和模拟案例提取回归；不删除作者信息、不减少未知读者、不改变历史快照。下一项改进验收是作者背景仍可供理解，但误引仍被拒绝，正常及未知评论的引用和部分成功链路不变。先用本地测试验证，不因定时运行继续尝试更多同类付费提示组合；语义错配仍需后续改进。

## 2026-10-03：受众角色的依据回看

本轮问题是受众卡片只显示引用与原始 ID，创作者难以判断评论和角色是否相关。验收要求：展开后读取当次分析快照，显示被引评论全文并能打开原笔记；同一运行共享详情请求；切换运行／账号不沿用旧数据；失败可重试，旧记录缺快照或重复 ID 不误指向当前素材。新增 `AudienceGroups.tsx` 将卡片及懒加载详情从页面拆出，前端接入已有 `/api/audience-analyses/{id}`，类型允许详情携带 notes；未新增后端接口或改数据库。

已完成：有完整快照时直接使用，否则展开依据后才请求一次详情。引用评论旁展示当次评论原文；笔记标题卡复用笔记浏览器，可打开全文和已保存评论，不查当前素材、不拉封面或图片。失败保留历史引用并提供重试；无快照或来源 ID 不唯一时说明缺失，不随意选一个。运行／工作区切换重置展开与详情状态，旧请求返回被忽略，并验证接口返回的运行与工作区归属；页面也过滤切换期间残留的其他工作区历史。兼容后端旧快照的 snapshot-note / snapshot-comment 序号 ID，无引用的旧分组保持原展示。自动保存全部有效角色的规则未改。

验证：`npm --prefix frontend test -- --run` 153 项通过（新增 7 项）；`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。测试覆盖懒加载共享、原文回看、失败重试、切换中迟到响应、错误工作区、已有／缺失快照、重复评论和旧序号引用。隔离浏览器验证使用 frontend 目录的 `npm exec -- vite --host 127.0.0.1 --port 5178 --strictPort` 加 Python Playwright 路由响应，不启动后端：模拟一次 500 后重试成功，1000／375／320 像素无横向溢出，长评论、笔记弹窗、Escape 与焦点返回、重开不重复请求均通过，并检查截图。临时页面与服务已清理。此验证不等于生产端到端或模型效果验收；已有 Node localstorage 警告仍在。后端未改，沿用上轮 339 项通过记录；没有模型调用、抓取、正式服务启动、部署、提交或推送。需要用户决定：无。

下一次测试：回到生成质量，使用上轮报告中“招聘评论支持审美需求”“收藏被扩展为下载复现”“LSE 课业场景”三个反例，检查教学示例是否教会了错误的依据归因。拟修改代码：audience_examples.py 的简短正反对照和对应提示构建测试，必要时给检查报告补语义复核清单，不用关键词匹配冒充语义验证。下一项新改进及验收：一次同输入 Qwen 对照中，人物保持宽兴趣与具体判断，但引用能支持核心需求；可模拟的判断习惯不写成已发生的个人经历。最多一次有目的验证，仍失败则记录，不能以结构通过声称改善。当前人物语义错配仍未解决，依据回看只是让问题可检查。

## 2026-10-03：一次带来源角色的真实受众检查

本轮验收分两部分：作者回复不能被用作读者需求证据；生成 6～8 位宽兴趣、需求及判断有具体差异的简短人物。新增 `scripts/check_audience_analysis.py`，复用生产的离线转换、导入规范化、最近 10 篇范围和受众上下文；默认免费预览，显式 live 才调用一次 Qwen，不自动重试、不打开数据库。报告保留输入、结构化原始输出、校验结果、模型与 token 用量、耗时及提示／输入哈希，已有报告目录拒绝覆盖。格式校验失败仍保留已收到的结构化输出；若调用在模型服务的 JSON 解析层失败，则仅记录阶段与错误类型，尚不能恢复原始响应文本，错误消息不回显可能含凭证的内容。

真实验证使用已有 QSheep 抓取目录 `data/xhs-captures/659db724-b474-4614-b1de-4530b6291124/raw`，最近 10 篇、85 条评论，其中 7 条作者、78 条非作者、0 条身份未知。仅一次 `qwen-plus` 请求，49.85 秒，输入 14,720 tokens、输出 2,172 tokens。模型给出 8 位角色，全部通过结构／来源／逐字引用检查，没有引用作者回复。人物质量未通过人工验收：“审美启蒙派”引用的是“有没有产品实习的 hc”这一招聘问题，不能支持视觉风格需求；“工具实操派”从收藏评论扩展到会下载并复现，“陪伴共鸣派”加入 LSE 课业压力和截图保存的具体情境。立即找入口与先核对门槛的两位角色有实际需求差异，但仍有角色绑定单篇帖子。这说明来源标记解决了一个明确问题，不能替代语义支持判断，也不能宣称人物效果已稳定改善。保留失败例子，不追加付费重试或临时堆叠提示词。

实际命令：`backend/.venv/bin/python scripts/check_audience_analysis.py data/xhs-captures/659db724-b474-4614-b1de-4530b6291124/raw` 免费预览；同命令加 `--live --output data/evals/audience-roles-20261003` 实测一次。原始报告及人工 review.json 在该 Git 忽略目录，不写正式分析／粉丝。新增 5 项脚本测试，覆盖真实范围与来源逻辑、免费默认、单次调用、部分有效结果、失败脱敏／输出保留及拒绝覆盖已有报告（部分测试合并多项断言）。`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 339 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_analysis.py scripts/check_audience_reactions.py scripts/xhs_mediacrawler_fixture.py`、`git diff --check` 通过。保留既有 LangChain 弃用提醒；前端未改，未启动正式后端、抓取、部署、提交或推送。需要用户决定：无。

下一次测试：受众卡片的依据能否回看本次运行的笔记标题、正文片段与被引用评论，检查切换分析／账号、旧结果无快照、详情请求失败。拟修改代码：AudienceAnalysisPage 的依据展开区域，必要时按需读取单次受众分析详情，复用笔记浏览组件并补缓存隔离与组件测试。下一项新改进及验收：创作者不必理解 noteId，就能看出“这句评论是否支持这个角色”；不使用当前素材替换历史依据，不凭关键词硬判语义正确，也不改自动保存全部有效角色的产品规则。后续再针对本轮错配样例改进生成与校验，不以自动结构测试充当语义验收。

## 2026-10-03：作者评论不再作为读者需求证据

本轮验收是确认已有原始数据是否有可靠作者标记，贯通导入与受众输入，缺信息不凭文风推断，误引作者回复时保留其他有效角色。初查没有明文 user_id，进一步查当前 MediaCrawler 源码发现笔记与评论使用同一 SHA-256 截断方法保存 creator_hash；丢失发生在主平台转换中。只读比较：QSheep 20 篇／137 条评论里有 7 条作者评论，_tt 4 篇／26 条里有 2 条，近期 30 篇／198 条里有 14 条。数字对应保存样本，不代表当前线上总量。另一个旧 capture 有 5 行不完整 JSONL，本轮未修复，也未把它当完整验证样本。

已完成：离线转换和导入保留笔记、评论的 authorHash；新增 xhs_comment_roles.py 只比较合法 16 位匿名哈希；audience_context 给模型发送 author/non_author/unknown 标记及采样计数，不发送哈希。作者回复只作解释背景，不允许成为读者需求引用或读者历史配对案例；验证层拒绝误引的角色，其他有效角色仍部分成功保存。非作者不等于真实粉丝，未知保持未知。旧档案、粉丝和运行不回填、不覆盖；不新增数据库表，不改模拟方法版本，来源判定方法单独记入 sampling。

验证命令：在 backend 下运行 `.venv/bin/python -m pytest -q -o addopts='' tests/test_xhs_comment_roles.py tests/test_xhs_mediacrawler_fixture.py tests/test_audience_evidence.py tests/test_audience_diagnostics.py`，59 项通过；完整 `.venv/bin/python -m pytest -q -o addopts=''` 334 项通过。新增 9 项测试，覆盖非法／缺失哈希、来源标记、哈希不发送模型，以及真实导入 API 至分析部分成功和粉丝保存；另补离线转换字段断言与旧原型的 unknown 预期。首次检查的新测试括号／长行错误及全量测试中新增字段的精确预期均已修正。`backend/.venv/bin/ruff check backend/app backend/tests scripts/xhs_mediacrawler_fixture.py scripts/check_audience_reactions.py`、`git diff --check` 通过。保留既有 LangChain 弃用提醒。用 Python 在内存跑三份已保存真实样本的“离线转换 → 导入解析 → 受众上下文”，作者数分别为 7、2、14，无数据库写入、无模型调用。前端未改，沿用上轮 146 项记录；没有启动正式后端、抓取、部署、提交或推送。需要用户决定：无。

下一次测试：用保存的 QSheep 原始数据重建带来源角色的最近 10 篇输入，最多一次 Qwen 画像调用，检查作者回复误用、宽兴趣及具体人物差异，结果仅存隔离报告。拟新增／修改代码：补可复用的受众分析检查脚本，记录模型、范围、角色计数和逐组校验结果，避免手工输入漂移。下一项改进的验收：模型零作者证据引用、有效角色的需求／判断有实际区别，语义失败如实记录，不反复付费刷通过。旧资产来源字段回填尚未实施，不能声称现有数据库立即获得这项能力。

## 2026-10-03：账号分析依据回看加固

本轮从上次交接检查关键词、优势及原笔记回看，发现同一笔记多段引用会重复计数和显示卡片，快照缺正文时结论被静默隐藏，切换运行可能沿用展开状态。验收是引用数量按不同笔记计数、历史引文和结论不因缺正文消失、缺正文的表现行不再提供无反应入口、切换分析关闭旧详情，且封面只取当次运行所属工作区。修改 `AccountPortraitView.tsx`、`ArtifactRenderers.tsx`，新增独立回归测试；未改后端、提示词、历史数据或已有用户编辑。

已完成上述修正。多段原文仍全部保留，但支持笔记和例外笔记分别按 ID 去重；快照缺少笔记时显示“仅显示历史引用”，不从当前资产补入新正文。画像以运行 ID 隔离交互状态，封面候选按运行工作区过滤。注意：历史运行有正文快照时，即使当前资产删除仍能回看；没有快照时不能恢复正文，本轮不追溯抓取、不篡改结论，也没有额外验证引文的语义支持程度。

验证命令：`npm --prefix frontend test -- --run` 146 项通过（新增 4 项，覆盖重复依据／例外、缺快照、跨运行对话框和封面隔离）；`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。另在 frontend 目录以 `npm exec -- vite --host 127.0.0.1 --port 5178 --strictPort` 启动隔离页面，用 `backend/.venv/bin/python` 的 Playwright Chrome 检查 1000／375／320 像素折叠与展开无横向溢出、长标题笔记弹窗、Escape 关闭后焦点归还、缺快照提示，并查看 320 像素截图。临时页面及服务已清理；未重启正式后端、调用模型、抓取、部署、提交或推送。已有 Node localstorage 测试警告仍存在。需要用户决定：无。

下一次测试：核对已保存离线评论是否带评论者 ID，以及其与主页作者 ID 的对应关系；使用临时样本验证作者回复、普通读者和缺失身份三种情况，不读取或输出登录凭证。拟新增／修改代码：若原始数据确有可靠字段，在小红书解析器及受众输入快照中保留最小来源角色标记并补兼容测试；若没有，记录缺口，不凭文风硬判。下一项新改进及验收：受众分析能把作者补充说明与读者需求分开；只有可靠 ID 匹配才标为作者，未知保持未知，旧导入和旧分析仍可读。真实账号画像的语义审阅、模拟汇总额外建议和虚构个人日程仍待后续，不以本轮界面测试替代模型验收。

## 2026-10-03：模拟粉丝选择区就地预览

本轮解决选择粉丝时只能看名称、需要离开模拟页面才能比较人物的问题。验收要求是：已选槽位显示宽兴趣、具体需求及人物特点，长内容可展开；切换、清空和资产刷新后显示正确；兼容无兴趣字段的旧角色；失效或归档选择不留下旧画像；手机窄屏不横向溢出。修改范围为 `SimulatedFansPage.tsx`、对应组件测试及 `App.css`，未改模型、数据库或执行链路。

已完成：使用当前已保存的编辑定义展示预览，不读取原始生成快照；默认需求和特点各显示最多两行，展开后可阅读全文、内容偏好和表达方式。未选槽位不占预览空间；失效选择明确提示重新选择，保留原有去重及新增槽位行为。切换人物重置展开状态。没有模型调用，没有启动正式后端、部署、提交或推送。

验证：`npm --prefix frontend test -- --run` 142 项通过（本轮新增 3 项）；`npm --prefix frontend run lint`、`npm --prefix frontend run build`、`git diff --check` 通过。使用 `npm exec -- vite --host 127.0.0.1 --port 5178 --strictPort` 在 frontend 目录启动临时预览，随后以 `backend/.venv/bin/python` 执行 Playwright Chrome 无头检查：1100、375、320 像素下无横向溢出，长文本展开、键盘 Enter 收起、清空／重选、移除第四槽均通过，并人工查看截图。首次预览误以仓库根目录启动导致临时页面资源未加载，纠正目录后通过；临时页面与服务已清理。这是实际组件和样式的隔离检查，不代表完整生产页面或真实模型效果已再次验收。旧有 Node localstorage 测试警告仍在，不影响测试结果。需要用户决定：无。

下一轮测试：账号分析结果中的关键词、具体优势及原笔记回看，覆盖旧结果缺字段、长标题、笔记已删除和切换档案。下一轮拟修改代码：先检查 `StageResultViews`／结果渲染器及相关测试，根据可复现问题补来源笔记导航或空态保护，不重写分析流程。下一项新改进：让用户从一条账号优势直接找到支持它的已导入笔记；验收是关联有效、无法关联时不误跳到其他账号、旧历史仍可读。模拟汇总补写无来源品牌、角色虚构具体日程，以及作者回复来源标记仍列为后续效果任务，本轮没有宣称解决。

## 2026-10-03：第一轮同题模拟与汇总自查

本轮验收点是：同一段完整正文、相同宽兴趣下，不同需求能产生有意义的反应；正文已经解答的问题不重复追问；沉默与执行缺失分开；第二轮只能看到公开评论。新增 `scripts/check_audience_reactions.py`，默认只预览免费测试案例，显式 `--live` 才使用 Qwen。三个角色和正文均为人工编写的受控案例，不是实际粉丝或真实账号效果回测。脚本在临时 SQLite 中运行真实 LangGraph，结束后移除临时数据库；成功阶段及原始模型输出保存在指定的新报告目录，正式数据库不读不写。每个操作／角色最多一次实际请求，图内部重试不会重复付费；整图最多七次调用。`--synthesis-from` 可复用既有反应，仅调用一次汇总。

真实 `qwen-plus` 首轮用了六次请求：三次独立反应、两次讨论、一次汇总。行动派表达了马上尝试的意愿，查证派在条件明确后选择不评论，安静读者也保持沉默；没有重复追问正文已回答的费用、步骤或公开要求。两位读者看到行动派留言后仍选择不回应，没有为了热闹硬辩论。不过，行动派自行补出了“下周团建”这一未提供情境，汇总还误把“不转码”解释成视频编解码，并把第二轮沉默说成缺失，因此不能把整轮标作语义验收全部通过。

针对汇总，新增程序计算的 `discussionCoverage`，明确初始反应缺失、主动不评论、可参加讨论、缺少讨论结果以及已选择沉默，避免让模型自己猜执行状态。提示区分完整文字与概念预演，允许不强凑风险，并明确建议字段为字符串数组。只复测汇总三次：第一次发现对象数组不兼容，随后补齐准确格式示例及失败原始输出保存；后两次格式通过，视频编解码误读和沉默缺失问题未重现。本轮实际请求共九次（含一次结构校验失败）。最终结果仍出现“程序核对”等内部用语及未提供的工具品牌，说明仅加强提示还不能保证这些输出要求；不再继续盲目重试付费请求。输出分别在被 Git 忽略的 `data/evals/reactions-20261003-*/`，不进入正式分析、粉丝或模拟历史。

验证命令：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 325 项通过；`backend/.venv/bin/ruff check backend/app backend/tests scripts/check_audience_reactions.py`、`git diff --check` 通过。新增七项测试覆盖真实图路径、正式数据库隔离、付费不重试、公开信息边界、沉默与缺失区分、单次汇总重放及校验失败保留输出。前端本轮未改；没有启动正式服务、提交或推送。需要用户决定：无。

下一次测试模拟粉丝选择区：已有／空槽、重复选择限制、切换人物、长名称和窄屏。拟修改 `SimulatedFanPicker`，在每个已选角色下就地显示简短兴趣、需求与判断习惯，未选时不占预览空间；补组件测试，使用隔离页面做视觉检查。验收是不用离开当前页面即可分辨同兴趣人物，而且不出现横向溢出或大段说明。后续效果任务保留“行动意愿不能编造个人日程”和“汇总额外建议不冒充受众发现”；作者来源角色信息需先查原始数据再决定实现，不靠语气硬标注。

## 2026-10-03：每半小时持续迭代

已更新并启用当前任务的定时跟进，沿用原任务 `sqsagent`，每 30 分钟触发一次，不重复创建任务。范围扩展为账号分析、受众分析、用户／粉丝模拟，以及各页面的布局、审美与可用性。每轮优先修复影响结果或操作的问题，再轮换推进分析效果、模拟差异和界面体验，避免只反复堆叠提示词。每次从未完成的交接项中选择一项，先写验收标准，再实现和验证；测试通过、真实模型效果、人工界面验收分开记录。

每轮交接固定说明本次完成或失败、实际测试与剩余限制，以及下一次要测试的功能、要新增／修改的代码、下一项改进和验收点。保留未提交改动及用户编辑，不自动提交、推送、抓取或部署；必要的小规模真实 Qwen 检查按用户默认授权执行，但不为了定时运行而重复付费。界面检查优先使用临时测试数据和隔离服务，不自行重启已关闭的正式后端。需要用户决定的事项明确记录，没有则说明无。

下一轮先验证同题模拟：选择共享宽兴趣、需求与判断不同的少量角色，面对同一段完整文字分别生成反应，检查是否只是复述历史评论、是否重复追问正文已回答的问题，以及沉默／认同／追问是否符合各自需求。必要时新增可复用的只读验证脚本和固定响应回归测试，修正反应及讨论提示，不写入正式模拟历史。验收是模型输入差异能解释实际反应差异，而非强制每人表达相反意见。

随后推进评论来源角色信息与界面检查：先核对离线抓取数据能否提供作者标记，避免凭语气硬分类；再检查受众卡片、选择槽、保存反馈和窄屏布局，并根据可复现的问题安排下一轮代码。账号分析方向同步保留具体优势、关键词和原笔记回看这一重点。当前没有新增需要用户拍板的事项。

## 2026-10-02：宽兴趣角色的两次真实 Qwen 检查

按用户对必要小规模模型验证的默认授权，用已保存的 QSheep 最近 10 条笔记、85 条评论，经过产品的 `ModelCallService` 和受众结果校验做了两次真实 `qwen-plus` 调用。数据库以只读方式打开，未启动后端、未重新抓取、未保存分析或覆盖粉丝。测试显式使用已配置的 Qwen OpenAI 兼容通道，不改变现有环境文件中的默认 provider。

首轮耗时 48.6 秒，输入 13,555 tokens、输出 2,152 tokens；8 位角色均通过结构及原文引用核验，但人工阅读发现兴趣仍有“AI实习、产品实习、运营实习”等细分堆叠，需求容易变成某条笔记的一次咨询。一段给读者提供投递方式的回复还被用来刻画读者的催促行为。由此补充了题材先归并为上位兴趣、角色跨笔记复用、供给信息不等于读者反应的提示和正反例；询问指导也不自动推成付费意愿。

同批样本复测耗时 56.5 秒，输入 13,954 tokens、输出 2,512 tokens；再次返回 8 位，8 位引用通过。兴趣主要归为职业发展、AI应用、个人成长、视觉创作、留学等；共享这些兴趣的角色分别需要行动入口、卡点拆解、关键条件核对、随用随查、价值认同等帮助。首轮被误用的两条作者答复口吻引文未再出现。这是两次案例观察，不是稳定质量提升的统计结论；本次只验证画像生成，没有另行付费运行完整模拟。

剩余问题：部分表达习惯仍复述原评论，画像偶尔写“高频收藏”或“用点赞表达认同”等无法由样本确认的行为；摘要和部分人物字段也未稳定遵守建议字数。当前导入评论没有保留作者身份标记，供给／读者区分仍依赖模型理解，不能声称已做到确定性排除。下一步先用同一选题检查不同角色的真实反应是否有意义，再考虑补齐评论来源角色元信息，不继续以增加人格字段代替效果验证。提示与数据链路的回归检查沿用下节；本轮后端 318 项测试及后端 lint、diff 检查通过，前端未改。

## 2026-10-01：兴趣更宽，需求与性格更具体

受众分析新增 `interests` 宽兴趣字段，生成目标 1～3 项，资产最多保存 6 项、每项 30 字。兴趣可以是“留学、职业发展”，不应是某校某篇笔记的问题；`profile` 改为一句话行为触发与判断／行动，`coreConcern` 写具体需要的帮助或决定，`contentPreference` 写内容形式，`expressionStyle` 写说话和参与方式。相同兴趣下允许多位有不同需求的读者；无法确定一种性格时拆成几位合理人物，不只改语气、不强制对立。生成数量仍优先 8 位、通常 6～8 位，每轮全部有效角色继续自动保存。

兴趣贯穿分析短卡片、粉丝编辑、派生声音、模拟快照、独立反应与第二轮交流。旧数据缺字段时按空列表读取，旧客户端漏传时保留已保存的兴趣；不改写历史或新增数据库表。文档已区分当前短角色与尚未实现的 `facets`／原型候选确认方案，后者不是当前自动保存的前提。

工程验证：`cd backend && .venv/bin/python -m pytest -q -o addopts=''` 318 项通过；`backend/.venv/bin/ruff check backend/app backend/tests` 通过；`npm --prefix frontend test -- --run` 139 项通过，`npm --prefix frontend run lint`、`npm --prefix frontend run build` 及 `git diff --check` 通过。新增回归覆盖宽兴趣标签校验、旧客户端漏传保留、显式清空、相同兴趣角色独立保存、派生声音继承编辑值、重启后使用冻结快照，以及独立反应和第二轮交流的实际模型输入。兴趣标签本身含逗号／顿号时，未编辑该字段会保留原数组，不因改名字而重新拆分。仅有既有 LangChain 弃用和 Node localstorage 参数提示。

剩余验收：人工并排检查同一宽兴趣下的具体需求与判断差异，随后在有明确验证目标和授权时做一次真实模型检查。本轮未调用真实模型、未重生成已有粉丝，不能宣称模型效果已经改善；后端保持关闭，未提交或推送。

## 2026-10-01：更多、更简短的受众角色

受众分析提示词与教学示例改为每轮优先 8 位、通常 6～8 位，每位是一句话特点、一个关注点、简短内容偏好和说话风格。同一需求可以生成不同态度和性格的人物，不再只做话题分组。每次新分析的全部有效角色自动保存到模拟粉丝，重复处理同一结果不会重复新增，也不覆盖旧编辑。页面卡片保持简短，依据和分析说明默认折叠；旧长描述与历史结果不做裁剪。默认参加模拟仍是三个槽位，可自行增加。生成数量和长度是模型目标，引用失败或材料过少可少于六位。

后端全套测试及 lint、前端 134 项测试及 lint/build 通过。经用户明确授权，用 QSheep 的 10 条已保存笔记做了一次 Qwen `qwen-plus` 检查：返回 8 位，8 位引用通过，简介最长 55 字，结果未写入数据库。发现部分名称仍偏话题且含多余身份背景，随后再收紧提示，强调用态度和表达命名、简介仅写阅读行为；这一末次提示微调尚未再次付费复测。此处为当时验证记录，不代表上方新增宽兴趣字段后的真实模型结果。后端后来已按用户要求在数据交接前关闭；本轮不自动启动。

## 2026-10-01：账号画像更面向创作者

账号诊断新增账号关键词、具体优势和鼓励语，并把这些放在结果页前面；模型提示强调先看到创作者已有的价值，不写成审稿意见。笔记表现的数据口径改为可展开说明，条件不足的前后变化不再占一整块提醒。新字段可选，老分析历史继续显示原结果；每条新结论仍能打开对应笔记。后端全套测试及 lint、前端 133 项测试及 lint/build 通过。下一步要用真实账号结果检查“夸得具体、有辨识度、不像模板文案”，并由用户判断语气是否合适；本次未重新诊断或覆盖现有历史。

## 2026-10-01：同一关注点的多种人物声音

模拟粉丝可从一位已保存粉丝派生 12 种内置声音：行动派、共鸣派、查证派、质疑派、沉默收藏者等。粉丝资产页可勾选后批量加入，角色继承原关注点和依据，但拥有不同的判断方式、表达语气及参与倾向，并继续允许显式编辑。重复选择同一来源和模板复用原角色，不覆盖用户改动；源资产和旧历史不变。模拟提示词开始明确使用这些人物差异，避免把每位都写成相同的内容策划。更多角色的独立反应和讨论请求采用四路并发，不设人数上限也不瞬间发出所有调用。此扩充是确定性的 demo 角色设定，不是新的受众分析模型调用；真实模型的人物适配仍是下一阶段。后端全套测试及相关 lint、前端 132 项测试及 lint/build、`git diff --check` 均通过；未调用真实模型、抓取或提交。

## 2026-10-01：受众模拟改为可扩展选择槽

公开模拟默认显示三个下拉槽位，可按需点「＋ 新增」继续选择当前账号的未归档模拟粉丝；额外槽位可移除，空槽位不参与执行，同一粉丝不能重复选择。后端创建请求及粉丝快照不再限制三位，四位粉丝按选择顺序完成运行的集成测试通过。上线时自动保存仍为首次前三位，随后已改为每次分析保存全部有效角色，见上方增量；默认三个槽位不是模拟人数上限。旧历史快照不改。后端完整测试与相关 lint、前端 131 项测试与 lint/build 均通过。下文旧记录提到的“每次最多三位”仅是当时实现，已由本节取代。本轮未抓取、调用真实模型或提交。

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

以下为上线时记录：当前自动保存数量与模拟选择上限均已由 2026-10-01 的增量取代，旧历史不回写。

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

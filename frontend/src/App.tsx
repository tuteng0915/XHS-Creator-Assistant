import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'

import {
  ApiError,
  agentApi,
  agentConversationApi,
  analysisRunApi,
  assetProposalApi,
  draftApi,
  simulationRunApi,
  skillApi,
  sourceMaterialApi,
  topicApi,
  workspaceApi,
  workflowAssetApi,
} from './api'
import { HealthPage } from './HealthPage'
import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  INPUT_ASSET_DEFINITIONS,
  inputAssetPreview,
  inputAssetUpdatedLabel,
  isTrendCsvInputAsset,
  type InputAssetPanel,
} from './inputAssets'
import type {
  Agent,
  AgentConversation,
  AgentConversationSummary,
  AgentSummary,
  AnalysisRun,
  AnalysisRunSummary,
  ActivityEvent,
  AssetProposal,
  Draft,
  DraftSummary,
  SavePhase,
  SimulationRun,
  SimulationRunSummary,
  Skill,
  SkillSummary,
  SourceMaterial,
  TextSourceMaterial,
  Topic,
  TopicSourceWorkflow,
  TrendCsvSourceMaterial,
  Workspace,
  WorkflowAsset,
  WorkflowAssetSummary,
  WorkflowType,
} from './types'
import {
  ACCOUNT_STAGES,
  type GenerationMode,
  TREND_STAGES,
  type TopicCandidate,
  VIDEO_CREATOR_STAGES,
  type WorkflowTab,
} from './workflows'

type SaveKey =
  | 'workspace'
  | 'accountProfiles'
  | 'historical'
  | 'comments'
  | 'trend'
  | 'video'
  | 'manualTopic'
  | 'topic'
  | 'draft'
type SaveState = { phase: SavePhase; message?: string }
type ActivePage =
  | 'account-profile'
  | 'source-materials'
  | 'account-diagnosis'
  | 'trend-analysis'
  | 'video-quality'
  | 'history'
  | 'topics'
  | 'drafts'
  | 'simulations'
  | 'skills'
  | 'agents'
  | 'workflows'
type ProfileSourceMode = 'workspace' | 'saved' | 'manual'
type StageView = {
  key: string
  n: string
  title: string
  status: 'waiting' | 'running' | 'completed' | 'failed'
  result?: unknown
  error?: string
}
type WorkflowOutputKind = 'analysis' | 'simulation'
type WorkflowStageViews = Record<WorkflowTab, StageView[]>
type WorkflowOutputKinds = Record<WorkflowTab, WorkflowOutputKind>
const MAKER_AGENT_IDS = {
  skill: 'skill_maker',
  agent: 'agent_maker',
  workflow: 'workflow_maker',
} as const
const NEW_INPUT_ASSET_ID = '__new_input_asset__'

const idleState: SaveState = { phase: 'idle' }
const emptyWorkflowStageViews = (): WorkflowStageViews => ({
  account: [],
  trend: [],
  video: [],
})
const defaultWorkflowOutputKinds = (): WorkflowOutputKinds => ({
  account: 'analysis',
  trend: 'analysis',
  video: 'analysis',
})
const SIMULATION_STAGES = [
  { key: 'personas', n: '01', title: '受众角色推导' },
  { key: 'initial_reactions', n: '02', title: '第一轮独立反应' },
  { key: 'debate_responses', n: '03', title: '第二轮交叉回应' },
  { key: 'synthesis', n: '04', title: '策略合成' },
]
const SAMPLE_ACCOUNT_INPUT = {
  positioning: `账号:@QSheep｜留学内容创作者,1.4K 粉。核心人群=正在准备/纠结出国读研的文科生(传媒、社科、人类学),目标英港新前30。
内容主张:真实反思 + 决策方法,不贩卖焦虑、不灌鸡汤。
作者优势:亲历者视角、擅长把模糊焦虑拆成可执行的决策步骤、文笔好。
目标:选题持续围绕「选校决策 / 申请策略 / 留学反思」,但要避开已经写过的老话题。`,
  historicalPosts: `二本逆袭G5?别再被这种标题骗了 ｜ 赞1.4k 藏980 ｜ 爆
留学中介到底值不值5万块|我的真实账单与避坑清单 ｜ 赞1.1k 藏860 ｜ 爆
选校时我后悔没早知道的6件事 ｜ 赞720 藏610 ｜ 爆
文科留学回国到底有没有用|工作一年后说点实话 ｜ 赞90 藏40 ｜ 平
DIY申请时间线:从大三暑假到递交我每个月都干了啥 ｜ 赞60 藏150 ｜ 差`,
  comments: `中介那部分太真实了,我现在就纠结要不要DIY,自己怕搞砸
想问下双非背景冲英国前30有戏吗,真的好焦虑
回国后发现海归学历根本不值钱,有点后悔
求一个选校时间线!完全不知道几月该干嘛,好慌
文书到底自己写还是找人改啊,我憋了两周写不出来
家里不太支持留学,该怎么说服父母
雅思一直卡6.5,是不是该先把雅思考完再准备申请
想知道港三和英国前30到底怎么选,纠结死了
均分85冲刺前20稳吗,GPA算是劣势吗
看了好多博主都在贩卖焦虑,终于有人好好说话了
转专业申请会不会很吃亏,本科传媒想转社科
预算有限,中介和DIY的钱到底该花在哪一步
实习经历很水,文书里要不要硬写
拿到offer了但突然不确定该不该去,好迷茫`,
  simulationTopic: '5万块中介费,该花的是这3步,剩下4步你自己做更好',
}
const SAMPLE_TREND_INPUT = {
  positioning: `账号：数字游民生活方式推广者
核心人群：想从城市职场转向远程工作/自由职业的年轻人，尤其是非技术背景、文科生、运营/内容/教育从业者。
内容主张：真实记录转型路径，不神化自由职业，强调技能、现金流和风险边界。
目标：找到兼具热度和可执行性的数字游民选题。`,
  keyword: '数字游民',
  simulationTopic:
    '文科生/非技术背景，靠什么开始数字游民？6条真实路径\n切入角度：把「没有可以远程的技能」这个最大卡点，拆成6个具体可行的技能转换方向',
}
const SAMPLE_TREND_CSV = `title,likes,collects,comments,tags,content_snippet,date
一天三份工，还能躺平？巴厘岛游民生活大公开,1790,526,77,#旅居巴厘岛 #数字游民 #巴厘岛,巴厘岛数字游民 一天三份收入的一天 是怎么样度过的,2026-01-02
分享一家全员远程办公的公司(19),883,657,426,#远程办公 #远程工作 #数字游民,从22年11月开始分享全员远程工作公司以来，这个系列终于轮到我自己的公司了,2026-01-03
普通小孩儿不要轻易尝试数字游民,953,402,87,#数字游民 #裸辞 #旅居,白人Privilege：挣发达国家的钱 去第三世界花 并不建议脑子一热就去做数字游民,2026-01-04
不会英语泰语，如何在泰国躺平式搞钱？,286,221,47,#泰国 #曼谷 #数字游民 #跨境电商,普通人低成本旅居和远程赚钱的真实路径,2026-01-05
VLOG｜一份主业多份副业，我靠什么技能赚钱,197,115,10,#数字游民 #远程工作 #副业,主业副业组合与现金流拆解,2026-01-06
30岁沪漂女高管裸辞炒股：不上班月入10w+,115,77,83,#裸辞 #投资理财 #数字游民,从魔都996到小城自由职业 我终于逃离内卷的沪漂,2026-01-07
VLOG｜成为数字游民前，我都做了哪些准备,120,50,4,#数字游民 #远程工作 #副业,成为数字游民之前的技能和存款准备,2026-01-08
26岁年薪7位数 如何用AI拿到远程工作offer,61,106,0,#数字游民 #远程工作 #AI人工智能,4步利用AI工具帮你找到远程工作,2026-01-09
自由职业｜线上中文老师的一天,75,50,15,#自由职业 #数字游民 #线上中文教师,从高校岗位转向线上中文教师的一天,2026-01-10
普通人也能成为数字游民（内附找工作渠道）,45,57,3,#数字游民 #远程工作 #远程办公,远程工作可能没那么玄乎，它和普通人的距离可能只是一个获取招聘信息的渠道,2026-01-11`

const SAMPLE_VIDEO_INPUT = {
  positioning: `业务场景：AIGC 视频创作者激励计划
目标：从收集到的视频创作者中筛选适合长期激励和运营扶持的对象。
判断原则：
- 剧本驱动型创作者通常适合激励计划，因为激励能放大持续更新、系列化和剧情迭代。
- 商单驱动型创作者主要受品牌预算和转化目标影响，平台激励通常很难改变行为。
- 技术探索驱动型创作者需要分类讨论：能转化为稳定栏目则可条件适配，否则更适合技术共创或专项活动。`,
  videoCreatorSamples: `创作者：@AI短剧研究所
平台：小红书 / 抖音
样本：
1.《机器人女友觉醒后删除了我的记忆》｜AIGC短剧｜赞 2.3w｜评论 1800｜完播率较高
观察：固定赛博都市世界观，同一女主角连续出现，开头 3 秒直接给冲突，结尾留悬念。
2.《当古代谋士拿到 ChatGPT》｜AIGC剧情｜赞 1.7w｜收藏 4200
观察：角色设定清晰，台词有反转，画面风格统一，但人物手部和口型偶有跳变。
3.《用 5 个 AI 工具做一支广告片》｜工具教程｜赞 3200｜收藏 5100
观察：偏技术拆解，互动主要来自创作者询问工具链。
4. 最近 30 天更新 18 条，其中 12 条是同一世界观短剧，4 条工具教程，2 条品牌合作植入。
运营备注：评论区大量催更剧情线，商单内容互动明显低于剧情内容。`,
  simulationTopic: '如果把 @AI短剧研究所 纳入 4 周 AIGC 短剧连续更新激励计划，应该怎么设计任务和风险边界？',
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : '操作失败，请重试。'
}

function SaveIndicator({ state }: { state: SaveState }) {
  if (state.phase === 'idle') return null
  const labels = {
    saving: '保存中…',
    saved: '已保存',
    error: state.message || '保存失败',
    idle: '',
  }
  return (
    <span className={`save-state ${state.phase}`} role="status">
      {labels[state.phase]}
    </span>
  )
}

function latestTextMaterial(
  materials: SourceMaterial[],
  type: 'account_profile' | 'historical_posts' | 'comments' | 'video_creator_samples',
): TextSourceMaterial | undefined {
  return materials.find(
    (material): material is TextSourceMaterial => material.type === type,
  )
}

function latestTrendMaterial(
  materials: SourceMaterial[],
): TrendCsvSourceMaterial | undefined {
  return materials.find(
    (material): material is TrendCsvSourceMaterial =>
      material.type === 'trend_csv',
  )
}

function workflowFromTab(tab: WorkflowTab): WorkflowType {
  if (tab === 'account') return 'account_diagnosis'
  if (tab === 'video') return 'video_creator_quality'
  return 'trend_analysis'
}

function workflowTabFromSource(sourceWorkflow?: unknown): WorkflowTab {
  if (sourceWorkflow === 'video_creator_quality') return 'video'
  return sourceWorkflow === 'trend_analysis' ? 'trend' : 'account'
}

function workflowTabFromSimulation(run: SimulationRun): WorkflowTab {
  const topic = run.inputSnapshot.topic as { sourceWorkflow?: unknown } | null
  const draft = run.inputSnapshot.draft as { sourceWorkflow?: unknown } | null
  return workflowTabFromSource(draft?.sourceWorkflow || topic?.sourceWorkflow)
}

function workflowLabel(type: WorkflowType): string {
  if (type === 'account_diagnosis') return '账号诊断'
  if (type === 'video_creator_quality') return '视频创作者质量诊断'
  return '热点分析'
}

function activePageForWorkflowTab(tab: WorkflowTab): ActivePage {
  if (tab === 'account') return 'account-diagnosis'
  if (tab === 'video') return 'video-quality'
  return 'trend-analysis'
}

function stageSeed(tab: WorkflowTab): StageView[] {
  const stages =
    tab === 'account'
      ? ACCOUNT_STAGES
      : tab === 'video'
        ? VIDEO_CREATOR_STAGES
        : TREND_STAGES
  return stages.map((stage) => ({ ...stage, status: 'waiting' }))
}

function stageSeedFromRun(run: AnalysisRun): StageView[] {
  const tab =
    run.workflowType === 'account_diagnosis'
      ? 'account'
      : run.workflowType === 'video_creator_quality'
        ? 'video'
        : 'trend'
  return stageSeed(tab).map((stage) => ({
    ...stage,
    status: run.stageErrors[stage.key]
      ? 'failed'
      : run.stageResults[stage.key]
        ? 'completed'
        : run.status === 'running'
          ? 'running'
          : 'waiting',
    result: run.stageResults[stage.key],
    error: run.stageErrors[stage.key],
  }))
}

function stageSeedFromSimulation(run: SimulationRun): StageView[] {
  const hasSynthesis = Object.keys(run.synthesis || {}).length > 0
  const resultByStage: Record<string, unknown> = {
    personas: run.personaDefinitions.length
      ? { personas: run.personaDefinitions }
      : undefined,
    initial_reactions: run.reactionResults.length
      ? { reactions: run.reactionResults }
      : undefined,
    debate_responses: run.debateResults.length
      ? { debateResponses: run.debateResults }
      : undefined,
    synthesis: hasSynthesis ? { synthesis: run.synthesis } : undefined,
  }
  return SIMULATION_STAGES.map((stage) => ({
    ...stage,
    status: run.stageErrors[stage.key]
      ? 'failed'
      : resultByStage[stage.key]
        ? 'completed'
        : run.status === 'running'
          ? 'running'
          : 'waiting',
    result: resultByStage[stage.key],
    error: run.stageErrors[stage.key],
  }))
}

function getTopicsFromStage(result: unknown): TopicCandidate[] {
  if (!result || typeof result !== 'object') return []
  const topics = (result as { topics?: unknown }).topics
  return Array.isArray(topics) ? (topics as TopicCandidate[]) : []
}

function ProfileView({ data }: { data: Record<string, unknown> }) {
  const pillars = Array.isArray(data.pillars) ? data.pillars : []
  const formulas = Array.isArray(data.titleFormulas) ? data.titleFormulas : []
  const hooks = Array.isArray(data.hookStyles) ? data.hookStyles : []
  const structure = (data.viralStructure || {}) as {
    name?: string
    steps?: string[]
  }
  const contrast = data.contrast as
    | {
        winners?: Array<{ title: string; metric: string }>
        losers?: Array<{ title: string; metric: string }>
        winFactors?: string[]
        loseFactors?: string[]
        takeaways?: string[]
      }
    | undefined
  return (
    <div className="stage-block">
      {contrast && (
        <>
          <label>📊 高表现 vs 低表现 · 对比诊断</label>
          <div className="cmp">
            <div className="cmp-col cmp-win">
              <h5>✅ 高表现共性</h5>
              {(contrast.winners || []).map((item) => (
                <div className="cmp-item" key={item.title}>
                  <b>{item.title}</b> · {item.metric}
                </div>
              ))}
              <ul>{(contrast.winFactors || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
            <div className="cmp-col cmp-lose">
              <h5>⚠️ 低表现共性</h5>
              {(contrast.losers || []).map((item) => (
                <div className="cmp-item" key={item.title}>
                  <b>{item.title}</b> · {item.metric}
                </div>
              ))}
              <ul>{(contrast.loseFactors || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>
          <div className="takeaway">
            <b>→ 可执行结论：</b>
            <ol>{(contrast.takeaways || []).map((item) => <li key={item}>{item}</li>)}</ol>
          </div>
        </>
      )}
      <label>📚 内容支柱</label>
      <div className="pill-row">
        {pillars.map((pillar) => (
          <span className="quote red" key={String(pillar)}>
            {String(pillar)}
          </span>
        ))}
      </div>
      <label>✍️ 惯用标题公式</label>
      <div className="outline">
        {formulas.map((formula) => {
          const item = formula as { formula?: string; examples?: string[] }
          return (
            <div className="ol" key={item.formula}>
              <div className="sec">公式</div>
              <div className="ct">
                <b>{item.formula}</b>
                {(item.examples || []).map((example) => (
                  <div className="quote" key={example}>
                    例：{example}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <label>🪝 开头钩子习惯</label>
      <ul>{hooks.map((hook) => <li key={String(hook)}>{String(hook)}</li>)}</ul>
      <label>🧱 惯用爆款结构 · {structure.name}</label>
      <div className="titles">
        {(structure.steps || []).map((step, index) => (
          <div className="titlev" key={step}>
            <span>{index + 1}</span>
            {step}
          </div>
        ))}
      </div>
    </div>
  )
}

function PainPointsView({ items }: { items: unknown }) {
  const painPoints = Array.isArray(items) ? items : []
  return (
    <>
      {painPoints.map((item) => {
        const point = item as {
          theme?: string
          intensity?: string
          count?: number
          evidence?: string[]
        }
        return (
          <div className="pp" key={point.theme}>
            <div className="pp-top">
              <b>{point.theme}</b>
              <span className={`tag ${point.intensity === '高' ? 'high' : 'mid'}`}>
                强度 {point.intensity}
              </span>
              <span className="tag cnt">{point.count || 0} 条相关</span>
            </div>
            <div>
              {(point.evidence || []).map((quote) => (
                <span className="quote" key={quote}>
                  “{quote}”
                </span>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}

function TrendAnalysisView({ data }: { data: Record<string, unknown> }) {
  const themes = Array.isArray(data.themes) ? data.themes : []
  const patterns = Array.isArray(data.viralPatterns) ? data.viralPatterns : []
  const windows = Array.isArray(data.opportunityWindows)
    ? data.opportunityWindows
    : []
  return (
    <div className="stage-block">
      <label>🔥 高频内容主题</label>
      {themes.map((item) => {
        const theme = item as {
          theme?: string
          engagement?: string
          count?: number
          topPost?: string
          summary?: string
        }
        return (
          <div className="trend-theme" key={theme.theme}>
            <div className="trend-theme-top">
              <b>{theme.theme}</b>
              <span className={`tag ${theme.engagement === '高' ? 'high' : 'mid'}`}>
                热度 {theme.engagement}
              </span>
              <span className="tag cnt">{theme.count || 0} 篇相关</span>
            </div>
            <div>
              <span className="quote">代表帖：{theme.topPost}</span>
            </div>
            <div className="subline">{theme.summary}</div>
          </div>
        )
      })}
      <label>✨ 爆款规律</label>
      <ul>{patterns.map((item) => <li key={String(item)}>{String(item)}</li>)}</ul>
      <label>🎯 内容机会窗口</label>
      {windows.map((item) => (
        <div className="opportunity" key={String(item)}>
          <b>🪟</b> {String(item)}
        </div>
      ))}
    </div>
  )
}

function StructureView({ data }: { data: Record<string, unknown> }) {
  const outline = Array.isArray(data.outline) ? data.outline : []
  return (
    <div className="stage-block">
      <div className="outline">
        {outline.map((item) => {
          const part = item as { sec?: string; ct?: string }
          return (
            <div className="ol" key={`${part.sec}-${part.ct}`}>
              <div className="sec">{part.sec}</div>
              <div className="ct">{part.ct}</div>
            </div>
          )
        })}
      </div>
      <div className="reuse">
        <b>♻ 可复用表达结构：</b> {String(data.reuse || '')}
      </div>
    </div>
  )
}

function TitlesView({ items }: { items: unknown }) {
  const titles = Array.isArray(items) ? items : []
  return (
    <>
      {titles.map((item) => {
        const title = item as { topic?: string; variants?: string[] }
        return (
          <div className="topic" key={title.topic}>
            <h4>📌 {title.topic}</h4>
            <div className="titles">
              {(title.variants || []).map((variant, index) => (
                <div className="titlev" key={variant}>
                  <span>{String.fromCharCode(65 + index)}</span>
                  {variant}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}

function ListBlock({ title, items }: { title: string; items: unknown }) {
  const values = Array.isArray(items) ? items : []
  if (values.length === 0) return null
  return (
    <>
      <b>{title}：</b>
      <ul>{values.map((item) => <li key={String(item)}>{String(item)}</li>)}</ul>
    </>
  )
}

function PersonaListView({ items }: { items: unknown }) {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <div className="persona-list">
      {(items as Array<Record<string, unknown>>).map((persona) => {
        const title = String(
          persona.archetype || persona.name || persona.id || 'Persona',
        )
        const profile = String(persona.profile || persona.background || '')
        const personality = String(persona.personality || '')
        const concern = String(persona.concerns || persona.coreConcern || '')
        const preference = String(persona.contentPreference || '')
        return (
          <div className="topic" key={String(persona.id || persona.name)}>
            <h4>{title}</h4>
            <div className="angle">{profile}</div>
            <div className="why">
              {personality && (
                <>
                  <b>性格：</b> {personality}
                  <br />
                </>
              )}
              <b>关注：</b> {concern}
              {preference && (
                <>
                  <br />
                  <b>内容偏好：</b> {preference}
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ReactionListView({
  items,
  type,
}: {
  items: unknown
  type: 'reaction' | 'debate'
}) {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <div className="persona-list">
      {(items as Array<Record<string, unknown>>).map((item) => (
        <div className="topic" key={String(item.personaId)}>
          <h4>Persona {String(item.personaId)}</h4>
          {type === 'reaction' ? (
            <>
              <div className="angle">
                {String(item.stance || item.sentiment || '')} ·{' '}
                {String(item.quote || item.text || '')}
              </div>
              <ListBlock title="顾虑" items={item.concerns} />
              <ListBlock title="机会" items={item.opportunities} />
            </>
          ) : (
            <>
              <div className="angle">{String(item.response || item.text || '')}</div>
              {item.stance && (
                <div className="why">
                  <b>立场：</b> {String(item.stance)}
                  {Boolean(item.targetedAt) && (
                    <>
                      <br />
                      <b>回应对象：</b> {String(item.targetedAt)}
                    </>
                  )}
                </div>
              )}
              <ListBlock title="新顾虑" items={item.newConcerns} />
              <ListBlock title="更强信号" items={item.strongerSignals} />
            </>
          )}
        </div>
      ))}
    </div>
  )
}

function SynthesisView({ data }: { data: Record<string, unknown> }) {
  const topResonance = data.topResonance as
    | { persona?: string; reason?: string; expectedBehavior?: string }
    | undefined
  return (
    <div className="structure-card">
      <h4>{String(data.verdict || '模拟结论')}</h4>
      {topResonance && Object.keys(topResonance).length > 0 && (
        <div className="why">
          <b>🎯 最有共鸣受众：</b> {String(topResonance.persona || '')}
          <br />
          {String(topResonance.reason || '')}
          <br />
          <b>预期行为：</b> {String(topResonance.expectedBehavior || '')}
        </div>
      )}
      <p>
        <b>最大阻力：</b> {String(data.mainResistance || '')}
      </p>
      <p>
        <b>最强切角：</b> {String(data.strongestAngle || '')}
      </p>
      <ListBlock title="内容调整" items={data.contentAdjustments} />
      <ListBlock title="风险提醒" items={data.riskWarnings} />
      <ListBlock title="潜在争议点" items={data.controversyPoints} />
      <ListBlock title="优化建议" items={data.suggestions} />
    </div>
  )
}

function VideoCreatorProfileView({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="stage-block">
      <div className="structure-card">
        <h4>{String(data.creatorType || '创作者类型待判断')}</h4>
        <p>
          <b>置信度：</b> {String(data.typeConfidence || '')}
        </p>
        <p>{String(data.summary || '')}</p>
        <p>
          <b>受众定位：</b> {String(data.audiencePositioning || '')}
        </p>
      </div>
      <ListBlock title="内容支柱" items={data.contentPillars} />
      <ListBlock title="驱动信号" items={data.motivationSignals} />
      <ListBlock title="证据" items={data.evidence} />
      <ListBlock title="不确定项" items={data.uncertainties} />
    </div>
  )
}

function VideoQualityView({ data }: { data: Record<string, unknown> }) {
  const dimensions = Array.isArray(data.dimensionScores)
    ? data.dimensionScores
    : []
  return (
    <div className="stage-block">
      <div className="structure-card">
        <h4>
          质量评级：{String(data.level || '')} · {String(data.overallScore || '')}
        </h4>
      </div>
      <div className="outline">
        {dimensions.map((item) => {
          const dimension = item as {
            dimension?: string
            score?: number
            reason?: string
          }
          return (
            <div className="ol" key={dimension.dimension}>
              <div className="sec">{dimension.dimension}</div>
              <div className="ct">
                <b>{dimension.score ?? ''}</b> · {dimension.reason}
              </div>
            </div>
          )
        })}
      </div>
      <ListBlock title="优势" items={data.strengths} />
      <ListBlock title="短板" items={data.weaknesses} />
      <ListBlock title="证据" items={data.evidence} />
    </div>
  )
}

function IncentiveFitView({ data }: { data: Record<string, unknown> }) {
  const programMatch = (data.programMatch || {}) as Record<string, unknown>
  return (
    <div className="stage-block">
      <div className="structure-card">
        <h4>
          激励适配：{String(data.recommendation || '')} ·{' '}
          {String(data.fitScore || '')}
        </h4>
        <p>{String(data.rationale || '')}</p>
        <div className="why">
          <b>适合计划：</b> {String(programMatch.bestProgramType || '')}
          <br />
          <b>原因：</b> {String(programMatch.why || '')}
          <br />
          <b>避免：</b> {String(programMatch.avoid || '')}
        </div>
      </div>
      <ListBlock title="适配条件" items={data.conditions} />
      <ListBlock title="风险" items={data.risks} />
      <ListBlock title="运营动作" items={data.operatorActions} />
    </div>
  )
}

function WorkspaceApp() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('')
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [materials, setMaterials] = useState<SourceMaterial[]>([])
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRunSummary[]>([])
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null)
  const [simulationRuns, setSimulationRuns] = useState<SimulationRunSummary[]>([])
  const [selectedSimulationRun, setSelectedSimulationRun] =
    useState<SimulationRun | null>(null)
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [agentConversations, setAgentConversations] = useState<
    AgentConversationSummary[]
  >([])
  const [selectedAgentConversation, setSelectedAgentConversation] =
    useState<AgentConversation | null>(null)
  const [assetProposals, setAssetProposals] = useState<AssetProposal[]>([])
  const [agentMessageDraft, setAgentMessageDraft] = useState('')
  const [agentSending, setAgentSending] = useState(false)
  const [agentConversationCreating, setAgentConversationCreating] = useState(false)
  const [workflowAssets, setWorkflowAssets] = useState<WorkflowAssetSummary[]>([])
  const [selectedWorkflowAsset, setSelectedWorkflowAsset] =
    useState<WorkflowAsset | null>(null)
  const [drafts, setDrafts] = useState<DraftSummary[]>([])
  const [selectedDraft, setSelectedDraft] = useState<Draft | null>(null)
  const [draftEditor, setDraftEditor] = useState('')
  const [topics, setTopics] = useState<Topic[]>([])
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null)
  const [topicFilter, setTopicFilter] = useState<TopicSourceWorkflow | 'all'>('all')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createPositioning, setCreatePositioning] = useState('')
  const [creating, setCreating] = useState(false)
  const [activePage, setActivePage] = useState<ActivePage>('account-diagnosis')
  const [workflowTab, setWorkflowTab] = useState<WorkflowTab>('account')
  const [mode, setMode] = useState<GenerationMode>('demo')
  const [workspaceName, setWorkspaceName] = useState('')
  const [positioning, setPositioning] = useState('')
  const [profileSourceMode, setProfileSourceMode] =
    useState<ProfileSourceMode>('workspace')
  const [selectedProfileMaterialId, setSelectedProfileMaterialId] = useState('')
  const [manualWorkflowProfile, setManualWorkflowProfile] = useState('')
  const [accountProfilesFile, setAccountProfilesFile] = useState<File | null>(null)
  const [inputAssetPanel, setInputAssetPanel] =
    useState<InputAssetPanel>('historical_posts')
  const [selectedHistoricalMaterialId, setSelectedHistoricalMaterialId] =
    useState('')
  const [selectedCommentsMaterialId, setSelectedCommentsMaterialId] = useState('')
  const [selectedTrendMaterialId, setSelectedTrendMaterialId] = useState('')
  const [selectedVideoMaterialId, setSelectedVideoMaterialId] = useState('')
  const [historicalPosts, setHistoricalPosts] = useState('')
  const [comments, setComments] = useState('')
  const [trendKeyword, setTrendKeyword] = useState('')
  const [trendFile, setTrendFile] = useState<File | null>(null)
  const [videoCreatorSamples, setVideoCreatorSamples] = useState('')
  const [simulationTopic, setSimulationTopic] = useState('')
  const [analysisStageViewsByWorkflow, setAnalysisStageViewsByWorkflow] =
    useState<WorkflowStageViews>(emptyWorkflowStageViews)
  const [simulationStageViews, setSimulationStageViews] = useState<StageView[]>([])
  const [workflowOutputKindByWorkflow, setWorkflowOutputKindByWorkflow] =
    useState<WorkflowOutputKinds>(defaultWorkflowOutputKinds)
  const [currentRun, setCurrentRun] = useState<AnalysisRun | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')
  const [manualTopicTitle, setManualTopicTitle] = useState('')
  const [manualTopicAngle, setManualTopicAngle] = useState('')
  const [topicDraft, setTopicDraft] = useState({ title: '', angle: '' })
  const [saveStates, setSaveStates] = useState<Record<SaveKey, SaveState>>({
    workspace: idleState,
    accountProfiles: idleState,
    historical: idleState,
    comments: idleState,
    trend: idleState,
    video: idleState,
    manualTopic: idleState,
    topic: idleState,
    draft: idleState,
  })

  const accountProfileMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextSourceMaterial =>
          material.type === 'account_profile',
      ),
    [materials],
  )
  const selectedProfileMaterial = useMemo(
    () => {
      if (selectedProfileMaterialId === NEW_INPUT_ASSET_ID) return null
      return (
        accountProfileMaterials.find(
        (material) => material.id === selectedProfileMaterialId,
        ) ||
        accountProfileMaterials[0] ||
        null
      )
    },
    [accountProfileMaterials, selectedProfileMaterialId],
  )
  const historicalMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextSourceMaterial =>
          material.type === 'historical_posts',
      ),
    [materials],
  )
  const commentsMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextSourceMaterial => material.type === 'comments',
      ),
    [materials],
  )
  const trendMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TrendCsvSourceMaterial =>
          material.type === 'trend_csv',
      ),
    [materials],
  )
  const videoCreatorSamplesMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextSourceMaterial =>
          material.type === 'video_creator_samples',
      ),
    [materials],
  )
  const historicalMaterial = useMemo(
    () => {
      if (selectedHistoricalMaterialId === NEW_INPUT_ASSET_ID) return undefined
      return (
        historicalMaterials.find(
        (material) => material.id === selectedHistoricalMaterialId,
        ) ||
        historicalMaterials[0] ||
        undefined
      )
    },
    [historicalMaterials, selectedHistoricalMaterialId],
  )
  const commentsMaterial = useMemo(
    () => {
      if (selectedCommentsMaterialId === NEW_INPUT_ASSET_ID) return undefined
      return (
        commentsMaterials.find(
          (material) => material.id === selectedCommentsMaterialId,
        ) ||
        commentsMaterials[0] ||
        undefined
      )
    },
    [commentsMaterials, selectedCommentsMaterialId],
  )
  const videoCreatorSamplesMaterial = useMemo(
    () => {
      if (selectedVideoMaterialId === NEW_INPUT_ASSET_ID) return undefined
      return (
        videoCreatorSamplesMaterials.find(
        (material) => material.id === selectedVideoMaterialId,
        ) ||
        videoCreatorSamplesMaterials[0] ||
        undefined
      )
    },
    [videoCreatorSamplesMaterials, selectedVideoMaterialId],
  )
  const trendMaterial = useMemo(
    () => {
      if (selectedTrendMaterialId === NEW_INPUT_ASSET_ID) return undefined
      return (
        trendMaterials.find((material) => material.id === selectedTrendMaterialId) ||
        trendMaterials[0] ||
        undefined
      )
    },
    [trendMaterials, selectedTrendMaterialId],
  )
  const agentChatComposerRef = useRef<HTMLTextAreaElement | null>(null)
  const selectedAgentConversationId = selectedAgentConversation?.id

  useEffect(() => {
    if (activePage !== 'agents' || !selectedAgentConversationId) return
    window.setTimeout(() => {
      const composer = agentChatComposerRef.current
      if (!composer) return
      if (typeof composer.scrollIntoView === 'function') {
        composer.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
      composer.focus()
    }, 0)
  }, [activePage, selectedAgentConversationId])

  useEffect(() => {
    let active = true
    workspaceApi
      .list()
      .then((items) => {
        if (!active) return
        setWorkspaces(items)
        setSelectedWorkspaceId((current) => current || items[0]?.id || '')
        setLoading(false)
      })
      .catch((error: unknown) => {
        if (!active) return
        setLoadError(errorMessage(error))
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedWorkspaceId) {
      resetWorkspaceState()
      return
    }
    let active = true
    setLoading(true)
    setLoadError('')
    Promise.all([
      workspaceApi.get(selectedWorkspaceId),
      sourceMaterialApi.list(selectedWorkspaceId),
      analysisRunApi.list(selectedWorkspaceId),
      simulationRunApi.list(selectedWorkspaceId),
      skillApi.list(selectedWorkspaceId),
      agentApi.list(selectedWorkspaceId),
      agentConversationApi.list(selectedWorkspaceId),
      workflowAssetApi.list(selectedWorkspaceId),
      draftApi.list(selectedWorkspaceId),
      topicApi.list(selectedWorkspaceId),
    ])
      .then(
        ([
          loadedWorkspace,
          loadedMaterials,
          loadedRuns,
          loadedSimulationRuns,
          loadedSkills,
          loadedAgents,
          loadedAgentConversations,
          loadedWorkflowAssets,
          loadedDrafts,
          loadedTopics,
        ]) => {
        if (!active) return
        setWorkspace(loadedWorkspace)
        setMaterials(loadedMaterials)
        setAnalysisRuns(loadedRuns)
        setSimulationRuns(loadedSimulationRuns)
        setSkills(loadedSkills)
        setAgents(loadedAgents)
        setAgentConversations(loadedAgentConversations)
        setWorkflowAssets(loadedWorkflowAssets)
        setDrafts(loadedDrafts)
        setTopics(loadedTopics)
        setSelectedTopic(
          loadedTopics.find((topic) => topic.id === loadedWorkspace.currentTopicId) ||
            loadedTopics[0] ||
            null,
        )
        setWorkspaceName(loadedWorkspace.name)
        setPositioning(loadedWorkspace.accountPositioning)
        setProfileSourceMode('workspace')
        setSelectedProfileMaterialId(
          latestTextMaterial(loadedMaterials, 'account_profile')?.id || '',
        )
        setManualWorkflowProfile('')
        setAccountProfilesFile(null)
        setInputAssetPanel('historical_posts')
        setSelectedHistoricalMaterialId(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.id || '',
        )
        setSelectedCommentsMaterialId(
          latestTextMaterial(loadedMaterials, 'comments')?.id || '',
        )
        setSelectedTrendMaterialId(latestTrendMaterial(loadedMaterials)?.id || '')
        setSelectedVideoMaterialId(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.id || '',
        )
        setHistoricalPosts(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.content || '',
        )
        setComments(latestTextMaterial(loadedMaterials, 'comments')?.content || '')
        setVideoCreatorSamples(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.content || '',
        )
        setTrendKeyword(latestTrendMaterial(loadedMaterials)?.keyword || '')
        setSimulationTopic('')
        setCurrentRun(null)
        setSelectedRun(null)
        setSelectedSimulationRun(null)
        setSelectedSkill(null)
        setSelectedAgent(null)
        setSelectedAgentConversation(null)
        setAssetProposals([])
        setAgentMessageDraft('')
        setSelectedWorkflowAsset(null)
        setSelectedDraft(null)
        setDraftEditor('')
        setAnalysisStageViewsByWorkflow(emptyWorkflowStageViews())
        setSimulationStageViews([])
        setWorkflowOutputKindByWorkflow(defaultWorkflowOutputKinds())
        setSaveStates({
          workspace: idleState,
          accountProfiles: idleState,
          historical: idleState,
          comments: idleState,
          trend: idleState,
          video: idleState,
          manualTopic: idleState,
          topic: idleState,
          draft: idleState,
        })
        setLoading(false)
      },
      )
      .catch((error: unknown) => {
        if (!active) return
        setLoadError(errorMessage(error))
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [selectedWorkspaceId])

  function resetWorkspaceState() {
    setWorkspace(null)
    setMaterials([])
    setAnalysisRuns([])
    setSimulationRuns([])
    setSkills([])
    setAgents([])
    setWorkflowAssets([])
    setDrafts([])
    setTopics([])
    setSelectedTopic(null)
    setWorkspaceName('')
    setPositioning('')
    setProfileSourceMode('workspace')
    setSelectedProfileMaterialId('')
    setManualWorkflowProfile('')
    setAccountProfilesFile(null)
    setInputAssetPanel('historical_posts')
    setSelectedHistoricalMaterialId('')
    setSelectedCommentsMaterialId('')
    setSelectedTrendMaterialId('')
    setSelectedVideoMaterialId('')
    setHistoricalPosts('')
    setComments('')
    setVideoCreatorSamples('')
    setTrendKeyword('')
    setCurrentRun(null)
    setSelectedSimulationRun(null)
    setSelectedSkill(null)
    setSelectedAgent(null)
    setAgentConversations([])
    setSelectedAgentConversation(null)
    setAssetProposals([])
    setAgentMessageDraft('')
    setAgentConversationCreating(false)
    setSelectedWorkflowAsset(null)
    setSelectedDraft(null)
    setDraftEditor('')
    setAnalysisStageViewsByWorkflow(emptyWorkflowStageViews())
    setSimulationStageViews([])
    setWorkflowOutputKindByWorkflow(defaultWorkflowOutputKinds())
  }

  function setSaveState(key: SaveKey, state: SaveState) {
    setSaveStates((current) => ({ ...current, [key]: state }))
  }

  function openInputAsset(panel: InputAssetPanel) {
    setInputAssetPanel(panel)
    setActivePage('source-materials')
  }

  function chooseTextMaterial(material: TextSourceMaterial) {
    if (material.type === 'account_profile') {
      setSelectedProfileMaterialId(material.id)
      setPositioning(material.content)
      setProfileSourceMode('saved')
      setSaveState('workspace', idleState)
      setSaveState('accountProfiles', idleState)
      return
    }
    if (material.type === 'historical_posts') {
      setSelectedHistoricalMaterialId(material.id)
      setHistoricalPosts(material.content)
      setSaveState('historical', idleState)
      return
    }
    if (material.type === 'comments') {
      setSelectedCommentsMaterialId(material.id)
      setComments(material.content)
      setSaveState('comments', idleState)
      return
    }
    if (material.type === 'video_creator_samples') {
      setSelectedVideoMaterialId(material.id)
      setVideoCreatorSamples(material.content)
      setSaveState('video', idleState)
    }
  }

  function chooseTrendMaterial(material: TrendCsvSourceMaterial) {
    setSelectedTrendMaterialId(material.id)
    setTrendKeyword(material.keyword)
    setTrendFile(null)
    setSaveState('trend', idleState)
  }

  function startNewInputAsset(panel: InputAssetPanel) {
    if (panel === 'account_profiles') {
      setSelectedProfileMaterialId(NEW_INPUT_ASSET_ID)
      setProfileSourceMode('workspace')
      setPositioning('')
      setSaveState('workspace', idleState)
      setSaveState('accountProfiles', idleState)
      return
    }
    if (panel === 'historical_posts') {
      setSelectedHistoricalMaterialId(NEW_INPUT_ASSET_ID)
      setHistoricalPosts('')
      setSaveState('historical', idleState)
      return
    }
    if (panel === 'comments') {
      setSelectedCommentsMaterialId(NEW_INPUT_ASSET_ID)
      setComments('')
      setSaveState('comments', idleState)
      return
    }
    if (panel === 'trend_csv') {
      setSelectedTrendMaterialId(NEW_INPUT_ASSET_ID)
      setTrendKeyword('')
      setTrendFile(null)
      setSaveState('trend', idleState)
      return
    }
    setSelectedVideoMaterialId(NEW_INPUT_ASSET_ID)
    setVideoCreatorSamples('')
    setSaveState('video', idleState)
  }

  async function refreshWorkspaceSummary() {
    if (!workspace) return
    const [
      loadedWorkspace,
      loadedRuns,
      loadedSimulationRuns,
      loadedSkills,
      loadedAgents,
      loadedAgentConversations,
      loadedWorkflowAssets,
      loadedDrafts,
      loadedTopics,
    ] =
      await Promise.all([
      workspaceApi.get(workspace.id),
      analysisRunApi.list(workspace.id),
      simulationRunApi.list(workspace.id),
      skillApi.list(workspace.id),
      agentApi.list(workspace.id),
      agentConversationApi.list(workspace.id),
      workflowAssetApi.list(workspace.id),
      draftApi.list(workspace.id),
      topicApi.list(workspace.id),
    ])
    setWorkspace(loadedWorkspace)
    setWorkspaces((current) =>
      current.map((item) => (item.id === loadedWorkspace.id ? loadedWorkspace : item)),
    )
    setAnalysisRuns(loadedRuns)
    setSimulationRuns(loadedSimulationRuns)
    setSkills(loadedSkills)
    setAgents(loadedAgents)
    setAgentConversations(loadedAgentConversations)
    setWorkflowAssets(loadedWorkflowAssets)
    setDrafts(loadedDrafts)
    setTopics(loadedTopics)
    setSelectedTopic(
      loadedTopics.find((topic) => topic.id === loadedWorkspace.currentTopicId) ||
        loadedTopics[0] ||
        null,
    )
  }

  async function createWorkspace(event: FormEvent) {
    event.preventDefault()
    if (!createName.trim()) return
    setCreating(true)
    setLoadError('')
    try {
      const created = await workspaceApi.create(createName.trim(), createPositioning)
      setWorkspaces((current) => [created, ...current])
      setSelectedWorkspaceId(created.id)
      setCreateName('')
      setCreatePositioning('')
      setShowCreate(false)
    } catch (error) {
      setLoadError(errorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  function applyDemoSample(force = false, targetTab: WorkflowTab = workflowTab) {
    if (targetTab === 'account') {
      if (force || !positioning.trim()) setPositioning(SAMPLE_ACCOUNT_INPUT.positioning)
      if (force || !historicalPosts.trim()) {
        setHistoricalPosts(SAMPLE_ACCOUNT_INPUT.historicalPosts)
      }
      if (force || !comments.trim()) setComments(SAMPLE_ACCOUNT_INPUT.comments)
      if (force || !simulationTopic.trim()) {
        setSimulationTopic(SAMPLE_ACCOUNT_INPUT.simulationTopic)
      }
      return
    }
    if (targetTab === 'video') {
      if (force || !positioning.trim()) setPositioning(SAMPLE_VIDEO_INPUT.positioning)
      if (force || !videoCreatorSamples.trim()) {
        setVideoCreatorSamples(SAMPLE_VIDEO_INPUT.videoCreatorSamples)
      }
      if (force || !simulationTopic.trim()) {
        setSimulationTopic(SAMPLE_VIDEO_INPUT.simulationTopic)
      }
      return
    }
    if (force || !positioning.trim()) setPositioning(SAMPLE_TREND_INPUT.positioning)
    if (force || !trendKeyword.trim()) setTrendKeyword(SAMPLE_TREND_INPUT.keyword)
    if (force || !simulationTopic.trim()) {
      setSimulationTopic(SAMPLE_TREND_INPUT.simulationTopic)
    }
  }

  async function persistWorkspace(
    nextName = workspaceName,
    nextPositioning = positioning,
  ): Promise<Workspace> {
    if (!workspace) throw new Error('No workspace selected')
    if (
      nextName === workspace.name &&
      nextPositioning === workspace.accountPositioning
    ) {
      return workspace
    }
    const updated = await workspaceApi.update(workspace.id, {
      name: nextName,
      accountPositioning: nextPositioning,
      expectedUpdatedAt: workspace.updatedAt,
    })
    setWorkspace(updated)
    setWorkspaces((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    )
    return updated
  }

  async function persistTextMaterial(
    type:
      | 'account_profile'
      | 'historical_posts'
      | 'comments'
      | 'video_creator_samples',
    content: string,
    existing?: TextSourceMaterial,
  ): Promise<TextSourceMaterial> {
    if (!workspace) throw new Error('No workspace selected')
    if (existing && existing.content === content) return existing
    const saved = existing
      ? await sourceMaterialApi.update(existing.id, {
          content,
          expectedUpdatedAt: existing.updatedAt,
        })
      : await sourceMaterialApi.createText(
          workspace.id,
          type,
          type === 'historical_posts'
            ? '历史笔记'
            : type === 'comments'
              ? '评论样本'
              : type === 'account_profile'
                ? 'Account Profile'
                : '视频创作者样本',
          content,
        )
    if (saved.type !== type) {
      throw new Error('Saved source material type did not match request')
    }
    setMaterials((current) => [
      saved,
      ...current.filter((item) => item.id !== saved.id),
    ])
    if (type === 'account_profile') setSelectedProfileMaterialId(saved.id)
    if (type === 'historical_posts') setSelectedHistoricalMaterialId(saved.id)
    if (type === 'comments') setSelectedCommentsMaterialId(saved.id)
    if (type === 'video_creator_samples') setSelectedVideoMaterialId(saved.id)
    return saved
  }

  async function persistTrendCsv(
    file: File,
    keyword: string,
  ): Promise<TrendCsvSourceMaterial> {
    if (!workspace) throw new Error('No workspace selected')
    const uploaded = await sourceMaterialApi.uploadTrendCsv(
      workspace.id,
      file.name,
      keyword,
      file,
    )
    setMaterials((current) => [uploaded, ...current])
    setSelectedTrendMaterialId(uploaded.id)
    setTrendKeyword(uploaded.keyword)
    setTrendFile(null)
    return uploaded
  }

  async function uploadTrendCsv() {
    if (!workspace || !trendFile) {
      setSaveState('trend', { phase: 'error', message: '请选择 CSV 文件。' })
      return
    }
    setSaveState('trend', { phase: 'saving' })
    try {
      await persistTrendCsv(trendFile, trendKeyword)
      setSaveState('trend', { phase: 'saved' })
    } catch (error) {
      setSaveState('trend', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function uploadAccountProfilesCsv() {
    if (!workspace || !accountProfilesFile) {
      setSaveState('accountProfiles', {
        phase: 'error',
        message: '请选择包含 profile 的 CSV / TSV 文件。',
      })
      return
    }
    setSaveState('accountProfiles', { phase: 'saving' })
    try {
      const imported = await sourceMaterialApi.uploadAccountProfilesCsv(
        workspace.id,
        accountProfilesFile,
      )
      setMaterials((current) => [...imported.materials, ...current])
      setSelectedProfileMaterialId(imported.materials[0]?.id || '')
      setAccountProfilesFile(null)
      setSaveState('accountProfiles', { phase: 'saved' })
    } catch (error) {
      setSaveState('accountProfiles', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function ensureInputsSavedForRun(
    targetTab: WorkflowTab = workflowTab,
    includeProfile = true,
  ): Promise<{
    accountProfileMaterialId?: string
    manualAccountProfile?: string
    historical?: TextSourceMaterial
    comments?: TextSourceMaterial
    trend?: TrendCsvSourceMaterial
    video?: TextSourceMaterial
    simulationTopic: string
  }> {
    if (!workspace) throw new Error('No workspace selected')
    const sample =
      targetTab === 'account'
        ? SAMPLE_ACCOUNT_INPUT
        : targetTab === 'video'
          ? SAMPLE_VIDEO_INPUT
          : SAMPLE_TREND_INPUT
    const nextPositioning =
      mode === 'demo' && !positioning.trim() ? sample.positioning : positioning
    const nextSimulationTopic =
      mode === 'demo' && !simulationTopic.trim()
        ? sample.simulationTopic
        : simulationTopic
    if (nextPositioning !== positioning) setPositioning(nextPositioning)
    if (nextSimulationTopic !== simulationTopic) {
      setSimulationTopic(nextSimulationTopic)
    }

    setSaveState('workspace', { phase: 'saving' })
    await persistWorkspace(workspaceName, nextPositioning)
    setSaveState('workspace', { phase: 'saved' })

    const profileInput: {
      accountProfileMaterialId?: string
      manualAccountProfile?: string
    } = {}
    if (!includeProfile) {
      // Batch runs provide profile material IDs explicitly below.
    } else if (profileSourceMode === 'saved') {
      const material = selectedProfileMaterial
      if (!material) throw new Error('请选择一个已保存的 Account Profile。')
      profileInput.accountProfileMaterialId = material.id
    } else if (profileSourceMode === 'manual') {
      const manualProfile =
        mode === 'demo' && !manualWorkflowProfile.trim()
          ? sample.positioning
          : manualWorkflowProfile
      if (!manualProfile.trim()) throw new Error('请填写手动 Account Profile。')
      if (manualProfile !== manualWorkflowProfile) {
        setManualWorkflowProfile(manualProfile)
      }
      profileInput.manualAccountProfile = manualProfile
    }

    if (targetTab === 'account') {
      const nextHistoricalPosts =
        mode === 'demo' && !historicalPosts.trim()
          ? SAMPLE_ACCOUNT_INPUT.historicalPosts
          : historicalPosts
      const nextComments =
        mode === 'demo' && !comments.trim() ? SAMPLE_ACCOUNT_INPUT.comments : comments
      if (nextHistoricalPosts !== historicalPosts) setHistoricalPosts(nextHistoricalPosts)
      if (nextComments !== comments) setComments(nextComments)
      if (!nextHistoricalPosts.trim() || !nextComments.trim()) {
        throw new Error('请填写历史笔记和评论样本。')
      }

      setSaveState('historical', { phase: 'saving' })
      const savedHistorical = await persistTextMaterial(
        'historical_posts',
        nextHistoricalPosts,
        historicalMaterial,
      )
      setSaveState('historical', { phase: 'saved' })

      setSaveState('comments', { phase: 'saving' })
      const savedComments = await persistTextMaterial(
        'comments',
        nextComments,
        commentsMaterial,
      )
      setSaveState('comments', { phase: 'saved' })
      return {
        ...profileInput,
        historical: savedHistorical,
        comments: savedComments,
        simulationTopic: nextSimulationTopic,
      }
    }

    if (targetTab === 'video') {
      const nextVideoCreatorSamples =
        mode === 'demo' && !videoCreatorSamples.trim()
          ? SAMPLE_VIDEO_INPUT.videoCreatorSamples
          : videoCreatorSamples
      if (nextVideoCreatorSamples !== videoCreatorSamples) {
        setVideoCreatorSamples(nextVideoCreatorSamples)
      }
      if (!nextVideoCreatorSamples.trim()) {
        throw new Error('请填写视频创作者样本。')
      }

      setSaveState('video', { phase: 'saving' })
      const savedVideo = await persistTextMaterial(
        'video_creator_samples',
        nextVideoCreatorSamples,
        videoCreatorSamplesMaterial,
      )
      setSaveState('video', { phase: 'saved' })
      return {
        ...profileInput,
        video: savedVideo,
        simulationTopic: nextSimulationTopic,
      }
    }

    let savedTrend = trendMaterial
    if (trendFile) {
      setSaveState('trend', { phase: 'saving' })
      savedTrend = await persistTrendCsv(trendFile, trendKeyword)
      setSaveState('trend', { phase: 'saved' })
    } else if (mode === 'demo' && !savedTrend) {
      setSaveState('trend', { phase: 'saving' })
      const sampleFile = new File([SAMPLE_TREND_CSV], '数字游民趋势.csv', {
        type: 'text/csv',
      })
      savedTrend = await persistTrendCsv(
        sampleFile,
        trendKeyword || SAMPLE_TREND_INPUT.keyword,
      )
      setSaveState('trend', { phase: 'saved' })
    }
    if (!savedTrend) throw new Error('请上传热点 CSV。')
    if (trendKeyword.trim() && trendKeyword !== savedTrend.keyword) {
      setSaveState('trend', { phase: 'saving' })
      const updated = await sourceMaterialApi.update(savedTrend.id, {
        keyword: trendKeyword,
        expectedUpdatedAt: savedTrend.updatedAt,
      })
      if (updated.type !== 'trend_csv') {
        throw new Error('Updated source material type did not match request')
      }
      savedTrend = updated
      setMaterials((current) => [
        updated,
        ...current.filter((item) => item.id !== updated.id),
      ])
      setSaveState('trend', { phase: 'saved' })
    }
    return { ...profileInput, trend: savedTrend, simulationTopic: nextSimulationTopic }
  }

  function setAnalysisStageViews(
    targetTab: WorkflowTab,
    next: StageView[] | ((current: StageView[]) => StageView[]),
  ) {
    setAnalysisStageViewsByWorkflow((current) => ({
      ...current,
      [targetTab]: typeof next === 'function' ? next(current[targetTab]) : next,
    }))
  }

  function setAnalysisStageStatus(
    targetTab: WorkflowTab,
    key: string,
    patch: Partial<StageView>,
  ) {
    setAnalysisStageViews(targetTab, (current) =>
      current.map((stage) => (stage.key === key ? { ...stage, ...patch } : stage)),
    )
  }

  function setSimulationStageStatus(key: string, patch: Partial<StageView>) {
    setSimulationStageViews((current) =>
      current.map((stage) => (stage.key === key ? { ...stage, ...patch } : stage)),
    )
  }

  function setWorkflowOutputKind(targetTab: WorkflowTab, kind: WorkflowOutputKind) {
    setWorkflowOutputKindByWorkflow((current) => ({
      ...current,
      [targetTab]: kind,
    }))
  }

  async function runDiagnosis(targetTab: WorkflowTab = workflowTab) {
    if (!workspace) return
    setWorkflowTab(targetTab)
    setRunError('')
    setRunning(true)
    setWorkflowOutputKind(targetTab, 'analysis')
    setAnalysisStageViews(targetTab, stageSeed(targetTab))
    try {
      const savedInputs = await ensureInputsSavedForRun(targetTab)
      const created = await analysisRunApi.create(workspace.id, {
        workflowType: workflowFromTab(targetTab),
        accountProfileMaterialId: savedInputs.accountProfileMaterialId,
        manualAccountProfile: savedInputs.manualAccountProfile,
        historicalPostsMaterialId: savedInputs.historical?.id,
        commentsMaterialId: savedInputs.comments?.id,
        trendCsvMaterialId: savedInputs.trend?.id,
        videoCreatorSamplesMaterialId: savedInputs.video?.id,
        mode,
      })
      setCurrentRun(created)
      await runAnalysisGraphWorkflow(created, targetTab)
      await refreshWorkspaceSummary()
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveStates((current) =>
        Object.fromEntries(
          Object.entries(current).map(([key, state]) => [
            key,
            state.phase === 'saving' ? { phase: 'error', message } : state,
          ]),
        ) as Record<SaveKey, SaveState>,
      )
    } finally {
      setRunning(false)
    }
  }

  async function runBatchWorkflow(targetTab: WorkflowTab = workflowTab) {
    if (!workspace) return
    if (accountProfileMaterials.length === 0) {
      setRunError('请先在 Account Profiles 中上传或保存至少一个 Profile。')
      return
    }
    setWorkflowTab(targetTab)
    setRunError('')
    setRunning(true)
    try {
      const savedInputs = await ensureInputsSavedForRun(targetTab, false)
      await analysisRunApi.createBatch(workspace.id, {
        workflowType: workflowFromTab(targetTab),
        accountProfileMaterialIds: accountProfileMaterials.map((material) => material.id),
        historicalPostsMaterialId: savedInputs.historical?.id,
        commentsMaterialId: savedInputs.comments?.id,
        trendCsvMaterialId: savedInputs.trend?.id,
        videoCreatorSamplesMaterialId: savedInputs.video?.id,
        mode,
      })
      await refreshWorkspaceSummary()
      setActivePage('history')
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveStates((current) =>
        Object.fromEntries(
          Object.entries(current).map(([key, state]) => [
            key,
            state.phase === 'saving' ? { phase: 'error', message } : state,
          ]),
        ) as Record<SaveKey, SaveState>,
      )
    } finally {
      setRunning(false)
    }
  }

  function downloadAnalysisRunsCsv(targetTab?: WorkflowTab) {
    if (!workspace) return
    const url = analysisRunApi.exportCsvUrl(
      workspace.id,
      targetTab ? workflowFromTab(targetTab) : undefined,
    )
    const link = document.createElement('a')
    link.href = url
    link.download = `${targetTab ? workflowFromTab(targetTab) : 'analysis-runs'}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  async function runAnalysisGraphWorkflow(run: AnalysisRun, targetTab: WorkflowTab) {
    await new Promise<void>((resolve, reject) => {
      const source = new EventSource(`/api/analysis-runs/${run.id}/events`)
      const finish = async () => {
        source.close()
        const completed = await analysisRunApi.get(run.id)
        setCurrentRun(completed)
        setAnalysisStageViews(targetTab, stageSeedFromRun(completed))
        resolve()
      }
      const pollFallback = async () => {
        source.close()
        for (let attempt = 0; attempt < 40; attempt += 1) {
          const latest = await analysisRunApi.get(run.id)
          setCurrentRun(latest)
          setAnalysisStageViews(targetTab, stageSeedFromRun(latest))
          if (
            latest.status === 'completed' ||
            latest.status === 'partially_completed' ||
            latest.status === 'failed'
          ) {
            resolve()
            return
          }
          await new Promise((pollResolve) => window.setTimeout(pollResolve, 500))
        }
        throw new Error('事件流已断开，轮询运行状态超时。')
      }
      const fail = (error: unknown) => {
        source.close()
        reject(error)
      }
      const handleMessage = (message: MessageEvent<string>) => {
        const activity = JSON.parse(message.data) as ActivityEvent
        const eventType = activity.data.eventType
        if (eventType === 'stage.started' && activity.stageKey) {
          setAnalysisStageStatus(targetTab, activity.stageKey, { status: 'running' })
          return
        }
        if (eventType === 'stage.succeeded' && activity.stageKey) {
          const result = { ...activity.data }
          delete result.eventType
          setAnalysisStageStatus(targetTab, activity.stageKey, {
            status: 'completed',
            result,
            error: undefined,
          })
          return
        }
        if (eventType === 'stage.failed' && activity.stageKey) {
          setAnalysisStageStatus(targetTab, activity.stageKey, {
            status: 'failed',
            error: String(activity.data.error || '阶段执行失败'),
          })
          return
        }
        if (
          eventType === 'run.succeeded' ||
          eventType === 'run.partial' ||
          eventType === 'run.failed'
        ) {
          void finish().catch(fail)
        }
      }
      const eventTypes = [
        'run.created',
        'run.started',
        'stage.started',
        'stage.succeeded',
        'stage.failed',
        'run.partial',
        'run.succeeded',
        'run.failed',
      ]
      eventTypes.forEach((eventType) => {
        source.addEventListener(eventType, handleMessage as EventListener)
      })
      source.onerror = () => {
        void pollFallback().catch(fail)
      }
    })
  }

  async function runAudienceSimulation(draft?: Draft, targetTab: WorkflowTab = workflowTab) {
    if (!workspace) return
    setWorkflowTab(targetTab)
    setRunError('')
    setRunning(true)
    setCurrentRun(null)
    setWorkflowOutputKind(targetTab, 'simulation')
    setSimulationStageViews(
      SIMULATION_STAGES.map((stage) => ({ ...stage, status: 'waiting' })),
    )
    try {
      const savedInputs = draft
        ? { simulationTopic }
        : await ensureInputsSavedForRun(targetTab)
      if (draft) {
        setSaveState('workspace', { phase: 'saving' })
        await persistWorkspace()
        setSaveState('workspace', { phase: 'saved' })
      }
      const topicForSimulation = savedInputs.simulationTopic.trim()
      if (!draft && !topicForSimulation) throw new Error('请填写受众模拟选题。')
      const useSavedTopic =
        !draft && selectedTopic && topicForSimulation.includes(selectedTopic.title)
      const created = await simulationRunApi.create(workspace.id, {
        draftId: draft?.id,
        topicId: useSavedTopic ? selectedTopic.id : null,
        manualTopic: draft || useSavedTopic ? undefined : topicForSimulation,
        mode,
      })
      await runSimulationGraphWorkflow(created, targetTab)
      await refreshWorkspaceSummary()
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveStates((current) =>
        Object.fromEntries(
          Object.entries(current).map(([key, state]) => [
            key,
            state.phase === 'saving' ? { phase: 'error', message } : state,
          ]),
        ) as Record<SaveKey, SaveState>,
      )
    } finally {
      setRunning(false)
    }
  }

  async function runSimulationGraphWorkflow(run: SimulationRun, targetTab: WorkflowTab) {
    await new Promise<void>((resolve, reject) => {
      const source = new EventSource(`/api/simulation-runs/${run.id}/events`)
      const finish = async () => {
        source.close()
        const completed = await simulationRunApi.get(run.id)
        setWorkflowOutputKind(targetTab, 'simulation')
        setSimulationStageViews(stageSeedFromSimulation(completed))
        resolve()
      }
      const pollFallback = async () => {
        source.close()
        for (let attempt = 0; attempt < 40; attempt += 1) {
          const latest = await simulationRunApi.get(run.id)
          setWorkflowOutputKind(targetTab, 'simulation')
          setSimulationStageViews(stageSeedFromSimulation(latest))
          if (
            latest.status === 'completed' ||
            latest.status === 'partially_completed' ||
            latest.status === 'failed'
          ) {
            resolve()
            return
          }
          await new Promise((pollResolve) => window.setTimeout(pollResolve, 500))
        }
        throw new Error('受众模拟事件流已断开，轮询运行状态超时。')
      }
      const fail = (error: unknown) => {
        source.close()
        reject(error)
      }
      const handleMessage = (message: MessageEvent<string>) => {
        const activity = JSON.parse(message.data) as ActivityEvent
        const eventType = activity.data.eventType
        if (eventType === 'stage.started' && activity.stageKey) {
          setSimulationStageStatus(activity.stageKey, { status: 'running' })
          return
        }
        if (eventType === 'stage.succeeded' && activity.stageKey) {
          const result = { ...activity.data }
          delete result.eventType
          setSimulationStageStatus(activity.stageKey, {
            status: 'completed',
            result,
            error: undefined,
          })
          return
        }
        if (eventType === 'stage.failed' && activity.stageKey) {
          setSimulationStageStatus(activity.stageKey, {
            status: 'failed',
            error: String(activity.data.error || '阶段执行失败'),
          })
          return
        }
        if (
          eventType === 'run.succeeded' ||
          eventType === 'run.partial' ||
          eventType === 'run.failed'
        ) {
          void finish().catch(fail)
        }
      }
      const eventTypes = [
        'run.created',
        'run.started',
        'stage.started',
        'stage.succeeded',
        'stage.failed',
        'run.partial',
        'run.succeeded',
        'run.failed',
      ]
      eventTypes.forEach((eventType) => {
        source.addEventListener(eventType, handleMessage as EventListener)
      })
      source.onerror = () => {
        void pollFallback().catch(fail)
      }
    })
  }

  async function saveGeneratedTopic(candidate: TopicCandidate, run: AnalysisRun | null) {
    if (!workspace) throw new Error('No workspace selected')
    const created = await topicApi.create(workspace.id, {
      title: candidate.title,
      angle: candidate.angle,
      associatedPainPoint: candidate.pain || '',
      whyItFits: [candidate.whyFit, candidate.whyTrending].filter(Boolean).join('\n'),
      sourceAnalysisRunId: run?.id || null,
      sourceWorkflow: run ? undefined : 'manual',
    })
    await refreshWorkspaceSummary()
    return created
  }

  async function saveManualTopic(event: FormEvent) {
    event.preventDefault()
    if (!workspace || !manualTopicTitle.trim()) return
    setSaveState('manualTopic', { phase: 'saving' })
    try {
      const created = await topicApi.create(workspace.id, {
        title: manualTopicTitle.trim(),
        angle: manualTopicAngle,
        sourceWorkflow: 'manual',
      })
      setManualTopicTitle('')
      setManualTopicAngle('')
      setSelectedTopic(created)
      await refreshWorkspaceSummary()
      setSaveState('manualTopic', { phase: 'saved' })
    } catch (error) {
      setSaveState('manualTopic', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function selectTopic(topic: Topic) {
    const selected = await topicApi.select(topic.id)
    setSelectedTopic(selected)
    setSimulationTopic(`${selected.title}\n切入角度：${selected.angle}`)
    await refreshWorkspaceSummary()
  }

  async function archiveTopic(topic: Topic) {
    const archived = await topicApi.archive(topic.id)
    setTopics((current) =>
      current.map((item) => (item.id === archived.id ? archived : item)),
    )
    if (selectedTopic?.id === topic.id) setSelectedTopic(archived)
    await refreshWorkspaceSummary()
  }

  async function updateSelectedTopic() {
    if (!selectedTopic) return
    setSaveState('topic', { phase: 'saving' })
    try {
      const updated = await topicApi.update(selectedTopic.id, {
        title: topicDraft.title,
        angle: topicDraft.angle,
        expectedUpdatedAt: selectedTopic.updatedAt,
      })
      setSelectedTopic(updated)
      await refreshWorkspaceSummary()
      setSaveState('topic', { phase: 'saved' })
    } catch (error) {
      setSaveState('topic', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function generateDraftForTopic(topic: Topic) {
    setRunError('')
    setSaveState('draft', { phase: 'saving' })
    try {
      const draft = await draftApi.generateFromTopic(topic.id, mode)
      setSelectedDraft(draft)
      setDraftEditor(JSON.stringify(draft.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setActivePage('topics')
      setSaveState('draft', { phase: 'saved' })
      return draft
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveState('draft', { phase: 'error', message })
      throw error
    }
  }

  async function openDraft(draftId: string) {
    const draft = await draftApi.get(draftId)
    setSelectedDraft(draft)
    setDraftEditor(JSON.stringify(draft.editableContent, null, 2))
    setSaveState('draft', idleState)
  }

  async function saveDraftEdits() {
    if (!selectedDraft) return
    setSaveState('draft', { phase: 'saving' })
    try {
      const editableContent = JSON.parse(draftEditor) as Record<string, unknown>
      const updated = await draftApi.update(selectedDraft.id, {
        editableContent,
        expectedUpdatedAt: selectedDraft.updatedAt,
      })
      setSelectedDraft(updated)
      setDraftEditor(JSON.stringify(updated.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setSaveState('draft', { phase: 'saved' })
    } catch (error) {
      setSaveState('draft', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function openRun(runId: string, inOutput = false) {
    const run = await analysisRunApi.get(runId)
    setSelectedRun(run)
    if (inOutput) {
      const targetTab = workflowTabFromSource(run.workflowType)
      setCurrentRun(run)
      setAnalysisStageViews(targetTab, stageSeedFromRun(run))
      setWorkflowOutputKind(targetTab, 'analysis')
      setWorkflowTab(targetTab)
      setActivePage(activePageForWorkflowTab(targetTab))
    }
  }

  async function openSimulationRun(simulationId: string, inOutput = false) {
    const run = await simulationRunApi.get(simulationId)
    setSelectedSimulationRun(run)
    if (inOutput) {
      const targetTab = workflowTabFromSimulation(run)
      setCurrentRun(null)
      setSimulationStageViews(stageSeedFromSimulation(run))
      setWorkflowOutputKind(targetTab, 'simulation')
      setWorkflowTab(targetTab)
      const topic = run.inputSnapshot.topic as { title?: string; angle?: string }
      setSimulationTopic(
        [topic?.title || '', topic?.angle ? `切入角度：${topic.angle}` : '']
          .filter(Boolean)
          .join('\n'),
      )
      setActivePage(activePageForWorkflowTab(targetTab))
    }
  }

  async function openSkill(skillAssetId: string) {
    const skill = await skillApi.get(skillAssetId)
    setSelectedSkill(skill)
  }

  async function openAgent(agentAssetId: string) {
    const agent = await agentApi.get(agentAssetId)
    setSelectedAgent(agent)
    setSelectedAgentConversation((current) =>
      current?.agentAssetId === agent.id ? current : null,
    )
    setAgentMessageDraft('')
  }

  async function startAgentConversation(
    agent: Agent,
    title = `与 ${agent.displayName} 对话`,
    initialDraft = '',
  ) {
    if (!workspace) return
    setRunError('')
    setActivePage('agents')
    setAgentConversationCreating(true)
    try {
      const conversation = await agentConversationApi.create(
        workspace.id,
        agent.id,
        title,
      )
      setAgentConversations((current) => [
        conversation,
        ...current.filter((item) => item.id !== conversation.id),
      ])
      setSelectedAgentConversation(conversation)
      setAssetProposals([])
      setAgentMessageDraft(initialDraft)
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    } finally {
      setAgentConversationCreating(false)
    }
  }

  async function startMakerConversation(
    agentId: string,
    initialDraft: string,
  ) {
    setRunError('')
    setActivePage('agents')
    const summary = agents.find((agent) => agent.agentId === agentId)
    if (!summary) {
      setRunError('这个 workspace 还没有同步对应的 maker agent，请刷新后重试。')
      return
    }
    try {
      const agent =
        selectedAgent?.id === summary.id ? selectedAgent : await agentApi.get(summary.id)
      setSelectedAgent(agent)
      await startAgentConversation(
        agent,
        `与 ${agent.displayName} 对话`,
        initialDraft,
      )
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  async function openAgentConversation(conversationId: string) {
    setRunError('')
    const [conversation, proposals] = await Promise.all([
      agentConversationApi.get(conversationId),
      assetProposalApi.listForConversation(conversationId),
    ])
    setSelectedAgentConversation(conversation)
    setAssetProposals(proposals)
    setAgentMessageDraft('')
    const agent = agents.find((item) => item.id === conversation.agentAssetId)
    if (agent) {
      await openAgent(agent.id)
    }
  }

  async function sendAgentMessage(event: FormEvent) {
    event.preventDefault()
    if (!selectedAgentConversation || !agentMessageDraft.trim()) return
    setAgentSending(true)
    setRunError('')
    try {
      const conversation = await agentConversationApi.sendMessage(
        selectedAgentConversation.id,
        agentMessageDraft.trim(),
        mode,
      )
      setSelectedAgentConversation(conversation)
      setAssetProposals(
        await assetProposalApi.listForConversation(selectedAgentConversation.id),
      )
      setAgentMessageDraft('')
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    } finally {
      setAgentSending(false)
    }
  }

  async function openWorkflowAsset(workflowAssetId: string) {
    const workflowAsset = await workflowAssetApi.get(workflowAssetId)
    setSelectedWorkflowAsset(workflowAsset)
  }

  async function applyAssetProposal(proposal: AssetProposal) {
    setRunError('')
    try {
      const updated = await assetProposalApi.apply(proposal.id)
      setAssetProposals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  async function rejectAssetProposal(proposal: AssetProposal) {
    setRunError('')
    try {
      const updated = await assetProposalApi.reject(proposal.id)
      setAssetProposals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
    } catch (error) {
      setRunError(errorMessage(error))
    }
  }

  function renderStageResult(stage: StageView): ReactNode {
    if (!stage.result) return null
    const result = stage.result as Record<string, unknown>
    if (stage.key === 'profile' && result.profile) {
      return <ProfileView data={result.profile as Record<string, unknown>} />
    }
    if (stage.key === 'trend_analysis' && result.trendAnalysis) {
      return (
        <TrendAnalysisView data={result.trendAnalysis as Record<string, unknown>} />
      )
    }
    if (stage.key === 'pain_points') return <PainPointsView items={result.painPoints} />
    if (stage.key === 'topics') {
      return (
        <>
          {getTopicsFromStage(stage.result).map((topic) => (
            <GeneratedTopicCard key={topic.title} topic={topic} />
          ))}
        </>
      )
    }
    if (stage.key === 'titles') return <TitlesView items={result.titles} />
    if (stage.key === 'structure' && result.structure) {
      return <StructureView data={result.structure as Record<string, unknown>} />
    }
    if (stage.key === 'personas') return <PersonaListView items={result.personas} />
    if (stage.key === 'initial_reactions') {
      return <ReactionListView items={result.reactions} type="reaction" />
    }
    if (stage.key === 'debate_responses') {
      return <ReactionListView items={result.debateResponses} type="debate" />
    }
    if (stage.key === 'synthesis' && result.synthesis) {
      return <SynthesisView data={result.synthesis as Record<string, unknown>} />
    }
    if (stage.key === 'creator_profile' && result.creatorProfile) {
      return (
        <VideoCreatorProfileView
          data={result.creatorProfile as Record<string, unknown>}
        />
      )
    }
    if (stage.key === 'video_quality' && result.videoQuality) {
      return (
        <VideoQualityView data={result.videoQuality as Record<string, unknown>} />
      )
    }
    if (stage.key === 'incentive_fit' && result.incentiveFit) {
      return (
        <IncentiveFitView data={result.incentiveFit as Record<string, unknown>} />
      )
    }
    return <pre className="json-preview">{JSON.stringify(stage.result, null, 2)}</pre>
  }

  function draftDisplayTitle(draft: Draft) {
    const inputTopic = draft.inputSnapshot.topic as { title?: string } | undefined
    const structure = (draft.editableContent.structure || {}) as {
      topicChosen?: string
    }
    return structure.topicChosen || inputTopic?.title || '内容结构'
  }

  function renderDraftStructure(value: Record<string, unknown>) {
    const structure = (value.structure || null) as Record<string, unknown> | null
    if (structure) return <StructureView data={structure} />
    return <pre className="json-preview">{JSON.stringify(value, null, 2)}</pre>
  }

  function GeneratedTopicCard({ topic }: { topic: TopicCandidate }) {
    async function ensureSavedAndSelect() {
      const saved = await saveGeneratedTopic(topic, currentRun)
      await selectTopic(saved)
      return saved
    }
    return (
      <div className="topic">
        <h4>{topic.title}</h4>
        <div className="angle">
          切入角度：{topic.angle} · 对应痛点：{topic.pain || ''}
        </div>
        <div className="why">
          <b>为什么适合：</b> {topic.whyFit}
          {topic.whyTrending && (
            <>
              <br />
              <b>趋势依据：</b> {topic.whyTrending}
            </>
          )}
        </div>
        <div className="topic-actions">
          <button onClick={() => saveGeneratedTopic(topic, currentRun)}>
            保存到选题库
          </button>
          <button onClick={ensureSavedAndSelect}>设为当前选题</button>
          <button
            onClick={async () => {
              const saved = await ensureSavedAndSelect()
              setSimulationTopic(`${saved.title}\n切入角度：${saved.angle}`)
            }}
          >
            发送到受众模拟
          </button>
          <button
            onClick={async () => {
              const saved = await ensureSavedAndSelect()
              await generateDraftForTopic(saved)
            }}
          >
            生成内容结构
          </button>
          <button
            className="btn-fill"
            onClick={() => setSimulationTopic(`${topic.title}\n切入角度：${topic.angle}`)}
          >
            → 填入下期选题
          </button>
        </div>
      </div>
    )
  }

  useEffect(() => {
    if (selectedTopic) {
      setTopicDraft({ title: selectedTopic.title, angle: selectedTopic.angle })
    } else {
      setTopicDraft({ title: '', angle: '' })
    }
  }, [selectedTopic])

  const visibleTopics = topics.filter((topic) =>
    topicFilter === 'all' ? true : topic.sourceWorkflow === topicFilter,
  )

  return (
    <div className="app-shell">
      <aside className="workspace-sidebar">
        <div className="brand-row">
          <div className="logo">薯</div>
          <div>
            <strong>创作者工作区</strong>
            <span>Prototype migration</span>
          </div>
        </div>

        <label htmlFor="workspace-select">工作区</label>
        <select
          id="workspace-select"
          aria-label="选择工作区"
          value={selectedWorkspaceId}
          onChange={(event) => setSelectedWorkspaceId(event.target.value)}
        >
          {!workspaces.length && <option value="">尚无工作区</option>}
          {workspaces.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <button
          className="sidebar-create"
          type="button"
          onClick={() => setShowCreate((value) => !value)}
        >
          ＋ 新建工作区
        </button>

        {showCreate && (
          <form className="create-workspace" onSubmit={createWorkspace}>
            <label htmlFor="new-workspace-name">名称</label>
            <input
              id="new-workspace-name"
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
              required
            />
            <label htmlFor="new-workspace-positioning">账号定位</label>
            <textarea
              id="new-workspace-positioning"
              rows={3}
              value={createPositioning}
              onChange={(event) => setCreatePositioning(event.target.value)}
            />
            <button className="small-primary" disabled={creating}>
              {creating ? '创建中…' : '创建'}
            </button>
          </form>
        )}

        <nav aria-label="内容资产导航">
          <div className="nav-section-title">Input Assets</div>
          {INPUT_ASSET_DEFINITIONS.map((definition) => (
            <button
              key={definition.panel}
              className={
                activePage === 'source-materials' &&
                inputAssetPanel === definition.panel
                  ? 'active'
                  : ''
              }
              onClick={() => openInputAsset(definition.panel)}
            >
              <span>{definition.icon}</span> {definition.label}
            </button>
          ))}
          <div className="nav-section-title">Reusable Outputs</div>
          <button
            className={activePage === 'history' ? 'active' : ''}
            onClick={() => setActivePage('history')}
          >
            <span>◷</span> Analysis Results
          </button>
          <button
            className={activePage === 'topics' ? 'active' : ''}
            onClick={() => setActivePage('topics')}
          >
            <span>◇</span> Topic Library
          </button>
          <button
            className={activePage === 'simulations' ? 'active' : ''}
            onClick={() => setActivePage('simulations')}
          >
            <span>👥</span> Audience Simulations
          </button>
        </nav>
      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <div>
            <h1>创作者内容诊断与选题共创助手</h1>
            <p>左侧管理上下文与产物资产；右侧发起 workflow 调用并查看能力资产。</p>
          </div>
          <span className="badge">Workspace</span>
        </header>

        {loadError && <div className="error-banner">⚠ {loadError}</div>}
        {loading && <div className="loading-card">正在加载工作区…</div>}

        {!loading && !workspace && (
          <div className="empty-workspace">
            <h2>先创建一个创作者工作区</h2>
            <p>工作区用于保存账号定位、历史笔记、评论和热点 CSV。</p>
            <button className="primary" onClick={() => setShowCreate(true)}>
              新建工作区
            </button>
          </div>
        )}

        {!loading &&
          workspace &&
          activePage === 'account-profile' &&
          renderAccountProfilePage()}
        {!loading &&
          workspace &&
          activePage === 'source-materials' &&
          renderInputAssetsPage()}
        {!loading &&
          workspace &&
          activePage === 'account-diagnosis' &&
          renderWorkflowRunPage('account')}
        {!loading &&
          workspace &&
          activePage === 'trend-analysis' &&
          renderWorkflowRunPage('trend')}
        {!loading &&
          workspace &&
          activePage === 'video-quality' &&
          renderWorkflowRunPage('video')}

        {!loading && workspace && activePage === 'history' && renderHistoryPage()}
        {!loading && workspace && activePage === 'topics' && renderTopicsPage()}
        {!loading && workspace && activePage === 'drafts' && renderDraftsPage()}
        {!loading &&
          workspace &&
          activePage === 'simulations' &&
          renderSimulationsPage()}
        {!loading && workspace && activePage === 'skills' && renderSkillsPage()}
        {!loading && workspace && activePage === 'agents' && renderAgentsPage()}
        {!loading &&
          workspace &&
          activePage === 'workflows' &&
          renderWorkflowAssetsPage()}
      </main>

      <aside className="capability-sidebar">
        <div className="capability-header">
          <strong>能力资产</strong>
          <span>调用 workflow · 查看能力组合</span>
        </div>
        <nav aria-label="能力资产导航">
          <div className="nav-section-title">Workflow Calls</div>
          <button
            className={activePage === 'account-diagnosis' ? 'active' : ''}
            onClick={() => {
              setWorkflowTab('account')
              setActivePage('account-diagnosis')
            }}
          >
            <span>📊</span> Account Diagnosis
          </button>
          <button
            className={activePage === 'trend-analysis' ? 'active' : ''}
            onClick={() => {
              setWorkflowTab('trend')
              setActivePage('trend-analysis')
            }}
          >
            <span>🔥</span> Trend Analysis
          </button>
          <button
            className={activePage === 'video-quality' ? 'active' : ''}
            onClick={() => {
              setWorkflowTab('video')
              setActivePage('video-quality')
            }}
          >
            <span>🎬</span> Video Creator Quality
          </button>
          <div className="nav-section-title">Capability Assets</div>
          <button
            className={activePage === 'skills' ? 'active' : ''}
            onClick={() => setActivePage('skills')}
          >
            <span>✦</span> Skills
          </button>
          <button
            className={activePage === 'agents' ? 'active' : ''}
            onClick={() => setActivePage('agents')}
          >
            <span>◉</span> Agents
          </button>
          <button
            className={activePage === 'workflows' ? 'active' : ''}
            onClick={() => setActivePage('workflows')}
          >
            <span>⌘</span> Workflows
          </button>
        </nav>
        <div className="relationship-hint">
          <b>调用关系</b>
          <span>左侧 Input Assets 和 Reusable Outputs 提供上下文与产物；右侧 Workflow Calls 使用这些资产并由 Skills、Agents、Workflows 定义执行方式。</span>
        </div>
      </aside>
    </div>
  )

  async function saveAccountProfile() {
    setSaveState('workspace', { phase: 'saving' })
    setSaveState('accountProfiles', { phase: 'saving' })
    try {
      await persistWorkspace(workspaceName, positioning)
      const savedProfile = await persistTextMaterial(
        'account_profile',
        positioning,
        selectedProfileMaterial || accountProfileMaterials[0],
      )
      setSelectedProfileMaterialId(savedProfile.id)
      setSaveState('workspace', { phase: 'saved' })
      setSaveState('accountProfiles', { phase: 'saved' })
    } catch (error) {
      setSaveState('workspace', { phase: 'error', message: errorMessage(error) })
      setSaveState('accountProfiles', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function saveAccountProfileAsNew() {
    setSaveState('workspace', { phase: 'saving' })
    setSaveState('accountProfiles', { phase: 'saving' })
    try {
      await persistWorkspace(workspaceName, positioning)
      const savedProfile = await persistTextMaterial(
        'account_profile',
        positioning,
      )
      setSelectedProfileMaterialId(savedProfile.id)
      setProfileSourceMode('saved')
      setSaveState('workspace', { phase: 'saved' })
      setSaveState('accountProfiles', { phase: 'saved' })
    } catch (error) {
      setSaveState('workspace', { phase: 'error', message: errorMessage(error) })
      setSaveState('accountProfiles', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function saveHistoricalPosts() {
    setSaveState('historical', { phase: 'saving' })
    try {
      await persistTextMaterial('historical_posts', historicalPosts, historicalMaterial)
      setSaveState('historical', { phase: 'saved' })
    } catch (error) {
      setSaveState('historical', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveHistoricalPostsAsNew() {
    setSaveState('historical', { phase: 'saving' })
    try {
      await persistTextMaterial('historical_posts', historicalPosts)
      setSaveState('historical', { phase: 'saved' })
    } catch (error) {
      setSaveState('historical', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveComments() {
    setSaveState('comments', { phase: 'saving' })
    try {
      await persistTextMaterial('comments', comments, commentsMaterial)
      setSaveState('comments', { phase: 'saved' })
    } catch (error) {
      setSaveState('comments', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveCommentsAsNew() {
    setSaveState('comments', { phase: 'saving' })
    try {
      await persistTextMaterial('comments', comments)
      setSaveState('comments', { phase: 'saved' })
    } catch (error) {
      setSaveState('comments', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveVideoCreatorSamples() {
    setSaveState('video', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'video_creator_samples',
        videoCreatorSamples,
        videoCreatorSamplesMaterial,
      )
      setSaveState('video', { phase: 'saved' })
    } catch (error) {
      setSaveState('video', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveVideoCreatorSamplesAsNew() {
    setSaveState('video', { phase: 'saving' })
    try {
      await persistTextMaterial('video_creator_samples', videoCreatorSamples)
      setSaveState('video', { phase: 'saved' })
    } catch (error) {
      setSaveState('video', { phase: 'error', message: errorMessage(error) })
    }
  }

  function renderAccountProfilePage() {
    return (
      <div className="workspace-page asset-page">
        <section className="history-list">
          <div className="panel-title">◎ Account Profile</div>
          <p className="subline">
            账号定位现在作为可复用 context asset，被账号诊断、热点分析和受众模拟共同引用。
          </p>
          <div className="asset-card active">
            <b>{workspaceName || '未命名工作区'}</b>
            <span>{positioning.trim() ? '已填写账号定位' : '账号定位为空'}</span>
            <small>positioningVersion: {workspace?.positioningVersion ?? 0}</small>
          </div>
        </section>
        <section className="history-detail">
          <div className="detail-head">
            <div>
              <h2>Account Profile Asset</h2>
              <p>编辑后会更新当前 workspace 的账号定位资产。</p>
            </div>
          </div>
          <label htmlFor="workspace-name">工作区名称</label>
          <input
            id="workspace-name"
            value={workspaceName}
            onChange={(event) => {
              setWorkspaceName(event.target.value)
              setSaveState('workspace', idleState)
            }}
          />
          <label htmlFor="positioning">账号定位</label>
          <textarea
            id="positioning"
            rows={10}
            value={positioning}
            onChange={(event) => {
              setPositioning(event.target.value)
              setSaveState('workspace', idleState)
            }}
          />
          <div className="save-row">
            <button className="save-button" onClick={saveAccountProfile}>
              保存 Account Profile
            </button>
            <SaveIndicator state={saveStates.workspace} />
            <SaveIndicator state={saveStates.accountProfiles} />
          </div>
        </section>
      </div>
    )
  }

  function renderInputAssetsPage() {
    const definition = INPUT_ASSET_DEFINITION_BY_PANEL[inputAssetPanel]
    const panelMaterials: SourceMaterial[] =
      inputAssetPanel === 'account_profiles'
        ? accountProfileMaterials
        : inputAssetPanel === 'historical_posts'
          ? historicalMaterials
          : inputAssetPanel === 'comments'
            ? commentsMaterials
            : inputAssetPanel === 'trend_csv'
              ? trendMaterials
              : videoCreatorSamplesMaterials
    const selectedPanelAsset: SourceMaterial | null =
      inputAssetPanel === 'account_profiles'
        ? selectedProfileMaterial
        : inputAssetPanel === 'historical_posts'
          ? historicalMaterial || null
          : inputAssetPanel === 'comments'
            ? commentsMaterial || null
            : inputAssetPanel === 'trend_csv'
              ? trendMaterial || null
              : videoCreatorSamplesMaterial || null

    const selectInputAsset = (asset: SourceMaterial) => {
      if (isTrendCsvInputAsset(asset)) {
        chooseTrendMaterial(asset)
        return
      }
      chooseTextMaterial(asset)
    }

    const renderInputAssetDetail = () => {
      if (inputAssetPanel === 'account_profiles') {
        return (
          <>
            <div className="detail-head">
              <div>
                <h2>
                  {selectedProfileMaterial
                    ? selectedProfileMaterial.name
                    : '新建 Account Profile'}
                </h2>
                <p>{definition.description}</p>
              </div>
            </div>
            <div className="source-editor-card">
              <label htmlFor="workspace-name-inline">Workspace 名称</label>
              <input
                id="workspace-name-inline"
                value={workspaceName}
                onChange={(event) => {
                  setWorkspaceName(event.target.value)
                  setSaveState('workspace', idleState)
                }}
              />
              <label htmlFor="positioning-inline">账号定位</label>
              <textarea
                id="positioning-inline"
                rows={7}
                value={positioning}
                onChange={(event) => {
                  setPositioning(event.target.value)
                  setSaveState('workspace', idleState)
                }}
              />
              <div className="save-row">
                <button className="save-button" onClick={saveAccountProfile}>
                  {selectedProfileMaterial
                    ? '保存当前 Account Profile'
                    : '保存为 Account Profile'}
                </button>
                <button className="save-button" onClick={saveAccountProfileAsNew}>
                  另存为新 Account Profile
                </button>
                <SaveIndicator state={saveStates.workspace} />
                <SaveIndicator state={saveStates.accountProfiles} />
              </div>
              <p className="subline">
                当前实现会同步更新 workspace 默认定位；后续可拆成纯资产编辑。
              </p>
            </div>
            <div className="source-editor-card">
              <label htmlFor="account-profiles-file">
                Account Profiles 批量导入（CSV / TSV）
              </label>
              <input
                id="account-profiles-file"
                type="file"
                accept=".csv,.tsv"
                onChange={(event) => {
                  setAccountProfilesFile(event.target.files?.[0] || null)
                  setSaveState('accountProfiles', idleState)
                }}
              />
              <p className="subline">
                表头支持 name/profile、profile_name/account_profile、账号/定位。
              </p>
              <div className="save-row">
                <button className="save-button" onClick={uploadAccountProfilesCsv}>
                  上传并保存 Profiles
                </button>
                <SaveIndicator state={saveStates.accountProfiles} />
              </div>
            </div>
          </>
        )
      }

      if (inputAssetPanel === 'comments') {
        return (
          <>
            <div className="detail-head">
              <div>
                <h2>{commentsMaterial ? commentsMaterial.name : '新建 Comment Samples'}</h2>
                <p>{definition.description}</p>
              </div>
            </div>
            <div className="source-editor-card">
              <label htmlFor="comments">评论区原文（一行一条）</label>
              <textarea
                id="comments"
                rows={12}
                value={comments}
                onChange={(event) => {
                  setComments(event.target.value)
                  setSaveState('comments', idleState)
                }}
              />
              <div className="save-row">
                <button className="save-button" onClick={saveComments}>
                  {commentsMaterial ? '保存当前评论样本' : '保存为评论样本'}
                </button>
                <button className="save-button" onClick={saveCommentsAsNew}>
                  另存为新评论样本
                </button>
                <SaveIndicator state={saveStates.comments} />
              </div>
            </div>
          </>
        )
      }

      if (inputAssetPanel === 'trend_csv') {
        return (
          <>
            <div className="detail-head">
              <div>
                <h2>{trendMaterial ? trendMaterial.name : '上传新 Trend CSV'}</h2>
                <p>{definition.description}</p>
              </div>
            </div>
            <div className="source-editor-card">
              <label htmlFor="trend-keyword">话题关键词</label>
              <input
                id="trend-keyword"
                value={trendKeyword}
                onChange={(event) => {
                  setTrendKeyword(event.target.value)
                  setSaveState('trend', idleState)
                }}
                placeholder="例：数字游民、留学申请"
              />
              <label htmlFor="trend-file">热帖数据（CSV / TSV）</label>
              <input
                id="trend-file"
                type="file"
                accept=".csv,.tsv"
                onChange={(event) => {
                  setTrendFile(event.target.files?.[0] || null)
                  setSaveState('trend', idleState)
                }}
              />
              <div className="save-row">
                <button className="save-button" onClick={uploadTrendCsv}>
                  上传并保存 CSV
                </button>
                <SaveIndicator state={saveStates.trend} />
              </div>
              {trendMaterial && (
                <div className="csv-preview">
                  <div className="csv-summary">
                    <strong>{trendMaterial.originalFilename}</strong>
                    <span>{trendMaterial.rowCount} 条</span>
                  </div>
                  {trendMaterial.preview.length > 0 && (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            {Object.keys(trendMaterial.preview[0]).map((header) => (
                              <th key={header}>{header}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {trendMaterial.preview.map((row, index) => (
                            <tr key={index}>
                              {Object.keys(trendMaterial.preview[0]).map((header) => (
                                <td key={header}>{row[header] || ''}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )
      }

      if (inputAssetPanel === 'video_creator_samples') {
        return (
          <>
            <div className="detail-head">
              <div>
                <h2>
                  {videoCreatorSamplesMaterial
                    ? videoCreatorSamplesMaterial.name
                    : '新建 Video Creator Samples'}
                </h2>
                <p>{definition.description}</p>
              </div>
            </div>
            <div className="source-editor-card">
              <label htmlFor="video-creator-samples">
                视频创作者样本（创作者背景、视频样本、互动数据、运营备注）
              </label>
              <textarea
                id="video-creator-samples"
                rows={12}
                value={videoCreatorSamples}
                onChange={(event) => {
                  setVideoCreatorSamples(event.target.value)
                  setSaveState('video', idleState)
                }}
                placeholder="例：创作者 @xxx；样本视频标题、数据、画面/脚本/更新频率观察；是否商单驱动等"
              />
              <div className="save-row">
                <button className="save-button" onClick={saveVideoCreatorSamples}>
                  {videoCreatorSamplesMaterial
                    ? '保存当前视频创作者样本'
                    : '保存为视频创作者样本'}
                </button>
                <button className="save-button" onClick={saveVideoCreatorSamplesAsNew}>
                  另存为新视频创作者样本
                </button>
                <SaveIndicator state={saveStates.video} />
              </div>
            </div>
          </>
        )
      }

      return (
        <>
          <div className="detail-head">
            <div>
              <h2>
                {historicalMaterial ? historicalMaterial.name : '新建 Historical Posts'}
              </h2>
              <p>{definition.description}</p>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="historical-posts">
              主页 / 历史笔记 + 数据（格式：标题 ｜ 数据 ｜ 爆/平/差）
            </label>
            <textarea
              id="historical-posts"
              rows={12}
              value={historicalPosts}
              onChange={(event) => {
                setHistoricalPosts(event.target.value)
                setSaveState('historical', idleState)
              }}
            />
            <div className="save-row">
              <button className="save-button" onClick={saveHistoricalPosts}>
                {historicalMaterial ? '保存当前历史笔记' : '保存为历史笔记'}
              </button>
              <button className="save-button" onClick={saveHistoricalPostsAsNew}>
                另存为新历史笔记
              </button>
              <SaveIndicator state={saveStates.historical} />
            </div>
          </div>
        </>
      )
    }

    return (
      <div className="workspace-page asset-page">
        <section className="history-list">
          <div className="panel-title">
            {definition.icon} {definition.label}
          </div>
          <p className="subline">
            {definition.description}
          </p>
          <button
            className={`run-row ${selectedPanelAsset ? '' : 'active'}`}
            type="button"
            onClick={() => startNewInputAsset(inputAssetPanel)}
          >
            <span>{definition.newLabel}</span>
            <b>{definition.contentKind === 'file' ? 'upload' : 'new'}</b>
            <small>创建一个新的 {definition.singularLabel} 实例</small>
          </button>
          {panelMaterials.length === 0 ? (
            <div className="empty-card">{definition.emptyLabel}</div>
          ) : (
            panelMaterials.map((material) => (
              <button
                key={material.id}
                className={`run-row ${
                  selectedPanelAsset?.id === material.id ? 'active' : ''
                }`}
                type="button"
                onClick={() => selectInputAsset(material)}
              >
                <span>{material.name}</span>
                <b>{material.type}</b>
                <small>{inputAssetPreview(material)}</small>
                <small>更新于 {inputAssetUpdatedLabel(material)}</small>
              </button>
            ))
          )}
          <div className="asset-type-contract">
            <label>Asset Type Contract</label>
            <span>type: {definition.type}</span>
            <span>kind: {definition.contentKind}</span>
            <span>workflow roles: {definition.workflowRoles.join(', ')}</span>
            <span>context: {definition.contextSelectors.join(', ')}</span>
          </div>
        </section>
        <section className="history-detail source-editor-stack">
          {renderInputAssetDetail()}
        </section>
      </div>
    )
  }

  function renderWorkflowRunPage(targetTab: WorkflowTab) {
    const isAccount = targetTab === 'account'
    const isVideo = targetTab === 'video'
    const activeProfileContent =
      profileSourceMode === 'saved'
        ? selectedProfileMaterial?.content || ''
        : profileSourceMode === 'manual'
          ? manualWorkflowProfile
          : positioning
    const activeProfileLabel =
      profileSourceMode === 'saved'
        ? selectedProfileMaterial?.name || '未选择已保存 Profile'
        : profileSourceMode === 'manual'
          ? '手动输入 Profile'
          : 'Workspace Account Profile'
    const accountProfileRequirement = {
      name: 'Account Profile',
      status: activeProfileContent.trim() ? 'ready' : 'missing',
      detail: activeProfileContent.trim()
        ? `${activeProfileLabel}: ${activeProfileContent}`
        : '未填写账号定位',
    }
    const requiredAssets =
      targetTab === 'account'
        ? [
            accountProfileRequirement,
            {
              name: 'Historical Posts',
              status: historicalPosts.trim() ? 'ready' : 'missing',
              detail: `${historicalPosts.split('\n').filter(Boolean).length} 行`,
            },
            {
              name: 'Comment Samples',
              status: comments.trim() ? 'ready' : 'missing',
              detail: `${comments.split('\n').filter(Boolean).length} 行`,
            },
          ]
        : targetTab === 'video'
          ? [
              accountProfileRequirement,
              {
                name: 'Video Creator Samples',
                status: videoCreatorSamples.trim() ? 'ready' : 'missing',
                detail: `${videoCreatorSamples.split('\n').filter(Boolean).length} 行`,
              },
            ]
          : [
              accountProfileRequirement,
              {
                name: 'Trend CSV',
                status: trendMaterial || trendFile ? 'ready' : 'missing',
                detail: trendMaterial
                  ? `${trendMaterial.originalFilename} · ${trendMaterial.rowCount} 行`
                  : trendFile
                    ? trendFile.name
                    : '未上传 CSV',
              },
            ]
    const panelTitle = isAccount
      ? '📊 Account Diagnosis'
      : isVideo
        ? '🎬 Video Creator Quality'
        : '🔥 Trend Analysis'
    const description = isAccount
      ? '使用 Account Profile、Historical Posts 和 Comment Samples 生成账号诊断。'
      : isVideo
        ? '使用 Account Profile 和 Video Creator Samples 判断 AIGC 视频创作者质量与激励计划适配度。'
        : '使用 Account Profile 和 Trend CSV 生成热点分析。'
    const demoLabel = isAccount ? '账号诊断' : isVideo ? '视频创作者诊断' : '热点分析'
    const runLabel = isAccount
      ? '⚡ 生成账号诊断'
      : isVideo
        ? '⚡ 生成视频创作者诊断'
        : '⚡ 生成热点分析'
    return (
      <div className="prototype-grid">
        <section className="input-panel workflow-call-panel">
          <div className="panel-title">{panelTitle}</div>
          <p className="subline">{description}</p>
          <div className="source-editor-card compact">
            <label>Account Profile 来源</label>
            <div className="mode-switch">
              <button
                className={profileSourceMode === 'workspace' ? 'active' : ''}
                type="button"
                onClick={() => setProfileSourceMode('workspace')}
              >
                Workspace
              </button>
              <button
                className={profileSourceMode === 'saved' ? 'active' : ''}
                type="button"
                onClick={() => setProfileSourceMode('saved')}
              >
                已保存 Profile
              </button>
              <button
                className={profileSourceMode === 'manual' ? 'active' : ''}
                type="button"
                onClick={() => setProfileSourceMode('manual')}
              >
                手动输入
              </button>
            </div>
            {profileSourceMode === 'saved' && (
              <select
                value={selectedProfileMaterial?.id || ''}
                onChange={(event) => setSelectedProfileMaterialId(event.target.value)}
              >
                {accountProfileMaterials.length === 0 ? (
                  <option value="">还没有已保存 Profile</option>
                ) : (
                  accountProfileMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name}
                    </option>
                  ))
                )}
              </select>
            )}
            {profileSourceMode === 'manual' && (
              <textarea
                rows={4}
                value={manualWorkflowProfile}
                onChange={(event) => setManualWorkflowProfile(event.target.value)}
                placeholder="本次运行临时使用的账号/创作者定位，不覆盖 workspace profile。"
              />
            )}
          </div>
          {isAccount && (
            <div className="source-editor-card compact">
              <label htmlFor="workflow-historical-material">Historical Posts 实例</label>
              <select
                id="workflow-historical-material"
                value={historicalMaterial?.id || ''}
                onChange={(event) => {
                  const material = historicalMaterials.find(
                    (item) => item.id === event.target.value,
                  )
                  if (material) chooseTextMaterial(material)
                }}
              >
                {historicalMaterials.length === 0 ? (
                  <option value="">还没有保存的 Historical Posts</option>
                ) : (
                  historicalMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name}
                    </option>
                  ))
                )}
              </select>
              <label htmlFor="workflow-comments-material">Comment Samples 实例</label>
              <select
                id="workflow-comments-material"
                value={commentsMaterial?.id || ''}
                onChange={(event) => {
                  const material = commentsMaterials.find(
                    (item) => item.id === event.target.value,
                  )
                  if (material) chooseTextMaterial(material)
                }}
              >
                {commentsMaterials.length === 0 ? (
                  <option value="">还没有保存的 Comment Samples</option>
                ) : (
                  commentsMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name}
                    </option>
                  ))
                )}
              </select>
            </div>
          )}
          {targetTab === 'trend' && (
            <div className="source-editor-card compact">
              <label htmlFor="workflow-trend-material">Trend CSV Data 实例</label>
              <select
                id="workflow-trend-material"
                value={trendMaterial?.id || ''}
                onChange={(event) => {
                  const material = trendMaterials.find(
                    (item) => item.id === event.target.value,
                  )
                  if (material) chooseTrendMaterial(material)
                }}
              >
                {trendMaterials.length === 0 ? (
                  <option value="">还没有上传的 Trend CSV</option>
                ) : (
                  trendMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name} · {material.originalFilename}
                    </option>
                  ))
                )}
              </select>
            </div>
          )}
          {isVideo && (
            <div className="source-editor-card compact">
              <label htmlFor="workflow-video-material">Video Creator Samples 实例</label>
              <select
                id="workflow-video-material"
                value={videoCreatorSamplesMaterial?.id || ''}
                onChange={(event) => {
                  const material = videoCreatorSamplesMaterials.find(
                    (item) => item.id === event.target.value,
                  )
                  if (material) chooseTextMaterial(material)
                }}
              >
                {videoCreatorSamplesMaterials.length === 0 ? (
                  <option value="">还没有保存的 Video Creator Samples</option>
                ) : (
                  videoCreatorSamplesMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name}
                    </option>
                  ))
                )}
              </select>
            </div>
          )}
          <div className="asset-requirements">
            {requiredAssets.map((asset) => (
              <div className="asset-requirement" key={asset.name}>
                <div>
                  <b>{asset.name}</b>
                  <span>{asset.detail}</span>
                </div>
                <em className={asset.status}>{asset.status}</em>
              </div>
            ))}
          </div>
          <div className="workflow-shortcuts">
            <button onClick={() => openInputAsset('account_profiles')}>
              管理 Account Profiles
            </button>
            <button onClick={() => openInputAsset('historical_posts')}>
              管理输入资产
            </button>
          </div>
          {mode === 'demo' && (
            <button
              className="btn-fill"
              type="button"
              onClick={() => applyDemoSample(true, targetTab)}
            >
              ↺ 载入{demoLabel}演示样例
            </button>
          )}
          <div className="simulation-divider">
            <label htmlFor="simulation-topic">👥 下期选题（受众模拟的测试内容）</label>
            <textarea
              id="simulation-topic"
              rows={2}
              value={simulationTopic}
              onChange={(event) => setSimulationTopic(event.target.value)}
              placeholder="可从选题卡或选题库一键填入"
            />
          </div>

          <div className="mode-switch">
            <button
              className={mode === 'demo' ? 'active' : ''}
              onClick={() => {
                setMode('demo')
                applyDemoSample(false, targetTab)
              }}
            >
              演示模式
            </button>
            <button
              className={mode === 'live' ? 'active' : ''}
              onClick={() => setMode('live')}
            >
              实时生成
            </button>
          </div>
          <div className="action-row">
            <button
              className="primary"
              disabled={running}
              onClick={() => runDiagnosis(targetTab)}
            >
              {running ? '生成中…' : runLabel}
            </button>
            <button
              className="simulation-button"
              disabled={running || (mode === 'live' && !simulationTopic.trim())}
              onClick={() => runAudienceSimulation(undefined, targetTab)}
            >
              👥 受众模拟
            </button>
          </div>
          <div className="workflow-shortcuts">
            <button
              type="button"
              disabled={running || accountProfileMaterials.length === 0}
              onClick={() => runBatchWorkflow(targetTab)}
            >
              批量运行当前 Workflow（{accountProfileMaterials.length} Profiles）
            </button>
            <button type="button" onClick={() => downloadAnalysisRunsCsv(targetTab)}>
              下载结果 CSV
            </button>
          </div>
        </section>
        {renderWorkflowOutputPanel(
          targetTab,
          workflowOutputKindByWorkflow[targetTab] === 'simulation'
            ? simulationStageViews
            : analysisStageViewsByWorkflow[targetTab],
          workflowOutputKindByWorkflow[targetTab],
        )}
      </div>
    )
  }

  function renderWorkflowOutputPanel(
    targetTab: WorkflowTab,
    views: StageView[],
    outputKind: WorkflowOutputKind,
  ) {
    const isSimulation = outputKind === 'simulation'
    return (
      <section className="output-panel">
        {runError && <div className="error-banner">⚠ {runError}</div>}
        {!views.length ? (
          <div className="output-empty">
            <span>✓</span>
            <h2>
              {isSimulation
                ? '受众模拟待运行'
                : targetTab === 'account'
                  ? '账号诊断待运行'
                  : targetTab === 'video'
                    ? '视频创作者诊断待运行'
                    : '热点分析待运行'}
            </h2>
            <p>运行后结果会渐进渲染，并保存到 Analysis Results。</p>
          </div>
        ) : (
          views.map((stage) => (
            <div className="stage" key={stage.key}>
              <div className="stage-h">
                <div className="stage-n">{stage.n}</div>
                <h3>{stage.title}</h3>
                <div className={`stage-status ${stage.status}`}>
                  {stage.status === 'running'
                    ? '分析中…'
                    : stage.status === 'completed'
                      ? '已完成'
                      : stage.status === 'failed'
                        ? '失败'
                        : '等待中'}
                </div>
              </div>
              {stage.status === 'running' && (
                <div className="stage-loading">
                  <span className="spinner" />
                  分析中…
                </div>
              )}
              {stage.error && <div className="err">{stage.error}</div>}
              {renderStageResult(stage)}
            </div>
          ))
        )}
      </section>
    )
  }

  function renderHistoryPage() {
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">◷ Analysis Results</div>
          {analysisRuns.length === 0 ? (
            <div className="empty-card">暂无分析运行。</div>
          ) : (
            analysisRuns.map((run) => (
              <button
                key={run.id}
                className={`run-row ${selectedRun?.id === run.id ? 'active' : ''}`}
                onClick={() => openRun(run.id)}
              >
                <span>{workflowLabel(run.workflowType)}</span>
                <b>{run.status}</b>
                <small>{new Date(run.createdAt).toLocaleString()}</small>
              </button>
            ))
          )}
        </section>
        <section className="history-detail">
          {selectedRun ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{workflowLabel(selectedRun.workflowType)}</h2>
                  <p>
                    {selectedRun.status} ·{' '}
                    {new Date(selectedRun.createdAt).toLocaleString()}
                  </p>
                </div>
                <button onClick={() => openRun(selectedRun.id, true)}>
                  在输出区打开
                </button>
              </div>
              <label>原始输入快照</label>
              <pre className="json-preview">
                {JSON.stringify(selectedRun.inputSnapshot, null, 2)}
              </pre>
              <label>生成结果</label>
              {stageSeedFromRun(selectedRun).map((stage) => (
                <div className="stage compact" key={stage.key}>
                  <div className="stage-h">
                    <div className="stage-n">{stage.n}</div>
                    <h3>{stage.title}</h3>
                  </div>
                  {stage.error && <div className="err">{stage.error}</div>}
                  {renderStageResult(stage)}
                </div>
              ))}
            </>
          ) : (
            <div className="empty-card">选择一次运行查看输入和结果。</div>
          )}
        </section>
      </div>
    )
  }

  function renderTopicsPage() {
    return (
      <div className="workspace-page topics-page">
        <section className="history-list">
          <div className="panel-title">◇ Topic Library</div>
          <form className="manual-topic" onSubmit={saveManualTopic}>
            <input
              aria-label="手动选题标题"
              placeholder="手动输入选题"
              value={manualTopicTitle}
              onChange={(event) => setManualTopicTitle(event.target.value)}
            />
            <textarea
              aria-label="手动选题角度"
              placeholder="切入角度"
              rows={2}
              value={manualTopicAngle}
              onChange={(event) => setManualTopicAngle(event.target.value)}
            />
            <div className="save-row">
              <button className="small-primary">保存选题</button>
              <SaveIndicator state={saveStates.manualTopic} />
            </div>
          </form>
          <div className="filter-row">
            {(['all', 'account_diagnosis', 'trend_analysis', 'manual'] as const).map(
              (item) => (
                <button
                  key={item}
                  className={topicFilter === item ? 'active' : ''}
                  onClick={() => setTopicFilter(item)}
                >
                  {item === 'all'
                    ? '全部'
                    : item === 'account_diagnosis'
                      ? '账号诊断'
                      : item === 'trend_analysis'
                        ? '热点分析'
                        : '手动'}
                </button>
              ),
            )}
          </div>
          {visibleTopics.map((topic) => (
            <button
              key={topic.id}
              className={`topic-row ${selectedTopic?.id === topic.id ? 'active' : ''}`}
              onClick={() => setSelectedTopic(topic)}
            >
              <span>{topic.title}</span>
              <b>{topic.status}</b>
              <small>{topic.sourceWorkflow}</small>
            </button>
          ))}
        </section>
        <section className="history-detail">
          {selectedTopic ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{selectedTopic.title}</h2>
                  <p>
                    {selectedTopic.sourceWorkflow} · {selectedTopic.status}
                  </p>
                </div>
                <div className="detail-actions">
                  <button onClick={() => selectTopic(selectedTopic)}>设为当前</button>
                  <button onClick={() => archiveTopic(selectedTopic)}>归档</button>
                </div>
              </div>
              <label htmlFor="topic-title">标题</label>
              <input
                id="topic-title"
                value={topicDraft.title}
                onChange={(event) =>
                  setTopicDraft((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
              />
              <label htmlFor="topic-angle">切入角度</label>
              <textarea
                id="topic-angle"
                rows={4}
                value={topicDraft.angle}
                onChange={(event) =>
                  setTopicDraft((current) => ({
                    ...current,
                    angle: event.target.value,
                  }))
                }
              />
              <div className="save-row">
                <button className="save-button" onClick={updateSelectedTopic}>
                  保存选题编辑
                </button>
                <SaveIndicator state={saveStates.topic} />
              </div>
              <label>关联痛点</label>
              <div className="readonly-box">{selectedTopic.associatedPainPoint || '无'}</div>
              <label>为什么适合</label>
              <div className="readonly-box">{selectedTopic.whyItFits || '无'}</div>
            </>
          ) : (
            <div className="empty-card">选择或创建一个选题。</div>
          )}
        </section>
      </div>
    )
  }

  function renderDraftsPage() {
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">▱ Generated Structures</div>
          {drafts.length === 0 ? (
            <div className="empty-card">暂无内容结构或草稿。请先从选题卡生成内容结构。</div>
          ) : (
            drafts.map((draft) => (
              <button
                key={draft.id}
                className={`run-row ${selectedDraft?.id === draft.id ? 'active' : ''}`}
                onClick={() => openDraft(draft.id)}
              >
                <span>{draft.sourceWorkflow === 'trend_analysis' ? '热点结构' : '账号结构'}</span>
                <b>{draft.status}</b>
                <small>{new Date(draft.createdAt).toLocaleString()}</small>
              </button>
            ))
          )}
        </section>
        <section className="history-detail">
          {selectedDraft ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{draftDisplayTitle(selectedDraft)}</h2>
                  <p>
                    {selectedDraft.status} · {new Date(selectedDraft.createdAt).toLocaleString()}
                  </p>
                </div>
                <div className="detail-actions">
                  <button onClick={() => runAudienceSimulation(selectedDraft)}>
                    发送到受众模拟
                  </button>
                </div>
              </div>
              <label>生成快照（不可编辑）</label>
              {renderDraftStructure(selectedDraft.generatedSnapshot)}
              <label htmlFor="draft-editor">当前可编辑草稿 JSON</label>
              <textarea
                id="draft-editor"
                rows={12}
                value={draftEditor}
                onChange={(event) => {
                  setDraftEditor(event.target.value)
                  setSaveState('draft', idleState)
                }}
              />
              <div className="save-row">
                <button className="save-button" onClick={saveDraftEdits}>
                  保存草稿编辑
                </button>
                <SaveIndicator state={saveStates.draft} />
              </div>
              <label>输入快照</label>
              <pre className="json-preview">
                {JSON.stringify(selectedDraft.inputSnapshot, null, 2)}
              </pre>
            </>
          ) : (
            <div className="empty-card">选择一个 Draft 查看生成快照和当前编辑内容。</div>
          )}
        </section>
      </div>
    )
  }

  function renderSkillsPage() {
    const grouped = skills.reduce<Record<string, SkillSummary[]>>((acc, skill) => {
      acc[skill.category] = [...(acc[skill.category] || []), skill]
      return acc
    }, {})
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">✦ Skills</div>
          <p className="subline">
            Skills 是当前 workspace 可组合的产品能力资产；用户侧只读展示 contract，
            不提供通用 agent builder。
          </p>
          <div className="asset-maker-call">
            <span>不要手填 contract：描述你需要的能力，让 Skill Maker 生成定义提案。</span>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() =>
                startMakerConversation(
                  MAKER_AGENT_IDS.skill,
                  '我想设计一个新的 Skill，用来：\n\n它应该读取哪些 workspace 资产：\n\n它应该输出什么结构：',
                )
              }
            >
              让 Skill Maker 设计 Skill
            </button>
          </div>
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category} className="skill-group">
              <label>{category}</label>
              {items.map((skill) => (
                <button
                  key={skill.id}
                  className={`run-row ${selectedSkill?.id === skill.id ? 'active' : ''}`}
                  onClick={() => openSkill(skill.id)}
                >
                  <span>{skill.displayName}</span>
                  <b>{skill.status}</b>
                  <small>{skill.skillId}</small>
                </button>
              ))}
            </div>
          ))}
        </section>
        <section className="history-detail">
          {selectedSkill ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{selectedSkill.displayName}</h2>
                  <p>
                    {selectedSkill.skillId} · {selectedSkill.category} ·{' '}
                    {selectedSkill.version}
                  </p>
                </div>
                <span className={`tag ${selectedSkill.status === 'enabled' ? 'high' : 'mid'}`}>
                  {selectedSkill.status}
                </span>
              </div>
              <p>{selectedSkill.purpose}</p>
              <label>Artifact Effect</label>
              <div className="why">{selectedSkill.artifactEffect}</div>
              <label>Required Inputs</label>
              <ListBlock title="输入" items={selectedSkill.requiredInputs} />
              <label>Optional Inputs</label>
              <ListBlock title="可选" items={selectedSkill.optionalInputs} />
              <label>Composable With</label>
              <ListBlock title="下游 Skill" items={selectedSkill.composableWith} />
              <label>Failure Mode</label>
              <div className="why">{selectedSkill.failureMode}</div>
              <label>Context Policy</label>
              <pre className="json-preview">
                {JSON.stringify(selectedSkill.contextPolicy, null, 2)}
              </pre>
              <label>Output Schema</label>
              <pre className="json-preview">
                {JSON.stringify(selectedSkill.outputSchema, null, 2)}
              </pre>
              <label>Implementation Refs</label>
              <ListBlock title="代码引用" items={selectedSkill.implementationRefs} />
              {selectedSkill.userNotes && (
                <>
                  <label>Workspace Notes</label>
                  <div className="why">{selectedSkill.userNotes}</div>
                </>
              )}
            </>
          ) : (
            <div className="empty-card">选择一个 Skill 查看输入、输出和组合边界。</div>
          )}
        </section>
      </div>
    )
  }

  function renderAgentsPage() {
    const selectedAgentConversations = selectedAgent
      ? agentConversations.filter(
          (conversation) => conversation.agentAssetId === selectedAgent.id,
        )
      : []
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">◉ Agents</div>
          <p className="subline">
            Agent 是产品角色资产：system prompt + 多个 Skills +
            默认上下文边界。用户侧只读展示，不提供通用 agent builder。
          </p>
          <div className="asset-maker-call">
            <span>描述你需要的角色，Agent Maker 会组合 system prompt、skills 和上下文边界。</span>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() =>
                startMakerConversation(
                  MAKER_AGENT_IDS.agent,
                  '我想设计一个新的 Agent，用来：\n\n它应该具备哪些能力 / skills：\n\n它应该读取哪些资产，不应该读取哪些资产：',
                )
              }
            >
              让 Agent Maker 设计 Agent
            </button>
          </div>
          {runError && <div className="error-banner">⚠ {runError}</div>}
          {agents.map((agent) => (
            <button
              key={agent.id}
              className={`run-row ${selectedAgent?.id === agent.id ? 'active' : ''}`}
              onClick={() => openAgent(agent.id)}
            >
              <span>{agent.displayName}</span>
              <b>{agent.status}</b>
              <small>{agent.agentId}</small>
            </button>
          ))}
          {selectedAgent && (
            <>
              <div className="panel-title secondary-title">Conversations</div>
              <button
                className="small-primary"
                disabled={agentConversationCreating}
                onClick={() => startAgentConversation(selectedAgent)}
              >
                {agentConversationCreating ? '创建中…' : '＋ 开始对话'}
              </button>
              {selectedAgentConversations.length === 0 ? (
                <div className="empty-card compact-empty">暂无 agent 对话。</div>
              ) : (
                selectedAgentConversations.map((conversation) => (
                  <button
                    key={conversation.id}
                    className={`run-row ${
                      selectedAgentConversation?.id === conversation.id ? 'active' : ''
                    }`}
                    onClick={() => openAgentConversation(conversation.id)}
                  >
                    <span>{conversation.title}</span>
                    <b>{conversation.status}</b>
                    <small>{new Date(conversation.updatedAt).toLocaleString()}</small>
                  </button>
                ))
              )}
            </>
          )}
        </section>
        <section className="history-detail">
          {selectedAgent ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{selectedAgent.displayName}</h2>
                  <p>
                    {selectedAgent.agentId} · {selectedAgent.source} ·{' '}
                    {selectedAgent.version}
                  </p>
                </div>
                <span
                  className={`tag ${selectedAgent.status === 'enabled' ? 'high' : 'mid'}`}
                >
                  {selectedAgent.status}
                </span>
              </div>
              <p>{selectedAgent.purpose}</p>
              <label>System Prompt</label>
              <div className="why">{selectedAgent.systemPrompt}</div>
              <label>Skills</label>
              <ListBlock title="组合能力" items={selectedAgent.skillIds} />
              <label>Default Context Policy</label>
              <pre className="json-preview">
                {JSON.stringify(selectedAgent.defaultContextPolicy, null, 2)}
              </pre>
              {selectedAgent.userNotes && (
                <>
                  <label>Workspace Notes</label>
                  <div className="why">{selectedAgent.userNotes}</div>
                </>
              )}
              <label>Agent Conversation</label>
              {selectedAgentConversation ? (
                <>
                  <div className="agent-chat">
                    <p className="microcopy">
                      当前对话模式：{mode === 'demo' ? '演示模式' : '实时生成'}
                    </p>
                    {selectedAgentConversation.messages.length === 0 ? (
                      <div className="empty-card compact-empty">
                        发送第一条消息，Agent 会读取当前 workspace broad context。
                      </div>
                    ) : (
                      selectedAgentConversation.messages.map((message) => (
                        <div
                          className={`chat-message ${message.role}`}
                          key={message.id}
                        >
                          <b>{message.role === 'user' ? '你' : selectedAgent.displayName}</b>
                          <p>{message.content}</p>
                          {message.role === 'assistant' && (
                            <details>
                              <summary>
                                引用资产 {message.assetRefs.length} · Proposed Actions{' '}
                                {message.proposedActions.length}
                              </summary>
                              <pre className="json-preview">
                                {JSON.stringify(
                                  {
                                    assetRefs: message.assetRefs,
                                    proposedActions: message.proposedActions,
                                    modelMetadata: message.modelMetadata,
                                  },
                                  null,
                                  2,
                                )}
                              </pre>
                            </details>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                  {assetProposals.length > 0 && (
                    <div className="source-editor-card">
                      <label>Asset Proposals</label>
                      {assetProposals.map((proposal) => (
                        <div className="asset-requirement" key={proposal.id}>
                          <div>
                            <b>{proposal.title}</b>
                            <span>
                              {proposal.actionType} · {proposal.description}
                            </span>
                            {proposal.error && <span>错误：{proposal.error}</span>}
                          </div>
                          <div className="detail-actions">
                            <em className={proposal.status}>{proposal.status}</em>
                            {proposal.status === 'pending' && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => applyAssetProposal(proposal)}
                                >
                                  Apply
                                </button>
                                <button
                                  type="button"
                                  onClick={() => rejectAssetProposal(proposal)}
                                >
                                  Reject
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <form className="agent-chat-form" onSubmit={sendAgentMessage}>
                    <textarea
                      ref={agentChatComposerRef}
                      rows={3}
                      value={agentMessageDraft}
                      onChange={(event) => setAgentMessageDraft(event.target.value)}
                      placeholder="直接和这个 Agent 对话。第一版会引用 workspace 资产并提出建议，不会自动修改资产。"
                    />
                    <button
                      className="primary"
                      disabled={agentSending || !agentMessageDraft.trim()}
                    >
                      {agentSending ? '发送中…' : '发送给 Agent'}
                    </button>
                  </form>
                </>
              ) : (
                <div className="empty-card">
                  点击“开始对话”，直接调用这个 Agent。第一版只读 workspace
                  context，并把潜在修改保存为 proposed actions。
                </div>
              )}
            </>
          ) : (
            <div className="empty-card">
              选择一个 Agent 查看 system prompt、skills 和上下文边界。
            </div>
          )}
        </section>
      </div>
    )
  }

  function renderWorkflowAssetsPage() {
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">⌘ Workflows</div>
          <p className="subline">
            Workflow 是多 agent、多级 task 的产品工作流资产；用户侧只读展示计划结构，
            不提供通用流程编辑器。
          </p>
          <div className="asset-maker-call">
            <span>描述你想新增的创作者链路，Workflow Maker 会生成多 Agent task plan 提案。</span>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() =>
                startMakerConversation(
                  MAKER_AGENT_IDS.workflow,
                  '我想设计一个新的 Workflow，用来：\n\n输入资产包括：\n\n输出资产应该是：\n\n需要哪些 agent / skill 协作：',
                )
              }
            >
              让 Workflow Maker 设计 Workflow
            </button>
          </div>
          {workflowAssets.map((workflowAsset) => (
            <button
              key={workflowAsset.id}
              className={`run-row ${
                selectedWorkflowAsset?.id === workflowAsset.id ? 'active' : ''
              }`}
              onClick={() => openWorkflowAsset(workflowAsset.id)}
            >
              <span>{workflowAsset.displayName}</span>
              <b>{workflowAsset.status}</b>
              <small>{workflowAsset.workflowId}</small>
            </button>
          ))}
        </section>
        <section className="history-detail">
          {selectedWorkflowAsset ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{selectedWorkflowAsset.displayName}</h2>
                  <p>
                    {selectedWorkflowAsset.workflowId} ·{' '}
                    {selectedWorkflowAsset.source} ·{' '}
                    {selectedWorkflowAsset.version}
                  </p>
                </div>
                <span
                  className={`tag ${
                    selectedWorkflowAsset.status === 'enabled' ? 'high' : 'mid'
                  }`}
                >
                  {selectedWorkflowAsset.status}
                </span>
              </div>
              <p>{selectedWorkflowAsset.purpose}</p>
              <label>Artifact Effect</label>
              <div className="why">{selectedWorkflowAsset.artifactEffect}</div>
              <label>Entry Agents</label>
              <ListBlock
                title="入口角色"
                items={selectedWorkflowAsset.entryAgentIds}
              />
              <label>Agent Task Plan</label>
              <pre className="json-preview">
                {JSON.stringify(selectedWorkflowAsset.agentPlan, null, 2)}
              </pre>
              {selectedWorkflowAsset.userNotes && (
                <>
                  <label>Workspace Notes</label>
                  <div className="why">{selectedWorkflowAsset.userNotes}</div>
                </>
              )}
            </>
          ) : (
            <div className="empty-card">
              选择一个 Workflow 查看 entry agents、task 层级和产物影响。
            </div>
          )}
        </section>
      </div>
    )
  }

  function renderSimulationsPage() {
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">👥 Audience Simulations</div>
          {simulationRuns.length === 0 ? (
            <div className="empty-card">暂无受众模拟。</div>
          ) : (
            simulationRuns.map((run) => (
              <button
                key={run.id}
                className={`run-row ${
                  selectedSimulationRun?.id === run.id ? 'active' : ''
                }`}
                onClick={() => openSimulationRun(run.id)}
              >
                <span>受众模拟</span>
                <b>{run.status}</b>
                <small>{new Date(run.createdAt).toLocaleString()}</small>
              </button>
            ))
          )}
        </section>
        <section className="history-detail">
          {selectedSimulationRun ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>受众模拟</h2>
                  <p>
                    {selectedSimulationRun.status} ·{' '}
                    {new Date(selectedSimulationRun.createdAt).toLocaleString()}
                  </p>
                </div>
                <button onClick={() => openSimulationRun(selectedSimulationRun.id, true)}>
                  在输出区打开
                </button>
              </div>
              <label>原始输入快照</label>
              <pre className="json-preview">
                {JSON.stringify(selectedSimulationRun.inputSnapshot, null, 2)}
              </pre>
              <label>模拟结果</label>
              {stageSeedFromSimulation(selectedSimulationRun).map((stage) => (
                <div className="stage compact" key={stage.key}>
                  <div className="stage-h">
                    <div className="stage-n">{stage.n}</div>
                    <h3>{stage.title}</h3>
                  </div>
                  {stage.error && <div className="err">{stage.error}</div>}
                  {renderStageResult(stage)}
                </div>
              ))}
            </>
          ) : (
            <div className="empty-card">选择一次受众模拟查看输入和结果。</div>
          )}
        </section>
      </div>
    )
  }
}

function App() {
  if (window.location.pathname === '/health') return <HealthPage />
  return <WorkspaceApp />
}

export default App

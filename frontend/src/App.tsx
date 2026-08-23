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
  mediaAssetApi,
  simulationRunApi,
  skillApi,
  inputAssetApi,
  topicApi,
  workspaceApi,
  workflowAssetApi,
} from './api'
import { HealthPage } from './HealthPage'
import { AccountProfilePage } from './components/AccountProfilePage'
import { InputAssetsPage } from './components/InputAssetsPage'
import { MediaAssetsPage } from './components/MediaAssetsPage'
import {
  IncentiveFitView,
  ListBlock,
  PainPointsView,
  PersonaListView,
  ProfileView,
  ReactionListView,
  SaveIndicator,
  StructureView,
  SynthesisView,
  TitlesView,
  TrendAnalysisView,
  VideoCreatorProfileView,
  VideoQualityView,
  type SaveState,
} from './components/StageResultViews'
import { WorkspaceShell, type ActivePage } from './components/WorkspaceShell'
import {
  WorkflowOutputPanel,
  type StageView,
  type WorkflowOutputKind,
} from './components/WorkflowOutputPanel'
import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  inputAssetPreview,
  type InputAssetPanel,
} from './inputAssets'
import { usePendingAgentConversationPolling } from './hooks/usePendingAgentConversationPolling'
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
  SimulationRun,
  SimulationRunSummary,
  Skill,
  SkillSummary,
  InputAsset,
  MediaAsset,
  TextInputAsset,
  Topic,
  TopicSourceWorkflow,
  TrendCsvInputAsset,
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
import {
  previewXhsImportPackage,
  xhsPackageRelativePaths,
  type XhsImportPackagePreview,
} from './xhsCreatorProfile'

type SaveKey =
  | 'workspace'
  | 'accountProfiles'
  | 'historical'
  | 'comments'
  | 'trend'
  | 'video'
  | 'xhs'
  | 'manualTopic'
  | 'topic'
  | 'draft'
type WorkflowStageViews = Record<WorkflowTab, StageView[]>
type WorkflowOutputKinds = Record<WorkflowTab, WorkflowOutputKind>
type TextInputAssetPanel = Exclude<InputAssetPanel, 'trend_csv'>
type XhsImportPanel = Extract<
  TextInputAssetPanel,
  'historical_posts' | 'video_creator_samples' | 'xhs_creator_profiles'
>
type ConversationContextTarget = {
  assetType: 'skill' | 'agent' | 'workflow'
  assetId: string
}
const MAKER_AGENT_IDS = {
  skill: 'capability_maker',
  agent: 'capability_maker',
  workflow: 'capability_maker',
} as const
const NEW_INPUT_ASSET_ID = '__new_input_asset__'
const DEFAULT_WORKSPACE_NAME = '默认创作者工作区'

const TEXT_INPUT_ASSET_TYPE_BY_PANEL: Record<TextInputAssetPanel, TextInputAsset['type']> = {
  account_profiles: 'account_profile',
  historical_posts: 'historical_posts',
  comments: 'comments',
  video_creator_samples: 'video_creator_samples',
  xhs_creator_profiles: 'xhs_creator_profile',
}
const SAVE_KEY_BY_TEXT_INPUT_PANEL: Record<TextInputAssetPanel, SaveKey> = {
  account_profiles: 'accountProfiles',
  historical_posts: 'historical',
  comments: 'comments',
  video_creator_samples: 'video',
  xhs_creator_profiles: 'xhs',
}
const SAVE_KEY_BY_XHS_IMPORT_PANEL: Record<XhsImportPanel, SaveKey> = {
  historical_posts: 'historical',
  video_creator_samples: 'video',
  xhs_creator_profiles: 'xhs',
}
const XHS_IMPORT_TYPE_BY_PANEL: Record<
  XhsImportPanel,
  'historical_posts' | 'video_creator_samples' | 'xhs_creator_profile'
> = {
  historical_posts: 'historical_posts',
  video_creator_samples: 'video_creator_samples',
  xhs_creator_profiles: 'xhs_creator_profile',
}
const FORMATTER_SKILL_ID_BY_PANEL: Record<InputAssetPanel, string> = {
  account_profiles: 'input_asset.format_profile',
  historical_posts: 'input_asset.format_historical_posts',
  comments: 'input_asset.format_comments',
  trend_csv: 'input_asset.format_trend_csv_brief',
  video_creator_samples: 'input_asset.format_video_creator_samples',
  xhs_creator_profiles: 'input_asset.format_xhs_creator_profile',
}
const emptyTextInputAssetBatchFiles = (): Record<TextInputAssetPanel, File | null> => ({
  account_profiles: null,
  historical_posts: null,
  comments: null,
  video_creator_samples: null,
  xhs_creator_profiles: null,
})
const emptyXhsImportFiles = (): Record<XhsImportPanel, File | null> => ({
  historical_posts: null,
  video_creator_samples: null,
  xhs_creator_profiles: null,
})

function fileRelativePath(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
}

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
const SAMPLE_ASSET_NAMES = {
  qsheepProfile: 'Qsheep 留学账号',
  nomadProfile: '数字游民生活方式账号',
  videoProgramProfile: 'AIGC视频创作者激励计划',
  historicalPosts: '留学帖子数据合集',
  comments: '留学评论区合集',
  trendCsv: '数字游民趋势.csv',
  videoCreatorSamples: 'AI短剧创作者样本',
  xhsCreatorProfile: 'XHS QSheep 创作者主页',
} as const
const EMPTY_INPUT_ASSET_NAMES = {
  account_profile: '',
  historical_posts: '',
  comments: '',
  trend_csv: '',
  video_creator_samples: '',
  xhs_creator_profile: '',
} as const
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
核心人群：想从城市职场转向远程工作/自由职业的年轻人，尤其是文科生、非技术背景人群
内容主张：真实、可执行，不贩卖自由幻觉；强调技能准备、成本意识和风险管理
目标：围绕「如何开始数字游民生活」「旅居地选择与成本」「远程收入来源」持续产出`,
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

function latestTextMaterial(
  materials: InputAsset[],
  type: TextInputAsset['type'],
): TextInputAsset | undefined {
  return materials.find(
    (material): material is TextInputAsset => material.type === type,
  )
}

function latestTrendMaterial(
  materials: InputAsset[],
): TrendCsvInputAsset | undefined {
  return materials.find(
    (material): material is TrendCsvInputAsset =>
      material.type === 'trend_csv',
  )
}

async function chooseDefaultWorkspaceId(items: Workspace[]): Promise<string> {
  if (items.length === 1) return items[0].id
  const assetChecks = await Promise.all(
    items.map(async (item) => {
      try {
        const assets = await inputAssetApi.list(item.id)
        return { workspaceId: item.id, assetCount: assets.length }
      } catch {
        return { workspaceId: item.id, assetCount: 0 }
      }
    }),
  )
  return (
    assetChecks.find((item) => item.assetCount > 0)?.workspaceId ||
    items[0].id
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

function capabilityStatusClass(status: 'enabled' | 'disabled'): string {
  return `capability-status ${status}`
}

function newClientRequestKey(prefix: string): string {
  const randomId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${randomId}`
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

function WorkspaceApp() {
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('')
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [materials, setMaterials] = useState<InputAsset[]>([])
  const [mediaAssets, setMediaAssets] = useState<MediaAsset[]>([])
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
  const [showHelp, setShowHelp] = useState(false)
  const [activePage, setActivePage] = useState<ActivePage>('account-diagnosis')
  const [workflowTab, setWorkflowTab] = useState<WorkflowTab>('account')
  const [mode, setMode] = useState<GenerationMode>('demo')
  const [workspaceName, setWorkspaceName] = useState('')
  const [positioning, setPositioning] = useState('')
  const [accountProfileDraftName, setAccountProfileDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.qsheepProfile,
  )
  const [historicalPostsDraftName, setHistoricalPostsDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.historicalPosts,
  )
  const [commentsDraftName, setCommentsDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.comments,
  )
  const [trendCsvDraftName, setTrendCsvDraftName] = useState<string>(
    SAMPLE_ASSET_NAMES.trendCsv,
  )
  const [videoCreatorSamplesDraftName, setVideoCreatorSamplesDraftName] =
    useState<string>(SAMPLE_ASSET_NAMES.videoCreatorSamples)
  const [xhsCreatorProfileDraftName, setXhsCreatorProfileDraftName] =
    useState<string>(SAMPLE_ASSET_NAMES.xhsCreatorProfile)
  const [selectedProfileInputAssetId, setSelectedProfileInputAssetId] = useState('')
  const [inputAssetBatchFiles, setInputAssetBatchFiles] = useState<
    Record<TextInputAssetPanel, File | null>
  >(emptyTextInputAssetBatchFiles)
  const [xhsImportFiles, setXhsImportFiles] =
    useState<Record<XhsImportPanel, File | null>>(emptyXhsImportFiles)
  const [xhsPackageFiles, setXhsPackageFiles] = useState<File[]>([])
  const [xhsPackagePreview, setXhsPackagePreview] =
    useState<XhsImportPackagePreview | null>(null)
  const [xhsPackagePreviewError, setXhsPackagePreviewError] = useState('')
  const [xhsImportWarnings, setXhsImportWarnings] = useState<string[]>([])
  const [inputAssetPanel, setInputAssetPanel] =
    useState<InputAssetPanel>('historical_posts')
  const [selectedHistoricalInputAssetId, setSelectedHistoricalInputAssetId] =
    useState('')
  const [selectedCommentsInputAssetId, setSelectedCommentsInputAssetId] = useState('')
  const [selectedTrendInputAssetId, setSelectedTrendInputAssetId] = useState('')
  const [selectedVideoInputAssetId, setSelectedVideoInputAssetId] = useState('')
  const [selectedXhsCreatorProfileInputAssetId, setSelectedXhsCreatorProfileInputAssetId] =
    useState('')
  const [selectedVideoWorkflowMediaAssetIds, setSelectedVideoWorkflowMediaAssetIds] =
    useState<string[]>([])
  const [historicalPosts, setHistoricalPosts] = useState('')
  const [comments, setComments] = useState('')
  const [trendKeyword, setTrendKeyword] = useState('')
  const [trendFile, setTrendFile] = useState<File | null>(null)
  const [videoCreatorSamples, setVideoCreatorSamples] = useState('')
  const [xhsCreatorProfileContent, setXhsCreatorProfileContent] = useState('')
  const [inputAssetFormatterDraft, setInputAssetFormatterDraft] = useState('')
  const [inputAssetFormatterStatus, setInputAssetFormatterStatus] = useState('')
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
    xhs: idleState,
    manualTopic: idleState,
    topic: idleState,
    draft: idleState,
  })

  const accountProfileMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'account_profile',
      ),
    [materials],
  )
  const selectedProfileMaterial = useMemo(
    () => {
      if (selectedProfileInputAssetId === NEW_INPUT_ASSET_ID) return null
      return (
        accountProfileMaterials.find(
        (material) => material.id === selectedProfileInputAssetId,
        ) ||
        accountProfileMaterials[0] ||
        null
      )
    },
    [accountProfileMaterials, selectedProfileInputAssetId],
  )
  const historicalMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'historical_posts',
      ),
    [materials],
  )
  const commentsMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset => material.type === 'comments',
      ),
    [materials],
  )
  const trendMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TrendCsvInputAsset =>
          material.type === 'trend_csv',
      ),
    [materials],
  )
  const videoCreatorSamplesMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'video_creator_samples',
      ),
    [materials],
  )
  const xhsCreatorProfileMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'xhs_creator_profile',
      ),
    [materials],
  )
  const historicalMaterial = useMemo(
    () => {
      if (selectedHistoricalInputAssetId === NEW_INPUT_ASSET_ID) return undefined
      return (
        historicalMaterials.find(
        (material) => material.id === selectedHistoricalInputAssetId,
        ) ||
        historicalMaterials[0] ||
        undefined
      )
    },
    [historicalMaterials, selectedHistoricalInputAssetId],
  )
  const commentsMaterial = useMemo(
    () => {
      if (selectedCommentsInputAssetId === NEW_INPUT_ASSET_ID) return undefined
      return (
        commentsMaterials.find(
          (material) => material.id === selectedCommentsInputAssetId,
        ) ||
        commentsMaterials[0] ||
        undefined
      )
    },
    [commentsMaterials, selectedCommentsInputAssetId],
  )
  const videoCreatorSamplesMaterial = useMemo(
    () => {
      if (selectedVideoInputAssetId === NEW_INPUT_ASSET_ID) return undefined
      return (
        videoCreatorSamplesMaterials.find(
        (material) => material.id === selectedVideoInputAssetId,
        ) ||
        videoCreatorSamplesMaterials[0] ||
        undefined
      )
    },
    [videoCreatorSamplesMaterials, selectedVideoInputAssetId],
  )
  const xhsCreatorProfileMaterial = useMemo(
    () => {
      if (selectedXhsCreatorProfileInputAssetId === NEW_INPUT_ASSET_ID) {
        return undefined
      }
      return (
        xhsCreatorProfileMaterials.find(
          (material) => material.id === selectedXhsCreatorProfileInputAssetId,
        ) || undefined
      )
    },
    [xhsCreatorProfileMaterials, selectedXhsCreatorProfileInputAssetId],
  )
  const matchingXhsPackageMaterial = useMemo(() => {
    if (!xhsPackagePreview) return null
    const expectedName = `XHS ${xhsPackagePreview.displayName} 创作者主页`
    return (
      xhsCreatorProfileMaterials.find((material) => material.name === expectedName) ||
      null
    )
  }, [xhsCreatorProfileMaterials, xhsPackagePreview])
  const trendMaterial = useMemo(
    () => {
      if (selectedTrendInputAssetId === NEW_INPUT_ASSET_ID) return undefined
      return (
        trendMaterials.find((material) => material.id === selectedTrendInputAssetId) ||
        trendMaterials[0] ||
        undefined
      )
    },
    [trendMaterials, selectedTrendInputAssetId],
  )
  const videoWorkflowMediaAssets = useMemo(
    () =>
      selectedVideoWorkflowMediaAssetIds
        .map((assetId) => mediaAssets.find((asset) => asset.id === assetId))
        .filter((asset): asset is MediaAsset => Boolean(asset)),
    [mediaAssets, selectedVideoWorkflowMediaAssetIds],
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

  usePendingAgentConversationPolling({
    selectedAgentConversation,
    selectedAgentConversationId,
    setSelectedAgentConversation,
    setAgentConversations,
    setAssetProposals,
  })

  useEffect(() => {
    let active = true
    async function loadDefaultWorkspace() {
      try {
        const items = await workspaceApi.list()
        if (!active) return
        if (items.length > 0) {
          const workspaceId = await chooseDefaultWorkspaceId(items)
          if (!active) return
          setSelectedWorkspaceId((current) => current || workspaceId)
          return
        }
        const created = await workspaceApi.create(DEFAULT_WORKSPACE_NAME, '')
        if (!active) return
        setSelectedWorkspaceId(created.id)
      } catch (error: unknown) {
        if (!active) return
        setLoadError(errorMessage(error))
        setLoading(false)
      }
    }
    void loadDefaultWorkspace()
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
      inputAssetApi.list(selectedWorkspaceId),
      mediaAssetApi.list(selectedWorkspaceId),
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
          loadedMediaAssets,
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
        setMediaAssets(loadedMediaAssets)
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
        setSelectedProfileInputAssetId(
          latestTextMaterial(loadedMaterials, 'account_profile')?.id || '',
        )
        setAccountProfileDraftName(
          latestTextMaterial(loadedMaterials, 'account_profile')?.name ||
            SAMPLE_ASSET_NAMES.qsheepProfile,
        )
        setInputAssetBatchFiles(emptyTextInputAssetBatchFiles())
        setSelectedHistoricalInputAssetId(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.id || '',
        )
        setHistoricalPostsDraftName(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.name ||
            SAMPLE_ASSET_NAMES.historicalPosts,
        )
        setSelectedCommentsInputAssetId(
          latestTextMaterial(loadedMaterials, 'comments')?.id || '',
        )
        setCommentsDraftName(
          latestTextMaterial(loadedMaterials, 'comments')?.name ||
            SAMPLE_ASSET_NAMES.comments,
        )
        setSelectedTrendInputAssetId(latestTrendMaterial(loadedMaterials)?.id || '')
        setTrendCsvDraftName(
          latestTrendMaterial(loadedMaterials)?.name || SAMPLE_ASSET_NAMES.trendCsv,
        )
        setSelectedVideoInputAssetId(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.id || '',
        )
        setSelectedVideoWorkflowMediaAssetIds([])
        setVideoCreatorSamplesDraftName(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.name ||
            SAMPLE_ASSET_NAMES.videoCreatorSamples,
        )
        setSelectedXhsCreatorProfileInputAssetId(
          latestTextMaterial(loadedMaterials, 'xhs_creator_profile')?.id || '',
        )
        setXhsCreatorProfileDraftName(
          latestTextMaterial(loadedMaterials, 'xhs_creator_profile')?.name ||
            SAMPLE_ASSET_NAMES.xhsCreatorProfile,
        )
        setHistoricalPosts(
          latestTextMaterial(loadedMaterials, 'historical_posts')?.content || '',
        )
        setComments(latestTextMaterial(loadedMaterials, 'comments')?.content || '')
        setVideoCreatorSamples(
          latestTextMaterial(loadedMaterials, 'video_creator_samples')?.content || '',
        )
        setXhsCreatorProfileContent(
          latestTextMaterial(loadedMaterials, 'xhs_creator_profile')?.content || '',
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
          xhs: idleState,
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
    setMediaAssets([])
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
    setAccountProfileDraftName(SAMPLE_ASSET_NAMES.qsheepProfile)
    setHistoricalPostsDraftName(SAMPLE_ASSET_NAMES.historicalPosts)
    setCommentsDraftName(SAMPLE_ASSET_NAMES.comments)
    setTrendCsvDraftName(SAMPLE_ASSET_NAMES.trendCsv)
    setVideoCreatorSamplesDraftName(SAMPLE_ASSET_NAMES.videoCreatorSamples)
    setXhsCreatorProfileDraftName(SAMPLE_ASSET_NAMES.xhsCreatorProfile)
    setSelectedProfileInputAssetId('')
    setInputAssetBatchFiles(emptyTextInputAssetBatchFiles())
    setXhsImportFiles(emptyXhsImportFiles())
    setXhsPackageFiles([])
    setXhsPackagePreview(null)
    setXhsPackagePreviewError('')
    setXhsImportWarnings([])
    setInputAssetPanel('historical_posts')
    setSelectedHistoricalInputAssetId('')
    setSelectedCommentsInputAssetId('')
    setSelectedTrendInputAssetId('')
    setSelectedVideoInputAssetId('')
    setSelectedXhsCreatorProfileInputAssetId('')
    setSelectedVideoWorkflowMediaAssetIds([])
    setHistoricalPosts('')
    setComments('')
    setVideoCreatorSamples('')
    setXhsCreatorProfileContent('')
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
    setSaveStates({
      workspace: idleState,
      accountProfiles: idleState,
      historical: idleState,
      comments: idleState,
      trend: idleState,
      video: idleState,
      xhs: idleState,
      manualTopic: idleState,
      topic: idleState,
      draft: idleState,
    })
  }

  function setSaveState(key: SaveKey, state: SaveState) {
    setSaveStates((current) => ({ ...current, [key]: state }))
  }

  function clearXhsImportTransientState() {
    setXhsPackageFiles([])
    setXhsPackagePreview(null)
    setXhsPackagePreviewError('')
    setXhsImportWarnings([])
  }

  function openInputAsset(panel: InputAssetPanel) {
    setInputAssetPanel(panel)
    setInputAssetFormatterDraft('')
    setInputAssetFormatterStatus('')
    setActivePage('source-materials')
  }

  function chooseTextMaterial(material: TextInputAsset) {
    if (material.type === 'account_profile') {
      setSelectedProfileInputAssetId(material.id)
      setPositioning(material.content)
      setAccountProfileDraftName(material.name)
      setSaveState('workspace', idleState)
      setSaveState('accountProfiles', idleState)
      return
    }
    if (material.type === 'historical_posts') {
      setSelectedHistoricalInputAssetId(material.id)
      setHistoricalPostsDraftName(material.name)
      setHistoricalPosts(material.content)
      setSaveState('historical', idleState)
      return
    }
    if (material.type === 'comments') {
      setSelectedCommentsInputAssetId(material.id)
      setCommentsDraftName(material.name)
      setComments(material.content)
      setSaveState('comments', idleState)
      return
    }
    if (material.type === 'video_creator_samples') {
      setSelectedVideoInputAssetId(material.id)
      setVideoCreatorSamplesDraftName(material.name)
      setVideoCreatorSamples(material.content)
      setSaveState('video', idleState)
      return
    }
    if (material.type === 'xhs_creator_profile') {
      setSelectedXhsCreatorProfileInputAssetId(material.id)
      setXhsCreatorProfileDraftName(material.name)
      setXhsCreatorProfileContent(material.content)
      clearXhsImportTransientState()
      setSaveState('xhs', idleState)
    }
  }

  function chooseTrendMaterial(material: TrendCsvInputAsset) {
    setSelectedTrendInputAssetId(material.id)
    setTrendCsvDraftName(material.name)
    setTrendKeyword(material.keyword)
    setTrendFile(null)
    setSaveState('trend', idleState)
  }

  function startNewInputAsset(panel: InputAssetPanel) {
    if (panel === 'account_profiles') {
      setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
      setPositioning('')
      setAccountProfileDraftName(EMPTY_INPUT_ASSET_NAMES.account_profile)
      setSaveState('workspace', idleState)
      setSaveState('accountProfiles', idleState)
      return
    }
    if (panel === 'historical_posts') {
      setSelectedHistoricalInputAssetId(NEW_INPUT_ASSET_ID)
      setHistoricalPostsDraftName(EMPTY_INPUT_ASSET_NAMES.historical_posts)
      setHistoricalPosts('')
      setSaveState('historical', idleState)
      return
    }
    if (panel === 'comments') {
      setSelectedCommentsInputAssetId(NEW_INPUT_ASSET_ID)
      setCommentsDraftName(EMPTY_INPUT_ASSET_NAMES.comments)
      setComments('')
      setSaveState('comments', idleState)
      return
    }
    if (panel === 'trend_csv') {
      setSelectedTrendInputAssetId(NEW_INPUT_ASSET_ID)
      setTrendCsvDraftName(EMPTY_INPUT_ASSET_NAMES.trend_csv)
      setTrendKeyword('')
      setTrendFile(null)
      setSaveState('trend', idleState)
      return
    }
    if (panel === 'xhs_creator_profiles') {
      setSelectedXhsCreatorProfileInputAssetId(NEW_INPUT_ASSET_ID)
      setXhsCreatorProfileDraftName(EMPTY_INPUT_ASSET_NAMES.xhs_creator_profile)
      setXhsCreatorProfileContent('')
      clearXhsImportTransientState()
      setSaveState('xhs', idleState)
      return
    }
    setSelectedVideoInputAssetId(NEW_INPUT_ASSET_ID)
    setVideoCreatorSamplesDraftName(EMPTY_INPUT_ASSET_NAMES.video_creator_samples)
    setVideoCreatorSamples('')
    setSaveState('video', idleState)
  }

  async function applyInputAssetFormatter() {
    const raw = inputAssetFormatterDraft.trim()
    if (!raw) {
      setInputAssetFormatterStatus('请先粘贴需要整理的信息。')
      return
    }
    const skillId = FORMATTER_SKILL_ID_BY_PANEL[inputAssetPanel]
    const formatterSkill = skills.find((skill) => skill.skillId === skillId)
    if (!formatterSkill) {
      setInputAssetFormatterStatus('当前 workspace 还没有同步输入素材整理 skill，请刷新后重试。')
      return
    }
    setInputAssetFormatterStatus('整理中…')
    try {
      const result = await skillApi.invoke(formatterSkill.id, {
        input: {
          rawText: raw,
          targetAssetType: INPUT_ASSET_DEFINITION_BY_PANEL[inputAssetPanel].type,
        },
        mode,
      })
      const output = result.output
      const name = typeof output.name === 'string' ? output.name : ''
      const content = typeof output.content === 'string' ? output.content : ''
      const keyword = typeof output.keyword === 'string' ? output.keyword : ''
      const notes = typeof output.notes === 'string' ? output.notes : '已整理为草稿，请确认后保存。'
      if (inputAssetPanel === 'account_profiles') {
        setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setAccountProfileDraftName(name || '整理后的账号概况')
        setPositioning(content)
        setSaveState('workspace', idleState)
        setSaveState('accountProfiles', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'historical_posts') {
        setSelectedHistoricalInputAssetId(NEW_INPUT_ASSET_ID)
        setHistoricalPostsDraftName(name || '整理后的历史笔记合集')
        setHistoricalPosts(content)
        setSaveState('historical', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'comments') {
        setSelectedCommentsInputAssetId(NEW_INPUT_ASSET_ID)
        setCommentsDraftName(name || '整理后的评论样本合集')
        setComments(content)
        setSaveState('comments', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'trend_csv') {
        setSelectedTrendInputAssetId(NEW_INPUT_ASSET_ID)
        setTrendCsvDraftName(name || '整理后的趋势数据')
        setTrendKeyword(keyword)
        setSaveState('trend', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      if (inputAssetPanel === 'xhs_creator_profiles') {
        setSelectedXhsCreatorProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setXhsCreatorProfileDraftName(name || '整理后的小红书创作者主页')
        setXhsCreatorProfileContent(content)
        setSaveState('xhs', idleState)
        setInputAssetFormatterStatus(notes)
        return
      }
      setSelectedVideoInputAssetId(NEW_INPUT_ASSET_ID)
      setVideoCreatorSamplesDraftName(name || '整理后的视频创作者样本')
      setVideoCreatorSamples(content)
      setSaveState('video', idleState)
      setInputAssetFormatterStatus(notes)
    } catch (error) {
      setInputAssetFormatterStatus(`整理失败：${errorMessage(error)}`)
    }
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

  function applyDemoSample(force = false, targetTab: WorkflowTab = workflowTab) {
    if (targetTab === 'account') {
      if (force || !positioning.trim()) {
        setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setAccountProfileDraftName(SAMPLE_ASSET_NAMES.qsheepProfile)
        setPositioning(SAMPLE_ACCOUNT_INPUT.positioning)
      }
      if (force || !historicalPosts.trim()) {
        setSelectedHistoricalInputAssetId(NEW_INPUT_ASSET_ID)
        setHistoricalPostsDraftName(SAMPLE_ASSET_NAMES.historicalPosts)
        setHistoricalPosts(SAMPLE_ACCOUNT_INPUT.historicalPosts)
      }
      if (force || !comments.trim()) {
        setSelectedCommentsInputAssetId(NEW_INPUT_ASSET_ID)
        setCommentsDraftName(SAMPLE_ASSET_NAMES.comments)
        setComments(SAMPLE_ACCOUNT_INPUT.comments)
      }
      if (force || !simulationTopic.trim()) {
        setSimulationTopic(SAMPLE_ACCOUNT_INPUT.simulationTopic)
      }
      return
    }
    if (targetTab === 'video') {
      if (force || !positioning.trim()) {
        setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
        setAccountProfileDraftName(SAMPLE_ASSET_NAMES.videoProgramProfile)
        setPositioning(SAMPLE_VIDEO_INPUT.positioning)
      }
      if (force || !videoCreatorSamples.trim()) {
        setSelectedVideoInputAssetId(NEW_INPUT_ASSET_ID)
        setVideoCreatorSamplesDraftName(SAMPLE_ASSET_NAMES.videoCreatorSamples)
        setVideoCreatorSamples(SAMPLE_VIDEO_INPUT.videoCreatorSamples)
      }
      if (force || !simulationTopic.trim()) {
        setSimulationTopic(SAMPLE_VIDEO_INPUT.simulationTopic)
      }
      return
    }
    if (force || !positioning.trim()) {
      setSelectedProfileInputAssetId(NEW_INPUT_ASSET_ID)
      setAccountProfileDraftName(SAMPLE_ASSET_NAMES.nomadProfile)
      setPositioning(SAMPLE_TREND_INPUT.positioning)
    }
    if (force || !trendKeyword.trim()) {
      setSelectedTrendInputAssetId(NEW_INPUT_ASSET_ID)
      setTrendCsvDraftName(SAMPLE_ASSET_NAMES.trendCsv)
      setTrendKeyword(SAMPLE_TREND_INPUT.keyword)
    }
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
    return updated
  }

  async function persistTextMaterial(
    type:
      | 'account_profile'
      | 'historical_posts'
      | 'comments'
      | 'video_creator_samples'
      | 'xhs_creator_profile',
    content: string,
    existing?: TextInputAsset,
    nameOverride?: string,
  ): Promise<TextInputAsset> {
    if (!workspace) throw new Error('No workspace selected')
    const fallbackName =
      type === 'historical_posts'
        ? SAMPLE_ASSET_NAMES.historicalPosts
        : type === 'comments'
          ? SAMPLE_ASSET_NAMES.comments
          : type === 'account_profile'
            ? SAMPLE_ASSET_NAMES.qsheepProfile
            : type === 'video_creator_samples'
              ? SAMPLE_ASSET_NAMES.videoCreatorSamples
              : SAMPLE_ASSET_NAMES.xhsCreatorProfile
    const nextName = (nameOverride || existing?.name || fallbackName).trim()
    if (!nextName) throw new Error('请填写输入资产名称。')
    if (existing && existing.content === content && existing.name === nextName) {
      return existing
    }
    const saved = existing
      ? await inputAssetApi.update(existing.id, {
          name: nextName,
          content,
          expectedUpdatedAt: existing.updatedAt,
        })
      : await inputAssetApi.createText(
          workspace.id,
          type,
          nextName,
          content,
        )
    if (saved.type !== type) {
      throw new Error('Saved input asset type did not match request')
    }
    setMaterials((current) => [
      saved,
      ...current.filter((item) => item.id !== saved.id),
    ])
    if (type === 'account_profile') {
      setSelectedProfileInputAssetId(saved.id)
      setAccountProfileDraftName(saved.name)
    }
    if (type === 'historical_posts') {
      setSelectedHistoricalInputAssetId(saved.id)
      setHistoricalPostsDraftName(saved.name)
    }
    if (type === 'comments') {
      setSelectedCommentsInputAssetId(saved.id)
      setCommentsDraftName(saved.name)
    }
    if (type === 'video_creator_samples') {
      setSelectedVideoInputAssetId(saved.id)
      setVideoCreatorSamplesDraftName(saved.name)
    }
    if (type === 'xhs_creator_profile') {
      setSelectedXhsCreatorProfileInputAssetId(saved.id)
      setXhsCreatorProfileDraftName(saved.name)
      setXhsCreatorProfileContent(saved.content)
    }
    return saved
  }

  async function persistTrendCsv(
    file: File,
    keyword: string,
    name = trendCsvDraftName,
  ): Promise<TrendCsvInputAsset> {
    if (!workspace) throw new Error('No workspace selected')
    const cleanName = name.trim()
    if (!cleanName) throw new Error('请填写趋势 CSV 名称。')
    const uploaded = await inputAssetApi.uploadTrendCsv(
      workspace.id,
      cleanName,
      keyword,
      file,
    )
    setMaterials((current) => [uploaded, ...current])
    setSelectedTrendInputAssetId(uploaded.id)
    setTrendCsvDraftName(uploaded.name)
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
      await persistTrendCsv(trendFile, trendKeyword, trendCsvDraftName)
      setSaveState('trend', { phase: 'saved' })
    } catch (error) {
      setSaveState('trend', { phase: 'error', message: errorMessage(error) })
    }
  }

  function setInputAssetBatchFile(panel: TextInputAssetPanel, file: File | null) {
    setInputAssetBatchFiles((current) => ({ ...current, [panel]: file }))
    setSaveState(SAVE_KEY_BY_TEXT_INPUT_PANEL[panel], idleState)
  }

  async function uploadTextInputAssetsCsv(panel: TextInputAssetPanel) {
    const file = inputAssetBatchFiles[panel]
    const saveKey = SAVE_KEY_BY_TEXT_INPUT_PANEL[panel]
    if (!workspace || !file) {
      setSaveState(saveKey, {
        phase: 'error',
        message: '请选择 CSV / TSV 文件。',
      })
      return
    }
    setSaveState(saveKey, { phase: 'saving' })
    try {
      const imported = await inputAssetApi.uploadTextCsv(
        workspace.id,
        TEXT_INPUT_ASSET_TYPE_BY_PANEL[panel],
        file,
      )
      setMaterials((current) => [...imported.materials, ...current])
      const first = imported.materials[0]
      if (first) chooseTextMaterial(first)
      setInputAssetBatchFiles((current) => ({ ...current, [panel]: null }))
      setSaveState(saveKey, { phase: 'saved' })
    } catch (error) {
      setSaveState(saveKey, {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  function setXhsImportFile(panel: XhsImportPanel, file: File | null) {
    setXhsImportFiles((current) => ({ ...current, [panel]: file }))
    setXhsImportWarnings([])
    setSaveState(SAVE_KEY_BY_XHS_IMPORT_PANEL[panel], idleState)
  }

  async function uploadXhsImport(panel: XhsImportPanel) {
    const file = xhsImportFiles[panel]
    const saveKey = SAVE_KEY_BY_XHS_IMPORT_PANEL[panel]
    if (!workspace || !file) {
      setSaveState(saveKey, {
        phase: 'error',
        message: '请选择 XHS 导出 JSON / Markdown 文件。',
      })
      return
    }
    setSaveState(saveKey, { phase: 'saving' })
    try {
      const imported = await inputAssetApi.uploadXhsImport(
        workspace.id,
        XHS_IMPORT_TYPE_BY_PANEL[panel],
        file,
      )
      setMaterials((current) => [
        imported.inputAsset,
        ...current.filter((item) => item.id !== imported.inputAsset.id),
      ])
      chooseTextMaterial(imported.inputAsset)
      setXhsImportFiles((current) => ({ ...current, [panel]: null }))
      setXhsImportWarnings(imported.warnings)
      const warningSuffix =
        imported.warnings.length > 0 ? `；${imported.warnings.length} 条提示` : ''
      setSaveState(saveKey, {
        phase: 'saved',
        message: `已导入 ${imported.parsedNoteCount} 条笔记${warningSuffix}`,
      })
    } catch (error) {
      setSaveState(saveKey, {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function setXhsImportPackageFiles(files: File[]) {
    setXhsPackageFiles(files)
    setXhsImportWarnings([])
    setXhsPackagePreview(null)
    setXhsPackagePreviewError('')
    setSaveState('xhs', idleState)
    if (files.length === 0) return
    try {
      const preview = await previewXhsImportPackage(files)
      if (!preview) {
        setXhsPackagePreviewError(
          '没有找到可预览的 xhs_creator_profile.json / profile.json。',
        )
        return
      }
      setXhsPackagePreview(preview)
    } catch (error) {
      setXhsPackagePreviewError(errorMessage(error))
    }
  }

  async function uploadXhsImportPackage(saveAsNew = false) {
    if (!workspace) {
      setSaveState('xhs', {
        phase: 'error',
        message: '工作区尚未加载。',
      })
      return
    }
    if (xhsPackageFiles.length === 0) {
      setSaveState('xhs', {
        phase: 'error',
        message: '请选择包含 profile JSON 和 images 目录的文件夹。',
      })
      return
    }

    const profileFile =
      xhsPackageFiles.find((file) =>
        /(^|\/)(xhs_creator_profile|profile)\.json$/i.test(fileRelativePath(file)),
      ) ||
      xhsPackageFiles.find((file) =>
        fileRelativePath(file).toLowerCase().endsWith('.json'),
      )
    if (!profileFile) {
      setSaveState('xhs', {
        phase: 'error',
        message: '文件夹中没有找到 xhs_creator_profile.json 或 profile.json。',
      })
      return
    }

    const packageRelativePaths = xhsPackageRelativePaths(xhsPackageFiles)
    const mediaFiles = xhsPackageFiles.filter((file) => file !== profileFile)
    const relativePaths = mediaFiles.map(
      (file) => packageRelativePaths[xhsPackageFiles.indexOf(file)] || file.name,
    )
    setSaveState('xhs', { phase: 'saving' })
    try {
      const imported = await inputAssetApi.uploadXhsImportPackage(
        workspace.id,
        profileFile,
        mediaFiles,
        relativePaths,
        '',
        saveAsNew,
      )
      setMaterials((current) => [
        imported.inputAsset,
        ...current.filter((item) => item.id !== imported.inputAsset.id),
      ])
      setMediaAssets((current) => [
        ...imported.mediaAssets,
        ...current.filter(
          (item) => !imported.mediaAssets.some((asset) => asset.id === item.id),
        ),
      ])
      chooseTextMaterial(imported.inputAsset)
      setXhsPackageFiles([])
      setXhsPackagePreview(null)
      setXhsPackagePreviewError('')
      setXhsImportWarnings(imported.warnings)
      const warningSuffix =
        imported.warnings.length > 0 ? `；${imported.warnings.length} 条提示` : ''
      setSaveState('xhs', {
        phase: 'saved',
        message: `已导入 ${imported.parsedNoteCount} 条笔记和 ${imported.mediaAssets.length} 张封面${warningSuffix}`,
      })
    } catch (error) {
      setSaveState('xhs', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function ensureInputsSavedForRun(
    targetTab: WorkflowTab = workflowTab,
    includeProfile = true,
  ): Promise<{
    accountProfileInputAssetId?: string
    manualAccountProfile?: string
    historical?: TextInputAsset
    comments?: TextInputAsset
    trend?: TrendCsvInputAsset
    video?: TextInputAsset
    xhsCreatorProfile?: TextInputAsset
    simulationTopic: string
  }> {
    if (!workspace) throw new Error('No workspace selected')
    const sample =
      targetTab === 'account'
        ? SAMPLE_ACCOUNT_INPUT
        : targetTab === 'video'
          ? SAMPLE_VIDEO_INPUT
          : SAMPLE_TREND_INPUT
    const nextSimulationTopic =
      mode === 'demo' && !simulationTopic.trim()
        ? sample.simulationTopic
        : simulationTopic
    if (nextSimulationTopic !== simulationTopic) {
      setSimulationTopic(nextSimulationTopic)
    }

    const profileInput: {
      accountProfileInputAssetId?: string
      manualAccountProfile?: string
    } = {}
    const accountUsesXhsCreatorProfile =
      targetTab === 'account' && Boolean(xhsCreatorProfileMaterial)
    if (!includeProfile || accountUsesXhsCreatorProfile) {
      // Batch runs provide profile input asset IDs explicitly below.
      // XHS creator profile runs derive a compact profile snapshot in the backend.
    } else {
      let material = selectedProfileMaterial
      if (!material && mode === 'demo') {
        setSaveState('accountProfiles', { phase: 'saving' })
        const sampleName =
          targetTab === 'trend'
            ? SAMPLE_ASSET_NAMES.nomadProfile
            : targetTab === 'video'
              ? SAMPLE_ASSET_NAMES.videoProgramProfile
            : SAMPLE_ASSET_NAMES.qsheepProfile
        material = await persistTextMaterial(
          'account_profile',
          sample.positioning,
          undefined,
          sampleName,
        )
        setPositioning(sample.positioning)
        setSaveState('accountProfiles', { phase: 'saved' })
      }
      if (!material) throw new Error('请先在账号概况中选择或保存一个账号概况。')
      profileInput.accountProfileInputAssetId = material.id
    }

    if (targetTab === 'account') {
      if (xhsCreatorProfileMaterial) {
        return {
          ...profileInput,
          xhsCreatorProfile: xhsCreatorProfileMaterial,
          simulationTopic: nextSimulationTopic,
        }
      }
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
        historicalPostsDraftName || SAMPLE_ASSET_NAMES.historicalPosts,
      )
      setSaveState('historical', { phase: 'saved' })

      setSaveState('comments', { phase: 'saving' })
      const savedComments = await persistTextMaterial(
        'comments',
        nextComments,
        commentsMaterial,
        commentsDraftName || SAMPLE_ASSET_NAMES.comments,
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
        videoCreatorSamplesDraftName || SAMPLE_ASSET_NAMES.videoCreatorSamples,
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
      savedTrend = await persistTrendCsv(trendFile, trendKeyword, trendCsvDraftName)
      setSaveState('trend', { phase: 'saved' })
    } else if (mode === 'demo' && !savedTrend) {
      setSaveState('trend', { phase: 'saving' })
      const sampleFile = new File([SAMPLE_TREND_CSV], SAMPLE_ASSET_NAMES.trendCsv, {
        type: 'text/csv',
      })
      savedTrend = await persistTrendCsv(
        sampleFile,
        trendKeyword || SAMPLE_TREND_INPUT.keyword,
        trendCsvDraftName || SAMPLE_ASSET_NAMES.trendCsv,
      )
      setSaveState('trend', { phase: 'saved' })
    }
    if (!savedTrend) throw new Error('请上传热点 CSV。')
    const nextTrendName = (trendCsvDraftName || savedTrend.name).trim()
    if (
      (trendKeyword.trim() && trendKeyword !== savedTrend.keyword) ||
      nextTrendName !== savedTrend.name
    ) {
      setSaveState('trend', { phase: 'saving' })
      const updated = await inputAssetApi.update(savedTrend.id, {
        name: nextTrendName,
        keyword: trendKeyword || savedTrend.keyword,
        expectedUpdatedAt: savedTrend.updatedAt,
      })
      if (updated.type !== 'trend_csv') {
        throw new Error('Updated input asset type did not match request')
      }
      savedTrend = updated
      setTrendCsvDraftName(updated.name)
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
        idempotencyKey: newClientRequestKey(`analysis-${targetTab}`),
        accountProfileInputAssetId: savedInputs.accountProfileInputAssetId,
        manualAccountProfile: savedInputs.manualAccountProfile,
        historicalPostsInputAssetId: savedInputs.historical?.id,
        commentsInputAssetId: savedInputs.comments?.id,
        trendCsvInputAssetId: savedInputs.trend?.id,
        videoCreatorSamplesInputAssetId: savedInputs.video?.id,
        xhsCreatorProfileInputAssetId: savedInputs.xhsCreatorProfile?.id,
        mediaAssetIds:
          targetTab === 'video' ? selectedVideoWorkflowMediaAssetIds : undefined,
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
    const useXhsBatch = targetTab === 'account' && Boolean(xhsCreatorProfileMaterial)
    const batchCount = useXhsBatch
      ? xhsCreatorProfileMaterials.length
      : accountProfileMaterials.length
    if (batchCount === 0) {
      setRunError(
        useXhsBatch
          ? '请先在小红书创作者主页中导入至少一个主页资产。'
          : '请先在账号概况中上传或保存至少一个账号概况。',
      )
      return
    }
    setWorkflowTab(targetTab)
    setRunError('')
    setRunning(true)
    try {
      const savedInputs = await ensureInputsSavedForRun(targetTab, false)
      await analysisRunApi.createBatch(workspace.id, {
        workflowType: workflowFromTab(targetTab),
        idempotencyKey: newClientRequestKey(`analysis-batch-${targetTab}`),
        accountProfileInputAssetIds: useXhsBatch
          ? []
          : accountProfileMaterials.map((material) => material.id),
        xhsCreatorProfileInputAssetIds: useXhsBatch
          ? xhsCreatorProfileMaterials.map((material) => material.id)
          : undefined,
        historicalPostsInputAssetId: savedInputs.historical?.id,
        commentsInputAssetId: savedInputs.comments?.id,
        trendCsvInputAssetId: savedInputs.trend?.id,
        videoCreatorSamplesInputAssetId: savedInputs.video?.id,
        xhsCreatorProfileInputAssetId: savedInputs.xhsCreatorProfile?.id,
        mediaAssetIds:
          targetTab === 'video' ? selectedVideoWorkflowMediaAssetIds : undefined,
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
    contextTarget?: ConversationContextTarget,
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
        contextTarget,
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
    contextTarget?: ConversationContextTarget,
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
        contextTarget,
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

  function getHelpContent(): {
    title: string
    description: string
    bullets: string[]
  } {
    if (activePage === 'source-materials') {
      const definition = INPUT_ASSET_DEFINITION_BY_PANEL[inputAssetPanel]
      return {
        title: `${definition.label} 帮助`,
        description:
          '输入素材是 workflow 可复用的内容资产实例。每一种资产类型都有固定 contract，不是通用文件夹。',
        bullets: [
          definition.description,
          `当前类型：${definition.type}，内容形态：${definition.contentKind}。`,
          `Workflow role：${definition.workflowRoles.join(', ')}。`,
          `Context selector：${definition.contextSelectors.join(', ')}。`,
          '左侧列表选择已有实例；点击新建或上传可以创建新的输入实例。',
          '保存是显式动作；运行 workflow 前，当前编辑内容也会自动保存为对应输入素材。',
        ],
      }
    }

    if (activePage === 'image-assets' || activePage === 'video-assets') {
      const isImage = activePage === 'image-assets'
      return {
        title: `${isImage ? '图片素材' : '视频素材'}帮助`,
        description:
          '媒体素材是内容资产的一部分，用于保存创作者图片/视频材料和后续可复用的派生信息。',
        bullets: [
          '当前版本只做上传、metadata、derived JSON 和用户备注，不做视频理解或图片理解。',
          '原始文件由后端受控保存，前端通过 /api/media-assets/{id}/file 预览。',
          'metadata 和 derived 字段先允许手动编辑，为后续 OCR、ASR、视觉摘要、生成链路预留结构。',
          '后续视频博主质量诊断可以读取媒体资产的 compact snapshot，而不是直接读取完整二进制。',
        ],
      }
    }

    if (
      activePage === 'account-diagnosis' ||
      activePage === 'trend-analysis' ||
      activePage === 'video-quality'
    ) {
      const workflowHelp = {
        account: {
          title: '账号诊断帮助',
          description:
            '账号诊断会读取账号概况、历史笔记和评论样本，生成账号画像、痛点分析和候选选题。',
          bullets: [
            '账号概况、历史笔记和评论样本都以已保存实例形式传入 workflow。',
            '历史笔记和评论样本会绑定为本次 run 的 immutable input snapshot。',
            'Demo 模式会在缺少输入时填入示例数据；Live 模式使用真实模型配置。',
            '批量运行会对多个账号概况逐个创建 run。',
          ],
        },
        trend: {
          title: '热点分析帮助',
          description:
            '热点分析会读取账号概况和趋势 CSV 数据，先确定性解析排名，再生成趋势洞察和候选选题。',
          bullets: [
            '趋势 CSV 上传后保存为输入素材；原始文件由后端托管，前端只展示 preview。',
            'Workflow 会保留 top-50 engagement ranking 行为。',
            '运行时保存的是 compact input snapshot，不把完整 CSV 放进 graph state。',
            '适合用来把热点内容转成适配当前账号定位的选题。',
          ],
        },
        video: {
          title: '视频博主质量诊断帮助',
          description:
            '视频博主质量诊断会读取账号概况和视频创作者样本，判断创作者画像、视频质量和激励计划适配度。',
          bullets: [
            '样本应包含创作者背景、视频标题/数据、内容观察和运营备注。',
            '适合创作者运营批量评估 AIGC 视频创作者。',
            '输出会区分剧本驱动、商单驱动、技术探索等不同激励适配路径。',
            '后续可结合批量账号概况和输入素材做批量诊断和 CSV 导出。',
          ],
        },
      }[workflowTab]
      return workflowHelp
    }

    if (activePage === 'history') {
      return {
        title: '分析结果帮助',
        description:
          '这里保存每次账号诊断、热点分析、视频博主质量诊断的运行历史。',
        bullets: [
          '每条 run 都包含 workflow type、status、input snapshot、stage results 和 errors。',
          '重新打开历史结果不会重新执行 workflow。',
          'Input snapshot 是不可变执行历史，用于复盘和后续生成选题/结构。',
          '失败或部分完成的 run 也会保留可用 stage result。',
        ],
      }
    }

    if (activePage === 'topics') {
      return {
        title: '选题库帮助',
        description:
          '选题库保存来自诊断、热点分析或手动录入的选题资产。',
        bullets: [
          '选题可以被设为 Current Topic，用于内容结构生成或受众模拟。',
          'title 和 angle 可编辑；generated snapshot 作为来源记录保留。',
          'Archive 会把选题从候选工作流中移出，但不删除历史。',
          '从生成卡片“填入下一步”的快捷动作会尽量绑定到 Topic entity。',
        ],
      }
    }

    if (activePage === 'drafts') {
      return {
        title: '内容结构帮助',
        description:
          '内容结构保存从选题生成的结构化草稿，以及用户后续编辑内容。',
        bullets: [
          'generated snapshot 是模型生成快照，不应被用户编辑覆盖。',
          'editable content 保存用户修改版本。',
          '结构可以继续发送到受众模拟。',
          '这个页面当前不作为左侧一级导航暴露，但仍是 Topic 到 Simulation 的连接资产。',
        ],
      }
    }

    if (activePage === 'simulations') {
      return {
        title: '受众模拟帮助',
        description:
          '这里保存围绕某个 Topic 或内容结构运行的受众模拟结果。',
        bullets: [
          '模拟会生成产品特定 personas，不是通用可配置 agents。',
          '每个 persona 的反应是独立结果，失败时尽量保留部分反应。',
          '可以重新打开历史 simulation，不会重新执行。',
          '适合验证选题角度、受众疑虑、反对意见和内容策略。',
        ],
      }
    }

    if (activePage === 'skills') {
      return {
        title: 'Skills 帮助',
        description:
          'Skills 是产品内部可组合能力资产，描述输入 contract、输出 schema、side effects 和组合边界。',
        bullets: [
          '当前用户侧只读；我们可以在代码和 maker agent 中新增或调整。',
          'Capability Maker 会根据需求调用对应 skill，生成 Skill asset proposal。',
          'Skill 的输入应引用 InputAsset、AnalysisRun、Topic 等产品资产。',
          '旧 source.* skill id 暂时保留为兼容 ID，但 contract 已迁到 InputAsset 语义。',
        ],
      }
    }

    if (activePage === 'agents') {
      return {
        title: 'Agents 帮助',
        description:
          'Agents 是产品角色资产：system prompt + 多个 Skills + 默认 context policy。',
        bullets: [
          'Conversation 入口可以和 agent 对话，用于生成或修改资产提案。',
          'Agent 可以读取 broad workspace context pack，但不能直接访问数据库或任意文件。',
          'Capability Maker 可用于生成 Agent asset proposal。',
          '未来 agent 可逐步拥有确认后应用的资产修改能力。',
        ],
      }
    }

    if (activePage === 'workflows') {
      return {
        title: 'Workflows 帮助',
        description:
          'Workflows 是多 agent、多 task 的产品执行计划，不是通用流程编辑器。',
        bullets: [
          'workflow 调用在右侧发起；这里查看 workflow asset 定义和 agent plan。',
          '当前 graph 执行仍由后端产品接口封装，前端不暴露 LangGraph 术语。',
          'Capability Maker 可用于生成 workflow asset proposal。',
          'Workflow 输入应绑定具体 InputAsset 实例或由运行前自动保存。',
        ],
      }
    }

    return {
      title: '工作区整体帮助',
      description:
        '这个 workspace 用来管理创作者内容资产、分析结果、选题、内容结构、受众模拟，以及 Skills / Agents / Workflows 能力资产。',
      bullets: [
        '左侧是内容资产：输入素材和可复用输出统一放在一起。',
        '右侧是能力资产与 workflow 调用入口：Skills、Agents、Workflows。',
        '两侧组合起来完成调用：内容资产提供上下文，能力资产定义如何处理这些上下文。',
        '所有 workflow 运行都会尽量保存可复用的数据库记录，避免刷新后丢失。',
      ],
    }
  }

  const visibleTopics = topics.filter((topic) =>
    topicFilter === 'all' ? true : topic.sourceWorkflow === topicFilter,
  )
  const helpContent = getHelpContent()
  const mainContent = (
    <>
      {loadError && <div className="error-banner">⚠ {loadError}</div>}
      {loading && <div className="loading-card">正在加载工作区…</div>}

      {!loading && !workspace && (
        <div className="empty-workspace">
          <h2>默认工作区暂不可用</h2>
          <p>系统会自动使用一个默认工作区保存输入资产、分析结果和能力资产。</p>
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
      {!loading && workspace && activePage === 'image-assets' && (
        <MediaAssetsPage
          workspaceId={workspace.id}
          mediaType="image"
          assets={mediaAssets}
          skills={skills}
          mode={mode}
          onAssetsChange={setMediaAssets}
        />
      )}
      {!loading && workspace && activePage === 'video-assets' && (
        <MediaAssetsPage
          workspaceId={workspace.id}
          mediaType="video"
          assets={mediaAssets}
          skills={skills}
          mode={mode}
          onAssetsChange={setMediaAssets}
        />
      )}
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
    </>
  )

  return (
    <WorkspaceShell
      workspace={workspace}
      activePage={activePage}
      inputAssetPanel={inputAssetPanel}
      showHelp={showHelp}
      helpContent={helpContent}
      onOpenInputAsset={openInputAsset}
      onSetActivePage={setActivePage}
      onSetWorkflowTab={setWorkflowTab}
      onToggleHelp={() => setShowHelp((value) => !value)}
    >
      {mainContent}
    </WorkspaceShell>
  )

  async function saveAccountProfile() {
    setSaveState('workspace', { phase: 'saving' })
    setSaveState('accountProfiles', { phase: 'saving' })
    try {
      await persistWorkspace(workspaceName, positioning)
      const savedProfile = await persistTextMaterial(
        'account_profile',
        positioning,
        selectedProfileMaterial || undefined,
        accountProfileDraftName,
      )
      setSelectedProfileInputAssetId(savedProfile.id)
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
        undefined,
        accountProfileDraftName,
      )
      setSelectedProfileInputAssetId(savedProfile.id)
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
      await persistTextMaterial(
        'historical_posts',
        historicalPosts,
        historicalMaterial,
        historicalPostsDraftName,
      )
      setSaveState('historical', { phase: 'saved' })
    } catch (error) {
      setSaveState('historical', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveHistoricalPostsAsNew() {
    setSaveState('historical', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'historical_posts',
        historicalPosts,
        undefined,
        historicalPostsDraftName,
      )
      setSaveState('historical', { phase: 'saved' })
    } catch (error) {
      setSaveState('historical', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveComments() {
    setSaveState('comments', { phase: 'saving' })
    try {
      await persistTextMaterial('comments', comments, commentsMaterial, commentsDraftName)
      setSaveState('comments', { phase: 'saved' })
    } catch (error) {
      setSaveState('comments', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveCommentsAsNew() {
    setSaveState('comments', { phase: 'saving' })
    try {
      await persistTextMaterial('comments', comments, undefined, commentsDraftName)
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
        videoCreatorSamplesDraftName,
      )
      setSaveState('video', { phase: 'saved' })
    } catch (error) {
      setSaveState('video', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveVideoCreatorSamplesAsNew() {
    setSaveState('video', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'video_creator_samples',
        videoCreatorSamples,
        undefined,
        videoCreatorSamplesDraftName,
      )
      setSaveState('video', { phase: 'saved' })
    } catch (error) {
      setSaveState('video', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveXhsCreatorProfile() {
    setSaveState('xhs', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'xhs_creator_profile',
        xhsCreatorProfileContent,
        xhsCreatorProfileMaterial,
        xhsCreatorProfileDraftName,
      )
      setSaveState('xhs', { phase: 'saved' })
    } catch (error) {
      setSaveState('xhs', { phase: 'error', message: errorMessage(error) })
    }
  }

  async function saveXhsCreatorProfileAsNew() {
    setSaveState('xhs', { phase: 'saving' })
    try {
      await persistTextMaterial(
        'xhs_creator_profile',
        xhsCreatorProfileContent,
        undefined,
        xhsCreatorProfileDraftName,
      )
      setSaveState('xhs', { phase: 'saved' })
    } catch (error) {
      setSaveState('xhs', { phase: 'error', message: errorMessage(error) })
    }
  }

  function renderAccountProfilePage() {
    return (
      <AccountProfilePage
        workspaceName={workspaceName}
        positioning={positioning}
        positioningVersion={workspace?.positioningVersion ?? 0}
        workspaceSaveState={saveStates.workspace}
        accountProfilesSaveState={saveStates.accountProfiles}
        onWorkspaceNameChange={(value) => {
          setWorkspaceName(value)
          setSaveState('workspace', idleState)
        }}
        onPositioningChange={(value) => {
          setPositioning(value)
          setSaveState('workspace', idleState)
        }}
        onSave={saveAccountProfile}
      />
    )
  }

  function renderInputAssetsPage() {
    return (
      <InputAssetsPage
        inputAssetPanel={inputAssetPanel}
        accountProfileMaterials={accountProfileMaterials}
        historicalMaterials={historicalMaterials}
        commentsMaterials={commentsMaterials}
        trendMaterials={trendMaterials}
        videoCreatorSamplesMaterials={videoCreatorSamplesMaterials}
        xhsCreatorProfileMaterials={xhsCreatorProfileMaterials}
        selectedProfileMaterial={selectedProfileMaterial}
        historicalMaterial={historicalMaterial}
        commentsMaterial={commentsMaterial}
        trendMaterial={trendMaterial}
        videoCreatorSamplesMaterial={videoCreatorSamplesMaterial}
        xhsCreatorProfileMaterial={xhsCreatorProfileMaterial}
        workspaceName={workspaceName}
        positioning={positioning}
        accountProfileDraftName={accountProfileDraftName}
        historicalPostsDraftName={historicalPostsDraftName}
        commentsDraftName={commentsDraftName}
        trendCsvDraftName={trendCsvDraftName}
        videoCreatorSamplesDraftName={videoCreatorSamplesDraftName}
        xhsCreatorProfileDraftName={xhsCreatorProfileDraftName}
        historicalPosts={historicalPosts}
        comments={comments}
        trendKeyword={trendKeyword}
        videoCreatorSamples={videoCreatorSamples}
        xhsCreatorProfileContent={xhsCreatorProfileContent}
        inputAssetFormatterDraft={inputAssetFormatterDraft}
        inputAssetFormatterStatus={inputAssetFormatterStatus}
        workspaceSaveState={saveStates.workspace}
        accountProfilesSaveState={saveStates.accountProfiles}
        historicalSaveState={saveStates.historical}
        commentsSaveState={saveStates.comments}
        trendSaveState={saveStates.trend}
        videoSaveState={saveStates.video}
        xhsSaveState={saveStates.xhs}
        onStartNewInputAsset={startNewInputAsset}
        onChooseTextMaterial={chooseTextMaterial}
        onChooseTrendMaterial={chooseTrendMaterial}
        onFormatterDraftChange={(value) => {
          setInputAssetFormatterDraft(value)
          setInputAssetFormatterStatus('')
        }}
        onApplyInputAssetFormatter={applyInputAssetFormatter}
        onAccountProfileDraftNameChange={setAccountProfileDraftName}
        onWorkspaceNameChange={(value) => {
          setWorkspaceName(value)
          setSaveState('workspace', idleState)
        }}
        onPositioningChange={(value) => {
          setPositioning(value)
          setSaveState('workspace', idleState)
        }}
        onSaveAccountProfile={saveAccountProfile}
        onSaveAccountProfileAsNew={saveAccountProfileAsNew}
        onHistoricalPostsDraftNameChange={(value) => {
          setHistoricalPostsDraftName(value)
          setSaveState('historical', idleState)
        }}
        onHistoricalPostsChange={(value) => {
          setHistoricalPosts(value)
          setSaveState('historical', idleState)
        }}
        onSaveHistoricalPosts={saveHistoricalPosts}
        onSaveHistoricalPostsAsNew={saveHistoricalPostsAsNew}
        onCommentsDraftNameChange={(value) => {
          setCommentsDraftName(value)
          setSaveState('comments', idleState)
        }}
        onCommentsChange={(value) => {
          setComments(value)
          setSaveState('comments', idleState)
        }}
        onSaveComments={saveComments}
        onSaveCommentsAsNew={saveCommentsAsNew}
        onTrendCsvDraftNameChange={(value) => {
          setTrendCsvDraftName(value)
          setSaveState('trend', idleState)
        }}
        onTrendKeywordChange={(value) => {
          setTrendKeyword(value)
          setSaveState('trend', idleState)
        }}
        onTrendFileChange={(file) => {
          setTrendFile(file)
          setSaveState('trend', idleState)
        }}
        onUploadTrendCsv={uploadTrendCsv}
        onVideoCreatorSamplesDraftNameChange={(value) => {
          setVideoCreatorSamplesDraftName(value)
          setSaveState('video', idleState)
        }}
        onVideoCreatorSamplesChange={(value) => {
          setVideoCreatorSamples(value)
          setSaveState('video', idleState)
        }}
        onSaveVideoCreatorSamples={saveVideoCreatorSamples}
        onSaveVideoCreatorSamplesAsNew={saveVideoCreatorSamplesAsNew}
        onXhsCreatorProfileDraftNameChange={(value) => {
          setXhsCreatorProfileDraftName(value)
          setSaveState('xhs', idleState)
        }}
        onXhsCreatorProfileContentChange={(value) => {
          setXhsCreatorProfileContent(value)
          setSaveState('xhs', idleState)
        }}
        onSaveXhsCreatorProfile={saveXhsCreatorProfile}
        onSaveXhsCreatorProfileAsNew={saveXhsCreatorProfileAsNew}
        onSetInputAssetBatchFile={setInputAssetBatchFile}
        onUploadTextInputAssetsCsv={uploadTextInputAssetsCsv}
        xhsImportFiles={xhsImportFiles}
        onSetXhsImportFile={setXhsImportFile}
        onUploadXhsImport={uploadXhsImport}
        xhsPackageFiles={xhsPackageFiles}
        xhsPackagePreview={xhsPackagePreview}
        xhsPackagePreviewError={xhsPackagePreviewError}
        xhsImportWarnings={xhsImportWarnings}
        matchingXhsPackageMaterial={matchingXhsPackageMaterial}
        onSetXhsPackageFiles={setXhsImportPackageFiles}
        onUploadXhsImportPackage={uploadXhsImportPackage}
      />
    )
  }

  function renderWorkflowRunPage(targetTab: WorkflowTab) {
    const isAccount = targetTab === 'account'
    const isVideo = targetTab === 'video'
    const panelTitle = isAccount
      ? '📊 账号诊断'
      : isVideo
        ? '🎬 视频博主质量诊断'
        : '🔥 热点分析'
    const description = isAccount
      ? '优先使用小红书创作者主页资产；未选择时回退到账号概况、历史笔记和评论样本。'
      : isVideo
        ? '使用账号概况和视频创作者样本判断 AIGC 视频创作者质量与激励计划适配度。'
        : '使用账号概况和趋势 CSV 生成热点分析。'
    const runLabel = isAccount
      ? '⚡ 生成账号诊断'
      : isVideo
        ? '⚡ 生成视频创作者诊断'
        : '⚡ 生成热点分析'
    const renderInputPreview = (
      name: string,
      status: 'ready' | 'missing',
      detail: string,
    ) => (
      <div className="asset-requirement workflow-input-preview">
        <div>
          <b>{name}</b>
          <span>{detail}</span>
        </div>
        <em className={status}>{status}</em>
      </div>
    )
    const xhsCreatorProfilePreview = (asset: TextInputAsset) => {
      try {
        const parsed = JSON.parse(asset.content) as {
          notes?: unknown[]
          creator?: { displayName?: string }
        }
        const displayName = parsed.creator?.displayName || asset.name
        return `${displayName} · ${parsed.notes?.length || 0} 条笔记`
      } catch {
        return inputAssetPreview(asset)
      }
    }
    const mediaWorkflowPreview = (asset: MediaAsset) => {
      const hasUnderstanding = Boolean(
        asset.derived.qwenUnderstanding ||
          asset.derived.imageUnderstanding ||
          asset.derived.videoUnderstanding ||
          asset.derived.visualSummary ||
          asset.derived.sceneSummary,
      )
      return `${asset.type === 'image' ? '图片' : '视频'} · ${asset.name} · ${
        hasUnderstanding ? '已有理解结果' : '未保存理解结果'
      }`
    }
    return (
      <div className="prototype-grid">
        <section className="input-panel workflow-call-panel">
          <div className="panel-title">{panelTitle}</div>
          <p className="subline">{description}</p>
          {isAccount && (
            <div className="source-editor-card compact">
              <label htmlFor="workflow-xhs-creator-profile-material">
                小红书创作者主页实例
              </label>
              <select
                id="workflow-xhs-creator-profile-material"
                value={selectedXhsCreatorProfileInputAssetId}
                onChange={(event) =>
                  setSelectedXhsCreatorProfileInputAssetId(event.target.value)
                }
              >
                <option value="">不使用，改用下方兼容输入</option>
                {xhsCreatorProfileMaterials.map((material) => (
                  <option value={material.id} key={material.id}>
                    {material.name}
                  </option>
                ))}
              </select>
              {renderInputPreview(
                '小红书创作者主页',
                xhsCreatorProfileMaterial ? 'ready' : 'missing',
                xhsCreatorProfileMaterial
                  ? xhsCreatorProfilePreview(xhsCreatorProfileMaterial)
                  : '未选择结构化小红书主页资产',
              )}
            </div>
          )}
          {!(isAccount && xhsCreatorProfileMaterial) && (
            <div className="source-editor-card compact">
              <label htmlFor="workflow-account-profile-material">
                账号概况实例
              </label>
              <select
                id="workflow-account-profile-material"
                value={selectedProfileMaterial?.id || ''}
                onChange={(event) => setSelectedProfileInputAssetId(event.target.value)}
              >
                {accountProfileMaterials.length === 0 ? (
                  <option value="">还没有保存的账号概况</option>
                ) : (
                  accountProfileMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name}
                    </option>
                  ))
                )}
              </select>
              {renderInputPreview(
                '账号概况',
                selectedProfileMaterial ? 'ready' : 'missing',
                selectedProfileMaterial
                  ? inputAssetPreview(selectedProfileMaterial)
                  : '未选择账号概况实例',
              )}
            </div>
          )}
          {isAccount && !xhsCreatorProfileMaterial && (
            <>
              <div className="source-editor-card compact">
                <label htmlFor="workflow-historical-material">历史笔记实例</label>
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
                    <option value="">还没有保存的历史笔记</option>
                  ) : (
                    historicalMaterials.map((material) => (
                      <option value={material.id} key={material.id}>
                        {material.name}
                      </option>
                    ))
                  )}
                </select>
                {renderInputPreview(
                  '历史笔记',
                  historicalMaterial ? 'ready' : 'missing',
                  historicalMaterial
                    ? inputAssetPreview(historicalMaterial)
                    : '未选择历史笔记实例',
                )}
              </div>
              <div className="source-editor-card compact">
                <label htmlFor="workflow-comments-material">评论样本实例</label>
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
                    <option value="">还没有保存的评论样本</option>
                  ) : (
                    commentsMaterials.map((material) => (
                      <option value={material.id} key={material.id}>
                        {material.name}
                      </option>
                    ))
                  )}
                </select>
                {renderInputPreview(
                  '评论样本',
                  commentsMaterial ? 'ready' : 'missing',
                  commentsMaterial
                    ? inputAssetPreview(commentsMaterial)
                    : '未选择评论样本实例',
                )}
              </div>
            </>
          )}
          {targetTab === 'trend' && (
            <div className="source-editor-card compact">
              <label htmlFor="workflow-trend-material">趋势 CSV 数据实例</label>
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
                  <option value="">还没有上传的趋势 CSV</option>
                ) : (
                  trendMaterials.map((material) => (
                    <option value={material.id} key={material.id}>
                      {material.name} · {material.originalFilename}
                    </option>
                  ))
                )}
              </select>
              {renderInputPreview(
                '趋势 CSV',
                trendMaterial ? 'ready' : 'missing',
                trendMaterial ? inputAssetPreview(trendMaterial) : '未选择趋势 CSV 实例',
              )}
            </div>
          )}
          {isVideo && (
            <>
              <div className="source-editor-card compact">
                <label htmlFor="workflow-video-material">视频创作者样本实例</label>
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
                    <option value="">还没有保存的视频创作者样本</option>
                  ) : (
                    videoCreatorSamplesMaterials.map((material) => (
                      <option value={material.id} key={material.id}>
                        {material.name}
                      </option>
                    ))
                  )}
                </select>
                {renderInputPreview(
                  '视频创作者样本',
                  videoCreatorSamplesMaterial ? 'ready' : 'missing',
                  videoCreatorSamplesMaterial
                    ? inputAssetPreview(videoCreatorSamplesMaterial)
                    : '未选择视频创作者样本实例',
                )}
              </div>
              <div className="source-editor-card compact">
                <label>关联图片/视频素材</label>
                {mediaAssets.length === 0 ? (
                  <div className="empty-card">还没有图片或视频素材。</div>
                ) : (
                  <div className="asset-mini-list">
                    {mediaAssets.map((asset) => (
                      <label className="media-select-row" key={asset.id}>
                        <input
                          type="checkbox"
                          checked={selectedVideoWorkflowMediaAssetIds.includes(
                            asset.id,
                          )}
                          onChange={(event) => {
                            setSelectedVideoWorkflowMediaAssetIds((current) =>
                              event.target.checked
                                ? [...current, asset.id]
                                : current.filter((id) => id !== asset.id),
                            )
                          }}
                        />
                        <span>{mediaWorkflowPreview(asset)}</span>
                      </label>
                    ))}
                  </div>
                )}
                {renderInputPreview(
                  '媒体素材',
                  videoWorkflowMediaAssets.length ? 'ready' : 'missing',
                  videoWorkflowMediaAssets.length
                    ? videoWorkflowMediaAssets.map(mediaWorkflowPreview).join('\n')
                    : '可选。建议先在图片/视频素材页保存 Qwen 理解结果。',
                )}
              </div>
            </>
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
              disabled={
                running ||
                (isAccount && xhsCreatorProfileMaterial
                  ? xhsCreatorProfileMaterials.length === 0
                  : accountProfileMaterials.length === 0)
              }
              onClick={() => runBatchWorkflow(targetTab)}
            >
              {isAccount && xhsCreatorProfileMaterial
                ? `批量运行当前 Workflow（${xhsCreatorProfileMaterials.length} 个小红书主页）`
                : `批量运行当前 Workflow（${accountProfileMaterials.length} 个账号概况）`}
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
    return (
      <WorkflowOutputPanel
        targetTab={targetTab}
        views={views}
        outputKind={outputKind}
        runError={runError}
        renderStageResult={renderStageResult}
      />
    )
  }

  function renderHistoryPage() {
    return (
      <div className="workspace-page">
        <section className="history-list">
          <div className="panel-title">◷ 分析结果</div>
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
          <div className="panel-title">◇ 选题库</div>
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
          <div className="panel-title">▱ 内容结构</div>
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
            <span>不要手填 contract：描述你需要的能力，让 Capability Maker 生成 Skill 提案。</span>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() =>
                startMakerConversation(
                  MAKER_AGENT_IDS.skill,
                  '我想设计一个新的 Skill，用来：\n\n它应该读取哪些 workspace 资产：\n\n它应该输出什么结构：',
                  selectedSkill
                    ? { assetType: 'skill', assetId: selectedSkill.id }
                    : undefined,
                )
              }
            >
              让 Capability Maker 设计 Skill
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
                  <b className={capabilityStatusClass(skill.status)}>{skill.status}</b>
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
                <span className={capabilityStatusClass(selectedSkill.status)}>
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
            <span>描述你需要的角色，Capability Maker 会组合 system prompt、skills 和上下文边界。</span>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() =>
                startMakerConversation(
                  MAKER_AGENT_IDS.agent,
                  '我想设计一个新的 Agent，用来：\n\n它应该具备哪些能力 / skills：\n\n它应该读取哪些资产，不应该读取哪些资产：',
                  selectedAgent && selectedAgent.agentId !== MAKER_AGENT_IDS.agent
                    ? { assetType: 'agent', assetId: selectedAgent.id }
                    : undefined,
                )
              }
            >
              让 Capability Maker 设计 Agent
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
              <b className={capabilityStatusClass(agent.status)}>{agent.status}</b>
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
                  className={capabilityStatusClass(selectedAgent.status)}
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
                    <div className="mode-switch">
                      <button
                        type="button"
                        className={mode === 'demo' ? 'active' : ''}
                        onClick={() => setMode('demo')}
                      >
                        演示模式
                      </button>
                      <button
                        type="button"
                        className={mode === 'live' ? 'active' : ''}
                        onClick={() => setMode('live')}
                      >
                        实时生成
                      </button>
                    </div>
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
            <span>描述你想新增的创作者链路，Capability Maker 会生成多 Agent task plan 提案。</span>
            <button
              className="small-primary"
              disabled={agentConversationCreating}
              onClick={() =>
                startMakerConversation(
                  MAKER_AGENT_IDS.workflow,
                  '我想设计一个新的 Workflow，用来：\n\n输入资产包括：\n\n输出资产应该是：\n\n需要哪些 agent / skill 协作：',
                  selectedWorkflowAsset
                    ? { assetType: 'workflow', assetId: selectedWorkflowAsset.id }
                    : undefined,
                )
              }
            >
              让 Capability Maker 设计 Workflow
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
              <b className={capabilityStatusClass(workflowAsset.status)}>
                {workflowAsset.status}
              </b>
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
                  className={capabilityStatusClass(selectedWorkflowAsset.status)}
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
          <div className="panel-title">👥 受众模拟</div>
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

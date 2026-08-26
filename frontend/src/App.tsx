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
import sampleTrendCsv from '../../sample_trend.csv?raw'
import { HealthPage } from './HealthPage'
import { AccountProfilePage } from './components/AccountProfilePage'
import { AgentConversationPanel } from './components/AgentConversationPanel'
import { AgentsPage } from './components/AgentsPage'
import { ConversationsPage } from './components/ConversationsPage'
import { DraftsPage } from './components/DraftsPage'
import { InputAssetsPage } from './components/InputAssetsPage'
import { MediaAssetsPage } from './components/MediaAssetsPage'
import { SimulationHistoryPage } from './components/SimulationHistoryPage'
import {
  agentPlanJsonWithTasks,
  listFromText,
  textFromList,
  validateAgentDefinitionDraft,
  validateWorkflowDefinitionDraft,
  workflowTasksFromPlanJson,
  type AgentDefinitionDraft,
  type SkillDefinitionDraft,
  type WorkflowDefinitionDraft,
  type WorkflowTaskDraft,
} from './capabilityDefinitionValidation'
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
import { TopicLibraryPage } from './components/TopicLibraryPage'
import { WorkspaceShell, type ActivePage } from './components/WorkspaceShell'
import { WorkflowsPage } from './components/WorkflowsPage'
import { WorkflowCallPanel } from './components/WorkflowCallPanel'
import {
  WorkflowOutputPanel,
  type StageView,
  type WorkflowOutputKind,
} from './components/WorkflowOutputPanel'
import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  type InputAssetPanel,
} from './inputAssets'
import { getWorkspaceHelpContent } from './helpContent'
import { usePendingAgentConversationPolling } from './hooks/usePendingAgentConversationPolling'
import type {
  Agent,
  AgentConversation,
  AgentConversationSummary,
  AgentConversationStatus,
  AgentDefinitionUpdate,
  AgentSummary,
  AnalysisRun,
  AnalysisRunSummary,
  ActivityEvent,
  AssetProposal,
  CapabilityDefinitionDiff,
  Draft,
  DraftSummary,
  SimulationRun,
  SimulationRunSummary,
  Skill,
  SkillDefinitionUpdate,
  SkillInvokeResponse,
  SkillSummary,
  InputAsset,
  MediaAsset,
  ReviewStatus,
  TextInputAsset,
  Topic,
  TopicSourceWorkflow,
  TrendCsvInputAsset,
  Workspace,
  WorkflowAsset,
  WorkflowAssetDefinitionUpdate,
  WorkflowAssetSummary,
  WorkflowType,
} from './types'
import {
  type GenerationMode,
  type TopicCandidate,
  type WorkflowTab,
} from './workflows'
import {
  activePageForWorkflowTab,
  defaultWorkflowOutputKinds,
  emptyWorkflowStageViews,
  simulationStageSeed,
  stageSeed,
  stageSeedFromRun,
  stageSeedFromSimulation,
  type WorkflowOutputKinds,
  type WorkflowStageViews,
} from './workflowStageViews'
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
  | 'analysisReview'
  | 'simulationReview'

type CapabilityAssetType = 'skill' | 'agent' | 'workflow'
type DefinitionDiffStatus =
  | 'idle'
  | 'loading'
  | 'loaded'
  | 'reverting'
  | 'reverted'
  | 'error'
type TextInputAssetPanel = Exclude<InputAssetPanel, 'trend_csv'>
type XhsImportPanel = Extract<
  TextInputAssetPanel,
  'historical_posts' | 'video_creator_samples' | 'xhs_creator_profiles'
>
type ConversationContextTarget = {
  assetType: 'skill' | 'agent' | 'workflow'
  assetId: string
}
type VideoRubricTextDraft = {
  creatorTypes: string
  qualityDimensions: string
  evidenceRules: string
  incentiveRules: string
}
type SkillTestStatus = 'idle' | 'running' | 'completed' | 'error'
const MAKER_AGENT_IDS = {
  skill: 'capability_maker',
  agent: 'capability_maker',
  workflow: 'capability_maker',
} as const
const VIDEO_RUBRIC_SKILL_IDS = new Set([
  'analysis.video_creator_profile',
  'analysis.video_quality',
  'analysis.incentive_fit',
])
const DEFAULT_VIDEO_PM_RUBRIC = {
  creatorTypes: [
    {
      type: '剧本驱动型',
      fitForIncentive: '高',
      rule: '连续发布剧情/角色/世界观内容，评论区出现催更、追剧情、讨论人物关系等信号。',
    },
    {
      type: '商单驱动型',
      fitForIncentive: '低',
      rule: '内容以品牌植入、商品转化或短期商业任务为主，非商单内容弱或不稳定。',
    },
    {
      type: '技术探索驱动型',
      fitForIncentive: '中',
      rule: '主要展示工具链、模型实验或制作流程，需要结合更新稳定性和受众反馈判断。',
    },
  ],
  qualityDimensions: [
    {
      dimension: '叙事完整度',
      high: '有清晰冲突、转折和结尾钩子，适合系列化。',
      medium: '有主题但结构松散，缺少强钩子或连续性。',
      low: '只有概念展示，缺少故事推进或观看理由。',
      evidenceRequired: '标题、正文、评论反馈、视频理解或封面线索。',
    },
    {
      dimension: '画面完成度',
      high: '风格统一、主体清晰、构图稳定，封面/画面能支撑内容承诺。',
      medium: '整体可用但存在风格跳变、信息密度不足或封面弱。',
      low: '画面粗糙、主体混乱或明显影响可信度。',
      evidenceRequired: '封面、截图、视频理解或用户手动样本观察。',
    },
  ],
  evidenceRules: [
    '必须引用标题、正文、互动、评论、封面或已保存媒体理解中的具体证据。',
    '没有真实视频理解时，不得声称看过镜头、剪辑、口型、配音或完整视频。',
    '证据弱时必须降低 evidenceConfidence，并填写 cannotAssess 或 recommendedNextEvidence。',
  ],
  incentiveRules: [
    {
      signal: '剧本驱动 + 系列化潜力高',
      interpretation: '适合用连续更新任务、流量扶持和阶段奖励放大。',
      operatorAction: '设计 4 周连续更新激励，要求保留同一世界观或栏目。',
    },
    {
      signal: '商单占比高 + 非商单互动弱',
      interpretation: '激励计划较难改变其内容行为。',
      operatorAction: '谨慎纳入，优先谈商业合作或限定非商单内容任务。',
    },
  ],
}
const NEW_INPUT_ASSET_ID = '__new_input_asset__'
const DEFAULT_WORKSPACE_NAME = '默认创作者工作区'

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
const emptyXhsImportFiles = (): Record<XhsImportPanel, File | null> => ({
  historical_posts: null,
  video_creator_samples: null,
  xhs_creator_profiles: null,
})

function fileRelativePath(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
}

const idleState: SaveState = { phase: 'idle' }
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
const SAMPLE_TREND_CSV = sampleTrendCsv

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

function reviewStatusLabel(status: ReviewStatus): string {
  const labels: Record<ReviewStatus, string> = {
    unreviewed: '未复盘',
    useful: '有用',
    rejected: '弃用',
  }
  return labels[status]
}

function capabilityStatusClass(status: 'enabled' | 'disabled'): string {
  return `capability-status ${status}`
}

function skillToDefinitionDraft(skill: Skill): SkillDefinitionDraft {
  return {
    displayName: skill.displayName,
    category: skill.category,
    purpose: skill.purpose,
    artifactEffect: skill.artifactEffect,
    failureMode: skill.failureMode,
    version: skill.version,
    userNotes: skill.userNotes,
    triggerIntents: textFromList(skill.triggerIntents),
    requiredInputs: textFromList(skill.requiredInputs),
    optionalInputs: textFromList(skill.optionalInputs),
    sideEffects: textFromList(skill.sideEffects),
    composableWith: textFromList(skill.composableWith),
    implementationRefs: textFromList(skill.implementationRefs),
    contextPolicyJson: JSON.stringify(skill.contextPolicy, null, 2),
    outputSchemaJson: JSON.stringify(skill.outputSchema, null, 2),
  }
}

function agentToDefinitionDraft(agent: Agent): AgentDefinitionDraft {
  return {
    displayName: agent.displayName,
    purpose: agent.purpose,
    systemPrompt: agent.systemPrompt,
    skillIds: textFromList(agent.skillIds),
    defaultContextPolicyJson: JSON.stringify(agent.defaultContextPolicy, null, 2),
    version: agent.version,
    userNotes: agent.userNotes,
  }
}

function workflowToDefinitionDraft(
  workflowAsset: WorkflowAsset,
): WorkflowDefinitionDraft {
  return {
    displayName: workflowAsset.displayName,
    purpose: workflowAsset.purpose,
    entryAgentIds: textFromList(workflowAsset.entryAgentIds),
    agentPlanJson: JSON.stringify(workflowAsset.agentPlan, null, 2),
    artifactEffect: workflowAsset.artifactEffect,
    callBinding: workflowAsset.callBinding,
    version: workflowAsset.version,
    userNotes: workflowAsset.userNotes,
  }
}

function isVideoRubricSkill(skillId: string): boolean {
  return VIDEO_RUBRIC_SKILL_IDS.has(skillId)
}

function isDirectlyInvokableSkill(skillId: string): boolean {
  return skillId.startsWith('input_asset.format_') || skillId.startsWith('media.')
}

function supportsSkillDryRun(skillId: string): boolean {
  return (
    skillId.startsWith('analysis.') ||
    skillId.startsWith('topic.') ||
    skillId.startsWith('draft.') ||
    skillId.startsWith('simulation.') ||
    skillId.startsWith('input_asset.format_') ||
    skillId.startsWith('media.')
  )
}

function defaultSkillTestInput(skill: Skill): string {
  if (skill.skillId.startsWith('input_asset.format_')) {
    return JSON.stringify(
      {
        rawText: '这里粘贴一段待整理素材。\n例如：评论1：太焦虑了，不知道怎么选校。',
      },
      null,
      2,
    )
  }
  if (skill.skillId === 'media.understand_image') {
    return JSON.stringify(
      {
        prompt: '请理解这张图文素材，提取画面摘要、文字、创作者信号和不确定性。',
        imageUrl: 'https://example.com/image.png',
      },
      null,
      2,
    )
  }
  if (skill.skillId === 'media.understand_video') {
    return JSON.stringify(
      {
        prompt: '请基于视频预览帧理解这个视频素材，提取内容质量信号和不确定性。',
        videoUrl: 'https://example.com/video.mp4',
      },
      null,
      2,
    )
  }
  if (skill.skillId === 'media.generate_image') {
    return JSON.stringify(
      {
        prompt: '生成一张适合小红书封面的 AIGC 创作者视觉参考图。',
      },
      null,
      2,
    )
  }
  if (skill.skillId === 'media.generate_video') {
    return JSON.stringify(
      {
        prompt: '生成一段 3 秒 AIGC 视频概念片，用于测试视觉方向。',
      },
      null,
      2,
    )
  }
  return JSON.stringify({}, null, 2)
}

function objectArrayToPipeText(
  items: unknown,
  fields: string[],
  fallbackItems: Record<string, string>[],
): string {
  const rows = Array.isArray(items) && items.length > 0 ? items : fallbackItems
  return rows
    .map((item) => {
      const row = item && typeof item === 'object' ? (item as Record<string, unknown>) : {}
      return fields.map((field) => String(row[field] || '')).join(' | ')
    })
    .join('\n')
}

function pipeTextToObjectArray(value: string, fields: string[]): Record<string, string>[] {
  return value
    .split('\n')
    .map((row) => row.trim())
    .filter(Boolean)
    .map((row) => {
      const cells = row.split('|').map((cell) => cell.trim())
      return fields.reduce<Record<string, string>>((acc, field, index) => {
        acc[field] = cells[index] || ''
        return acc
      }, {})
    })
}

function videoRubricDraftFromContextPolicyJson(value: string): VideoRubricTextDraft | null {
  try {
    const contextPolicy = JSON.parse(value) as Record<string, unknown>
    const rubric =
      contextPolicy.pmRubric && typeof contextPolicy.pmRubric === 'object'
        ? (contextPolicy.pmRubric as Record<string, unknown>)
        : DEFAULT_VIDEO_PM_RUBRIC
    return {
      creatorTypes: objectArrayToPipeText(
        rubric.creatorTypes,
        ['type', 'fitForIncentive', 'rule'],
        DEFAULT_VIDEO_PM_RUBRIC.creatorTypes,
      ),
      qualityDimensions: objectArrayToPipeText(
        rubric.qualityDimensions,
        ['dimension', 'high', 'medium', 'low', 'evidenceRequired'],
        DEFAULT_VIDEO_PM_RUBRIC.qualityDimensions,
      ),
      evidenceRules: textFromList(
        Array.isArray(rubric.evidenceRules)
          ? rubric.evidenceRules.map((item) => String(item))
          : DEFAULT_VIDEO_PM_RUBRIC.evidenceRules,
      ),
      incentiveRules: objectArrayToPipeText(
        rubric.incentiveRules,
        ['signal', 'interpretation', 'operatorAction'],
        DEFAULT_VIDEO_PM_RUBRIC.incentiveRules,
      ),
    }
  } catch {
    return null
  }
}

function contextPolicyJsonWithVideoRubric(
  value: string,
  rubricDraft: VideoRubricTextDraft,
): string {
  const contextPolicy = JSON.parse(value) as Record<string, unknown>
  return JSON.stringify(
    {
      ...contextPolicy,
      pmRubric: {
        creatorTypes: pipeTextToObjectArray(rubricDraft.creatorTypes, [
          'type',
          'fitForIncentive',
          'rule',
        ]),
        qualityDimensions: pipeTextToObjectArray(rubricDraft.qualityDimensions, [
          'dimension',
          'high',
          'medium',
          'low',
          'evidenceRequired',
        ]),
        evidenceRules: listFromText(rubricDraft.evidenceRules),
        incentiveRules: pipeTextToObjectArray(rubricDraft.incentiveRules, [
          'signal',
          'interpretation',
          'operatorAction',
        ]),
      },
    },
    null,
    2,
  )
}

function newClientRequestKey(prefix: string): string {
  const randomId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${randomId}`
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
  const [skillDefinitionDraft, setSkillDefinitionDraft] =
    useState<SkillDefinitionDraft | null>(null)
  const [skillDefinitionSaving, setSkillDefinitionSaving] = useState(false)
  const [skillDefinitionStatus, setSkillDefinitionStatus] = useState('')
  const [skillTestInput, setSkillTestInput] = useState('')
  const [skillTestMode, setSkillTestMode] = useState<GenerationMode>('demo')
  const [skillTestStatus, setSkillTestStatus] = useState<SkillTestStatus>('idle')
  const [skillTestResult, setSkillTestResult] = useState<SkillInvokeResponse | null>(
    null,
  )
  const [skillTestError, setSkillTestError] = useState('')
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [agentDefinitionDraft, setAgentDefinitionDraft] =
    useState<AgentDefinitionDraft | null>(null)
  const [agentDefinitionSaving, setAgentDefinitionSaving] = useState(false)
  const [agentDefinitionStatus, setAgentDefinitionStatus] = useState('')
  const [agentConversations, setAgentConversations] = useState<
    AgentConversationSummary[]
  >([])
  const [selectedAgentConversation, setSelectedAgentConversation] =
    useState<AgentConversation | null>(null)
  const [assetProposals, setAssetProposals] = useState<AssetProposal[]>([])
  const [conversationTitleDraft, setConversationTitleDraft] = useState('')
  const [agentMessageDraft, setAgentMessageDraft] = useState('')
  const [agentMessageClientKey, setAgentMessageClientKey] = useState(() =>
    newClientRequestKey('agent-message'),
  )
  const [agentSending, setAgentSending] = useState(false)
  const [conversationSaving, setConversationSaving] = useState(false)
  const [conversationSaveStatus, setConversationSaveStatus] = useState('')
  const [agentConversationCreating, setAgentConversationCreating] = useState(false)
  const [workflowAssets, setWorkflowAssets] = useState<WorkflowAssetSummary[]>([])
  const [selectedWorkflowAsset, setSelectedWorkflowAsset] =
    useState<WorkflowAsset | null>(null)
  const [workflowDefinitionDraft, setWorkflowDefinitionDraft] =
    useState<WorkflowDefinitionDraft | null>(null)
  const [workflowDefinitionSaving, setWorkflowDefinitionSaving] = useState(false)
  const [workflowDefinitionStatus, setWorkflowDefinitionStatus] = useState('')
  const [definitionDiff, setDefinitionDiff] =
    useState<CapabilityDefinitionDiff | null>(null)
  const [definitionDiffStatus, setDefinitionDiffStatus] =
    useState<DefinitionDiffStatus>('idle')
  const [definitionDiffError, setDefinitionDiffError] = useState('')
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
  const [xhsImportFiles, setXhsImportFiles] =
    useState<Record<XhsImportPanel, File | null>>(emptyXhsImportFiles)
  const [xhsPackageFiles, setXhsPackageFiles] = useState<File[]>([])
  const [xhsPackagePreview, setXhsPackagePreview] =
    useState<XhsImportPackagePreview | null>(null)
  const [xhsPackagePreviewError, setXhsPackagePreviewError] = useState('')
  const [xhsImportWarnings, setXhsImportWarnings] = useState<string[]>([])
  const [inputAssetPanel, setInputAssetPanel] =
    useState<InputAssetPanel>('historical_posts')
  const [inputAssetDetailOpen, setInputAssetDetailOpen] = useState(false)
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
    analysisReview: idleState,
    simulationReview: idleState,
  })
  const [analysisReviewDraft, setAnalysisReviewDraft] = useState<{
    userNotes: string
    reviewStatus: ReviewStatus
  }>({ userNotes: '', reviewStatus: 'unreviewed' })
  const [simulationReviewDraft, setSimulationReviewDraft] = useState<{
    userNotes: string
    reviewStatus: ReviewStatus
  }>({ userNotes: '', reviewStatus: 'unreviewed' })

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

  function updateAgentMessageDraft(value: string) {
    setAgentMessageDraft(value)
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
  }

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
        setAgentMessageClientKey(newClientRequestKey('agent-message'))
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
          analysisReview: idleState,
          simulationReview: idleState,
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
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
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
      analysisReview: idleState,
      simulationReview: idleState,
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
    setInputAssetDetailOpen(false)
    setInputAssetFormatterDraft('')
    setInputAssetFormatterStatus('')
    setActivePage('source-materials')
  }

  function chooseTextMaterialFromInputAssetPage(material: TextInputAsset) {
    setInputAssetDetailOpen(true)
    chooseTextMaterial(material)
  }

  function chooseTrendMaterialFromInputAssetPage(material: TrendCsvInputAsset) {
    setInputAssetDetailOpen(true)
    chooseTrendMaterial(material)
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
    setInputAssetDetailOpen(true)
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
      setInputAssetDetailOpen(true)
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
      setVideoCreatorSamplesDraftName(name || '整理后的视频创作样本')
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
    if (!cleanName) throw new Error('请填写趋势数据名称。')
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
    includeSimulationTopic = false,
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
      includeSimulationTopic && mode === 'demo' && !simulationTopic.trim()
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
      if (xhsCreatorProfileMaterial) {
        return {
          ...profileInput,
          xhsCreatorProfile: xhsCreatorProfileMaterial,
          simulationTopic: nextSimulationTopic,
        }
      }
      const nextVideoCreatorSamples =
        mode === 'demo' && !videoCreatorSamples.trim()
          ? SAMPLE_VIDEO_INPUT.videoCreatorSamples
          : videoCreatorSamples
      if (nextVideoCreatorSamples !== videoCreatorSamples) {
        setVideoCreatorSamples(nextVideoCreatorSamples)
      }
      if (!nextVideoCreatorSamples.trim()) {
        throw new Error('请填写视频创作样本。')
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
    setSimulationStageViews(simulationStageSeed())
    try {
      const savedInputs = draft
        ? { simulationTopic }
        : await ensureInputsSavedForRun(targetTab, true, true)
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
      setActivePage('drafts')
      setSaveState('draft', { phase: 'saved' })
      return draft
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveState('draft', { phase: 'error', message })
      throw error
    }
  }

  async function generateBriefForTopic(topic: Topic) {
    setRunError('')
    setSaveState('draft', { phase: 'saving' })
    try {
      const draft = await draftApi.generateBriefFromTopic(topic.id, mode)
      setSelectedDraft(draft)
      setDraftEditor(JSON.stringify(draft.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setActivePage('drafts')
      setSaveState('draft', { phase: 'saved' })
      return draft
    } catch (error) {
      const message = errorMessage(error)
      setRunError(message)
      setSaveState('draft', { phase: 'error', message })
      throw error
    }
  }

  async function generateStructureFromBrief(draft: Draft) {
    setRunError('')
    setSaveState('draft', { phase: 'saving' })
    try {
      const structureDraft = await draftApi.generateStructureFromBrief(draft.id, mode)
      setSelectedDraft(structureDraft)
      setDraftEditor(JSON.stringify(structureDraft.editableContent, null, 2))
      await refreshWorkspaceSummary()
      setActivePage('drafts')
      setSaveState('draft', { phase: 'saved' })
      return structureDraft
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
    setAnalysisReviewDraft({
      userNotes: run.userNotes,
      reviewStatus: run.reviewStatus,
    })
    setSaveState('analysisReview', idleState)
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
    setSimulationReviewDraft({
      userNotes: run.userNotes,
      reviewStatus: run.reviewStatus,
    })
    setSaveState('simulationReview', idleState)
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

  async function saveAnalysisRunReview() {
    if (!selectedRun) return
    setSaveState('analysisReview', { phase: 'saving' })
    try {
      const updated = await analysisRunApi.updateReview(selectedRun.id, {
        userNotes: analysisReviewDraft.userNotes,
        reviewStatus: analysisReviewDraft.reviewStatus,
        expectedUpdatedAt: selectedRun.updatedAt,
      })
      setSelectedRun(updated)
      setAnalysisReviewDraft({
        userNotes: updated.userNotes,
        reviewStatus: updated.reviewStatus,
      })
      setAnalysisRuns((current) =>
        current.map((run) => (run.id === updated.id ? updated : run)),
      )
      if (currentRun?.id === updated.id) setCurrentRun(updated)
      setSaveState('analysisReview', { phase: 'saved' })
    } catch (error) {
      setSaveState('analysisReview', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function saveSimulationRunReview() {
    if (!selectedSimulationRun) return
    setSaveState('simulationReview', { phase: 'saving' })
    try {
      const updated = await simulationRunApi.updateReview(selectedSimulationRun.id, {
        userNotes: simulationReviewDraft.userNotes,
        reviewStatus: simulationReviewDraft.reviewStatus,
        expectedUpdatedAt: selectedSimulationRun.updatedAt,
      })
      setSelectedSimulationRun(updated)
      setSimulationReviewDraft({
        userNotes: updated.userNotes,
        reviewStatus: updated.reviewStatus,
      })
      setSimulationRuns((current) =>
        current.map((run) => (run.id === updated.id ? updated : run)),
      )
      setSaveState('simulationReview', { phase: 'saved' })
    } catch (error) {
      setSaveState('simulationReview', {
        phase: 'error',
        message: errorMessage(error),
      })
    }
  }

  async function openSkill(skillAssetId: string) {
    const skill = await skillApi.get(skillAssetId)
    setSelectedSkill(skill)
    setSkillDefinitionDraft(null)
    setSkillDefinitionStatus('')
    resetDefinitionDiff()
    setSkillTestInput(defaultSkillTestInput(skill))
    setSkillTestStatus('idle')
    setSkillTestResult(null)
    setSkillTestError('')
  }

  function startSkillDefinitionEdit(skill: Skill) {
    setSkillDefinitionDraft(skillToDefinitionDraft(skill))
    setSkillDefinitionStatus('')
  }

  async function saveSkillDefinition() {
    if (!selectedSkill || !skillDefinitionDraft) return
    setSkillDefinitionSaving(true)
    setSkillDefinitionStatus('saving')
    try {
      const contextPolicy = JSON.parse(skillDefinitionDraft.contextPolicyJson) as Record<
        string,
        unknown
      >
      const outputSchema = JSON.parse(skillDefinitionDraft.outputSchemaJson) as Record<
        string,
        unknown
      >
      const payload: SkillDefinitionUpdate = {
        displayName: skillDefinitionDraft.displayName,
        category: skillDefinitionDraft.category,
        purpose: skillDefinitionDraft.purpose,
        artifactEffect: skillDefinitionDraft.artifactEffect,
        failureMode: skillDefinitionDraft.failureMode,
        version: skillDefinitionDraft.version,
        userNotes: skillDefinitionDraft.userNotes,
        triggerIntents: listFromText(skillDefinitionDraft.triggerIntents),
        requiredInputs: listFromText(skillDefinitionDraft.requiredInputs),
        optionalInputs: listFromText(skillDefinitionDraft.optionalInputs),
        sideEffects: listFromText(skillDefinitionDraft.sideEffects),
        composableWith: listFromText(skillDefinitionDraft.composableWith),
        implementationRefs: listFromText(skillDefinitionDraft.implementationRefs),
        contextPolicy,
        outputSchema,
        expectedUpdatedAt: selectedSkill.updatedAt,
      }
      const updated = await skillApi.updateDefinition(selectedSkill.id, payload)
      setSelectedSkill(updated)
      setSkills((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setSkillDefinitionDraft(skillToDefinitionDraft(updated))
      setSkillDefinitionStatus('saved')
      resetDefinitionDiff()
      await refreshWorkspaceSummary()
    } catch (error) {
      setSkillDefinitionStatus(`error:${errorMessage(error)}`)
    } finally {
      setSkillDefinitionSaving(false)
    }
  }

  async function runSkillTest() {
    if (!selectedSkill) return
    setSkillTestStatus('running')
    setSkillTestError('')
    setSkillTestResult(null)
    try {
      const input = JSON.parse(skillTestInput) as Record<string, unknown>
      const runner = isDirectlyInvokableSkill(selectedSkill.skillId)
        ? skillApi.invoke
        : skillApi.dryRun
      const result = await runner(selectedSkill.id, {
        input,
        mode: skillTestMode,
      })
      setSkillTestResult(result)
      setSkillTestStatus('completed')
    } catch (error) {
      setSkillTestError(errorMessage(error))
      setSkillTestStatus('error')
    }
  }

  async function openAgent(agentAssetId: string) {
    const agent = await agentApi.get(agentAssetId)
    setSelectedAgent(agent)
    setAgentDefinitionDraft(null)
    setAgentDefinitionStatus('')
    resetDefinitionDiff()
    setSelectedAgentConversation((current) =>
      current?.agentAssetId === agent.id ? current : null,
    )
    setAgentMessageDraft('')
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
  }

  function startAgentDefinitionEdit(agent: Agent) {
    setAgentDefinitionDraft(agentToDefinitionDraft(agent))
    setAgentDefinitionStatus('')
  }

  async function saveAgentDefinition() {
    if (!selectedAgent || !agentDefinitionDraft) return
    setAgentDefinitionSaving(true)
    setAgentDefinitionStatus('saving')
    try {
      const validation = validateAgentDefinitionDraft(agentDefinitionDraft, skills)
      if (validation.errors.length > 0 || !validation.ok) {
        throw new Error(validation.errors.join('\n'))
      }
      const payload: AgentDefinitionUpdate = {
        displayName: agentDefinitionDraft.displayName,
        purpose: agentDefinitionDraft.purpose,
        systemPrompt: agentDefinitionDraft.systemPrompt,
        skillIds: listFromText(agentDefinitionDraft.skillIds),
        defaultContextPolicy: validation.value,
        version: agentDefinitionDraft.version,
        userNotes: agentDefinitionDraft.userNotes,
        expectedUpdatedAt: selectedAgent.updatedAt,
      }
      const updated = await agentApi.updateDefinition(selectedAgent.id, payload)
      setSelectedAgent(updated)
      setAgents((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setAgentDefinitionDraft(agentToDefinitionDraft(updated))
      setAgentDefinitionStatus('saved')
      resetDefinitionDiff()
      await refreshWorkspaceSummary()
    } catch (error) {
      setAgentDefinitionStatus(`error:${errorMessage(error)}`)
    } finally {
      setAgentDefinitionSaving(false)
    }
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
      setConversationTitleDraft(conversation.title)
      setConversationSaveStatus('')
      setAgentMessageDraft(initialDraft)
      setAgentMessageClientKey(newClientRequestKey('agent-message'))
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
    setConversationTitleDraft(conversation.title)
    setConversationSaveStatus('')
    setAgentMessageDraft('')
    setAgentMessageClientKey(newClientRequestKey('agent-message'))
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
        agentMessageClientKey,
      )
      setSelectedAgentConversation(conversation)
      setConversationTitleDraft(conversation.title)
      setAssetProposals(
        await assetProposalApi.listForConversation(selectedAgentConversation.id),
      )
      setAgentMessageDraft('')
      setAgentMessageClientKey(newClientRequestKey('agent-message'))
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    } finally {
      setAgentSending(false)
    }
  }

  async function updateAgentConversationAsset(
    patch: { title?: string; status?: AgentConversationStatus },
  ) {
    if (!selectedAgentConversation) return
    setConversationSaving(true)
    setConversationSaveStatus('saving')
    setRunError('')
    try {
      const updated = await agentConversationApi.update(selectedAgentConversation.id, {
        ...patch,
        expectedUpdatedAt: selectedAgentConversation.updatedAt,
      })
      setSelectedAgentConversation(updated)
      setConversationTitleDraft(updated.title)
      setAgentConversations((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setConversationSaveStatus('saved')
      await refreshWorkspaceSummary()
    } catch (error) {
      const message = errorMessage(error)
      setConversationSaveStatus(`error:${message}`)
      setRunError(message)
    } finally {
      setConversationSaving(false)
    }
  }

  async function openWorkflowAsset(workflowAssetId: string) {
    const workflowAsset = await workflowAssetApi.get(workflowAssetId)
    setSelectedWorkflowAsset(workflowAsset)
    setWorkflowDefinitionDraft(null)
    setWorkflowDefinitionStatus('')
    resetDefinitionDiff()
  }

  function startWorkflowDefinitionEdit(workflowAsset: WorkflowAsset) {
    setWorkflowDefinitionDraft(workflowToDefinitionDraft(workflowAsset))
    setWorkflowDefinitionStatus('')
  }

  async function saveWorkflowDefinition() {
    if (!selectedWorkflowAsset || !workflowDefinitionDraft) return
    setWorkflowDefinitionSaving(true)
    setWorkflowDefinitionStatus('saving')
    try {
      const validation = validateWorkflowDefinitionDraft(
        workflowDefinitionDraft,
        agents,
        skills,
      )
      if (validation.errors.length > 0 || !validation.ok) {
        throw new Error(validation.errors.join('\n'))
      }
      const payload: WorkflowAssetDefinitionUpdate = {
        displayName: workflowDefinitionDraft.displayName,
        purpose: workflowDefinitionDraft.purpose,
        entryAgentIds: listFromText(workflowDefinitionDraft.entryAgentIds),
        agentPlan: validation.value,
        artifactEffect: workflowDefinitionDraft.artifactEffect,
        callBinding: workflowDefinitionDraft.callBinding,
        version: workflowDefinitionDraft.version,
        userNotes: workflowDefinitionDraft.userNotes,
        expectedUpdatedAt: selectedWorkflowAsset.updatedAt,
      }
      const updated = await workflowAssetApi.updateDefinition(
        selectedWorkflowAsset.id,
        payload,
      )
      setSelectedWorkflowAsset(updated)
      setWorkflowAssets((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setWorkflowDefinitionDraft(workflowToDefinitionDraft(updated))
      setWorkflowDefinitionStatus('saved')
      resetDefinitionDiff()
      await refreshWorkspaceSummary()
    } catch (error) {
      setWorkflowDefinitionStatus(`error:${errorMessage(error)}`)
    } finally {
      setWorkflowDefinitionSaving(false)
    }
  }

  function resetDefinitionDiff() {
    setDefinitionDiff(null)
    setDefinitionDiffStatus('idle')
    setDefinitionDiffError('')
  }

  async function loadCapabilityDefinitionDiff(assetType: CapabilityAssetType) {
    setDefinitionDiffStatus('loading')
    setDefinitionDiffError('')
    try {
      const diff =
        assetType === 'skill' && selectedSkill
          ? await skillApi.definitionDiff(selectedSkill.id)
          : assetType === 'agent' && selectedAgent
            ? await agentApi.definitionDiff(selectedAgent.id)
            : assetType === 'workflow' && selectedWorkflowAsset
              ? await workflowAssetApi.definitionDiff(selectedWorkflowAsset.id)
              : null
      if (!diff) return
      setDefinitionDiff(diff)
      setDefinitionDiffStatus('loaded')
    } catch (error) {
      setDefinitionDiffError(errorMessage(error))
      setDefinitionDiffStatus('error')
    }
  }

  async function revertCapabilityDefinition(assetType: CapabilityAssetType) {
    setDefinitionDiffStatus('reverting')
    setDefinitionDiffError('')
    try {
      if (assetType === 'skill' && selectedSkill) {
        const updated = await skillApi.revertDefinition(
          selectedSkill.id,
          selectedSkill.updatedAt,
        )
        setSelectedSkill(updated)
        setSkills((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setSkillDefinitionDraft((current) =>
          current ? skillToDefinitionDraft(updated) : current,
        )
      } else if (assetType === 'agent' && selectedAgent) {
        const updated = await agentApi.revertDefinition(
          selectedAgent.id,
          selectedAgent.updatedAt,
        )
        setSelectedAgent(updated)
        setAgents((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setAgentDefinitionDraft((current) =>
          current ? agentToDefinitionDraft(updated) : current,
        )
      } else if (assetType === 'workflow' && selectedWorkflowAsset) {
        const updated = await workflowAssetApi.revertDefinition(
          selectedWorkflowAsset.id,
          selectedWorkflowAsset.updatedAt,
        )
        setSelectedWorkflowAsset(updated)
        setWorkflowAssets((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setWorkflowDefinitionDraft((current) =>
          current ? workflowToDefinitionDraft(updated) : current,
        )
      }
      setDefinitionDiffStatus('reverted')
      setDefinitionDiff(null)
      await refreshWorkspaceSummary()
    } catch (error) {
      setDefinitionDiffError(errorMessage(error))
      setDefinitionDiffStatus('error')
    }
  }

  async function updateWorkflowCallBinding(
    workflowAsset: WorkflowAsset,
    callBinding: WorkflowAsset['callBinding'],
  ) {
    setRunError('')
    try {
      const updated = await workflowAssetApi.updateCallBinding(workflowAsset.id, {
        callBinding,
        expectedUpdatedAt: workflowAsset.updatedAt,
      })
      setSelectedWorkflowAsset(updated)
      setWorkflowAssets((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      await refreshWorkspaceSummary()
    } catch (error) {
      setRunError(errorMessage(error))
    }
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

  async function previewAssetProposal(proposal: AssetProposal) {
    return assetProposalApi.preview(proposal.id)
  }

  async function updateAssetProposal(
    proposal: AssetProposal,
    patch: {
      title: string
      description: string
      proposedAction: Record<string, unknown>
    },
  ) {
    setRunError('')
    const updated = await assetProposalApi.update(proposal.id, {
      ...patch,
      expectedUpdatedAt: proposal.updatedAt,
    })
    setAssetProposals((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    )
    return updated
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
    const brief = (draft.editableContent.brief || {}) as {
      topicTitle?: string
      refinedAngle?: string
    }
    if (draft.kind === 'content_brief') {
      return brief.topicTitle || inputTopic?.title || '创作 Brief'
    }
    const structure = (draft.editableContent.structure || {}) as {
      topicChosen?: string
    }
    return structure.topicChosen || inputTopic?.title || '内容结构'
  }

  function draftKindLabel(draft: Draft | DraftSummary) {
    return draft.kind === 'content_brief' ? '创作 Brief' : '内容结构'
  }

  function renderContentBrief(value: Record<string, unknown>) {
    const brief = (value.brief || null) as Record<string, unknown> | null
    if (!brief) return <pre className="json-preview">{JSON.stringify(value, null, 2)}</pre>
    const list = (key: string) => (Array.isArray(brief[key]) ? (brief[key] as unknown[]) : [])
    return (
      <div className="stage-card">
        <h3>{String(brief.topicTitle || '创作 Brief')}</h3>
        <p>
          <b>精炼角度：</b>
          {String(brief.refinedAngle || '未填写')}
        </p>
        <p>
          <b>目标读者：</b>
          {String(brief.targetReader || '未填写')}
        </p>
        <p>
          <b>内容承诺：</b>
          {String(brief.contentPromise || '未填写')}
        </p>
        <p>
          <b>核心观点：</b>
          {String(brief.corePoint || '未填写')}
        </p>
        <p>
          <b>开头钩子：</b>
          {String(brief.openingHook || '未填写')}
        </p>
        <div className="mini-grid">
          <div>
            <b>论证路径</b>
            <ul>
              {list('argumentPath').map((item, index) => (
                <li key={`${index}-${String(item)}`}>{String(item)}</li>
              ))}
            </ul>
          </div>
          <div>
            <b>素材需求</b>
            <ul>
              {list('materialNeeds').map((item, index) => (
                <li key={`${index}-${String(item)}`}>{String(item)}</li>
              ))}
            </ul>
          </div>
          <div>
            <b>标题方向</b>
            <ul>
              {list('titleDirections').map((item, index) => (
                <li key={`${index}-${String(item)}`}>{String(item)}</li>
              ))}
            </ul>
          </div>
          <div>
            <b>风险</b>
            <ul>
              {list('risks').map((item, index) => (
                <li key={`${index}-${String(item)}`}>{String(item)}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    )
  }

  function renderDraftStructure(value: Record<string, unknown>) {
    if (value.brief) return renderContentBrief(value)
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
              await generateBriefForTopic(saved)
            }}
          >
            生成创作 Brief
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
  const helpContent = getWorkspaceHelpContent({
    activePage,
    inputAssetPanel,
    workflowTab,
  })
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
          onModeChange={setMode}
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
          onModeChange={setMode}
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
      {!loading && workspace && activePage === 'topics' && (
        <TopicLibraryPage
          visibleTopics={visibleTopics}
          selectedTopic={selectedTopic}
          topicFilter={topicFilter}
          manualTopicTitle={manualTopicTitle}
          manualTopicAngle={manualTopicAngle}
          topicDraft={topicDraft}
          manualTopicSaveState={saveStates.manualTopic}
          topicSaveState={saveStates.topic}
          onManualTopicTitleChange={setManualTopicTitle}
          onManualTopicAngleChange={setManualTopicAngle}
          onSaveManualTopic={saveManualTopic}
          onTopicFilterChange={setTopicFilter}
          onSelectTopicRow={setSelectedTopic}
          onSelectCurrentTopic={selectTopic}
          onGenerateBrief={generateBriefForTopic}
          onGenerateDraft={generateDraftForTopic}
          onArchiveTopic={archiveTopic}
          onTopicDraftChange={setTopicDraft}
          onSaveTopicEdits={updateSelectedTopic}
        />
      )}
      {!loading && workspace && activePage === 'drafts' && (
        <DraftsPage
          drafts={drafts}
          selectedDraft={selectedDraft}
          draftEditor={draftEditor}
          draftSaveState={saveStates.draft}
          onOpenDraft={openDraft}
          onDraftEditorChange={(value) => {
            setDraftEditor(value)
            setSaveState('draft', idleState)
          }}
          onSaveDraftEdits={saveDraftEdits}
          onGenerateStructureFromBrief={generateStructureFromBrief}
          onRunAudienceSimulation={runAudienceSimulation}
          renderDraftStructure={renderDraftStructure}
          draftDisplayTitle={draftDisplayTitle}
          draftKindLabel={draftKindLabel}
        />
      )}
      {!loading && workspace && activePage === 'simulations' && (
        <SimulationHistoryPage
          simulationRuns={simulationRuns}
          selectedSimulationRun={selectedSimulationRun}
          simulationReviewDraft={simulationReviewDraft}
          simulationReviewSaveState={saveStates.simulationReview}
          reviewStatusLabel={reviewStatusLabel}
          onOpenSimulationRun={openSimulationRun}
          onSimulationReviewDraftChange={setSimulationReviewDraft}
          onSaveSimulationRunReview={saveSimulationRunReview}
          renderRunReviewEditor={renderRunReviewEditor}
          stageSeedFromSimulation={stageSeedFromSimulation}
          renderStageResult={renderStageResult}
        />
      )}
      {!loading &&
        workspace &&
        activePage === 'conversations' &&
        renderConversationsPage()}
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
      workflowAssets={workflowAssets}
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
        inputAssetDetailOpen={inputAssetDetailOpen}
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
        onOpenInputAsset={openInputAsset}
        onChooseTextMaterial={chooseTextMaterialFromInputAssetPage}
        onChooseTrendMaterial={chooseTrendMaterialFromInputAssetPage}
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
    return (
      <div className="prototype-grid">
        <WorkflowCallPanel
          targetTab={targetTab}
          mode={mode}
          running={running}
          simulationTopic={simulationTopic}
          selectedXhsCreatorProfileInputAssetId={
            selectedXhsCreatorProfileInputAssetId
          }
          xhsCreatorProfileMaterial={xhsCreatorProfileMaterial}
          xhsCreatorProfileMaterials={xhsCreatorProfileMaterials}
          selectedProfileMaterial={selectedProfileMaterial}
          accountProfileMaterials={accountProfileMaterials}
          historicalMaterial={historicalMaterial}
          historicalMaterials={historicalMaterials}
          commentsMaterial={commentsMaterial}
          commentsMaterials={commentsMaterials}
          trendMaterial={trendMaterial}
          trendMaterials={trendMaterials}
          videoCreatorSamplesMaterial={videoCreatorSamplesMaterial}
          videoCreatorSamplesMaterials={videoCreatorSamplesMaterials}
          mediaAssets={mediaAssets}
          selectedVideoWorkflowMediaAssetIds={selectedVideoWorkflowMediaAssetIds}
          videoWorkflowMediaAssets={videoWorkflowMediaAssets}
          onSelectXhsCreatorProfileInputAssetId={
            setSelectedXhsCreatorProfileInputAssetId
          }
          onSelectProfileInputAssetId={setSelectedProfileInputAssetId}
          onChooseTextMaterial={chooseTextMaterial}
          onChooseTrendMaterial={chooseTrendMaterial}
          onSetSelectedVideoWorkflowMediaAssetIds={
            setSelectedVideoWorkflowMediaAssetIds
          }
          onSimulationTopicChange={setSimulationTopic}
          onSetMode={setMode}
          onApplyDemoSample={applyDemoSample}
          onRunDiagnosis={runDiagnosis}
          onRunAudienceSimulation={runAudienceSimulation}
          onDownloadAnalysisRunsCsv={downloadAnalysisRunsCsv}
        />
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
                <small>{reviewStatusLabel(run.reviewStatus)}</small>
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
              {renderRunReviewEditor({
                idPrefix: 'analysis-run-review',
                draft: analysisReviewDraft,
                onDraftChange: setAnalysisReviewDraft,
                onSave: saveAnalysisRunReview,
                saveState: saveStates.analysisReview,
                hint: '执行输入、阶段结果和模型元数据是不可变历史；这里仅保存人工复盘判断。',
              })}
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

  function renderRunReviewEditor({
    idPrefix,
    draft,
    onDraftChange,
    onSave,
    saveState,
    hint,
  }: {
    idPrefix: string
    draft: { userNotes: string; reviewStatus: ReviewStatus }
    onDraftChange: (draft: { userNotes: string; reviewStatus: ReviewStatus }) => void
    onSave: () => void
    saveState: SaveState
    hint: string
  }) {
    return (
      <section className="review-card">
        <div className="detail-head">
          <div>
            <h3>人工复盘</h3>
            <p>{hint}</p>
          </div>
          <SaveIndicator state={saveState} />
        </div>
        <label htmlFor={`${idPrefix}-status`}>复盘状态</label>
        <select
          id={`${idPrefix}-status`}
          value={draft.reviewStatus}
          onChange={(event) =>
            onDraftChange({
              ...draft,
              reviewStatus: event.target.value as ReviewStatus,
            })
          }
        >
          <option value="unreviewed">未复盘</option>
          <option value="useful">有用</option>
          <option value="rejected">弃用</option>
        </select>
        <label htmlFor={`${idPrefix}-notes`}>复盘备注</label>
        <textarea
          id={`${idPrefix}-notes`}
          rows={4}
          placeholder="记录这次结果是否可复用、哪里需要调整、后续如何改 prompt 或资产。"
          value={draft.userNotes}
          onChange={(event) =>
            onDraftChange({ ...draft, userNotes: event.target.value })
          }
        />
        <div className="save-row">
          <button type="button" onClick={onSave}>
            保存复盘
          </button>
          <SaveIndicator state={saveState} />
        </div>
      </section>
    )
  }

  function renderCapabilityDefinitionDiffPanel(assetType: CapabilityAssetType) {
    const isCurrentDiff = definitionDiff?.assetType === assetType
    const statusText =
      definitionDiffStatus === 'loading'
        ? '加载中…'
        : definitionDiffStatus === 'reverting'
          ? '恢复中…'
          : definitionDiffStatus === 'reverted'
            ? '已恢复内置版本'
            : definitionDiffStatus === 'error'
              ? `失败：${definitionDiffError}`
              : ''
    return (
      <div className="source-editor-card capability-diff-card">
        <div className="detail-head compact">
          <div>
            <h3>Definition Diff</h3>
            <p>对比当前 workspace override 和代码内置版本；只影响能力资产定义。</p>
          </div>
          <span>{isCurrentDiff ? definitionDiff.source : 'not loaded'}</span>
        </div>
        <div className="save-row">
          <button
            type="button"
            className="secondary-button"
            disabled={
              definitionDiffStatus === 'loading' ||
              definitionDiffStatus === 'reverting'
            }
            onClick={() => loadCapabilityDefinitionDiff(assetType)}
          >
            查看与内置差异
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={
              !isCurrentDiff ||
              !definitionDiff.canRevert ||
              definitionDiffStatus === 'reverting'
            }
            onClick={() => revertCapabilityDefinition(assetType)}
          >
            恢复内置版本
          </button>
          {statusText && (
            <span
              className={
                definitionDiffStatus === 'error' ? 'inline-error' : 'inline-save-state'
              }
            >
              {statusText}
            </span>
          )}
        </div>
        {isCurrentDiff && (
          <>
            <label>Changed Fields</label>
            <div className="why">
              {definitionDiff.changedFields.length > 0
                ? definitionDiff.changedFields.join(' / ')
                : '没有定义字段差异'}
            </div>
            <div className="compact-grid two-col">
              <div>
                <label>Current Definition</label>
                <pre className="json-preview">
                  {JSON.stringify(definitionDiff.currentDefinition, null, 2)}
                </pre>
              </div>
              <div>
                <label>Builtin Definition</label>
                <pre className="json-preview">
                  {JSON.stringify(definitionDiff.builtinDefinition, null, 2)}
                </pre>
              </div>
            </div>
          </>
        )}
      </div>
    )
  }

  function renderSkillDefinitionEditor() {
    if (!skillDefinitionDraft) return null
    const updateDraft = (patch: Partial<SkillDefinitionDraft>) => {
      setSkillDefinitionDraft((current) => (current ? { ...current, ...patch } : current))
    }
    const statusText =
      skillDefinitionStatus === 'saving'
        ? '保存中…'
        : skillDefinitionStatus === 'saved'
          ? '已保存'
          : skillDefinitionStatus.startsWith('error:')
            ? skillDefinitionStatus.replace('error:', '保存失败：')
            : ''
    return (
      <div className="source-editor-card capability-editor-card">
        <p className="subline">
          PM 调优模式：保存后会把当前 skill 变成 workspace-level generated override，
          不会直接修改 builtin seed。
        </p>
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="skill-display-name">Skill 名称</label>
            <input
              id="skill-display-name"
              value={skillDefinitionDraft.displayName}
              onChange={(event) => updateDraft({ displayName: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="skill-category">分类</label>
            <input
              id="skill-category"
              value={skillDefinitionDraft.category}
              onChange={(event) => updateDraft({ category: event.target.value })}
            />
          </div>
        </div>
        <label htmlFor="skill-purpose">用途 / 调优说明</label>
        <textarea
          id="skill-purpose"
          rows={3}
          value={skillDefinitionDraft.purpose}
          onChange={(event) => updateDraft({ purpose: event.target.value })}
        />
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="skill-artifact-effect">Artifact Effect</label>
            <input
              id="skill-artifact-effect"
              value={skillDefinitionDraft.artifactEffect}
              onChange={(event) => updateDraft({ artifactEffect: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="skill-version">版本</label>
            <input
              id="skill-version"
              value={skillDefinitionDraft.version}
              onChange={(event) => updateDraft({ version: event.target.value })}
            />
          </div>
        </div>
        <label htmlFor="skill-failure-mode">Failure Mode</label>
        <textarea
          id="skill-failure-mode"
          rows={2}
          value={skillDefinitionDraft.failureMode}
          onChange={(event) => updateDraft({ failureMode: event.target.value })}
        />
        {selectedSkill &&
          isVideoRubricSkill(selectedSkill.skillId) &&
          renderVideoRubricEditor(skillDefinitionDraft, updateDraft)}
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="skill-required-inputs">Required Inputs（一行一个）</label>
            <textarea
              id="skill-required-inputs"
              rows={5}
              value={skillDefinitionDraft.requiredInputs}
              onChange={(event) => updateDraft({ requiredInputs: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="skill-optional-inputs">Optional Inputs（一行一个）</label>
            <textarea
              id="skill-optional-inputs"
              rows={5}
              value={skillDefinitionDraft.optionalInputs}
              onChange={(event) => updateDraft({ optionalInputs: event.target.value })}
            />
          </div>
        </div>
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="skill-trigger-intents">Trigger Intents（一行一个）</label>
            <textarea
              id="skill-trigger-intents"
              rows={4}
              value={skillDefinitionDraft.triggerIntents}
              onChange={(event) => updateDraft({ triggerIntents: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="skill-composable-with">Composable With（一行一个）</label>
            <textarea
              id="skill-composable-with"
              rows={4}
              value={skillDefinitionDraft.composableWith}
              onChange={(event) => updateDraft({ composableWith: event.target.value })}
            />
          </div>
        </div>
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="skill-side-effects">Side Effects（一行一个）</label>
            <textarea
              id="skill-side-effects"
              rows={4}
              value={skillDefinitionDraft.sideEffects}
              onChange={(event) => updateDraft({ sideEffects: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="skill-implementation-refs">Implementation Refs（一行一个）</label>
            <textarea
              id="skill-implementation-refs"
              rows={4}
              value={skillDefinitionDraft.implementationRefs}
              onChange={(event) => updateDraft({ implementationRefs: event.target.value })}
            />
          </div>
        </div>
        <label htmlFor="skill-context-policy-json">Context Policy JSON</label>
        <textarea
          id="skill-context-policy-json"
          rows={8}
          value={skillDefinitionDraft.contextPolicyJson}
          onChange={(event) => updateDraft({ contextPolicyJson: event.target.value })}
        />
        <label htmlFor="skill-output-schema-json">Output Schema JSON</label>
        <textarea
          id="skill-output-schema-json"
          rows={8}
          value={skillDefinitionDraft.outputSchemaJson}
          onChange={(event) => updateDraft({ outputSchemaJson: event.target.value })}
        />
        <label htmlFor="skill-user-notes">Workspace Notes</label>
        <textarea
          id="skill-user-notes"
          rows={3}
          value={skillDefinitionDraft.userNotes}
          onChange={(event) => updateDraft({ userNotes: event.target.value })}
        />
        <div className="save-row">
          <button
            className="save-button"
            disabled={skillDefinitionSaving}
            onClick={saveSkillDefinition}
          >
            {skillDefinitionSaving ? '保存中…' : '保存 Skill Contract'}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={skillDefinitionSaving}
            onClick={() => {
              setSkillDefinitionDraft(null)
              setSkillDefinitionStatus('')
            }}
          >
            取消编辑
          </button>
          {statusText && (
            <span
              className={
                skillDefinitionStatus.startsWith('error:')
                  ? 'inline-error'
                  : 'inline-save-state'
              }
            >
              {statusText}
            </span>
          )}
        </div>
      </div>
    )
  }

  function renderVideoRubricEditor(
    draft: SkillDefinitionDraft,
    updateDraft: (patch: Partial<SkillDefinitionDraft>) => void,
  ) {
    const rubricDraft = videoRubricDraftFromContextPolicyJson(draft.contextPolicyJson)
    if (!rubricDraft) {
      return (
        <div className="rubric-editor-card error">
          <b>视频诊断 Rubric</b>
          <p>Context Policy JSON 当前无法解析。先修复 JSON 后，才能使用结构化 rubric 编辑器。</p>
        </div>
      )
    }
    const updateRubric = (patch: Partial<VideoRubricTextDraft>) => {
      updateDraft({
        contextPolicyJson: contextPolicyJsonWithVideoRubric(draft.contextPolicyJson, {
          ...rubricDraft,
          ...patch,
        }),
      })
    }
    return (
      <div className="rubric-editor-card">
        <div className="rubric-editor-head">
          <div>
            <b>视频诊断 Rubric</b>
            <p>
              这里会写入 <code>contextPolicy.pmRubric</code>。每行是一条规则，
              用竖线分隔字段。
            </p>
          </div>
          <span>structured</span>
        </div>
        <label htmlFor="video-rubric-creator-types">
          创作者类型规则：类型 | 激励适配度 | 判定规则
        </label>
        <textarea
          id="video-rubric-creator-types"
          rows={5}
          value={rubricDraft.creatorTypes}
          onChange={(event) => updateRubric({ creatorTypes: event.target.value })}
        />
        <label htmlFor="video-rubric-quality-dimensions">
          质量评价维度：维度 | 高分标准 | 中分标准 | 低分标准 | 必要证据
        </label>
        <textarea
          id="video-rubric-quality-dimensions"
          rows={6}
          value={rubricDraft.qualityDimensions}
          onChange={(event) => updateRubric({ qualityDimensions: event.target.value })}
        />
        <label htmlFor="video-rubric-evidence-rules">证据限制规则（一行一个）</label>
        <textarea
          id="video-rubric-evidence-rules"
          rows={4}
          value={rubricDraft.evidenceRules}
          onChange={(event) => updateRubric({ evidenceRules: event.target.value })}
        />
        <label htmlFor="video-rubric-incentive-rules">
          激励适配规则：信号 | 解读 | 运营动作
        </label>
        <textarea
          id="video-rubric-incentive-rules"
          rows={5}
          value={rubricDraft.incentiveRules}
          onChange={(event) => updateRubric({ incentiveRules: event.target.value })}
        />
      </div>
    )
  }

  function renderSkillTestPanel(skill: Skill) {
    const canInvoke = isDirectlyInvokableSkill(skill.skillId)
    const canDryRun = supportsSkillDryRun(skill.skillId)
    return (
      <div className="source-editor-card skill-test-card">
        <div className="detail-head compact">
          <div>
            <h3>Skill Test</h3>
            <p>用当前 Skill 的受控 invoke / dry-run API 做一次最小测试。</p>
          </div>
          {canInvoke ? (
            <span>invoke-ready</span>
          ) : canDryRun ? (
            <span>dry-run-ready</span>
          ) : (
            <span>workflow-only</span>
          )}
        </div>
        {!canInvoke && !canDryRun ? (
          <div className="empty-card">
            这个 Skill 当前不能单独 invoke 或 dry-run。它会通过绑定的产品 workflow 执行。
          </div>
        ) : (
          <>
            <div className="compact-grid two-col">
              <div>
                <label htmlFor="skill-test-mode">模式</label>
                <select
                  id="skill-test-mode"
                  value={skillTestMode}
                  onChange={(event) =>
                    setSkillTestMode(event.target.value as GenerationMode)
                  }
                >
                  <option value="demo">demo</option>
                  <option value="live">live</option>
                </select>
              </div>
              <div className="skill-test-hint">
                invoke-ready 可在 live 模式调用真实后端；dry-run 不写业务资产。
              </div>
            </div>
            <label htmlFor="skill-test-input">Input JSON</label>
            <textarea
              id="skill-test-input"
              rows={7}
              value={skillTestInput}
              onChange={(event) => {
                setSkillTestInput(event.target.value)
                setSkillTestStatus('idle')
                setSkillTestResult(null)
                setSkillTestError('')
              }}
            />
            <div className="save-row">
              <button
                className="save-button"
                disabled={skillTestStatus === 'running'}
                onClick={runSkillTest}
              >
                {skillTestStatus === 'running' ? '测试中…' : '运行 Skill Test'}
              </button>
              {skillTestStatus === 'completed' && (
                <span className="inline-save-state">测试完成</span>
              )}
              {skillTestStatus === 'error' && (
                <span className="inline-error">测试失败：{skillTestError}</span>
              )}
            </div>
            {skillTestResult && (
              <>
                <label>Output</label>
                <pre className="json-preview">
                  {JSON.stringify(skillTestResult.output, null, 2)}
                </pre>
                <label>Model Metadata</label>
                <pre className="json-preview">
                  {JSON.stringify(skillTestResult.modelMetadata, null, 2)}
                </pre>
              </>
            )}
          </>
        )}
      </div>
    )
  }

  function renderAgentDefinitionEditor() {
    if (!agentDefinitionDraft) return null
    const updateDraft = (patch: Partial<AgentDefinitionDraft>) => {
      setAgentDefinitionDraft((current) => (current ? { ...current, ...patch } : current))
    }
    const statusText =
      agentDefinitionStatus === 'saving'
        ? '保存中…'
        : agentDefinitionStatus === 'saved'
          ? '已保存'
          : agentDefinitionStatus.startsWith('error:')
            ? agentDefinitionStatus.replace('error:', '保存失败：')
            : ''
    return (
      <div className="source-editor-card capability-editor-card">
        <p className="subline">
          PM 调优模式：保存后会把当前 agent 变成 workspace-level generated override。
          skillIds 必须引用当前 workspace 已存在的 Skills。
        </p>
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="agent-display-name">Agent 名称</label>
            <input
              id="agent-display-name"
              value={agentDefinitionDraft.displayName}
              onChange={(event) => updateDraft({ displayName: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="agent-version">版本</label>
            <input
              id="agent-version"
              value={agentDefinitionDraft.version}
              onChange={(event) => updateDraft({ version: event.target.value })}
            />
          </div>
        </div>
        <label htmlFor="agent-purpose">用途 / 调优说明</label>
        <textarea
          id="agent-purpose"
          rows={3}
          value={agentDefinitionDraft.purpose}
          onChange={(event) => updateDraft({ purpose: event.target.value })}
        />
        <label htmlFor="agent-system-prompt">System Prompt</label>
        <textarea
          id="agent-system-prompt"
          rows={8}
          value={agentDefinitionDraft.systemPrompt}
          onChange={(event) => updateDraft({ systemPrompt: event.target.value })}
        />
        <label htmlFor="agent-skill-ids">Skill IDs（一行一个）</label>
        <textarea
          id="agent-skill-ids"
          rows={6}
          value={agentDefinitionDraft.skillIds}
          onChange={(event) => updateDraft({ skillIds: event.target.value })}
        />
        <div className="structured-editor-card">
          <div className="asset-section-head">
            <h3>组合 Skills</h3>
            <span>structured</span>
          </div>
          <p className="subline">
            这里会同步写入 Skill IDs。仍可在上方 textarea 中手动补充暂未登记的 stable id。
          </p>
          <div className="capability-checkbox-list">
            {skills.map((skill) => {
              const selected = listFromText(agentDefinitionDraft.skillIds).includes(
                skill.skillId,
              )
              return (
                <label key={skill.id}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={(event) => {
                      const next = new Set(listFromText(agentDefinitionDraft.skillIds))
                      if (event.target.checked) next.add(skill.skillId)
                      else next.delete(skill.skillId)
                      updateDraft({ skillIds: textFromList([...next]) })
                    }}
                  />
                  <span>
                    <b>{skill.displayName}</b>
                    <small>{skill.skillId}</small>
                  </span>
                </label>
              )
            })}
          </div>
        </div>
        <label htmlFor="agent-context-policy-json">Default Context Policy JSON</label>
        <textarea
          id="agent-context-policy-json"
          rows={8}
          value={agentDefinitionDraft.defaultContextPolicyJson}
          onChange={(event) =>
            updateDraft({ defaultContextPolicyJson: event.target.value })
          }
        />
        <label htmlFor="agent-user-notes">Workspace Notes</label>
        <textarea
          id="agent-user-notes"
          rows={3}
          value={agentDefinitionDraft.userNotes}
          onChange={(event) => updateDraft({ userNotes: event.target.value })}
        />
        <div className="save-row">
          <button
            className="save-button"
            disabled={agentDefinitionSaving}
            onClick={saveAgentDefinition}
          >
            {agentDefinitionSaving ? '保存中…' : '保存 Agent Definition'}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={agentDefinitionSaving}
            onClick={() => {
              setAgentDefinitionDraft(null)
              setAgentDefinitionStatus('')
            }}
          >
            取消编辑
          </button>
          {statusText && (
            <span
              className={
                agentDefinitionStatus.startsWith('error:')
                  ? 'inline-error'
                  : 'inline-save-state'
              }
            >
              {statusText}
            </span>
          )}
        </div>
      </div>
    )
  }

  function renderWorkflowDefinitionEditor() {
    if (!workflowDefinitionDraft) return null
    const updateDraft = (patch: Partial<WorkflowDefinitionDraft>) => {
      setWorkflowDefinitionDraft((current) =>
        current ? { ...current, ...patch } : current,
      )
    }
    const workflowTaskDrafts = workflowTasksFromPlanJson(
      workflowDefinitionDraft.agentPlanJson,
    )
    const updateTaskDrafts = (tasks: WorkflowTaskDraft[]) => {
      updateDraft({
        agentPlanJson: agentPlanJsonWithTasks(
          workflowDefinitionDraft.agentPlanJson,
          tasks,
        ),
      })
    }
    const statusText =
      workflowDefinitionStatus === 'saving'
        ? '保存中…'
        : workflowDefinitionStatus === 'saved'
          ? '已保存'
          : workflowDefinitionStatus.startsWith('error:')
            ? workflowDefinitionStatus.replace('error:', '保存失败：')
            : ''
    return (
      <div className="source-editor-card capability-editor-card">
        <p className="subline">
          PM 调优模式：保存后会把当前 workflow 变成 workspace-level generated override。
          这里编辑的是产品 task plan，不是任意图执行器。
        </p>
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="workflow-display-name">Workflow 名称</label>
            <input
              id="workflow-display-name"
              value={workflowDefinitionDraft.displayName}
              onChange={(event) => updateDraft({ displayName: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="workflow-version">版本</label>
            <input
              id="workflow-version"
              value={workflowDefinitionDraft.version}
              onChange={(event) => updateDraft({ version: event.target.value })}
            />
          </div>
        </div>
        <label htmlFor="workflow-purpose">用途 / 调优说明</label>
        <textarea
          id="workflow-purpose"
          rows={3}
          value={workflowDefinitionDraft.purpose}
          onChange={(event) => updateDraft({ purpose: event.target.value })}
        />
        <label htmlFor="workflow-entry-agent-ids">Entry Agent IDs（一行一个）</label>
        <textarea
          id="workflow-entry-agent-ids"
          rows={4}
          value={workflowDefinitionDraft.entryAgentIds}
          onChange={(event) => updateDraft({ entryAgentIds: event.target.value })}
        />
        <div className="structured-editor-card">
          <div className="asset-section-head">
            <h3>Workflow Tasks</h3>
            <span>structured</span>
          </div>
          <p className="subline">
            表格会同步写入 agentPlan.tasks。复杂字段仍可在下方 JSON 里手动编辑。
          </p>
          {workflowTaskDrafts === null ? (
            <div className="err">Agent Task Plan JSON 当前无法解析，先修复 JSON。</div>
          ) : (
            <>
              <div className="workflow-task-editor">
                {workflowTaskDrafts.map((task, index) => (
                  <div className="workflow-task-card" key={`${task.taskId}-${index}`}>
                    <div className="asset-section-head">
                      <h3>Task {index + 1}</h3>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() =>
                          updateTaskDrafts(
                            workflowTaskDrafts.filter((_, itemIndex) => itemIndex !== index),
                          )
                        }
                      >
                        删除
                      </button>
                    </div>
                    <div className="compact-grid two-col">
                      <div>
                        <label htmlFor={`workflow-task-id-${index}`}>Task ID</label>
                        <input
                          id={`workflow-task-id-${index}`}
                          value={task.taskId}
                          onChange={(event) => {
                            const next = [...workflowTaskDrafts]
                            next[index] = { ...task, taskId: event.target.value }
                            updateTaskDrafts(next)
                          }}
                        />
                      </div>
                      <div>
                        <label htmlFor={`workflow-task-agent-${index}`}>Agent</label>
                        <select
                          id={`workflow-task-agent-${index}`}
                          value={task.agentId}
                          onChange={(event) => {
                            const next = [...workflowTaskDrafts]
                            next[index] = { ...task, agentId: event.target.value }
                            updateTaskDrafts(next)
                          }}
                        >
                          <option value="">未选择</option>
                          {agents.map((agent) => (
                            <option key={agent.id} value={agent.agentId}>
                              {agent.displayName} · {agent.agentId}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <label htmlFor={`workflow-task-skills-${index}`}>
                      Skill IDs（一行一个）
                    </label>
                    <textarea
                      id={`workflow-task-skills-${index}`}
                      rows={3}
                      value={task.skillIds}
                      onChange={(event) => {
                        const next = [...workflowTaskDrafts]
                        next[index] = { ...task, skillIds: event.target.value }
                        updateTaskDrafts(next)
                      }}
                    />
                    <div className="capability-checkbox-list compact">
                      {skills.map((skill) => {
                        const selected = listFromText(task.skillIds).includes(
                          skill.skillId,
                        )
                        return (
                          <label key={skill.id}>
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={(event) => {
                                const nextSkills = new Set(listFromText(task.skillIds))
                                if (event.target.checked) nextSkills.add(skill.skillId)
                                else nextSkills.delete(skill.skillId)
                                const next = [...workflowTaskDrafts]
                                next[index] = {
                                  ...task,
                                  skillIds: textFromList([...nextSkills]),
                                }
                                updateTaskDrafts(next)
                              }}
                            />
                            <span>
                              <b>{skill.displayName}</b>
                              <small>{skill.skillId}</small>
                            </span>
                          </label>
                        )
                      })}
                    </div>
                    <div className="compact-grid two-col">
                      <div>
                        <label htmlFor={`workflow-task-depends-${index}`}>
                          Depends On（一行一个 taskId）
                        </label>
                        <textarea
                          id={`workflow-task-depends-${index}`}
                          rows={3}
                          value={task.dependsOn}
                          onChange={(event) => {
                            const next = [...workflowTaskDrafts]
                            next[index] = { ...task, dependsOn: event.target.value }
                            updateTaskDrafts(next)
                          }}
                        />
                      </div>
                      <label className="checkbox-line">
                        <input
                          type="checkbox"
                          checked={task.parallel}
                          onChange={(event) => {
                            const next = [...workflowTaskDrafts]
                            next[index] = { ...task, parallel: event.target.checked }
                            updateTaskDrafts(next)
                          }}
                        />
                        可并行执行
                      </label>
                    </div>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  updateTaskDrafts([
                    ...workflowTaskDrafts,
                    {
                      taskId: `task_${workflowTaskDrafts.length + 1}`,
                      agentId: '',
                      skillIds: '',
                      dependsOn: '',
                      parallel: false,
                    },
                  ])
                }
              >
                添加 Task
              </button>
            </>
          )}
        </div>
        <label htmlFor="workflow-agent-plan-json">Agent Task Plan JSON</label>
        <textarea
          id="workflow-agent-plan-json"
          rows={12}
          value={workflowDefinitionDraft.agentPlanJson}
          onChange={(event) => updateDraft({ agentPlanJson: event.target.value })}
        />
        <div className="compact-grid two-col">
          <div>
            <label htmlFor="workflow-artifact-effect">Artifact Effect</label>
            <input
              id="workflow-artifact-effect"
              value={workflowDefinitionDraft.artifactEffect}
              onChange={(event) => updateDraft({ artifactEffect: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="workflow-call-binding-edit">调用注册</label>
            <select
              id="workflow-call-binding-edit"
              value={workflowDefinitionDraft.callBinding}
              onChange={(event) =>
                updateDraft({
                  callBinding: event.target.value as WorkflowAsset['callBinding'],
                })
              }
            >
              <option value="">不注册为调用入口</option>
              <option value="account">账号诊断执行入口</option>
              <option value="trend">热点分析执行入口</option>
              <option value="video">视频博主质量诊断执行入口</option>
            </select>
          </div>
        </div>
        <label htmlFor="workflow-user-notes">Workspace Notes</label>
        <textarea
          id="workflow-user-notes"
          rows={3}
          value={workflowDefinitionDraft.userNotes}
          onChange={(event) => updateDraft({ userNotes: event.target.value })}
        />
        <div className="save-row">
          <button
            className="save-button"
            disabled={workflowDefinitionSaving}
            onClick={saveWorkflowDefinition}
          >
            {workflowDefinitionSaving ? '保存中…' : '保存 Workflow Definition'}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={workflowDefinitionSaving}
            onClick={() => {
              setWorkflowDefinitionDraft(null)
              setWorkflowDefinitionStatus('')
            }}
          >
            取消编辑
          </button>
          {statusText && (
            <span
              className={
                workflowDefinitionStatus.startsWith('error:')
                  ? 'inline-error'
                  : 'inline-save-state'
              }
            >
              {statusText}
            </span>
          )}
        </div>
      </div>
    )
  }

  function renderConversationsPage() {
    return (
      <ConversationsPage
        conversations={agentConversations}
        selectedConversation={selectedAgentConversation}
        agents={agents}
        assetProposals={assetProposals}
        availableSkills={skills}
        conversationTitleDraft={conversationTitleDraft}
        conversationSaving={conversationSaving}
        conversationSaveStatus={conversationSaveStatus}
        onOpenConversation={openAgentConversation}
        onOpenConversationAgent={(agentAssetId) => {
          setActivePage('agents')
          openAgent(agentAssetId)
        }}
        onConversationTitleDraftChange={(value) => {
          setConversationTitleDraft(value)
          setConversationSaveStatus('')
        }}
        onUpdateConversation={updateAgentConversationAsset}
        onUpdateProposal={updateAssetProposal}
        onPreviewProposal={previewAssetProposal}
        onApplyProposal={applyAssetProposal}
        onRejectProposal={rejectAssetProposal}
      />
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
                    {selectedSkill.source} · {selectedSkill.version}
                  </p>
                </div>
                <span className={capabilityStatusClass(selectedSkill.status)}>
                  {selectedSkill.status}
                </span>
              </div>
              <div className="detail-actions">
                <button
                  type="button"
                  onClick={() => startSkillDefinitionEdit(selectedSkill)}
                >
                  编辑 contract
                </button>
                <button
                  type="button"
                  disabled={agentConversationCreating}
                  onClick={() =>
                    startMakerConversation(
                      MAKER_AGENT_IDS.skill,
                      `我想调优这个 Skill：${selectedSkill.displayName}\n\n需要修改的 rubric / prompt / 输出结构：`,
                      { assetType: 'skill', assetId: selectedSkill.id },
                    )
                  }
                >
                  让 Capability Maker 调优
                </button>
              </div>
              {renderCapabilityDefinitionDiffPanel('skill')}
              {renderSkillDefinitionEditor()}
              {renderSkillTestPanel(selectedSkill)}
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
    return (
      <AgentsPage
        agents={agents}
        skills={skills}
        selectedAgent={selectedAgent}
        conversations={agentConversations}
        selectedConversation={selectedAgentConversation}
        agentConversationCreating={agentConversationCreating}
        runError={runError}
        definitionDiffPanel={renderCapabilityDefinitionDiffPanel('agent')}
        definitionEditor={renderAgentDefinitionEditor()}
        conversationPanel={
          <AgentConversationPanel
            conversation={selectedAgentConversation}
            agent={selectedAgent}
            proposals={assetProposals}
            availableSkills={skills}
            availableAgents={agents}
            mode={mode}
            draft={agentMessageDraft}
            sending={agentSending}
            composerRef={agentChatComposerRef}
            onModeChange={setMode}
            onDraftChange={updateAgentMessageDraft}
            onSend={sendAgentMessage}
            onUpdateProposal={updateAssetProposal}
            onPreviewProposal={previewAssetProposal}
            onApplyProposal={applyAssetProposal}
            onRejectProposal={rejectAssetProposal}
          />
        }
        onOpenAgent={openAgent}
        onEditAgent={startAgentDefinitionEdit}
        onDesignAgent={() =>
          startMakerConversation(
            MAKER_AGENT_IDS.agent,
            '我想设计一个新的 Agent，用来：\n\n它应该具备哪些能力 / skills：\n\n它应该读取哪些资产，不应该读取哪些资产：',
            selectedAgent && selectedAgent.agentId !== MAKER_AGENT_IDS.agent
              ? { assetType: 'agent', assetId: selectedAgent.id }
              : undefined,
          )
        }
        onTuneAgent={(agent) =>
          startMakerConversation(
            MAKER_AGENT_IDS.agent,
            `我想调优这个 Agent：${agent.displayName}\n\n需要修改的 system prompt / skills / context policy：`,
            { assetType: 'agent', assetId: agent.id },
          )
        }
        onStartConversation={startAgentConversation}
        onOpenConversation={openAgentConversation}
        onOpenSkill={(skillAssetId) => {
          setActivePage('skills')
          openSkill(skillAssetId)
        }}
      />
    )
  }

  function renderWorkflowAssetsPage() {
    return (
      <WorkflowsPage
        workflowAssets={workflowAssets}
        agents={agents}
        skills={skills}
        selectedWorkflowAsset={selectedWorkflowAsset}
        agentConversationCreating={agentConversationCreating}
        definitionDiffPanel={renderCapabilityDefinitionDiffPanel('workflow')}
        definitionEditor={renderWorkflowDefinitionEditor()}
        onOpenWorkflow={openWorkflowAsset}
        onEditWorkflow={startWorkflowDefinitionEdit}
        onDesignWorkflow={() =>
          startMakerConversation(
            MAKER_AGENT_IDS.workflow,
            '我想设计一个新的 Workflow，用来：\n\n输入资产包括：\n\n输出资产应该是：\n\n需要哪些 agent / skill 协作：',
            selectedWorkflowAsset
              ? { assetType: 'workflow', assetId: selectedWorkflowAsset.id }
              : undefined,
          )
        }
        onTuneWorkflow={(workflowAsset) =>
          startMakerConversation(
            MAKER_AGENT_IDS.workflow,
            `我想调优这个 Workflow：${workflowAsset.displayName}\n\n需要修改的 task plan / agent / skill / 调用注册：`,
            { assetType: 'workflow', assetId: workflowAsset.id },
          )
        }
        onUpdateCallBinding={updateWorkflowCallBinding}
        onOpenAgent={(agentAssetId) => {
          setActivePage('agents')
          openAgent(agentAssetId)
        }}
        onOpenSkill={(skillAssetId) => {
          setActivePage('skills')
          openSkill(skillAssetId)
        }}
      />
    )
  }

}

function App() {
  if (window.location.pathname === '/health') return <HealthPage />
  return <WorkspaceApp />
}

export default App

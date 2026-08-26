import { ApiError, inputAssetApi } from './api'
import {
  listFromText,
  textFromList,
  type AgentDefinitionDraft,
  type SkillDefinitionDraft,
  type WorkflowDefinitionDraft,
} from './capabilityDefinitionValidation'
import type {
  Agent,
  Draft,
  DraftSummary,
  InputAsset,
  ReviewStatus,
  SimulationRun,
  Skill,
  TextInputAsset,
  TrendCsvInputAsset,
  Workspace,
  WorkflowAsset,
  WorkflowType,
} from './types'
import type { SaveState } from './components/StageResultViews'
import type { InputAssetPanel } from './inputAssets'
import type { TopicCandidate, WorkflowTab } from './workflows'

export type SaveKey =
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

export type CapabilityAssetType = 'skill' | 'agent' | 'workflow'
export type DefinitionDiffStatus =
  | 'idle'
  | 'loading'
  | 'loaded'
  | 'reverting'
  | 'reverted'
  | 'error'
export type TextInputAssetPanel = Exclude<InputAssetPanel, 'trend_csv'>
export type XhsImportPanel = Extract<
  TextInputAssetPanel,
  'historical_posts' | 'video_creator_samples' | 'xhs_creator_profiles'
>
export type ConversationContextTarget = {
  assetType: 'skill' | 'agent' | 'workflow'
  assetId: string
}
export type VideoRubricTextDraft = {
  creatorTypes: string
  qualityDimensions: string
  evidenceRules: string
  incentiveRules: string
}

export const MAKER_AGENT_IDS = {
  skill: 'capability_maker',
  agent: 'capability_maker',
  workflow: 'capability_maker',
} as const

export const VIDEO_RUBRIC_SKILL_IDS = new Set([
  'analysis.video_creator_profile',
  'analysis.video_quality',
  'analysis.incentive_fit',
])

export const DEFAULT_VIDEO_PM_RUBRIC = {
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

export const NEW_INPUT_ASSET_ID = '__new_input_asset__'
export const DEFAULT_WORKSPACE_NAME = '默认创作者工作区'

export const idleState: SaveState = { phase: 'idle' }

export const SAMPLE_ASSET_NAMES = {
  qsheepProfile: 'Qsheep 留学账号',
  nomadProfile: '数字游民生活方式账号',
  videoProgramProfile: 'AIGC视频创作者激励计划',
  historicalPosts: '留学帖子数据合集',
  comments: '留学评论区合集',
  trendCsv: '数字游民趋势.csv',
  videoCreatorSamples: 'AI短剧创作者样本',
  xhsCreatorProfile: 'XHS QSheep 创作者主页',
} as const

export const EMPTY_INPUT_ASSET_NAMES = {
  account_profile: '',
  historical_posts: '',
  comments: '',
  trend_csv: '',
  video_creator_samples: '',
  xhs_creator_profile: '',
} as const

export const SAVE_KEY_BY_XHS_IMPORT_PANEL: Record<XhsImportPanel, SaveKey> = {
  historical_posts: 'historical',
  video_creator_samples: 'video',
  xhs_creator_profiles: 'xhs',
}

export const XHS_IMPORT_TYPE_BY_PANEL: Record<
  XhsImportPanel,
  'historical_posts' | 'video_creator_samples' | 'xhs_creator_profile'
> = {
  historical_posts: 'historical_posts',
  video_creator_samples: 'video_creator_samples',
  xhs_creator_profiles: 'xhs_creator_profile',
}

export const FORMATTER_SKILL_ID_BY_PANEL: Record<InputAssetPanel, string> = {
  account_profiles: 'input_asset.format_profile',
  historical_posts: 'input_asset.format_historical_posts',
  comments: 'input_asset.format_comments',
  trend_csv: 'input_asset.format_trend_csv_brief',
  video_creator_samples: 'input_asset.format_video_creator_samples',
  xhs_creator_profiles: 'input_asset.format_xhs_creator_profile',
}

export const emptyXhsImportFiles = (): Record<XhsImportPanel, File | null> => ({
  historical_posts: null,
  video_creator_samples: null,
  xhs_creator_profiles: null,
})

export function fileRelativePath(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : '操作失败，请重试。'
}

export function latestTextMaterial(
  materials: InputAsset[],
  type: TextInputAsset['type'],
): TextInputAsset | undefined {
  return materials.find(
    (material): material is TextInputAsset => material.type === type,
  )
}

export function latestTrendMaterial(
  materials: InputAsset[],
): TrendCsvInputAsset | undefined {
  return materials.find(
    (material): material is TrendCsvInputAsset =>
      material.type === 'trend_csv',
  )
}

export async function chooseDefaultWorkspaceId(items: Workspace[]): Promise<string> {
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

export function workflowFromTab(tab: WorkflowTab): WorkflowType {
  if (tab === 'account') return 'account_diagnosis'
  if (tab === 'video') return 'video_creator_quality'
  return 'trend_analysis'
}

export function workflowTabFromSource(sourceWorkflow?: unknown): WorkflowTab {
  if (sourceWorkflow === 'video_creator_quality') return 'video'
  return sourceWorkflow === 'trend_analysis' ? 'trend' : 'account'
}

export function workflowTabFromSimulation(run: SimulationRun): WorkflowTab {
  const topic = run.inputSnapshot.topic as { sourceWorkflow?: unknown } | null
  const draft = run.inputSnapshot.draft as { sourceWorkflow?: unknown } | null
  return workflowTabFromSource(draft?.sourceWorkflow || topic?.sourceWorkflow)
}

export function workflowLabel(type: WorkflowType): string {
  if (type === 'account_diagnosis') return '账号诊断'
  if (type === 'video_creator_quality') return '视频创作者质量诊断'
  return '热点分析'
}

export function reviewStatusLabel(status: ReviewStatus): string {
  const labels: Record<ReviewStatus, string> = {
    unreviewed: '未复盘',
    useful: '有用',
    rejected: '弃用',
  }
  return labels[status]
}

export function capabilityStatusClass(status: 'enabled' | 'disabled'): string {
  return `capability-status ${status}`
}

export function skillToDefinitionDraft(skill: Skill): SkillDefinitionDraft {
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

export function agentToDefinitionDraft(agent: Agent): AgentDefinitionDraft {
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

export function workflowToDefinitionDraft(
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

export function isVideoRubricSkill(skillId: string): boolean {
  return VIDEO_RUBRIC_SKILL_IDS.has(skillId)
}

export function isDirectlyInvokableSkill(skillId: string): boolean {
  return skillId.startsWith('input_asset.format_') || skillId.startsWith('media.')
}

export function supportsSkillDryRun(skillId: string): boolean {
  return (
    skillId.startsWith('analysis.') ||
    skillId.startsWith('topic.') ||
    skillId.startsWith('draft.') ||
    skillId.startsWith('simulation.') ||
    skillId.startsWith('input_asset.format_') ||
    skillId.startsWith('media.')
  )
}

export function defaultSkillTestInput(skill: Skill): string {
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

export function objectArrayToPipeText(
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

export function pipeTextToObjectArray(
  value: string,
  fields: string[],
): Record<string, string>[] {
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

export function videoRubricDraftFromContextPolicyJson(
  value: string,
): VideoRubricTextDraft | null {
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

export function contextPolicyJsonWithVideoRubric(
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

export function newClientRequestKey(prefix: string): string {
  const randomId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${randomId}`
}

export function getTopicsFromStage(result: unknown): TopicCandidate[] {
  if (!result || typeof result !== 'object') return []
  const topics = (result as { topics?: unknown }).topics
  return Array.isArray(topics) ? (topics as TopicCandidate[]) : []
}

export function draftDisplayTitle(draft: Draft) {
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

export function draftKindLabel(draft: Draft | DraftSummary) {
  return draft.kind === 'content_brief' ? '创作 Brief' : '内容结构'
}

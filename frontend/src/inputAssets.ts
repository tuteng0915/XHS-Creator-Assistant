import type {
  InputAsset,
  InputAssetType,
  TextInputAsset,
  TrendCsvInputAsset,
} from './types'

export type InputAssetPanel =
  | 'account_profiles'
  | 'historical_posts'
  | 'comments'
  | 'trend_csv'
  | 'video_creator_samples'
  | 'xhs_creator_profiles'

export const CREATOR_INPUT_ASSET_PANELS = [
  'xhs_creator_profiles',
  'account_profiles',
  'historical_posts',
  'comments',
  'video_creator_samples',
] as const satisfies readonly InputAssetPanel[]

export type InputAssetContentKind = 'text' | 'file'

export interface InputAssetTypeDefinition {
  panel: InputAssetPanel
  type: InputAssetType
  label: string
  singularLabel: string
  description: string
  icon: string
  contentKind: InputAssetContentKind
  emptyLabel: string
  newLabel: string
  saveCurrentLabel?: string
  saveAsNewLabel?: string
  workflowRoles: string[]
  contextSelectors: string[]
}

export const INPUT_ASSET_DEFINITIONS: InputAssetTypeDefinition[] = [
  {
    panel: 'account_profiles',
    type: 'account_profile',
    label: '账号概况',
    singularLabel: '账号概况',
    description: '可复用的账号/创作者定位，用于单次选择或批量运行 workflow。',
    icon: '◎',
    contentKind: 'text',
    emptyLabel: '还没有已保存的账号概况。',
    newLabel: '新建账号概况',
    saveCurrentLabel: '保存当前账号概况',
    saveAsNewLabel: '另存为新账号概况',
    workflowRoles: ['account_profile'],
    contextSelectors: ['account_positioning'],
  },
  {
    panel: 'historical_posts',
    type: 'historical_posts',
    label: '历史笔记',
    singularLabel: '历史笔记',
    description: '历史笔记用于账号画像、内容支柱、爆款结构和声音指纹分析。',
    icon: '▤',
    contentKind: 'text',
    emptyLabel: '还没有已保存的历史笔记实例。',
    newLabel: '新建历史笔记',
    saveCurrentLabel: '保存当前历史笔记',
    saveAsNewLabel: '另存为新历史笔记',
    workflowRoles: ['historical_posts'],
    contextSelectors: ['historical_posts_text'],
  },
  {
    panel: 'comments',
    type: 'comments',
    label: '评论样本',
    singularLabel: '评论样本',
    description: '评论样本用于提取受众痛点；保存后可被账号诊断引用。',
    icon: '💬',
    contentKind: 'text',
    emptyLabel: '还没有已保存的评论样本实例。',
    newLabel: '新建评论样本',
    saveCurrentLabel: '保存当前评论样本',
    saveAsNewLabel: '另存为新评论样本',
    workflowRoles: ['comment_samples'],
    contextSelectors: ['comment_samples_text'],
  },
  {
    panel: 'trend_csv',
    type: 'trend_csv',
    label: '趋势数据',
    singularLabel: '趋势数据',
    description: '上传热点数据后，workflow 会在后端确定性解析并生成 compact preview。',
    icon: '▧',
    contentKind: 'file',
    emptyLabel: '还没有已上传的趋势数据实例。',
    newLabel: '上传新趋势数据',
    workflowRoles: ['trend_csv'],
    contextSelectors: ['trend_top_ranked_posts'],
  },
  {
    panel: 'video_creator_samples',
    type: 'video_creator_samples',
    label: '视频创作样本',
    singularLabel: '视频创作样本',
    description: '视频创作样本用于视频质量诊断和激励计划适配判断。',
    icon: '🎬',
    contentKind: 'text',
    emptyLabel: '还没有已保存的视频创作样本。',
    newLabel: '新建视频创作样本',
    saveCurrentLabel: '保存当前视频创作样本',
    saveAsNewLabel: '另存为新视频创作样本',
    workflowRoles: ['video_creator_samples'],
    contextSelectors: ['video_creator_samples_text'],
  },
  {
    panel: 'xhs_creator_profiles',
    type: 'xhs_creator_profile',
    label: '小红书创作者主页',
    singularLabel: '小红书创作者主页',
    description:
      '独立 xhs local importer 产出的结构化主页资产，保留笔记、评论、互动数据和封面关联。',
    icon: '📕',
    contentKind: 'text',
    emptyLabel: '还没有已保存的小红书创作者主页。',
    newLabel: '新建小红书创作者主页',
    saveCurrentLabel: '保存当前小红书创作者主页',
    saveAsNewLabel: '另存为新小红书创作者主页',
    workflowRoles: ['xhs_creator_profile'],
    contextSelectors: ['selected_xhs_creator_profile', 'media_assets_overview'],
  },
]

export const INPUT_ASSET_DEFINITION_BY_PANEL = Object.fromEntries(
  INPUT_ASSET_DEFINITIONS.map((definition) => [definition.panel, definition]),
) as Record<InputAssetPanel, InputAssetTypeDefinition>

export function isCreatorInputAssetPanel(
  panel: InputAssetPanel,
): panel is (typeof CREATOR_INPUT_ASSET_PANELS)[number] {
  return CREATOR_INPUT_ASSET_PANELS.includes(
    panel as (typeof CREATOR_INPUT_ASSET_PANELS)[number],
  )
}

export function isTextInputAsset(asset: InputAsset): asset is TextInputAsset {
  return asset.type !== 'trend_csv'
}

export function isTrendCsvInputAsset(
  asset: InputAsset,
): asset is TrendCsvInputAsset {
  return asset.type === 'trend_csv'
}

export function inputAssetPreview(asset: InputAsset): string {
  if (isTrendCsvInputAsset(asset)) {
    return `${asset.originalFilename} · ${asset.rowCount} 行 · ${asset.keyword}`
  }
  const text = asset.content.trim().replace(/\s+/g, ' ')
  return truncatePreview(text || '空内容')
}

function truncatePreview(value: string, maxChars = 180): string {
  if (value.length <= maxChars) return value
  return `${value.slice(0, maxChars - 1).trimEnd()}…`
}

export function inputAssetUpdatedLabel(asset: InputAsset): string {
  return new Date(asset.updatedAt).toLocaleString()
}

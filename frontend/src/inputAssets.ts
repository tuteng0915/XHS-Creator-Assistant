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
    label: 'Account Profiles',
    singularLabel: 'Account Profile',
    description: '可复用的账号/创作者定位，用于单次选择或批量运行 workflow。',
    icon: '◎',
    contentKind: 'text',
    emptyLabel: '还没有已保存的 Account Profile。',
    newLabel: '新建 Account Profile',
    saveCurrentLabel: '保存当前 Account Profile',
    saveAsNewLabel: '另存为新 Account Profile',
    workflowRoles: ['account_profile'],
    contextSelectors: ['account_positioning'],
  },
  {
    panel: 'historical_posts',
    type: 'historical_posts',
    label: 'Historical Posts',
    singularLabel: 'Historical Posts',
    description: '历史笔记用于账号画像、内容支柱、爆款结构和声音指纹分析。',
    icon: '▤',
    contentKind: 'text',
    emptyLabel: '还没有已保存的 Historical Posts 实例。',
    newLabel: '新建 Historical Posts',
    saveCurrentLabel: '保存当前历史笔记',
    saveAsNewLabel: '另存为新历史笔记',
    workflowRoles: ['historical_posts'],
    contextSelectors: ['historical_posts_text'],
  },
  {
    panel: 'comments',
    type: 'comments',
    label: 'Comment Samples',
    singularLabel: 'Comment Samples',
    description: '评论样本用于提取受众痛点；保存后可被账号诊断引用。',
    icon: '💬',
    contentKind: 'text',
    emptyLabel: '还没有已保存的 Comment Samples 实例。',
    newLabel: '新建 Comment Samples',
    saveCurrentLabel: '保存当前评论样本',
    saveAsNewLabel: '另存为新评论样本',
    workflowRoles: ['comment_samples'],
    contextSelectors: ['comment_samples_text'],
  },
  {
    panel: 'trend_csv',
    type: 'trend_csv',
    label: 'Trend CSV Data',
    singularLabel: 'Trend CSV',
    description: '上传热点数据后，workflow 会在后端确定性解析并生成 compact preview。',
    icon: '▧',
    contentKind: 'file',
    emptyLabel: '还没有已上传的 Trend CSV 实例。',
    newLabel: '上传新 Trend CSV',
    workflowRoles: ['trend_csv'],
    contextSelectors: ['trend_top_ranked_posts'],
  },
  {
    panel: 'video_creator_samples',
    type: 'video_creator_samples',
    label: 'Video Creator Samples',
    singularLabel: 'Video Creator Samples',
    description: '视频创作者样本用于视频质量诊断和激励计划适配判断。',
    icon: '🎬',
    contentKind: 'text',
    emptyLabel: '还没有已保存的视频创作者样本。',
    newLabel: '新建 Video Creator Samples',
    saveCurrentLabel: '保存当前视频创作者样本',
    saveAsNewLabel: '另存为新视频创作者样本',
    workflowRoles: ['video_creator_samples'],
    contextSelectors: ['video_creator_samples_text'],
  },
]

export const INPUT_ASSET_DEFINITION_BY_PANEL = Object.fromEntries(
  INPUT_ASSET_DEFINITIONS.map((definition) => [definition.panel, definition]),
) as Record<InputAssetPanel, InputAssetTypeDefinition>

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
  return text || '空内容'
}

export function inputAssetUpdatedLabel(asset: InputAsset): string {
  return new Date(asset.updatedAt).toLocaleString()
}

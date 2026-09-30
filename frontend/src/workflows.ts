export type WorkflowTab = 'account' | 'trend' | 'video'
export type GenerationMode = 'demo' | 'live'

export interface TopicCandidate {
  title: string
  angle: string
  pain?: string
  whyFit?: string
  whyTrending?: string
  pendingSuggestions?: string[]
}

export const ACCOUNT_STAGES = [
  { key: 'profile', n: '①', title: '账号画像' },
  { key: 'pain_points', n: '②', title: '读者反馈' },
  { key: 'topics', n: '③', title: '下一步 · 选题建议' },
] as const

export const TREND_STAGES = [
  { key: 'trend_analysis', n: '①', title: '热点归纳' },
  { key: 'pain_points', n: '②', title: '痛点归类' },
  { key: 'topics', n: '③', title: '选题生成' },
  { key: 'titles', n: '④', title: '标题变体' },
] as const

export const VIDEO_CREATOR_STAGES = [
  { key: 'creator_profile', n: '①', title: '创作者画像 · 驱动类型判断' },
  { key: 'video_quality', n: '②', title: '视频质量诊断' },
  { key: 'incentive_fit', n: '③', title: '激励计划适配判断' },
] as const

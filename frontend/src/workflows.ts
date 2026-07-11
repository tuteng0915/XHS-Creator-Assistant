export type WorkflowTab = 'account' | 'trend'
export type GenerationMode = 'demo' | 'live'

export interface TopicCandidate {
  title: string
  angle: string
  pain?: string
  whyFit?: string
  whyTrending?: string
}

export const ACCOUNT_STAGES = [
  { key: 'profile', n: '①', title: '主页诊断 · 数据对比 + 爆款结构' },
  { key: 'pain_points', n: '②', title: '痛点归类' },
  { key: 'topics', n: '③', title: '选题生成' },
] as const

export const TREND_STAGES = [
  { key: 'trend_analysis', n: '①', title: '热点归纳' },
  { key: 'pain_points', n: '②', title: '痛点归类' },
  { key: 'topics', n: '③', title: '选题生成' },
  { key: 'titles', n: '④', title: '标题变体' },
] as const

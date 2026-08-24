import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import {
  IncentiveFitView,
  VideoCreatorProfileView,
  VideoQualityView,
} from './StageResultViews'

afterEach(() => {
  cleanup()
})

const evidenceFields = {
  evidenceScope: {
    sourceType: 'xhs_creator_profile',
    hasVideoNotes: true,
    hasVideoUnderstanding: false,
    hasImageUnderstanding: true,
    hasComments: true,
    mediaAssetCount: 1,
  },
  evidenceConfidence: '中',
  evidenceLimitations: ['未提供已确认的视频理解结果；不得声称看过完整视频。'],
  recommendedNextEvidence: ['补充至少 1 条代表视频的视频理解结果。'],
}

describe('video stage result evidence boundary rendering', () => {
  it('renders creator profile evidence confidence and limitations', () => {
    render(
      <VideoCreatorProfileView
        data={{
          creatorType: 'script_driven',
          typeConfidence: '高',
          summary: '连续短剧创作者。',
          audiencePositioning: 'AIGC 短剧用户',
          ...evidenceFields,
        }}
      />,
    )

    expect(screen.getByText('证据不足，需要保守判断')).toBeInTheDocument()
    expect(screen.getByText(/证据置信度/)).toBeInTheDocument()
    expect(screen.getByText(/未提供已确认的视频理解结果/)).toBeInTheDocument()
  })

  it('renders video quality cannot-assess items', () => {
    render(
      <VideoQualityView
        data={{
          level: '中',
          overallScore: 68,
          strengths: ['系列化潜力'],
          weaknesses: ['缺少真实视频理解'],
          cannotAssess: ['无法可靠评估完整视频的镜头调度。'],
          ...evidenceFields,
        }}
      />,
    )

    expect(screen.getByText(/当前不可可靠评估/)).toBeInTheDocument()
    expect(screen.getAllByText(/镜头调度/).length).toBeGreaterThan(0)
    expect(screen.getByText(/建议补充：/)).toBeInTheDocument()
    expect(screen.getByText(/建议补充证据/)).toBeInTheDocument()
  })

  it('renders incentive fit inherited evidence boundary', () => {
    render(
      <IncentiveFitView
        data={{
          recommendation: 'conditional_fit',
          fitScore: 72,
          rationale: '适配需要补充视频证据。',
          programMatch: { bestProgramType: '系列更新激励', why: '有系列信号', avoid: '不要只看单条爆款' },
          ...evidenceFields,
        }}
      />,
    )

    expect(screen.getByText(/激励适配：conditional_fit/)).toBeInTheDocument()
    expect(screen.getByText('72')).toBeInTheDocument()
    expect(screen.getByText(/有视频理解/)).toBeInTheDocument()
    expect(screen.getByText(/false/)).toBeInTheDocument()
  })
})

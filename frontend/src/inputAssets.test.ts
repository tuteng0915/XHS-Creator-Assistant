import { describe, expect, it } from 'vitest'

import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  inputAssetPreview,
  inputAssetUpdatedLabel,
  isTextInputAsset,
  isTrendCsvInputAsset,
} from './inputAssets'
import type { TextInputAsset, TrendCsvInputAsset } from './types'

const base = {
  id: 'asset-1',
  workspaceId: 'workspace-1',
  name: '资产',
  createdAt: '2026-07-11T10:00:00Z',
  updatedAt: '2026-07-11T11:12:13Z',
}

describe('inputAssets', () => {
  it('keeps product asset definitions addressable by panel', () => {
    expect(INPUT_ASSET_DEFINITION_BY_PANEL.account_profiles.type).toBe(
      'account_profile',
    )
    expect(INPUT_ASSET_DEFINITION_BY_PANEL.historical_posts.workflowRoles).toEqual([
      'historical_posts',
    ])
    expect(INPUT_ASSET_DEFINITION_BY_PANEL.trend_csv.contentKind).toBe('file')
    expect(INPUT_ASSET_DEFINITION_BY_PANEL.video_creator_samples.contextSelectors).toEqual([
      'video_creator_samples_text',
    ])
    expect(INPUT_ASSET_DEFINITION_BY_PANEL.xhs_creator_profiles.type).toBe(
      'xhs_creator_profile',
    )
    expect(INPUT_ASSET_DEFINITION_BY_PANEL.xhs_creator_profiles.workflowRoles).toEqual([
      'xhs_creator_profile',
    ])
  })

  it('recognizes text input assets and builds compact text previews', () => {
    const asset: TextInputAsset = {
      ...base,
      type: 'comments',
      content: '  第一条评论\n\n第二条评论   ',
    }

    expect(isTextInputAsset(asset)).toBe(true)
    expect(isTrendCsvInputAsset(asset)).toBe(false)
    expect(inputAssetPreview(asset)).toBe('第一条评论 第二条评论')
  })

  it('recognizes trend CSV assets and builds metadata previews', () => {
    const asset: TrendCsvInputAsset = {
      ...base,
      type: 'trend_csv',
      keyword: '数字游民',
      originalFilename: 'trend.csv',
      mediaType: 'text/csv',
      byteSize: 128,
      sha256: 'abc',
      rowCount: 50,
      preview: [{ title: '普通人如何开始数字游民' }],
    }

    expect(isTextInputAsset(asset)).toBe(false)
    expect(isTrendCsvInputAsset(asset)).toBe(true)
    expect(inputAssetPreview(asset)).toBe('trend.csv · 50 行 · 数字游民')
  })

  it('returns a localized updated label without mutating the asset', () => {
    const asset: TextInputAsset = {
      ...base,
      type: 'historical_posts',
      content: '留学帖子数据合集',
    }

    const before = { ...asset }
    expect(inputAssetUpdatedLabel(asset)).toContain('2026')
    expect(asset).toEqual(before)
  })

  it('treats XHS creator profiles as text input assets', () => {
    const asset: TextInputAsset = {
      ...base,
      type: 'xhs_creator_profile',
      content: '{"schemaVersion":"xhs-creator-profile/v1","notes":[]}',
    }

    expect(isTextInputAsset(asset)).toBe(true)
    expect(inputAssetPreview(asset)).toContain('xhs-creator-profile/v1')
  })
})

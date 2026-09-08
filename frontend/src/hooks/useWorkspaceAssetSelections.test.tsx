import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { NEW_INPUT_ASSET_ID } from '../appUtils'
import type {
  InputAsset,
  MediaAsset,
  TextInputAsset,
  TrendCsvInputAsset,
} from '../types'
import { useWorkspaceAssetSelections } from './useWorkspaceAssetSelections'

const updatedAt = '2026-09-08T00:00:00Z'

function textAsset(
  id: string,
  type: TextInputAsset['type'],
  name: string,
  content = '',
): TextInputAsset {
  return {
    id,
    workspaceId: 'workspace-1',
    type,
    name,
    content,
    createdAt: updatedAt,
    updatedAt,
  }
}

const trendAsset: TrendCsvInputAsset = {
  id: 'trend-1',
  workspaceId: 'workspace-1',
  type: 'trend_csv',
  name: '数字游民趋势数据',
  keyword: '数字游民',
  originalFilename: 'trend.csv',
  mediaType: 'text/csv',
  byteSize: 128,
  sha256: 'sha',
  rowCount: 2,
  preview: [{ title: '清迈真实开销' }],
  createdAt: updatedAt,
  updatedAt,
}

const imageAsset: MediaAsset = {
  id: 'media-1',
  workspaceId: 'workspace-1',
  type: 'image',
  name: '封面',
  purpose: '小红书笔记封面',
  sourceType: 'upload',
  originalFilename: 'cover.jpg',
  mediaType: 'image/jpeg',
  byteSize: 128,
  sha256: 'sha',
  metadata: {},
  derived: {},
  userNotes: '',
  fileUrl: '/api/media-assets/media-1/file',
  externalUrl: '',
  createdAt: updatedAt,
  updatedAt,
}

function renderSelections(overrides: Partial<Parameters<typeof useWorkspaceAssetSelections>[0]> = {}) {
  const materials: InputAsset[] = [
    textAsset('profile-1', 'account_profile', '账号概况', '定位'),
    textAsset('history-1', 'historical_posts', '历史笔记', '笔记'),
    textAsset('comments-1', 'comments', '评论样本', '评论'),
    textAsset('video-sample-1', 'video_creator_samples', '视频样本', '样本'),
    textAsset('xhs-1', 'xhs_creator_profile', 'XHS QSheep 创作者主页', '{}'),
    trendAsset,
  ]
  return renderHook(() =>
    useWorkspaceAssetSelections({
      materials,
      mediaAssets: [imageAsset],
      selectedProfileInputAssetId: '',
      selectedHistoricalInputAssetId: '',
      selectedCommentsInputAssetId: '',
      selectedTrendInputAssetId: '',
      selectedVideoInputAssetId: '',
      selectedXhsCreatorProfileInputAssetId: '',
      selectedVideoWorkflowMediaAssetIds: [],
      xhsPackagePreview: null,
      ...overrides,
    }),
  )
}

describe('useWorkspaceAssetSelections', () => {
  it('groups input assets and falls back to the first saved material', () => {
    const { result } = renderSelections()

    expect(result.current.accountProfileMaterials).toHaveLength(1)
    expect(result.current.selectedProfileMaterial?.id).toBe('profile-1')
    expect(result.current.historicalMaterial?.id).toBe('history-1')
    expect(result.current.commentsMaterial?.id).toBe('comments-1')
    expect(result.current.trendMaterial?.id).toBe('trend-1')
    expect(result.current.videoCreatorSamplesMaterial?.id).toBe('video-sample-1')
  })

  it('respects explicit new-asset selections without silently falling back', () => {
    const { result } = renderSelections({
      selectedProfileInputAssetId: NEW_INPUT_ASSET_ID,
      selectedHistoricalInputAssetId: NEW_INPUT_ASSET_ID,
      selectedTrendInputAssetId: NEW_INPUT_ASSET_ID,
    })

    expect(result.current.selectedProfileMaterial).toBeNull()
    expect(result.current.historicalMaterial).toBeUndefined()
    expect(result.current.trendMaterial).toBeUndefined()
  })

  it('resolves selected media assets and matching XHS import package', () => {
    const { result } = renderSelections({
      selectedVideoWorkflowMediaAssetIds: ['media-1', 'missing-media'],
      xhsPackagePreview: {
        displayName: 'QSheep',
        noteCount: 20,
        videoNoteCount: 1,
        normalNoteCount: 19,
        commentCount: 137,
        coverReferenceCount: 20,
        topNotes: [],
        warnings: [],
        profileFileName: 'xhs_creator_profile.json',
        selectedFileCount: 21,
        imageFileCount: 20,
        matchedCoverFileCount: 20,
        missingCoverCount: 0,
      },
    })

    expect(result.current.videoWorkflowMediaAssets).toEqual([imageAsset])
    expect(result.current.matchingXhsPackageMaterial?.id).toBe('xhs-1')
  })
})

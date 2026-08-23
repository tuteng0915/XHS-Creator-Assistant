import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InputAssetsPage } from './InputAssetsPage'
import type { TextInputAsset } from '../types'

const savedState = { phase: 'saved' as const }
const idleState = { phase: 'idle' as const }

const xhsAsset: TextInputAsset = {
  id: 'xhs-1',
  workspaceId: 'workspace-1',
  type: 'xhs_creator_profile',
  name: 'XHS 秀***冰 创作者主页',
  content: JSON.stringify({
    schemaVersion: 'xhs-creator-profile/v1',
    creator: { displayName: '秀***冰' },
    notes: [
      {
        noteId: 'n1',
        title: '高互动笔记',
        metrics: { liked: 100, collected: 20, comments: 3, shares: 4 },
        comments: [{ content: '评论' }],
        cover: { relativePath: 'images/n1/0.jpg' },
      },
    ],
    warnings: ['历史 warning'],
  }),
  createdAt: '2026-08-22T00:00:00Z',
  updatedAt: '2026-08-22T00:00:00Z',
}

afterEach(() => {
  cleanup()
})

describe('InputAssetsPage', () => {
  it('renders XHS creator profile summaries, package previews, and all warnings', () => {
    render(
      <InputAssetsPage
        inputAssetPanel="xhs_creator_profiles"
        accountProfileMaterials={[]}
        historicalMaterials={[]}
        commentsMaterials={[]}
        trendMaterials={[]}
        videoCreatorSamplesMaterials={[]}
        xhsCreatorProfileMaterials={[xhsAsset]}
        selectedProfileMaterial={null}
        xhsCreatorProfileMaterial={xhsAsset}
        workspaceName="默认工作区"
        positioning=""
        accountProfileDraftName=""
        historicalPostsDraftName=""
        commentsDraftName=""
        trendCsvDraftName=""
        videoCreatorSamplesDraftName=""
        xhsCreatorProfileDraftName={xhsAsset.name}
        historicalPosts=""
        comments=""
        trendKeyword=""
        videoCreatorSamples=""
        xhsCreatorProfileContent={xhsAsset.content}
        inputAssetFormatterDraft=""
        inputAssetFormatterStatus=""
        workspaceSaveState={idleState}
        accountProfilesSaveState={idleState}
        historicalSaveState={idleState}
        commentsSaveState={idleState}
        trendSaveState={idleState}
        videoSaveState={idleState}
        xhsSaveState={savedState}
        onStartNewInputAsset={vi.fn()}
        onChooseTextMaterial={vi.fn()}
        onChooseTrendMaterial={vi.fn()}
        onFormatterDraftChange={vi.fn()}
        onApplyInputAssetFormatter={vi.fn()}
        onAccountProfileDraftNameChange={vi.fn()}
        onWorkspaceNameChange={vi.fn()}
        onPositioningChange={vi.fn()}
        onSaveAccountProfile={vi.fn()}
        onSaveAccountProfileAsNew={vi.fn()}
        onHistoricalPostsDraftNameChange={vi.fn()}
        onHistoricalPostsChange={vi.fn()}
        onSaveHistoricalPosts={vi.fn()}
        onSaveHistoricalPostsAsNew={vi.fn()}
        onCommentsDraftNameChange={vi.fn()}
        onCommentsChange={vi.fn()}
        onSaveComments={vi.fn()}
        onSaveCommentsAsNew={vi.fn()}
        onTrendCsvDraftNameChange={vi.fn()}
        onTrendKeywordChange={vi.fn()}
        onTrendFileChange={vi.fn()}
        onUploadTrendCsv={vi.fn()}
        onVideoCreatorSamplesDraftNameChange={vi.fn()}
        onVideoCreatorSamplesChange={vi.fn()}
        onSaveVideoCreatorSamples={vi.fn()}
        onSaveVideoCreatorSamplesAsNew={vi.fn()}
        onXhsCreatorProfileDraftNameChange={vi.fn()}
        onXhsCreatorProfileContentChange={vi.fn()}
        onSaveXhsCreatorProfile={vi.fn()}
        onSaveXhsCreatorProfileAsNew={vi.fn()}
        onSetInputAssetBatchFile={vi.fn()}
        onUploadTextInputAssetsCsv={vi.fn()}
        xhsImportFiles={{
          historical_posts: null,
          video_creator_samples: null,
          xhs_creator_profiles: null,
        }}
        onSetXhsImportFile={vi.fn()}
        onUploadXhsImport={vi.fn()}
        xhsPackageFiles={[new File(['{}'], 'xhs_creator_profile.json')]}
        xhsPackagePreview={{
          displayName: '秀***冰',
          profileFileName: 'xhs_creator_profile.json',
          selectedFileCount: 5,
          imageFileCount: 4,
          noteCount: 4,
          videoNoteCount: 0,
          normalNoteCount: 4,
          commentCount: 26,
          coverReferenceCount: 4,
          matchedCoverFileCount: 4,
          missingCoverCount: 0,
          topNotes: [],
          warnings: [],
        }}
        xhsPackagePreviewError=""
        xhsImportWarnings={['导入提示一', '导入提示二']}
        matchingXhsPackageMaterial={xhsAsset}
        onSetXhsPackageFiles={vi.fn()}
        onUploadXhsImportPackage={vi.fn()}
      />,
    )

    expect(screen.getByText('主页摘要')).toBeInTheDocument()
    expect(screen.getAllByText('秀***冰').length).toBeGreaterThan(0)
    expect(screen.getByText('高互动笔记')).toBeInTheDocument()
    expect(screen.getByText('导入前预览')).toBeInTheDocument()
    expect(screen.getByText('匹配封面：4')).toBeInTheDocument()
    expect(screen.getByText(/默认会更新已有资产/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '更新已有 XHS 主页' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '另存为新主页' })).toBeInTheDocument()
    expect(screen.getByText('导入提示一')).toBeInTheDocument()
    expect(screen.getByText('导入提示二')).toBeInTheDocument()
  })
})

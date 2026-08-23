import { describe, expect, it } from 'vitest'

import {
  previewXhsImportPackage,
  summarizeXhsCreatorProfileContent,
  xhsPackageRelativePaths,
} from './xhsCreatorProfile'

function fileWithRelativePath(content: string, name: string, relativePath: string) {
  const file = new File([content], name, { type: 'application/json' })
  Object.defineProperty(file, 'text', {
    value: () => Promise.resolve(content),
  })
  Object.defineProperty(file, 'webkitRelativePath', {
    value: relativePath,
  })
  return file
}

describe('xhsCreatorProfile', () => {
  it('summarizes XHS creator profile JSON for details views', () => {
    const summary = summarizeXhsCreatorProfileContent(
      JSON.stringify({
        schemaVersion: 'xhs-creator-profile/v1',
        creator: { displayName: '秀***冰' },
        notes: [
          {
            noteId: 'n1',
            title: '低互动',
            metrics: { liked: 1, collected: 1, comments: 1, shares: 1 },
            comments: [{ content: '评论' }],
            cover: { relativePath: 'images/n1/0.jpg' },
          },
          {
            noteId: 'n2',
            title: '高互动',
            metrics: { liked: 100, collected: 20, comments: 3, shares: 4 },
            comments: [],
          },
        ],
        warnings: ['缺少一张封面'],
      }),
    )

    expect(summary?.displayName).toBe('秀***冰')
    expect(summary?.noteCount).toBe(2)
    expect(summary?.commentCount).toBe(1)
    expect(summary?.coverReferenceCount).toBe(1)
    expect(summary?.topNotes[0].title).toBe('高互动')
    expect(summary?.warnings).toEqual(['缺少一张封面'])
  })

  it('previews selected import package folders before upload', async () => {
    const profile = fileWithRelativePath(
      JSON.stringify({
        schemaVersion: 'xhs-creator-profile/v1',
        creator: { displayName: 'QSheep' },
        notes: [
          {
            noteId: 'n1',
            title: '有封面',
            comments: [{ content: '评论' }],
            cover: { relativePath: 'images/n1/0.jpg' },
          },
          {
            noteId: 'n2',
            title: '缺封面',
            comments: [],
            cover: { relativePath: 'images/n2/0.jpg' },
          },
        ],
      }),
      'xhs_creator_profile.json',
      'package/xhs_creator_profile.json',
    )
    const cover = fileWithRelativePath('jpg', '0.jpg', 'package/images/n1/0.jpg')

    const preview = await previewXhsImportPackage([profile, cover])

    expect(preview?.displayName).toBe('QSheep')
    expect(preview?.selectedFileCount).toBe(2)
    expect(preview?.imageFileCount).toBe(1)
    expect(preview?.matchedCoverFileCount).toBe(1)
    expect(preview?.missingCoverCount).toBe(1)
  })

  it('strips the common selected folder prefix from package paths', () => {
    const profile = fileWithRelativePath('{}', 'xhs_creator_profile.json', '_tt/xhs_creator_profile.json')
    const cover = fileWithRelativePath('jpg', '0.jpg', '_tt/images/n1/0.jpg')

    expect(xhsPackageRelativePaths([profile, cover])).toEqual([
      'xhs_creator_profile.json',
      'images/n1/0.jpg',
    ])
  })
})

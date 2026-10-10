import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, audienceAnalysisApi, inputAssetApi, mediaAssetApi, readerSelectionApi, simulationRunApi, xhsCaptureApi } from './api'
import type { MediaAsset, TextInputAsset } from './types'

const imageAsset: MediaAsset = {
  id: 'media-image-1',
  workspaceId: 'workspace-1',
  type: 'image',
  name: '主页截图',
  purpose: '账号主页视觉定位参考',
  sourceType: 'upload',
  originalFilename: 'home.png',
  mediaType: 'image/png',
  byteSize: 128,
  sha256: 'abc',
  metadata: { width: null, height: null },
  derived: { extractedText: '', visualSummary: '', tags: [] },
  userNotes: '',
  fileUrl: '/api/media-assets/media-image-1/file',
  createdAt: '2026-07-11T10:00:00Z',
  updatedAt: '2026-07-11T10:00:00Z',
}

const historicalAsset: TextInputAsset = {
  id: 'input-1',
  workspaceId: 'workspace-1',
  type: 'historical_posts',
  name: 'XHS 导入',
  content: '### 1. 留学申请复盘',
  createdAt: '2026-08-22T00:00:00Z',
  updatedAt: '2026-08-22T00:00:00Z',
}

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

it('uses a new audience scope discriminator so old servers cannot silently ignore selected IDs', async () => {
  const fetch = vi.spyOn(globalThis,'fetch').mockImplementation(() => jsonResponse({id:'run'}))
  await audienceAnalysisApi.create('w','p','most_liked_10',['n2'])
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({sourceMaterialId:'p',scope:'selected_notes',selectionScope:'most_liked_10',selectedNoteIds:['n2']})
})

it('explains an old server scope rejection but preserves unrelated validation errors', async () => {
  const fetch = vi.spyOn(globalThis,'fetch')
    .mockImplementationOnce(() => jsonResponse({detail:[null,{type:'literal_error',loc:['body','scope'],input:'selected_notes',msg:'Input should be recent_10 or all'}]},422))
    .mockImplementationOnce(() => jsonResponse({detail:'所选笔记无效或已变更，请重新选择当前账号的笔记。'},422))
    .mockImplementationOnce(() => jsonResponse({detail:[{type:'too_short',loc:['body','selectedNoteIds'],msg:'需要至少一篇笔记'}]},422))
  await expect(audienceAnalysisApi.create('w','p','all',['n'])).rejects.toThrow('请更新并重启后端')
  await expect(audienceAnalysisApi.create('w','p','all',['n'])).rejects.toThrow('所选笔记无效或已变更')
  await expect(audienceAnalysisApi.create('w','p','all',[])).rejects.toThrow('需要至少一篇笔记')
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('uses scoped relative recommendation URLs and preserves adoption metadata on simulation creation', async()=>{
  const fetch=vi.spyOn(globalThis,'fetch').mockImplementation(()=>jsonResponse({id:'r'}))
  await readerSelectionApi.create('w',{requestKey:'key',topicId:'t',desiredCount:4})
  expect(fetch).toHaveBeenLastCalledWith('/api/workspaces/w/reader-selections',expect.objectContaining({method:'POST',
    body:JSON.stringify({requestKey:'key',topicId:'t',desiredCount:4})}))
  await readerSelectionApi.get('w','r')
  expect(fetch.mock.calls.at(-1)?.[0]).toBe('/api/workspaces/w/reader-selections/r')
  const payload={topicId:'t',simulatedFanIds:['d','a'],readerSelectionId:'r',readerSelectionInputHash:'a'.repeat(64),mode:'live' as const}
  await simulationRunApi.create('w',payload)
  expect(fetch).toHaveBeenLastCalledWith('/api/workspaces/w/simulation-runs',expect.objectContaining({method:'POST',body:JSON.stringify(payload)}))
})

it('sends the same explicit account notes to retrieval and simulation without a legacy whole-account target',async()=>{
  const fetch=vi.spyOn(globalThis,'fetch').mockImplementation(()=>jsonResponse({id:'r'}))
  const accountNoteSelection={sourceMaterialId:'p',selectedNoteIds:['n1','n3']}
  await readerSelectionApi.create('w',{requestKey:'key',desiredCount:3,accountNoteSelection})
  await simulationRunApi.create('w',{mode:'live',simulatedFanIds:['fan'],accountNoteSelection})
  for(const [,init] of fetch.mock.calls){
    const payload=JSON.parse(String(init?.body))
    expect(payload.accountNoteSelection).toEqual(accountNoteSelection)
    expect(payload).not.toHaveProperty('accountProfileId')
  }
})

it('explains old account-scope servers without downgrading to a whole-account request',async()=>{
  const fetch=vi.spyOn(globalThis,'fetch')
    .mockImplementationOnce(()=>jsonResponse({detail:[null,{type:'extra_forbidden',loc:['body','accountNoteSelection'],msg:'Extra inputs are not permitted'}]},422))
    .mockImplementationOnce(()=>jsonResponse({detail:'请选择一个账号、选题、草稿、历史笔记或手动标题'},422))
    .mockImplementationOnce(()=>jsonResponse({detail:'所选笔记无效或已变更，请重新选择当前账号的笔记。'},422))
  const accountNoteSelection={sourceMaterialId:'p',selectedNoteIds:['n']}
  await expect(readerSelectionApi.create('w',{requestKey:'k',desiredCount:3,accountNoteSelection})).rejects.toThrow('请更新并重启后端')
  await expect(simulationRunApi.create('w',{mode:'live',accountNoteSelection})).rejects.toThrow('请更新并重启后端')
  await expect(simulationRunApi.create('w',{mode:'live',accountNoteSelection})).rejects.toThrow('所选笔记无效或已变更')
  expect(fetch).toHaveBeenCalledTimes(3)
})

describe('mediaAssetApi', () => {
  it('uses relative URLs and FormData for media uploads', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(await jsonResponse(imageAsset, 201))
    const file = new File(['fake-image'], 'home.png', { type: 'image/png' })

    const response = await mediaAssetApi.upload(
      'workspace-1',
      'image',
      '主页截图',
      '账号主页视觉定位参考',
      file,
    )

    expect(response.id).toBe('media-image-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workspaces/workspace-1/media-assets/upload',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
    const init = fetchMock.mock.calls[0][1] as RequestInit
    const form = init.body as FormData
    expect(form.get('type')).toBe('image')
    expect(form.get('name')).toBe('主页截图')
    expect(form.get('purpose')).toBe('账号主页视觉定位参考')
    expect(form.get('file')).toBe(file)
  })

  it('sends JSON updates and surfaces backend validation errors', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(await jsonResponse({ ...imageAsset, name: '主页截图 v2' }))
      .mockResolvedValueOnce(
        await jsonResponse({ detail: 'Media asset name cannot be blank' }, 422),
      )

    const updated = await mediaAssetApi.update('media-image-1', {
      name: '主页截图 v2',
      purpose: '主页视觉定位参考',
      expectedUpdatedAt: imageAsset.updatedAt,
    })

    expect(updated.name).toBe('主页截图 v2')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/media-assets/media-image-1',
      expect.objectContaining({
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({
      name: '主页截图 v2',
      purpose: '主页视觉定位参考',
      expectedUpdatedAt: imageAsset.updatedAt,
    })

    await expect(
      mediaAssetApi.update('media-image-1', {
        name: ' ',
        expectedUpdatedAt: imageAsset.updatedAt,
      }),
    ).rejects.toEqual(new ApiError('Media asset name cannot be blank', 422))
  })
})

describe('inputAssetApi', () => {
  it('uploads XHS offline import files through the backend only', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      await jsonResponse(
        {
          inputAsset: historicalAsset,
          parsedNoteCount: 1,
          sourceUrl: 'https://www.xiaohongshu.com/user/profile/u1',
          warnings: [],
        },
        201,
      ),
    )
    const file = new File(['{"schemaVersion":"xhs-profile-import/v1"}'], 'xhs.json', {
      type: 'application/json',
    })

    const response = await inputAssetApi.uploadXhsImport(
      'workspace-1',
      'historical_posts',
      file,
    )

    expect(response.inputAsset.id).toBe('input-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workspaces/workspace-1/input-assets/xhs-import',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
    const init = fetchMock.mock.calls[0][1] as RequestInit
    const form = init.body as FormData
    expect(form.get('type')).toBe('historical_posts')
    expect(form.get('file')).toBe(file)
  })

  it('uploads XHS creator profile imports as the dedicated input asset type', async () => {
    const xhsAsset: TextInputAsset = {
      ...historicalAsset,
      id: 'xhs-profile-1',
      type: 'xhs_creator_profile',
      name: 'XHS QSheep 创作者主页',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      await jsonResponse(
        {
          inputAsset: xhsAsset,
          parsedNoteCount: 20,
          sourceUrl: 'https://www.xiaohongshu.com/user/profile/u1',
          warnings: [],
        },
        201,
      ),
    )
    const file = new File(['{"schemaVersion":"xhs-creator-profile/v1"}'], 'xhs.json', {
      type: 'application/json',
    })

    await inputAssetApi.uploadXhsImport(
      'workspace-1',
      'xhs_creator_profile',
      file,
      'XHS QSheep 创作者主页',
    )

    const init = fetchMock.mock.calls[0][1] as RequestInit
    const form = init.body as FormData
    expect(form.get('type')).toBe('xhs_creator_profile')
    expect(form.get('name')).toBe('XHS QSheep 创作者主页')
  })

  it('uploads XHS import packages with profile JSON and relative media paths', async () => {
    const xhsAsset: TextInputAsset = {
      ...historicalAsset,
      id: 'xhs-profile-1',
      type: 'xhs_creator_profile',
      name: 'XHS QSheep 创作者主页',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      await jsonResponse(
        {
          inputAsset: xhsAsset,
          mediaAssets: [imageAsset],
          parsedNoteCount: 1,
          sourceUrl: 'https://www.xiaohongshu.com/user/profile/u1',
          warnings: [],
        },
        201,
      ),
    )
    const profile = new File(
      ['{"schemaVersion":"xhs-creator-profile/v1"}'],
      'xhs_creator_profile.json',
      { type: 'application/json' },
    )
    const cover = new File(['fake-image'], '0.jpg', { type: 'image/jpeg' })

    const response = await inputAssetApi.uploadXhsImportPackage(
      'workspace-1',
      profile,
      [cover],
      ['images/n1/0.jpg'],
      '',
      true,
    )

    expect(response.mediaAssets).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workspaces/workspace-1/input-assets/xhs-import-package',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
    const init = fetchMock.mock.calls[0][1] as RequestInit
    const form = init.body as FormData
    expect(form.get('name')).toBe('')
    expect(form.get('saveAsNew')).toBe('true')
    expect((form.get('profile') as File).name).toBe('xhs_creator_profile.json')
    expect((form.get('files') as File).name).toBe('images/n1/0.jpg')
    expect(form.get('relativePaths')).toBe('images/n1/0.jpg')
  })
})

describe('xhsCaptureApi', () => {
  it('creates a bounded backend capture job with a relative API URL', async () => {
    const job = {
      id: 'capture-1',
      workspaceId: 'workspace-1',
      profileUrl: 'https://www.xiaohongshu.com/user/profile/u1',
      resolvedUrl: '',
      status: 'pending',
      noteLimit: 20,
      includeComments: true,
      statusMessage: '正在准备导入任务',
      progress: {
        phase: 'starting', capturedNotes: 0, capturedComments: 0,
        commentNotesCompleted: 0, commentNotesTotal: null,
      },
      error: '',
      resultInputAssetId: null,
      createdAt: '2026-09-23T10:00:00Z',
      startedAt: null,
      completedAt: null,
      updatedAt: '2026-09-23T10:00:00Z',
    }
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(await jsonResponse(job, 202))

    const response = await xhsCaptureApi.create('workspace-1', {
      profileUrl: job.profileUrl,
      noteLimit: 20,
      includeComments: true,
    })

    expect(response.id).toBe('capture-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/workspaces/workspace-1/xhs-capture-jobs',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
})

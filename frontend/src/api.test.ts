import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, mediaAssetApi } from './api'
import type { MediaAsset } from './types'

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

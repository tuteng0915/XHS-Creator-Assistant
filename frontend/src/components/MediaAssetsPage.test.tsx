import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MediaAssetsPage } from './MediaAssetsPage'
import type { MediaAsset } from '../types'

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

const videoAsset: MediaAsset = {
  ...imageAsset,
  id: 'media-video-1',
  type: 'video',
  name: 'AI短剧样本',
  purpose: '视频质量诊断样本',
  sourceType: 'upload',
  originalFilename: 'sample.mp4',
  mediaType: 'video/mp4',
  metadata: { durationSeconds: null, width: null, height: null, fps: null },
  derived: {
    transcript: '',
    sceneSummary: '',
    visualSummary: '',
    audioSummary: '',
    tags: [],
    metrics: {},
  },
  fileUrl: '/api/media-assets/media-video-1/file',
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
  cleanup()
  vi.restoreAllMocks()
})

describe('MediaAssetsPage', () => {
  it('renders and saves editable image metadata without replacing the file', async () => {
    const onAssetsChange = vi.fn()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      expect(String(input)).toBe('/api/media-assets/media-image-1')
      expect(init?.method).toBe('PATCH')
      const body = JSON.parse(String(init?.body)) as {
        derived: Record<string, unknown>
        userNotes: string
        expectedUpdatedAt: string
      }
      expect(body.derived.visualSummary).toBe('主页强调留学申请路径。')
      expect(body.userNotes).toBe('截图来自小红书主页。')
      expect(body.expectedUpdatedAt).toBe(imageAsset.updatedAt)
      return jsonResponse({
        ...imageAsset,
        name: '主页截图',
        derived: body.derived,
        userNotes: body.userNotes,
        updatedAt: '2026-07-11T11:00:00Z',
      })
    })

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="image"
        assets={[imageAsset]}
        onAssetsChange={onAssetsChange}
      />,
    )

    expect(screen.getAllByText('主页截图').length).toBeGreaterThan(0)
    expect(screen.getByAltText('主页截图')).toHaveAttribute(
      'src',
      imageAsset.fileUrl,
    )
    fireEvent.change(screen.getByLabelText('derived JSON'), {
      target: {
        value: JSON.stringify(
          {
            extractedText: '关注留学申请',
            visualSummary: '主页强调留学申请路径。',
            tags: ['主页'],
          },
          null,
          2,
        ),
      },
    })
    fireEvent.change(screen.getByLabelText('用户备注'), {
      target: { value: '截图来自小红书主页。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存图片素材' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(onAssetsChange).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'media-image-1',
        userNotes: '截图来自小红书主页。',
      }),
    ])
    expect(await screen.findByText('已保存')).toBeInTheDocument()
  })

  it('uploads a video asset and selects the returned asset', async () => {
    const onAssetsChange = vi.fn()
    const uploaded: MediaAsset = {
      ...imageAsset,
      id: 'media-video-1',
      type: 'video',
      name: 'AI短剧样本',
      purpose: '视频质量诊断样本',
      originalFilename: 'sample.mp4',
      mediaType: 'video/mp4',
      metadata: { durationSeconds: null, width: null, height: null, fps: null },
      derived: {
        transcript: '',
        sceneSummary: '',
        visualSummary: '',
        audioSummary: '',
        tags: [],
        metrics: {},
      },
      fileUrl: '/api/media-assets/media-video-1/file',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      expect(String(input)).toBe('/api/workspaces/workspace-1/media-assets/upload')
      expect(init?.method).toBe('POST')
      const form = init?.body as FormData
      expect(form.get('type')).toBe('video')
      expect(form.get('name')).toBe('AI短剧样本')
      expect(form.get('purpose')).toBe('视频质量诊断样本')
      expect(form.get('file')).toBeInstanceOf(File)
      return jsonResponse(uploaded, 201)
    })

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="video"
        assets={[]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('视频素材名称'), {
      target: { value: 'AI短剧样本' },
    })
    fireEvent.change(screen.getAllByLabelText('用途')[0], {
      target: { value: '视频质量诊断样本' },
    })
    fireEvent.change(screen.getByLabelText('文件'), {
      target: {
        files: [new File(['fake-video'], 'sample.mp4', { type: 'video/mp4' })],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '上传视频' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(onAssetsChange).toHaveBeenCalledWith([uploaded])
    expect(await screen.findByText('已保存')).toBeInTheDocument()
  })

  it('does not call the API when editable JSON is invalid', async () => {
    const onAssetsChange = vi.fn()
    const fetchMock = vi.spyOn(globalThis, 'fetch')

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="image"
        assets={[imageAsset]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('derived JSON'), {
      target: { value: 'not-json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存图片素材' }))

    expect(fetchMock).not.toHaveBeenCalled()
    expect(onAssetsChange).not.toHaveBeenCalled()
    expect(await screen.findByRole('status')).toHaveTextContent(/derived:/)
  })

  it('requires a file before uploading media', async () => {
    const onAssetsChange = vi.fn()
    const fetchMock = vi.spyOn(globalThis, 'fetch')

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="image"
        assets={[]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('图片素材名称'), {
      target: { value: '主页截图' },
    })
    fireEvent.click(screen.getByRole('button', { name: '上传图片' }))

    expect(fetchMock).not.toHaveBeenCalled()
    expect(onAssetsChange).not.toHaveBeenCalled()
    expect(await screen.findByText('请选择要上传的文件')).toBeInTheDocument()
  })

  it('runs image understanding and saves the confirmed result into derived data', async () => {
    const onAssetsChange = vi.fn()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url === '/api/skills/skill-understand-image/invoke') {
        expect(init?.method).toBe('POST')
        const body = JSON.parse(String(init?.body)) as {
          mode: string
          input: Record<string, unknown>
        }
        expect(body.mode).toBe('live')
        expect(body.input.mediaAssetId).toBe('media-image-1')
        return jsonResponse({
          skillAssetId: 'skill-understand-image',
          skillId: 'media.understand_image',
          status: 'completed',
          output: {
            text: '主页视觉强调留学申请路径。',
            imageUnderstanding: {
              visualSummary: '主页视觉强调留学申请路径。',
              extractedText: '留学申请',
              styleTags: ['清爽'],
              creatorSignals: ['专业可信'],
              risks: [],
              uncertainties: [],
            },
          },
          modelMetadata: { provider: 'qwen' },
        })
      }
      if (url === '/api/media-assets/media-image-1') {
        expect(init?.method).toBe('PATCH')
        const body = JSON.parse(String(init?.body)) as {
          derived: Record<string, unknown>
          expectedUpdatedAt: string
        }
        expect(body.expectedUpdatedAt).toBe(imageAsset.updatedAt)
        expect(body.derived.visualSummary).toBe('主页视觉强调留学申请路径。')
        expect(body.derived.imageUnderstanding).toEqual(
          expect.objectContaining({ creatorSignals: ['专业可信'] }),
        )
        expect(body.derived.qwenUnderstanding).toEqual(
          expect.objectContaining({
            text: '主页视觉强调留学申请路径。',
            structured: expect.objectContaining({ extractedText: '留学申请' }),
          }),
        )
        return jsonResponse({
          ...imageAsset,
          derived: body.derived,
          updatedAt: '2026-07-11T12:00:00Z',
        })
      }
      throw new Error(`unexpected request ${url}`)
    })

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="image"
        mode="live"
        skills={[
          {
            id: 'skill-understand-image',
            workspaceId: 'workspace-1',
            skillId: 'media.understand_image',
            displayName: 'Understand Image Asset',
            category: 'media',
            purpose: '',
            artifactEffect: '',
            source: 'builtin',
            status: 'enabled',
            version: 'v1',
            updatedAt: '2026-07-11T10:00:00Z',
          },
        ]}
        assets={[imageAsset]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '理解图片' }))
    expect(await screen.findByText('主页视觉强调留学申请路径。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '保存理解结果到素材' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(onAssetsChange).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'media-image-1',
        derived: expect.objectContaining({
          visualSummary: '主页视觉强调留学申请路径。',
        }),
      }),
    ])
  })

  it('generates an image media asset through the media skill and prepends it', async () => {
    const onAssetsChange = vi.fn()
    const generated: MediaAsset = {
      ...imageAsset,
      id: 'media-generated-1',
      name: 'Qwen 生成图片',
      sourceType: 'generated',
      originalFilename: 'qwen-image.png',
      externalUrl: 'https://cdn.example.test/qwen-image.png',
      fileUrl: '/api/media-assets/media-generated-1/file',
      metadata: { prompt: '生成一张主页参考图' },
      updatedAt: '2026-07-11T12:00:00Z',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      expect(String(input)).toBe('/api/skills/skill-generate-image/invoke')
      expect(init?.method).toBe('POST')
      const body = JSON.parse(String(init?.body)) as {
        input: Record<string, unknown>
      }
      expect(body.input.prompt).toBe('生成一张主页参考图')
      expect(body.input.size).toBe('1024*1024')
      return jsonResponse({
        skillAssetId: 'skill-generate-image',
        skillId: 'media.generate_image',
        status: 'completed',
        output: { mediaAsset: generated },
        modelMetadata: { provider: 'qwen' },
      })
    })

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="image"
        mode="live"
        skills={[
          {
            id: 'skill-generate-image',
            workspaceId: 'workspace-1',
            skillId: 'media.generate_image',
            displayName: 'Generate Image Asset',
            category: 'media',
            purpose: '',
            artifactEffect: '',
            source: 'builtin',
            status: 'enabled',
            version: 'v1',
            updatedAt: '2026-07-11T10:00:00Z',
          },
        ]}
        assets={[imageAsset]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('生成 prompt'), {
      target: { value: '生成一张主页参考图' },
    })
    fireEvent.click(screen.getByRole('button', { name: '生成图片' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(onAssetsChange).toHaveBeenCalledWith([generated, imageAsset])
  })

  it('derives video preview frames and keeps the parent video selected', async () => {
    const onAssetsChange = vi.fn()
    const updatedVideo: MediaAsset = {
      ...videoAsset,
      derived: {
        ...videoAsset.derived,
        videoPreview: {
          frameCount: 1,
          frames: [
            {
              mediaAssetId: 'media-frame-1',
              fileUrl: '/api/media-assets/media-frame-1/file',
              frameIndex: 1,
            },
          ],
        },
      },
      updatedAt: '2026-07-11T12:00:00Z',
    }
    const frame: MediaAsset = {
      ...imageAsset,
      id: 'media-frame-1',
      name: 'AI短剧样本 - 抽帧 01',
      sourceType: 'extracted_frame',
      originalFilename: 'sample-frame-01.jpg',
      mediaType: 'image/jpeg',
      fileUrl: '/api/media-assets/media-frame-1/file',
      metadata: { sourceVideoAssetId: 'media-video-1', frameIndex: 1 },
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      expect(String(input)).toBe('/api/media-assets/media-video-1/derive-video-preview')
      expect(init?.method).toBe('POST')
      return jsonResponse({ videoAsset: updatedVideo, frames: [frame] })
    })

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="video"
        assets={[videoAsset]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '抽取视频帧预览' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(onAssetsChange).toHaveBeenCalledWith([updatedVideo, frame])
    expect(await screen.findByText('已抽取 1 帧')).toBeInTheDocument()
  })

  it('uses mediaAssetId when understanding a local uploaded video without public URLs', async () => {
    const onAssetsChange = vi.fn()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      expect(String(input)).toBe('/api/skills/skill-understand-video/invoke')
      expect(init?.method).toBe('POST')
      const body = JSON.parse(String(init?.body)) as {
        mode: string
        input: Record<string, unknown>
      }
      expect(body.mode).toBe('live')
      expect(body.input.mediaAssetId).toBe('media-video-1')
      expect(body.input.videoUrl).toBeUndefined()
      expect(body.input.videoFrameUrls).toBeUndefined()
      return jsonResponse({
        skillAssetId: 'skill-understand-video',
        skillId: 'media.understand_video',
        status: 'completed',
        output: {
          text: '短剧开场冲突明确。',
          videoAsset: {
            ...videoAsset,
            derived: {
              ...videoAsset.derived,
              videoPreview: {
                frameCount: 1,
                frames: [{ mediaAssetId: 'media-frame-1', frameIndex: 1 }],
              },
            },
            updatedAt: '2026-07-11T12:00:00Z',
          },
          derivedFrameAssets: [
            {
              ...imageAsset,
              id: 'media-frame-1',
              sourceType: 'extracted_frame',
              originalFilename: 'sample-frame-01.jpg',
            },
          ],
          videoUnderstanding: {
            sceneSummary: '短剧开场冲突明确。',
            visualSummary: '竖屏人物对话。',
            qualitySignals: ['剧情驱动'],
            creatorSignals: ['系列化'],
            incentiveFitSignals: ['适合激励'],
          },
        },
        modelMetadata: { provider: 'qwen' },
      })
    })

    render(
      <MediaAssetsPage
        workspaceId="workspace-1"
        mediaType="video"
        mode="live"
        skills={[
          {
            id: 'skill-understand-video',
            workspaceId: 'workspace-1',
            skillId: 'media.understand_video',
            displayName: 'Understand Video Asset',
            category: 'media',
            purpose: '',
            artifactEffect: '',
            source: 'builtin',
            status: 'enabled',
            version: 'v1',
            updatedAt: '2026-07-11T10:00:00Z',
          },
        ]}
        assets={[videoAsset]}
        onAssetsChange={onAssetsChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '理解视频' }))

    expect(await screen.findByText('短剧开场冲突明确。')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(onAssetsChange).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'media-video-1',
        updatedAt: '2026-07-11T12:00:00Z',
      }),
      expect.objectContaining({ id: 'media-frame-1' }),
    ])
  })
})

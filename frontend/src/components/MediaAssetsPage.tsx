import { useEffect, useMemo, useState } from 'react'

import { mediaAssetApi, skillApi } from '../api'
import type { MediaAsset, MediaAssetType, SkillSummary } from '../types'
import { SaveIndicator, type SaveState } from './StageResultViews'

type MediaAssetsPageProps = {
  workspaceId: string
  mediaType: MediaAssetType
  assets: MediaAsset[]
  skills?: SkillSummary[]
  mode?: 'demo' | 'live'
  onModeChange?: (mode: 'demo' | 'live') => void
  onAssetsChange: (assets: MediaAsset[]) => void
}

type PreviewFrame = { mediaAssetId: string; fileUrl: string; frameIndex?: number }

const MEDIA_LABEL = {
  image: {
    icon: '🖼',
    label: '图文素材',
    singular: '图文素材',
    empty: '还没有已上传的图文素材。',
    accept: 'image/*',
    upload: '上传图片',
  },
  video: {
    icon: '🎞',
    label: '视频素材',
    singular: '视频素材',
    empty: '还没有已上传的视频素材。',
    accept: 'video/*',
    upload: '上传视频',
  },
} as const

function mediaAssetPreview(asset: MediaAsset): string {
  if (asset.type === 'image') {
    const width = asset.metadata.width
    const height = asset.metadata.height
    const size = width && height ? `${width}×${height}` : '尺寸未填写'
    return `${asset.originalFilename} · ${size}`
  }
  const duration = asset.metadata.durationSeconds
  const label = duration ? `${duration} 秒` : '时长未填写'
  return `${asset.originalFilename} · ${label}`
}

function formatJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2)
}

function parseJsonField(value: string, label: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(`${label} 必须是 JSON object`)
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    if (error instanceof Error) throw new Error(`${label}: ${error.message}`)
    throw new Error(`${label}: JSON 格式错误`)
  }
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

function outputText(output: Record<string, unknown>): string {
  const text = output.text
  if (typeof text === 'string') return text
  const note = output.note
  if (typeof note === 'string') return note
  return JSON.stringify(output, null, 2)
}

function outputMediaAsset(output: Record<string, unknown>): MediaAsset | null {
  const value = output.mediaAsset
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as MediaAsset
}

function outputMediaAssetList(output: Record<string, unknown>): MediaAsset[] {
  const assets: MediaAsset[] = []
  const videoAsset = output.videoAsset
  if (videoAsset && typeof videoAsset === 'object' && !Array.isArray(videoAsset)) {
    assets.push(videoAsset as MediaAsset)
  }
  const frames = output.derivedFrameAssets
  if (Array.isArray(frames)) {
    for (const frame of frames) {
      if (frame && typeof frame === 'object' && !Array.isArray(frame)) {
        assets.push(frame as MediaAsset)
      }
    }
  }
  return assets
}

function derivedWithUnderstanding(
  asset: MediaAsset,
  understandingText: string,
  understandingOutput?: Record<string, unknown> | null,
): Record<string, unknown> {
  const base = { ...asset.derived }
  const stamp = new Date().toISOString()
  const imageUnderstanding = understandingOutput?.imageUnderstanding
  const videoUnderstanding = understandingOutput?.videoUnderstanding
  if (asset.type === 'image') {
    const structured =
      imageUnderstanding && typeof imageUnderstanding === 'object'
        ? (imageUnderstanding as Record<string, unknown>)
        : {}
    const visualSummary =
      typeof structured.visualSummary === 'string' && structured.visualSummary
        ? structured.visualSummary
        : understandingText
    return {
      ...base,
      visualSummary,
      extractedText:
        typeof structured.extractedText === 'string'
          ? structured.extractedText
          : base.extractedText,
      tags: Array.isArray(structured.styleTags) ? structured.styleTags : base.tags,
      imageUnderstanding: structured,
      qwenUnderstanding: { text: understandingText, structured, updatedAt: stamp },
    }
  }
  const structured =
    videoUnderstanding && typeof videoUnderstanding === 'object'
      ? (videoUnderstanding as Record<string, unknown>)
      : {}
  const sceneSummary =
    typeof structured.sceneSummary === 'string' && structured.sceneSummary
      ? structured.sceneSummary
      : understandingText
  return {
    ...base,
    sceneSummary,
    transcript:
      typeof structured.transcript === 'string' ? structured.transcript : base.transcript,
    visualSummary:
      typeof structured.visualSummary === 'string'
        ? structured.visualSummary
        : base.visualSummary,
    audioSummary:
      typeof structured.audioSummary === 'string'
        ? structured.audioSummary
        : base.audioSummary,
    tags: Array.isArray(structured.qualitySignals) ? structured.qualitySignals : base.tags,
    videoUnderstanding: structured,
    qwenUnderstanding: { text: understandingText, structured, updatedAt: stamp },
  }
}

export function MediaAssetsPage({
  workspaceId,
  mediaType,
  assets,
  skills = [],
  mode = 'demo',
  onModeChange,
  onAssetsChange,
}: MediaAssetsPageProps) {
  const definition = MEDIA_LABEL[mediaType]
  const understandSkillId =
    mediaType === 'image' ? 'media.understand_image' : 'media.understand_video'
  const generateSkillId =
    mediaType === 'image' ? 'media.generate_image' : 'media.generate_video'
  const understandSkill = skills.find((skill) => skill.skillId === understandSkillId)
  const generateSkill = skills.find((skill) => skill.skillId === generateSkillId)
  const filteredAssets = useMemo(
    () => assets.filter((asset) => asset.type === mediaType),
    [assets, mediaType],
  )
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const selectedAsset =
    filteredAssets.find((asset) => asset.id === selectedAssetId) ||
    filteredAssets[0] ||
    null
  const [uploadName, setUploadName] = useState('')
  const [uploadPurpose, setUploadPurpose] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftPurpose, setDraftPurpose] = useState('')
  const [metadataDraft, setMetadataDraft] = useState('{}')
  const [derivedDraft, setDerivedDraft] = useState('{}')
  const [userNotesDraft, setUserNotesDraft] = useState('')
  const [saveState, setSaveState] = useState<SaveState>({ phase: 'idle' })
  const [uploadState, setUploadState] = useState<SaveState>({ phase: 'idle' })
  const [understandPrompt, setUnderstandPrompt] = useState(
    mediaType === 'image'
      ? '请描述这张图片，并提取对创作者账号/内容判断有用的视觉线索。'
      : '请分析这个视频或视频帧，提取画面、叙事、质量和创作者运营线索。',
  )
  const [videoReferenceUrls, setVideoReferenceUrls] = useState('')
  const [understandingResult, setUnderstandingResult] = useState('')
  const [understandingOutput, setUnderstandingOutput] =
    useState<Record<string, unknown> | null>(null)
  const [understandingState, setUnderstandingState] = useState<SaveState>({
    phase: 'idle',
  })
  const [understandingSaveState, setUnderstandingSaveState] = useState<SaveState>({
    phase: 'idle',
  })
  const [videoPreviewState, setVideoPreviewState] = useState<SaveState>({
    phase: 'idle',
  })
  const [generationPrompt, setGenerationPrompt] = useState('')
  const [generationName, setGenerationName] = useState('')
  const [generationPurpose, setGenerationPurpose] = useState('')
  const [imageSize, setImageSize] = useState('1024*1024')
  const [videoResolution, setVideoResolution] = useState('720P')
  const [videoRatio, setVideoRatio] = useState('16:9')
  const [videoDuration, setVideoDuration] = useState('5')
  const [generationState, setGenerationState] = useState<SaveState>({
    phase: 'idle',
  })
  const [activeActionPanel, setActiveActionPanel] = useState<
    'upload' | 'generate' | null
  >(null)
  const previewFrames = useMemo(() => {
    if (!selectedAsset || selectedAsset.type !== 'video') return []
    const videoPreview = selectedAsset.derived.videoPreview
    if (!videoPreview || typeof videoPreview !== 'object' || Array.isArray(videoPreview)) {
      return []
    }
    const frames = (videoPreview as Record<string, unknown>).frames
    if (!Array.isArray(frames)) return []
    const parsedFrames: PreviewFrame[] = []
    for (const frame of frames) {
      if (!frame || typeof frame !== 'object' || Array.isArray(frame)) continue
      const value = frame as Record<string, unknown>
      const mediaAssetId =
        typeof value.mediaAssetId === 'string' ? value.mediaAssetId : ''
      const fileUrl = typeof value.fileUrl === 'string' ? value.fileUrl : ''
      const frameIndex =
        typeof value.frameIndex === 'number' ? value.frameIndex : undefined
      if (mediaAssetId && fileUrl) {
        parsedFrames.push({ mediaAssetId, fileUrl, frameIndex })
      }
    }
    return parsedFrames
  }, [selectedAsset])

  useEffect(() => {
    setSelectedAssetId('')
    setUploadName('')
    setUploadPurpose('')
    setUploadFile(null)
    setSaveState({ phase: 'idle' })
    setUploadState({ phase: 'idle' })
    setUnderstandingResult('')
    setUnderstandingOutput(null)
    setUnderstandingState({ phase: 'idle' })
    setUnderstandingSaveState({ phase: 'idle' })
    setVideoPreviewState({ phase: 'idle' })
    setGenerationPrompt('')
    setGenerationName('')
    setGenerationPurpose('')
    setVideoReferenceUrls('')
    setActiveActionPanel(null)
    setUnderstandPrompt(
      mediaType === 'image'
        ? '请描述这张图片，并提取对创作者账号/内容判断有用的视觉线索。'
        : '请分析这个视频或视频帧，提取画面、叙事、质量和创作者运营线索。',
    )
  }, [mediaType, workspaceId])

  useEffect(() => {
    if (!selectedAsset) {
      setDraftName('')
      setDraftPurpose('')
      setMetadataDraft('{}')
      setDerivedDraft('{}')
      setUserNotesDraft('')
      return
    }
    setDraftName(selectedAsset.name)
    setDraftPurpose(selectedAsset.purpose)
    setMetadataDraft(formatJson(selectedAsset.metadata))
    setDerivedDraft(formatJson(selectedAsset.derived))
    setUserNotesDraft(selectedAsset.userNotes)
    setSaveState({ phase: 'idle' })
    setUnderstandingSaveState({ phase: 'idle' })
    setVideoPreviewState({ phase: 'idle' })
  }, [selectedAsset])

  function mergeAssets(nextAssets: MediaAsset[]) {
    const byId = new Map(assets.map((asset) => [asset.id, asset]))
    for (const asset of nextAssets) {
      byId.set(asset.id, asset)
    }
    onAssetsChange(Array.from(byId.values()))
  }

  async function uploadAsset() {
    if (!uploadFile) {
      setUploadState({ phase: 'error', message: '请选择要上传的文件' })
      return
    }
    setUploadState({ phase: 'saving' })
    try {
      const uploaded = await mediaAssetApi.upload(
        workspaceId,
        mediaType,
        uploadName || uploadFile.name,
        uploadPurpose,
        uploadFile,
      )
      onAssetsChange([uploaded, ...assets.filter((asset) => asset.id !== uploaded.id)])
      setSelectedAssetId(uploaded.id)
      setUploadName('')
      setUploadPurpose('')
      setUploadFile(null)
      setUploadState({ phase: 'saved' })
    } catch (error) {
      setUploadState({
        phase: 'error',
        message: error instanceof Error ? error.message : '上传失败',
      })
    }
  }

  async function saveAsset() {
    if (!selectedAsset) return
    setSaveState({ phase: 'saving' })
    try {
      const updated = await mediaAssetApi.update(selectedAsset.id, {
        name: draftName,
        purpose: draftPurpose,
        metadata: parseJsonField(metadataDraft, 'metadata'),
        derived: parseJsonField(derivedDraft, 'derived'),
        userNotes: userNotesDraft,
        expectedUpdatedAt: selectedAsset.updatedAt,
      })
      onAssetsChange(
        assets.map((asset) => (asset.id === updated.id ? updated : asset)),
      )
      setSaveState({ phase: 'saved' })
    } catch (error) {
      setSaveState({
        phase: 'error',
        message: error instanceof Error ? error.message : '保存失败',
      })
    }
  }

  async function runUnderstanding() {
    if (!selectedAsset) return
    if (!understandSkill) {
      setUnderstandingState({ phase: 'error', message: '未找到对应的 Qwen 理解 skill' })
      return
    }
    setUnderstandingState({ phase: 'saving' })
    setUnderstandingResult('')
    setUnderstandingOutput(null)
    try {
      const input: Record<string, unknown> = { prompt: understandPrompt }
      if (mediaType === 'image') {
        input.mediaAssetId = selectedAsset.id
      } else {
        const references = splitLines(videoReferenceUrls)
        if (references.length > 1) {
          input.videoFrameUrls = references
        } else if (references.length === 1) {
          input.videoUrl = references[0]
        } else if (selectedAsset.externalUrl) {
          input.videoUrl = selectedAsset.externalUrl
        } else {
          input.mediaAssetId = selectedAsset.id
        }
      }
      const response = await skillApi.invoke(understandSkill.id, { mode, input })
      const returnedAssets = outputMediaAssetList(response.output)
      if (returnedAssets.length) {
        mergeAssets(returnedAssets)
      }
      setUnderstandingResult(outputText(response.output))
      setUnderstandingOutput(response.output)
      setUnderstandingState({ phase: 'saved' })
      setUnderstandingSaveState({ phase: 'idle' })
    } catch (error) {
      setUnderstandingState({
        phase: 'error',
        message: error instanceof Error ? error.message : '理解失败',
      })
    }
  }

  async function deriveVideoPreview() {
    if (!selectedAsset || selectedAsset.type !== 'video') return
    setVideoPreviewState({ phase: 'saving' })
    try {
      const response = await mediaAssetApi.deriveVideoPreview(selectedAsset.id)
      mergeAssets([response.videoAsset, ...response.frames])
      setSelectedAssetId(response.videoAsset.id)
      setVideoPreviewState({
        phase: 'saved',
        message: `已抽取 ${response.frames.length} 帧`,
      })
    } catch (error) {
      setVideoPreviewState({
        phase: 'error',
        message: error instanceof Error ? error.message : '抽帧失败',
      })
    }
  }

  async function saveUnderstandingToAsset() {
    if (!selectedAsset || !understandingResult) return
    setUnderstandingSaveState({ phase: 'saving' })
    try {
      const nextDerived = derivedWithUnderstanding(
        selectedAsset,
        understandingResult,
        understandingOutput,
      )
      const updated = await mediaAssetApi.update(selectedAsset.id, {
        derived: nextDerived,
        expectedUpdatedAt: selectedAsset.updatedAt,
      })
      onAssetsChange(
        assets.map((asset) => (asset.id === updated.id ? updated : asset)),
      )
      setDerivedDraft(formatJson(updated.derived))
      setUnderstandingSaveState({ phase: 'saved' })
    } catch (error) {
      setUnderstandingSaveState({
        phase: 'error',
        message: error instanceof Error ? error.message : '保存理解结果失败',
      })
    }
  }

  async function generateMedia() {
    if (!generateSkill) {
      setGenerationState({ phase: 'error', message: '未找到对应的 Qwen 生成 skill' })
      return
    }
    if (!generationPrompt.trim()) {
      setGenerationState({ phase: 'error', message: '请输入生成 prompt' })
      return
    }
    setGenerationState({ phase: 'saving' })
    try {
      const input: Record<string, unknown> = {
        prompt: generationPrompt,
        name:
          generationName ||
          (mediaType === 'image' ? 'Qwen 生成图片' : 'Qwen 生成视频'),
        purpose: generationPurpose,
      }
      if (mediaType === 'image') {
        input.size = imageSize
      } else {
        input.resolution = videoResolution
        input.ratio = videoRatio
        input.duration = Number(videoDuration) || 5
      }
      const response = await skillApi.invoke(generateSkill.id, { mode, input })
      const generated = outputMediaAsset(response.output)
      if (!generated) {
        setGenerationState({
          phase: 'saved',
          message: outputText(response.output),
        })
        return
      }
      onAssetsChange([
        generated,
        ...assets.filter((asset) => asset.id !== generated.id),
      ])
      setSelectedAssetId(generated.id)
      setGenerationPrompt('')
      setGenerationName('')
      setGenerationPurpose('')
      setGenerationState({ phase: 'saved' })
    } catch (error) {
      setGenerationState({
        phase: 'error',
        message: error instanceof Error ? error.message : '生成失败',
      })
    }
  }

  return (
    <div className="workspace-page asset-page">
      <section className="history-list">
        <div className="panel-title">
          {definition.icon} {definition.label}
        </div>
        <p className="microcopy">
          当前模式：{mode === 'demo' ? '演示模式' : '实时生成'}。
          {mode === 'demo'
            ? '理解和生成会返回 demo 结果，不会调用 Qwen。'
            : '理解和生成会调用已配置的 Qwen API。'}
        </p>
        {onModeChange && (
          <div className="mode-switch">
            <button
              className={mode === 'demo' ? 'active' : ''}
              type="button"
              onClick={() => onModeChange('demo')}
            >
              演示模式
            </button>
            <button
              className={mode === 'live' ? 'active' : ''}
              type="button"
              onClick={() => onModeChange('live')}
            >
              实时生成
            </button>
          </div>
        )}
        <button
          className={`run-row ${activeActionPanel === 'upload' ? 'active' : ''}`}
          type="button"
          onClick={() => {
            setActiveActionPanel(activeActionPanel === 'upload' ? null : 'upload')
            setSelectedAssetId('')
          }}
        >
          <span>{definition.upload}</span>
          <b>new</b>
          <small>上传本地图文/视频文件，保存为媒体资产。</small>
        </button>
        <button
          className={`run-row ${activeActionPanel === 'generate' ? 'active' : ''}`}
          type="button"
          onClick={() => {
            setActiveActionPanel(
              activeActionPanel === 'generate' ? null : 'generate',
            )
            setSelectedAssetId('')
          }}
        >
          <span>{mediaType === 'image' ? '生成图文素材' : '生成视频素材'}</span>
          <b>qwen</b>
          <small>通过 Qwen 生成素材，结果会保存为新的媒体资产。</small>
        </button>
        {filteredAssets.length === 0 ? (
          <div className="empty-card">{definition.empty}</div>
        ) : (
          filteredAssets.map((asset) => (
            <button
              className={`run-row ${selectedAsset?.id === asset.id ? 'active' : ''}`}
              key={asset.id}
              type="button"
              onClick={() => {
                setSelectedAssetId(asset.id)
                setActiveActionPanel(null)
              }}
            >
              <span>{asset.name}</span>
              <b>{asset.sourceType}</b>
              <small>{mediaAssetPreview(asset)}</small>
              <small>更新于 {new Date(asset.updatedAt).toLocaleString()}</small>
            </button>
          ))
        )}
        <div className="asset-type-contract">
          <label>媒体资产 contract</label>
          <span>type: {mediaType}</span>
          <span>storage: disk file + SQLite metadata</span>
          <span>derived: 手动填写，后续可接 OCR / ASR / 视觉理解</span>
        </div>
      </section>

      <section className="history-detail source-editor-stack">
        {activeActionPanel === 'upload' ? (
          <div className="source-editor-card">
            <div className="detail-head">
              <div>
                <h2>{definition.upload}</h2>
                <p>保存文件、metadata、派生文本和备注；Qwen 理解结果需确认后写回。</p>
              </div>
            </div>
            <label htmlFor={`${mediaType}-upload-name`}>{definition.singular}名称</label>
            <input
              id={`${mediaType}-upload-name`}
              value={uploadName}
              onChange={(event) => setUploadName(event.target.value)}
              placeholder={`例：${mediaType === 'image' ? '主页截图' : 'AI短剧样本'}`}
            />
            <label htmlFor={`${mediaType}-upload-purpose`}>用途</label>
            <input
              id={`${mediaType}-upload-purpose`}
              value={uploadPurpose}
              onChange={(event) => setUploadPurpose(event.target.value)}
              placeholder="例：视频质量诊断样本、封面参考、评论区截图"
            />
            <label htmlFor={`${mediaType}-upload-file`}>文件</label>
            <input
              id={`${mediaType}-upload-file`}
              type="file"
              accept={definition.accept}
              onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
            />
            <div className="save-row">
              <button className="save-button" type="button" onClick={uploadAsset}>
                {definition.upload}
              </button>
              <SaveIndicator state={uploadState} />
            </div>
          </div>
        ) : activeActionPanel === 'generate' ? (
          <div className="source-editor-card">
            <div className="detail-head">
              <div>
                <h2>{mediaType === 'image' ? '生成图文素材' : '生成视频素材'}</h2>
                <p>
                  当前模式：{mode}。live 会调用 Qwen / DashScope，并把生成结果保存为媒体资产。
                </p>
              </div>
            </div>
            <label htmlFor={`${mediaType}-generation-prompt`}>生成 prompt</label>
            <textarea
              id={`${mediaType}-generation-prompt`}
              rows={4}
              value={generationPrompt}
              onChange={(event) => {
                setGenerationPrompt(event.target.value)
                setGenerationState({ phase: 'idle' })
              }}
              placeholder={
                mediaType === 'image'
                  ? '例：生成一张留学账号主页视觉参考图，清爽、可信、适合小红书。'
                  : '例：生成一个 AIGC 短剧开场镜头，竖屏，强冲突，电影感。'
              }
            />
            <label htmlFor={`${mediaType}-generation-name`}>生成资产名称</label>
            <input
              id={`${mediaType}-generation-name`}
              value={generationName}
              onChange={(event) => setGenerationName(event.target.value)}
              placeholder={mediaType === 'image' ? 'Qwen 生成图片' : 'Qwen 生成视频'}
            />
            <label htmlFor={`${mediaType}-generation-purpose`}>用途</label>
            <input
              id={`${mediaType}-generation-purpose`}
              value={generationPurpose}
              onChange={(event) => setGenerationPurpose(event.target.value)}
              placeholder="例：封面参考、视频脚本视觉测试、账号主页视觉探索"
            />
            {mediaType === 'image' ? (
              <>
                <label htmlFor="image-generation-size">图片尺寸</label>
                <input
                  id="image-generation-size"
                  value={imageSize}
                  onChange={(event) => setImageSize(event.target.value)}
                />
              </>
            ) : (
              <div className="compact-grid">
                <label htmlFor="video-generation-resolution">
                  分辨率
                  <input
                    id="video-generation-resolution"
                    value={videoResolution}
                    onChange={(event) => setVideoResolution(event.target.value)}
                  />
                </label>
                <label htmlFor="video-generation-ratio">
                  画幅比例
                  <input
                    id="video-generation-ratio"
                    value={videoRatio}
                    onChange={(event) => setVideoRatio(event.target.value)}
                  />
                </label>
                <label htmlFor="video-generation-duration">
                  时长秒数
                  <input
                    id="video-generation-duration"
                    value={videoDuration}
                    onChange={(event) => setVideoDuration(event.target.value)}
                  />
                </label>
              </div>
            )}
            <div className="save-row">
              <button className="save-button" type="button" onClick={generateMedia}>
                {mediaType === 'image' ? '生成图文素材' : '生成视频'}
              </button>
              <SaveIndicator state={generationState} />
            </div>
          </div>
        ) : selectedAsset ? (
          <div className="source-editor-card">
            <div className="detail-head">
              <div>
                <h2>{selectedAsset.name}</h2>
                <p>
                  {selectedAsset.originalFilename} · {selectedAsset.mediaType} ·{' '}
                  {selectedAsset.byteSize} bytes
                </p>
              </div>
            </div>
            {selectedAsset.type === 'image' ? (
              <img
                alt={selectedAsset.name}
                className="media-preview"
                src={selectedAsset.fileUrl}
              />
            ) : (
              <video className="media-preview" controls src={selectedAsset.fileUrl}>
                <track kind="captions" />
              </video>
            )}
            {selectedAsset.type === 'video' && (
              <div className="source-editor-card nested-card">
                <div className="detail-head">
                  <div>
                    <h3>视频帧预览</h3>
                    <p>
                      从本地视频抽取少量预览帧，供 Qwen
                      理解和视频质量诊断复用；不会把完整视频文件直接发送给模型。
                    </p>
                  </div>
                </div>
                <div className="save-row">
                  <button
                    className="save-button secondary"
                    type="button"
                    onClick={deriveVideoPreview}
                  >
                    抽取视频帧预览
                  </button>
                  <SaveIndicator state={videoPreviewState} />
                </div>
                {previewFrames.length > 0 && (
                  <div className="video-frame-grid">
                    {previewFrames.map((frame) => (
                      <figure key={frame.mediaAssetId}>
                        <img
                          alt={`抽帧 ${frame.frameIndex ?? ''}`.trim()}
                          src={frame.fileUrl}
                        />
                        <figcaption>
                          Frame {frame.frameIndex ?? frame.mediaAssetId}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="source-editor-card nested-card">
              <div className="detail-head">
                <div>
                  <h3>{mediaType === 'image' ? '理解这张图片' : '理解这个视频'}</h3>
                  <p>
                    结果先作为草稿展示；确认后才写入 derived，避免静默覆盖素材。
                  </p>
                </div>
              </div>
              <label htmlFor={`${mediaType}-understand-prompt`}>理解 prompt</label>
              <textarea
                id={`${mediaType}-understand-prompt`}
                rows={3}
                value={understandPrompt}
                onChange={(event) => setUnderstandPrompt(event.target.value)}
              />
              {mediaType === 'video' && (
                <>
                  <label htmlFor="video-reference-urls">
                    视频 URL / frame URLs（一行一个）
                  </label>
                  <textarea
                    id="video-reference-urls"
                    rows={4}
                    value={videoReferenceUrls}
                    onChange={(event) => setVideoReferenceUrls(event.target.value)}
                    placeholder="公开视频 URL，或多张视频帧图片 URL。留空时会优先使用 externalUrl；本地上传视频会由后端抽帧后理解。"
                  />
                </>
              )}
              <div className="save-row">
                <button
                  className="save-button"
                  type="button"
                  onClick={runUnderstanding}
                >
                  {mediaType === 'image' ? '理解图片' : '理解视频'}
                </button>
                <SaveIndicator state={understandingState} />
              </div>
              {understandingResult && (
                <div className="stage-json">
                  <pre>{understandingResult}</pre>
                </div>
              )}
              {understandingResult && (
                <div className="save-row">
                  <button
                    className="save-button secondary"
                    type="button"
                    onClick={saveUnderstandingToAsset}
                  >
                    保存理解结果到素材
                  </button>
                  <SaveIndicator state={understandingSaveState} />
                </div>
              )}
            </div>
            <label htmlFor={`${mediaType}-asset-name`}>{definition.singular}名称</label>
            <input
              id={`${mediaType}-asset-name`}
              value={draftName}
              onChange={(event) => {
                setDraftName(event.target.value)
                setSaveState({ phase: 'idle' })
              }}
            />
            <label htmlFor={`${mediaType}-asset-purpose`}>用途</label>
            <input
              id={`${mediaType}-asset-purpose`}
              value={draftPurpose}
              onChange={(event) => {
                setDraftPurpose(event.target.value)
                setSaveState({ phase: 'idle' })
              }}
            />
            <label htmlFor={`${mediaType}-asset-metadata`}>metadata JSON</label>
            <textarea
              id={`${mediaType}-asset-metadata`}
              rows={mediaType === 'image' ? 4 : 6}
              value={metadataDraft}
              onChange={(event) => {
                setMetadataDraft(event.target.value)
                setSaveState({ phase: 'idle' })
              }}
            />
            <label htmlFor={`${mediaType}-asset-derived`}>derived JSON</label>
            <textarea
              id={`${mediaType}-asset-derived`}
              rows={mediaType === 'image' ? 8 : 12}
              value={derivedDraft}
              onChange={(event) => {
                setDerivedDraft(event.target.value)
                setSaveState({ phase: 'idle' })
              }}
            />
            <label htmlFor={`${mediaType}-asset-notes`}>用户备注</label>
            <textarea
              id={`${mediaType}-asset-notes`}
              rows={5}
              value={userNotesDraft}
              onChange={(event) => {
                setUserNotesDraft(event.target.value)
                setSaveState({ phase: 'idle' })
              }}
            />
            <div className="save-row">
              <button className="save-button" type="button" onClick={saveAsset}>
                保存{definition.singular}
              </button>
              <SaveIndicator state={saveState} />
            </div>
          </div>
        ) : (
          <div className="empty-card">上传或选择一个{definition.singular}实例。</div>
        )}
      </section>
    </div>
  )
}

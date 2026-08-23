import type { Dispatch, SetStateAction } from 'react'

import { inputAssetPreview } from '../inputAssets'
import type {
  Draft,
  MediaAsset,
  TextInputAsset,
  TrendCsvInputAsset,
} from '../types'
import type { GenerationMode, WorkflowTab } from '../workflows'
import { xhsCreatorProfileSummaryFromAsset } from '../xhsCreatorProfile'

type WorkflowCallPanelProps = {
  targetTab: WorkflowTab
  mode: GenerationMode
  running: boolean
  simulationTopic: string
  selectedXhsCreatorProfileInputAssetId: string
  xhsCreatorProfileMaterial?: TextInputAsset
  xhsCreatorProfileMaterials: TextInputAsset[]
  selectedProfileMaterial: TextInputAsset | null
  accountProfileMaterials: TextInputAsset[]
  historicalMaterial?: TextInputAsset
  historicalMaterials: TextInputAsset[]
  commentsMaterial?: TextInputAsset
  commentsMaterials: TextInputAsset[]
  trendMaterial?: TrendCsvInputAsset
  trendMaterials: TrendCsvInputAsset[]
  videoCreatorSamplesMaterial?: TextInputAsset
  videoCreatorSamplesMaterials: TextInputAsset[]
  mediaAssets: MediaAsset[]
  selectedVideoWorkflowMediaAssetIds: string[]
  videoWorkflowMediaAssets: MediaAsset[]
  onSelectXhsCreatorProfileInputAssetId: (assetId: string) => void
  onSelectProfileInputAssetId: (assetId: string) => void
  onChooseTextMaterial: (material: TextInputAsset) => void
  onChooseTrendMaterial: (material: TrendCsvInputAsset) => void
  onSetSelectedVideoWorkflowMediaAssetIds: Dispatch<SetStateAction<string[]>>
  onSimulationTopicChange: (topic: string) => void
  onSetMode: (mode: GenerationMode) => void
  onApplyDemoSample: (force?: boolean, targetTab?: WorkflowTab) => void
  onRunDiagnosis: (targetTab?: WorkflowTab) => void | Promise<void>
  onRunAudienceSimulation: (
    draft?: Draft,
    targetTab?: WorkflowTab,
  ) => void | Promise<void>
  onRunBatchWorkflow: (targetTab?: WorkflowTab) => void | Promise<void>
  onDownloadAnalysisRunsCsv: (targetTab?: WorkflowTab) => void
}

export function WorkflowCallPanel(props: WorkflowCallPanelProps) {
  const {
    targetTab,
    mode,
    running,
    simulationTopic,
    selectedXhsCreatorProfileInputAssetId,
    xhsCreatorProfileMaterial,
    xhsCreatorProfileMaterials,
    selectedProfileMaterial,
    accountProfileMaterials,
    historicalMaterial,
    historicalMaterials,
    commentsMaterial,
    commentsMaterials,
    trendMaterial,
    trendMaterials,
    videoCreatorSamplesMaterial,
    videoCreatorSamplesMaterials,
    mediaAssets,
    selectedVideoWorkflowMediaAssetIds,
    videoWorkflowMediaAssets,
  } = props
  const isAccount = targetTab === 'account'
  const isVideo = targetTab === 'video'
  const panelTitle = isAccount
    ? '📊 账号诊断'
    : isVideo
      ? '🎬 视频博主质量诊断'
      : '🔥 热点分析'
  const description = isAccount
    ? '优先使用小红书创作者主页资产；未选择时回退到账号概况、历史笔记和评论样本。'
    : isVideo
      ? '使用账号概况和视频创作样本判断 AIGC 视频创作者质量与激励计划适配度。'
      : '使用账号概况和趋势 CSV 生成热点分析。'
  const runLabel = isAccount
    ? '⚡ 生成账号诊断'
    : isVideo
      ? '⚡ 生成视频创作者诊断'
      : '⚡ 生成热点分析'
  const usesXhsBatch = (isAccount || isVideo) && Boolean(xhsCreatorProfileMaterial)

  const renderInputPreview = (
    name: string,
    status: 'ready' | 'missing',
    detail: string,
  ) => (
    <div className="asset-requirement workflow-input-preview">
      <div>
        <b>{name}</b>
        <span>{detail}</span>
      </div>
      <em className={status}>{status}</em>
    </div>
  )

  const renderXhsWorkflowInputPreview = (
    asset: TextInputAsset | undefined,
    purpose: 'account' | 'video' = 'account',
  ) => {
    if (!asset) {
      return renderInputPreview(
        '小红书创作者主页',
        'missing',
        '未选择结构化小红书主页资产',
      )
    }
    const summary = xhsCreatorProfileSummaryFromAsset(asset)
    if (!summary) {
      return (
        <>
          {renderInputPreview('小红书创作者主页', 'ready', inputAssetPreview(asset))}
          <p className="workflow-derived-note">
            后端会尝试从该主页资产派生账号概况、历史笔记和评论样本快照。
          </p>
        </>
      )
    }
    return (
      <div className="xhs-summary-card workflow-xhs-preview">
        <div className="xhs-summary-head">
          <b>小红书创作者主页</b>
          <span>{asset.name}</span>
        </div>
        <div className="xhs-summary-grid">
          <span>账号：{summary.displayName}</span>
          <span>笔记：{summary.noteCount}</span>
          <span>视频：{summary.videoNoteCount}</span>
          <span>评论：{summary.commentCount}</span>
          <span>封面引用：{summary.coverReferenceCount}</span>
        </div>
        {purpose === 'account' ? (
          <div className="workflow-derived-assets">
            <label>本次账号诊断会由后端派生</label>
            <div>
              <span>账号概况快照</span>
              <span>历史笔记摘要</span>
              <span>评论痛点样本</span>
            </div>
          </div>
        ) : (
          <div className="workflow-derived-assets">
            <label>本次视频诊断会由后端派生</label>
            <div>
              <span>视频作者证据包</span>
              <span>{summary.videoNoteCount > 0 ? '包含视频笔记' : '未发现视频笔记'}</span>
              <span>{summary.coverReferenceCount > 0 ? '包含封面引用' : '无封面引用'}</span>
              <span>{summary.commentCount > 0 ? '包含评论反馈' : '无评论反馈'}</span>
            </div>
          </div>
        )}
        {summary.topNotes.length > 0 && (
          <div className="xhs-top-notes workflow-xhs-top-notes">
            <label>高互动样本</label>
            <ol>
              {summary.topNotes.slice(0, 3).map((note) => (
                <li key={note.noteId || note.title}>
                  <b>{note.title}</b>
                  <span>
                    赞 {note.liked ?? '-'} · 藏 {note.collected ?? '-'} · 评{' '}
                    {note.comments ?? '-'} · 分享 {note.shares ?? '-'}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {summary.warnings.length > 0 && (
          <p className="workflow-derived-note">
            该主页资产有 {summary.warnings.length} 条导入提示，可在内容资产详情页查看。
          </p>
        )}
        {purpose === 'video' && summary.videoNoteCount === 0 && (
          <p className="workflow-derived-note">
            当前主页没有 video 类型笔记；视频质量判断会按图文/封面/评论的间接证据保守输出。
          </p>
        )}
      </div>
    )
  }

  const mediaWorkflowPreview = (asset: MediaAsset) => {
    const hasUnderstanding = Boolean(
      asset.derived.qwenUnderstanding ||
        asset.derived.imageUnderstanding ||
        asset.derived.videoUnderstanding ||
        asset.derived.visualSummary ||
        asset.derived.sceneSummary,
    )
    return `${asset.type === 'image' ? '图片' : '视频'} · ${asset.name} · ${
      hasUnderstanding ? '已有理解结果' : '未保存理解结果'
    }`
  }

  return (
    <section className="input-panel workflow-call-panel">
      <div className="panel-title">{panelTitle}</div>
      <p className="subline">{description}</p>
      {isAccount && (
        <div className="source-editor-card compact">
          <label htmlFor="workflow-xhs-creator-profile-material">
            小红书创作者主页实例
          </label>
          <select
            id="workflow-xhs-creator-profile-material"
            value={selectedXhsCreatorProfileInputAssetId}
            onChange={(event) =>
              props.onSelectXhsCreatorProfileInputAssetId(event.target.value)
            }
          >
            <option value="">不使用，改用下方兼容输入</option>
            {xhsCreatorProfileMaterials.map((material) => (
              <option value={material.id} key={material.id}>
                {material.name}
              </option>
            ))}
          </select>
          {renderXhsWorkflowInputPreview(xhsCreatorProfileMaterial)}
        </div>
      )}
      {isVideo && (
        <div className="source-editor-card compact">
          <label htmlFor="workflow-video-xhs-creator-profile-material">
            小红书创作者主页实例
          </label>
          <select
            id="workflow-video-xhs-creator-profile-material"
            value={selectedXhsCreatorProfileInputAssetId}
            onChange={(event) =>
              props.onSelectXhsCreatorProfileInputAssetId(event.target.value)
            }
          >
            <option value="">不使用，改用视频创作样本</option>
            {xhsCreatorProfileMaterials.map((material) => (
              <option value={material.id} key={material.id}>
                {material.name}
              </option>
            ))}
          </select>
          {renderXhsWorkflowInputPreview(xhsCreatorProfileMaterial, 'video')}
        </div>
      )}
      {!(isAccount && xhsCreatorProfileMaterial) && (
        <div className="source-editor-card compact">
          <label htmlFor="workflow-account-profile-material">账号概况实例</label>
          <select
            id="workflow-account-profile-material"
            value={selectedProfileMaterial?.id || ''}
            onChange={(event) =>
              props.onSelectProfileInputAssetId(event.target.value)
            }
          >
            {accountProfileMaterials.length === 0 ? (
              <option value="">还没有保存的账号概况</option>
            ) : (
              accountProfileMaterials.map((material) => (
                <option value={material.id} key={material.id}>
                  {material.name}
                </option>
              ))
            )}
          </select>
          {renderInputPreview(
            '账号概况',
            selectedProfileMaterial ? 'ready' : 'missing',
            selectedProfileMaterial
              ? inputAssetPreview(selectedProfileMaterial)
              : '未选择账号概况实例',
          )}
        </div>
      )}
      {isAccount && !xhsCreatorProfileMaterial && (
        <>
          <div className="source-editor-card compact">
            <label htmlFor="workflow-historical-material">历史笔记实例</label>
            <select
              id="workflow-historical-material"
              value={historicalMaterial?.id || ''}
              onChange={(event) => {
                const material = historicalMaterials.find(
                  (item) => item.id === event.target.value,
                )
                if (material) props.onChooseTextMaterial(material)
              }}
            >
              {historicalMaterials.length === 0 ? (
                <option value="">还没有保存的历史笔记</option>
              ) : (
                historicalMaterials.map((material) => (
                  <option value={material.id} key={material.id}>
                    {material.name}
                  </option>
                ))
              )}
            </select>
            {renderInputPreview(
              '历史笔记',
              historicalMaterial ? 'ready' : 'missing',
              historicalMaterial
                ? inputAssetPreview(historicalMaterial)
                : '未选择历史笔记实例',
            )}
          </div>
          <div className="source-editor-card compact">
            <label htmlFor="workflow-comments-material">评论样本实例</label>
            <select
              id="workflow-comments-material"
              value={commentsMaterial?.id || ''}
              onChange={(event) => {
                const material = commentsMaterials.find(
                  (item) => item.id === event.target.value,
                )
                if (material) props.onChooseTextMaterial(material)
              }}
            >
              {commentsMaterials.length === 0 ? (
                <option value="">还没有保存的评论样本</option>
              ) : (
                commentsMaterials.map((material) => (
                  <option value={material.id} key={material.id}>
                    {material.name}
                  </option>
                ))
              )}
            </select>
            {renderInputPreview(
              '评论样本',
              commentsMaterial ? 'ready' : 'missing',
              commentsMaterial
                ? inputAssetPreview(commentsMaterial)
                : '未选择评论样本实例',
            )}
          </div>
        </>
      )}
      {targetTab === 'trend' && (
        <div className="source-editor-card compact">
          <label htmlFor="workflow-trend-material">趋势 CSV 数据实例</label>
          <select
            id="workflow-trend-material"
            value={trendMaterial?.id || ''}
            onChange={(event) => {
              const material = trendMaterials.find(
                (item) => item.id === event.target.value,
              )
              if (material) props.onChooseTrendMaterial(material)
            }}
          >
            {trendMaterials.length === 0 ? (
              <option value="">还没有上传的趋势 CSV</option>
            ) : (
              trendMaterials.map((material) => (
                <option value={material.id} key={material.id}>
                  {material.name} · {material.originalFilename}
                </option>
              ))
            )}
          </select>
          {renderInputPreview(
            '趋势 CSV',
            trendMaterial ? 'ready' : 'missing',
            trendMaterial ? inputAssetPreview(trendMaterial) : '未选择趋势 CSV 实例',
          )}
        </div>
      )}
      {isVideo && (
        <>
          {!xhsCreatorProfileMaterial && (
          <div className="source-editor-card compact">
            <label htmlFor="workflow-video-material">视频创作样本实例</label>
            <select
              id="workflow-video-material"
              value={videoCreatorSamplesMaterial?.id || ''}
              onChange={(event) => {
                const material = videoCreatorSamplesMaterials.find(
                  (item) => item.id === event.target.value,
                )
                if (material) props.onChooseTextMaterial(material)
              }}
            >
              {videoCreatorSamplesMaterials.length === 0 ? (
                <option value="">还没有保存的视频创作样本</option>
              ) : (
                videoCreatorSamplesMaterials.map((material) => (
                  <option value={material.id} key={material.id}>
                    {material.name}
                  </option>
                ))
              )}
            </select>
            {renderInputPreview(
              '视频创作样本',
              videoCreatorSamplesMaterial ? 'ready' : 'missing',
              videoCreatorSamplesMaterial
                ? inputAssetPreview(videoCreatorSamplesMaterial)
                : '未选择视频创作样本实例',
            )}
          </div>
          )}
          <div className="source-editor-card compact">
            <label>关联图片/视频素材</label>
            {mediaAssets.length === 0 ? (
              <div className="empty-card">还没有图片或视频素材。</div>
            ) : (
              <div className="asset-mini-list">
                {mediaAssets.map((asset) => (
                  <label className="media-select-row" key={asset.id}>
                    <input
                      type="checkbox"
                      checked={selectedVideoWorkflowMediaAssetIds.includes(asset.id)}
                      onChange={(event) => {
                        props.onSetSelectedVideoWorkflowMediaAssetIds((current) =>
                          event.target.checked
                            ? [...current, asset.id]
                            : current.filter((id) => id !== asset.id),
                        )
                      }}
                    />
                    <span>{mediaWorkflowPreview(asset)}</span>
                  </label>
                ))}
              </div>
            )}
            {renderInputPreview(
              '媒体素材',
              videoWorkflowMediaAssets.length ? 'ready' : 'missing',
              videoWorkflowMediaAssets.length
                ? videoWorkflowMediaAssets.map(mediaWorkflowPreview).join('\n')
                : '可选。建议先在图片/视频素材页保存 Qwen 理解结果。',
            )}
          </div>
        </>
      )}
      <div className="simulation-divider">
        <label htmlFor="simulation-topic">👥 下期选题（受众模拟的测试内容）</label>
        <textarea
          id="simulation-topic"
          rows={2}
          value={simulationTopic}
          onChange={(event) => props.onSimulationTopicChange(event.target.value)}
          placeholder="可从选题卡或选题库一键填入"
        />
      </div>

      <div className="mode-switch">
        <button
          className={mode === 'demo' ? 'active' : ''}
          onClick={() => {
            props.onSetMode('demo')
            props.onApplyDemoSample(false, targetTab)
          }}
        >
          演示模式
        </button>
        <button
          className={mode === 'live' ? 'active' : ''}
          onClick={() => props.onSetMode('live')}
        >
          实时生成
        </button>
      </div>
      <div className="action-row">
        <button
          className="primary"
          disabled={running}
          onClick={() => props.onRunDiagnosis(targetTab)}
        >
          {running ? '生成中…' : runLabel}
        </button>
        <button
          className="simulation-button"
          disabled={running || (mode === 'live' && !simulationTopic.trim())}
          onClick={() => props.onRunAudienceSimulation(undefined, targetTab)}
        >
          👥 受众模拟
        </button>
      </div>
      <div className="workflow-shortcuts">
        <button
          type="button"
          disabled={
            running ||
            (usesXhsBatch
              ? xhsCreatorProfileMaterials.length === 0
              : accountProfileMaterials.length === 0)
          }
          onClick={() => props.onRunBatchWorkflow(targetTab)}
        >
          {usesXhsBatch
            ? `批量运行当前 Workflow（${xhsCreatorProfileMaterials.length} 个小红书主页）`
            : `批量运行当前 Workflow（${accountProfileMaterials.length} 个账号概况）`}
        </button>
        <button type="button" onClick={() => props.onDownloadAnalysisRunsCsv(targetTab)}>
          下载结果 CSV
        </button>
      </div>
    </section>
  )
}

import type { AnalysisRun, MediaAsset } from '../types'

type ImageReading = {assetId: string; noteId: string; noteTitle?: string; page: number; status: string; text?: string; error?: string}

export function AccountDiagnosisRecovery({run, stage, busy, mediaAssets, onRetry, onOpenSource}: {
  run: AnalysisRun; stage: string; busy: boolean; mediaAssets: MediaAsset[];
  onRetry: (stage: string) => void; onOpenSource: (id: string) => void;
}) {
  const terminal = ['failed', 'partially_completed', 'completed'].includes(run.status)
  const metadata = run.modelMetadata as Record<string, unknown>
  const profile = metadata.profile as {imageReadings?: ImageReading[]; pipelineCheckpoint?: {readings?: object; overview?: object}} | undefined
  const images = profile?.imageReadings || []
  const imageFailed = images.some(row => row.status === 'failed')
  const stale = stage === 'topics' && metadata.topicsStale === true
  const retry = terminal && (Boolean(run.stageErrors[stage]) || stale || (stage === 'profile' && imageFailed))
  const recovery = metadata.recovery as {sourceRunId?: string} | undefined
  return <>
    {stage === 'profile' && recovery?.sourceRunId && <button type="button" disabled={busy} className="text-button" onClick={() => onOpenSource(recovery.sourceRunId!)}>查看原诊断</button>}
    {stage === 'profile' && images.length > 0 && <details className="account-image-readings">
      <summary>图片文字 · 已读取 {images.filter(row => row.status === 'completed').length}/{images.length} 张</summary>
      {images.map(row => <article key={row.assetId}>
        <p>{row.noteTitle || '笔记图片'} · 图片 {row.page} · {row.status === 'completed' ? '已读取' : row.error || '未读取'}</p>
        {mediaAssets.find(asset => asset.id === row.assetId)?.fileUrl && <a href={mediaAssets.find(asset => asset.id === row.assetId)!.fileUrl} target="_blank" rel="noreferrer">查看原图</a>}
        <p style={{whiteSpace: 'pre-wrap'}}>{row.text || (row.status === 'completed' ? '未识别到文字' : '')}</p>
      </article>)}
    </details>}
    {stage === 'profile' && terminal && imageFailed && <p role="status">部分图片未读到，报告已使用正文和成功读取的图片。</p>}
    {stale && <p role="status">这里的选题来自恢复前的诊断，可单独更新。</p>}
    {retry && <button type="button" disabled={busy} onClick={() => onRetry(stage)}>{stale ? '更新选题' : stage === 'profile' && !run.stageErrors.profile ? '重试图片并更新报告' : stage === 'profile' && profile?.pipelineCheckpoint?.overview ? '继续完成报告' : '仅重试此部分'}</button>}
  </>
}

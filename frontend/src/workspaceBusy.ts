import type { XhsCaptureJobStatus } from './types'

const CAPTURE_REASONS: Partial<Record<XhsCaptureJobStatus, string>> = {
  pending: '导入任务正在排队',
  waiting_for_login: '导入任务正在等待小红书登录',
  running: '正在爬取笔记和评论',
  processing: '正在整理导入的笔记和图片',
}

export function getWorkspaceBusyReason({ running, captureSubmitting, draftSaving, captureStatus }: {
  running: boolean
  captureSubmitting: boolean
  draftSaving: boolean
  captureStatus?: XhsCaptureJobStatus
}): string | undefined {
  const reasons = [
    running && '分析任务正在运行',
    captureSubmitting && '正在提交导入任务',
    draftSaving && '正在保存稿件',
    captureStatus && CAPTURE_REASONS[captureStatus],
  ].filter(Boolean)
  return reasons.length ? `${reasons.join('；')}。完成后可添加或切换账号。` : undefined
}

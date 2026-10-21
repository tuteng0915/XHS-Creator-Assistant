import { describe, expect, it } from 'vitest'
import { getWorkspaceBusyReason } from './workspaceBusy'

const idle = { running: false, captureSubmitting: false, draftSaving: false }

describe('getWorkspaceBusyReason', () => {
  it.each([
    ['pending', '正在排队'],
    ['waiting_for_login', '等待小红书登录'],
    ['running', '正在爬取笔记和评论'],
    ['processing', '正在整理导入'],
  ] as const)('explains active capture status %s', (captureStatus, expected) => {
    expect(getWorkspaceBusyReason({ ...idle, captureStatus })).toContain(expected)
  })

  it.each([undefined, 'completed', 'failed'] as const)('does not lock for terminal/absent status %s', captureStatus => {
    expect(getWorkspaceBusyReason({ ...idle, captureStatus })).toBeUndefined()
  })

  it('explains each simultaneous operation without losing the capture reason', () => {
    const reason = getWorkspaceBusyReason({ running: true, captureSubmitting: true, draftSaving: true, captureStatus: 'running' })
    for (const text of ['分析任务正在运行', '正在提交导入任务', '正在保存稿件', '正在爬取笔记和评论']) {
      expect(reason).toContain(text)
    }
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CreatorMaterialsPage } from './CreatorMaterialsPage'
import { CreatorDiagnosisPage } from './CreatorDiagnosisPage'
import type { TextInputAsset } from '../types'
import { creatorNotes, selectCreatorNotes } from '../creatorNotes'

const profile: TextInputAsset = {
  id: 'profile', workspaceId: 'account-1', name: '测试账号', type: 'xhs_creator_profile',
  createdAt: '', updatedAt: '', content: JSON.stringify({ notes: [
    { noteId: 'n1', title: '我的笔记', desc: '完整正文', comments: [{ content: '对应的评论' }] },
  ] }),
}

describe('creator materials and diagnosis', () => {
  it('keeps body and comments behind the note detail dialog', () => {
    render(<CreatorMaterialsPage profile={profile} mediaAssets={[]} onImport={vi.fn()} onAnalyze={vi.fn()} />)
    expect(screen.queryByText('完整正文')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /我的笔记/ }))
    expect(screen.getByRole('dialog', { name: '我的笔记' })).toBeInTheDocument()
    expect(screen.getByText('完整正文')).toBeInTheDocument()
    expect(screen.getByText('对应的评论')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(screen.queryByText('完整正文')).not.toBeInTheDocument()
  })

  it('keeps unknown dates out of date-limited runs and blocks empty analysis', () => {
    const onScopeChange = vi.fn()
    render(<CreatorDiagnosisPage profile={profile} scope="last_7_days" running={false} onRun={vi.fn()} onImport={vi.fn()} onScopeChange={onScopeChange}>{null}</CreatorDiagnosisPage>)
    expect(screen.getByRole('button', { name: '开始分析' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '调整范围' }))
    expect(screen.getByText('1 条笔记没有发布时间，未纳入此范围。')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('从已导入笔记中选择'), { target: { value: 'all' } })
    expect(onScopeChange).toHaveBeenCalledWith('all')
  })

  it('keeps old undated imports usable with the recent-count default', () => {
    expect(selectCreatorNotes(creatorNotes(profile), 'recent_10')).toHaveLength(1)
    expect(selectCreatorNotes(creatorNotes(profile), 'last_30_days')).toHaveLength(0)
  })
})

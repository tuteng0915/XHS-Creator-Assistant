import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CreatorMaterialsPage } from './CreatorMaterialsPage'
import { CreatorDiagnosisPage } from './CreatorDiagnosisPage'
import type { TextInputAsset } from '../types'
import { creatorNotes, selectCreatorNotes } from '../creatorNotes'

afterEach(cleanup)

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
    expect(screen.getByText(/1 篇未记录发布时间/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('查看范围'), { target: { value: 'all' } })
    fireEvent.click(screen.getByRole('button',{name:'全选当前范围'}))
    expect(onScopeChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '完成' }))
    expect(onScopeChange).toHaveBeenCalledWith('recent_10', ['n1'])
  })

  it('keeps old undated imports usable with the recent-count default', () => {
    expect(selectCreatorNotes(creatorNotes(profile), 'recent_10')).toHaveLength(1)
    expect(selectCreatorNotes(creatorNotes(profile), 'last_30_days')).toHaveLength(0)
  })

  it('shows honest imported time beside the heading and offers shared ranking controls', () => {
    const dated = {...profile,content:JSON.stringify({source:{importedAt:'2026-10-09T12:00:00Z'},notes:[
      {noteId:'new',title:'最近但低赞',publishedAt:'2026-10-09',metrics:{liked:1},comments:[]},
      {noteId:'top',title:'最高赞',publishedAt:'2026-10-01',metrics:{liked:20},comments:[]},
    ]})}
    render(<CreatorMaterialsPage profile={dated} mediaAssets={[]} onImport={vi.fn()} onAnalyze={vi.fn()} />)
    expect(screen.getByRole('heading',{name:'我的笔记'}).parentElement).toHaveTextContent('导入于 2026/10/9')
    expect(screen.queryByText(/数据截至/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('排序'),{target:{value:'liked'}})
    expect(screen.getAllByRole('article')[0]).toHaveTextContent('最高赞')
    expect(screen.getByLabelText('显示')).toBeVisible()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
})

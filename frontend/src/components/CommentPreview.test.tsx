import {cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {commentPreviewApi} from '../api'
import {CommentPreview} from './CommentPreview'

afterEach(()=>{cleanup();vi.restoreAllMocks()})
const target={sourceMaterialId:'m',noteId:'n'}

it('requests a preview for the frozen target and shows each comment with its tags',async()=>{
  const create=vi.spyOn(commentPreviewApi,'create').mockResolvedValue({title:'t',occasion:'招聘内推',occasionReason:'在招实习生',
    tagLibraryVersion:'v1',mode:'live',comments:[
      {tag:'求资源',isNewTag:false,detail:'投递方式',target:'缺失信息',reader:'陌生人',length:'一句话',text:'怎么投呀'},
      {tag:'蹲结果',isNewTag:true,detail:'',target:'',reader:'',length:'',text:'蹲'},
    ]})
  render(<CommentPreview workspaceId="w" target={target}/>)
  fireEvent.click(screen.getByRole('button',{name:'预览评论区'}))
  expect(await screen.findByText('怎么投呀')).toBeInTheDocument()
  expect(create).toHaveBeenCalledWith('w',target)
  expect(screen.getByText('招聘内推')).toBeInTheDocument()
  expect(screen.getByText('求资源 · 投递方式')).toBeInTheDocument()
  expect(screen.getByText('蹲结果（现场新增）')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'重新预览'})).toBeEnabled()
})

it('shows the failure and keeps the button available for a retry',async()=>{
  vi.spyOn(commentPreviewApi,'create').mockRejectedValue(new Error('这次没有生成可用的评论，请重试'))
  render(<CommentPreview workspaceId="w" target={target}/>)
  fireEvent.click(screen.getByRole('button',{name:'预览评论区'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('请重试')
  expect(screen.getByRole('button',{name:'预览评论区'})).toBeEnabled()
})

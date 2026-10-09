import { afterEach, expect, it, vi } from 'vitest'
import { collaborationCandidates, contentCollaborationApi, replaceSelectedText, selectionFromTextarea, type CollaborationMessage, type FrozenWritingFocus } from './contentCollaboration'

afterEach(() => vi.restoreAllMocks())
const body = '开头🙂重复。\n中间。\n重复。结尾'
const selected = selectionFromTextarea(body, body.lastIndexOf('重复。'), body.lastIndexOf('重复。') + 3)!
const focus: FrozenWritingFocus = {baseTopicId: 't', baseTitle: '标题', baseBody: body, baseUpdatedAt: 'v1', selection: selected}

it('converts UTF-16 textarea offsets to Unicode points and replaces only the selected duplicate', () => {
  expect(selected.start).toBe(Array.from(body.slice(0, body.lastIndexOf('重复。'))).length)
  expect(selected.end - selected.start).toBe(3)
  expect(replaceSelectedText(body, focus, '新的一段！')).toBe('开头🙂重复。\n中间。\n新的一段！结尾')
  expect(selectionFromTextarea('🙂你好', 0, 2)).toEqual({start: 0, end: 1, text: '🙂'})
  expect(selectionFromTextarea('🙂你好', 1, 2)).toBeNull()
})

it('refuses changed text, shifted offsets and invalid selections without searching for another matching quote', () => {
  expect(replaceSelectedText('新增。' + body, focus, '修改')).toBeNull()
  expect(replaceSelectedText(body.replace('中间', '中段'), focus, '修改')).toBeNull()
  expect(replaceSelectedText(body, {...focus, selection: {...selected, start: selected.start - 1}}, '修改')).toBeNull()
  expect(selectionFromTextarea(body, 4, 4)).toBeNull()
  expect(selectionFromTextarea('   ', 0, 3)).toBeNull()
})

it('uses only server-owned message focus, never candidate-supplied positioning; fails closed for broken snapshots', () => {
  const message: CollaborationMessage = {id:'m',sessionId:'s',sequenceNo:1,sender:'writing',recipient:'creator',content:'改写',replyToMessageId:null,createdAt:'',
    modelMetadata:{candidateSuggestions:[{kind:'copy_option',title:'建议',body:'新段',confidence:'inference',writingFocus:{...focus,baseTopicId:'other'}}]}}
  expect(collaborationCandidates(message)[0].writingFocus).toBeUndefined()
  expect(collaborationCandidates({...message,modelMetadata:{...message.modelMetadata,writingFocus:focus}})[0].writingFocus).toEqual(focus)
  const broken = collaborationCandidates({...message,modelMetadata:{...message.modelMetadata,writingFocus:{...focus,selection:{...selected,text:'不相符'}}}})[0]
  expect(broken.focusUnavailable).toBe(true)
  expect(broken.writingFocus).toBeUndefined()
})

it('leaves ordinary message payloads unchanged and sends references with explicit focus only when supplied', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ok:true,json:async()=>({})} as Response)
  await contentCollaborationApi.send('w','s','聊聊','writing','key')
  expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({content:'聊聊',recipient:'writing',requestKey:'key',mode:'live'})
  const writingFocus = {expectedUpdatedAt:'v1',selection:selected,readerReference:{simulationId:'run',stage:'interview' as const,messageId:'m',interviewId:'i'}}
  await contentCollaborationApi.send('w','s','改写','writing','key-2',writingFocus)
  expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body)).writingFocus).toEqual(writingFocus)
})

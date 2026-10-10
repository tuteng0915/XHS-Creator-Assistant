import { afterEach, expect, it, vi } from 'vitest'
import { collaborationCandidates, contentCollaborationApi, creatorContextSignature, creatorReferenceKey, emptyCreatorContext, replaceSelectedText, selectionFromTextarea, type CollaborationMessage, type CreatorContextReference, type FrozenWritingFocus } from './contentCollaboration'

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

it('creates explicit single-writer sessions and sends an empty reference set without defaulting to all history', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ok:true,json:async()=>({})} as Response)
  await contentCollaborationApi.create('w', 't', '当前稿件', 'create-key')
  expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toMatchObject({assistantMode:'single_writer', contextTarget:{assetType:'topic',assetId:'t'}})
  await contentCollaborationApi.send('w','s','聊聊','writing','key',undefined,emptyCreatorContext())
  expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({content:'聊聊',recipient:'writing',requestKey:'key',mode:'live',creatorContextSelection:emptyCreatorContext()})
})

it('keeps reference-set identity independent from chip order', () => {
  const references = [{kind:'account_analysis' as const,id:'a'}, {kind:'audience_analysis' as const,id:'b'}]
  expect(creatorContextSignature({...emptyCreatorContext(),references})).toBe(creatorContextSignature({...emptyCreatorContext(),references:[...references].reverse()}))
  expect(creatorContextSignature({...emptyCreatorContext(),references})).not.toBe(creatorContextSignature(emptyCreatorContext()))
})

it('distinguishes two original notes in one material and sends their exact identities', async () => {
  const first: CreatorContextReference = {kind:'imported_note', id:'material', noteId:'note-a'}
  const second: CreatorContextReference = {...first, noteId:'note-b'}
  expect(creatorReferenceKey(first)).not.toBe(creatorReferenceKey(second))
  expect(creatorReferenceKey({...first,id:'a:b',noteId:'c'})).not.toBe(creatorReferenceKey({...first,id:'a',noteId:'b:c'}))
  const selection = {...emptyCreatorContext(), references:[first,second]}
  expect(creatorContextSignature(selection)).toBe(creatorContextSignature({...selection,references:[second,first]}))
  expect(creatorContextSignature(selection)).not.toBe(creatorContextSignature({...selection,references:[first]}))
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ok:true,json:async()=>({})} as Response)
  await contentCollaborationApi.send('w','s','参考这两篇的口吻','writing','notes-key',undefined,selection)
  expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body)).creatorContextSelection).toEqual(selection)
})

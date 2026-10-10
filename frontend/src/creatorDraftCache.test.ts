import {afterEach, expect, it} from 'vitest'
import {emptyCreatorContext} from './contentCollaboration'
import {creatorDraftKey, readCreatorMessage, writeCreatorCache} from './creatorDraftCache'

afterEach(() => window.sessionStorage.clear())

it('restores mixed exact references only within the same account and topic', () => {
  const draft = {version:1 as const,message:'',selection:{...emptyCreatorContext(),references:[
    {kind:'account_analysis' as const,id:'analysis'},
    {kind:'imported_note' as const,id:'material',noteId:'note-a'},
    {kind:'imported_note' as const,id:'material',noteId:'note-b'},
  ]}}
  expect(writeCreatorCache('message','w','t',draft)).toBe(true)
  expect(readCreatorMessage('w','t').value).toEqual(draft)
  expect(readCreatorMessage('other','t').value).toBeNull()
  expect(readCreatorMessage('w','other').value).toBeNull()
})

it.each([
  {kind:'imported_note',id:'material'},
  {kind:'imported_note',id:'material',noteId:''},
  {kind:'imported_note',id:' ',noteId:'note'},
  {kind:'account_analysis',id:'a',noteId:'unexpected'},
  {kind:'unknown',id:'a'},
])('rejects invalid cached reference $kind', reference => {
  window.sessionStorage.setItem(creatorDraftKey('message','w','t'),JSON.stringify({version:1,message:'保持输入',selection:{...emptyCreatorContext(),references:[reference]}}))
  expect(readCreatorMessage('w','t').value).toBeNull()
})

it('keeps legacy analysis drafts readable if an API explicitly serialized the absent note ID as null', () => {
  const draft = {version:1,message:'先前输入',selection:{...emptyCreatorContext(),references:[{kind:'account_analysis',id:'analysis',noteId:null}]}}
  window.sessionStorage.setItem(creatorDraftKey('message','w','t'),JSON.stringify(draft))
  expect(readCreatorMessage('w','t').value?.message).toBe('先前输入')
})

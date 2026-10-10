import {useEffect, useState} from 'react'
import {analysisRunApi, audienceAnalysisApi} from '../api'
import {creatorReferenceKey, type CreatorContextReference, type CreatorContextSelection} from '../contentCollaboration'
import {importedReferenceNotes, importedReferencePreview, loadCreatorReference, referenceDate, referenceKindNames, type CreatorReferencePreview} from '../creatorReferences'
import type {MediaAsset, TextInputAsset} from '../types'
import {CreatorDialog} from './CreatorDialog'
import {CreatorNoteSelectionDialog} from './CreatorNoteSelectionDialog'
import {InfoHint} from './InfoHint'
import './CreatorReferencePicker.css'

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)
type Choice = {reference: CreatorContextReference; label: string}

export function CreatorReferencePicker({workspaceId, selection, onChange, disabled, profile, mediaAssets = []}: {
  workspaceId: string; selection: CreatorContextSelection; onChange: (value: CreatorContextSelection) => void; disabled: boolean
  profile?: TextInputAsset; mediaAssets?: MediaAsset[]
}) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<CreatorContextReference['kind']>('account_analysis')
  const [choices, setChoices] = useState<Choice[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [preview, setPreview] = useState<CreatorReferencePreview | null>(null)
  const [cache, setCache] = useState<Record<string, CreatorReferencePreview>>({})
  const [viewing, setViewing] = useState<CreatorContextReference | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [error, setError] = useState('')
  const [listReload, setListReload] = useState(0)
  const [previewReload, setPreviewReload] = useState(0)
  const [notePicker, setNotePicker] = useState<{workspaceId: string; sourceMaterialId: string} | null>(null)
  const selectedKey = selection.references.map(creatorReferenceKey).join('|')
  const sourceProfile = profile?.workspaceId === workspaceId && profile.type === 'xhs_creator_profile' ? profile : undefined
  const notes = importedReferenceNotes(sourceProfile)
  const availableNotes = notes.filter(note => !selection.references.some(reference => reference.kind === 'imported_note' && reference.id === sourceProfile?.id && reference.noteId === note.noteId))
  const savedImages = mediaAssets.filter(asset => asset.workspaceId === workspaceId && asset.mediaType.startsWith('image/'))
  const previewImages = preview?.note ? savedImages.filter(asset => asset.id === preview.note?.coverMediaAssetId || asset.metadata.noteId === preview.note?.noteId) : []

  useEffect(() => {setNotePicker(null)}, [workspaceId, profile?.id, disabled])

  useEffect(() => {
    let current = true
    for (const reference of selection.references) {
      const key = `${workspaceId}:${creatorReferenceKey(reference)}`
      if (cache[key]) continue
      void loadCreatorReference(workspaceId, reference).then(value => {
        if (current) setCache(previous => ({...previous, [key]: value}))
      }).catch(() => { /* Keep unavailable references removable; opening them shows the error. */ })
    }
    return () => {current = false}
  }, [workspaceId, selectedKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open || viewing) return
    let current = true
    setLoading(true); setError(''); setChoices([]); setSelectedId(''); setPreview(null)
    if (kind === 'imported_note') {setLoading(false); return}
    const request = kind === 'account_analysis'
      ? analysisRunApi.list(workspaceId).then(rows => rows.filter(row => row.workspaceId === workspaceId && row.workflowType === 'account_diagnosis' && row.status === 'completed')
        .map(row => ({reference: {kind: 'account_analysis' as const, id: row.id}, label: `${referenceDate(row.createdAt)}${row.origin === 'oracle_showcase' ? ' · 预写示例' : ''}`})))
      : audienceAnalysisApi.list(workspaceId).then(rows => rows.filter(row => row.workspaceId === workspaceId && row.status === 'completed')
        .map(row => ({reference: {kind: 'audience_analysis' as const, id: row.id}, label: `${referenceDate(row.createdAt)} · ${row.result.groups?.length || 0} 位候选${row.result.origin === 'oracle_showcase' ? ' · 预写示例' : ''}`})))
    void request.then(rows => {if (current) setChoices(rows)}).catch(e => {if (current) setError(errorText(e))}).finally(() => {if (current) setLoading(false)})
    return () => {current = false}
  }, [workspaceId, kind, open, viewing, listReload])

  useEffect(() => {
    if (!open) return
    const reference = viewing || (kind !== 'imported_note' ? choices.find(choice => choice.reference.id === selectedId)?.reference : undefined)
    if (!reference) {setPreview(null); setPreviewLoading(false); return}
    let current = true
    setPreviewLoading(true); setPreview(null); setError('')
    // Fetch the exact immutable record, even when a list supplied a summary.
    void loadCreatorReference(workspaceId, reference).then(value => {
      if (current) {setPreview(value); setCache(previous => ({...previous, [`${workspaceId}:${creatorReferenceKey(reference)}`]: value}))}
    }).catch(e => {if (current) setError(errorText(e))}).finally(() => {if (current) setPreviewLoading(false)})
    return () => {current = false}
  }, [workspaceId, open, viewing, selectedId, choices, previewReload, kind])

  function close() {setOpen(false); setNotePicker(null); setViewing(null); setError(''); setPreview(null)}
  function add() {
    if (!preview || disabled || selection.references.length >= 8) return
    const reference = preview.reference
    if (!selection.references.some(item => creatorReferenceKey(item) === creatorReferenceKey(reference))) onChange({...selection, references: [...selection.references, reference]})
    close()
  }
  function addNotes(ids?: string[]) {
    if (disabled || !sourceProfile || !notePicker || notePicker.workspaceId !== workspaceId || notePicker.sourceMaterialId !== sourceProfile.id || !ids?.length) return
    const selectedNotes = [...new Set(ids)].map(id => notes.find(note => note.noteId === id))
    if (selectedNotes.some(note => !note)) {setError('所选原笔记已变化，请重新选择。'); setNotePicker(null); return}
    const previews = selectedNotes.filter(note => !!note).map(note => importedReferencePreview(sourceProfile, note))
      .filter(value => !selection.references.some(reference => creatorReferenceKey(reference) === creatorReferenceKey(value.reference)))
    if (selection.references.length + previews.length > 8) {setError('最多添加 8 项参考，请减少所选原笔记。'); setNotePicker(null); return}
    if (previews.length) {
      setCache(previous => ({...previous, ...Object.fromEntries(previews.map(value => [`${workspaceId}:${creatorReferenceKey(value.reference)}`, value]))}))
      onChange({...selection, references: [...selection.references, ...previews.map(value => value.reference)]})
    }
    close()
  }
  const alreadySelected = !!preview && selection.references.some(reference => creatorReferenceKey(reference) === creatorReferenceKey(preview.reference))
  return <div className="creator-references">
    <div className="creator-references-heading"><span>本次参考 · {selection.references.length || '仅当前稿件'}<InfoHint label="创作参考说明">不添加参考时，只读取当前稿件与这段对话。可添加最多 8 项账号分析、受众分析或原笔记；更换参考后，下一条消息开启新的对话段。原笔记只读取所选标题与正文，不包含评论、图片或其他账号资料。</InfoHint></span><button type="button" className="text-button" disabled={disabled || selection.references.length >= 8} onClick={() => {setViewing(null); setOpen(true)}}>＋ 添加参考</button></div>
    {selection.references.length > 0 && <ul className="creator-reference-chips">{selection.references.map((reference, index) => {
      const key = creatorReferenceKey(reference), label = cache[`${workspaceId}:${key}`]?.label || `${referenceKindNames[reference.kind]} ${index + 1}`
      return <li key={key}><button type="button" className="text-button" onClick={() => {setViewing(reference); setOpen(true)}}>{label}</button><button type="button" className="icon-button" disabled={disabled} aria-label={`移除${label}`} onClick={() => onChange({...selection, references: selection.references.filter(item => creatorReferenceKey(item) !== key)})}>×</button></li>
    })}</ul>}
    {open && <CreatorDialog title={viewing ? '参考材料' : '添加参考'} onClose={close} className="creator-reference-dialog">
      {!viewing && <div className="creator-reference-selectors"><label>资料类型<select value={kind} onChange={event => setKind(event.target.value as CreatorContextReference['kind'])}><option value="account_analysis">账号分析</option><option value="audience_analysis">受众分析</option><option value="imported_note">原笔记</option></select></label>
        {kind !== 'imported_note' && <label>分析记录<select disabled={loading} value={selectedId} onChange={event => setSelectedId(event.target.value)}><option value="">{loading ? '正在读取…' : '选择一份分析'}</option>{choices.map(choice => <option key={choice.reference.id} value={choice.reference.id}>{choice.label}{selection.references.some(reference => creatorReferenceKey(reference) === creatorReferenceKey(choice.reference)) ? ' · 已添加' : ''}</option>)}</select></label>}
      </div>}
      {!viewing && kind === 'imported_note' && <section className="creator-reference-note-choice" aria-label="原笔记参考">
        <p>{!sourceProfile ? '请先导入账号笔记，再添加原笔记参考。' : !notes.length ? '当前没有可添加的有效原笔记。' : !availableNotes.length ? '这些原笔记已全部添加。' : `可添加 ${availableNotes.length} 篇原笔记 · 本次还可添加 ${Math.max(0, 8 - selection.references.length)} 项参考`}
          <InfoHint label="原笔记参考说明">可以查看已保存的图片与原文。助手只读取你所选笔记的标题与正文，不读取评论、图片或其他账号资料。</InfoHint></p>
        <button type="button" disabled={disabled || !sourceProfile || !availableNotes.length || selection.references.length >= 8} onClick={() => {if (sourceProfile) {setError(''); setNotePicker({workspaceId, sourceMaterialId: sourceProfile.id})}}}>选择原笔记</button>
      </section>}
      {!loading && !viewing && kind !== 'imported_note' && !choices.length && !error && <p className="creator-reference-empty">还没有已完成的{referenceKindNames[kind]}，也可以不添加参考，直接开始创作。</p>}
      {previewLoading && <p role="status">正在读取这份材料…</p>}
      {error && <div className="creator-reference-error" role="alert"><p>{error}</p><button type="button" onClick={() => {if (viewing || selectedId) setPreviewReload(value => value + 1); else setListReload(value => value + 1)}}>重试读取</button></div>}
      {preview && <section className="creator-reference-preview" aria-label={preview.note ? '原笔记原文' : '参考摘要'}><div><strong>{preview.label}</strong>{preview.isExample && <small>预写示例</small>}</div><small>{preview.scope}</small>
        {previewImages.length > 0 && <div className="creator-reference-note-images">{previewImages.map(image => <img key={image.id} src={image.fileUrl} alt={`${preview.note?.title || '原笔记'} · 已保存图片`} />)}</div>}
        <p className={preview.note ? 'creator-reference-note-body' : undefined}>{preview.summary}</p>{preview.lines.length > 0 && <ul>{preview.lines.map((line, index) => <li key={index}>{line}</li>)}</ul>}</section>}
      <div className="creator-reference-actions"><button type="button" onClick={close}>{viewing ? '关闭' : '取消'}</button>{!viewing && kind !== 'imported_note' && <button type="button" className="primary" disabled={disabled || !preview || previewLoading || alreadySelected || selection.references.length >= 8} onClick={add}>{alreadySelected ? '已添加' : '添加这份材料'}</button>}</div>
    </CreatorDialog>}
    {open && notePicker?.workspaceId === workspaceId && notePicker.sourceMaterialId === sourceProfile?.id && !disabled && <CreatorNoteSelectionDialog
      notes={availableNotes.map(note => ({...note, title: note.title || '未命名笔记'}))} mediaAssets={savedImages} scope="all" selectedIds={[]} title="选择原笔记参考" includeComments={false} contentOnlyPreview
      maxSelection={Math.max(0, 8 - selection.references.length)} onClose={() => setNotePicker(null)} onConfirm={(_scope, ids) => addNotes(ids)} />}
  </div>
}

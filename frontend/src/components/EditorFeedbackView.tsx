import {object, text, rows, strings, feedbackKinds as kinds, feedbackCards, feedbackGroups, verifiedConcerns, frozenTargetMatches, needsAuthorMaterial, type FeedbackRun, type Row} from '../editorFeedback'
import './EditorFeedbackView.css'

function Concerns({card, run}: {card:Row; run?:FeedbackRun}) {
  const concerns = verifiedConcerns(card, run)
  if (!concerns) return <p className="muted">{strings(card.readerConcernIds).length
    ? '具体顾虑暂无法核对，仍可查看当时发言。' : '此记录未保存具体顾虑关联，仍可查看当时发言。'}</p>
  return <div className="feedback-concerns"><b>回应的具体顾虑</b>
    {concerns.map(c => <div key={text(c.id)}>
      <p>{text(c.text)}</p>
      <small>{text(run?.personaDefinitions.find(p => p.id === c.personaId)?.name) || '当时的读者'} · {c.field === 'newConcerns' ? '回应后的顾虑记录' : '试读顾虑记录'}（非公开原话）</small>
    </div>)}
  </div>
}

function Source({id, run}: {id:string; run?:FeedbackRun}) {
  const matches = [...(run?.reactionResults || []), ...(run?.debateResults || [])].filter(m => m.messageId === id)
  if (matches.length !== 1) return <p className="muted">这条来源发言未保存或无法核对。</p>
  const source = matches[0]
  const person = run?.personaDefinitions.find(p => p.id === source.personaId)
  const name = text(person?.name) || text(person?.archetype) || '当时的读者（姓名未保存）'
  const reply = run?.debateResults.includes(source)
  const publicText = reply ? text(source.response) || text(source.text)
    : (source.action == null || source.action === 'comment') ? text(source.quote) || text(source.text) : ''
  return <div className="feedback-source">
    <b>{name} · {reply ? '公开回应' : publicText.trim() ? '公开评论' : '试读感受（未公开留言）'}</b>
    {publicText.trim() && <blockquote>{publicText}</blockquote>}
    {!reply && <>
      {text(source.understanding) && <p>当时理解：{text(source.understanding)}</p>}
      {strings(source.concerns).length > 0 && <p>关注点：{strings(source.concerns).join('；')}</p>}
      {strings(source.opportunities).length > 0 && <p>看到的价值：{strings(source.opportunities).join('；')}</p>}
      {!publicText.trim() && !text(source.understanding) && !strings(source.concerns).length && <p>{text(source.stance) || '此记录未保存具体感受。'}</p>}
    </>}
    {reply && !publicText.trim() && <p className="muted">未保存可核对的回应内容。</p>}
  </div>
}

function FrozenTarget({target, run}: {target:Row; run?:FeedbackRun}) {
  const hashMatches = frozenTargetMatches(target, run)
  if (target.field === 'whole') return <p className="muted">{hashMatches ? '针对当时整篇内容，不指定某一句。' : '当时的全文位置暂无法核对。'}</p>
  const field = target.field === 'title' ? 'title' : target.field === 'body' ? 'body' : null
  const content = field ? text(object(run?.inputSnapshot.topic)[field]) : ''
  const points = Array.from(content)
  const {start, end, occurrence} = target
  const quote = text(target.quote)
  if (!hashMatches) return <p className="muted">原文位置暂无法核对，未在当前稿件中查找替代内容。</p>
  return <><p className="muted">当时的{field === 'title' ? '标题' : '正文'} · 第 {Number(occurrence)} 处</p>
    <blockquote className="feedback-original" tabIndex={0} aria-label="当时的原文">{points.slice(0,Number(start)).join('')}<mark>{quote}</mark>{points.slice(Number(end)).join('')}</blockquote></>
}

export function EditorFeedbackView({data, run, onPrepare, editDisabled = false}: {
  data:Row; run?:FeedbackRun; onPrepare?: (card: Row) => void; editDisabled?: boolean
}) {
  const cards = feedbackCards(data)
  const diagnostics = object(data.editorFeedbackValidation)
  const hasUnavailableCards = rows(diagnostics.rejected).length > 0 || rows(data.editorFeedback).length > cards.length
  const keep = cards.filter(c => c.kind === 'keep')
  const changes = cards.filter(c => c.kind !== 'keep' && c.priority === 'first')
  const optional = cards.filter(c => c.kind !== 'keep' && c.priority !== 'first')
  function renderCard(card:Row, index:number, grouped = false) {
    const ids = strings(card.sourceMessageIds)
    const optionalEditor = card.sourceType === 'editor_optional'
    const target = object(card.target)
    const located = frozenTargetMatches(target, run)
    const isKeep = card.kind === 'keep'
    const material = needsAuthorMaterial(card)
    const showReason = isKeep || (!material && !text(card.suggestedText).trim())
    return <article className={`editor-feedback-card ${card.kind === 'keep' ? 'feedback-keep' : ''}`} key={`${text(card.id)}:${index}`}>
      <div className="feedback-card-meta">
        <span className="feedback-kind">{kinds[text(card.kind)]}{optionalEditor ? ' · 编辑补充' : ''}</span>
        {located && <span>{target.field === 'title' ? '标题' : target.field === 'body' ? '正文' : '整篇内容'}</span>}
        {grouped && <span className="feedback-option-label">改法 {index + 1}</span>}
      </div>
      <h5>{text(card.observation)}</h5>
      {showReason && <p>{text(card.reason)}</p>}
      {material ? <div className="feedback-suggestion"><b>等你补充的素材</b>
        {strings(card.materialRequests).length ? <ul>{strings(card.materialRequests).map((question, i) => <li key={i}>{question}</li>)}</ul>
          : <p>这条旧建议需要你的实际材料，请按上面的建议补充。</p>}
        {text(card.suggestedText) && <details><summary>查看旧版参考文字（未核实）</summary><p>{text(card.suggestedText)}</p></details>}
      </div> : text(card.suggestedText) && <div className="feedback-suggestion"><b>可参考的表达</b><p>{text(card.suggestedText)}</p></div>}
      {onPrepare && !isKeep && ['title','body'].includes(text(target.field)) && located
        && <div className="feedback-card-actions"><button disabled={editDisabled} onClick={() => onPrepare(card)}>{material ? '补充素材' : '查看改写'}</button></div>}
      <details className="feedback-evidence"><summary>查看依据与原文</summary>
        {!showReason && <p>{text(card.reason)}</p>}
        {strings(card.beneficiaries).length > 0 && <p className="muted">更适合：{strings(card.beneficiaries).map(id => {
          const p=run?.personaDefinitions.find(p=>p.id===id)
          return text(p?.name) || text(p?.archetype) || '当时的读者（姓名未保存）'
        }).join('、')}</p>}
        {text(card.tradeoff) && <p><b>取舍：</b>{text(card.tradeoff)}</p>}
        {!grouped && !optionalEditor && !isKeep && <Concerns card={card} run={run}/>}
        {optionalEditor ? <p className="muted">这是编辑助手的额外建议，不是读者已经提出的问题。</p>
          : ids.length ? ids.map((id,i)=><Source key={`${id}:${i}`} id={id} run={run}/>)
            : <p className="muted">此建议未保存可核对的读者来源。</p>}
        <FrozenTarget target={target} run={run}/>
      </details>
    </article>
  }
  function renderGroups(items:Row[]) {
    return feedbackGroups(items, run).map((group, index) => group.length === 1 ? renderCard(group[0], index) :
      <section className="feedback-alternatives" aria-label={`同一问题的 ${group.length} 种改法`} key={`group:${text(group[0].id)}:${index}`}>
        <h5>同一问题的 {group.length} 种改法</h5>
        <p className="muted">针对同一处原文，可择一参考或自行组合，不必逐条都改。</p>
        <details className="feedback-shared-concerns"><summary>查看共同关注点</summary><Concerns card={group[0]} run={run}/></details>
        {group.map((card, i) => renderCard(card, i, true))}
      </section>)
  }
  return <section className="editor-feedback" aria-label="创作修改反馈">
    {onPrepare && cards.some(c => c.kind !== 'keep' && ['title','body'].includes(text(object(c.target).field)) && frozenTargetMatches(object(c.target), run))
      && <p className="feedback-intro">先预览，确认采用后才更新稿件。</p>}
    {!cards.length && <p className="feedback-intro">{diagnostics.status === 'validated' && !hasUnavailableCards
      ? '本次没有具体修改建议。'
      : '这次未生成可用的修改建议，可查看读者发言或重新试读。'}</p>}
    {!!keep.length && <div className="feedback-section"><h4>值得保留</h4>{keep.map((card, i) => renderCard(card, i))}</div>}
    {!!changes.length && <div className="feedback-section"><h4>关键调整</h4>{renderGroups(changes)}</div>}
    {!!optional.length && <details className="feedback-optional"><summary>其他可选建议（{optional.length}）</summary>{renderGroups(optional)}</details>}
  </section>
}

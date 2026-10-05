import type { MediaAsset, SavePhase } from '../types'
import type { CreatorNote } from '../creatorNotes'
import { AccountPortraitView, type Observations, type Portrait } from './AccountPortraitView'
import { replyPersonaId, simulationPersonaLabels } from '../simulationPersonaLabels'
import { EditorFeedbackView } from './EditorFeedbackView'
import { feedbackCards, type FeedbackRun } from '../editorFeedback'

export type SaveState = { phase: SavePhase; message?: string }

export function SaveIndicator({ state }: { state: SaveState }) {
  if (state.phase === 'idle') return null
  const labels = {
    saving: '保存中…',
    saved: state.message || '已保存',
    error: state.message || '保存失败',
    idle: '',
  }
  return (
    <span className={`save-state ${state.phase}`} role="status">
      {labels[state.phase]}
    </span>
  )
}

export function ListBlock({ title, items }: { title: string; items: unknown }) {
  const values = Array.isArray(items) ? items : []
  if (values.length === 0) return null
  return (
    <>
      <b>{title}：</b>
      <ul>{values.map((item) => <li key={String(item)}>{String(item)}</li>)}</ul>
    </>
  )
}

function listValues(items: unknown): string[] {
  return Array.isArray(items) ? items.map((item) => String(item)) : []
}

function evidenceIsWeak(data: Record<string, unknown>): boolean {
  const confidence = String(data.evidenceConfidence || '').toLowerCase()
  return (
    confidence.includes('低') ||
    confidence.includes('low') ||
    listValues(data.cannotAssess).length > 0 ||
    listValues(data.recommendedNextEvidence).length > 0
  )
}

function EvidenceBoundaryPanel({ data }: { data: Record<string, unknown> }) {
  const confidence = String(data.evidenceConfidence || '')
  const scope = (data.evidenceScope || {}) as Record<string, unknown>
  const weak = evidenceIsWeak(data)
  const scopeEntries = [
    ['来源', scope.sourceType],
    ['有视频笔记', scope.hasVideoNotes],
    ['有视频理解', scope.hasVideoUnderstanding],
    ['有图片理解', scope.hasImageUnderstanding],
    ['有评论样本', scope.hasComments],
    ['媒体资产数', scope.mediaAssetCount],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '')

  if (
    !confidence &&
    scopeEntries.length === 0 &&
    !Array.isArray(data.evidenceLimitations) &&
    !Array.isArray(data.recommendedNextEvidence) &&
    !Array.isArray(data.cannotAssess)
  ) {
    return null
  }

  return (
    <div className={`structure-card evidence-boundary ${weak ? 'weak' : 'ok'}`}>
      <div className="evidence-boundary-head">
        <h4>{weak ? '证据不足，需要保守判断' : '证据边界'}</h4>
        {confidence && <span>{confidence}</span>}
      </div>
      {confidence && (
        <p>
          <b>证据置信度：</b> {confidence}
        </p>
      )}
      {scopeEntries.length > 0 && (
        <div className="why">
          {scopeEntries.map(([label, value]) => (
            <span key={String(label)}>
              <b>{String(label)}：</b> {String(value)}
              <br />
            </span>
          ))}
        </div>
      )}
      <ListBlock title="证据限制" items={data.evidenceLimitations} />
      <ListBlock title="无法可靠评估" items={data.cannotAssess} />
      <ListBlock title="建议补充证据" items={data.recommendedNextEvidence} />
    </div>
  )
}

export function ProfileView({ data, observations, notes = [], mediaAssets = [] }: {
  data: Record<string, unknown>
  observations?: Observations | null
  notes?: CreatorNote[]
  mediaAssets?: MediaAsset[]
}) {
  if (observations?.schemaVersion === 'xhs-account-observations/v1') {
    return <>
      <AccountPortraitView portrait={data.accountPortrait as Portrait | null} observations={observations} notes={notes} mediaAssets={mediaAssets} />
      <details className="account-legacy-profile" open={!data.accountPortrait}>
        <summary>更多内容归纳</summary>
        <LegacyProfileView data={data} showPerformanceContrast={false} />
      </details>
    </>
  }
  return <LegacyProfileView data={data} />
}

function LegacyProfileView({ data, showPerformanceContrast = true }: {
  data: Record<string, unknown>
  showPerformanceContrast?: boolean
}) {
  const pillars = Array.isArray(data.pillars) ? data.pillars : []
  const formulas = Array.isArray(data.titleFormulas) ? data.titleFormulas : []
  const hooks = Array.isArray(data.hookStyles) ? data.hookStyles : []
  const structure = (data.viralStructure || {}) as {
    name?: string
    steps?: string[]
  }
  const contrast = data.contrast as
    | {
        winners?: Array<{ title: string; metric: string }>
        losers?: Array<{ title: string; metric: string }>
        winFactors?: string[]
        loseFactors?: string[]
        takeaways?: string[]
      }
    | undefined
  return (
    <div className="stage-block">
      {/* Structured reports use frozen counts above, not model-written metrics or title matching. */}
      {contrast && showPerformanceContrast && (
        <>
          <label>📊 高表现 vs 低表现 · 对比诊断</label>
          <div className="cmp">
            <div className="cmp-col cmp-win">
              <h5>✅ 高表现共性</h5>
              {(contrast.winners || []).map((item) => (
                <div className="cmp-item" key={item.title}>
                  <b>{item.title}</b> · {item.metric}
                </div>
              ))}
              <ul>{(contrast.winFactors || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
            <div className="cmp-col cmp-lose">
              <h5>⚠️ 低表现共性</h5>
              {(contrast.losers || []).map((item) => (
                <div className="cmp-item" key={item.title}>
                  <b>{item.title}</b> · {item.metric}
                </div>
              ))}
              <ul>{(contrast.loseFactors || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>
        </>
      )}
      {Array.isArray(contrast?.takeaways) && contrast.takeaways.length > 0 && (
        <div className="takeaway">
          <b>可尝试的写法：</b>
          <ol>{contrast.takeaways.map((item) => <li key={item}>{item}</li>)}</ol>
        </div>
      )}
      <label>📚 内容支柱</label>
      <div className="pill-row">
        {pillars.map((pillar) => (
          <span className="quote red" key={String(pillar)}>
            {String(pillar)}
          </span>
        ))}
      </div>
      <label>✍️ 惯用标题公式</label>
      <div className="outline">
        {formulas.map((formula) => {
          const item = formula as { formula?: string; examples?: string[] }
          return (
            <div className="ol" key={item.formula}>
              <div className="sec">公式</div>
              <div className="ct">
                <b>{item.formula}</b>
                {(item.examples || []).map((example) => (
                  <div className="quote" key={example}>
                    例：{example}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <label>🪝 开头钩子习惯</label>
      <ul>{hooks.map((hook) => <li key={String(hook)}>{String(hook)}</li>)}</ul>
      <label>🧱 惯用爆款结构 · {structure.name}</label>
      <div className="titles">
        {(structure.steps || []).map((step, index) => (
          <div className="titlev" key={step}>
            <span>{index + 1}</span>
            {step}
          </div>
        ))}
      </div>
    </div>
  )
}

export function PainPointsView({ items }: { items: unknown }) {
  const painPoints = Array.isArray(items) ? items : []
  return (
    <>
      {painPoints.map((item) => {
        const point = item as {
          theme?: string
          intensity?: string
          count?: number
          evidence?: string[]
        }
        return (
          <div className="pp" key={point.theme}>
            <div className="pp-top">
              <b>{point.theme}</b>
              <span className={`tag ${point.intensity === '高' ? 'high' : 'mid'}`}>
                强度 {point.intensity}
              </span>
              <span className="tag cnt">{point.count || 0} 条相关</span>
            </div>
            <div>
              {(point.evidence || []).map((quote) => (
                <span className="quote" key={quote}>
                  “{quote}”
                </span>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}

export function TrendAnalysisView({ data }: { data: Record<string, unknown> }) {
  const themes = Array.isArray(data.themes) ? data.themes : []
  const patterns = Array.isArray(data.viralPatterns) ? data.viralPatterns : []
  const windows = Array.isArray(data.opportunityWindows)
    ? data.opportunityWindows
    : []
  return (
    <div className="stage-block">
      <label>🔥 高频内容主题</label>
      {themes.map((item) => {
        const theme = item as {
          theme?: string
          engagement?: string
          count?: number
          topPost?: string
          summary?: string
        }
        return (
          <div className="trend-theme" key={theme.theme}>
            <div className="trend-theme-top">
              <b>{theme.theme}</b>
              <span className={`tag ${theme.engagement === '高' ? 'high' : 'mid'}`}>
                热度 {theme.engagement}
              </span>
              <span className="tag cnt">{theme.count || 0} 篇相关</span>
            </div>
            <div>
              <span className="quote">代表帖：{theme.topPost}</span>
            </div>
            <div className="subline">{theme.summary}</div>
          </div>
        )
      })}
      <label>✨ 爆款规律</label>
      <ul>{patterns.map((item) => <li key={String(item)}>{String(item)}</li>)}</ul>
      <label>🎯 内容机会窗口</label>
      {windows.map((item) => (
        <div className="opportunity" key={String(item)}>
          <b>🪟</b> {String(item)}
        </div>
      ))}
    </div>
  )
}

export function StructureView({ data }: { data: Record<string, unknown> }) {
  const outline = Array.isArray(data.outline) ? data.outline : []
  return (
    <div className="stage-block">
      <div className="outline">
        {outline.map((item) => {
          const part = item as { sec?: string; ct?: string }
          return (
            <div className="ol" key={`${part.sec}-${part.ct}`}>
              <div className="sec">{part.sec}</div>
              <div className="ct">{part.ct}</div>
            </div>
          )
        })}
      </div>
      <div className="reuse">
        <b>♻ 可复用表达结构：</b> {String(data.reuse || '')}
      </div>
    </div>
  )
}

export function TitlesView({ items }: { items: unknown }) {
  const titles = Array.isArray(items) ? items : []
  return (
    <>
      {titles.map((item) => {
        const title = item as { topic?: string; variants?: string[] }
        return (
          <div className="topic" key={title.topic}>
            <h4>📌 {title.topic}</h4>
            <div className="titles">
              {(title.variants || []).map((variant, index) => (
                <div className="titlev" key={variant}>
                  <span>{String.fromCharCode(65 + index)}</span>
                  {variant}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}

export function PersonaListView({ items, personaLabels }: { items: unknown; personaLabels?: ReadonlyMap<string, string> }) {
  if (!Array.isArray(items) || items.length === 0) return null
  const labels = personaLabels || simulationPersonaLabels(items, [], [])
  return (
    <div className="persona-list">
      {(items as Array<Record<string, unknown>>).map((persona) => {
        const title = labels.get(String(persona.id)) || String(persona.name || persona.archetype || '未记录姓名的受众')
        const profile = String(persona.profile || persona.background || '')
        const personality = String(persona.personality || '')
        const concern = String(persona.concerns || persona.coreConcern || '')
        const preference = String(persona.contentPreference || '')
        return (
          <div className="topic" key={String(persona.id || persona.name)}>
            <h4>{title}</h4>
            <div className="angle">{profile}</div>
            <div className="why">
              {personality && (
                <>
                  <b>性格：</b> {personality}
                  <br />
                </>
              )}
              <b>关注：</b> {concern}
              {preference && (
                <>
                  <br />
                  <b>内容偏好：</b> {preference}
                </>
              )}
            </div>
            {Array.isArray(persona.evidenceRefs) && persona.evidenceRefs.length > 0 && <details>
              <summary>历史依据</summary>
              {(persona.evidenceRefs as Array<Record<string, unknown>>).map((ref, i) => <p key={i}>
                {ref.sourceType === 'comment' ? '评论直接表达' : '从笔记推断'} · 笔记 {String(ref.noteId)}
                {ref.commentId ? ` / 评论 ${String(ref.commentId)}` : ''}<br />{String(ref.quote)}
              </p>)}
            </details>}
            {persona.evidenceStatus === 'legacy_unverified' && <p className="muted">历史角色，来源引用尚未核验。</p>}
            {persona.evidenceStatus === 'hypothesis' && <p className="muted">假设性阅读视角，非实际受众观察。</p>}
            {Boolean(persona.limitations) && <p className="muted">{String(persona.limitations)}</p>}
          </div>
        )
      })}
    </div>
  )
}

export function ReactionListView({
  items,
  type,
  personaLabels,
}: {
  items: unknown
  type: 'reaction' | 'debate'
  personaLabels?: ReadonlyMap<string, string>
}) {
  if (!Array.isArray(items) || items.length === 0) return null
  const labels = personaLabels || simulationPersonaLabels([], type === 'reaction' ? items : [], type === 'debate' ? items : [])
  const label = (id: string) => labels.get(id) || '未记录姓名的受众'
  return (
    <div className="persona-list simulation-reactions">
      {(items as Array<Record<string, unknown>>).map((item) => (
        <div className="topic" key={String(item.personaId)}>
          <h4>{label(String(item.personaId))}</h4>
          {type === 'reaction' ? (
            <>
              <div className="angle">
                {String(item.stance || item.sentiment || '')} ·{' '}
                {item.action === 'skip' ? '划走，不评论' : item.action === 'no_comment' ? '读完，不评论' : `模拟评论：${String(item.quote || item.text || '')}`}
              </div>
              {Boolean(item.understanding) && <p>理解：{String(item.understanding)}</p>}
              {Boolean(item.triggerQuote) && <p>触发表达：{String(item.triggerQuote)}</p>}
              <ListBlock title="顾虑" items={item.concerns} />
              <ListBlock title="机会" items={item.opportunities} />
            </>
          ) : (
            <>
              <div className="angle">{String(item.response || item.text || '不追加回应')}</div>
              {Boolean(item.replyToId || item.targetedAt) && <p>回应：{replyPersonaId(item) ? label(replyPersonaId(item)) : '未记录回应对象'}</p>}
              {Boolean(item.changedMind && item.changeReason) && <p>看法变化：{String(item.changeReason)}</p>}
              {item.stance && (
                <div className="why">
                  <b>立场：</b> {String(item.stance)}
                </div>
              )}
              <ListBlock title="新顾虑" items={item.newConcerns} />
              <ListBlock title="更强信号" items={item.strongerSignals} />
            </>
          )}
        </div>
      ))}
    </div>
  )
}

export function SynthesisView({ data, feedbackRun }: { data: Record<string, unknown>; feedbackRun?: FeedbackRun }) {
  const topResonance = data.topResonance as
    | { persona?: string; reason?: string; expectedBehavior?: string }
    | undefined
  return (
    <div className="structure-card">
      <p className="muted">发布前预演 · 模拟反应不是实际评论，也不预测流量。</p>
      <h4>{String(data.verdict || '模拟结论')}</h4>
      {topResonance && Object.keys(topResonance).length > 0 && (
        <div className="why">
          <b>🎯 最有共鸣受众：</b> {String(topResonance.persona || '')}
          <br />
          {String(topResonance.reason || '')}
          <br />
          <b>预期行为：</b> {String(topResonance.expectedBehavior || '')}
        </div>
      )}
      <p>
        <b>最大阻力：</b> {String(data.mainResistance || '')}
      </p>
      <p>
        <b>最强切角：</b> {String(data.strongestAngle || '')}
      </p>
      {('editorFeedback' in data || 'editorFeedbackValidation' in data) && <EditorFeedbackView key={feedbackRun?.id || 'unavailable'} data={data} run={feedbackRun} />}
      {!feedbackCards(data).length && <ListBlock title="内容调整" items={data.contentAdjustments} />}
      <ListBlock title="风险提醒" items={data.riskWarnings} />
      <ListBlock title="潜在争议点" items={data.controversyPoints} />
      <ListBlock title="优化建议" items={data.suggestions} />
      {Boolean(data.limitations) && <p className="muted">{String(data.limitations)}</p>}
    </div>
  )
}

export function VideoCreatorProfileView({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="stage-block">
      <div className="structure-card">
        <h4>{String(data.creatorType || '创作者类型待判断')}</h4>
        <p>
          <b>置信度：</b> {String(data.typeConfidence || '')}
        </p>
        <p>{String(data.summary || '')}</p>
        <p>
          <b>受众定位：</b> {String(data.audiencePositioning || '')}
        </p>
      </div>
      <ListBlock title="内容支柱" items={data.contentPillars} />
      <ListBlock title="驱动信号" items={data.motivationSignals} />
      <ListBlock title="证据" items={data.evidence} />
      <ListBlock title="不确定项" items={data.uncertainties} />
      <EvidenceBoundaryPanel data={data} />
    </div>
  )
}

export function VideoQualityView({ data }: { data: Record<string, unknown> }) {
  const dimensions = Array.isArray(data.dimensionScores)
    ? data.dimensionScores
    : []
  const cannotAssess = listValues(data.cannotAssess)
  const recommendedNextEvidence = listValues(data.recommendedNextEvidence)
  return (
    <div className="stage-block">
      <div className={`structure-card video-verdict ${evidenceIsWeak(data) ? 'weak' : 'ok'}`}>
        <h4>
          质量评级：{String(data.level || '')} · {String(data.overallScore || '')}
        </h4>
        {cannotAssess.length > 0 && (
          <p>
            当前不可可靠评估：{cannotAssess.slice(0, 3).join('；')}
          </p>
        )}
        {recommendedNextEvidence.length > 0 && (
          <p>
            建议补充：{recommendedNextEvidence.slice(0, 3).join('；')}
          </p>
        )}
      </div>
      <div className="outline">
        {dimensions.map((item) => {
          const dimension = item as {
            dimension?: string
            score?: number
            reason?: string
          }
          return (
            <div className="ol" key={dimension.dimension}>
              <div className="sec">{dimension.dimension}</div>
              <div className="ct">
                <b>{dimension.score ?? ''}</b> · {dimension.reason}
              </div>
            </div>
          )
        })}
      </div>
      <ListBlock title="优势" items={data.strengths} />
      <ListBlock title="短板" items={data.weaknesses} />
      <ListBlock title="证据" items={data.evidence} />
      <EvidenceBoundaryPanel data={data} />
    </div>
  )
}

export function IncentiveFitView({ data }: { data: Record<string, unknown> }) {
  const programMatch = (data.programMatch || {}) as Record<string, unknown>
  const recommendation = String(data.recommendation || '')
  const fitLevel =
    recommendation.includes('不') || recommendation.includes('低')
      ? 'low'
      : recommendation.includes('适合') || recommendation.includes('高')
        ? 'high'
        : 'mid'
  return (
    <div className="stage-block">
      <div className={`structure-card incentive-verdict ${fitLevel}`}>
        <div className="evidence-boundary-head">
          <h4>激励适配：{recommendation || '待判断'}</h4>
          <span>{String(data.fitScore || '')}</span>
        </div>
        <p>{String(data.rationale || '')}</p>
        <div className="why">
          <b>适合计划：</b> {String(programMatch.bestProgramType || '')}
          <br />
          <b>原因：</b> {String(programMatch.why || '')}
          <br />
          <b>避免：</b> {String(programMatch.avoid || '')}
        </div>
      </div>
      <ListBlock title="适配条件" items={data.conditions} />
      <ListBlock title="风险" items={data.risks} />
      <ListBlock title="运营动作" items={data.operatorActions} />
      <EvidenceBoundaryPanel data={data} />
    </div>
  )
}

import {
  IncentiveFitView,
  PainPointsView,
  PersonaListView,
  ProfileView,
  ReactionListView,
  StructureView,
  SynthesisView,
  TitlesView,
  TrendAnalysisView,
  VideoCreatorProfileView,
  VideoQualityView,
} from './StageResultViews'
import type { StageView } from './WorkflowOutputPanel'
import { getTopicsFromStage } from '../appUtils'
import type { AnalysisRun, MediaAsset, Topic } from '../types'
import type { TopicCandidate } from '../workflows'
import { PendingSuggestions } from './PendingSuggestions'
import { creatorNotesFromPayload } from '../creatorNotes'
import type { Observations } from './AccountPortraitView'

type GeneratedTopicCardProps = {
  publicMode?: boolean
  onSimulateSavedTopic?: (topic: Topic) => void
  topic: TopicCandidate
  currentRun: AnalysisRun | null
  onSaveGeneratedTopic: (
    candidate: TopicCandidate,
    run: AnalysisRun | null,
  ) => Promise<Topic>
  onSelectTopic: (topic: Topic) => Promise<Topic>
  onGenerateBrief: (topic: Topic) => Promise<unknown>
  onGenerateDraft: (topic: Topic) => Promise<unknown>
  onFillSimulationTopic: (value: string) => void
}

function GeneratedTopicCard({
  publicMode = false,
  onSimulateSavedTopic,
  topic,
  currentRun,
  onSaveGeneratedTopic,
  onSelectTopic,
  onGenerateBrief,
  onGenerateDraft,
  onFillSimulationTopic,
}: GeneratedTopicCardProps) {
  async function ensureSavedAndSelect() {
    const saved = await onSaveGeneratedTopic(topic, currentRun)
    return onSelectTopic(saved)
  }

  return (
    <div className="topic">
      <h4>{topic.title}</h4>
      <div className="angle">
        切入角度：{topic.angle} · 对应痛点：{topic.pain || ''}
      </div>
      <div className="why">
        <b>为什么适合：</b> {topic.whyFit}
        {topic.whyTrending && (
          <>
            <br />
            <b>趋势依据：</b> {topic.whyTrending}
          </>
        )}
      </div>
      <PendingSuggestions value={topic.pendingSuggestions} />
      <div className="topic-actions">
        {publicMode ? <>
          <button onClick={() => void ensureSavedAndSelect().catch(() => undefined)}>查看选题</button>
          <button onClick={() => void ensureSavedAndSelect().then(onGenerateBrief).catch(() => undefined)}>AI 创作助手</button>
          <button onClick={() => void ensureSavedAndSelect().then((saved) => onSimulateSavedTopic?.(saved)).catch(() => undefined)}>受众模拟</button>
        </> : <>
        <button onClick={() => onSaveGeneratedTopic(topic, currentRun)}>
          保存到选题库
        </button>
        <button onClick={ensureSavedAndSelect}>设为当前选题</button>
        <button
          onClick={async () => {
            const saved = await ensureSavedAndSelect()
            onFillSimulationTopic(`${saved.title}\n切入角度：${saved.angle}`)
          }}
        >
          发送到受众模拟
        </button>
        <button
          onClick={async () => {
            const saved = await ensureSavedAndSelect()
            await onGenerateBrief(saved)
          }}
        >
          生成创作 Brief
        </button>
        <button
          onClick={async () => {
            const saved = await ensureSavedAndSelect()
            await onGenerateDraft(saved)
          }}
        >
          生成内容结构
        </button>
        <button
          className="btn-fill"
          onClick={() => onFillSimulationTopic(`${topic.title}\n切入角度：${topic.angle}`)}
        >
          → 填入下期选题
        </button>
        </>}
      </div>
    </div>
  )
}

type StageResultRendererProps = Omit<
  GeneratedTopicCardProps,
  'topic'
> & {
  stage: StageView
  mediaAssets?: MediaAsset[]
}

export function StageResultRenderer({
  publicMode = false,
  onSimulateSavedTopic,
  stage,
  mediaAssets = [],
  currentRun,
  onSaveGeneratedTopic,
  onSelectTopic,
  onGenerateBrief,
  onGenerateDraft,
  onFillSimulationTopic,
}: StageResultRendererProps) {
  if (!stage.result) return null
  const result = stage.result as Record<string, unknown>
  if (stage.key === 'profile' && result.profile) {
    return <ProfileView data={result.profile as Record<string, unknown>}
      observations={result.observations as Observations | undefined}
      notes={creatorNotesFromPayload(currentRun?.inputSnapshot.xhsCreatorProfile)}
      mediaAssets={mediaAssets} />
  }
  if (stage.key === 'trend_analysis' && result.trendAnalysis) {
    return (
      <TrendAnalysisView data={result.trendAnalysis as Record<string, unknown>} />
    )
  }
  if (stage.key === 'pain_points') return <PainPointsView items={result.painPoints} />
  if (stage.key === 'topics') {
    return (
      <>
        {getTopicsFromStage(stage.result).map((topic) => (
          <GeneratedTopicCard
            publicMode={publicMode}
            onSimulateSavedTopic={onSimulateSavedTopic}
            key={topic.title}
            topic={topic}
            currentRun={currentRun}
            onSaveGeneratedTopic={onSaveGeneratedTopic}
            onSelectTopic={onSelectTopic}
            onGenerateBrief={onGenerateBrief}
            onGenerateDraft={onGenerateDraft}
            onFillSimulationTopic={onFillSimulationTopic}
          />
        ))}
      </>
    )
  }
  if (stage.key === 'titles') return <TitlesView items={result.titles} />
  if (stage.key === 'structure' && result.structure) {
    return <StructureView data={result.structure as Record<string, unknown>} />
  }
  if (stage.key === 'personas') return <PersonaListView items={result.personas} />
  if (stage.key === 'initial_reactions') {
    return <ReactionListView items={result.reactions} type="reaction" />
  }
  if (stage.key === 'debate_responses') {
    if (result.skippedReason) return <p className="muted">{String(result.skippedReason)}</p>
    return <ReactionListView items={result.debateResponses} type="debate" />
  }
  if (stage.key === 'synthesis' && result.synthesis) {
    return <SynthesisView data={result.synthesis as Record<string, unknown>} />
  }
  if (stage.key === 'creator_profile' && result.creatorProfile) {
    return (
      <VideoCreatorProfileView
        data={result.creatorProfile as Record<string, unknown>}
      />
    )
  }
  if (stage.key === 'video_quality' && result.videoQuality) {
    return (
      <VideoQualityView data={result.videoQuality as Record<string, unknown>} />
    )
  }
  if (stage.key === 'incentive_fit' && result.incentiveFit) {
    return (
      <IncentiveFitView data={result.incentiveFit as Record<string, unknown>} />
    )
  }
  return <pre className="json-preview">{JSON.stringify(stage.result, null, 2)}</pre>
}

function ContentBriefView({ value }: { value: Record<string, unknown> }) {
  const brief = (value.brief || null) as Record<string, unknown> | null
  if (!brief) return <pre className="json-preview">{JSON.stringify(value, null, 2)}</pre>
  const list = (key: string) => (Array.isArray(brief[key]) ? (brief[key] as unknown[]) : [])
  return (
    <div className="stage-card">
      <h3>{String(brief.topicTitle || '创作 Brief')}</h3>
      <p>
        <b>精炼角度：</b>
        {String(brief.refinedAngle || '未填写')}
      </p>
      <p>
        <b>目标读者：</b>
        {String(brief.targetReader || '未填写')}
      </p>
      <p>
        <b>内容承诺：</b>
        {String(brief.contentPromise || '未填写')}
      </p>
      <p>
        <b>核心观点：</b>
        {String(brief.corePoint || '未填写')}
      </p>
      <p>
        <b>开头钩子：</b>
        {String(brief.openingHook || '未填写')}
      </p>
      <div className="mini-grid">
        <div>
          <b>论证路径</b>
          <ul>
            {list('argumentPath').map((item, index) => (
              <li key={`${index}-${String(item)}`}>{String(item)}</li>
            ))}
          </ul>
        </div>
        <div>
          <b>素材需求</b>
          <ul>
            {list('materialNeeds').map((item, index) => (
              <li key={`${index}-${String(item)}`}>{String(item)}</li>
            ))}
          </ul>
        </div>
        <div>
          <b>标题方向</b>
          <ul>
            {list('titleDirections').map((item, index) => (
              <li key={`${index}-${String(item)}`}>{String(item)}</li>
            ))}
          </ul>
        </div>
        <div>
          <b>风险</b>
          <ul>
            {list('risks').map((item, index) => (
              <li key={`${index}-${String(item)}`}>{String(item)}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

export function DraftStructureRenderer({
  value,
}: {
  value: Record<string, unknown>
}) {
  if (value.brief) return <ContentBriefView value={value} />
  const structure = (value.structure || null) as Record<string, unknown> | null
  if (structure) return <StructureView data={structure} />
  return <pre className="json-preview">{JSON.stringify(value, null, 2)}</pre>
}

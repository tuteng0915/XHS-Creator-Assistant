import type { Skill } from '../types'
import type { SkillDefinitionDraft } from '../capabilityDefinitionValidation'
import {
  contextPolicyJsonWithVideoRubric,
  isVideoRubricSkill,
  videoRubricDraftFromContextPolicyJson,
  type VideoRubricTextDraft,
} from '../appUtils'

type Props = {
  selectedSkill: Skill | null
  draft: SkillDefinitionDraft | null
  saving: boolean
  status: string
  onDraftChange: (draft: SkillDefinitionDraft | null) => void
  onStatusChange: (status: string) => void
  onSave: () => void
}

function VideoRubricEditor({
  draft,
  updateDraft,
}: {
  draft: SkillDefinitionDraft
  updateDraft: (patch: Partial<SkillDefinitionDraft>) => void
}) {
  const rubricDraft = videoRubricDraftFromContextPolicyJson(draft.contextPolicyJson)
  if (!rubricDraft) {
    return (
      <div className="rubric-editor-card error">
        <b>视频诊断 Rubric</b>
        <p>Context Policy JSON 当前无法解析。先修复 JSON 后，才能使用结构化 rubric 编辑器。</p>
      </div>
    )
  }
  const updateRubric = (patch: Partial<VideoRubricTextDraft>) => {
    updateDraft({
      contextPolicyJson: contextPolicyJsonWithVideoRubric(draft.contextPolicyJson, {
        ...rubricDraft,
        ...patch,
      }),
    })
  }
  return (
    <div className="rubric-editor-card">
      <div className="rubric-editor-head">
        <div>
          <b>视频诊断 Rubric</b>
          <p>
            这里会写入 <code>contextPolicy.pmRubric</code>。每行是一条规则，
            用竖线分隔字段。
          </p>
        </div>
        <span>structured</span>
      </div>
      <label htmlFor="video-rubric-creator-types">
        创作者类型规则：类型 | 激励适配度 | 判定规则
      </label>
      <textarea
        id="video-rubric-creator-types"
        rows={5}
        value={rubricDraft.creatorTypes}
        onChange={(event) => updateRubric({ creatorTypes: event.target.value })}
      />
      <label htmlFor="video-rubric-quality-dimensions">
        质量评价维度：维度 | 高分标准 | 中分标准 | 低分标准 | 必要证据
      </label>
      <textarea
        id="video-rubric-quality-dimensions"
        rows={6}
        value={rubricDraft.qualityDimensions}
        onChange={(event) => updateRubric({ qualityDimensions: event.target.value })}
      />
      <label htmlFor="video-rubric-evidence-rules">证据限制规则（一行一个）</label>
      <textarea
        id="video-rubric-evidence-rules"
        rows={4}
        value={rubricDraft.evidenceRules}
        onChange={(event) => updateRubric({ evidenceRules: event.target.value })}
      />
      <label htmlFor="video-rubric-incentive-rules">
        激励适配规则：信号 | 解读 | 运营动作
      </label>
      <textarea
        id="video-rubric-incentive-rules"
        rows={5}
        value={rubricDraft.incentiveRules}
        onChange={(event) => updateRubric({ incentiveRules: event.target.value })}
      />
    </div>
  )
}

export function SkillDefinitionEditor({
  selectedSkill,
  draft,
  saving,
  status,
  onDraftChange,
  onStatusChange,
  onSave,
}: Props) {
  if (!draft) return null

  const updateDraft = (patch: Partial<SkillDefinitionDraft>) => {
    onDraftChange({ ...draft, ...patch })
  }
  const statusText =
    status === 'saving'
      ? '保存中…'
      : status === 'saved'
        ? '已保存'
        : status.startsWith('error:')
          ? status.replace('error:', '保存失败：')
          : ''

  return (
    <div className="source-editor-card capability-editor-card">
      <p className="subline">
        PM 调优模式：保存后会把当前 skill 变成 workspace-level generated override，
        不会直接修改 builtin seed。
      </p>
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="skill-display-name">Skill 名称</label>
          <input
            id="skill-display-name"
            value={draft.displayName}
            onChange={(event) => updateDraft({ displayName: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="skill-category">分类</label>
          <input
            id="skill-category"
            value={draft.category}
            onChange={(event) => updateDraft({ category: event.target.value })}
          />
        </div>
      </div>
      <label htmlFor="skill-purpose">用途 / 调优说明</label>
      <textarea
        id="skill-purpose"
        rows={3}
        value={draft.purpose}
        onChange={(event) => updateDraft({ purpose: event.target.value })}
      />
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="skill-artifact-effect">Artifact Effect</label>
          <input
            id="skill-artifact-effect"
            value={draft.artifactEffect}
            onChange={(event) => updateDraft({ artifactEffect: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="skill-version">版本</label>
          <input
            id="skill-version"
            value={draft.version}
            onChange={(event) => updateDraft({ version: event.target.value })}
          />
        </div>
      </div>
      <label htmlFor="skill-failure-mode">Failure Mode</label>
      <textarea
        id="skill-failure-mode"
        rows={2}
        value={draft.failureMode}
        onChange={(event) => updateDraft({ failureMode: event.target.value })}
      />
      {selectedSkill && isVideoRubricSkill(selectedSkill.skillId) && (
        <VideoRubricEditor draft={draft} updateDraft={updateDraft} />
      )}
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="skill-required-inputs">Required Inputs（一行一个）</label>
          <textarea
            id="skill-required-inputs"
            rows={5}
            value={draft.requiredInputs}
            onChange={(event) => updateDraft({ requiredInputs: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="skill-optional-inputs">Optional Inputs（一行一个）</label>
          <textarea
            id="skill-optional-inputs"
            rows={5}
            value={draft.optionalInputs}
            onChange={(event) => updateDraft({ optionalInputs: event.target.value })}
          />
        </div>
      </div>
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="skill-trigger-intents">Trigger Intents（一行一个）</label>
          <textarea
            id="skill-trigger-intents"
            rows={4}
            value={draft.triggerIntents}
            onChange={(event) => updateDraft({ triggerIntents: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="skill-composable-with">Composable With（一行一个）</label>
          <textarea
            id="skill-composable-with"
            rows={4}
            value={draft.composableWith}
            onChange={(event) => updateDraft({ composableWith: event.target.value })}
          />
        </div>
      </div>
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="skill-side-effects">Side Effects（一行一个）</label>
          <textarea
            id="skill-side-effects"
            rows={4}
            value={draft.sideEffects}
            onChange={(event) => updateDraft({ sideEffects: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="skill-implementation-refs">Implementation Refs（一行一个）</label>
          <textarea
            id="skill-implementation-refs"
            rows={4}
            value={draft.implementationRefs}
            onChange={(event) => updateDraft({ implementationRefs: event.target.value })}
          />
        </div>
      </div>
      <label htmlFor="skill-context-policy-json">Context Policy JSON</label>
      <textarea
        id="skill-context-policy-json"
        rows={8}
        value={draft.contextPolicyJson}
        onChange={(event) => updateDraft({ contextPolicyJson: event.target.value })}
      />
      <label htmlFor="skill-output-schema-json">Output Schema JSON</label>
      <textarea
        id="skill-output-schema-json"
        rows={8}
        value={draft.outputSchemaJson}
        onChange={(event) => updateDraft({ outputSchemaJson: event.target.value })}
      />
      <label htmlFor="skill-user-notes">Workspace Notes</label>
      <textarea
        id="skill-user-notes"
        rows={3}
        value={draft.userNotes}
        onChange={(event) => updateDraft({ userNotes: event.target.value })}
      />
      <div className="save-row">
        <button className="save-button" disabled={saving} onClick={onSave}>
          {saving ? '保存中…' : '保存 Skill Contract'}
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={saving}
          onClick={() => {
            onDraftChange(null)
            onStatusChange('')
          }}
        >
          取消编辑
        </button>
        {statusText && (
          <span
            className={
              status.startsWith('error:') ? 'inline-error' : 'inline-save-state'
            }
          >
            {statusText}
          </span>
        )}
      </div>
    </div>
  )
}

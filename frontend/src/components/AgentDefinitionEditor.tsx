import {
  listFromText,
  textFromList,
  type AgentDefinitionDraft,
} from '../capabilityDefinitionValidation'
import type { SkillSummary } from '../types'

type Props = {
  draft: AgentDefinitionDraft | null
  saving: boolean
  status: string
  skills: SkillSummary[]
  onDraftChange: (draft: AgentDefinitionDraft | null) => void
  onStatusChange: (status: string) => void
  onSave: () => void
}

export function AgentDefinitionEditor({
  draft,
  saving,
  status,
  skills,
  onDraftChange,
  onStatusChange,
  onSave,
}: Props) {
  if (!draft) return null

  const updateDraft = (patch: Partial<AgentDefinitionDraft>) => {
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
        PM 调优模式：保存后会把当前 agent 变成 workspace-level generated override。
        skillIds 必须引用当前 workspace 已存在的 Skills。
      </p>
      <div className="compact-grid two-col">
        <div>
          <label htmlFor="agent-display-name">Agent 名称</label>
          <input
            id="agent-display-name"
            value={draft.displayName}
            onChange={(event) => updateDraft({ displayName: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="agent-version">版本</label>
          <input
            id="agent-version"
            value={draft.version}
            onChange={(event) => updateDraft({ version: event.target.value })}
          />
        </div>
      </div>
      <label htmlFor="agent-purpose">用途 / 调优说明</label>
      <textarea
        id="agent-purpose"
        rows={3}
        value={draft.purpose}
        onChange={(event) => updateDraft({ purpose: event.target.value })}
      />
      <label htmlFor="agent-system-prompt">System Prompt</label>
      <textarea
        id="agent-system-prompt"
        rows={8}
        value={draft.systemPrompt}
        onChange={(event) => updateDraft({ systemPrompt: event.target.value })}
      />
      <label htmlFor="agent-skill-ids">Skill IDs（一行一个）</label>
      <textarea
        id="agent-skill-ids"
        rows={6}
        value={draft.skillIds}
        onChange={(event) => updateDraft({ skillIds: event.target.value })}
      />
      <div className="structured-editor-card">
        <div className="asset-section-head">
          <h3>组合 Skills</h3>
          <span>structured</span>
        </div>
        <p className="subline">
          这里会同步写入 Skill IDs。仍可在上方 textarea 中手动补充暂未登记的 stable id。
        </p>
        <div className="capability-checkbox-list">
          {skills.map((skill) => {
            const selected = listFromText(draft.skillIds).includes(skill.skillId)
            return (
              <label key={skill.id}>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={(event) => {
                    const next = new Set(listFromText(draft.skillIds))
                    if (event.target.checked) next.add(skill.skillId)
                    else next.delete(skill.skillId)
                    updateDraft({ skillIds: textFromList([...next]) })
                  }}
                />
                <span>
                  <b>{skill.displayName}</b>
                  <small>{skill.skillId}</small>
                </span>
              </label>
            )
          })}
        </div>
      </div>
      <label htmlFor="agent-context-policy-json">Default Context Policy JSON</label>
      <textarea
        id="agent-context-policy-json"
        rows={8}
        value={draft.defaultContextPolicyJson}
        onChange={(event) =>
          updateDraft({ defaultContextPolicyJson: event.target.value })
        }
      />
      <label htmlFor="agent-user-notes">Workspace Notes</label>
      <textarea
        id="agent-user-notes"
        rows={3}
        value={draft.userNotes}
        onChange={(event) => updateDraft({ userNotes: event.target.value })}
      />
      <div className="save-row">
        <button className="save-button" disabled={saving} onClick={onSave}>
          {saving ? '保存中…' : '保存 Agent Definition'}
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

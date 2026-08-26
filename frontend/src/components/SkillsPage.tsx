import type { ReactNode } from 'react'

import { ListBlock } from './StageResultViews'
import {
  capabilityStatusClass,
  type ConversationContextTarget,
} from '../appUtils'
import type { Skill, SkillSummary } from '../types'

type Props = {
  skills: SkillSummary[]
  selectedSkill: Skill | null
  agentConversationCreating: boolean
  definitionDiffPanel: ReactNode
  definitionEditor: ReactNode
  skillTestPanel: ReactNode
  onOpenSkill: (skillAssetId: string) => void
  onEditSkill: (skill: Skill) => void
  onDesignSkill: (contextTarget?: ConversationContextTarget) => void
  onTuneSkill: (skill: Skill) => void
}

export function SkillsPage({
  skills,
  selectedSkill,
  agentConversationCreating,
  definitionDiffPanel,
  definitionEditor,
  skillTestPanel,
  onOpenSkill,
  onEditSkill,
  onDesignSkill,
  onTuneSkill,
}: Props) {
  const grouped = skills.reduce<Record<string, SkillSummary[]>>((acc, skill) => {
    acc[skill.category] = [...(acc[skill.category] || []), skill]
    return acc
  }, {})

  return (
    <div className="workspace-page">
      <section className="history-list">
        <div className="panel-title">✦ Skills</div>
        <p className="subline">
          Skills 是当前 workspace 可组合的产品能力资产；用户侧只读展示 contract，
          不提供通用 agent builder。
        </p>
        <div className="asset-maker-call">
          <span>不要手填 contract：描述你需要的能力，让 Capability Maker 生成 Skill 提案。</span>
          <button
            className="small-primary"
            disabled={agentConversationCreating}
            onClick={() =>
              onDesignSkill(
                selectedSkill
                  ? { assetType: 'skill', assetId: selectedSkill.id }
                  : undefined,
              )
            }
          >
            让 Capability Maker 设计 Skill
          </button>
        </div>
        {Object.entries(grouped).map(([category, items]) => (
          <div key={category} className="skill-group">
            <label>{category}</label>
            {items.map((skill) => (
              <button
                key={skill.id}
                className={`run-row ${selectedSkill?.id === skill.id ? 'active' : ''}`}
                onClick={() => onOpenSkill(skill.id)}
              >
                <span>{skill.displayName}</span>
                <b className={capabilityStatusClass(skill.status)}>{skill.status}</b>
                <small>{skill.skillId}</small>
              </button>
            ))}
          </div>
        ))}
      </section>
      <section className="history-detail">
        {selectedSkill ? (
          <>
            <div className="detail-head">
              <div>
                <h2>{selectedSkill.displayName}</h2>
                <p>
                  {selectedSkill.skillId} · {selectedSkill.category} ·{' '}
                  {selectedSkill.source} · {selectedSkill.version}
                </p>
              </div>
              <span className={capabilityStatusClass(selectedSkill.status)}>
                {selectedSkill.status}
              </span>
            </div>
            <div className="detail-actions">
              <button type="button" onClick={() => onEditSkill(selectedSkill)}>
                编辑 contract
              </button>
              <button
                type="button"
                disabled={agentConversationCreating}
                onClick={() => onTuneSkill(selectedSkill)}
              >
                让 Capability Maker 调优
              </button>
            </div>
            {definitionDiffPanel}
            {definitionEditor}
            {skillTestPanel}
            <p>{selectedSkill.purpose}</p>
            <label>Artifact Effect</label>
            <div className="why">{selectedSkill.artifactEffect}</div>
            <label>Required Inputs</label>
            <ListBlock title="输入" items={selectedSkill.requiredInputs} />
            <label>Optional Inputs</label>
            <ListBlock title="可选" items={selectedSkill.optionalInputs} />
            <label>Composable With</label>
            <ListBlock title="下游 Skill" items={selectedSkill.composableWith} />
            <label>Failure Mode</label>
            <div className="why">{selectedSkill.failureMode}</div>
            <label>Context Policy</label>
            <pre className="json-preview">
              {JSON.stringify(selectedSkill.contextPolicy, null, 2)}
            </pre>
            <label>Output Schema</label>
            <pre className="json-preview">
              {JSON.stringify(selectedSkill.outputSchema, null, 2)}
            </pre>
            <label>Implementation Refs</label>
            <ListBlock title="代码引用" items={selectedSkill.implementationRefs} />
            {selectedSkill.userNotes && (
              <>
                <label>Workspace Notes</label>
                <div className="why">{selectedSkill.userNotes}</div>
              </>
            )}
          </>
        ) : (
          <div className="empty-card">选择一个 Skill 查看输入、输出和组合边界。</div>
        )}
      </section>
    </div>
  )
}

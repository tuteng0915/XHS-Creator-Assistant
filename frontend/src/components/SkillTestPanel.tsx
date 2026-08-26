import type { GenerationMode } from '../workflows'
import type { Skill, SkillInvokeResponse } from '../types'
import {
  isDirectlyInvokableSkill,
  supportsSkillDryRun,
} from '../appUtils'

type SkillTestStatus = 'idle' | 'running' | 'completed' | 'error'

type Props = {
  skill: Skill
  skillTestMode: GenerationMode
  skillTestInput: string
  skillTestStatus: SkillTestStatus
  skillTestError: string
  skillTestResult: SkillInvokeResponse | null
  onSkillTestModeChange: (mode: GenerationMode) => void
  onSkillTestInputChange: (value: string) => void
  onRunSkillTest: () => void
}

export function SkillTestPanel({
  skill,
  skillTestMode,
  skillTestInput,
  skillTestStatus,
  skillTestError,
  skillTestResult,
  onSkillTestModeChange,
  onSkillTestInputChange,
  onRunSkillTest,
}: Props) {
  const canInvoke = isDirectlyInvokableSkill(skill.skillId)
  const canDryRun = supportsSkillDryRun(skill.skillId)

  return (
    <div className="source-editor-card skill-test-card">
      <div className="detail-head compact">
        <div>
          <h3>Skill Test</h3>
          <p>用当前 Skill 的受控 invoke / dry-run API 做一次最小测试。</p>
        </div>
        {canInvoke ? (
          <span>invoke-ready</span>
        ) : canDryRun ? (
          <span>dry-run-ready</span>
        ) : (
          <span>workflow-only</span>
        )}
      </div>
      {!canInvoke && !canDryRun ? (
        <div className="empty-card">
          这个 Skill 当前不能单独 invoke 或 dry-run。它会通过绑定的产品 workflow 执行。
        </div>
      ) : (
        <>
          <div className="compact-grid two-col">
            <div>
              <label htmlFor="skill-test-mode">模式</label>
              <select
                id="skill-test-mode"
                value={skillTestMode}
                onChange={(event) =>
                  onSkillTestModeChange(event.target.value as GenerationMode)
                }
              >
                <option value="demo">demo</option>
                <option value="live">live</option>
              </select>
            </div>
            <div className="skill-test-hint">
              invoke-ready 可在 live 模式调用真实后端；dry-run 不写业务资产。
            </div>
          </div>
          <label htmlFor="skill-test-input">Input JSON</label>
          <textarea
            id="skill-test-input"
            rows={7}
            value={skillTestInput}
            onChange={(event) => onSkillTestInputChange(event.target.value)}
          />
          <div className="save-row">
            <button
              className="save-button"
              disabled={skillTestStatus === 'running'}
              onClick={onRunSkillTest}
            >
              {skillTestStatus === 'running' ? '测试中…' : '运行 Skill Test'}
            </button>
            {skillTestStatus === 'completed' && (
              <span className="inline-save-state">测试完成</span>
            )}
            {skillTestStatus === 'error' && (
              <span className="inline-error">测试失败：{skillTestError}</span>
            )}
          </div>
          {skillTestResult && (
            <>
              <label>Output</label>
              <pre className="json-preview">
                {JSON.stringify(skillTestResult.output, null, 2)}
              </pre>
              <label>Model Metadata</label>
              <pre className="json-preview">
                {JSON.stringify(skillTestResult.modelMetadata, null, 2)}
              </pre>
            </>
          )}
        </>
      )}
    </div>
  )
}

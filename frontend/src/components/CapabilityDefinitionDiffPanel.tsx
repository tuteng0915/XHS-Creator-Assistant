import type { CapabilityDefinitionDiff } from '../types'
import type { CapabilityAssetType, DefinitionDiffStatus } from '../appUtils'

type Props = {
  assetType: CapabilityAssetType
  definitionDiff: CapabilityDefinitionDiff | null
  definitionDiffStatus: DefinitionDiffStatus
  definitionDiffError: string
  onLoadDiff: (assetType: CapabilityAssetType) => void
  onRevertDefinition: (assetType: CapabilityAssetType) => void
}

export function CapabilityDefinitionDiffPanel({
  assetType,
  definitionDiff,
  definitionDiffStatus,
  definitionDiffError,
  onLoadDiff,
  onRevertDefinition,
}: Props) {
  const isCurrentDiff = definitionDiff?.assetType === assetType
  const statusText =
    definitionDiffStatus === 'loading'
      ? '加载中…'
      : definitionDiffStatus === 'reverting'
        ? '恢复中…'
        : definitionDiffStatus === 'reverted'
          ? '已恢复内置版本'
          : definitionDiffStatus === 'error'
            ? `失败：${definitionDiffError}`
            : ''

  return (
    <div className="source-editor-card capability-diff-card">
      <div className="detail-head compact">
        <div>
          <h3>Definition Diff</h3>
          <p>对比当前 workspace override 和代码内置版本；只影响能力资产定义。</p>
        </div>
        <span>{isCurrentDiff ? definitionDiff.source : 'not loaded'}</span>
      </div>
      <div className="save-row">
        <button
          type="button"
          className="secondary-button"
          disabled={
            definitionDiffStatus === 'loading' ||
            definitionDiffStatus === 'reverting'
          }
          onClick={() => onLoadDiff(assetType)}
        >
          查看与内置差异
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={
            !isCurrentDiff ||
            !definitionDiff.canRevert ||
            definitionDiffStatus === 'reverting'
          }
          onClick={() => onRevertDefinition(assetType)}
        >
          恢复内置版本
        </button>
        {statusText && (
          <span
            className={
              definitionDiffStatus === 'error' ? 'inline-error' : 'inline-save-state'
            }
          >
            {statusText}
          </span>
        )}
      </div>
      {isCurrentDiff && (
        <>
          <label>Changed Fields</label>
          <div className="why">
            {definitionDiff.changedFields.length > 0
              ? definitionDiff.changedFields.join(' / ')
              : '没有定义字段差异'}
          </div>
          <div className="compact-grid two-col">
            <div>
              <label>Current Definition</label>
              <pre className="json-preview">
                {JSON.stringify(definitionDiff.currentDefinition, null, 2)}
              </pre>
            </div>
            <div>
              <label>Builtin Definition</label>
              <pre className="json-preview">
                {JSON.stringify(definitionDiff.builtinDefinition, null, 2)}
              </pre>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

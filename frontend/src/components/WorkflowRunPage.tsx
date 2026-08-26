import type { ReactNode } from 'react'

import {
  WorkflowCallPanel,
  type WorkflowCallPanelProps,
} from './WorkflowCallPanel'
import {
  WorkflowOutputPanel,
  type StageView,
  type WorkflowOutputKind,
} from './WorkflowOutputPanel'
import type { WorkflowTab } from '../workflows'

type Props = WorkflowCallPanelProps & {
  views: StageView[]
  outputKind: WorkflowOutputKind
  runError: string
  renderStageResult: (stage: StageView) => ReactNode
}

export function WorkflowRunPage({
  views,
  outputKind,
  runError,
  renderStageResult,
  ...workflowCallProps
}: Props) {
  const targetTab = workflowCallProps.targetTab

  return (
    <div className="prototype-grid">
      <WorkflowCallPanel {...workflowCallProps} />
      <WorkflowOutputPanel
        targetTab={targetTab as WorkflowTab}
        views={views}
        outputKind={outputKind}
        runError={runError}
        renderStageResult={renderStageResult}
      />
    </div>
  )
}

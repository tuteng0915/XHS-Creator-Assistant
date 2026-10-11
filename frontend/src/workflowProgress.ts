export type WorkflowProgress = {
  phase: 'overview' | 'reading' | 'synthesis'
  status: 'running' | 'completed'
  completed: number
  total: number
  preview?: string
}

export function parseWorkflowProgress(value: unknown): WorkflowProgress | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const item = value as Record<string, unknown>
  if (!['overview', 'reading', 'synthesis'].includes(String(item.phase))
      || !['running', 'completed'].includes(String(item.status))
      || !Number.isInteger(item.completed) || !Number.isInteger(item.total)
      || Number(item.completed) < 0 || Number(item.total) < 1
      || Number(item.completed) > Number(item.total)) return undefined
  return {
    phase: item.phase as WorkflowProgress['phase'],
    status: item.status as WorkflowProgress['status'],
    completed: Number(item.completed), total: Number(item.total),
    ...(typeof item.preview === 'string' ? {preview: item.preview} : {}),
  }
}

export function workflowProgressLabel(progress: WorkflowProgress): string {
  const labels = {overview: '整体阅读', reading: '逐篇细读', synthesis: '汇总报告'}
  return `${labels[progress.phase]} · ${progress.completed}/${progress.total}`
}

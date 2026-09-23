import type { ReactNode } from 'react'

const LABELS: Record<string, string> = {
  topicTitle: '选题标题', refinedAngle: '切入角度', targetReader: '目标读者', readerPain: '读者痛点',
  contentPromise: '内容价值', corePoint: '核心观点', formatRecommendation: '推荐形式',
  openingHook: '开头', argumentPath: '论述顺序', materialNeeds: '待补充材料',
  titleDirections: '标题方向', risks: '注意事项', revisionSuggestions: '修改建议',
  title: '标题', topic: '选题', angle: '切入角度', hook: '开头', opening: '开头',
  body: '正文', content: '内容', outline: '大纲', sections: '段落', summary: '摘要',
  conclusion: '结尾', ending: '结尾', cta: '互动引导', audience: '目标受众',
  targetAudience: '目标受众', audiencePainPoint: '受众痛点', coreMessage: '核心观点',
  keyMessage: '核心观点', mainMessage: '核心观点', tone: '语气', voice: '表达风格',
  suggestedTitle: '建议标题', suggestedTitles: '建议标题', visualDirection: '视觉方向',
  keyPoints: '要点', key_points: '要点', rationale: '理由', format: '形式',
  evidence: '支撑材料', structure: '结构', creativeBrief: '创作方案', brief: '创作方案',
}

export function CreatorDraftEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  let parsed: Record<string, unknown>
  try { parsed = JSON.parse(value) } catch { return <p role="alert">当前内容无法编辑，请重新打开这份创作方案。</p> }
  function update(path: (string | number)[], text: string) {
    const next = structuredClone(parsed)
    let node: Record<string | number, unknown> = next
    for (const key of path.slice(0, -1)) node = node[key] as Record<string | number, unknown>
    node[path[path.length - 1]] = text
    onChange(JSON.stringify(next, null, 2))
  }
  function fields(node: unknown, path: (string | number)[] = []): ReactNode {
    if (typeof node === 'string') {
      const key = String(path[path.length - 1])
      const label = LABELS[key] || (Number.isNaN(Number(key)) ? key : `${LABELS[String(path[path.length - 2])] || '内容'} ${Number(key) + 1}`)
      return <label key={path.join('.')} className="creator-draft-field">{label}<textarea rows={Math.min(8, Math.max(2, node.split('\n').length + 1))} value={node} onChange={(event) => update(path, event.target.value)} /></label>
    }
    if (Array.isArray(node)) return node.map((item, index) => fields(item, [...path, index]))
    if (node && typeof node === 'object') return Object.entries(node).map(([key, item]) => fields(item, [...path, key]))
    return null
  }
  return <div className="creator-draft-editor">{fields(parsed)}</div>
}

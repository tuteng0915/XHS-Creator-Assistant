import { InfoHint } from './InfoHint'
import './OracleNotice.css'

/** Keep provenance available without adding a label or banner to the report. */
export function OracleNotice({ label = '记录来源说明' }: { label?: string }) {
  return <InfoHint label={label}>基于本账号已保存笔记人工编排，未调用模型。</InfoHint>
}

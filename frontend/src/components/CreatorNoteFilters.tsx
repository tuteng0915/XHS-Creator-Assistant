import type { CreatorNoteRange, CreatorNoteSort } from '../creatorNotes'
import { InfoHint } from './InfoHint'
import './CreatorNoteFilters.css'

export function CreatorNoteFilters({range, sort, onRangeChange, onSortChange, limit, onLimitChange}: {
  range: CreatorNoteRange; sort: CreatorNoteSort;
  onRangeChange: (range: CreatorNoteRange) => void; onSortChange: (sort: CreatorNoteSort) => void;
  limit?: number; onLimitChange?: (limit: number) => void;
}) {
  return <div className="creator-note-filters">
    <label>查看范围<select value={range} onChange={event => onRangeChange(event.target.value as CreatorNoteRange)}>
      <option value="all">全部已导入</option><option value="last_7_days">最近 7 天</option>
      <option value="last_30_days">最近 30 天</option><option value="last_90_days">最近 90 天</option>
    </select></label>
    <label>排序<select value={sort} onChange={event => onSortChange(event.target.value as CreatorNoteSort)}>
      <option value="newest">最新发布</option><option value="liked">点赞最高</option><option value="engagement">互动最高</option>
    </select></label>
    {onLimitChange && <label>显示<select value={limit ?? 0} onChange={event => onLimitChange(Number(event.target.value))}>
      <option value="0">全部</option><option value="10">前 10 篇</option><option value="20">前 20 篇</option><option value="50">前 50 篇</option>
    </select></label>}
    <InfoHint label="笔记筛选说明">仅比较已导入笔记。互动按已记录的赞、藏、评、分享相加；缺失不算零，全部未知的笔记不进入前 N 排名，但仍可手选。时间范围不包含未知或未来日期。改变查看范围不会移除已选笔记。</InfoHint>
  </div>
}

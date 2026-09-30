export function PendingSuggestions({ value }: { value: unknown }) {
  const items = Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())) : []
  if (!items.length) return null
  return <details className="asset-json-details" open>
    <summary>待确认建议</summary>
    <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
  </details>
}

/** Stable abstract portraits: visual identity, not demographic inference. */
export function ReaderAvatar({id, name, size = 36}: {id: string; name: string; size?: number}) {
  let seed = 2166136261
  for (const char of id) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619) >>> 0
  const colors = ['#d9ede8', '#dde7fb', '#f7e3c9', '#eadff3', '#f5dfe3', '#dcecf1']
  const ink = ['#245c50', '#315aac', '#965c25', '#78549c', '#994c61', '#326a80']
  const variant = seed % colors.length
  return <svg className="reader-avatar" width={size} height={size} viewBox="0 0 48 48" role="img" aria-label={`${name}的头像`} style={{flexShrink: 0, borderRadius: 14}}>
    <rect width="48" height="48" rx="14" fill={colors[variant]} />
    <path d={seed % 2 ? 'M7 48Q8 29 24 30Q40 29 41 48' : 'M5 48Q12 31 24 33Q36 31 43 48'} fill={ink[variant]} opacity=".82" />
    <rect x="13" y="9" width="22" height="25" rx={seed % 3 === 0 ? 7 : 11} fill="#fffaf0" />
    <path d={seed % 2 ? 'M12 21Q10 7 24 7Q38 7 36 18Q27 19 21 13Q18 19 12 21' : 'M12 18Q13 6 26 8Q36 9 36 20L31 17L28 14L17 17Z'} fill={ink[variant]} />
    <circle cx="19.5" cy="22" r="1.3" fill="#364152" /><circle cx="28.5" cy="22" r="1.3" fill="#364152" />
    {seed % 3 === 1 && <path d="M15 21h9m0 0h9m-9 0v2m-9-2v4h8v-4m2 0v4h8v-4" fill="none" stroke={ink[variant]} strokeWidth="1" />}
    <path d={seed % 2 ? 'M21 28q3 3 6 0' : 'M21 28h6'} fill="none" stroke="#7e5860" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}

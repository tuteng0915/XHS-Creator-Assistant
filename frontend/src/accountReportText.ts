// Compare written statements only. Do not infer synonyms or rewrite saved text.
export const accountStatementKey = (value: string): string => value.replace(/\s+/g, ' ').trim().replace(/[。.]$/u, '')

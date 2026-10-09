export const ORACLE_SHOWCASE_ORIGIN = 'oracle_showcase'

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {}
}

export function isOracleShowcase(value: unknown): boolean {
  const record = object(value)
  return [record.origin, object(record.modelMetadata).origin,
    object(record.inputSnapshot).origin, object(record.result).origin]
    .some(origin => origin === ORACLE_SHOWCASE_ORIGIN)
}

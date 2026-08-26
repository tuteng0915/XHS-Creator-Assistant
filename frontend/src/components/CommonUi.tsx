import type { ReactNode } from 'react'

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-card">{children}</div>
}

export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null
  return <div className="error-banner">⚠ {message}</div>
}

export function JsonPreview({ value }: { value: unknown }) {
  return <pre className="json-preview">{JSON.stringify(value, null, 2)}</pre>
}


import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'

import './App.css'
import './Button.css'

// Curated examples belong to existing workspace histories, like other saved results.
const Entry = lazy(() => import('./App'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p role="status">正在打开工作区…</p>}><Entry /></Suspense>
  </StrictMode>,
)

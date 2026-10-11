import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../App.css'
import '../Button.css'
import { installPreviewApi } from './installPreviewApi'

installPreviewApi()
// Install network isolation before importing any rendered component.
const { ReadmePreview } = await import('./ReadmePreview')
createRoot(document.getElementById('root')!).render(<StrictMode><ReadmePreview /></StrictMode>)

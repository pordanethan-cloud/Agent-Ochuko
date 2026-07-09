import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App.tsx'

// Apply service-worker updates only while the tab is hidden so an in-progress
// chat is never interrupted by a mid-session page reload.
const updateSW = registerSW({
  onNeedRefresh() {
    const applyWhenHidden = () => {
      if (document.visibilityState === 'hidden') {
        document.removeEventListener('visibilitychange', applyWhenHidden)
        updateSW(true)
      }
    }
    document.addEventListener('visibilitychange', applyWhenHidden)
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

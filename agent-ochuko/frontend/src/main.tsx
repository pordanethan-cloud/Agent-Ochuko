import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App.tsx'

// Service-worker update flow (mobile users cannot hard-refresh):
// 1. On a cold start (<4s after load) apply a pending update immediately —
//    there is no in-progress chat to interrupt yet.
// 2. Otherwise apply as soon as the tab is hidden (user switches apps) so an
//    in-progress conversation is never reloaded mid-stream.
function applyUpdate(sw: { (reload?: boolean): Promise<void> }) {
  sw(true)
}

const updateSW = registerSW({
  onNeedRefresh() {
    // Cold start: take the new version right away.
    if (performance.now() < 4000) {
      applyUpdate(updateSW)
      return
    }
    const applyWhenHidden = () => {
      if (document.visibilityState === 'hidden') {
        document.removeEventListener('visibilitychange', applyWhenHidden)
        applyUpdate(updateSW)
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

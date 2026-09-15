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

// ── Stale-chunk recovery ─────────────────────────────────────────────────────
// After a deploy, a cached index.html can reference hashed JS/CSS chunks that
// no longer exist. The module load fails and the app renders NOTHING (blank
// screen) with no recovery path — a classic mobile "app went blank" bug.
// Detect it and hard-reload once so the fresh index.html + assets load.
const CHUNK_RELOAD_FLAG = 'ochuko_chunk_reload'
function recoverFromStaleChunk(detail: string) {
  if (sessionStorage.getItem(CHUNK_RELOAD_FLAG)) return // max one auto-reload per session
  sessionStorage.setItem(CHUNK_RELOAD_FLAG, '1')
  console.warn('[Boot] Stale chunk detected, reloading:', detail)
  window.location.reload()
}
window.addEventListener('error', (e) => {
  const msg = (e as ErrorEvent)?.message || ''
  const tgt = e.target as { src?: string } | null
  const failedAsset = tgt && typeof tgt.src === 'string' ? tgt.src : ''
  const staleChunk =
    /dynamically imported module|Importing a module script failed|ChunkLoadError|error loading dynamically/i.test(
      msg || failedAsset,
    ) || (failedAsset && /\.(js|mjs|css)($|\?)/.test(failedAsset))
  if (staleChunk) recoverFromStaleChunk(msg || failedAsset)
}, true) // capture phase — resource-load errors do not bubble
window.addEventListener('unhandledrejection', (e) => {
  const msg = String(e?.reason?.message || e?.reason || '')
  if (/dynamically imported module|Importing a module script failed|ChunkLoadError/i.test(msg)) {
    recoverFromStaleChunk(msg)
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

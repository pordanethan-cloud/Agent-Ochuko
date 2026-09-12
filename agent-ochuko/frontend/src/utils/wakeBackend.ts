// wakeBackend.ts — zero-cost cold-start handling for scale-to-zero deployments.
// With the backend scaled to 0 replicas (minReplicas=0, no idle compute cost),
// the first request after inactivity hits a cold start (~10-30s) where the edge
// refuses connections. This module fires a lightweight GET /health ping on app
// mount with retry/backoff so the container is warm before the user sends a
// message. The ping is the request that wakes the container anyway — there is
// no cost beyond the single request itself.
const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

let wakePromise: Promise<boolean> | null = null

export function wakeBackend(maxAttempts = 8, initialDelayMs = 2000): Promise<boolean> {
  // De-dupe: one wake cycle per page load, shared across all callers.
  if (wakePromise) return wakePromise
  wakePromise = (async () => {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const controller = new AbortController()
        const timer = setTimeout(() => controller.abort(), 10000)
        const res = await fetch(`${API_BASE}/health`, { signal: controller.signal })
        clearTimeout(timer)
        if (res.ok) return true
      } catch {
        // Connection refused / timeout — cold start in progress, retry.
      }
      // Exponential backoff: 2s, 4s, 8s, 16s, ... capped at 20s (~90s total).
      const delay = Math.min(initialDelayMs * 2 ** (attempt - 1), 20000)
      await new Promise((r) => setTimeout(r, delay))
    }
    return false
  })()
  return wakePromise
}

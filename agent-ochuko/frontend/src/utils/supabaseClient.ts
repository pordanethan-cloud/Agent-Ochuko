import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  console.error("Missing Supabase configuration. Check frontend .env file.")
}

export const supabase = createClient(supabaseUrl || '', supabaseAnonKey || '', {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true,
  }
})

/**
 * Helper to check if a JWT is valid and not expired (with 30s buffer).
 */
const isTokenValid = (token: string): boolean => {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return false
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    if (!payload.exp) return true
    const now = Math.floor(Date.now() / 1000)
    return payload.exp > (now + 30)
  } catch (e) {
    return false
  }
}

/**
 * Robust token getter. The LIVE Supabase session is the authoritative source
 * of the current identity; persisted copies are consulted only as fallbacks.
 *
 * Ordering rationale: after a mid-session account switch (multi-tab session
 * sync, OAuth callback, etc.), a previously cached `supabase_token` may belong
 * to a *different* user than the active session. Preferring the live session
 * prevents API calls from silently carrying a foreign identity, which the
 * backend rejects with 403 on ownership-checked endpoints.
 */
export const getEffectiveToken = async (): Promise<string | null> => {
  // 1. Live Supabase session (source of truth for the current identity)
  try {
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token && isTokenValid(session.access_token)) {
      // Keep the mirror copy in sync so fallback #3 stays usable if the live session is lost
      localStorage.setItem('supabase_token', session.access_token)
      return session.access_token
    }
  } catch (e) {
    console.warn('[SupabaseClient] getSession error:', e)
  }

  // 2. Raw Supabase SDK storage key (recovers from corrupted in-memory client state)
  try {
    if (supabaseUrl) {
      const host = new URL(supabaseUrl).hostname.split('.')[0]
      const storageKey = `sb-${host}-auth-token`
      const raw = localStorage.getItem(storageKey)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed?.access_token && isTokenValid(parsed.access_token)) {
          localStorage.setItem('supabase_token', parsed.access_token)
          return parsed.access_token
        }
      }
    }
  } catch (e) {}

  // 3. Mirror copy written by this helper / AuthCallback (last resort)
  const directToken = localStorage.getItem('supabase_token')
  if (directToken) {
    if (isTokenValid(directToken)) {
      return directToken
    }
    // Purge stale expired token
    localStorage.removeItem('supabase_token')
  }

  return null
}

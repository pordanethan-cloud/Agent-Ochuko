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
 * Robust token getter that handles clock skew, validates expiration, and falls back across storage layers.
 */
export const getEffectiveToken = async (): Promise<string | null> => {
  // 1. Direct local storage token check with expiration validation
  const directToken = localStorage.getItem('supabase_token')
  if (directToken) {
    if (isTokenValid(directToken)) {
      return directToken
    } else {
      // Purge stale expired token
      localStorage.removeItem('supabase_token')
    }
  }

  // 2. Standard Supabase session check
  try {
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token && isTokenValid(session.access_token)) {
      localStorage.setItem('supabase_token', session.access_token)
      return session.access_token
    }
  } catch (e) {
    console.warn('[SupabaseClient] getSession error:', e)
  }

  // 3. Raw Supabase localStorage key check
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

  return null
}

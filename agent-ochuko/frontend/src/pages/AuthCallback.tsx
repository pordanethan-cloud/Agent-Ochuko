import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../utils/supabaseClient'

export const AuthCallback: React.FC = () => {
  const navigate = useNavigate()
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [errorDesc, setErrorDesc] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const hashParams = new URLSearchParams(window.location.hash.substring(1))

    const err = params.get('error') || hashParams.get('error')
    const desc = params.get('error_description') || hashParams.get('error_description')

    if (err) {
      setErrorMsg(err)
      setErrorDesc(desc)
      return
    }

    let redirected = false

    const doRedirect = () => {
      if (redirected) return
      redirected = true
      // Clean hash & search params so back button won't re-process OAuth callback
      window.history.replaceState({}, document.title, window.location.pathname)
      navigate('/', { replace: true })
    }

    const access_token = hashParams.get('access_token') || params.get('access_token')
    const refresh_token = hashParams.get('refresh_token') || params.get('refresh_token')
    const expires_in = hashParams.get('expires_in') || params.get('expires_in') || '3600'

    if (access_token) {
      // 1. Persist direct access token to avoid clock skew blocking
      localStorage.setItem('supabase_token', access_token)

      // 2. Decode payload & populate Supabase SDK storage key directly
      try {
        const parts = access_token.split('.')
        if (parts.length === 3) {
          const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
          const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
          if (supabaseUrl) {
            const host = new URL(supabaseUrl).hostname.split('.')[0]
            const storageKey = `sb-${host}-auth-token`

            const sessionObj = {
              access_token,
              refresh_token: refresh_token || '',
              token_type: 'bearer',
              expires_in: parseInt(expires_in, 10),
              expires_at: Math.floor(Date.now() / 1000) + parseInt(expires_in, 10),
              user: {
                id: payload.sub,
                aud: payload.aud || 'authenticated',
                role: payload.role || 'authenticated',
                email: payload.email || '',
                email_confirmed_at: new Date().toISOString(),
                phone: payload.phone || '',
                confirmed_at: new Date().toISOString(),
                last_sign_in_at: new Date().toISOString(),
                app_metadata: payload.app_metadata || {},
                user_metadata: payload.user_metadata || {},
                identities: [],
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
              }
            }
            localStorage.setItem(storageKey, JSON.stringify(sessionObj))
          }
        }
      } catch (e) {
        console.warn('[AuthCallback] Manual session formatting skipped:', e)
      }

      // 3. Update Supabase SDK memory state if refresh token is available
      if (refresh_token) {
        supabase.auth.setSession({ access_token, refresh_token }).finally(() => {
          doRedirect()
        })
      } else {
        doRedirect()
      }
      return
    }

    // Fallback: check existing session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) doRedirect()
    })

    const fallback = setTimeout(() => {
      if (!redirected) {
        navigate('/login', { replace: true })
      }
    }, 4000)

    return () => {
      clearTimeout(fallback)
    }
  }, [navigate])

  if (errorMsg) {
    return (
      <div className="min-h-screen bg-brand-bg flex flex-col items-center justify-center text-brand-text p-6">
        <div className="w-full max-w-md bg-red-950/40 border border-red-900/50 rounded-2xl p-6 text-center space-y-4">
          <div className="w-12 h-12 bg-red-900/30 border border-red-800/40 flex items-center justify-center rounded-xl mx-auto text-red-400 font-bold text-lg">
            !
          </div>
          <h2 className="text-lg font-medium text-red-400">Authentication Failed</h2>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-red-300">Error: {errorMsg}</p>
            {errorDesc && <p className="text-xs text-red-400/90 leading-relaxed">{errorDesc}</p>}
          </div>
          <button
            onClick={() => navigate('/login')}
            className="mt-4 px-4 py-2 bg-brand-text text-brand-bg text-xs font-medium rounded-lg hover:bg-brand-text/90 transition duration-150"
          >
            Back to Login
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-bg flex flex-col items-center justify-center text-brand-text">
      <div className="w-8 h-8 border-2 border-brand-accent/50 border-t-brand-accent rounded-full animate-spin mb-4" />
      <span className="text-sm text-brand-muted font-light tracking-wide">Establishing secure session...</span>
    </div>
  )
}

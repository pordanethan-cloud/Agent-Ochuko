import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../utils/supabaseClient'

export const AuthCallback: React.FC = () => {
  const navigate = useNavigate()
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [errorDesc, setErrorDesc] = useState<string | null>(null)

  useEffect(() => {
    // Parse query and hash parameters for errors
    const params = new URLSearchParams(window.location.search)
    const hashParams = new URLSearchParams(window.location.hash.substring(1))

    const err = params.get('error') || hashParams.get('error')
    const desc = params.get('error_description') || hashParams.get('error_description')

    if (err) {
      setErrorMsg(err)
      setErrorDesc(desc)
      return // Stop automatic redirect so the user can see the error
    }

    // Listen for auth state change which occurs after Supabase parses the session from the URL hash/query
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        navigate('/')
      } else {
        // Fallback if session couldn't be established after callback
        const timer = setTimeout(() => {
          navigate('/login')
        }, 3000)
        return () => clearTimeout(timer)
      }
    })

    return () => {
      subscription.unsubscribe()
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


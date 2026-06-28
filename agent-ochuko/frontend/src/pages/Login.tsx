import React, { useState } from 'react'
import { supabase } from '../utils/supabaseClient'
import { Shield, ArrowRight } from 'lucide-react'

export const Login: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleGoogleLogin = async () => {
    setLoading(true)
    setError(null)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          // Redirects back to the main domain of the client app
          redirectTo: `${window.location.origin}/auth/callback`
        }
      })
      if (error) throw error
    } catch (err: any) {
      setError(err.message || 'An error occurred during Google sign in.')
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen bg-brand-bg flex items-center justify-center px-4 overflow-hidden selection:bg-brand-accent/20">
      {/* Premium Warm Ambient Glow Background */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-brand-accent/5 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-md bg-brand-surface/60 backdrop-blur-xl border border-brand-border rounded-2xl p-8 shadow-2xl relative z-10 transition-all duration-300 hover:border-brand-border/80">
        
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center mb-10">
          <div className="w-14 h-14 flex items-center justify-center rounded-xl overflow-hidden border border-brand-border/60 mb-6 shadow-xl">
            <img src="/favicon.png" alt="Agent Ochuko Logo" className="w-full h-full object-cover" />
          </div>
          <h1 className="text-3xl font-medium tracking-tight text-brand-text mb-2 font-sans">
            Agent Ochuko
          </h1>
          <p className="text-sm text-brand-muted max-w-[280px] leading-relaxed">
            Sign in to access your secure private cognitive assistant.
          </p>
        </div>

        {/* Action Area */}
        <div className="space-y-4">
          <button
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full h-12 bg-brand-text text-brand-bg font-medium rounded-xl flex items-center justify-center gap-3 transition-all duration-200 hover:bg-brand-text/90 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none group shadow-lg"
          >
            {loading ? (
              <span className="w-5 h-5 border-2 border-brand-bg/30 border-t-brand-bg rounded-full animate-spin" />
            ) : (
              <>
                {/* SVG for Google logo */}
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path
                    fill="currentColor"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="currentColor"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="currentColor"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="currentColor"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                <span>Continue with Google</span>
                <ArrowRight className="w-4 h-4 opacity-0 -translate-x-2 transition-all duration-200 group-hover:opacity-100 group-hover:translate-x-0" />
              </>
            )}
          </button>

          {error && (
            <div className="p-3 bg-red-950/40 border border-red-900/50 rounded-lg text-xs text-red-400 text-center leading-relaxed">
              {error}
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="mt-8 pt-6 border-t border-brand-border/60 flex items-center justify-center gap-2 text-xs text-brand-muted font-light">
          <Shield className="w-3.5 h-3.5" />
          <span>Secured via Supabase Auth & Row-Level Security</span>
        </div>

      </div>
    </div>
  )
}

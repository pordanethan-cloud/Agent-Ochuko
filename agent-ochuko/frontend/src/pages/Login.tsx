import React, { useState } from 'react'
import { supabase } from '../utils/supabaseClient'
import { Shield, ArrowRight, Mail, Lock, User } from 'lucide-react'

export const Login: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Form states
  const [isSignUp, setIsSignUp] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [preferredName, setPreferredName] = useState('')



  const handleGoogleLogin = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          queryParams: {
            prompt: 'select_account',   // always show account chooser after sign-out
          }
        }
      })
      if (error) throw error
    } catch (err: any) {
      setError(err.message || 'An error occurred during Google sign in.')
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setSuccess(null)

    const cleanEmail = email.trim()
    const cleanPassword = password.trim()
    const cleanName = preferredName.trim()

    if (!cleanEmail || !cleanPassword) {
      setError('Please fill in all required fields.')
      setLoading(false)
      return
    }

    try {
      if (isSignUp) {
        if (!cleanName) {
          setError('Preferred name is required for registration.')
          setLoading(false)
          return
        }

        const { data, error: signUpError } = await supabase.auth.signUp({
          email: cleanEmail,
          password: cleanPassword,
          options: {
            data: {
              preferred_name: cleanName,
            }
          }
        })

        if (signUpError) throw signUpError

        // Check if confirmation is required
        if (data.user && data.session === null) {
          setSuccess('Account created! Please check your email inbox to verify your account.')
        } else {
          setSuccess('Signup successful! Loading cognitive assistant...')
          window.location.reload()
        }
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email: cleanEmail,
          password: cleanPassword
        })

        if (signInError) throw signInError
        setSuccess('Authentication successful! Loading workspace...')
        window.location.reload()
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during authentication.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen bg-brand-bg flex flex-col items-center justify-center px-4 overflow-hidden selection:bg-brand-accent/20">
      
      {/* Premium Warm Ambient Glow Background */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand-accent/5 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute top-12 right-12 w-96 h-96 bg-[#c5a880]/3 rounded-full blur-[90px] pointer-events-none" />

      <div className="w-full max-w-md bg-brand-surface/60 backdrop-blur-2xl border border-brand-border rounded-2xl p-8 shadow-2xl relative z-10 transition-all duration-300 hover:border-brand-border/80">
        
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-14 h-14 flex items-center justify-center rounded-xl overflow-hidden border border-brand-border/60 mb-5 shadow-xl bg-brand-card">
            <img src="/favicon.png" alt="Agent Ochuko Logo" className="w-full h-full object-cover" />
          </div>
          <h1 className="text-3xl font-medium tracking-tight text-brand-text mb-2 font-sans">
            Agent Ochuko
          </h1>
          <p className="text-xs text-brand-muted max-w-[280px] leading-relaxed">
            {isSignUp 
              ? 'Register to create your secure private cognitive assistant.' 
              : 'Sign in to access your secure private cognitive assistant.'}
          </p>
        </div>

        {/* Credentials Form */}
        <form onSubmit={handleSubmit} className="space-y-4 mb-6">
          {isSignUp && (
            <div className="space-y-1.5">
              <label className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold px-1">
                Preferred Name
              </label>
              <div className="relative flex items-center">
                <User className="absolute left-3 w-4 h-4 text-brand-muted/70" />
                <input
                  type="text"
                  placeholder="How should Ochuko address you?"
                  value={preferredName}
                  onChange={(e) => setPreferredName(e.target.value)}
                  className="w-full h-11 pl-10 pr-4 bg-brand-bg/80 border border-brand-border rounded-xl text-sm text-brand-text placeholder:text-brand-muted/40 focus:outline-none focus:border-brand-accent/50 transition-all"
                  required={isSignUp}
                />
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold px-1">
              Email Address
            </label>
            <div className="relative flex items-center">
              <Mail className="absolute left-3 w-4 h-4 text-brand-muted/70" />
              <input
                type="email"
                placeholder="you@domain.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-11 pl-10 pr-4 bg-brand-bg/80 border border-brand-border rounded-xl text-sm text-brand-text placeholder:text-brand-muted/40 focus:outline-none focus:border-brand-accent/50 transition-all"
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] uppercase tracking-wider text-brand-muted font-semibold px-1">
              Password
            </label>
            <div className="relative flex items-center">
              <Lock className="absolute left-3 w-4 h-4 text-brand-muted/70" />
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-11 pl-10 pr-4 bg-brand-bg/80 border border-brand-border rounded-xl text-sm text-brand-text placeholder:text-brand-muted/40 focus:outline-none focus:border-brand-accent/50 transition-all"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full h-11 bg-brand-text text-brand-bg font-semibold rounded-xl flex items-center justify-center gap-2 transition-all duration-200 hover:bg-brand-text/90 active:scale-[0.99] disabled:opacity-50 disabled:pointer-events-none shadow-md mt-6"
          >
            {loading ? (
              <span className="w-5 h-5 border-2 border-brand-bg/30 border-t-brand-bg rounded-full animate-spin" />
            ) : (
              <>
                <span>{isSignUp ? 'Create Account' : 'Sign In'}</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Separator */}
        <div className="relative flex py-4 items-center">
          <div className="flex-grow border-t border-brand-border/60"></div>
          <span className="flex-shrink mx-4 text-[10px] text-brand-muted/50 uppercase tracking-widest font-semibold">Or continue with</span>
          <div className="flex-grow border-t border-brand-border/60"></div>
        </div>

        {/* Action Area: Warm-themed Google button */}
        <div className="flex flex-col items-center w-full gap-4 mt-2">
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full h-11 bg-[#161412] hover:bg-[#1f1b19] border border-[#2d2722] hover:border-[#c5a880]/30 text-[#f5f2eb] font-semibold rounded-xl flex items-center justify-center gap-3 transition-all duration-200 active:scale-[0.99] disabled:opacity-50 disabled:pointer-events-none shadow-lg shadow-black/40"
            title="Sign in with Google"
          >
            {loading ? (
              <span className="w-5 h-5 border-2 border-[#f5f2eb]/30 border-t-[#f5f2eb] rounded-full animate-spin" />
            ) : (
              <>
                {/* SVG for Google logo */}
                <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
                  <path
                    fill="#EA4335"
                    d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.213-5.26 4.758l3.528 2.733c2.062-1.9 3.245-4.702 3.245-8.02 0-.61-.052-1.226-.157-1.833z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09a7.12 7.12 0 0 1-.35-2.09c0-.73.13-1.43.35-2.09V7.06H2.18A11.96 11.96 0 0 0 1 12c0 1.8.4 3.51 1.18 4.94l3.66-2.85z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c3.24 0 5.97-1.07 7.96-2.91l-3.528-2.733c-1.127.754-2.564 1.203-4.432 1.203-3.41 0-6.3-2.3-7.33-5.4H1.18v2.85C3.18 20.15 7.27 23 12 23z"
                  />
                  <path
                    fill="#4285F4"
                    d="M4.67 8.16C5.7 5.06 8.59 2.76 12 2.76c1.8 0 3.42.62 4.7 1.83l3.528-3.528C17.97.87 15.22 0 12 0 7.27 0 3.18 2.85 1.18 6.94l3.49 1.22z"
                  />
                </svg>
                <span>Continue with Google</span>
              </>
            )}
          </button>

          {/* Toggle form type */}
          <p className="text-center text-xs text-brand-muted font-normal mt-1">
            {isSignUp ? 'Already have an account? ' : "Don't have an account? "}
            <button
              type="button"
              onClick={() => {
                setIsSignUp(!isSignUp)
                setError(null)
                setSuccess(null)
              }}
              className="text-brand-text hover:text-brand-text/80 font-bold underline transition-colors"
            >
              {isSignUp ? 'Sign In' : 'Sign Up'}
            </button>
          </p>

          {error && (
            <div className="w-full p-3 bg-red-950/40 border border-red-900/50 rounded-xl text-xs text-red-400 text-center leading-relaxed">
              {error}
            </div>
          )}

          {success && (
            <div className="w-full p-3 bg-emerald-950/40 border border-emerald-900/50 rounded-xl text-xs text-emerald-400 text-center leading-relaxed">
              {success}
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="mt-8 pt-5 border-t border-brand-border/60 flex items-center justify-center gap-2 text-[10px] text-brand-muted/70 font-semibold tracking-wide">
          <Shield className="w-3.5 h-3.5 text-brand-muted/60" />
          <span>Secured via Supabase Auth & Row-Level Security</span>
        </div>

      </div>

    </div>
  )
}

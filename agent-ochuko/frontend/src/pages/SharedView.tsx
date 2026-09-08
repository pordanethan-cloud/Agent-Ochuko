import React, { useState, useEffect, useMemo } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { Loader2, Download, ArrowRight, Brain, X, GitFork, LogIn, Sparkles } from 'lucide-react'
import { renderRichContent, renderMarkdown, useKaTeX } from './Dashboard'
import { getEffectiveToken } from '../utils/supabaseClient'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

interface Message {
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}

interface SharedConvo {
  title: string
  created_at: string
  messages: Message[]
}

export const SharedView: React.FC = () => {
  const { token: routeToken } = useParams<{ token?: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // Support both /shared/:token and /shared/?token=:token
  const token = routeToken || searchParams.get('token') || ''

  const [convo, setConvo] = useState<SharedConvo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null)
  const [isForking, setIsForking] = useState(false)
  const [forkError, setForkError] = useState<string | null>(null)

  const hasLatex = useMemo(() => convo?.messages.some(m => m.content.includes('$')) || false, [convo])
  useKaTeX(hasLatex)

  // Check auth session
  useEffect(() => {
    let isMounted = true
    getEffectiveToken().then((authToken) => {
      if (isMounted) {
        setIsAuthenticated(!!authToken)
      }
    })
    return () => {
      isMounted = false
    }
  }, [])

  // Fetch shared conversation
  useEffect(() => {
    if (!token) {
      setError('No shared conversation link or token provided.')
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    fetch(`${API_BASE}/v1/shared/${token}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(
            res.status === 404
              ? 'Shared link not found or has been deactivated.'
              : 'Failed to load conversation.'
          )
        }
        return res.json()
      })
      .then((data) => {
        setConvo(data)
        setLoading(false)

        // Dynamic SEO: Title & Description
        document.title = `${data.title} | Shared on Agent Ochuko`
        const firstAssistantMsg =
          data.messages.find((m: Message) => m.role === 'assistant')?.content || ''
        const description = firstAssistantMsg.slice(0, 160) || `Shared conversation on Agent Ochuko`

        let metaDesc = document.querySelector('meta[name="description"]')
        if (!metaDesc) {
          metaDesc = document.createElement('meta')
          metaDesc.setAttribute('name', 'description')
          document.head.appendChild(metaDesc)
        }
        metaDesc.setAttribute('content', description)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [token])

  const handleContinue = async () => {
    const currentUrl = window.location.pathname + window.location.search

    // If unauthenticated or token expired, redirect to login with redirect back
    if (!isAuthenticated) {
      navigate(`/login?redirect=${encodeURIComponent(currentUrl)}`)
      return
    }

    if (!token) return

    setIsForking(true)
    setForkError(null)

    try {
      const authToken = await getEffectiveToken()
      if (!authToken) {
        navigate(`/login?redirect=${encodeURIComponent(currentUrl)}`)
        return
      }

      const res = await fetch(`${API_BASE}/v1/shared/${token}/fork`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to fork conversation.')
      }

      const data = await res.json()

      // Queue conversation ID for immediate hydration in Dashboard
      sessionStorage.setItem('pending_active_convo_id', data.conversation_id)
      localStorage.setItem('pending_active_convo_id', data.conversation_id)

      // Navigate to chat
      navigate('/')
    } catch (err: any) {
      console.error('Failed to continue conversation:', err)
      setForkError(err.message || 'Could not fork conversation.')
      setIsForking(false)
    }
  }

  const handleExportJSON = () => {
    if (!convo) return
    const dataStr = JSON.stringify(
      {
        title: convo.title,
        exported_at: new Date().toISOString(),
        messages: convo.messages.map((m) => ({ role: m.role, content: m.content })),
      },
      null,
      2
    )
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${convo.title.toLowerCase().replace(/[^a-z0-9]+/g, '_')}_export.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <div className="h-screen h-[100dvh] bg-[#08090a] flex flex-col items-center justify-center text-[#8e95a2]">
        <Loader2 className="w-8 h-8 text-[#ffffff] animate-spin mb-4" />
        <p className="text-sm font-medium tracking-wide">Loading conversation...</p>
      </div>
    )
  }

  if (error || !convo) {
    return (
      <div className="h-screen h-[100dvh] bg-[#08090a] flex flex-col items-center justify-center text-center p-6">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center text-red-500 mb-6 border border-red-500/20">
          <X className="w-8 h-8" />
        </div>
        <h1 className="text-lg font-bold text-brand-text mb-2">Failed to load shared chat</h1>
        <p className="text-sm text-[#8e95a2] max-w-md mb-6">{error || 'Unknown error occurred.'}</p>
        <a
          href="/"
          className="text-xs font-bold text-[#ffffff] hover:text-[#f3f4f6] flex items-center gap-1.5 transition-all"
        >
          Go to Home <ArrowRight className="w-3.5 h-3.5" />
        </a>
      </div>
    )
  }

  return (
    <div className="h-screen h-[100dvh] max-h-[100dvh] bg-[#08090a] flex flex-col text-brand-text overflow-hidden">
      {/* Top Navigation Bar */}
      <header className="bg-[#0b0c0e] border-b border-[#141618] h-14 px-4 sm:px-6 flex items-center justify-between shrink-0 select-none z-10">
        <div className="flex items-center gap-2 sm:gap-3">
          <a href="/" className="flex items-center gap-2 hover:opacity-80 transition">
            <Brain className="w-5 h-5 text-[#ffffff]" />
            <span className="text-[12px] font-black text-brand-text tracking-widest uppercase">
              Agent Ochuko
            </span>
          </a>
          <span className="hidden sm:inline-block text-[9px] font-bold text-[#8e95a2]/60 tracking-wider uppercase border-l border-[#1c1e22] pl-2.5 ml-1">
            Shared Conversation
          </span>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={handleExportJSON}
            title="Download conversation JSON"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#1e2025] hover:border-white/10 hover:bg-white/5 text-[11px] font-medium text-[#8e95a2] hover:text-brand-text transition duration-150"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export JSON</span>
          </button>

          <button
            onClick={handleContinue}
            disabled={isForking}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[11px] font-semibold transition duration-150 shadow-sm ${
              isAuthenticated
                ? 'bg-white text-black hover:bg-neutral-200 active:scale-[0.98]'
                : 'bg-white/10 text-white border border-white/20 hover:bg-white/15'
            } ${isForking ? 'opacity-70 cursor-not-allowed' : ''}`}
          >
            {isForking ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Importing...</span>
              </>
            ) : isAuthenticated ? (
              <>
                <GitFork className="w-3.5 h-3.5" />
                <span>Continue in Chat</span>
              </>
            ) : (
              <>
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign in to Continue</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Conversation Container with guaranteed vertical scrolling */}
      <main className="flex-1 min-h-0 overflow-y-auto py-8 sm:py-12 px-4 sm:px-8 md:px-12">
        <div className="max-w-3xl mx-auto space-y-8">
          {/* Title and Metadata Area */}
          <div className="border-b border-[#141618] pb-6 mb-8">
            <div className="flex items-center gap-2 text-brand-muted text-[11px] uppercase tracking-wider font-semibold mb-2">
              <Sparkles className="w-3.5 h-3.5 text-brand-accent" />
              <span>Shared Session</span>
            </div>
            <h1 className="text-xl md:text-2xl font-bold text-[#f0ece4] tracking-tight mb-2">
              {convo.title}
            </h1>
            <p className="text-[10px] text-[#8e95a2]/60 font-medium uppercase tracking-wider">
              Shared on{' '}
              {new Date(convo.created_at).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>
          </div>

          {/* Messages Loop */}
          {convo.messages.map((msg, i) => (
            <div
              key={i}
              className={`flex w-full gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[88%] md:max-w-[80%] rounded-2xl px-5 py-4 text-[13px] leading-relaxed select-text ${
                  msg.role === 'user'
                    ? 'bg-[#ffffff]/10 text-brand-text border border-[#ffffff]/20 font-medium'
                    : 'bg-[#0d0f11] text-brand-text border border-[#141618]'
                }`}
              >
                {renderRichContent(msg.content, renderMarkdown, false)}
              </div>
            </div>
          ))}

          {/* Bottom Interactive Continuation Card */}
          <div className="mt-12 pt-8 border-t border-[#141618]">
            <div className="bg-[#0b0c0e] border border-[#1c1e22] rounded-2xl p-6 sm:p-8 flex flex-col sm:flex-row items-center justify-between gap-6 shadow-xl">
              <div className="space-y-1.5 text-center sm:text-left">
                <h2 className="text-sm font-semibold text-white flex items-center justify-center sm:justify-start gap-2">
                  <GitFork className="w-4 h-4 text-[#ffffff]" />
                  <span>Continue this conversation</span>
                </h2>
                <p className="text-xs text-[#8e95a2] max-w-md leading-relaxed">
                  Fork this discussion directly into your Agent Ochuko workspace to ask questions, explore insights, and keep chatting.
                </p>
                {forkError && (
                  <p className="text-xs text-red-400 mt-1">{forkError}</p>
                )}
              </div>

              <button
                onClick={handleContinue}
                disabled={isForking}
                className={`shrink-0 w-full sm:w-auto px-5 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition duration-150 ${
                  isAuthenticated
                    ? 'bg-white text-black hover:bg-neutral-200 shadow-md active:scale-95'
                    : 'bg-white/10 hover:bg-white/15 text-white border border-white/20'
                } ${isForking ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                {isForking ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Importing to your account...</span>
                  </>
                ) : isAuthenticated ? (
                  <>
                    <span>Continue in Chat</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    <span>Sign in with Google to Continue</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

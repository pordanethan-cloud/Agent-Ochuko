import React, { useState, useEffect, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Download, ArrowRight, Brain, X } from 'lucide-react'
import { renderRichContent, renderMarkdown, useKaTeX } from './Dashboard'

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
  const { token } = useParams<{ token: string }>()
  const [convo, setConvo] = useState<SharedConvo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const hasLatex = useMemo(() => convo?.messages.some(m => m.content.includes('$')) || false, [convo])
  useKaTeX(hasLatex)

  useEffect(() => {
    if (!token) return
    setLoading(true)
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
      <div className="min-h-screen bg-[#08090a] flex flex-col items-center justify-center text-[#8e95a2]">
        <Loader2 className="w-8 h-8 text-[#ffffff] animate-spin mb-4" />
        <p className="text-sm font-medium tracking-wide">Loading conversation...</p>
      </div>
    )
  }

  if (error || !convo) {
    return (
      <div className="min-h-screen bg-[#08090a] flex flex-col items-center justify-center text-center p-6">
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
    <div className="min-h-screen bg-[#08090a] flex flex-col text-brand-text">
      {/* Top Watermark */}
      <div className="bg-[#0b0c0e] border-b border-[#141618] h-14 px-6 flex items-center justify-between shrink-0 select-none">
        <div className="flex items-center gap-2">
          <Brain className="w-5 h-5 text-[#ffffff]" />
          <span className="text-[12px] font-black text-brand-text tracking-widest uppercase">
            Agent Ochuko
          </span>
          <span className="text-[9px] font-bold text-[#8e95a2]/40 tracking-wider uppercase border-l border-[#1c1e22] pl-2.5 ml-1.5">
            Shared Conversation
          </span>
        </div>
        <button
          onClick={handleExportJSON}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-[#1e2025] hover:border-white/10 hover:bg-white/5 text-[11px] font-bold text-[#8e95a2] hover:text-brand-text transition duration-150"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export JSON</span>
        </button>
      </div>

      {/* Main Conversation Container */}
      <div className="flex-1 overflow-y-auto py-12 px-5 md:px-10">
        <div className="max-w-3xl mx-auto space-y-8">
          {/* Title Area */}
          <div className="border-b border-[#141618] pb-6 mb-8">
            <h1 className="text-xl md:text-2xl font-bold text-[#f0ece4] tracking-tight mb-2">
              {convo.title}
            </h1>
            <p className="text-[10px] text-[#8e95a2]/50 font-bold uppercase tracking-wider">
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
                className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-5 py-4 text-[13px] leading-relaxed select-text ${
                  msg.role === 'user'
                    ? 'bg-[#ffffff]/10 text-brand-text border border-[#ffffff]/20 font-medium'
                    : 'bg-[#0d0f11] text-brand-text border border-[#141618]'
                }`}
              >
                {renderRichContent(msg.content, renderMarkdown, false)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

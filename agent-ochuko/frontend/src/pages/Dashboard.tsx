import React, { useState, useEffect } from 'react'
import { supabase } from '../utils/supabaseClient'
import { LogOut, Send, Brain, Cpu, MessageSquare, Menu } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [mode, setMode] = useState<'think' | 'solve' | 'discuss'>('discuss')
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isSidebarHovered, setIsSidebarHovered] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        setUserEmail(user.email || 'User')
      }
    })
  }, [])

  const handleSignOut = async () => {
    await supabase.auth.signOut()
  }

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return

    const userMessage = input.trim()
    setInput('')
    const newMessages: Message[] = [...messages, { role: 'user', content: userMessage }]
    setMessages(newMessages)
    setIsStreaming(true)

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token

      const response = await fetch(`${API_BASE}/v1/responses/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          conversation_id: '00000000-0000-0000-0000-000000000000',
          mode: mode,
          messages: newMessages.map(m => ({ role: m.role, content: m.content }))
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No body reader available')

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      let accumulatedText = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim()
            if (dataStr === '[DONE]') continue
            try {
              const data = JSON.parse(dataStr)
              if (data.type === 'content_block_delta') {
                const text = data.delta.text
                accumulatedText += text
                setMessages((prev) => {
                  const updated = [...prev]
                  if (updated.length > 0) {
                    updated[updated.length - 1] = {
                      role: 'assistant',
                      content: accumulatedText
                    }
                  }
                  return updated
                })
              } else if (data.type === 'error') {
                // Re-throw so the outer catch can display the error
                throw new Error(`Agent error: ${data.error}`)
              }
            } catch (err: any) {
              // Only re-throw real errors (not JSON parse errors on partial chunks)
              if (err.message && !err.message.includes('JSON')) {
                throw err
              }
              // Otherwise: parse error on incomplete SSE chunk, ignore and continue
            }
          }
        }

      }
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <div className="flex h-screen bg-brand-bg text-brand-text font-sans antialiased overflow-hidden relative">
      
      {/* Invisible Hover Peek Detector on left edge */}
      <div 
        onMouseEnter={() => setIsSidebarHovered(true)}
        className="absolute left-0 top-0 w-3 h-full z-20"
      />

      {/* Backdrop overlay when sidebar is active */}
      {(isSidebarOpen || isSidebarHovered) && (
        <div 
          onClick={() => setIsSidebarOpen(false)}
          className="absolute inset-0 bg-black/60 backdrop-blur-[3px] z-20 transition-opacity duration-300"
        />
      )}

      {/* Slide-out Sidebar Drawer */}
      <aside 
        onMouseLeave={() => setIsSidebarHovered(false)}
        className={`absolute top-0 left-0 h-full w-64 bg-brand-surface/95 border-r border-brand-border/60 z-30 transition-transform duration-300 ease-out flex flex-col justify-between p-6 backdrop-blur-xl shadow-2xl ${
          isSidebarOpen || isSidebarHovered ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div>
          <div className="flex items-center gap-3 px-2 py-3 mb-6 border-b border-brand-border/45 pb-4">
            <div className="w-8 h-8 flex items-center justify-center rounded-lg overflow-hidden border border-brand-accent/30 bg-brand-bg shadow-inner">
              <img src="/favicon.png" alt="Agent Ochuko" className="w-full h-full object-cover" />
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-sm tracking-wide">Agent Ochuko</span>
              <span className="text-[10px] text-brand-accent font-medium tracking-wider uppercase">System active</span>
            </div>
          </div>

          <button
            onClick={() => {
              setMessages([])
              setIsSidebarOpen(false)
            }}
            className="w-full h-10 border border-brand-border bg-brand-bg/50 hover:bg-brand-bg text-brand-text hover:border-brand-accent/50 transition duration-150 rounded-lg text-xs font-semibold flex items-center justify-center gap-2"
          >
            New Session
          </button>
        </div>

        {/* User profile footer */}
        <div className="border-t border-brand-border/40 pt-4 space-y-3">
          <div className="flex items-center gap-3 px-2">
            <div className="w-8 h-8 bg-brand-bg border border-brand-border flex items-center justify-center rounded-full overflow-hidden">
              <img src="/favicon.png" alt="User" className="w-full h-full object-cover" />
            </div>
            <div className="flex flex-col truncate">
              <span className="text-[10px] text-brand-muted uppercase font-semibold">Logged In</span>
              <span className="text-xs text-brand-text truncate max-w-[140px] font-medium">{userEmail}</span>
            </div>
          </div>
          <button
            onClick={handleSignOut}
            className="w-full h-10 hover:bg-red-950/20 text-red-400 hover:text-red-300 transition duration-150 rounded-lg text-xs font-semibold flex items-center gap-3 px-3 border border-transparent hover:border-red-900/40"
          >
            <LogOut className="w-4 h-4" />
            <span>Terminate Session</span>
          </button>
        </div>
      </aside>

      {/* Main Chat Workspace */}
      <main className="flex-1 flex flex-col justify-between relative bg-brand-bg overflow-hidden z-10">
        
        {/* Top Header */}
        <header className="h-14 border-b border-brand-border/40 bg-brand-surface/30 backdrop-blur-md flex items-center justify-between px-6 z-10 relative">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              onMouseEnter={() => setIsSidebarHovered(true)}
              className="p-1.5 rounded-lg border border-brand-border bg-brand-surface/40 hover:bg-brand-surface text-brand-muted hover:text-brand-text hover:border-brand-accent/40 transition duration-150 active:scale-95 flex items-center justify-center"
              aria-label="Toggle Sidebar"
            >
              <Menu className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-3">
              <span className="font-semibold text-sm tracking-wide text-brand-text">Agent Ochuko</span>
              <div className="h-4 w-px bg-brand-border/60 hidden sm:block" />
              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-brand-accent/10 border border-brand-accent/20 text-brand-accent font-semibold hidden sm:inline-block">
                {mode} mode
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-accent opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-accent"></span>
            </span>
            <span className="text-[10px] font-semibold tracking-wider text-brand-muted uppercase">SYSTEM AUTH SYNCED</span>
          </div>
        </header>

        {/* Ambient background highlight */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[700px] h-[700px] bg-brand-accent/2 rounded-full blur-[160px] pointer-events-none" />

        {/* Chat History */}
        <div className="flex-1 overflow-y-auto p-6 md:p-12 space-y-6 relative z-10">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center space-y-8 mt-16 md:mt-24">
              <div className="w-16 h-16 bg-brand-surface border border-brand-border rounded-2xl flex items-center justify-center shadow-2xl overflow-hidden relative group">
                <div className="absolute inset-0 bg-brand-accent/5 opacity-0 group-hover:opacity-100 transition duration-300" />
                <img src="/favicon.png" alt="Agent Ochuko" className="w-full h-full object-cover transition duration-300 group-hover:scale-105" />
              </div>
              <div className="space-y-3">
                <h2 className="text-2xl font-bold tracking-tight text-brand-text">Agent Ochuko</h2>
                <p className="text-sm text-brand-muted leading-relaxed max-w-md mx-auto">
                  A calm, high-competence assistant designed to assist across law, finance, psychology, systems, and strategy.
                </p>
                <p className="text-xs text-brand-accent font-semibold tracking-wider uppercase">
                  All requests processed within strict legal parameters
                </p>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex gap-4 p-5 rounded-xl border transition-all duration-200 ${
                    msg.role === 'user'
                      ? 'bg-brand-surface/20 border-brand-border/60 ml-8 sm:ml-16 border-l-brand-accent/40'
                      : 'bg-brand-card/40 border-brand-border mr-8 sm:mr-16 shadow-lg shadow-black/10'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 overflow-hidden ${
                    msg.role === 'user' ? 'border-brand-border bg-brand-surface' : 'border-brand-accent/20 bg-brand-surface/80'
                  }`}>
                    <img src="/favicon.png" alt={msg.role === 'user' ? 'User' : 'Agent Ochuko'} className="w-full h-full object-cover" />
                  </div>
                  <div className="text-sm leading-relaxed whitespace-pre-wrap flex-1 self-center text-brand-text/90 font-medium">
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Input Bar & Controls */}
        <div className="p-4 md:p-6 bg-gradient-to-t from-brand-bg via-brand-bg to-transparent relative z-10 border-t border-brand-border/30">
          <div className="max-w-3xl mx-auto mb-4 flex gap-2 justify-center sm:justify-start">
            {[
              { id: 'think', label: 'Think Mode', desc: 'Deep multi-angle analysis (GPT-5.4)', icon: Brain },
              { id: 'solve', label: 'Solve Mode', desc: 'Precision logic & step-by-step reasoning', icon: Cpu },
              { id: 'discuss', label: 'Discuss Mode', desc: 'Quick natural dialog & consultation', icon: MessageSquare },
            ].map((m) => {
              const Icon = m.icon
              const isActive = mode === m.id
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setMode(m.id as 'think' | 'solve' | 'discuss')}
                  title={m.desc}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold border transition-all duration-200 active:scale-95 ${
                    isActive
                      ? 'bg-brand-accent/10 border-brand-accent/80 text-brand-accent shadow-lg shadow-brand-accent/5'
                      : 'bg-brand-surface/40 border-brand-border/40 text-brand-muted hover:border-brand-border hover:text-brand-text'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{m.label}</span>
                </button>
              )
            })}
          </div>
          
          <form onSubmit={handleSend} className="max-w-3xl mx-auto relative flex items-center">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Submit an inquiry..."
              disabled={isStreaming}
              className="w-full h-12 bg-brand-surface/40 border border-brand-border/80 rounded-xl pl-4 pr-12 text-sm text-brand-text placeholder-brand-muted focus:outline-none focus:border-brand-accent focus:ring-1 focus:ring-brand-accent/30 transition duration-150 disabled:opacity-50"
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={isStreaming || !input.trim()}
              className="absolute right-2.5 w-8 h-8 bg-brand-accent text-brand-bg rounded-lg flex items-center justify-center hover:bg-brand-accent/90 transition duration-150 disabled:opacity-30 active:scale-95 shadow-md shadow-brand-accent/10"
            >
              <Send className="w-3.5 h-3.5 font-bold" />
            </button>
          </form>
          <div className="text-[10px] text-center text-brand-muted mt-3 font-semibold tracking-wide uppercase">
            SECURE CLIENT INTERFACE • AUTH SYNCED
          </div>
        </div>

      </main>
    </div>
  )
}

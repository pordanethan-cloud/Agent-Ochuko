import React, { useState, useEffect, useRef } from 'react'
import { supabase } from '../utils/supabaseClient'
import { LogOut, Send, Brain, Cpu, MessageSquare, Menu, Copy, Check, Globe, Pencil, Trash } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

interface Message {
  role: 'user' | 'assistant'
  content: string
  routing_mode?: string
  routing_reason?: string
}

// ─── Inline markdown: bold, italic, code ─────────────────────────────────────
function renderInline(text: string, keyBase: string): React.ReactNode {
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g
  const segments: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push(<span key={`${keyBase}-t${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>)
    }
    if (match[0].startsWith('**')) {
      segments.push(
        <strong key={`${keyBase}-b${match.index}`} className="font-semibold text-[#f0ece4]">
          {match[2]}
        </strong>
      )
    } else if (match[0].startsWith('*')) {
      segments.push(
        <em key={`${keyBase}-i${match.index}`} className="italic text-brand-text/75">
          {match[3]}
        </em>
      )
    } else {
      segments.push(
        <code
          key={`${keyBase}-c${match.index}`}
          className="bg-black/40 border border-brand-border/50 rounded px-1.5 py-[1px] text-[11px] font-mono text-[#c5a880]/90"
        >
          {match[4]}
        </code>
      )
    }
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    segments.push(<span key={`${keyBase}-tail`}>{text.slice(lastIndex)}</span>)
  }

  return segments.length === 1 ? segments[0] : <>{segments}</>
}

// ─── Block markdown renderer ──────────────────────────────────────────────────
function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const raw = lines[i]
    const kb = `md-${i}`

    // Fenced code block
    if (raw.startsWith('```')) {
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      nodes.push(
        <pre
          key={kb}
          className="bg-black/50 border border-brand-border/40 rounded-lg px-5 py-4 my-4 overflow-x-auto"
        >
          <code className="text-[11.5px] font-mono text-[#d4c5a0]/85 leading-relaxed">
            {codeLines.join('\n')}
          </code>
        </pre>
      )
      i++ // skip closing ```
      continue
    }

    // Headings
    if (raw.startsWith('### ')) {
      nodes.push(
        <h3 key={kb} className="text-[13px] font-bold text-[#f0ece4] mt-5 mb-2 tracking-tight">
          {renderInline(raw.slice(4), kb)}
        </h3>
      )
      i++; continue
    }
    if (raw.startsWith('## ')) {
      nodes.push(
        <h2 key={kb} className="text-sm font-bold text-[#f0ece4] mt-6 mb-2 tracking-tight">
          {renderInline(raw.slice(3), kb)}
        </h2>
      )
      i++; continue
    }
    if (raw.startsWith('# ')) {
      nodes.push(
        <h1 key={kb} className="text-base font-bold text-[#f0ece4] mt-6 mb-2 tracking-tight">
          {renderInline(raw.slice(2), kb)}
        </h1>
      )
      i++; continue
    }

    // Horizontal rule
    if (/^---+$/.test(raw.trim())) {
      nodes.push(<hr key={kb} className="border-brand-border/30 my-5" />)
      i++; continue
    }

    // Unordered list — gather consecutive items
    if (/^[-*+] /.test(raw)) {
      const items: string[] = []
      while (i < lines.length && /^[-*+] /.test(lines[i])) {
        items.push(lines[i].slice(2))
        i++
      }
      nodes.push(
        <ul key={kb} className="my-3 space-y-2">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2.5 leading-relaxed">
              <span className="text-[#c5a880] text-[8px] mt-[5px] shrink-0">◆</span>
              <span className="text-[13px] text-brand-text/85">{renderInline(item, `${kb}-li${j}`)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    // Ordered list
    if (/^\d+\. /.test(raw)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\. /, ''))
        i++
      }
      nodes.push(
        <ol key={kb} className="my-3 space-y-2">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2.5 leading-relaxed">
              <span className="text-[#c5a880] font-semibold text-[11px] shrink-0 min-w-[1.25rem] mt-[2px]">
                {j + 1}.
              </span>
              <span className="text-[13px] text-brand-text/85">{renderInline(item, `${kb}-oli${j}`)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    // Empty line → paragraph spacer
    if (raw.trim() === '') {
      nodes.push(<div key={kb} className="h-2.5" />)
      i++; continue
    }

    // Normal paragraph line
    nodes.push(
      <p key={kb} className="text-[13.5px] text-brand-text/88 leading-[1.78] tracking-[0.01em]">
        {renderInline(raw, kb)}
      </p>
    )
    i++
  }

  return <>{nodes}</>
}

function getFriendlyErrorMessage(message: string): string {
  const lower = message.toLowerCase()

  if (lower.includes("deactivated") || lower.includes("inactive") || lower.includes("user_inactive")) {
    return "Your account access has been deactivated. Please reach out to your workspace administrator for assistance."
  }
  if (lower.includes("revoked") || lower.includes("blocked") || lower.includes("account_blocked")) {
    return "Access to this system has been restricted. Please contact support if you believe this is in error."
  }
  if (lower.includes("budget") || lower.includes("budget_exhausted")) {
    return "You have reached your daily message budget. Daily limits reset automatically at midnight UTC."
  }
  if (lower.includes("quota") || lower.includes("quota_exhausted")) {
    return "Your monthly resource quota has been fully utilized. Quotas reset at the start of next month."
  }
  if (lower.includes("maintenance")) {
    return "Agent Ochuko is currently undergoing scheduled maintenance. Please try again in a few minutes."
  }
  if (lower.includes("registration") || lower.includes("closed")) {
    return "New registrations are currently closed. Please contact the administrator."
  }
  if (lower.includes("unauthorized") || lower.includes("token") || lower.includes("401")) {
    return "Your session has expired. Please sign out and sign in again to refresh your authentication."
  }
  if (lower.includes("supabase") || lower.includes("database") || lower.includes("postgres") || lower.includes("db") || lower.includes("relation") || lower.includes("connection")) {
    return "We are experiencing a temporary database connection issue. Our team is working to restore full connectivity; please try again in a few moments."
  }
  if (lower.includes("500") || lower.includes("internal server") || lower.includes("failed to load resource")) {
    return "We encountered a temporary technical issue. Our systems are recovering; please try sending your message again in a moment."
  }
  if (lower.includes("openai") || lower.includes("rate limit") || lower.includes("model")) {
    return "The AI engine is temporarily experiencing high traffic. Please try again shortly."
  }

  return `We were unable to process your request at this moment (${message}). Please try again in a few moments or contact support.`
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [mode, setMode] = useState<'think' | 'solve' | 'discuss'>('discuss')
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isSidebarHovered, setIsSidebarHovered] = useState(false)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [webSearchStatus, setWebSearchStatus] = useState<'idle' | 'searching' | 'done'>('idle')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isAutoScrollEnabledRef = useRef<boolean>(true)
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)
  const [editingMessageText, setEditingMessageText] = useState("")
  const abortControllerRef = useRef<AbortController | null>(null)

  const [activeConversationId, setActiveConversationId] = useState<string>('00000000-0000-0000-0000-000000000000')
  const [conversations, setConversations] = useState<any[]>([])
  const [convoToDelete, setConvoToDelete] = useState<string | null>(null)


  const fetchConversations = async () => {
    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) return

      const res = await fetch(`${API_BASE}/v1/conversations`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (res.ok) {
        const data = await res.json()
        setConversations(data)
      }
    } catch (e) {
      console.error("Failed to fetch conversations:", e)
    }
  }

  const handleNewSession = () => {
    setMessages([])
    setActiveConversationId('00000000-0000-0000-0000-000000000000')
    setMode('discuss')
    setIsSidebarOpen(false)
  }

  const handleConfirmDelete = async () => {
    if (!convoToDelete) return
    const id = convoToDelete
    setConvoToDelete(null)
    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) return

      const res = await fetch(`${API_BASE}/v1/conversations/${id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (res.ok) {
        if (id === activeConversationId) {
          handleNewSession()
        }
        fetchConversations()
      } else {
        console.error("Failed to delete conversation:", res.statusText)
      }
    } catch (e) {
      console.error("Error deleting conversation:", e)
    }
  }


  const handleSelectConversation = async (id: string, convoMode: 'think' | 'solve' | 'discuss') => {
    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) return

      const res = await fetch(`${API_BASE}/v1/conversations/${id}/messages`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (res.ok) {
        const data = await res.json()
        const mapped = data.map((m: any) => ({
          role: m.role,
          content: m.content,
          routing_mode: m.routing_mode,
          routing_reason: m.routing_reason,
        }))
        setMessages(mapped)
        setActiveConversationId(id)
        setMode(convoMode)
        setIsSidebarOpen(false)
      }
    } catch (e) {
      console.error("Failed to load message history:", e)
    }
  }

  const handleModeChange = async (newMode: 'think' | 'solve' | 'discuss') => {
    setMode(newMode)
    if (activeConversationId && activeConversationId !== '00000000-0000-0000-0000-000000000000') {
      try {
        const session = await supabase.auth.getSession()
        const token = session.data.session?.access_token
        if (!token) return

        await fetch(`${API_BASE}/v1/conversations/${activeConversationId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ mode: newMode }),
        })
        fetchConversations()
      } catch (e) {
        console.error("Failed to update conversation mode:", e)
      }
    }
  }

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        setUserEmail(user.email || 'User')
        fetchConversations()
      }
    })
  }, [])

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Check scroll position to determine if we should stay locked to the bottom
  const handleScroll = () => {
    const container = scrollContainerRef.current
    if (container) {
      const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100
      isAutoScrollEnabledRef.current = isAtBottom
    }
  }

  // Auto-scroll on new content only if user is already at the bottom
  useEffect(() => {
    const container = scrollContainerRef.current
    if (container && isAutoScrollEnabledRef.current) {
      container.scrollTop = container.scrollHeight
    }
  }, [messages])

  const handleSignOut = async () => {
    await supabase.auth.signOut()
  }

  const handleCopy = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedIndex(index)
      setTimeout(() => setCopiedIndex(null), 2000)
    } catch (_) {}
  }

  const triggerStream = async (history: Message[], newUserMessage: string) => {
    // 1. Abort any active stream before launching a new one
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    setIsStreaming(true)
    setWebSearchStatus('idle')

    // Append the new user message and an assistant placeholder
    const nextMessages: Message[] = [...history, { role: 'user', content: newUserMessage }]
    setMessages([...nextMessages, { role: 'assistant', content: '' }])

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token

      const response = await fetch(`${API_BASE}/v1/responses/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          conversation_id: activeConversationId,
          mode,
          messages: nextMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
        signal: abortController.signal,
      })

      if (!response.ok) {
        let errMsg = `HTTP error! status: ${response.status}`
        try {
          const errData = await response.json()
          if (errData?.error?.message) {
            errMsg = errData.error.message
          } else if (errData?.error?.code) {
            errMsg = errData.error.code
          }
        } catch (_) {
          try {
            const txt = await response.text()
            if (txt && txt.length < 200) errMsg = txt
          } catch (_) {}
        }
        throw new Error(errMsg)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No body reader available')

      let accumulatedText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const dataStr = line.slice(6).trim()
          if (dataStr === '[DONE]') continue
          try {
            const data = JSON.parse(dataStr)
            if (data.type === 'content_block_delta') {
              accumulatedText += data.delta.text
              setMessages((prev) => {
                const updated = [...prev]
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: accumulatedText
                }
                return updated
              })
            } else if (data.type === 'routing_info') {
              setMessages((prev) => {
                const updated = [...prev]
                if (updated.length > 0) {
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    routing_mode: data.routing_mode
                  }
                }
                return updated
              })
            } else if (data.type === 'conversation_id') {
              setActiveConversationId(data.conversation_id)
              fetchConversations()
            } else if (data.type === 'web_search_status') {
              setWebSearchStatus(data.status === 'searching' ? 'searching' : 'done')
            } else if (data.type === 'error') {
              throw new Error(`Agent error: ${data.error}`)
            }
          } catch (err: any) {
            if (err.name === 'AbortError') return
            // Only re-throw real errors, not JSON parse errors on partial chunks
            if (err.message && !err.message.startsWith('Unexpected') && !err.message.includes('JSON')) {
              throw err
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return // silently exit
      const explanation = getFriendlyErrorMessage(err.message || 'unknown')
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: explanation,
          routing_mode: 'discuss'
        }
        return updated
      })
    } finally {
      if (abortControllerRef.current === abortController) {
        setIsStreaming(false)
        setWebSearchStatus('idle')
        abortControllerRef.current = null
        // Return focus to input so user can type the next message immediately
        setTimeout(() => inputRef.current?.focus(), 0)
      }
    }
  }

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return

    const userMessage = input.trim()
    setInput('')
    // Force focus back to input immediately so user can type ahead while streaming
    setTimeout(() => inputRef.current?.focus(), 0)

    await triggerStream(messages, userMessage)
  }

  const handleEditSubmit = async (index: number) => {
    const newText = editingMessageText.trim()
    if (!newText) return

    setEditingMessageIndex(null)
    setEditingMessageText("")

    // Truncate messages list up to the edited user message
    const truncatedHistory = messages.slice(0, index)
    await triggerStream(truncatedHistory, newText)
  }

  return (
    <div className="flex h-screen bg-brand-bg text-brand-text font-sans antialiased overflow-hidden relative">

      {/* Left-edge hover zone */}
      <div
        onMouseEnter={() => setIsSidebarHovered(true)}
        className="absolute left-0 top-0 w-3 h-full z-20"
      />

      {/* Backdrop */}
      {(isSidebarOpen || isSidebarHovered) && (
        <div
          onClick={() => { setIsSidebarOpen(false); setIsSidebarHovered(false) }}
          className="absolute inset-0 bg-black/55 backdrop-blur-[2px] z-20 transition-opacity duration-300"
        />
      )}

      {/* Slide-out Sidebar Drawer */}
      <aside
        onMouseLeave={() => setIsSidebarHovered(false)}
        className={`absolute top-3 left-3 h-[calc(100vh-24px)] w-64 bg-[#0d0f11]/95 border border-[#1e2025] rounded-2xl z-30 flex flex-col justify-between px-6 py-7 backdrop-blur-xl shadow-2xl shadow-black/80 transition-all duration-300 ease-out ${
          isSidebarOpen || isSidebarHovered ? 'translate-x-0 opacity-100' : '-translate-x-[calc(100%+24px)] opacity-0 pointer-events-none'
        }`}
      >
        <div>
          <div className="flex items-center gap-3 mb-8 pb-6 border-b border-[#1e2025]">
            <div className="w-9 h-9 rounded-xl overflow-hidden border border-[#c5a880]/15 bg-brand-bg shrink-0">
              <img src="/favicon.png" alt="Ochuko" className="w-full h-full object-cover" />
            </div>
            <div>
              <p className="font-semibold text-[13px] text-brand-text tracking-tight">Agent Ochuko</p>
              <p className="text-[9px] text-[#c5a880] font-bold tracking-widest uppercase mt-0.5">System Active</p>
            </div>
          </div>

          <button
            onClick={handleNewSession}
            className="w-full h-10 border border-[#1e2025] bg-black/30 hover:bg-black/50 text-brand-text hover:border-[#c5a880]/30 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center tracking-wide mb-6"
          >
            New Session
          </button>

          {/* Conversation List */}
          <div className="flex-1 overflow-y-auto space-y-1.5 max-h-[calc(100vh-270px)] pr-1 custom-scrollbar">
            <p className="text-[9px] font-bold tracking-widest text-[#8e95a2]/50 uppercase mb-2">Sessions</p>
            {conversations.length === 0 ? (
              <p className="text-[10px] text-[#8e95a2]/40 italic pl-1">No past sessions</p>
            ) : (
              conversations.map((convo) => {
                const active = convo.id === activeConversationId
                return (
                  <div key={convo.id} className="group relative flex items-center w-full">
                    <button
                      onClick={() => handleSelectConversation(convo.id, convo.mode)}
                      className={`flex-1 text-left px-3 py-2 rounded-lg text-[11px] font-medium truncate transition duration-150 block pr-8 ${
                        active
                          ? 'bg-[#c5a880]/10 text-brand-text border border-[#c5a880]/20'
                          : 'text-[#8e95a2] hover:text-brand-text hover:bg-white/5 border border-transparent'
                      }`}
                    >
                      {convo.title || 'Untitled Session'}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setConvoToDelete(convo.id)
                      }}
                      className="absolute right-2 opacity-0 group-hover:opacity-100 p-1 text-[#8e95a2] hover:text-red-400 transition duration-150 rounded hover:bg-white/5"
                      title="Delete Session"
                    >
                      <Trash className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )
              })
            )}
          </div>
        </div>

        <div className="border-t border-[#1e2025] pt-5 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full overflow-hidden border border-[#1e2025] bg-brand-bg shrink-0">
              <img src="/favicon.png" alt="User" className="w-full h-full object-cover" />
            </div>
            <div className="truncate">
              <p className="text-[9px] text-brand-muted uppercase font-bold tracking-widest">Authenticated</p>
              <p className="text-[11px] text-brand-text font-medium truncate mt-0.5">{userEmail}</p>
            </div>
          </div>
          <button
            onClick={handleSignOut}
            className="w-full h-10 text-red-400/70 hover:text-red-300 hover:bg-red-950/15 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center gap-2.5 px-3 border border-transparent hover:border-red-900/30"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Terminate Session</span>
          </button>
        </div>
      </aside>

      {/* Chat Workspace */}
      <main className="flex-1 flex flex-col relative bg-brand-bg overflow-hidden z-10 min-w-0">

        {/* Header */}
        <header className="h-14 border-b border-[#1a1c1f] bg-[#0a0b0d]/80 backdrop-blur-md flex items-center justify-between px-5 shrink-0">
          <div className="flex items-center gap-3.5">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              onMouseEnter={() => setIsSidebarHovered(true)}
              className="p-[7px] rounded-lg border border-[#1e2025] bg-brand-surface/20 hover:bg-brand-surface text-brand-muted hover:text-brand-text hover:border-[#c5a880]/25 transition duration-150 active:scale-95"
              aria-label="Toggle Sidebar"
            >
              <Menu className="w-4 h-4" />
            </button>
            <div className="w-px h-4 bg-[#1e2025]" />
            <span className="font-semibold text-[13px] text-brand-text tracking-tight">Agent Ochuko</span>
            <span className="text-[9px] uppercase tracking-widest px-2 py-[3px] rounded border border-[#c5a880]/15 text-[#c5a880]/70 font-bold hidden sm:inline-block">
              {mode}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#c5a880] opacity-50" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#c5a880]" />
            </span>
            <span className="text-[9px] font-bold tracking-widest text-brand-muted uppercase hidden sm:block">Auth Synced</span>
          </div>
        </header>



        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto py-8 px-5 md:px-10 relative z-10"
        >
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center space-y-7">
              <div className="w-16 h-16 bg-brand-surface border border-[#1e2025] rounded-2xl overflow-hidden shadow-xl relative group">
                <div className="absolute inset-0 bg-[#c5a880]/4 opacity-0 group-hover:opacity-100 transition duration-500" />
                <img
                  src="/favicon.png"
                  alt="Agent Ochuko"
                  className="w-full h-full object-cover transition duration-500 group-hover:scale-105"
                  fetchPriority="high"
                />
              </div>
              <div className="space-y-3">
                <h2 className="text-[21px] font-bold tracking-tight text-brand-text">Agent Ochuko</h2>
                <p className="text-[13px] text-brand-muted leading-relaxed max-w-[280px] mx-auto">
                  Calm. Competent. Precise. Across law, finance, psychology, systems, and strategy.
                </p>
                <p className="text-[9px] text-[#c5a880]/70 font-bold tracking-widest uppercase">
                  All responses within strict legal parameters
                </p>
              </div>
            </div>
          ) : (
            <div className="max-w-2xl mx-auto space-y-5">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`group relative flex gap-3.5 ${msg.role === 'user' ? 'ml-6 sm:ml-14' : ''}`}
                >
                  {/* Avatar */}
                  <div
                    className={`w-7 h-7 rounded-lg border flex items-center justify-center shrink-0 overflow-hidden mt-1 ${
                      msg.role === 'user'
                        ? 'border-[#1e2025] bg-brand-surface/60'
                        : 'border-[#c5a880]/12 bg-brand-surface/30'
                    }`}
                  >
                    <img
                      src="/favicon.png"
                      alt={msg.role === 'user' ? 'User' : 'Ochuko'}
                      className="w-full h-full object-cover"
                    />
                  </div>

                  {/* Right side container: Bubble + Actions */}
                  <div className="flex-1 min-w-0 flex flex-col gap-1.5">
                    {/* Bubble */}
                    <div
                      className={`relative rounded-xl px-5 py-4 border min-w-0 ${
                        msg.role === 'user'
                          ? 'bg-[#0f1113]/60 border-[#1e2025]/80'
                          : 'bg-[#0c0e10]/90 border-[#1a1d20] shadow-lg shadow-black/30'
                      }`}
                    >
                      {/* Content */}
                      {msg.role === 'user' ? (
                        editingMessageIndex === i ? (
                          <div className="space-y-3 pt-1">
                            <textarea
                              aria-label="Edit message"
                              value={editingMessageText}
                              onChange={(e) => setEditingMessageText(e.target.value)}
                              className="w-full bg-[#0d0f11] border border-[#1a1d20] focus:border-[#c5a880]/40 rounded-lg p-3 text-[13.5px] text-brand-text focus:outline-none resize-none font-sans"
                              rows={Math.max(2, editingMessageText.split('\n').length)}
                            />
                            <div className="flex gap-2 justify-end">
                              <button
                                onClick={() => setEditingMessageIndex(null)}
                                className="px-3 py-1.5 border border-[#1e2025] hover:border-[#252830] hover:bg-white/5 rounded-lg text-[11px] font-semibold text-brand-muted hover:text-brand-text transition duration-150"
                              >
                                Cancel
                              </button>
                              <button
                                onClick={() => handleEditSubmit(i)}
                                className="px-3 py-1.5 bg-[#c5a880] text-[#08090a] hover:bg-[#d4b990] rounded-lg text-[11px] font-bold transition duration-150 shadow-md shadow-[#c5a880]/5"
                              >
                                Save & Submit
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-[13.5px] text-brand-text/90 leading-[1.7] font-medium">
                            {msg.content}
                          </p>
                        )
                      ) : msg.content === '' && isStreaming ? (
                        // Typing / searching indicator — appears immediately before first token
                        <div className="flex items-center gap-2 h-6">
                          {webSearchStatus === 'searching' ? (
                            <>
                              <Globe className="w-3.5 h-3.5 text-[#c5a880] animate-pulse" />
                              <span className="text-[11px] text-[#c5a880]/70 font-semibold tracking-wide">
                                Searching the web...
                              </span>
                            </>
                          ) : (
                            [0, 150, 300].map((delay, d) => (
                              <span
                                key={d}
                                className={`w-1.5 h-1.5 rounded-full bg-[#c5a880]/50 animate-bounce dot-bounce-${delay}`}
                              />
                            ))
                          )}
                        </div>
                      ) : (
                        // Rendered markdown
                        <div className="space-y-0.5">
                          {renderMarkdown(msg.content)}
                        </div>
                      )}
                    </div>



                    {/* Actions Row at the bottom (outside the bubble), visible on hover */}
                    {((msg.role === 'assistant' && msg.content.length > 0) || (msg.role === 'user' && editingMessageIndex !== i)) && (
                      <div className="flex items-center gap-3.5 pl-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        {msg.role === 'assistant' && msg.content.length > 0 && (
                          <button
                            onClick={() => handleCopy(msg.content, i)}
                            title="Copy response"
                            className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase"
                          >
                            {copiedIndex === i ? (
                              <>
                                <Check className="w-3 h-3 text-[#c5a880]" />
                                <span className="text-[#c5a880]">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        )}

                        {msg.role === 'user' && editingMessageIndex !== i && (
                          <button
                            onClick={() => {
                              setEditingMessageIndex(i)
                              setEditingMessageText(msg.content)
                            }}
                            title="Edit prompt"
                            className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase"
                          >
                            <Pencil className="w-3 h-3" />
                            <span>Edit</span>
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="shrink-0 px-5 md:px-10 pb-6 pt-3 border-t border-[#141618] bg-gradient-to-t from-brand-bg to-transparent relative z-10">
          {/* Mode selector + Web Search toggle */}
          <div className="max-w-2xl mx-auto mb-3 flex gap-1.5 items-center">
            {([
              { id: 'think', label: 'Think', icon: Brain },
              { id: 'solve', label: 'Solve', icon: Cpu },
              { id: 'discuss', label: 'Discuss', icon: MessageSquare },
            ] as const).map(({ id, label, icon: Icon }) => {
              const active = mode === id
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleModeChange(id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold border transition-all duration-200 active:scale-95 tracking-widest uppercase ${
                    active
                      ? 'bg-[#c5a880]/8 border-[#c5a880]/40 text-[#c5a880]'
                      : 'bg-transparent border-[#1a1d20] text-brand-muted hover:border-[#252830] hover:text-brand-text/60'
                  }`}
                >
                  <Icon className="w-3 h-3" />
                  <span>{label}</span>
                </button>
              )
            })}

          </div>

          {/* Input */}
          <form onSubmit={handleSend} className="max-w-2xl mx-auto relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Submit an inquiry..."
              className="w-full h-12 bg-[#0d0f11]/80 border border-[#1a1d20] rounded-xl pl-4 pr-14 text-[13.5px] text-brand-text placeholder-[#8e95a2]/40 focus:outline-none focus:border-[#c5a880]/40 focus:ring-1 focus:ring-[#c5a880]/15 transition duration-150"
            />
            <button
              type="submit"
              disabled={isStreaming || !input.trim()}
              aria-label="Send"
              className="absolute right-2 top-2 w-8 h-8 bg-[#c5a880] text-[#08090a] rounded-lg flex items-center justify-center hover:bg-[#d4b990] transition duration-150 disabled:opacity-20 active:scale-95 shadow-md shadow-[#c5a880]/10 font-bold"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>

          <p className="text-center text-[9px] text-brand-muted/40 font-bold tracking-[0.15em] uppercase mt-3">
            Secure · OAuth Synced · Legal Parameters Active
          </p>
        </div>

      </main>

      {convoToDelete && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-[2px] flex items-center justify-center z-50 p-4">
          <div className="bg-[#0d0f11] border border-[#1e2025] rounded-2xl w-full max-w-sm p-6 shadow-2xl space-y-6">
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-brand-text">Delete Session</h3>
              <p className="text-[12px] text-[#8e95a2] leading-relaxed">
                Are you sure you want to permanently delete this chat session? This action cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setConvoToDelete(null)}
                className="px-3.5 py-1.5 rounded-lg border border-[#1e2025] hover:bg-white/5 text-[11px] font-semibold text-brand-text transition"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="px-3.5 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 text-[11px] font-semibold text-red-450 transition"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


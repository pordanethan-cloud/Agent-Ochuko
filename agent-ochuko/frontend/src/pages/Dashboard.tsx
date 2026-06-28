import React, { useState, useEffect } from 'react'
import { supabase } from '../utils/supabaseClient'
import { LogOut, Send, User, Sparkles } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)

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

  const runTestScaffold = async () => {
    if (isStreaming) return
    
    // Add user test message
    const newMessages: Message[] = [...messages, { role: 'user', content: '__test_scaffold__' }]
    setMessages(newMessages)
    setIsStreaming(true)

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token

      const response = await fetch('http://localhost:8000/v1/responses/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          conversation_id: '00000000-0000-0000-0000-000000000000',
          messages: [{ role: 'user', content: '__test_scaffold__' }]
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No body reader available')

      // Add empty assistant message to append stream to
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
                // Update last assistant message
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
              }
            } catch (err) {
              // Parse error on incomplete chunks, ignore
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

      const response = await fetch('http://localhost:8000/v1/responses/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          conversation_id: '00000000-0000-0000-0000-000000000000',
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
                throw new Error(data.error)
              }
            } catch (err) {
              // Parse error on incomplete chunks, ignore
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
    <div className="flex h-screen bg-brand-bg text-brand-text font-sans antialiased overflow-hidden">
      
      {/* Sidebar - High Altitude Warm Gray */}
      <aside className="w-64 bg-brand-surface/40 border-r border-brand-border flex flex-col justify-between p-4 z-10 backdrop-blur-md">
        <div>
          <div className="flex items-center gap-3 px-2 py-3 mb-6">
            <div className="w-8 h-8 flex items-center justify-center rounded-lg overflow-hidden border border-brand-border/60">
              <img src="/favicon.png" alt="Agent Ochuko Logo" className="w-full h-full object-cover" />
            </div>
            <span className="font-medium tracking-wide">Agent Ochuko</span>
          </div>

          <button
            onClick={() => setMessages([])}
            className="w-full h-10 border border-brand-border hover:bg-brand-surface/60 transition duration-150 rounded-lg text-sm font-medium flex items-center justify-center gap-2"
          >
            New Chat
          </button>
        </div>

        {/* User profile footer */}
        <div className="border-t border-brand-border/60 pt-4 space-y-3">
          <div className="flex items-center gap-3 px-2">
            <div className="w-8 h-8 bg-brand-card border border-brand-border flex items-center justify-center rounded-full text-brand-muted">
              <User className="w-4 h-4" />
            </div>
            <span className="text-xs text-brand-muted truncate max-w-[140px]">{userEmail}</span>
          </div>
          <button
            onClick={handleSignOut}
            className="w-full h-10 hover:bg-red-950/20 text-red-400 hover:text-red-300 transition duration-150 rounded-lg text-xs font-medium flex items-center gap-3 px-3 border border-transparent hover:border-red-900/40"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Chat Workspace */}
      <main className="flex-1 flex flex-col justify-between relative bg-brand-bg overflow-hidden">
        {/* Glow behind chat */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-brand-accent/3 rounded-full blur-[140px] pointer-events-none" />

        {/* Chat History */}
        <div className="flex-1 overflow-y-auto p-6 md:p-12 space-y-6 relative z-10">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center space-y-6 mt-16 md:mt-24">
              <div className="w-16 h-16 bg-brand-surface border border-brand-border rounded-2xl flex items-center justify-center text-brand-accent shadow-xl overflow-hidden">
                <img src="/favicon.png" alt="Agent Ochuko" className="w-full h-full object-cover" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-medium tracking-tight">Agent Ochuko Scaffold</h2>
                <p className="text-sm text-brand-muted leading-relaxed">
                  Your secure environment is ready. Click the test button to run the endpoint verification smoke test.
                </p>
              </div>
              <button
                onClick={runTestScaffold}
                disabled={isStreaming}
                className="h-10 px-5 bg-brand-surface border border-brand-border hover:border-brand-accent/50 hover:bg-brand-surface/80 text-brand-accent text-sm font-medium rounded-lg transition duration-150 active:scale-[0.98]"
              >
                Run Smoke Test
              </button>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex gap-4 p-4 rounded-xl border ${
                    msg.role === 'user'
                      ? 'bg-brand-surface/40 border-brand-border ml-12'
                      : 'bg-brand-card/50 border-brand-border mr-12'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-lg border border-brand-border flex items-center justify-center shrink-0 overflow-hidden ${
                    msg.role === 'user' ? 'bg-brand-card text-brand-muted' : ''
                  }`}>
                    {msg.role === 'user' ? (
                      <User className="w-4 h-4" />
                    ) : (
                      <img src="/favicon.png" alt="Agent Ochuko" className="w-full h-full object-cover" />
                    )}
                  </div>
                  <div className="text-sm leading-relaxed whitespace-pre-wrap flex-1 self-center text-brand-text/95">
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="p-4 md:p-6 bg-gradient-to-t from-brand-bg via-brand-bg to-transparent relative z-10">
          <form onSubmit={handleSend} className="max-w-3xl mx-auto relative flex items-center">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything..."
              disabled={isStreaming}
              className="w-full h-12 bg-brand-surface/50 border border-brand-border rounded-xl pl-4 pr-12 text-sm text-brand-text placeholder-brand-muted focus:outline-none focus:border-brand-accent/60 transition duration-150 disabled:opacity-50"
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={isStreaming || !input.trim()}
              className="absolute right-2 w-8 h-8 bg-brand-text text-brand-bg rounded-lg flex items-center justify-center hover:bg-brand-text/90 transition duration-150 disabled:opacity-30 active:scale-95"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <div className="text-[10px] text-center text-brand-muted mt-3 font-light">
            OAuth-validated secure API session
          </div>
        </div>

      </main>
    </div>
  )
}

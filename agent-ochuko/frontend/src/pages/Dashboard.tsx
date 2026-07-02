import React, { useState, useEffect, useRef, useCallback } from 'react'
import { supabase } from '../utils/supabaseClient'
import { LogOut, Send, Square, Brain, Cpu, MessageSquare, Menu, Copy, Check, Globe, Pencil, Trash, Paperclip, FileText, Loader2, X, Mic, Volume2, ChevronDown, ChevronUp } from 'lucide-react'
import { useVoice } from '../hooks/useVoice'
import { useJob } from '../hooks/useJob'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

interface Source {
  title: string
  url: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  routing_mode?: string
  routing_reason?: string
  fileAttachment?: { name: string; jobType: 'ocr' | 'vision' }
  sources?: Source[]
  imageUrl?: string      // set when a generated image is ready
  imagePending?: boolean // true while the FLUX job is in-flight
}

// ─── Inline markdown: bold, italic, code, links ───────────────────────────────
function renderInline(text: string, keyBase: string): React.ReactNode {
  const pattern = /(\*\*(.*?)\*\*|\*(.*?)\*|`(.*?)`|\[(.*?)\]\((.*?)\))/g
  const segments: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push(<span key={`${keyBase}-t${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>)
    }

    const fullMatch = match[0]
    if (fullMatch.startsWith('**')) {
      segments.push(
        <strong key={`${keyBase}-b${match.index}`} className="font-semibold text-[#f0ece4]">
          {match[2]}
        </strong>
      )
    } else if (fullMatch.startsWith('*')) {
      segments.push(
        <em key={`${keyBase}-i${match.index}`} className="italic text-[#c5a880]/90">
          {match[3]}
        </em>
      )
    } else if (fullMatch.startsWith('`')) {
      segments.push(
        <code
          key={`${keyBase}-c${match.index}`}
          className="bg-black/40 border border-[#c5a880]/20 rounded px-1.5 py-[1px] text-[11.5px] font-mono text-[#c5a880]/90"
        >
          {match[4]}
        </code>
      )
    } else if (fullMatch.startsWith('[')) {
      const label = match[5]
      const url = match[6]
      segments.push(
        <a
          key={`${keyBase}-l${match.index}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#c5a880] hover:text-[#d4b990] underline underline-offset-4 decoration-[#c5a880]/40 transition duration-150"
        >
          {label}
        </a>
      )
    }

    lastIndex = match.index + fullMatch.length
  }

  if (lastIndex < text.length) {
    segments.push(<span key={`${keyBase}-tail`}>{text.slice(lastIndex)}</span>)
  }

  return segments.length === 1 ? segments[0] : <>{segments}</>
}

interface ParsedMessage {
  textPrefix: string
  hasPastedText: boolean
  pastedName?: string
  pastedContent?: string
}

function parsePastedText(content: string): ParsedMessage {
  const pattern = /(?:\r?\n\r?\n)?\[Pasted Content: (.*?)\]\r?\n```\r?\n([\s\S]*?)```$/
  const match = content.match(pattern)
  if (match) {
    const textPrefix = content.slice(0, match.index).trim()
    return {
      textPrefix,
      hasPastedText: true,
      pastedName: match[1],
      pastedContent: match[2].trim(),
    }
  }
  return {
    textPrefix: content,
    hasPastedText: false,
  }
}

// ── ImagePending — shimmer placeholder while FLUX is running ─────────────────
const ImagePending: React.FC<{ prompt?: string }> = ({ prompt }) => (
  <div className="flex flex-col gap-2.5 my-1">
    <div className="w-72 h-52 rounded-2xl bg-[#111316] border border-[#1e2025] overflow-hidden relative">
      {/* Animated shimmer */}
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.8s_infinite] bg-gradient-to-r from-transparent via-[#c5a880]/5 to-transparent" />
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-[#c5a880]/30 border-t-[#c5a880] animate-spin" />
        <span className="text-[10px] font-bold text-[#c5a880]/60 tracking-widest uppercase">Generating image…</span>
      </div>
    </div>
    {prompt && (
      <p className="text-[10px] text-brand-muted/60 italic px-1 max-w-[280px] truncate">{prompt}</p>
    )}
  </div>
)

// ── ImageBubble — premium image card shown once generation is done ───────────
const ImageBubble: React.FC<{ url: string; prompt?: string }> = ({ url, prompt }) => (
  <div className="flex flex-col gap-2 my-1 group/img">
    <div className="relative rounded-2xl overflow-hidden border border-[#1e2025] shadow-xl shadow-black/50 w-fit max-w-sm">
      <img
        src={url}
        alt={prompt || 'Generated image'}
        className="block w-full max-w-sm object-cover transition-transform duration-500 group-hover/img:scale-[1.02]"
        loading="lazy"
      />
      {/* Download overlay on hover */}
      <div className="absolute inset-0 bg-black/0 group-hover/img:bg-black/40 transition-all duration-300 flex items-end justify-end p-3">
        <a
          href={url}
          download
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-0 group-hover/img:opacity-100 transition-opacity duration-200 flex items-center gap-1.5 px-3 py-1.5 bg-[#c5a880] text-[#08090a] rounded-lg text-[10px] font-bold tracking-wider uppercase shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          ↓ Download
        </a>
      </div>
    </div>
    {prompt && (
      <p className="text-[10px] text-brand-muted/70 italic px-1 max-w-[320px]">{prompt}</p>
    )}
  </div>
)

// ─── Code Block Component with Copy ──────────────────────────────────────────
const CodeBlock: React.FC<{ language: string; content: string }> = ({ language, content }) => {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (_) {}
  }

  return (
    <div className="bg-[#0b0c0e] border border-[#1a1d20]/80 rounded-xl overflow-hidden my-4 shadow-lg">
      <div className="flex items-center justify-between px-4 py-2 bg-[#121417] border-b border-[#1a1d20]/50 select-none">
        <span className="text-[10px] font-bold text-brand-muted tracking-widest uppercase font-mono">
          {language}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[10px] font-semibold text-brand-muted hover:text-brand-text transition duration-150 tracking-wider uppercase"
        >
          {copied ? (
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
      </div>
      <pre className="p-4 overflow-x-auto">
        <code className="text-[11.5px] font-mono text-[#d4c5a0]/85 leading-relaxed block whitespace-pre">
          {content}
        </code>
      </pre>
    </div>
  )
}

interface ASTBlock {
  type: 'heading' | 'code' | 'blockquote' | 'table' | 'list' | 'hr' | 'paragraph'
  level?: number
  language?: string
  content?: string
  headers?: string[]
  rows?: string[][]
  ordered?: boolean
  items?: string[]
}

// ─── Markdown AST Parser ──────────────────────────────────────────────────────
function parseMarkdownToBlocks(text: string): ASTBlock[] {
  const lines = text.split('\n')
  const blocks: ASTBlock[] = []
  let i = 0

  while (i < lines.length) {
    const raw = lines[i]
    const trimmed = raw.trim()

    // 1. Fenced Code Block
    if (trimmed.startsWith('```')) {
      const language = trimmed.slice(3).trim()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      blocks.push({
        type: 'code',
        language: language || 'text',
        content: codeLines.join('\n')
      })
      i++ // skip closing ```
      continue
    }

    // 2. Blockquote
    if (trimmed.startsWith('>')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        const content = lines[i].trim().replace(/^>\s?/, '')
        quoteLines.push(content)
        i++
      }
      blocks.push({
        type: 'blockquote',
        content: quoteLines.join('\n')
      })
      continue
    }

    // 3. Table
    if (trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.length > 1) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
        tableLines.push(lines[i].trim())
        i++
      }

      if (tableLines.length >= 1) {
        let headers: string[] = []
        let rows: string[][] = []
        let hasSeparator = false

        if (tableLines.length > 1) {
          const secondLine = tableLines[1]
          const cleaned = secondLine.replace(/[|:\s-]/g, '')
          if (cleaned === '') {
            hasSeparator = true
          }
        }

        if (hasSeparator) {
          headers = tableLines[0]
            .split('|')
            .slice(1, -1)
            .map(h => h.trim())
          
          for (let j = 2; j < tableLines.length; j++) {
            const rowCells = tableLines[j]
              .split('|')
              .slice(1, -1)
              .map(c => c.trim())
            rows.push(rowCells)
          }
        } else {
          headers = tableLines[0]
            .split('|')
            .slice(1, -1)
            .map(h => h.trim())
          for (let j = 1; j < tableLines.length; j++) {
            const rowCells = tableLines[j]
              .split('|')
              .slice(1, -1)
              .map(c => c.trim())
            rows.push(rowCells)
          }
        }

        blocks.push({
          type: 'table',
          headers,
          rows
        })
        continue
      }
    }

    // 4. Headings
    if (trimmed.startsWith('#')) {
      const match = trimmed.match(/^(#{1,6})\s+(.*)$/)
      if (match) {
        const level = match[1].length
        const content = match[2]
        blocks.push({
          type: 'heading',
          level,
          content
        })
        i++
        continue
      }
    }

    // 5. Horizontal rule
    if (/^---+$/.test(trimmed) || /^==+$/.test(trimmed) || /^\*\*\*+$/.test(trimmed)) {
      blocks.push({ type: 'hr' })
      i++
      continue
    }

    // 6. Unordered List
    if (/^[-*+]\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*+]\s+/, ''))
        i++
      }
      blocks.push({
        type: 'list',
        ordered: false,
        items
      })
      continue
    }

    // 7. Ordered List
    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ''))
        i++
      }
      blocks.push({
        type: 'list',
        ordered: true,
        items
      })
      continue
    }

    // 8. Empty line / Paragraph spacer
    if (trimmed === '') {
      i++
      continue
    }

    // 9. Paragraph
    const pLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].trim().startsWith('```') &&
      !lines[i].trim().startsWith('#') &&
      !lines[i].trim().startsWith('>') &&
      !lines[i].trim().startsWith('|') &&
      !/^[-*+]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !/^---+$/.test(lines[i].trim())
    ) {
      pLines.push(lines[i].trim())
      i++
    }
    if (pLines.length > 0) {
      blocks.push({
        type: 'paragraph',
        content: pLines.join(' ')
      })
    }
  }

  return blocks
}

// ─── Block markdown renderer ──────────────────────────────────────────────────
function renderMarkdown(text: string): React.ReactNode {
  const blocks = parseMarkdownToBlocks(text)
  return (
    <div className="space-y-4">
      {blocks.map((block, index) => {
        const key = `block-${index}`
        switch (block.type) {
          case 'heading': {
            const level = block.level || 1
            const content = renderInline(block.content || '', key)
            switch (level) {
              case 1:
                return (
                  <h1 key={key} className="text-base font-bold text-[#f0ece4] mt-6 mb-2 tracking-tight">
                    {content}
                  </h1>
                )
              case 2:
                return (
                  <h2 key={key} className="text-sm font-bold text-[#f0ece4] mt-5 mb-2 tracking-tight">
                    {content}
                  </h2>
                )
              case 3:
                return (
                  <h3 key={key} className="text-[13px] font-bold text-[#f0ece4] mt-4 mb-1.5 tracking-tight">
                    {content}
                  </h3>
                )
              case 4:
                return (
                  <h4 key={key} className="text-[12.5px] font-bold text-[#f0ece4] mt-3.5 mb-1.5 tracking-tight">
                    {content}
                  </h4>
                )
              case 5:
                return (
                  <h5 key={key} className="text-[12px] font-bold text-[#f0ece4] mt-3 mb-1 tracking-tight">
                    {content}
                  </h5>
                )
              case 6:
                return (
                  <h6 key={key} className="text-[11.5px] font-bold text-[#f0ece4] mt-2.5 mb-1 tracking-tight">
                    {content}
                  </h6>
                )
              default:
                return (
                  <h1 key={key} className="text-base font-bold text-[#f0ece4] mt-6 mb-2 tracking-tight">
                    {content}
                  </h1>
                )
            }
          }
          case 'code': {
            return (
              <CodeBlock
                key={key}
                language={block.language || 'text'}
                content={block.content || ''}
              />
            )
          }
          case 'blockquote': {
            return (
              <blockquote
                key={key}
                className="border-l-2 border-[#c5a880] pl-4 my-4 italic text-brand-text/75 bg-[#c5a880]/4 py-2 pr-3 rounded-r-lg"
              >
                {renderInline(block.content || '', key)}
              </blockquote>
            )
          }
          case 'table': {
            return (
              <div key={key} className="overflow-x-auto my-5 border border-[#1a1d20]/50 rounded-xl bg-black/20">
                <table className="min-w-full divide-y divide-[#1a1d20]/30 text-left text-[12.5px]">
                  <thead className="bg-[#1c1e22]/50 text-[#f0ece4]">
                    <tr>
                      {block.headers?.map((header, hIdx) => (
                        <th
                          key={hIdx}
                          className="px-4 py-3 font-semibold border-b border-[#1a1d20]/30 tracking-wider text-[11px] uppercase text-[#c5a880]/80"
                        >
                          {renderInline(header, `${key}-th-${hIdx}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1a1d20]/20">
                    {block.rows?.map((row, rIdx) => (
                      <tr
                        key={rIdx}
                        className={rIdx % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.02]'}
                      >
                        {row.map((cell, cIdx) => (
                          <td key={cIdx} className="px-4 py-3 text-brand-text/85">
                            {renderInline(cell, `${key}-td-${rIdx}-${cIdx}`)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
          case 'list': {
            if (block.ordered) {
              return (
                <ol key={key} className="my-3 space-y-2 pl-1">
                  {block.items?.map((item, j) => (
                    <li key={j} className="flex gap-2.5 leading-relaxed items-start">
                      <span className="text-[#c5a880] font-semibold text-[11.5px] shrink-0 min-w-[1.25rem] mt-[1.5px]">
                        {j + 1}.
                      </span>
                      <span className="text-[13px] text-brand-text/85">
                        {renderInline(item, `${key}-oli-${j}`)}
                      </span>
                    </li>
                  ))}
                </ol>
              )
            } else {
              return (
                <ul key={key} className="my-3 space-y-2 pl-1">
                  {block.items?.map((item, j) => (
                    <li key={j} className="flex gap-2.5 leading-relaxed items-start">
                      <span className="text-[#c5a880] text-[8px] mt-[6.5px] shrink-0 select-none">◆</span>
                      <span className="text-[13px] text-brand-text/85">
                        {renderInline(item, `${key}-uli-${j}`)}
                      </span>
                    </li>
                  ))}
                </ul>
              )
            }
          }
          case 'hr': {
            return <hr key={key} className="border-[#1a1d20]/30 my-5" />
          }
          case 'paragraph': {
            return (
              <p key={key} className="text-[13.5px] text-brand-text/88 leading-[1.78] tracking-[0.01em]">
                {renderInline(block.content || '', key)}
              </p>
            )
          }
          default:
            return null
        }
      })}
    </div>
  )
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

  if (lower.includes("completed event") || lower.includes("guardrail") || lower.includes("content_filter") || lower.includes("safety")) {
    return "This request was blocked by the system safety guardrails because the prompt or response contained content violating safety policies. Please rephrase your query and try again."
  }

  return `We were unable to process your request at this moment (${message}). Please try again in a few moments or contact support.`
}

// ── VoiceWaveform — 5-bar volume-driven equaliser ────────────────────────────
const VoiceWaveform: React.FC<{ volume: number }> = ({ volume }) => {
  const bars = [0.35, 0.65, 1.0, 0.65, 0.35]
  return (
    <div className="flex items-end justify-center gap-[3px] h-4" aria-hidden>
      {bars.map((base, idx) => (
        <div
          key={idx}
          className="w-[3px] rounded-full bg-[#c5a880] transition-all duration-75"
          style={{
            height: `${Math.max(3, Math.round(base * volume * 14 + 3))}px`,
            opacity: 0.4 + base * volume * 0.6,
          }}
        />
      ))}
    </div>
  )
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
  const [activityLabel, setActivityLabel] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isAutoScrollEnabledRef = useRef<boolean>(true)
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)
  const [editingMessageText, setEditingMessageText] = useState("")
  const abortControllerRef = useRef<AbortController | null>(null)

  const [attachedFile, setAttachedFile] = useState<{
    name: string
    type: string
    blobUrl: string
    fileId: string
  } | null>(null)
  const [pastedText, setPastedText] = useState<{
    content: string
    name: string
    sizeBytes: number
  } | null>(null)
  const [expandedPastedMessages, setExpandedPastedMessages] = useState<Record<number, boolean>>({})
  const [copiedPastedIndex, setCopiedPastedIndex] = useState<number | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData('text')
    if (text.length > 400 || text.includes('\n')) {
      e.preventDefault()
      const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
      let title = 'Pasted Text'
      if (lines.length > 0) {
        const firstLine = lines[0]
        title = firstLine.length > 25 ? `${firstLine.substring(0, 25)}...` : firstLine
      }
      setPastedText({
        content: text,
        name: title,
        sizeBytes: new Blob([text]).size,
      })
    }
  }

  const [activeConversationId, setActiveConversationId] = useState<string>('00000000-0000-0000-0000-000000000000')
  const [conversations, setConversations] = useState<any[]>([])
  const [convoToDelete, setConvoToDelete] = useState<string | null>(null)

  // ── Voice dictation ────────────────────────────────────────────────────────
  const voice = useVoice((text: string) => setInput(text))

  // ── TTS per-message playback state ─────────────────────────────────────────
  const [activeTtsJobId, setActiveTtsJobId] = useState<string | null>(null)
  const [ttsState, setTtsState] = useState<Record<number, {
    status: 'idle' | 'loading' | 'playing' | 'done' | 'failed'
    blobUrl: string | null
    progress: number
  }>>({})
  const activeTtsAudioRef = useRef<HTMLAudioElement | null>(null)
  const activeTtsIndexRef = useRef<number | null>(null)
  const activeTtsJob = useJob(activeTtsJobId)

  // ── Toast notifications ────────────────────────────────────────────────────
  const [toasts, setToasts] = useState<{ id: string; message: string; type: 'info' | 'error' }[]>([])

  const showToast = useCallback((message: string, type: 'info' | 'error' = 'info') => {
    const id = Date.now().toString()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000)
  }, [])

  // Surface voice hook errors as toasts
  useEffect(() => {
    if (voice.error === 'permission_denied') {
      showToast('Microphone access required for voice input', 'error')
    } else if (voice.error === 'transcription_failed') {
      showToast('Transcription failed — please try again', 'error')
    } else if (voice.error === 'browser_incompatible') {
      showToast('Voice input is not supported in this browser', 'info')
    }
  }, [voice.error, showToast])

  // TTS job completion: play audio or fall back to browser speechSynthesis
  useEffect(() => {
    const idx = activeTtsIndexRef.current
    if (idx === null) return

    if (activeTtsJob.status === 'done' && activeTtsJob.resultBlobUrl) {
      if (activeTtsAudioRef.current) {
        activeTtsAudioRef.current.pause()
        activeTtsAudioRef.current = null
      }
      const audio = new Audio(activeTtsJob.resultBlobUrl)
      activeTtsAudioRef.current = audio
      audio.ontimeupdate = () => {
        if (audio.duration > 0) {
          setTtsState(prev => ({
            ...prev,
            [idx]: { ...prev[idx], progress: Math.round((audio.currentTime / audio.duration) * 100) }
          }))
        }
      }
      audio.onended = () => {
        setTtsState(prev => ({ ...prev, [idx]: { ...prev[idx], status: 'done', progress: 0 } }))
        activeTtsAudioRef.current = null
        activeTtsIndexRef.current = null
      }
      setTtsState(prev => ({ ...prev, [idx]: { ...prev[idx], status: 'playing', blobUrl: activeTtsJob.resultBlobUrl } }))
      audio.play().catch(() => { /* autoplay policy: requires user gesture on some browsers */ })
      setActiveTtsJobId(null)

    } else if (activeTtsJob.status === 'failed') {
      // Azure Speech unavailable — fall back to browser speechSynthesis
      const msgContent = messages[idx]?.content || ''
      if (msgContent) {
        window.speechSynthesis.cancel()
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(msgContent))
      }
      setTtsState(prev => ({ ...prev, [idx]: { ...prev[idx], status: 'done', progress: 0 } }))
      activeTtsIndexRef.current = null
      setActiveTtsJobId(null)
    }
  }, [activeTtsJob.status, activeTtsJob.resultBlobUrl, messages])

  const toggleVoice = useCallback(async () => {
    if (voice.isRecording) {
      voice.stopRecording()
    } else {
      await voice.startRecording()
    }
  }, [voice])

  const handleTTSPlay = useCallback(async (idx: number, content: string) => {
    // Stop any active audio
    if (activeTtsAudioRef.current) {
      activeTtsAudioRef.current.pause()
      activeTtsAudioRef.current = null
    }
    window.speechSynthesis.cancel()
    setActiveTtsJobId(null)

    // Toggle off: if this message is already playing, stop it
    if (ttsState[idx]?.status === 'playing') {
      setTtsState(prev => ({ ...prev, [idx]: { ...prev[idx], status: 'done', progress: 0 } }))
      activeTtsIndexRef.current = null
      return
    }

    activeTtsIndexRef.current = idx
    setTtsState(prev => ({ ...prev, [idx]: { status: 'loading', blobUrl: null, progress: 0 } }))

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) throw new Error('Not authenticated')

      const res = await fetch(`${API_BASE}/v1/agents/speech/tts`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: content, voice: 'auto', conversation_id: activeConversationId }),
      })

      if (!res.ok) throw new Error(`TTS enqueue failed: ${res.status}`)
      const data = await res.json()
      setActiveTtsJobId(data.job_id)
    } catch {
      // Immediate browser fallback on network or quota error
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(content))
      setTtsState(prev => ({ ...prev, [idx]: { status: 'done', blobUrl: null, progress: 0 } }))
      activeTtsIndexRef.current = null
    }
  }, [ttsState, activeConversationId])


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
    // Abort any active stream cleanly before switching — each session is independent
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsStreaming(false)
      setWebSearchStatus('idle')
    }

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

  const triggerStream = async (history: Message[], newUserMessage: string | Message, overrideConvoId?: string) => {
    // 1. Abort any active stream before launching a new one
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    setIsStreaming(true)
    setWebSearchStatus('idle')

    const userMessageObj: Message = typeof newUserMessage === 'string'
      ? { role: 'user', content: newUserMessage }
      : newUserMessage

    // Append the new user message and an assistant placeholder
    const nextMessages: Message[] = [...history, userMessageObj]
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
          conversation_id: overrideConvoId || activeConversationId,
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
              setActivityLabel(data.status === 'searching' ? 'Searching the web...' : 'Search complete.')
            } else if (data.type === 'search_activity') {
              if (data.status === 'searching') {
                setWebSearchStatus('searching')
                setActivityLabel(data.label || 'Searching...')
              } else if (data.status === 'done') {
                setWebSearchStatus('done')
                setActivityLabel(data.label || 'Search complete.')
                if (data.sources && data.sources.length > 0) {
                  // Append sources to the streaming message
                  setMessages((prev) => {
                    const updated = [...prev]
                    if (updated.length > 0) {
                      const lastMsg = updated[updated.length - 1]
                      if (lastMsg.role === 'assistant') {
                        lastMsg.sources = data.sources
                      }
                    }
                    return updated
                  })
                }
              } else if (data.status === 'error') {
                setWebSearchStatus('idle')
                setActivityLabel(data.label || 'Search failed.')
              }
            } else if (data.type === 'image_gen_queued') {
              // AI decided to generate an image — show pending bubble and subscribe
              const imgJobId: string = data.job_id
              const imgPrompt: string = data.prompt || ''

              // Append a pending image bubble after the (possibly still-streaming) text
              setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: imgPrompt, imagePending: true },
              ])

              // Subscribe to job completion via Supabase Realtime
              const imgChannel = supabase
                .channel(`img-job-${imgJobId}`)
                .on(
                  'postgres_changes',
                  { event: 'UPDATE', schema: 'public', table: 'jobs', filter: `id=eq.${imgJobId}` },
                  (imgPayload) => {
                    const j = imgPayload.new
                    if (j.status === 'done' && j.result?.image_url) {
                      setMessages((prev) =>
                        prev.map((m) =>
                          m.imagePending && m.content === imgPrompt
                            ? { ...m, imagePending: false, imageUrl: j.result.image_url }
                            : m
                        )
                      )
                      imgChannel.unsubscribe()
                    } else if (j.status === 'failed') {
                      console.error("Image generation job failed:", j.error)
                      setMessages((prev) =>
                        prev.map((m) =>
                          m.imagePending && m.content === imgPrompt
                            ? { role: 'assistant', content: `Image generation failed: ${j.error || 'Please try again.'}` }
                            : m
                        )
                      )
                      imgChannel.unsubscribe()
                    }
                  }
                )
                .subscribe()

              // 90s stall guard
              setTimeout(() => {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.imagePending && m.content === imgPrompt
                      ? { role: 'assistant', content: 'Image generation timed out. Please try again.' }
                      : m
                  )
                )
                imgChannel.unsubscribe()
              }, 90_000)

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
      console.error("Agent chat stream failed:", err)
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

  // Stop the active stream — aborts the fetch, marks the partial message as stopped
  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last?.role === 'assistant' && last.content.length > 0) {
        next[next.length - 1] = {
          ...last,
          content: last.content + '\n\n*— stopped —*'
        }
      } else if (last?.role === 'assistant') {
        // Remove empty placeholder if nothing was streamed yet
        next.pop()
      }
      return next
    })
    setIsStreaming(false)
    setWebSearchStatus('idle')
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  const handleTriggerUpload = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Allow PDF and images
    const allowedExts = ['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif']
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
    if (!allowedExts.includes(ext)) {
      alert(`Unsupported file type. Allowed extensions: ${allowedExts.join(', ')}`)
      return
    }

    setUploading(true)
    setUploadProgress(0)

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) throw new Error('Authentication session not found.')

      let convoId = activeConversationId
      if (!convoId || convoId === '00000000-0000-0000-0000-000000000000') {
        convoId = crypto.randomUUID()
      }

      // 1. Get secure presigned SAS upload URL from backend
      const sasRes = await fetch(`${API_BASE}/v1/files/upload`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          filename: file.name,
          mime_type: file.type,
          conversation_id: convoId
        })
      })

      if (!sasRes.ok) {
        throw new Error(await sasRes.text())
      }

      const { upload_url, blob_url, file_id } = await sasRes.json()

      // 2. Perform direct PUT upload to Cloudflare R2 / Azure Blob Storage
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', upload_url)
        if (upload_url.includes('blob.core.windows.net')) {
          xhr.setRequestHeader('x-ms-blob-type', 'BlockBlob')
        }
        xhr.setRequestHeader('Content-Type', file.type)

        xhr.upload.onprogress = (evt) => {
          if (evt.lengthComputable) {
            const pct = Math.round((evt.loaded / evt.total) * 100)
            setUploadProgress(pct)
          }
        }

        xhr.onload = () => {
          if (xhr.status === 201 || xhr.status === 200) {
            resolve()
          } else {
            reject(new Error(`Storage upload returned status ${xhr.status}`))
          }
        }

        xhr.onerror = () => reject(new Error('Network error during upload to storage'))
        xhr.send(file)
      })

      setAttachedFile({
        name: file.name,
        type: file.type,
        blobUrl: blob_url,
        fileId: file_id
      })

    } catch (err: any) {
      console.error('File upload error:', err)
      alert(`File upload failed: ${err.message || err}`)
    } finally {
      setUploading(false)
      setUploadProgress(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const triggerAgentJob = async (jobType: 'ocr' | 'vision', blobUrl: string, promptText?: string) => {
    const historyBeforeJob = [...messages]
    setIsStreaming(true)

    let convoId = activeConversationId
    if (!convoId || convoId === '00000000-0000-0000-0000-000000000000') {
      convoId = crypto.randomUUID()
      setActiveConversationId(convoId)
    }

    // Capture file metadata now — before any setState calls clear it
    const fileName = attachedFile?.name || (jobType === 'ocr' ? 'document.pdf' : 'image.png')
    const fileAttachment: Message['fileAttachment'] = { name: fileName, jobType }
    // Plain-text version stored to DB (content field must be a string)
    const userMsgText = promptText
      ? `[${jobType === 'ocr' ? 'Document' : 'Image'} Analysis: ${fileName}] ${promptText}`
      : `[${jobType === 'ocr' ? 'Document' : 'Image'} Analysis: ${fileName}]`

    // Use functional update to avoid stale messages closure
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: userMsgText, fileAttachment },
      { role: 'assistant', content: '' }
    ])
    setAttachedFile(null)

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) throw new Error('Authentication session not found.')

      const endpoint = jobType === 'ocr' ? '/v1/agents/ocr' : '/v1/agents/vision'
      const requestBody = jobType === 'ocr'
        ? { conversation_id: convoId, blob_url: blobUrl }
        : { conversation_id: convoId, blob_url: blobUrl, prompt: promptText || 'Describe the content in this image.' }

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(requestBody)
      })

      if (!res.ok) {
        let errDetail = 'The document analysis service is temporarily unavailable.'
        try {
          const errBody = await res.json()
          errDetail = errBody?.detail || errBody?.message || errDetail
        } catch {
          errDetail = (await res.text()) || errDetail
        }
        throw new Error(errDetail)
      }

      const { job_id } = await res.json()

      // Subscribe to Supabase Realtime updates on the jobs table
      const channel = supabase
        .channel(`job-${job_id}`)
        .on(
          'postgres_changes',
          { event: 'UPDATE', schema: 'public', table: 'jobs', filter: `id=eq.${job_id}` },
          async (payload) => {
            const updatedJob = payload.new
            clearTimeout(stallTimer)
            
            if (updatedJob.status === 'processing') {
               setMessages((prev) => {
                 const next = [...prev]
                 next[next.length - 1] = {
                   role: 'assistant',
                   content: 'Cognitive model actively processing layouts and extracting content...'
                 }
                 return next
               })
            } else if (updatedJob.status === 'done') {
              const textResult = updatedJob.result?.text || 'No result data returned by the agent.'
              
              // Unsubscribe from Supabase realtime job channel
              channel.unsubscribe()

              // Save the system context message containing the analysis results to history
              try {
                await supabase.from('messages').insert([
                  {
                    conversation_id: convoId,
                    role: 'system',
                    content: `[System Context: The user has attached a file. Analysis result: ${textResult}]`,
                    routing_mode: 'discuss'
                  }
                ])
              } catch (dbErr) {
                console.error('Failed to commit system context to history:', dbErr)
              }

              // Trigger the stream response using the LLM. 
              // We pass the userMessageObj with the fileAttachment to keep the UI chip rendered!
              await triggerStream(historyBeforeJob, {
                role: 'user',
                content: userMsgText,
                fileAttachment
              }, convoId)
            } else if (updatedJob.status === 'failed') {
              const errMsg = updatedJob.error || 'Background analysis encountered an error.'
              setMessages((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                // Replace if still in a loading/processing state (empty placeholder or processing message)
                if (last.role === 'assistant' && (
                  last.content === '' ||
                  last.content.includes('processing layouts') ||
                  last.content.includes('Queuing')
                )) {
                  next[next.length - 1] = {
                    role: 'assistant',
                    content: errMsg
                  }
                }
                return next
              })
              setIsStreaming(false)
              channel.unsubscribe()
            }
          }
        )
        .subscribe()

      // Timeout — if Azure Function hasn't updated the job within 90 s, unblock the UI
      let stallTimer = setTimeout(() => {
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          // Replace if still in a loading/processing state (empty placeholder or processing message)
          if (last.role === 'assistant' && (
            last.content === '' ||
            last.content.includes('processing layouts') ||
            last.content.includes('Queuing')
          )) {
            next[next.length - 1] = {
              role: 'assistant',
              content: `Your document has been queued for analysis. Results will be added here automatically once processing completes — this may take a minute.`
            }
          }
          return next
        })
        setIsStreaming(false)
        channel.unsubscribe()
      }, 90_000)

    } catch (err: any) {
      console.error('Agent job trigger failed:', err)
      // err.message is already the clean detail string from our API response parser
      const explanation = err.message && !err.message.startsWith('{') && !err.message.startsWith('Error:')
        ? err.message
        : getFriendlyErrorMessage(err.message || 'unknown')
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = {
          role: 'assistant',
          content: explanation
        }
        return next
      })
      setIsStreaming(false)
    }
  }

  // ── Hybrid Search (Google grounding + Azure synthesis) ───────────────────
  // Patterns that should bypass the normal stream and use the grounding endpoint
  const SEARCH_INTENT_PATTERNS = [
    /^(search|look up|find|what('s| is) (happening|the latest|new)|latest|news|current|today|right now|who (is|are|won)|when (is|did|will)|where (is|are)|how much (is|does))/i,
    /^\/(search|web|google)\s+/i,
  ]

  const triggerHybridSearch = async (userPrompt: string) => {
    const nextMessages: Message[] = [...messages, { role: 'user', content: userPrompt }]
    setMessages([...nextMessages, { role: 'assistant', content: '' }])
    setIsStreaming(true)
    setWebSearchStatus('searching')

    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token
      if (!token) throw new Error('Authentication session not found.')

      const res = await fetch(`${API_BASE}/v1/search/ask-hybrid`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt: userPrompt }),
      })

      setWebSearchStatus('done')

      if (!res.ok) {
        let errMsg = `HTTP ${res.status}`
        try { const d = await res.json(); errMsg = d?.detail || errMsg } catch (_) {}
        throw new Error(errMsg)
      }

      const data = await res.json()
      const answer: string = data.answer || ''
      const sources: Source[] = Array.isArray(data.sources) ? data.sources : []

      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: answer,
          sources: sources.length > 0 ? sources : undefined,
        }
        return updated
      })
    } catch (err: any) {
      setWebSearchStatus('idle')
      const explanation = getFriendlyErrorMessage(err.message || 'unknown')
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'assistant', content: explanation }
        return updated
      })
    } finally {
      setIsStreaming(false)
      setWebSearchStatus('idle')
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isStreaming || uploading) return

    if (attachedFile) {
      const isPdf = attachedFile.type === 'application/pdf' || attachedFile.name.toLowerCase().endsWith('.pdf')
      const jobType = isPdf ? 'ocr' : 'vision'
      const promptText = input.trim()
      setInput('')
      setTimeout(() => inputRef.current?.focus(), 0)
      await triggerAgentJob(jobType, attachedFile.blobUrl, promptText)
      return
    }

    if (!input.trim() && !pastedText) return

    let userMessage = input.trim()
    setInput('')

    if (pastedText) {
      userMessage = userMessage
        ? `${userMessage}\n\n[Pasted Content: ${pastedText.name}]\n\`\`\`\n${pastedText.content}\n\`\`\``
        : `[Pasted Content: ${pastedText.name}]\n\`\`\`\n${pastedText.content}\n\`\`\``
      setPastedText(null)
    }

    setTimeout(() => inputRef.current?.focus(), 0)

    // Route to hybrid search if the message matches a web-search intent pattern
    if (SEARCH_INTENT_PATTERNS.some((p) => p.test(userMessage))) {
      await triggerHybridSearch(userMessage)
      return
    }

    await triggerStream(messages, userMessage)
  }

  const handleEditSubmit = async (index: number) => {
    const newText = editingMessageText.trim()
    if (!newText || isStreaming) return

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
            <div className="max-w-2xl mx-auto space-y-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`group relative flex w-full gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {/* Avatar only for assistant */}
                  {msg.role !== 'user' && (
                    <div className="w-8 h-8 rounded-lg border border-[#c5a880]/15 bg-brand-surface/30 flex items-center justify-center shrink-0 overflow-hidden mt-1 select-none">
                      <img
                        src="/favicon.png"
                        alt="Ochuko"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}

                  {/* Right/Left side container: Bubble + Actions */}
                  <div className={`flex flex-col gap-1.5 ${msg.role === 'user' ? 'max-w-[85%] items-end' : 'flex-1 min-w-0'}`}>
                    {/* Bubble */}
                    <div
                      className={`relative rounded-xl px-5 py-4 min-w-0 ${
                        msg.role === 'user'
                          ? 'bg-[#1c1e22]/50 border border-[#2b2e35] text-brand-text/90 rounded-tr-none'
                          : 'bg-transparent border-transparent md:px-2'
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
                        ) : msg.fileAttachment ? (
                          // Agent job — render as file chip + optional prompt text
                          <div className="space-y-2">
                            <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-[#c5a880]/8 border border-[#c5a880]/20">
                              <FileText className="w-4 h-4 text-[#c5a880] shrink-0" />
                              <div className="min-w-0">
                                <p className="text-[11px] font-bold text-[#c5a880] uppercase tracking-widest">
                                  {msg.fileAttachment.jobType === 'ocr' ? 'Document Analysis' : 'Image Analysis'}
                                </p>
                                <p className="text-[13px] text-brand-text/90 font-medium truncate">
                                  {msg.fileAttachment.name}
                                </p>
                              </div>
                            </div>
                            {/* Show any prompt text the user typed alongside the file */}
                            {msg.content.includes('] ') && (
                              <p className="text-[13.5px] text-brand-text/90 leading-[1.7] font-medium whitespace-pre-wrap">
                                {msg.content.replace(/^\[.*?\] /, '')}
                              </p>
                            )}
                          </div>
                        ) : (
                          (() => {
                            const parsed = parsePastedText(msg.content)
                            if (parsed.hasPastedText) {
                              const isExpanded = !!expandedPastedMessages[i]
                              return (
                                <div className="space-y-2">
                                  {parsed.textPrefix && (
                                    <p className="text-[13.5px] text-brand-text/90 leading-[1.7] font-medium whitespace-pre-wrap">
                                      {parsed.textPrefix}
                                    </p>
                                  )}
                                  <div
                                    onClick={() => setExpandedPastedMessages(prev => ({ ...prev, [i]: !prev[i] }))}
                                    className="flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-lg bg-[#c5a880]/8 border border-[#c5a880]/20 cursor-pointer hover:bg-[#c5a880]/15 transition-all duration-150 select-none max-w-sm"
                                  >
                                    <div className="flex items-center gap-2 min-w-0">
                                      <FileText className="w-4 h-4 text-[#c5a880] shrink-0" />
                                      <div className="min-w-0">
                                        <p className="text-[11px] font-bold text-[#c5a880] uppercase tracking-widest leading-none mb-1">
                                          Pasted Content
                                        </p>
                                        <p className="text-[12px] text-brand-text/90 font-medium truncate">
                                          {parsed.pastedName}
                                        </p>
                                      </div>
                                    </div>
                                    <div className="text-[#8e95a2] hover:text-[#c5a880] shrink-0">
                                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                    </div>
                                  </div>
                                  
                                  {isExpanded && (
                                    <div className="bg-[#0d0f11] border border-[#1e2025] rounded-lg p-3 relative group/panel">
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          navigator.clipboard.writeText(parsed.pastedContent || '')
                                          setCopiedPastedIndex(i)
                                          setTimeout(() => setCopiedPastedIndex(null), 2000)
                                        }}
                                        className="absolute right-2 top-2 p-1.5 rounded bg-white/5 hover:bg-white/10 text-[#8e95a2] hover:text-brand-text transition opacity-0 group-hover/panel:opacity-100"
                                        title="Copy content"
                                      >
                                        {copiedPastedIndex === i ? (
                                          <Check className="w-3 h-3 text-green-400" />
                                        ) : (
                                          <Copy className="w-3 h-3" />
                                        )}
                                      </button>
                                      <pre className="text-[11.5px] font-mono text-brand-text/80 overflow-x-auto max-h-96 whitespace-pre-wrap break-all pr-8 select-text">
                                        {parsed.pastedContent}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                              )
                            }
                            return (
                              <p className="text-[13.5px] text-brand-text/90 leading-[1.7] font-medium whitespace-pre-wrap">
                                {msg.content}
                              </p>
                            )
                          })()
                        )
                      ) : msg.content === '' && isStreaming ? (
                        // Typing / searching indicator — appears immediately before first token
                        <div className="flex items-center gap-2 h-6">
                          {webSearchStatus === 'searching' ? (
                            <>
                              <Globe className="w-3.5 h-3.5 text-[#c5a880] animate-pulse" />
                              <span className="text-[11px] text-[#c5a880]/70 font-semibold tracking-wide">
                                {activityLabel || 'Searching the web...'}
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
                      ) : msg.imagePending ? (
                        // FLUX generation in progress — shimmer placeholder
                        <ImagePending prompt={msg.content || undefined} />
                      ) : msg.imageUrl ? (
                        // Image ready — premium bubble with download
                        <ImageBubble url={msg.imageUrl} prompt={msg.content || undefined} />
                      ) : (
                        // Rendered markdown
                        <div className="space-y-0.5">
                          {renderMarkdown(msg.content)}
                        </div>
                      )}
                    </div>

                    {/* Source badges — shown below assistant bubbles when hybrid search is used */}
                    {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1 px-1">
                        {msg.sources.map((src, si) => (
                          <a
                            key={si}
                            href={src.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={src.url}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#1e2025] bg-[#0d0f11]/80 hover:border-[#c5a880]/40 hover:bg-[#c5a880]/5 transition-all duration-150 group/badge max-w-[220px]"
                          >
                            {/* Favicon */}
                            <img
                              src={`https://www.google.com/s2/favicons?sz=16&domain=${(() => {
                                try {
                                  return new URL(src.url).hostname
                                } catch (_) {
                                  return ''
                                }
                              })()}`}
                              alt=""
                              className="w-3 h-3 rounded-sm shrink-0 opacity-70 group-hover/badge:opacity-100"
                              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                            />
                            <span className="text-[10px] font-semibold text-[#8e95a2] group-hover/badge:text-[#c5a880] truncate tracking-tight transition-colors duration-150">
                              {src.title.length > 28 ? src.title.slice(0, 28) + '…' : src.title}
                            </span>
                            <span className="text-[9px] text-[#8e95a2]/40 group-hover/badge:text-[#c5a880]/50 shrink-0 transition-colors duration-150">↗</span>
                          </a>
                        ))}
                      </div>
                    )}

                    {/* Actions Row at the bottom (outside the bubble), visible on hover */}
                    {((msg.role === 'assistant' && msg.content.length > 0) || (msg.role === 'user' && editingMessageIndex !== i)) && (
                      <div className="flex items-center gap-3.5 px-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        {msg.content.length > 0 && (
                          <button
                            onClick={() => handleCopy(msg.content, i)}
                            title={msg.role === 'user' ? "Copy prompt" : "Copy response"}
                            className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase"
                          >
                            {copiedIndex === i ? (
                              <>
                                <Check className="w-3.5 h-3.5 text-[#c5a880]" />
                                <span className="text-[#c5a880]">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3.5 h-3.5" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        )}

                        {/* TTS Listen/Stop button — assistant messages only */}
                        {msg.role === 'assistant' && msg.content.length > 0 && (
                          <>
                            <button
                              id={`tts-play-${i}`}
                              type="button"
                              onClick={() => handleTTSPlay(i, msg.content)}
                              title={ttsState[i]?.status === 'playing' ? 'Stop audio' : 'Listen to response'}
                              className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase"
                            >
                              {ttsState[i]?.status === 'loading' ? (
                                <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Loading</span></>
                              ) : ttsState[i]?.status === 'playing' ? (
                                <><Square className="w-3.5 h-3.5 fill-current" /><span>Stop</span></>
                              ) : (
                                <><Volume2 className="w-3.5 h-3.5" /><span>Listen</span></>
                              )}
                            </button>
                            {/* Audio progress bar — visible only while playing */}
                            {ttsState[i]?.status === 'playing' && (
                              <div className="w-16 h-[2px] bg-[#1a1d20] rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-[#c5a880]/70 transition-all duration-500"
                                  style={{ width: `${ttsState[i]?.progress ?? 0}%` }}
                                />
                              </div>
                            )}
                          </>
                        )}

                        {msg.role === 'user' && editingMessageIndex !== i && (
                          <button
                            onClick={() => {
                              if (isStreaming) return
                              setEditingMessageIndex(i)
                              setEditingMessageText(msg.content)
                            }}
                            disabled={isStreaming}
                            title="Edit prompt"
                            className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            <Pencil className="w-3.5 h-3.5" />
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

          {/* Attached File Preview */}
          {attachedFile && (
            <div className="max-w-2xl mx-auto mb-2 flex items-center justify-between p-2 bg-[#0d0f11] border border-[#1e2025] rounded-lg">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-[#c5a880]" />
                <span className="text-[11px] text-brand-text/80 font-medium truncate max-w-[180px]">
                  {attachedFile.name}
                </span>
                <span className="text-[9px] text-[#c5a880] tracking-wider uppercase bg-[#c5a880]/10 px-1.5 py-0.5 rounded border border-[#c5a880]/20 font-bold font-mono">
                  {attachedFile.type.split('/')[1] || 'pdf'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setAttachedFile(null)}
                className="p-1 text-[#8e95a2] hover:text-red-400 transition"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Pasted Text Preview */}
          {pastedText && (
            <div className="max-w-2xl mx-auto mb-2 flex items-center justify-between p-2 bg-[#0d0f11] border border-[#1e2025] rounded-lg">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-[#c5a880]" />
                <span className="text-[11px] text-brand-text/80 font-medium truncate max-w-[220px]">
                  {pastedText.name}
                </span>
                <span className="text-[9px] text-[#c5a880] tracking-wider uppercase bg-[#c5a880]/10 px-1.5 py-0.5 rounded border border-[#c5a880]/20 font-bold font-mono">
                  {(pastedText.sizeBytes / 1024).toFixed(1)} KB
                </span>
              </div>
              <button
                type="button"
                onClick={() => setPastedText(null)}
                className="p-1 text-[#8e95a2] hover:text-red-400 transition"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Uploading progress indicator */}
          {uploading && (
            <div className="max-w-2xl mx-auto mb-2 flex items-center justify-between p-2 bg-[#0d0f11] border border-[#1e2025]/50 rounded-lg animate-pulse">
              <div className="flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 text-[#c5a880] animate-spin" />
                <span className="text-[11px] text-[#c5a880] font-semibold tracking-wide">
                  Uploading to secure storage... {uploadProgress !== null ? `${uploadProgress}%` : ''}
                </span>
              </div>
            </div>
          )}

          {/* Voice recording status strip — waveform + label, shown while recording */}
          {voice.isRecording && (
            <div className="max-w-2xl mx-auto mb-2 flex items-center justify-between px-1">
              <div className="flex items-center gap-2.5">
                <VoiceWaveform volume={voice.currentVolume} />
                <span className="text-[10px] font-bold text-[#c5a880]/80 tracking-widest uppercase"
                  style={{ animation: 'pulse 1.5s ease-in-out infinite' }}
                >
                  Listening...
                </span>
              </div>
              <span className="text-[9px] text-brand-muted/40 font-medium select-none">
                {voice.currentVolume > 0.08 ? 'Voice detected' : 'Waiting for speech...'}
              </span>
            </div>
          )}

          {/* Input */}
          <form onSubmit={handleSend} className="max-w-2xl mx-auto relative flex items-center gap-2">
            <div className="relative flex-1">
              {/* Mic button — hidden when browser doesn’t support MediaRecorder */}
              {voice.isSupported && (
                <button
                  id="voice-mic-button"
                  type="button"
                  onClick={toggleVoice}
                  disabled={isStreaming || uploading}
                  title={voice.isRecording ? 'Stop recording' : 'Voice input'}
                  aria-label={voice.isRecording ? 'Stop recording' : 'Start voice input'}
                  className={`absolute left-3 top-3.5 p-0.5 transition-all duration-150 active:scale-95 rounded z-10 disabled:opacity-20 ${
                    voice.isRecording
                      ? 'text-[#c5a880] voice-pulse-ring'
                      : 'text-[#8e95a2] hover:text-[#c5a880] hover:bg-white/5'
                  }`}
                >
                  <Mic className="w-4 h-4" />
                </button>
              )}
              <input
                ref={inputRef}
                type="text"
                value={input}
                onPaste={handlePaste}
                onChange={(e) => {
                  setInput(e.target.value)
                  // User manually edited — detach from live transcript
                  if (voice.isRecording) voice.clearTranscript()
                }}
                disabled={isStreaming || uploading}
                placeholder={
                  voice.isRecording ? 'Listening...' :
                  isStreaming ? 'Agent is thinking...' :
                  attachedFile ? 'Add prompt details for the agent...' :
                  pastedText ? 'Add prompt details for the pasted text...' : 'Submit an inquiry...'
                }
                className={`w-full h-12 bg-[#0d0f11]/80 border rounded-xl pr-14 text-[13.5px] text-brand-text focus:outline-none focus:ring-1 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed input-masked-fade ${
                  voice.isSupported ? 'pl-10' : 'pl-4 no-mic'
                } ${
                  voice.isRecording
                    ? 'border-[#c5a880]/40 focus:border-[#c5a880]/60 focus:ring-[#c5a880]/20 placeholder-[#c5a880]/50'
                    : 'border-[#1a1d20] focus:border-[#c5a880]/40 focus:ring-[#c5a880]/15 placeholder-[#8e95a2]/40'
                }`}
              />
              {voice.isTranscribing && <div className="input-loading-bar" aria-hidden />}
              <button
                type="button"
                onClick={handleTriggerUpload}
                disabled={uploading}
                className="absolute right-3 top-3.5 p-0.5 text-[#8e95a2] hover:text-[#c5a880] hover:bg-white/5 rounded transition duration-150 active:scale-95 disabled:opacity-20"
                title="Attach document or image"
              >
                <Paperclip className="w-4 h-4" />
              </button>
            </div>

            {isStreaming ? (
              // Stop button — aborts the active model stream only, not Azure background jobs
              <button
                type="button"
                onClick={handleStop}
                aria-label="Stop generation"
                title="Stop generation"
                className="w-12 h-12 bg-[#1a1c20] border border-[#2b2e35] text-[#c5a880] rounded-xl flex items-center justify-center hover:bg-[#c5a880]/10 hover:border-[#c5a880]/40 transition duration-150 active:scale-95 shadow-md shrink-0 group"
              >
                <Square className="w-[14px] h-[14px] fill-[#c5a880] group-hover:fill-[#d4b990] transition duration-150" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={uploading || (!input.trim() && !attachedFile && !pastedText)}
                aria-label="Send"
                className="w-12 h-12 bg-[#c5a880] text-[#08090a] rounded-xl flex items-center justify-center hover:bg-[#d4b990] transition duration-150 disabled:opacity-20 active:scale-95 shadow-md shadow-[#c5a880]/10 font-bold shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            )}

            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileChange}
              accept=".pdf,.png,.jpg,.jpeg,.webp,.gif"
              className="hidden"
            />
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

      {/* Toast notification container — top-right, non-blocking */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none" aria-live="polite">
        {toasts.map(t => (
          <div
            key={t.id}
            className={`px-4 py-2.5 rounded-xl border text-[12px] font-semibold tracking-wide shadow-xl shadow-black/40 backdrop-blur-md ${
              t.type === 'error'
                ? 'bg-red-950/90 border-red-500/20 text-red-300'
                : 'bg-[#0d0f11]/90 border-[#c5a880]/20 text-brand-text'
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </div>
  )
}


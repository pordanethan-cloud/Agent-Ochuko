// @refresh reset
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'

import { supabase, getEffectiveToken } from '../utils/supabaseClient'
import { wakeBackend } from '../utils/wakeBackend'

import { LogOut, Send, Square, Brain, Cpu, MessageSquare, Menu, Copy, Check, Globe, Pencil, Trash, Paperclip, FileText, Loader2, X, ChevronDown, ChevronUp, Search, Lock, Download, Share2, Settings, Maximize2, Minimize2, ExternalLink, KeyRound, Unlock, Plus, Minus, Mic, MoreVertical, Bot, Eye, Code2, Folder, FolderPlus, Terminal } from 'lucide-react'

import { useNavigate, useLocation } from 'react-router-dom'
import { AppLock } from '../components/AppLock'
import { useVoice } from '../hooks/useVoice'
import {
  AgentExecutionStepper,
  AgentHITLApprovalCard,
  AgentUserInputCard,
  AgentSiteDeploymentCard,
  TurnTracker,
  AgentFileChangesCard,
} from '../components/AgentModeWidgets'
import type { PlanStepItem, AgentTaskData } from '../components/AgentModeWidgets'
import { ArtifactPanel } from '../components/ArtifactPanel'
import { RepositoryDeliverableCard } from '../components/RepositoryDeliverableCard'
import { SportsMatchCard } from '../components/SportsMatchCard'
import { OptionsCard } from '../components/OptionsCard'
import { ZipAppPreviewer } from '../components/ZipAppPreviewer'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { safeRandomUUID } from '../utils/safeRandom'





const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// ─── Artifact helpers ──────────────────────────────────────────────────────────
// Single presentation path: every artifact open routes through the
// `open-file-preview` event → ArtifactPanel (Ochuko right dock).
// The old inline sidebar/fullscreen artifact UI is retired for text artifacts.

function mimeFromName(name: string): string {
  const ext = (name || '').toLowerCase().split('.').pop() || ''
  const map: Record<string, string> = {
    // Web & Code
    html: 'text/html', htm: 'text/html', css: 'text/css',
    js: 'text/javascript', mjs: 'text/javascript', cjs: 'text/javascript',
    ts: 'text/typescript', tsx: 'text/typescript', jsx: 'text/javascript',
    json: 'application/json', md: 'text/markdown', markdown: 'text/markdown',
    txt: 'text/plain', py: 'text/x-python', yaml: 'text/yaml', yml: 'text/yaml',
    xml: 'application/xml', sql: 'text/x-sql', sh: 'application/x-sh', bash: 'application/x-sh',
    bat: 'application/x-msdos-program', cmd: 'text/plain', ps1: 'text/plain',
    java: 'text/x-java-source', c: 'text/x-c', cpp: 'text/x-c', cc: 'text/x-c', h: 'text/x-c', hpp: 'text/x-c',
    cs: 'text/plain', rs: 'text/rust', go: 'text/x-go', rb: 'text/x-ruby', php: 'text/x-php',
    kt: 'text/x-kotlin', gradle: 'text/plain', properties: 'text/plain', ini: 'text/plain', cfg: 'text/plain',
    toml: 'application/toml', env: 'text/plain', dockerfile: 'text/plain', graphql: 'application/graphql', gql: 'application/graphql',
    proto: 'text/plain', pb: 'application/x-protobuf', swift: 'text/x-swift', scala: 'text/x-scala', r: 'text/x-r', lua: 'text/x-lua',
    dart: 'application/dart', zig: 'text/plain', sol: 'text/plain', wasm: 'application/wasm',
    diff: 'text/x-diff', patch: 'text/x-diff', vue: 'text/plain', svelte: 'text/plain',
    tex: 'text/x-tex', log: 'text/plain', ipynb: 'application/json',
    // Tabular & Spreadsheets
    csv: 'text/csv', tsv: 'text/tab-separated-values',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    xls: 'application/vnd.ms-excel', xlsm: 'application/vnd.ms-excel.sheet.macroEnabled.12',
    ods: 'application/vnd.oasis.opendocument.spreadsheet', parquet: 'application/octet-stream',
    // Documents
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ppt: 'application/vnd.ms-powerpoint',
    rtf: 'application/rtf', odt: 'application/vnd.oasis.opendocument.text',
    odp: 'application/vnd.oasis.opendocument.presentation', epub: 'application/epub+zip',
    // Compressed Archives & Disk Images
    zip: 'application/zip', tar: 'application/x-tar', gz: 'application/gzip',
    tgz: 'application/gzip', bz2: 'application/x-bzip2', tbz2: 'application/x-bzip2',
    xz: 'application/x-xz', txz: 'application/x-xz', '7z': 'application/x-7z-compressed',
    rar: 'application/vnd.rar', zst: 'application/zstd', lzma: 'application/x-lzma',
    cab: 'application/vnd.ms-cab-compressed', iso: 'application/x-iso9660-image', dmg: 'application/x-apple-diskimage',
    // Images & Media
    svg: 'image/svg+xml', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
    webp: 'image/webp', gif: 'image/gif', bmp: 'image/bmp', ico: 'image/x-icon',
    tiff: 'image/tiff', tif: 'image/tiff', avif: 'image/avif', heic: 'image/heic', heif: 'image/heif',
    // Audio (including WhatsApp voice notes & recordings)
    mp3: 'audio/mpeg', wav: 'audio/wav', m4a: 'audio/mp4', ogg: 'audio/ogg',
    opus: 'audio/opus', oga: 'audio/ogg', amr: 'audio/amr', flac: 'audio/flac', aac: 'audio/aac',
  }
  return map[ext] || 'text/plain'
}

// When a batch of generated files is a multi-file project, prefer the
// index.html entry so the preview renders the real site (styles included).
function pickEntryFile<T extends { filename: string; download_url?: string; size_bytes?: number }>(files: T[]): T | null {
  const entry = files.find(f => {
    const n = (f.filename || '').toLowerCase()
    return n === 'index.html' || n.endsWith('/index.html')
  })
  return entry || files[0] || null
}

function dispatchOpenFilePreview(detail: {
  name: string
  type: string
  url?: string
  sizeBytes?: number
  content?: string
  siteSlug?: string
  projectFiles?: Record<string, string> | Array<{ name: string; content?: string; url?: string; sizeBytes?: number; type?: string }>
  siblingFiles?: Array<{ name: string; content?: string; url?: string; sizeBytes?: number; type?: string }>
}) {
  window.dispatchEvent(new CustomEvent('open-file-preview', { detail }))
}

// ─── Visit Tracking ───────────────────────────────────────────────────────────────

interface VisitData {
  firstVisit: number
  lastVisit: number
  visitCount: number
  consecutiveDays: number
}

function getVisitData(): VisitData {
  const stored = localStorage.getItem('visit_data')
  if (stored) {
    try {
      return JSON.parse(stored)
    } catch {
      // Corrupted data, start fresh
    }
  }
  return {
    firstVisit: Date.now(),
    lastVisit: Date.now(),
    visitCount: 1,
    consecutiveDays: 1
  }
}

function updateVisitData(): VisitData {
  const current = getVisitData()
  const now = Date.now()
  const oneDay = 24 * 60 * 60 * 1000
  const daysSinceLast = Math.floor((now - current.lastVisit) / oneDay)
  
  let newConsecutiveDays = current.consecutiveDays
  if (daysSinceLast === 1) {
    newConsecutiveDays++
  } else if (daysSinceLast > 1) {
    newConsecutiveDays = 1
  }
  
  const updated: VisitData = {
    firstVisit: current.firstVisit,
    lastVisit: now,
    visitCount: current.visitCount + 1,
    consecutiveDays: newConsecutiveDays
  }
  
  localStorage.setItem('visit_data', JSON.stringify(updated))
  return updated
}

// ─── Name Extraction ─────────────────────────────────────────────────────────────

function extractFirstName(email: string): string {
  if (!email) return ''
  const localPart = email.split('@')[0]
  const cleaned = localPart.replace(/[0-9._-]/g, ' ').trim()
  const parts = cleaned.split(/\s+/).filter(p => p.length > 0)
  if (parts.length > 0) {
    return parts[0].charAt(0).toUpperCase() + parts[0].slice(1).toLowerCase()
  }
  return ''
}

/**
 * Returns FIRST NAME ONLY.
 * Priority: preferredName first word → email local-part first word → honorific.
 */
function getDisplayName(preferredName: string | null, userEmail: string | null): string {
  if (preferredName && preferredName.trim()) {
    // Always use only the first word of the preferred name
    const firstName = preferredName.trim().split(/\s+/)[0]
    return firstName.charAt(0).toUpperCase() + firstName.slice(1)
  }
  if (userEmail) {
    const firstName = extractFirstName(userEmail)
    if (firstName) return firstName
  }
  // Neutral fallback — no career/role titles
  return 'there'
}

// ─── Time-Based Greetings & Context ──────────────────────────────────────────

function getTimeGreeting(hour: number): string {
  if (hour >= 5  && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function getDynamicGreeting(preferredName: string | null, userEmail: string | null): string {
  updateVisitData()
  const hour      = new Date().getHours()
  const firstName = getDisplayName(preferredName, userEmail)
  const greeting  = getTimeGreeting(hour)
  return `${greeting}, ${firstName}`
}

// ─── Chat Auto-Title (client-side, no server call) ───────────────────────────

/**
 * Generates a short human-readable title from the first user message.
 * Strips markdown/code fences, takes the first 6 meaningful words,
 * truncates to 50 chars. Runs entirely in memory — no network call.
 */
function generateAutoTitle(firstUserMessage: string): string {
  if (!firstUserMessage?.trim()) return 'Untitled Session'

  // Strip markdown artifacts, URLs, code fences
  let text = firstUserMessage
    .replace(/```[\s\S]*?```/g, '')      // code blocks
    .replace(/`[^`]+`/g, '')             // inline code
    .replace(/https?:\/\/\S+/g, '')      // URLs
    .replace(/[#*_~>|\[\]]/g, '')        // markdown symbols
    .replace(/\s+/g, ' ')
    .trim()

  // Split into words, filter stopwords for a cleaner title
  const STOP = new Set([
    'a','an','the','is','are','was','were','be','been','being',
    'i','me','my','we','our','you','your','it','its','and','or','but',
    'so','if','in','on','at','to','of','for','by','with','from','that',
    'this','how','what','why','when','where','who','can','could','should',
    'would','will','do','does','did','have','has','had','get','got','make',
    'use','just','like','also','then','than','as','up','about','which',
    'some','any','all','not','no','yes','please','help','tell','show',
    'give','need','want','know','think','feel','look','see','put','take',
  ])

  const words = text.split(' ').filter(w => w.length > 1)
  const meaningful = words.filter(w => !STOP.has(w.toLowerCase()))

  // Use meaningful words if ≥2 survive, else fall back to raw words (skip stopwords-only inputs)
  const chosen = meaningful.length >= 2 ? meaningful : words
  const title  = chosen.slice(0, 6).join(' ')

  // Capitalise first letter, truncate at 50 chars
  const capped = title.charAt(0).toUpperCase() + title.slice(1)
  return capped.length > 52 ? capped.slice(0, 50) + '…' : capped
}

// ─── KaTeX lazy-loader ────────────────────────────────────────────────────────

// Only loads the KaTeX bundle when a '$' is detected in a message.

// After first load it's browser-cached — subsequent renders are instant.

export function useKaTeX(active: boolean) {

  const [katexReady, setKatexReady] = useState(false)

  useEffect(() => {

    if (!active || katexReady) return

    Promise.all([

      import('katex/dist/katex.min.css' as any).catch(() => {}),

      import('katex'),

    ]).then(([_, katexModule]) => {
      const k = (katexModule as any).default || katexModule;
      (window as any).katex = k;
      (window as any).__katex = k;
      setKatexReady(true)
    }).catch(() => {})

  }, [active])

  return katexReady

}

/*
function renderLatex(tex: string, displayMode: boolean): React.ReactNode {
  try {
    // @ts-ignore — katex loaded lazily
    const katex = (window as any).__katex || require('katex')
    const html = katex.renderToString(tex, { displayMode, throwOnError: false })
    return (
      <span
        className={displayMode ? 'block my-3 text-center overflow-x-auto' : 'inline'}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    )
  } catch {
    return <code className="text-brand-accent">{tex}</code>
  }
}
*/

interface Source {

  title: string

  url: string

}

interface Message {

  role: 'user' | 'assistant'

  content: string

  routing_mode?: string

  routing_reason?: string

  fileAttachment?: { name: string; jobType: 'ocr' | 'vision' | 'code'; url?: string }

  fileAttachments?: { name: string; jobType: 'ocr' | 'vision' | 'code'; url?: string }[]

  sources?: Source[]

  imageUrl?: string

  imagePending?: boolean

  imagePrompt?: string

  imageJobId?: string

  agentStep?: number

  agentMaxSteps?: number

  agentLabel?: string

  agentTodos?: { content: string; status: string }[]

  agentOrient?: { iteration: number; progressed?: boolean; observations?: { name: string; status: string; summary: string }[] }

  widgetData?: { code: string; title: string; loadingMessages?: string[]; widgetType?: string; widgetLoading?: boolean }[]

  displayCards?: { card_type: string; payload: any; summary?: string }[]

  timestamp?: number     // Unix ms — set at send/receive time for relative display

  generatedFiles?: { filename: string; download_url: string; size_bytes: number }[]

  thinkingContent?: string   // Reasoning text from <thinking> blocks (THINK/SOLVE modes)

  isCompactionMarker?: boolean  // Synthetic message: marks where context was compacted + summarised

  compactionSummary?: string    // The summary text produced during compaction

  isArchived?: boolean          // Indicates if this message was archived due to compaction

  agentTaskData?: AgentTaskData // Autonomous Agent Mode task plan and execution data

  agentApprovalRequired?: {     // In-chat HITL safety confirmation gate
    step: PlanStepItem
    taskId: string
    reason?: string
  }

  agentUserInputRequired?: {    // Interactive clarification question / options prompt
    taskId: string
    stepIndex: number
    question: string
    options: string[]
    selectType?: string
  }

}

const triggerDirectDownload = async (url: string, fallbackFilename: string) => {
  let filename = fallbackFilename
  try {
    const urlParts = url.split('/')
    const lastPart = urlParts[urlParts.length - 1].split('?')[0]
    if (lastPart && lastPart.includes('.')) {
      filename = decodeURIComponent(lastPart)
    }
  } catch (_) {}

  try {
    const token = await getEffectiveToken()
    const headers: Record<string, string> = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const res = await fetch(url, { headers })
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    // iOS Safari aborts blob downloads if the URL is revoked synchronously
    // after click(); delay the revoke so the download has time to start.
    setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000)
  } catch (err) {
    console.error("Direct download failed, falling back to window.open:", err)
    try {
      const token = await getEffectiveToken()
      let finalUrl = url
      if (token && !finalUrl.includes('token=')) {
        finalUrl += (finalUrl.includes('?') ? '&' : '?') + `token=${encodeURIComponent(token)}`
      }
      window.open(finalUrl, '_blank')
    } catch (_) {
      window.open(url, '_blank')
    }
  }
}

// ─── Docx Preview Component ───────────────────────────────────────────────────

interface DocxPreviewProps {
  url: string
}

export function DocxPreview({ url }: DocxPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    if (!url) return

    setLoading(true)
    setError(null)

    fetch(url)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)
        return res.arrayBuffer()
      })
      .then(async (arrayBuffer) => {
        if (!active) return
        if (containerRef.current) {
          containerRef.current.innerHTML = ''
          try {
            // Lazy load docx-preview
            const docxModule = await import('docx-preview')
            const renderFn = docxModule.renderAsync || (docxModule as any).default?.renderAsync
            if (!renderFn) {
              throw new Error("renderAsync not found in docx-preview module")
            }
            await renderFn(arrayBuffer, containerRef.current, undefined, {
              className: "docx-rendered",
              inWrapper: false,
              ignoreWidth: true,
              ignoreHeight: true,
              debug: false
            })
          } catch (renderErr) {
            console.error("docx-preview render failed:", renderErr)
            throw renderErr
          }
        }
      })
      .then(() => {
        if (active) setLoading(false)
      })
      .catch(err => {
        console.error("Failed to render DOCX:", err)
        if (active) {
          setError("Failed to load or parse DOCX document.")
          setLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [url])

  return (
    <div className="w-full h-full min-h-[500px] flex flex-col bg-white text-black p-4 rounded-lg overflow-auto select-text relative">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
          <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center p-6 text-red-500 font-semibold bg-white/95 text-center z-10">
          {error}
        </div>
      )}
      <div ref={containerRef} className="w-full prose max-w-none text-left docx-container" />
    </div>
  )
}

// ─── Generated file download card ─────────────────────────────────────────────

function FileDownloadCard({
  filename,
  download_url,
  size_bytes,
  onView
}: {
  filename: string
  download_url: string
  size_bytes: number
  onView?: () => void
}) {
  // Guards: backend SSE payloads occasionally omit filename/size_bytes — a
  // throw here (e.g. undefined.split) would crash the whole app at render time.
  const safeName = filename || 'Unnamed file'
  const ext = safeName.split('.').pop()?.toLowerCase() || ''
  const extLabel = ext.toUpperCase() || 'FILE'
  const size = size_bytes || 0
  const sizeLabel = size > 1024 * 1024
    ? `${(size / (1024 * 1024)).toFixed(1)} MB`
    : size > 1024
    ? `${(size / 1024).toFixed(1)} KB`
    : size > 0 ? `${size} B` : ''

  // Two-colour discipline: one neutral tile for every file type.
  const hasUrl = download_url && !download_url.startsWith('sandbox:') && !download_url.includes('/mnt/data/')

  return (
    <div className="mt-2 flex items-center gap-3 px-3.5 py-2.5 rounded-lg border border-white/10 bg-brand-card/60 hover:bg-brand-card hover:border-white/25 transition-all duration-200 group/dl w-full select-none">
      {/* File type icon — neutral, palette-consistent */}
      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border border-white/10 bg-white/[0.05]">
        <span className="text-[9px] font-black tracking-tight text-white/70">{extLabel}</span>
      </div>

      {/* File info */}
      <div className="flex-1 min-w-0">
        <p className="text-[12.5px] font-semibold text-brand-text truncate leading-tight">{safeName}</p>
        {sizeLabel && <p className="text-[10px] text-[#8e95a2] mt-0.5">{sizeLabel}</p>}
        {!hasUrl && (
          <p className="text-[10px] text-white/40 mt-0.5">Sandbox file — ask me to resend it for a download link</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5 shrink-0">
        {onView && hasUrl && (
          <button
            onClick={onView}
            className="px-2.5 py-1 rounded-lg text-[10px] font-semibold text-[#8e95a2] hover:text-brand-text border border-[#ffffff]/10 hover:border-[#ffffff]/25 hover:bg-white/5 transition duration-150"
            title="View file"
          >
            View
          </button>
        )}
        {hasUrl ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              triggerDirectDownload(download_url, filename)
            }}
            className="w-8 h-8 rounded-lg flex items-center justify-center border border-[#ffffff]/15 hover:border-[#ffffff]/40 bg-[#ffffff]/5 hover:bg-[#ffffff]/10 text-[#8e95a2] hover:text-brand-text transition duration-150"
            title={`Download ${safeName}`}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
        ) : (
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center border border-white/10 bg-white/[0.03] text-white/25 cursor-not-allowed"
            title="Sandbox-only file — ask the agent to resend for a downloadable link"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Inline Widget Renderer Component (visualize__show_widget) ───────────

function WidgetRenderer({
  code,
  title,
  loadingMessages: _loadingMessages = [],
  widgetType: _widgetType = 'diagram',
  widgetLoading = false,
}: {
  code: string
  title: string
  loadingMessages?: string[]
  widgetType?: string
  widgetLoading?: boolean
}) {
  const [fullscreen, setFullscreen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [iframeHeight, setIframeHeight] = useState(340)
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close actions dropdown on click outside
  useEffect(() => {
    const clickOutside = (e: MouseEvent) => {
      if (menuOpen && menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', clickOutside)
    return () => document.removeEventListener('mousedown', clickOutside)
  }, [menuOpen])

  // Dynamically auto-resize iframe to fit content size exactly
  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (e.data && e.data.type === 'resize-iframe') {
        const height = parseInt(e.data.height, 10);
        if (!isNaN(height) && height > 0) {
          // Keep dynamic height within healthy preview bounds (180px to 800px)
          setIframeHeight(Math.max(180, Math.min(800, height)));
        }
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const loadingMessages = _loadingMessages.length > 0 ? _loadingMessages : ['Assembling visual...']

  // Cycle loading messages every 800ms while in loading state
  useEffect(() => {
    if (!widgetLoading) return
    const interval = setInterval(() => {
      setLoadingMsgIdx((i) => (i + 1) % loadingMessages.length)
    }, 800)
    return () => clearInterval(interval)
  }, [widgetLoading, loadingMessages.length])

  const isSvg = useMemo(() => {
    const trimmed = code.trim().toLowerCase()
    return trimmed.startsWith('<svg') || (trimmed.includes('<svg') && trimmed.includes('</svg>'))
  }, [code])

  const cleanSvg = useMemo(() => {
    if (!isSvg) return ''
    let cleaned = code
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/\son\w+="[^"]*"/gi, '')
      .replace(/\son\w+='[^']*'/gi, '')

    const tokenStyle = `<style>
      :root, svg {
        --bg-void: #161615;
        --bg-deep: #1a1a18;
        --bg-surface: #212120;
        --bg-raised: #262624;
        --bg-overlay: #2e2e2c;
        --brass-core: #e8e6e3;
        --brass-bright: #f0efec;
        --brass-dim: #8a8880;
        --brass-whisper: rgba(255, 255, 255, 0.06);
        --brass-glow: rgba(255, 255, 255, 0.14);
        --text-primary: #e9e8e6;
        --text-secondary: #a6a29c;
        --text-muted: #6e6c68;
        --text-accent: #e8e6e3;
        --border-subtle: rgba(255, 255, 255, 0.10);
        --border-visible: rgba(255, 255, 255, 0.20);
        --border-strong: rgba(255, 255, 255, 0.35);
        --success: #34d399;
        --warning: #fbbf24;
        --error: #f87171;
        --info: #93c5fd;
        --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
        --font-ui: 'Inter', system-ui, sans-serif;
      }
      svg {
        background-color: var(--bg-deep, #1a1a18);
        color: var(--text-primary, #e9e8e6);
        font-family: var(--font-ui, 'Inter', sans-serif);
      }
      text {
        fill: var(--text-primary, #e9e8e6) !important;
      }
    </style>`

    if (cleaned.includes('<svg') && !cleaned.includes('--brass-core')) {
      cleaned = cleaned.replace(/(<svg[^>]*>)/i, `$1${tokenStyle}`)
    }
    return cleaned
  }, [code, isSvg])


  // Listen for iframe postMessage (sendPrompt bridge and iframe_height resize)
  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (!e.data) return
      if (e.data.type === 'widget_height' && typeof e.data.height === 'number') {
        setIframeHeight(Math.min(800, Math.max(220, e.data.height)))
      } else if (e.data.type === 'agent_prompt' && typeof e.data.text === 'string') {
        const cleanPrompt = e.data.text.slice(0, 500).replace(/[<>]/g, '').trim()
        if (cleanPrompt) {
          window.dispatchEvent(new CustomEvent('agent:send_prompt', { detail: { text: cleanPrompt } }))
        }
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (_) {}
  }

  const handleDownloadPng = () => {
    if (!isSvg) return
    try {
      const blob = new Blob([cleanSvg || code], { type: 'image/svg+xml;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        canvas.width = img.width || 800
        canvas.height = img.height || 600
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.fillStyle = '#1a1a18'
          ctx.fillRect(0, 0, canvas.width, canvas.height)
          ctx.drawImage(img, 0, 0)
          const pngUrl = canvas.toDataURL('image/png')
          triggerDirectDownload(pngUrl, `${title || 'ochuko_widget'}.png`)
        }
        URL.revokeObjectURL(url)
      }
      img.src = url
    } catch (e) {
      console.error('PNG export failed:', e)
    }
  }

  const fullHtml = useMemo(() => {
    if (isSvg) return ''
    const bridgeScript = `
      <script>
        function sendPrompt(text) {
          if (typeof text === 'string' && text.trim()) {
            window.parent.postMessage({ type: 'agent_prompt', text: text }, '*');
          }
        }
        window.addEventListener('load', function() {
          var h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
          window.parent.postMessage({ type: 'widget_height', height: h + 24 }, '*');
        });
      </script>
    `
    if (code.includes('<html') || code.includes('<body')) {
      return code.includes('</body>') ? code.replace('</body>', `${bridgeScript}</body>`) : code + bridgeScript
    }

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    :root {
      --bg-void:    #161615;
      --bg-deep:    #1a1a18;
      --bg-surface: #212120;
      --bg-raised:  #262624;
      --bg-overlay: #2e2e2c;
      --brass-core:    #e8e6e3;
      --brass-bright:  #f0efec;
      --brass-dim:     #8a8880;
      --brass-whisper: rgba(255,255,255,0.06);
      --brass-glow:    rgba(255,255,255,0.14);
      --text-primary:   #e9e8e6;
      --text-secondary: #a6a29c;
      --text-muted:     #6e6c68;
      --text-accent:    #e8e6e3;
      --border-subtle:  rgba(255,255,255,0.10);
      --border-visible: rgba(255,255,255,0.20);
      --border-strong:  rgba(255,255,255,0.35);
      --success: #34d399;
      --warning: #fbbf24;
      --error:   #f87171;
      --info:    #93c5fd;
      --font-mono: 'JetBrains Mono','Fira Code',monospace;
      --font-ui:   'Inter',system-ui,sans-serif;
    }
    body {
      margin: 0;
      padding: 12px;
      background: transparent;
      color: var(--text-primary);
      font-family: var(--font-ui);
      overflow-x: auto;
      max-width: 100vw;
    }
    #app, body > div:first-of-type {
      max-width: 100%;
      box-sizing: border-box;
    }
    /* Elegant dark custom scrollbar for all scrollable elements inside the iframe */
    *::-webkit-scrollbar {
      width: 5px;
      height: 5px;
    }
    *::-webkit-scrollbar-track {
      background: transparent;
    }
    *::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.12);
      border-radius: 99px;
    }
    *::-webkit-scrollbar-thumb:hover {
      background: rgba(255, 255, 255, 0.25);
    }
    * {
      scrollbar-width: thin;
      scrollbar-color: rgba(255, 255, 255, 0.12) transparent;
    }
  </style>
  ${bridgeScript}
</head>
<body>
  ${code}
  <script>
    // Scale container if it overflows the iframe viewport width (minimum scale 0.85 to stay readable)
    const fitViewport = () => {
      const el = document.getElementById('app') || document.body.firstElementChild;
      if (!el) return;
      el.style.maxWidth = '100%';
      const elWidth = el.scrollWidth;
      const viewWidth = window.innerWidth;
      if (elWidth > viewWidth && viewWidth > 0) {
        const ratio = Math.max(0.85, viewWidth / elWidth);
        el.style.transform = 'scale(' + ratio + ')';
        el.style.transformOrigin = 'top left';
        el.style.width = elWidth + 'px';
        el.style.marginBottom = (el.scrollHeight * (1 - ratio)) + 'px';
      } else {
        el.style.transform = '';
        el.style.width = '';
        el.style.marginBottom = '';
      }
    };

    // Report height updates to the parent page to resize the container
    const reportHeight = () => {
      fitViewport();
      const height = document.documentElement.scrollHeight || document.body.scrollHeight;
      window.parent.postMessage({ type: 'resize-iframe', height: height }, '*');
    };

    window.addEventListener('load', reportHeight);
    window.addEventListener('resize', reportHeight);

    // Also track layout modifications
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(reportHeight);
      observer.observe(document.body);
    }
  </script>
</body>
</html>`
  }, [code, isSvg])

  // ── Loading state ────────────────────────────────────────────────────────────
  if (widgetLoading) {
    return (
      <div className="mt-3 my-2 rounded-lg bg-[#1A3038]/90 border border-[rgba(233,236,239,0.12)] shadow-xl overflow-hidden font-sans animate-fadeIn">
        <div className="flex items-center gap-3 px-4 py-3.5 bg-[#223D47]/85 border-b border-[rgba(233,236,239,0.08)]">
          <div
            className="w-3.5 h-3.5 rounded-full border-2 border-white/10 shrink-0"
            style={{
              borderTopColor: '#00A896',
              animation: 'widget-spin 0.75s linear infinite',
            }}
          />
          <span
            className="text-[12px] font-medium text-[#F4F1DE] font-mono transition-all duration-300"
            key={loadingMsgIdx}
          >
            {loadingMessages[loadingMsgIdx]}
          </span>
        </div>
        <style>{`@keyframes widget-spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
  }

  return (
    <div className="relative group/widget w-full my-4 font-sans select-none animate-widgetUnfold z-10">
      {/* Absolute 3-Dots Action Button & Dropdown Menu */}
      <div ref={menuRef} className="absolute right-3.5 top-3.5 z-50">
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          className="p-1.5 rounded-lg border border-white/5 bg-[#12141c]/90 text-[#8e95a2] hover:text-[#ffffff] hover:bg-[#1a1d29] shadow-lg backdrop-blur-md cursor-pointer transition duration-150"
          title="More actions"
        >
          <MoreVertical className="w-3.5 h-3.5" />
        </button>

        {menuOpen && (
          <div className="absolute right-0 mt-1.5 w-44 py-1.5 bg-[#0f1118]/95 border border-white/10 rounded-lg shadow-2xl backdrop-blur-md text-[11px] font-medium text-[#8e95a2] select-none flex flex-col z-[100]">

            {isSvg && (
              <>
                <button
                  type="button"
                  onClick={() => { setZoom((z) => Math.max(0.6, z - 0.2)); setMenuOpen(false); }}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/5 hover:text-white transition duration-150"
                >
                  Zoom Out
                </button>
                <button
                  type="button"
                  onClick={() => { setZoom(1); setMenuOpen(false); }}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/5 hover:text-white transition duration-150"
                >
                  Reset Zoom ({Math.round(zoom * 100)}%)
                </button>
                <button
                  type="button"
                  onClick={() => { setZoom((z) => Math.min(2.5, z + 0.2)); setMenuOpen(false); }}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/5 hover:text-white transition duration-150"
                >
                  Zoom In
                </button>
                <button
                  type="button"
                  onClick={() => { handleDownloadPng(); setMenuOpen(false); }}
                  className="w-full text-left px-3 py-1.5 hover:bg-white/5 hover:text-white transition duration-150 border-b border-white/[0.05]"
                >
                  Export PNG
                </button>
              </>
            )}
            <button
              type="button"
              onClick={() => { handleCopyCode(); setMenuOpen(false); }}
              className="w-full text-left px-3 py-1.5 hover:bg-white/5 hover:text-white transition duration-150"
            >
              {copied ? 'Copied!' : 'Copy Code'}
            </button>
            <button
              type="button"
              onClick={() => { setFullscreen(true); setMenuOpen(false); }}
              className="w-full text-left px-3 py-1.5 hover:bg-white/5 hover:text-white transition duration-150"
            >
              Expand Fullscreen
            </button>
          </div>
        )}
      </div>

      {/* Content Canvas Area — direct borderless view */}
      <div className="w-full bg-transparent overflow-x-auto flex justify-center items-center min-h-[180px] relative">
        {isSvg ? (
          <div
            className="transition-transform duration-200 flex justify-center items-center max-w-full [&>svg]:max-w-full [&>svg]:h-auto [&>svg>rect:first-of-type]:fill-transparent"
            style={{
              transform: `scale(${zoom})`,
              transformOrigin: 'top center',
              '--bg-void': '#0D191D',
              '--bg-deep': '#1A3038',
              '--bg-surface': '#223D47',
              '--bg-raised': '#294954',
              '--bg-overlay': '#325764',
              '--brass-core': '#00A896',
              '--brass-bright': '#FFB703',
              '--brass-dim': '#2E6F40',
              '--brass-whisper': 'rgba(0, 168, 150, 0.08)',
              '--brass-glow': 'rgba(0, 168, 150, 0.18)',
              '--text-primary': '#F4F1DE',
              '--text-secondary': '#E9ECEF',
              '--text-muted': '#8e95a2',
              '--text-accent': '#D4AF37',
              '--border-subtle': 'rgba(233, 236, 239, 0.08)',
              '--border-visible': 'rgba(233, 236, 239, 0.18)',
              '--border-strong': 'rgba(233, 236, 239, 0.35)',
            } as React.CSSProperties}
            dangerouslySetInnerHTML={{ __html: cleanSvg || code }}
          />
        ) : (
          <iframe
            srcDoc={fullHtml}
            sandbox="allow-scripts"
            className="w-full rounded-lg border-0 bg-[#0d0d14]/20 transition-all duration-200"
            style={{ height: `${iframeHeight}px` }}
            title={title}
          />
        )}
      </div>

      {/* Fullscreen Modal — Complete edge-to-edge canvas wrapped in React Portal */}
      {fullscreen && createPortal(
        <div className="fixed inset-0 z-50 bg-[#06060a] flex items-center justify-center animate-fadeIn select-none">
          {/* Floating close button */}
          <button
            type="button"
            onClick={() => setFullscreen(false)}
            className="absolute right-6 top-6 z-30 p-2 rounded-full border border-white/10 bg-black/60 hover:bg-black/80 text-white cursor-pointer transition shadow-lg animate-scaleIn"
            title="Exit Fullscreen"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="w-full h-full flex items-center justify-center p-4">
            {isSvg ? (
              <div
                className="w-full h-full flex items-center justify-center [&>svg]:w-full [&>svg]:h-full [&>svg]:max-h-screen [&>svg]:object-contain"
                style={{
                  '--bg-void': '#0D191D',
                  '--bg-deep': '#1A3038',
                  '--bg-surface': '#223D47',
                  '--bg-raised': '#294954',
                  '--bg-overlay': '#325764',
                  '--brass-core': '#00A896',
                  '--brass-bright': '#FFB703',
                  '--brass-dim': '#2E6F40',
                  '--brass-whisper': 'rgba(0, 168, 150, 0.08)',
                  '--brass-glow': 'rgba(0, 168, 150, 0.18)',
                  '--text-primary': '#F4F1DE',
                  '--text-secondary': '#E9ECEF',
                  '--text-muted': '#8e95a2',
                  '--text-accent': '#D4AF37',
                  '--border-subtle': 'rgba(233, 236, 239, 0.08)',
                  '--border-visible': 'rgba(233, 236, 239, 0.18)',
                  '--border-strong': 'rgba(233, 236, 239, 0.35)',
                } as React.CSSProperties}
                dangerouslySetInnerHTML={{ __html: cleanSvg || code }}
              />
            ) : (
              <iframe
                srcDoc={fullHtml}
                sandbox="allow-scripts"
                className="w-full h-full min-h-[80vh] border-0 bg-[#0c0d10]"
                title={title}
              />
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

// ─── Mermaid block renderer ───────────────────────────────────────────────────

// Lazy-imports mermaid.js on first use. Renders diagram → inline SVG.

// During streaming (isStreaming=true for the last message), skipped.

let _mermaidReady = false

// Render cache: cleaned code → SVG string. Re-mounts (virtualization, tab
// switches) inject instantly instead of re-parsing/re-rendering.
const _mermaidRenderCache = new Map<string, string>()

// Pre-warm the mermaid chunk during idle time so the first diagram doesn't
// stall behind a ~1MB lazy import.
let _mermaidPreWarmeupStarted = false
function preWarmMermaid() {
  if (_mermaidPreWarmeupStarted) return
  _mermaidPreWarmeupStarted = true
  const start = () => {
    import('mermaid').then((m) => {
      m.default.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'loose',
        suppressErrorRendering: true,
        htmlLabels: true,
        wrap: true,
        markdownAutoWrap: true,
        themeVariables: { fontSize: '13px' },
        flowchart: { padding: 10, useMaxWidth: true },
        sequence: { wrap: true },
        maxTextSize: 120000,
      })
      _mermaidReady = true
    }).catch(() => { /* lazy path will retry on demand */ })
  }
  const w = window as any
  if (typeof w.requestIdleCallback === 'function') w.requestIdleCallback(start, { timeout: 3000 })
  else setTimeout(start, 1500)
}

// Validate and clean mermaid code before rendering
function validateMermaidCode(code: string): { valid: boolean, cleanedCode: string, error?: string } {
  if (!code || code.trim().length === 0) {
    return { valid: false, cleanedCode: '', error: 'Empty mermaid code' }
  }

  // Clean up common issues
  let cleaned = code.trim()

  // Remove wrapping backticks / markdown fence if present
  cleaned = cleaned.replace(/^```(?:mermaid)?\r?\n?/i, '').replace(/\r?\n?```$/i, '').trim()

  // Ensure proper line endings
  cleaned = cleaned.replace(/\r\n/g, '\n')

  return { valid: true, cleanedCode: cleaned }
}

// ── VoiceWaveform — 5-bar volume-driven equaliser ─────────────────────────────
const VoiceWaveform: React.FC<{ volume: number }> = ({ volume }) => {
  const bars = [0.35, 0.65, 1.0, 0.65, 0.35]
  return (
    <div className="flex items-end gap-[2px] h-4">
      {bars.map((scale, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full bg-brand-text transition-all duration-75"
          style={{ height: `${Math.max(3, volume * scale * 16)}px` }}
        />
      ))}
    </div>
  )
}

function MermaidBlock({ code }: { code: string }) {

  const diagramRef = useRef<HTMLDivElement>(null)

  const [showSource, setShowSource] = useState(false)

  const [copied, setCopied] = useState(false)

  const [isLoading, setIsLoading] = useState(false)

  const [isExpanded, setIsExpanded] = useState(false)

  // Validate and clean code on mount
  const validation = useMemo(() => validateMermaidCode(code), [code])

  useEffect(() => {

    if (showSource) return

    let cancelled = false

    async function render() {

      if (!diagramRef.current) return

      // Cache hit → inject the previously rendered SVG instantly.
      const cached = _mermaidRenderCache.get(validation.cleanedCode)
      if (cached) {
        diagramRef.current.innerHTML = cached
        const cachedSvg = diagramRef.current.querySelector('svg')
        if (cachedSvg) {
          cachedSvg.style.maxWidth = '100%'
          cachedSvg.style.width = '100%'
          cachedSvg.style.height = 'auto'
          cachedSvg.setAttribute('preserveAspectRatio', 'xMidYMid meet')
        }
        return
      }

      setIsLoading(true)

      try {

        if (!validation.valid) {
          throw new Error(validation.error || 'Invalid mermaid syntax')
        }

        if (!_mermaidReady) {

          const m = await import('mermaid')

          m.default.initialize({
            startOnLoad: false,
            theme: 'dark',
            securityLevel: 'loose',
            suppressErrorRendering: true,
            htmlLabels: true,
            wrap: true,
            markdownAutoWrap: true,
            themeVariables: { fontSize: '13px' },
            flowchart: { padding: 10, useMaxWidth: true },
            sequence: { wrap: true },
            maxTextSize: 120000,
          })

          _mermaidReady = true

        }

        const { default: mermaid } = await import('mermaid')

        const renderId = `mermaid-${Date.now()}-${Math.floor(Math.random() * 100000)}`

        const { svg } = await mermaid.render(renderId, validation.cleanedCode)

        // Keep the cache bounded (diagrams are small SVG strings).
        if (_mermaidRenderCache.size >= 50) {
          const oldest = _mermaidRenderCache.keys().next().value
          if (oldest !== undefined) _mermaidRenderCache.delete(oldest)
        }
        _mermaidRenderCache.set(validation.cleanedCode, svg)

        // Clean up temporary DOM element appended by mermaid if still present
        const tempEl = document.getElementById(renderId)
        if (tempEl) tempEl.remove()

        if (!cancelled && diagramRef.current) {
          diagramRef.current.innerHTML = svg
          const svgEl = diagramRef.current.querySelector('svg')
          if (svgEl) {
            svgEl.style.maxWidth = '100%'
            svgEl.style.width = '100%'
            svgEl.style.height = 'auto'
            svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet')
          }
        }

      } catch (err: any) {

        console.error('Mermaid rendering error:', err)

        if (!cancelled) {

          if (diagramRef.current) {

            diagramRef.current.innerHTML = `<pre class="text-rose-400 text-xs p-2">Diagram error: ${err?.message || 'invalid syntax'}</pre>`

          }

        }

      } finally {

        if (!cancelled) {

          setIsLoading(false)

        }

      }

    }

    render()

    return () => { cancelled = true }

  }, [validation, showSource])

  const handleCopy = () => {

    navigator.clipboard.writeText(code).then(() => {

      setCopied(true)

      setTimeout(() => setCopied(false), 1500)

    }).catch(() => {
      // Safari rejects clipboard writes outside user gestures / secure contexts
    })

  }

  const handleDownload = () => {
    const svgEl = diagramRef.current?.querySelector('svg')
    if (!svgEl) return
    try {
      const svgString = new XMLSerializer().serializeToString(svgEl)
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
      const blobURL = window.URL.createObjectURL(svgBlob)
      const image = new Image()
      image.onload = () => {
        try {
          const canvas = document.createElement('canvas')
          const bbox = svgEl.getBoundingClientRect()
          const width = svgEl.viewBox.baseVal.width || bbox.width || 800
          const height = svgEl.viewBox.baseVal.height || bbox.height || 600

          const scale = 2
          canvas.width = width * scale
          canvas.height = height * scale
          const context = canvas.getContext('2d')
          if (context) {
            context.fillStyle = '#0d1117'
            context.fillRect(0, 0, canvas.width, canvas.height)
            context.scale(scale, scale)
            context.drawImage(image, 0, 0, width, height)
            const pngURL = canvas.toDataURL('image/png')
            const downloadLink = document.createElement('a')
            downloadLink.href = pngURL
            downloadLink.download = `mermaid_diagram_${Date.now()}.png`
            document.body.appendChild(downloadLink)
            downloadLink.click()
            document.body.removeChild(downloadLink)
          }
        } catch (err) {
          console.error('PNG conversion error:', err)
        } finally {
          window.URL.revokeObjectURL(blobURL)
        }
      }
      image.onerror = () => {
        console.error('Failed to load SVG for PNG conversion')
        window.URL.revokeObjectURL(blobURL)
      }
      image.src = blobURL
    } catch (err) {
      console.error('Download error:', err)
    }
  }

  const handleFullscreen = () => {
    const svgEl = diagramRef.current?.querySelector('svg')
    if (!svgEl) return
    try {
      // Clone the SVG and add responsive full-screen styling with dark background
      const svgClone = svgEl.cloneNode(true) as SVGElement
      svgClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
      svgClone.style.maxWidth = '100%'
      svgClone.style.width = '100%'
      svgClone.style.height = 'auto'

      // Ensure proper viewBox for responsive scaling
      if (!svgClone.getAttribute('viewBox')) {
        const bbox = svgEl.getBoundingClientRect()
        const w = svgEl.viewBox?.baseVal?.width || bbox.width || 800
        const h = svgEl.viewBox?.baseVal?.height || bbox.height || 600
        svgClone.setAttribute('viewBox', `0 0 ${w} ${h}`)
      }

      // Add dark background rectangle if not present
      if (!svgClone.querySelector('rect.bg-rect')) {
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
        rect.setAttribute('class', 'bg-rect')
        rect.setAttribute('width', '100%')
        rect.setAttribute('height', '100%')
        rect.setAttribute('fill', '#0d1117')
        svgClone.insertBefore(rect, svgClone.firstChild)
      }

      const svgString = new XMLSerializer().serializeToString(svgClone)
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
      const blobUrl = window.URL.createObjectURL(svgBlob)
      window.dispatchEvent(new CustomEvent('open-file-preview', {
        detail: {
          name: 'Mermaid Diagram',
          type: 'image/svg+xml',
          url: blobUrl
        }
      }))
    } catch (err) {
      console.error('Preview error:', err)
    }
  }

  return (

    <div className={`group my-3 relative rounded-lg border border-[#1e2025] bg-[#0d1117] overflow-hidden ${isExpanded ? 'w-full' : 'max-w-[620px]'}`}>
      {isLoading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#0d1117]/80 backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-brand-muted/30 border-t-brand-text rounded-full animate-spin" />
            <p className="text-sm text-brand-muted">Rendering diagram...</p>
          </div>
        </div>
      )}

      {/* Corner icon buttons — top right, revealed on hover */}

      <div className="absolute top-2 right-2 z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">

        {/* Eye / Code toggle */}

        <button

          onClick={() => setShowSource(s => !s)}

          title={showSource ? 'Show diagram' : 'Show source'}

          className={`flex items-center justify-center w-7 h-7 rounded-md border transition-colors ${

            showSource

              ? 'bg-[#1f1f1f] border-[#58a6ff44] text-[#58a6ff]'

              : 'bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58]'

          }`}

        >

          {showSource ? (

            /* Eye icon — back to diagram */

            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">

              <path d="M8 2C4.5 2 1.7 4.3 0 8c1.7 3.7 4.5 6 8 6s6.3-2.3 8-6c-1.7-3.7-4.5-6-8-6zm0 10a4 4 0 110-8 4 4 0 010 8zm0-6.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5z"/>

            </svg>

          ) : (

            /* Code </> icon — show source */

            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">

              <path d="M4.72 3.22a.75.75 0 011.06 1.06L2.06 8l3.72 3.72a.75.75 0 11-1.06 1.06L.47 8.53a.75.75 0 010-1.06l4.25-4.25zm6.56 0a.75.75 0 10-1.06 1.06L13.94 8l-3.72 3.72a.75.75 0 101.06 1.06l4.25-4.25a.75.75 0 000-1.06l-4.25-4.25z"/>

            </svg>

          )}

        </button>

        {/* Copy */}

        <button

          onClick={handleCopy}

          title="Copy source"

          className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"

        >

          {copied ? (

            <svg width="13" height="13" viewBox="0 0 16 16" fill="#3fb950">

              <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/>

            </svg>

          ) : (

            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">

              <path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 010 1.5h-1.5a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-1.5a.75.75 0 011.5 0v1.5A1.75 1.75 0 019.25 16h-7.5A1.75 1.75 0 010 14.25v-7.5z"/>

              <path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0114.25 11h-7.5A1.75 1.75 0 015 9.25v-7.5zm1.75-.25a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25h-7.5z"/>

            </svg>

          )}

        </button>

        {!showSource && (
          <>
            {/* Expand/Collapse */}
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              title={isExpanded ? "Collapse Diagram" : "Expand Diagram"}
              className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
            >
              {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </button>

            {/* Fullscreen */}
            <button
              type="button"
              onClick={handleFullscreen}
              title="Fullscreen"
              className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </button>

            {/* Download */}
            <button
              type="button"
              onClick={handleDownload}
              title="Download as PNG"
              className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          </>
        )}

      </div>

      {/* Content */}

      {showSource

        ? <pre className="p-4 pt-8 text-xs text-[#a5d6ff] overflow-x-auto font-mono leading-relaxed m-0">{code}</pre>

        : <div 
            ref={diagramRef} 
            className={`p-4 overflow-auto mermaid-diagram-container flex justify-center items-center transition-all duration-300 [&>svg]:max-w-full [&>svg]:w-full [&>svg]:h-auto ${
              isExpanded 
                ? 'w-full min-h-[500px] max-h-[85vh]' 
                : 'w-full min-h-[220px] max-h-[450px]'
            }`}
          />

      }

    </div>

  )

}

// ─── SVG inline renderer ──────────────────────────────────────────────────────
// Renders SVG via a base64 data-URI <img> so that ALL SVG attributes are
// preserved faithfully (DOMPurify was stripping width/height/viewBox/transform
// and causing scrambled output). Adds Copy / Download-as-PNG / Fullscreen controls.

function SvgBlock({ svg }: { svg: string }) {
  const [copied, setCopied] = useState(false)

  // Encode to a safe data URI — no DOMPurify stripping
  const dataUri = useMemo(() => {
    try {
      return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
    } catch {
      return ''
    }
  }, [svg])

  const handleCopy = () => {
    navigator.clipboard.writeText(svg).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {
      // Safari rejects clipboard writes outside user gestures / secure contexts
    })
  }

  const handleDownload = () => {
    // Render to canvas and save as PNG
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth || 800
      canvas.height = img.naturalHeight || 600
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.fillStyle = '#0d1117'
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.drawImage(img, 0, 0)
        const a = document.createElement('a')
        a.href = canvas.toDataURL('image/png')
        a.download = `image_${Date.now()}.png`
        a.click()
      }
    }
    img.src = dataUri
  }

  const handleFullscreen = () => {
    window.dispatchEvent(new CustomEvent('open-file-preview', {
      detail: { name: 'SVG Image', type: 'image/svg+xml', url: dataUri }
    }))
  }

  if (!dataUri) {
    return (
      <div className="my-3 p-3 rounded-lg border border-rose-500/30 bg-rose-500/5 text-rose-300 text-sm">
        Could not render SVG (encoding error).
      </div>
    )
  }

  return (
    <div className="group my-3 relative rounded-lg border border-[#1e2025] bg-[#0d1117] overflow-hidden">
      {/* Controls — top-right, revealed on hover */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        {/* Copy SVG source */}
        <button
          onClick={handleCopy}
          title="Copy SVG source"
          className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
        <button
          onClick={handleFullscreen}
          title="Fullscreen"
          className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
        {/* Download as PNG */}
        <button
          onClick={handleDownload}
          title="Download as PNG"
          className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* SVG rendered as img — preserves all attributes */}
      <div className="p-4 flex justify-center overflow-auto max-h-[500px]">
        <img
          src={dataUri}
          alt="SVG image"
          className="max-w-full object-contain"
          style={{ background: 'transparent' }}
        />
      </div>
    </div>
  )
}



// ─── Block parser ─────────────────────────────────────────────────────────────

// Splits response text into typed segments in priority order:

// mermaid > svg > code > markdown prose

type Block =

  | { type: 'mermaid'; content: string }

  | { type: 'svg'; content: string }

  | { type: 'code'; content: string; lang: string }

  | { type: 'markdown'; content: string }

function parseBlocks(text: string): Block[] {

  const MERMAID = /```mermaid\r?\n([\s\S]*?)```/g

  const SVG     = /(<svg[\s\S]*?<\/svg>)/gi

  const CODE    = /```(\w*)\r?\n([\s\S]*?)```/g

  const matches: { start: number; end: number; block: Block }[] = []

  let m: RegExpExecArray | null

  while ((m = MERMAID.exec(text)) !== null)

    matches.push({ start: m.index, end: m.index + m[0].length, block: { type: 'mermaid', content: m[1].trim() } })

  while ((m = SVG.exec(text)) !== null) {

    if (!matches.some(b => b.start <= m!.index && m!.index < b.end))

      matches.push({ start: m.index, end: m.index + m[0].length, block: { type: 'svg', content: m[1] } })

  }

  while ((m = CODE.exec(text)) !== null) {

    if (!matches.some(b => b.start <= m!.index && m!.index < b.end)) {
      const lang = m[1] || 'text'
      const content = m[2]
      // Promote ```svg / ```xml fences whose content is SVG markup to a visual svg block
      const isSvgFence = (lang === 'svg' || lang === 'xml') && /^\s*<svg[\s>]/i.test(content)
      if (isSvgFence) {
        matches.push({ start: m.index, end: m.index + m[0].length, block: { type: 'svg', content: content.trim() } })
      } else {
        matches.push({ start: m.index, end: m.index + m[0].length, block: { type: 'code', content, lang } })
      }
    }

  }

  matches.sort((a, b) => a.start - b.start)

  const blocks: Block[] = []

  let cursor = 0

  for (const { start, end, block } of matches) {

    if (start > cursor) {

      const prose = text.slice(cursor, start).trim()

      if (prose) blocks.push({ type: 'markdown', content: prose })

    }

    blocks.push(block)

    cursor = end

  }

  if (cursor < text.length) {

    const tail = text.slice(cursor).trim()

    if (tail) blocks.push({ type: 'markdown', content: tail })

  }

  return blocks.length ? blocks : [{ type: 'markdown', content: text }]

}

// ─── Rich content renderer ────────────────────────────────────────────────────

// Top-level renderer for assistant messages.

// During streaming (isStreaming = true on last msg) skips Mermaid/SVG

// so partial fences don't flicker — falls back to renderMarkdown().

// After [DONE] the component re-renders and diagrams appear cleanly.

export function renderRichContent(

  text: string,

  renderMarkdown: (t: string) => React.ReactNode,

  isCurrentlyStreaming: boolean,

): React.ReactNode {

  // During streaming, skip block parsing — use the fast prose renderer with active cursor
  if (isCurrentlyStreaming) {
    return (
      <div className="relative">
        {renderMarkdown(text)}
        <span className="inline-block w-1.5 h-3.5 bg-white/70 animate-pulse ml-1 align-baseline rounded-sm" />
      </div>
    )
  }

  const blocks = parseBlocks(text)

  return (

    <>

      {blocks.map((block, i) => {

        switch (block.type) {

          case 'mermaid':

            return <MermaidBlock key={i} code={block.content} />

          case 'svg':

            return <SvgBlock key={i} svg={block.content} />

          case 'code':

            // Delegate to existing renderMarkdown which handles code fences with copy button

            return <React.Fragment key={i}>{renderMarkdown('```' + block.lang + '\n' + block.content + '\n```')}</React.Fragment>

          case 'markdown':

          default:

            return <React.Fragment key={i}>{renderMarkdown(block.content)}</React.Fragment>

        }

      })}

    </>

  )

}

// ─── Inline markdown: bold, italic, code, links ───────────────────────────────

function renderMath(tex: string, displayMode: boolean): React.ReactNode {
  const katex = (window as any).katex || (window as any).__katex;
  if (katex) {
    try {
      const sanitizedTex = (tex || '').replace(/[\u2010-\u2015\u2212]/g, '-')
      const html = katex.renderToString(sanitizedTex, { displayMode, throwOnError: false, strict: false })
      return (
        <span
          className={displayMode ? 'block my-3 text-center overflow-x-auto' : 'inline'}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )
    } catch {
      return <code className="text-brand-accent">{tex}</code>
    }
  }
  return <span className="font-mono">{displayMode ? `$$${tex}$$` : `$${tex}$`}</span>
}

function renderInline(text: string, keyBase: string, generatedFiles?: any[]): React.ReactNode {
  // Normalize LaTeX \[ ... \] to $$...$$ and \( ... \) to $...$ for universal KaTeX math rendering
  const normalizedText = (text || '')
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => `$$${inner}$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, inner) => `$${inner}$`)

  const pattern = /(\$\$([\s\S]*?)\$\$|\$(?!\s)([^\$]+?)(?<!\s)\$|\*\*(.*?)\*\*|\*(.*?)\*|`(.*?)`|\[(.*?)\]\((.*?)\)|(https?:\/\/[^\s\)<>"]+))/g

  const segments: React.ReactNode[] = []

  let lastIndex = 0

  let match: RegExpExecArray | null

  while ((match = pattern.exec(normalizedText)) !== null) {

    if (match.index > lastIndex) {

      segments.push(<span key={`${keyBase}-t${lastIndex}`}>{normalizedText.slice(lastIndex, match.index)}</span>)

    }

    const fullMatch = match[0]

    if (fullMatch.startsWith('$$')) {

      segments.push(<React.Fragment key={`${keyBase}-display-math-${match.index}`}>{renderMath(match[2], true)}</React.Fragment>)

    } else if (fullMatch.startsWith('$')) {

      segments.push(<React.Fragment key={`${keyBase}-inline-math-${match.index}`}>{renderMath(match[3], false)}</React.Fragment>)

    } else if (fullMatch.startsWith('**')) {

      segments.push(

        <strong key={`${keyBase}-b${match.index}`} className="font-semibold text-[#f0ece4]">

          {match[4]}

        </strong>

      )

    } else if (fullMatch.startsWith('*')) {

      segments.push(

        <em key={`${keyBase}-i${match.index}`} className="italic text-[#ffffff]/90">

          {match[5]}

        </em>

      )

    } else if (fullMatch.startsWith('`')) {

      segments.push(

        <code

          key={`${keyBase}-c${match.index}`}

          className="bg-black/40 border border-[#ffffff]/20 rounded px-1.5 py-[1px] text-[11.5px] font-mono text-[#ffffff]/90"

        >

          {match[6]}

        </code>

      )

    } else if (fullMatch.startsWith('http://') || fullMatch.startsWith('https://')) {

      // Suppress raw localhost placeholder URLs silently (LLM hallucination artefact)
      if (!fullMatch.includes('localhost') && !fullMatch.includes('127.0.0.1')) {
        segments.push(

          <a

            key={`${keyBase}-url${match.index}`}

            href={fullMatch}

            target="_blank"

            rel="noopener noreferrer"

            className="text-[#ffffff] hover:text-[#f3f4f6] underline underline-offset-4 decoration-[#ffffff]/40 transition duration-150"

          >

            {fullMatch}

          </a>

        )
      }

    } else if (fullMatch.startsWith('[')) {

      const label = match[7]

      let url = match[8]

      // Citation marker: [n](https://...) with a purely numeric label renders
      // as a compact glass-HUD superscript chip with the domain on hover.
      if (/^\d{1,3}$/.test(label.trim()) && /^https?:\/\//.test(url)) {
        let domain = ''
        try { domain = new URL(url).hostname.replace(/^www\./, '') } catch { /* keep empty */ }
        segments.push(
          <a
            key={`${keyBase}-cite${match.index}`}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            title={domain || url}
            className="inline-flex items-center justify-center align-super ml-0.5 mr-0.5 min-w-[16px] h-[15px] px-[4px] rounded-full text-[9.5px] font-sans font-semibold bg-white/10 border border-white/20 text-white/70 hover:bg-white/20 hover:text-white transition duration-150 leading-none"
          >
            {label.trim()}
          </a>
        )
        lastIndex = match.index + fullMatch.length
        continue
      }

      // Resolve sandbox paths from current turn's generated files if available
      if ((url.includes('/mnt/data/') || url.startsWith('sandbox:')) && generatedFiles) {
        const filename = url.split('/').pop()?.replace(/^sandbox:/, '') || '';
        const matchingFile = generatedFiles.find(gf =>
          gf.filename?.toLowerCase() === filename.toLowerCase() ||
          gf.filename?.toLowerCase().endsWith(filename.toLowerCase())
        );
        if (matchingFile && matchingFile.download_url) {
          url = matchingFile.download_url;
        }
      }

      // If still a sandbox path, resolve dynamically to persistent backend sandbox file server
      if ((url.startsWith('sandbox:') || url.includes('/mnt/data/')) && !(url.startsWith('https://') || url.startsWith('http://'))) {
        const rawFilename = url.split('/').pop()?.replace(/^sandbox:/, '') || '';
        const curConvoId = (window as any).__activeConversationId || sessionStorage.getItem('pending_active_convo_id') || localStorage.getItem('pending_active_convo_id') || '';
        if (rawFilename && curConvoId && curConvoId !== '00000000-0000-0000-0000-000000000000') {
          url = `${API_BASE}/v1/files/sandbox/${curConvoId}/${encodeURIComponent(rawFilename)}`;
        }
      }

      // Resolve localhost or placeholder links by matching label text to a generated file
      if (
        generatedFiles &&
        (url.includes('localhost') || url === '#' || url === '' || url === '/') &&
        label
      ) {
        const labelLower = label.trim().toLowerCase();
        const matchingFile = generatedFiles.find(gf =>
          gf.filename?.toLowerCase() === labelLower ||
          labelLower.endsWith(gf.filename?.toLowerCase() || '__never__')
        );
        if (matchingFile && matchingFile.download_url) {
          url = matchingFile.download_url;
        }
      }

      const lowerUrl = url.toLowerCase()
      const isDownloadable = lowerUrl.endsWith('.docx') || lowerUrl.endsWith('.dotx') || lowerUrl.endsWith('.xlsx') || lowerUrl.endsWith('.zip') || lowerUrl.endsWith('.md') || lowerUrl.endsWith('.pdf') || lowerUrl.endsWith('.html') || lowerUrl.includes('/files/sandbox/') || lowerUrl.includes('/generated/') || lowerUrl.includes('r2.dev') || lowerUrl.includes('blob.core.windows.net') || label.toLowerCase().startsWith('download')

      if (isDownloadable) {
        const isZip = lowerUrl.endsWith('.zip') || label.toLowerCase().includes('zip') || label.toLowerCase().includes('website')
        const isHtmlOrWeb = lowerUrl.endsWith('.html') || lowerUrl.endsWith('.htm') || label.toLowerCase().includes('.html') || lowerUrl.includes('/v1/sites/')
        const targetFilename = label || (url.split('/').pop()?.split('?')[0] || 'file')

        const handleReview = (e: React.MouseEvent) => {
          e.preventDefault()
          e.stopPropagation()
          window.dispatchEvent(new CustomEvent('open-file-preview', {
            detail: {
              name: targetFilename,
              type: mimeFromName(targetFilename),
              url: url,
            }
          }))
        }

        segments.push(
          <div
            key={`${keyBase}-l${match.index}`}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 my-1 rounded-xl bg-white/[0.07] hover:bg-white/[0.12] border border-white/15 text-white font-medium text-[13px] transition select-none shadow-sm align-middle group max-w-full"
          >
            {/* Click to Review / Preview */}
            <button
              type="button"
              onClick={handleReview}
              className="inline-flex items-center gap-2 hover:text-emerald-400 transition cursor-pointer text-left min-w-0"
              title={`Review ${label}`}
            >
              <Eye className="w-3.5 h-3.5 text-emerald-400 group-hover:text-emerald-300 transition shrink-0" />
              <span className="truncate max-w-[200px] sm:max-w-xs">{label}</span>
            </button>

            {/* Quick Review badge button */}
            <button
              type="button"
              onClick={handleReview}
              className="px-1.5 py-0.5 rounded text-[10px] font-semibold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 transition shrink-0 cursor-pointer"
              title={`Review ${label}`}
            >
              Review
            </button>

            {/* Direct Download Button */}
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                triggerDirectDownload(url, label || 'download')
              }}
              className="p-1 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition shrink-0 cursor-pointer"
              title={`Download ${label}`}
            >
              <Download className="w-3.5 h-3.5 text-blue-400 hover:text-blue-300" />
            </button>

            {/* Format badge */}
            <span className="text-[9.5px] font-mono text-white/50 uppercase px-1.5 py-0.5 rounded bg-white/5 border border-white/10 shrink-0">
              {isZip ? 'ZIP' : isHtmlOrWeb ? 'WEB' : 'FILE'}
            </span>
          </div>
        )
      } else {
        segments.push(
          <a
            key={`${keyBase}-l${match.index}`}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#ffffff] hover:text-[#f3f4f6] underline underline-offset-4 decoration-[#ffffff]/40 transition duration-150"
          >
            {label}
          </a>
        )
      }

    }

    lastIndex = match.index + fullMatch.length

  }

  if (lastIndex < text.length) {

    segments.push(<span key={`${keyBase}-tail`}>{text.slice(lastIndex)}</span>)

  }

  return segments.length === 1 ? segments[0] : <>{segments}</>

}

interface PastedSnippetItem {
  name: string
  content: string
}

interface ParsedMessage {
  textPrefix: string
  hasPastedText: boolean
  pastedItems: PastedSnippetItem[]
  pastedName?: string
  pastedContent?: string
}

function parsePastedText(content: string): ParsedMessage {
  if (!content) {
    return {
      textPrefix: '',
      hasPastedText: false,
      pastedItems: []
    }
  }

  const pattern = /\[Pasted Content: (.*?)\]\r?\n```\r?\n([\s\S]*?)```/g
  const matches = Array.from(content.matchAll(pattern))

  if (matches.length > 0) {
    const firstMatchIndex = matches[0].index ?? content.length
    const textPrefix = content.slice(0, firstMatchIndex).trim()
    const pastedItems: PastedSnippetItem[] = matches.map(m => ({
      name: m[1],
      content: m[2].trim()
    }))

    return {
      textPrefix,
      hasPastedText: true,
      pastedItems,
      pastedName: pastedItems[0]?.name,
      pastedContent: pastedItems[0]?.content
    }
  }

  return {
    textPrefix: content,
    hasPastedText: false,
    pastedItems: []
  }
}

// ── ImagePending — shimmer placeholder while FLUX is running ─────────────────

const ImagePending: React.FC<{ prompt?: string }> = ({ prompt }) => (

  <div className="flex flex-col gap-2.5 my-1">

    <div className="w-72 h-52 rounded-lg bg-[#111316] border border-[#1e2025] overflow-hidden relative">

      {/* Animated shimmer */}

      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.8s_infinite] bg-gradient-to-r from-transparent via-[#ffffff]/5 to-transparent" />

      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">

        <div className="w-8 h-8 rounded-full border-2 border-[#ffffff]/30 border-t-[#ffffff] animate-spin" />

        <span className="text-[10px] font-bold text-[#ffffff]/60 tracking-widest uppercase">Generating image…</span>

      </div>

    </div>

    {prompt && (

      <p className="text-[10px] text-brand-muted/60 italic px-1 max-w-[280px] truncate">{prompt}</p>

    )}

  </div>

)

// ── ImageBubble — premium image card shown once generation is done ───────────

const ImageBubble: React.FC<{ url: string; prompt?: string }> = ({ url, prompt }) => {
  const handlePreview = () => {
    const event = new CustomEvent('open-file-preview', {
      detail: {
        name: prompt || 'Generated Image',
        type: 'image/png',
        url: url
      }
    })
    window.dispatchEvent(event)
  }

  return (
    <div className="flex flex-col gap-2 my-1 group/img">
      <div 
        onClick={handlePreview}
        className="relative rounded-lg overflow-hidden border border-[#1e2025] shadow-xl shadow-black/50 w-fit max-w-sm cursor-pointer"
      >
        <img
          src={url}
          alt={prompt || 'Generated image'}
          className="block w-full max-w-sm object-cover transition-transform duration-500 group-hover/img:scale-[1.02]"
          loading="eager"
        />
        {/* Download overlay on hover */}
        <div className="absolute inset-0 bg-black/0 group-hover/img:bg-black/40 transition-all duration-300 flex items-end justify-end p-3">
          <a
            href={url}
            download
            target="_blank"
            rel="noopener noreferrer"
            className="opacity-0 group-hover/img:opacity-100 transition-opacity duration-200 flex items-center gap-1.5 px-3 py-1.5 bg-[#ffffff] text-[#1a1a18] rounded-lg text-[10px] font-bold tracking-wider uppercase shadow-lg"
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
}

// ─── Language → file extension map ───────────────────────────────────────────

const LANG_EXT: Record<string, string> = {

  python: '.py', py: '.py', javascript: '.js', js: '.js', jsx: '.jsx',

  typescript: '.ts', ts: '.ts', tsx: '.tsx', markdown: '.md', md: '.md',

  json: '.json', html: '.html', xml: '.xml', css: '.css', scss: '.scss',

  sql: '.sql', bash: '.sh', shell: '.sh', sh: '.sh', rust: '.rs',

  go: '.go', java: '.java', c: '.c', cpp: '.cpp', 'c++': '.cpp',

  yaml: '.yaml', yml: '.yaml', toml: '.toml', ini: '.ini',

  text: '.txt', txt: '.txt', plaintext: '.txt',

}

function highlightCode(code: string, language: string): string {
  if (!code) return ''
  const lang = language.toLowerCase()
  let escaped = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  if (lang === 'python' || lang === 'py') {
    return escaped
      .replace(/\b(def|class|import|from|as|return|if|elif|else|try|except|finally|for|while|in|is|and|or|not|with|assert|pass|break|continue|lambda|global|nonlocal|async|await|None|True|False)\b/g, '<span class="text-[#c678dd] font-semibold">$1</span>')
      .replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="text-[#98c379]">$1</span>')
      .replace(/(#.*)/g, '<span class="text-[#5c6370] italic">$1</span>')
      .replace(/\b([a-zA-Z_]\w*)(?=\()/g, '<span class="text-[#61afef]">$1</span>')
      .replace(/\b(\d+)\b/g, '<span class="text-[#d19a66]">$1</span>')
  } else if (['javascript', 'js', 'typescript', 'ts', 'tsx', 'jsx'].includes(lang)) {
    return escaped
      .replace(/\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|default|import|export|from|as|class|extends|new|this|typeof|instanceof|void|async|await|try|catch|finally|throw|true|false|null|undefined|interface|type|public|private|protected|readonly|any|string|number|boolean)\b/g, '<span class="text-[#c678dd] font-semibold">$1</span>')
      .replace(/(`[\s\S]*?`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="text-[#98c379]">$1</span>')
      .replace(/(\/\/.*|\/\*[\s\S]*?\*\/)/g, '<span class="text-[#5c6370] italic">$1</span>')
      .replace(/\b([a-zA-Z_]\w*)(?=\()/g, '<span class="text-[#61afef]">$1</span>')
      .replace(/\b(\d+)\b/g, '<span class="text-[#d19a66]">$1</span>')
  } else if (lang === 'json') {
    return escaped
      .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*")(\s*:)/g, '<span class="text-[#e06c75]">$1</span>$3')
      .replace(/: \s*("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*")/g, ': <span class="text-[#98c379]">$1</span>')
      .replace(/\b(true|false|null)\b/g, '<span class="text-[#56b6c2]">$1</span>')
      .replace(/\b(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\b/g, '<span class="text-[#d19a66]">$1</span>')
  } else if (lang === 'css') {
    return escaped
      .replace(/([^{]+)(?=\s*\{)/g, '<span class="text-[#61afef]">$1</span>')
      .replace(/([a-zA-Z-]+)(?=\s*:)/g, '<span class="text-[#abb2bf]">$1</span>')
      .replace(/(:\s*[^;]+)/g, '<span class="text-[#d19a66]">$1</span>')
      .replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="text-[#5c6370] italic">$1</span>')
  } else if (lang === 'html' || lang === 'xml') {
    return escaped
      .replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="text-[#5c6370] italic">$1</span>')
      .replace(/(&lt;\/?[a-zA-Z0-9:-]+)/g, '<span class="text-[#e06c75]">$1</span>')
      .replace(/(\/?&gt;)/g, '<span class="text-[#e06c75]">$1</span>')
      .replace(/(\s[a-zA-Z0-9:-]+=)/g, '<span class="text-[#d19a66]">$1</span>')
      .replace(/("[^"]*"|'[^']*')/g, '<span class="text-[#98c379]">$1</span>')
  }
  return escaped
}

export const CodeView: React.FC<{ language: string; content: string }> = ({ language, content }) => {
  const lines = useMemo(() => content.split('\n'), [content])
  const highlightedHtml = useMemo(() => highlightCode(content, language), [content, language])
  const highlightedLines = useMemo(() => highlightedHtml.split('\n'), [highlightedHtml])

  return (
    <div className="flex font-mono text-[11px] sm:text-[11.5px] leading-relaxed select-text overflow-x-auto text-[#abb2bf] bg-[#07080a] p-4.5 rounded-lg border border-[#1e2025]">
      {/* Line numbers column */}
      <div className="select-none pr-3.5 border-r border-[#1e2025] text-right text-[#4b5263] min-w-[2.25rem] font-bold">
        {lines.map((_, i) => (
          <div key={i} className="h-5">{i + 1}</div>
        ))}
      </div>
      {/* Code column */}
      <div className="pl-4 flex-1 whitespace-pre">
        {highlightedLines.map((line, i) => (
          <div key={i} className="h-5" dangerouslySetInnerHTML={{ __html: line || ' ' }} />
        ))}
      </div>
    </div>
  )
}

const BlockquoteWithCopy: React.FC<{ content: string; children: React.ReactNode }> = ({ content, children }) => {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (_) {}
  }

  return (
    <div className="group relative border-l-2 border-brand-accent/40 bg-brand-accent/[0.04] pl-3.5 pr-8 py-2.5 my-2.5 text-brand-text/90 rounded-r-lg select-text">
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-lg border border-[#1e2025] bg-[#0d0f11]/60 hover:bg-[#ffffff]/5 text-[#8e95a2] hover:text-brand-text opacity-0 group-hover:opacity-100 transition duration-150 active:scale-95"
        title="Copy template"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-[#3fb950]" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
      <div className="text-[15px] sm:text-[14px] leading-[1.65]">
        {children}
      </div>
    </div>
  )
}

// ─── Code Block Component with Copy + Download ────────────────────────────────

const CodeBlock: React.FC<{ language: string; content: string }> = ({ language, content }) => {

  const [copied, setCopied] = useState(false)

  const [menuOpen, setMenuOpen] = useState(false)

  const menuRef = useRef<HTMLDivElement>(null)

  const ext = LANG_EXT[language?.toLowerCase()] ?? '.txt'

  const extLabel = ext.replace('.', '').toUpperCase() || 'TXT'

  const handleCopy = async () => {

    try {

      await navigator.clipboard.writeText(content)

      setCopied(true)

      setTimeout(() => setCopied(false), 2000)

    } catch (_) {}

  }

  const handleDownload = () => {

    const blob = new Blob([content], { type: 'text/plain' })

    const url = URL.createObjectURL(blob)

    const a = document.createElement('a')

    a.href = url

    a.download = `code${ext}`

    a.click()

    URL.revokeObjectURL(url)

    setMenuOpen(false)

  }

  useEffect(() => {

    if (!menuOpen) return

    const handler = (e: MouseEvent) => {

      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {

        setMenuOpen(false)

      }

    }

    document.addEventListener('mousedown', handler)

    return () => document.removeEventListener('mousedown', handler)

  }, [menuOpen])

  return (

    <div className="group relative bg-[#1d1d1b] border border-brand-border rounded-none sm:rounded-lg -mx-2 sm:mx-0 my-4 shadow-lg z-10">

      {/* Split-button — top-right; always visible on touch (no hover), hover-reveal on desktop */}

      <div ref={menuRef} className="absolute top-2 right-2 z-50 flex items-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity duration-150">


        {/* Copy */}

        <button

          onClick={handleCopy}

          className="flex items-center gap-1.5 px-3 h-9 text-[11px] font-medium rounded-l-md border border-r-0 border-[#30363d] bg-[#262624] text-[#a6a29c] hover:text-[#e9e8e6] hover:bg-[#313130] transition-colors select-none"

        >

          {copied ? (

            <>

              <Check className="w-3 h-3 text-[#3fb950]" />

              <span className="text-[#3fb950]">Copied</span>

            </>

          ) : (

            <>

              <Copy className="w-3 h-3" />

              <span>Copy</span>

            </>

          )}

        </button>

        {/* Chevron */}

        <div className="relative flex">

          <button

            onClick={() => setMenuOpen(o => !o)}

            className="flex items-center justify-center px-2.5 h-9 rounded-r-md border border-[#30363d] bg-[#262624] text-[#a6a29c] hover:text-[#e9e8e6] hover:bg-[#313130] transition-colors"

          >

            <ChevronDown className="w-3 h-3" />

          </button>

          {menuOpen && (

            <div className="absolute top-full right-0 mt-1 w-44 rounded-lg border border-[#30363d] bg-[#161b22] shadow-2xl overflow-hidden">

              <button

                onClick={handleDownload}

                className="w-full text-left px-3 py-2.5 text-[12px] text-[#c9d1d9] hover:bg-[#21262d] transition-colors flex items-center gap-2"

              >

                <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="text-[#58a6ff]">

                  <path d="M2.75 14A1.75 1.75 0 011 12.25v-2.5a.75.75 0 011.5 0v2.5c0 .138.112.25.25.25h10.5a.25.25 0 00.25-.25v-2.5a.75.75 0 011.5 0v2.5A1.75 1.75 0 0113.25 14H2.75z"/>

                  <path d="M7.25 7.689V2a.75.75 0 011.5 0v5.689l1.97-1.969a.749.749 0 111.06 1.06l-3.25 3.25a.749.749 0 01-1.06 0L4.22 6.78a.749.749 0 111.06-1.06l1.97 1.969z"/>

                </svg>

                Download as {extLabel}

              </button>

              <button

                onClick={() => {

                  const event = new CustomEvent('open-artifact', {

                    detail: { filename: `code${ext}`, content }

                  })

                  window.dispatchEvent(event)

                  setMenuOpen(false)

                }}

                className="w-full text-left px-3 py-2.5 text-[12px] text-[#c9d1d9] hover:bg-[#21262d] transition-colors flex items-center gap-2 border-t border-[#1e2025]"

              >

                <FileText className="w-3.5 h-3.5 text-[#ffffff]" />

                View as Artifact

              </button>

              <button

                onClick={() => {

                  const event = new CustomEvent('open-file-preview', {

                    detail: {

                      name: `code${ext}`,

                      type: 'text/plain',

                      content: content

                    }

                  })

                  window.dispatchEvent(event)

                  setMenuOpen(false)

                }}

                className="w-full text-left px-3 py-2.5 text-[12px] text-[#c9d1d9] hover:bg-[#21262d] transition-colors flex items-center gap-2 border-t border-[#1e2025]"

              >

                <Maximize2 className="w-3.5 h-3.5 text-brand-text/80" />

                Preview Fullscreen

              </button>

            </div>

          )}

        </div>

      </div>

      {/* Language label — bottom-left */}

      {language && (

        <span className="absolute bottom-2 left-3 z-10 text-[9px] font-bold text-[#3a3e45] tracking-widest uppercase font-mono select-none pointer-events-none">

          {language}

        </span>

      )}

      <pre className="p-3 pb-7 sm:p-4 overflow-x-auto">

        <code className="text-[13px] sm:text-[12px] font-mono text-[#d4c5a0]/85 leading-[1.6] block whitespace-pre">

          {content}

        </code>

      </pre>

    </div>

  )

}

const BLOCKED_SOURCE_DOMAINS = new Set([
  'thebiglead.com',
  'sundayguardianlive.com',
  'sportsmole.co.uk',
  'caughtoffside.com',
  'hitc.com',
  'tribalfootball.com',
  'givemesport.com',
  'footballtransfers.com',
  'yardbarker.com',
  'essentiallysports.com',
  'fanbuzz.com',
  'bolavip.com',
  'clutchpoints.com',
])

const SourcesStack: React.FC<{ sources: Source[] }> = ({ sources }) => {

  const [isOpen, setIsOpen] = useState(false)

  // Filter out known clickbait and content mill scraper domains
  const validSources = React.useMemo(() => {
    return (sources || []).filter((s) => {
      try {
        const host = new URL(s.url).hostname.toLowerCase().replace(/^www\./, '')
        if (BLOCKED_SOURCE_DOMAINS.has(host)) return false
        for (const b of BLOCKED_SOURCE_DOMAINS) {
          if (host.endsWith('.' + b)) return false
        }
        return true
      } catch (_) {
        return false
      }
    })
  }, [sources])

  // Get unique hosts/domains for the favicons
  const uniqueHosts = React.useMemo(() => {
    const hosts: string[] = []
    const seen = new Set<string>()

    for (const src of validSources) {
      try {
        let host = new URL(src.url).hostname
        if (host === 'vertexaisearch.cloud.google.com' && src.title && src.title.includes('.')) {
          host = src.title.trim().toLowerCase()
        }
        if (host && !seen.has(host)) {
          seen.add(host)
          hosts.push(host)
        }
      } catch (_) {}
    }

    return hosts
  }, [validSources])

  if (!validSources || validSources.length === 0) return null

  const displayedFavicons = uniqueHosts.slice(0, 3)

  return (

    <div className="mt-3.5 pt-3 border-t border-[#1e2025]/40 px-1 select-none">

      {/* Clickable Header Stack */}

      <div 

        onClick={() => setIsOpen(!isOpen)}

        className="flex items-center gap-3 cursor-pointer group/stack w-fit"

      >

        {/* Overlapping circle stack */}

        <div className="flex items-center">

          {displayedFavicons.map((host, idx) => (

            <div 

              key={idx}

              className="w-6 h-6 rounded-full border border-[#1e2025] bg-[#0c0d10] flex items-center justify-center overflow-hidden shrink-0 relative transition-all duration-200 hover:translate-y-[-2px] hover:scale-[1.05] shadow-md shadow-black/40"

              style={{

                marginLeft: idx > 0 ? '-10px' : '0px',

                zIndex: 10 - idx,

              }}

            >

              <img

                src={`https://icons.duckduckgo.com/ip3/${host}.ico`}

                alt=""

                className="w-4 h-4 rounded-sm object-contain"

                onError={(e) => {

                  e.currentTarget.style.display = 'none';

                }}

              />

            </div>

          ))}

        </div>

        {/* Text and Toggle Indicator */}

        <div className="flex items-center gap-1.5">

          <span className="text-[12px] font-semibold text-[#8e95a2] group-hover/stack:text-[#f0ece4] transition-colors duration-150">

            {validSources.length} {validSources.length === 1 ? 'site' : 'sites'}

          </span>

          <span className="text-[#8e95a2]/60 group-hover/stack:text-[#ffffff] transition-colors duration-150">

            {isOpen ? (

              <ChevronUp className="w-3.5 h-3.5" />

            ) : (

              <ChevronDown className="w-3.5 h-3.5" />

            )}

          </span>

        </div>

      </div>

      {/* Expanded Grid of Source Cards */}

      {isOpen && (

        <div className="flex flex-wrap gap-2 mt-3 animate-fadeIn">

          {validSources.map((src, si) => (

            <a

              key={si}

              href={src.url}

              target="_blank"

              rel="noopener noreferrer"

              title={src.title || src.url}

              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-brand-border bg-brand-card/95 hover:border-white/30 hover:bg-white/5 transition-all duration-200 group/badge max-w-[240px] shadow-sm animate-fadeIn"

            >

              <img

                src={`https://icons.duckduckgo.com/ip3/${(() => {

                  try {

                    let host = new URL(src.url).hostname

                    if (host === 'vertexaisearch.cloud.google.com' && src.title && src.title.includes('.')) {

                      host = src.title.trim().toLowerCase()

                    }

                    return host

                  } catch (_) {

                    return ''

                  }

                })()}.ico`}

                alt=""

                className="w-3.5 h-3.5 rounded-sm shrink-0 opacity-75 group-hover/badge:opacity-100 transition-opacity duration-150"

                onError={(e) => {

                  e.currentTarget.style.display = 'none';

                }}

              />

              <span className="text-[10.5px] font-medium text-[#8e95a2] group-hover/badge:text-[#f0ece4] truncate tracking-tight transition-colors duration-150">

                {(() => {
                  const t = src.title || ''
                  // If title looks like a real title (not a URL), use it
                  if (t && !t.startsWith('http') && !t.startsWith('vertexai')) return t
                  // Otherwise extract clean domain from URL
                  try {
                    const host = new URL(src.url).hostname.replace('www.', '')
                    return host === 'vertexaisearch.cloud.google.com' ? 'Google Search' : host
                  } catch { return 'Source' }
                })()}

              </span>

              <span className="text-[9px] text-[#8e95a2]/30 group-hover/badge:text-[#ffffff]/70 shrink-0 transition-all duration-150 translate-y-[0.5px] group-hover/badge:translate-x-0.5 group-hover/badge:-translate-y-0.5">

                ↗

              </span>

            </a>

          ))}

        </div>

      )}

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

    } else {

      blocks.push({

        type: 'paragraph',

        content: lines[i].trim()

      })

      i++

    }

  }

  return blocks

}

// ─── Block markdown renderer ──────────────────────────────────────────────────

export function renderMarkdown(text: string, generatedFiles?: any[]): React.ReactNode {
  const extracted = extractSourcesSection(text)
  const noticeText = extractNoticeSection(extracted.body)
  const noticeBlock = noticeText ? <PolicyNoticeCard notice={noticeText} /> : null
  const sourcesBlock = extracted.sources.length > 0 ? <SourcesBlock sources={extracted.sources} /> : null
  const blocks = parseMarkdownToBlocks(extracted.body)

  return (
    <div className="space-y-5 font-serif max-w-[760px]">
      {blocks.map((block, index) => {
        const key = `block-${index}`

        switch (block.type) {
          case 'heading': {
            const level = block.level || 1
            const content = renderInline(block.content || '', key, generatedFiles)

            switch (level) {
              case 1:
                return (
                  <h1 key={key} className="text-[20px] sm:text-[22px] font-bold text-white mt-4 mb-2 tracking-tight font-sans">
                    {content}
                  </h1>
                )
              case 2:
                return (
                  <h2 key={key} className="text-[18px] sm:text-[19px] font-semibold text-white mt-3.5 mb-1.5 tracking-tight font-sans">
                    {content}
                  </h2>
                )
              case 3:
                return (
                  <h3 key={key} className="text-[16px] sm:text-[17px] font-semibold text-[#f4f4f5] mt-3 mb-1 tracking-tight font-sans">
                    {content}
                  </h3>
                )
              case 4:
                return (
                  <h4 key={key} className="text-[15px] sm:text-[15.5px] font-semibold text-[#e4e4e7] mt-2.5 mb-1 tracking-tight font-sans">
                    {content}
                  </h4>
                )
              case 5:
                return (
                  <h5 key={key} className="text-[14px] sm:text-[14.5px] font-semibold text-[#e4e4e7] mt-2 mb-1 tracking-tight font-sans">
                    {content}
                  </h5>
                )
              case 6:
                return (
                  <h6 key={key} className="text-[13.5px] sm:text-[14px] font-semibold text-[#e4e4e7] mt-2 mb-1 tracking-tight font-sans">
                    {content}
                  </h6>
                )
              default:
                return (
                  <h1 key={key} className="text-[20px] sm:text-[22px] font-bold text-white mt-4 mb-2 tracking-tight font-sans">
                    {content}
                  </h1>
                )
            }
          }

          case 'code': {
            const content = block.content || ''
            const lang = (block.language || '').toLowerCase().trim()

            // Sports match card native rendering: if the code block is tagged sports_card / match_card
            if (lang === 'sports_card' || lang === 'match_card' || lang === 'live_score' || lang === 'scoreboard') {
              try {
                const cardData = JSON.parse(content)
                if (cardData && typeof cardData === 'object' && cardData.home_team && cardData.away_team) {
                  return <SportsMatchCard key={key} {...cardData} />
                }
              } catch {
                // fall through to standard code block if parsing fails
              }
            }

            // Ochuko parity: code blocks in chat are ALWAYS plain highlighted
            // code with a single Copy action. No inline iframe previews, no
            // auto-SVG cards — deliverables live in files (sandbox_write) and
            // present through the ArtifactPanel; widgets arrive via
            // msg.widgetData (visualize__show_widget), a separate path.

            return (
              <CodeBlock
                key={key}
                language={block.language || 'text'}
                content={content}
              />
            )
          }

          case 'blockquote': {
            return (
              <BlockquoteWithCopy
                key={key}
                content={block.content || ''}
              >
                {renderInline(block.content || '', key, generatedFiles)}
              </BlockquoteWithCopy>
            )
          }

          case 'table': {
            return (
              <div key={key} className="overflow-x-auto my-3 border border-white/10 rounded-lg bg-[#0e1013]/60 shadow-sm font-sans">
                <table className="min-w-full divide-y divide-white/10 text-left text-[13px]">
                  <thead className="bg-[#1c1e22]/60 text-white">
                    <tr>
                      {block.headers?.map((header, hIdx) => (
                        <th
                          key={hIdx}
                          className="px-3 py-2 font-semibold border-b border-white/10 tracking-wider text-[11px] uppercase text-white/70"
                        >
                          {renderInline(header, `${key}-th-${hIdx}`, generatedFiles)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {block.rows?.map((row, rIdx) => (
                      <tr
                        key={rIdx}
                        className={rIdx % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.02]'}
                      >
                        {row.map((cell, cIdx) => (
                          <td key={cIdx} className="px-3 py-1.5 text-white/85">
                            {renderInline(cell, `${key}-td-${rIdx}-${cIdx}`, generatedFiles)}
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
                <ol key={key} className="my-3 space-y-3 pl-0.5 max-w-[760px]">
                  {block.items?.map((item, j) => (
                    <li key={j} className="flex gap-2.5 leading-relaxed items-start">
                      <span className="text-white/60 font-sans font-semibold text-[14px] shrink-0 min-w-[1.4rem] mt-[1.5px]">
                        {j + 1}.
                      </span>
                      <span className="text-[16px] sm:text-[15.5px] text-[#e3e3df] leading-[1.7]">
                        {renderInline(item, `${key}-oli-${j}`, generatedFiles)}
                      </span>
                    </li>
                  ))}
                </ol>
              )
            } else {
              return (
                <ul key={key} className="my-3 space-y-2.5 pl-0.5 max-w-[760px]">
                  {block.items?.map((item, j) => (
                    <li key={j} className="flex gap-3 leading-relaxed items-start">
                      <span className="text-white/50 text-[15px] leading-[1.7] shrink-0 select-none">·</span>
                      <span className="text-[16px] sm:text-[15.5px] text-[#e3e3df] leading-[1.7]">
                        {renderInline(item, `${key}-uli-${j}`, generatedFiles)}
                      </span>
                    </li>
                  ))}
                </ul>
              )
            }
          }

          case 'hr': {
            return <hr key={key} className="border-white/10 my-4" />
          }

          case 'paragraph': {
            return (
              <p key={key} className="text-[16px] sm:text-[15.5px] text-[#e3e3df] leading-[1.7] tracking-normal font-sans sm:font-serif">
                {renderInline(block.content || '', key, generatedFiles)}
              </p>
            )
          }

          default:
            return null
        }
      })}
      {sourcesBlock}
      {noticeBlock}
    </div>
  )
}

// ── Policy / stop notice card ─────────────────────────────────────────────────
// The backend degrades safety refusals and early stops into a trailing
// "*(Note: Response stopped early: ...)*" marker. Detect it and render a calm,
// distinct notice card instead of error-styled inline text.

function extractNoticeSection(text: string): string | null {
  const raw = text || ''
  const m = raw.match(/\*{0,2}\(Note: Response stopped early:[^]*\)\*{0,2}\s*$/)
  if (m && m.index !== undefined) {
    const noticeText = m[0].replace(/^\*{0,2}\(Note: Response stopped early:\s*/, '').replace(/\)\*{0,2}\s*$/, '')
    return noticeText.trim() || null
  }
  return null
}

function PolicyNoticeCard({ notice }: { notice: string }) {
  const isGuardrail = /safety|guardrail|flagged|policy/i.test(notice)
  return (
    <div className="mt-2.5 flex items-start gap-2.5 border border-white/10 rounded-lg bg-white/[0.03] px-3.5 py-3 font-sans">
      <span
        className="shrink-0 mt-[1px] inline-flex items-center justify-center w-[18px] h-[18px] rounded-full text-[10px] font-bold bg-white/10 border border-white/20 text-white/70 leading-none"
        aria-hidden="true"
      >
        i
      </span>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-white/50">
          {isGuardrail ? 'Policy notice' : 'Response stopped early'}
        </p>
        <p className="text-[13px] text-white/70 leading-relaxed mt-0.5">{notice}</p>
      </div>
    </div>
  )
}

// ── Citation sources block ────────────────────────────────────────────────────
// Extracts a trailing "**Sources:**" section (emitted by the research citation
// contract) from message text and renders it as a collapsible glass-HUD block.

function extractSourcesSection(text: string): { body: string; sources: { title: string; url: string }[] } {
  const raw = text || ''
  const patterns = [
    /\n\*\*Sources?:?\*\*\s*\n?/i,
    /\nSources?:\s*\n/i,
  ]
  for (const re of patterns) {
    const m = raw.match(re)
    if (m && m.index !== undefined && m.index > raw.length * 0.25) {
      const body = raw.slice(0, m.index)
      const section = raw.slice(m.index + m[0].length)
      const sources: { title: string; url: string }[] = []
      const seen = new Set<string>()
      const lineRe = /\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g
      let lm: RegExpExecArray | null
      while ((lm = lineRe.exec(section)) !== null) {
        const url = lm[2]
        if (!seen.has(url)) {
          seen.add(url)
          sources.push({ title: lm[1] || url, url })
        }
      }
      if (sources.length === 0) {
        const urlRe = /(https?:\/\/[^\s)]+)/g
        while ((lm = urlRe.exec(section)) !== null) {
          const url = lm[1]
          if (!seen.has(url)) { seen.add(url); sources.push({ title: url, url }) }
        }
      }
      if (sources.length > 0) return { body, sources }
    }
  }
  return { body: raw, sources: [] }
}

function SourcesBlock({ sources }: { sources: { title: string; url: string }[] }) {
  const [open, setOpen] = React.useState(false)
  return (
    <div className="mt-2.5 border border-white/10 rounded-lg bg-[#0e1013]/60 overflow-hidden font-sans">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-[12px] font-semibold uppercase tracking-wider text-white/60 hover:text-white/90 hover:bg-white/[0.03] transition duration-150"
      >
        <span className="text-[9px] leading-none text-white/40">{open ? '▾' : '▸'}</span>
        Sources
        <span className="ml-1 text-[10px] font-normal normal-case tracking-normal text-white/40">
          ({sources.length})
        </span>
      </button>
      {open && (
        <ul className="px-3.5 pb-3 pt-0.5 space-y-1.5 border-t border-white/[0.06]">
          {sources.map((s, i) => {
            let domain = ''
            try { domain = new URL(s.url).hostname.replace(/^www\./, '') } catch { /* keep empty */ }
            return (
              <li key={i} className="flex items-baseline gap-2 text-[13px]">
                <span className="shrink-0 inline-flex items-center justify-center min-w-[16px] h-[15px] px-[4px] rounded-full text-[9.5px] font-semibold bg-white/10 border border-white/20 text-white/70 leading-none">
                  {i + 1}
                </span>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white/80 hover:text-white underline underline-offset-4 decoration-white/30 truncate transition duration-150"
                  title={domain || s.url}
                >
                  {s.title}
                </a>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function getFriendlyErrorMessage(message: string): string {

  const lower = message.toLowerCase()

  if (
    lower.includes("provisioned throughput") ||
    lower.includes("high demand") ||
    lower.includes("peak load") ||
    lower.includes("maximum usage size")
  ) {
    return "The AI service is currently experiencing extremely high demand. Please try again in a few moments, or contact your administrator to configure Provisioned Throughput for dedicated capacity."
  }

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

  if (
    lower.includes("streaming connection issue") ||
    lower.includes("unexpected keyword argument") ||
    lower.includes("asyncresponses") ||
    lower.includes("stream()") ||
    (lower.includes("connection issue") && !lower.includes("database"))
  ) {
    return "Something went wrong with the AI response stream. Please try sending your message again."
  }

  if (lower.includes("supabase") || lower.includes("database") || lower.includes("postgres") || lower.includes("db") || lower.includes("relation")) {

    return "We are experiencing a temporary database connection issue. Our team is working to restore full connectivity; please try again in a few moments."

  }

  if (lower.includes("500") || lower.includes("internal server") || lower.includes("failed to load resource")) {

    return "We encountered a temporary technical issue. Our systems are recovering; please try sending your message again in a moment."

  }

  if (lower.includes("failed to fetch") || lower.includes("networkerror") || lower.includes("load failed") || lower.includes("network error") || lower.includes("server unavailable")) {

    return "We couldn't reach the server — it may still be starting up. Please try sending your message again in a few seconds."

  }

  if (lower.includes("openai") || lower.includes("rate limit") || lower.includes("model")) {

    return "The AI engine is temporarily experiencing high traffic. Please try again shortly."

  }

  if (lower.includes("completed event") || lower.includes("guardrail") || lower.includes("content_filter") || lower.includes("safety")) {

    return "This request was blocked by the system safety guardrails because the prompt or response contained content violating safety policies. Please rephrase your query and try again."

  }

  return `We were unable to process your request at this moment (${message}). Please try again in a few moments or contact support.`

}

// Phase 2 — uncapped OODA UI: "Step N" only. The loop budget self-extends
// while the model keeps making tool-call progress, so there is no meaningful
// "of M" ceiling to display. Progress track is indeterminate (pulsing) while
// running and snaps full on completion.
const AgentStepIndicator: React.FC<{ step: number; maxSteps?: number; label?: string; isComplete?: boolean }> = ({ step, label, isComplete }) => {
  const currentStep = Math.max(1, step || 1)

  return (
    <div className="w-full max-w-full min-w-0 my-2 px-2.5 sm:px-3.5 py-2 sm:py-2.5 rounded-xl bg-[#0c0d10]/95 border border-white/[0.08] shadow-md backdrop-blur-xl select-none animate-fadeIn flex flex-col gap-1.5 box-border overflow-hidden">
      <div className="flex items-center justify-between gap-1.5 sm:gap-2.5 w-full min-w-0">
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 flex-1 overflow-hidden">
          {/* Minimalist Status Dot */}
          <div className="flex items-center justify-center shrink-0 w-2.5 h-2.5">
            <span className={`w-1.5 h-1.5 rounded-full ${isComplete ? 'bg-[#8e95a2]' : 'bg-[#a0a6b2] animate-pulse'}`} />
          </div>

          {/* Monospace Badge — uncapped: no "of M" suffix */}
          <span className="px-1.5 sm:px-2 py-0.5 rounded bg-[#16181d] border border-white/10 text-[9px] sm:text-[9.5px] font-mono font-medium text-[#a0a6b2] tracking-wider uppercase shrink-0">
            {`STEP ${currentStep}`}
          </span>

          {/* Action Label — responsive truncation */}
          {label ? (
            <span className="text-[11px] sm:text-[11.5px] font-sans text-[#cbd5e1] truncate min-w-0 flex-1 leading-snug" title={label}>
              {label}
            </span>
          ) : (
            <span className="text-[11px] sm:text-[11.5px] font-sans text-[#717784] italic truncate min-w-0 flex-1 leading-snug">
              {isComplete ? 'Completed' : 'Running pipeline...'}
            </span>
          )}
        </div>
      </div>

      {/* Razor-thin Indeterminate Progress Track */}
      <div className="w-full h-[1.5px] sm:h-[2px] bg-white/[0.08] rounded-full overflow-hidden">
        <div
          className={`h-full bg-[#8e95a2] transition-all duration-300 ease-out rounded-full opacity-80 ${isComplete ? '' : 'animate-pulse'}`}
          style={{ width: isComplete ? '100%' : '35%' }}
        />
      </div>
    </div>
  )
}

// Phase 3 — live task checklist (update_todo / agent_todo SSE). Claude Code-style
// TodoWrite rendering: checkbox states, strike-through on completion, highlight
// on the single in-progress item.
const AgentTodoChecklist: React.FC<{ todos: { content: string; status: string }[] }> = ({ todos }) => {
  if (!todos || todos.length === 0) return null
  const done = todos.filter(t => t.status === 'completed').length
  return (
    <div className="w-full max-w-full min-w-0 my-2 px-2.5 sm:px-3.5 py-2 rounded-xl bg-[#0c0d10]/95 border border-white/[0.08] shadow-md backdrop-blur-xl select-none animate-fadeIn flex flex-col gap-1 box-border overflow-hidden">
      <div className="flex items-center gap-2 px-0.5">
        <span className="px-1.5 sm:px-2 py-0.5 rounded bg-[#16181d] border border-white/10 text-[9px] sm:text-[9.5px] font-mono font-medium text-[#a0a6b2] tracking-wider uppercase shrink-0">
          {`TASKS ${done}/${todos.length}`}
        </span>
        <span className="text-[10px] font-mono text-[#717784] tracking-wider shrink-0 tabular-nums ml-auto">
          {`${Math.round((done / todos.length) * 100)}%`}
        </span>
      </div>
      <ul className="flex flex-col gap-1 mt-1">
        {todos.map((t, i) => {
          const isDone = t.status === 'completed'
          const isActive = t.status === 'in_progress'
          return (
            <li key={i} className="flex items-start gap-2 min-w-0">
              <span className={`mt-[5px] w-3 h-3 shrink-0 rounded-[4px] border flex items-center justify-center text-[8px] leading-none ${isDone ? 'bg-[#8e95a2] border-[#8e95a2] text-[#0c0d10]' : isActive ? 'border-[#a0a6b2]' : 'border-white/20'}`}>
                {isDone ? '✓' : ''}
              </span>
              <span
                className={`text-[11.5px] leading-snug min-w-0 break-words ${isDone ? 'text-[#717784] line-through' : isActive ? 'text-[#e5e9f0] font-medium' : 'text-[#cbd5e1]'}`}
              >
                {t.content}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const ThinkingPanel: React.FC<{ content: string; isStreaming?: boolean }> = ({ content, isStreaming }) => {
  const [expanded, setExpanded] = useState<boolean>(!!isStreaming)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-expand when reasoning starts, auto-collapse when final answer finishes
  useEffect(() => {
    if (isStreaming) {
      setExpanded(true)
    } else {
      // Auto-collapse cleanly once reasoning + response complete
      setExpanded(false)
    }
  }, [isStreaming])

  // Auto-scroll to keep latest thought tokens in view while streaming
  useEffect(() => {
    if (isStreaming && expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [content, isStreaming, expanded])

  if (!content || !content.trim()) return null

  const trimmed = content.trim()
  const wordCount = trimmed.split(/\s+/).length

  return (
    <div className={`my-2 rounded-lg border overflow-hidden select-none transition-all duration-300 ${
      isStreaming
        ? 'bg-brand-card/95 border-white/[0.14]'
        : 'bg-[#1d1d1b]/95 border-white/[0.08] shadow-md'
    }`}>
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 bg-white/[0.03] hover:bg-white/[0.05] border-b border-white/[0.05] transition-colors duration-150 text-left"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className={`relative flex items-center justify-center w-5 h-5 rounded-md ${
            isStreaming ? 'bg-white/[0.08] text-white/80' : 'bg-white/[0.05] text-[#a6a29c]'
          }`}>
            <Brain className={`w-3.5 h-3.5 ${isStreaming ? 'animate-pulse' : ''}`} />
            {isStreaming && (
              <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-white/70 animate-ping" />
            )}
          </div>
          <span className="text-[12px] font-mono font-medium text-white/60 tracking-wide truncate">
            {isStreaming ? 'Reasoning step-by-step...' : `Thought process (${wordCount} words)`}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-[#8e95a2]">
          {isStreaming ? (
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-white/[0.06] border border-white/15 text-[10px] font-mono text-white/70">
              <span className="w-1.5 h-1.5 rounded-full bg-white/70 animate-pulse" />
              <span>Thinking</span>
            </div>
          ) : (
            <span className="text-[10.5px] font-sans text-white/40">
              {expanded ? 'Hide' : 'Show details'}
            </span>
          )}
          {expanded ? <ChevronUp className="w-3.5 h-3.5 text-white/50" /> : <ChevronDown className="w-3.5 h-3.5 text-white/50" />}
        </div>
      </button>

      {expanded && (
        <div
          ref={scrollRef}
          className="p-3.5 max-h-80 overflow-y-auto font-mono text-[11.5px] text-[#a09e9e] leading-relaxed whitespace-pre-wrap select-text bg-[#07080c]/95 border-t border-white/[0.03] transition-all"
        >
          {trimmed}
        </div>
      )}
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

// ─── LazyMessage (Virtualized rendering for long message history) ────────────────

const ChatSkeleton: React.FC = () => (
    <div className="max-w-2xl mx-auto space-y-8 animate-pulse pt-4">
      {/* Assistant message skeleton */}
      <div className="flex gap-4 items-start">
        <div className="w-8 h-8 rounded-lg bg-[#1e2025]/60 border border-[#ffffff]/5 shrink-0" />
        <div className="flex-1 space-y-3 pt-1">
          <div className="h-4 bg-[#1e2025]/60 rounded w-1/4" />
          <div className="h-3 bg-[#1e2025]/40 rounded w-3/4" />
          <div className="h-3 bg-[#1e2025]/40 rounded w-5/6" />
          <div className="h-3 bg-[#1e2025]/30 rounded w-1/2" />
        </div>
      </div>
      
      {/* User message skeleton */}
      <div className="flex gap-4 items-start justify-end">
        <div className="flex flex-col items-end space-y-3 w-[70%]">
          <div className="h-4 bg-[#1e2025]/60 rounded w-1/3" />
          <div className="h-3 bg-[#1e2025]/40 rounded w-full" />
          <div className="h-3 bg-[#1e2025]/30 rounded w-2/3" />
        </div>
      </div>

      {/* Assistant message skeleton 2 */}
      <div className="flex gap-4 items-start">
        <div className="w-8 h-8 rounded-lg bg-[#1e2025]/60 border border-[#ffffff]/5 shrink-0" />
        <div className="flex-1 space-y-3 pt-1">
          <div className="h-4 bg-[#1e2025]/60 rounded w-1/5" />
          <div className="h-3 bg-[#1e2025]/40 rounded w-2/3" />
          <div className="h-3 bg-[#1e2025]/40 rounded w-4/5" />
        </div>
      </div>
    </div>
  )

const FileAttachmentChip: React.FC<{
  attachment: { name: string; jobType: 'ocr' | 'vision' | 'code'; url?: string }
}> = ({ attachment }) => {
  const isImage = attachment.jobType === 'vision'
  const isPdf   = attachment.jobType === 'ocr'
  const isCode  = attachment.jobType === 'code'

  const handlePreview = () => {
    if (!attachment.url) return
    let previewType = mimeFromName(attachment.name)
    if (isPdf) {
      previewType = 'application/pdf'
    }
    window.dispatchEvent(new CustomEvent('open-file-preview', {
      detail: {
        name: attachment.name,
        type: previewType,
        url: attachment.url,
      }
    }))
  }

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (attachment.url) triggerDirectDownload(attachment.url, attachment.name)
  }

  // ── Image thumbnail (vision jobs) — compact, elegant thumbnail ──────────────
  if (isImage) {
    return (
      <div
        onClick={handlePreview}
        title={attachment.url ? `Preview ${attachment.name}` : attachment.name}
        className={`relative group/img w-36 sm:w-40 h-24 sm:h-28 rounded-lg overflow-hidden shrink-0 border border-white/10 bg-black/40 shadow-sm ${
          attachment.url ? 'cursor-pointer hover:border-white/30' : 'cursor-default'
        } transition-all duration-200`}
      >
        {attachment.url ? (
          <img
            src={attachment.url}
            alt={attachment.name}
            className="w-full h-full object-cover rounded-lg"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center rounded-lg bg-white/5">
            <FileText className="w-5 h-5 text-white/30" />
          </div>
        )}
        {/* Subtle hover overlay with filename */}
        <div className="absolute inset-0 rounded-lg bg-black/60 opacity-0 group-hover/img:opacity-100 transition-opacity flex items-end p-2">
          <span className="text-[10px] text-white font-medium leading-tight truncate w-full">{attachment.name}</span>
        </div>
        {/* Download action (uploaded files) */}
        {attachment.url && (
          <button
            type="button"
            onClick={handleDownload}
            title={`Download ${attachment.name}`}
            className="absolute top-1.5 right-1.5 p-1.5 rounded-md bg-black/60 text-white/80 hover:text-white hover:bg-black/80 opacity-0 group-hover/img:opacity-100 transition"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    )
  }

  const ext = attachment.name.split('.').pop()?.toUpperCase() || 'FILE'
  const displayLabel = isCode ? `${ext} · Code` : (isPdf ? 'PDF · Document' : 'Document')

  // ── Document chip (OCR / PDF / Code) ──────────────────────────────────────────────
  return (
    <div
      onClick={handlePreview}
      title={attachment.url ? `Preview ${attachment.name}` : attachment.name}
      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-white/[0.06] border border-white/15 max-w-[210px] ${
        attachment.url ? 'cursor-pointer hover:bg-white/[0.12] hover:border-white/25' : 'cursor-default'
      } transition`}
    >
      <div className="w-6 h-6 rounded-md bg-white/10 flex items-center justify-center shrink-0">
        <FileText className="w-3.5 h-3.5 text-white/80" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[8.5px] font-bold text-white/50 uppercase tracking-wider leading-none mb-0.5">{displayLabel}</p>
        <p className="text-[11.5px] text-brand-text/90 font-medium truncate">{attachment.name}</p>
      </div>
      {attachment.url && (
        <div className="shrink-0 flex items-center gap-1 text-white/40">
          <button
            type="button"
            onClick={handleDownload}
            title={`Download ${attachment.name}`}
            className="p-1 rounded-md hover:text-white hover:bg-white/10 transition"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <ExternalLink className="w-2.5 h-2.5" />
        </div>
      )}
    </div>
  )
}

// LazyMessage is kept as a thin passthrough — it no longer estimates heights.
// Height guessing caused layout jumps when the real content differed from the
// estimate. The IntersectionObserver's 800 px rootMargin already pre-renders
// content well before it scrolls into view, so virtualisation is unnecessary.
const LazyMessage: React.FC<{
  children: React.ReactNode
  estimatedHeight?: number
  turnIndex?: number
}> = ({ children, turnIndex }) => {
  // Anchor div doubles as the TurnTracker scroll target for this turn.
  // Per-message ErrorBoundary: one malformed message can no longer blank the
  // whole chat — only that message degrades to a small error notice.
  return (
    <div data-turn-anchor={turnIndex}>
      <ErrorBoundary
        fallback={
          <div className="my-2 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-[12px] text-red-300/80">
            This message hit a rendering error. Other messages are unaffected.
          </div>
        }
      >
        {children}
      </ErrorBoundary>
    </div>
  )
}


// ── User-scoped cache helpers ─────────────────────────────────────────────────
// All keys are prefixed with userId so different users on the same browser
// never share cached conversations, IDs, or visit data.

function userCacheKey(userId: string, suffix: string): string {
  return `u_${userId}_${suffix}`
}

const saveConvoCache = (userId: string | null, id: string, messages: Message[], mode: string) => {
  if (!userId) return
  try {
    const cacheKey = userCacheKey(userId, `convo_cache_${id}`)
    localStorage.setItem(cacheKey, JSON.stringify({ messages, mode }))

    const idsKey = userCacheKey(userId, 'cached_convo_ids')
    let cachedIds: string[] = []
    try {
      const rawIds = localStorage.getItem(idsKey)
      cachedIds = rawIds ? JSON.parse(rawIds) : []
    } catch {}

    cachedIds = cachedIds.filter(cid => cid !== id)
    cachedIds.push(id)

    if (cachedIds.length > 20) {
      const oldestId = cachedIds.shift()
      if (oldestId) {
        localStorage.removeItem(userCacheKey(userId, `convo_cache_${oldestId}`))
      }
    }
    localStorage.setItem(idsKey, JSON.stringify(cachedIds))
  } catch (e) {
    console.warn("Failed to save conversation cache to localStorage:", e)
  }
}

// ── IndexedDB Directory Handle Persistence ──────────────────────────────────
const IDB_FS_NAME = 'ochuko_fs_store'
const IDB_FS_STORE = 'handles'
const IDB_FS_KEY = 'mounted_dir_handle'

function openDirHandleDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_FS_NAME, 1)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(IDB_FS_STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function persistDirHandle(handle: any): Promise<void> {
  try {
    const db = await openDirHandleDB()
    const tx = db.transaction(IDB_FS_STORE, 'readwrite')
    tx.objectStore(IDB_FS_STORE).put(handle, IDB_FS_KEY)
  } catch (err) {
    console.warn('Could not persist dir handle to IndexedDB:', err)
  }
}

async function retrievePersistedDirHandle(): Promise<any | null> {
  try {
    const db = await openDirHandleDB()
    return new Promise((resolve) => {
      const tx = db.transaction(IDB_FS_STORE, 'readonly')
      const req = tx.objectStore(IDB_FS_STORE).get(IDB_FS_KEY)
      req.onsuccess = () => resolve(req.result || null)
      req.onerror = () => resolve(null)
    })
  } catch {
    return null
  }
}

async function clearPersistedDirHandle(): Promise<void> {
  try {
    const db = await openDirHandleDB()
    const tx = db.transaction(IDB_FS_STORE, 'readwrite')
    tx.objectStore(IDB_FS_STORE).delete(IDB_FS_KEY)
  } catch {}
}

export const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [preferredName, setPreferredName] = useState<string | null>(null)
  // Stable ref holding the Supabase userId — set once on auth, used for cache key scoping.
  const userIdRef = useRef<string | null>(null)
  const [isFetchingHistory, setIsFetchingHistory] = useState(false)
  // ── Session-identity guard (Fix 1) ──
  // Set when the live Supabase session switches to a different user mid-session
  // (e.g. a sign-in in another tab synced via shared localStorage, or an OAuth
  // fragment re-auth). NON-DESTRUCTIVE: a modal asks the user what to do —
  // nothing is auto-reset, so multi-tab use and in-progress work are preserved.
  const [sessionSwitchPrompt, setSessionSwitchPrompt] = useState<{ newUserId: string; newEmail: string | null } | null>(null)
  // ── Conversation access error (Fix 2) ──
  // Shown as a non-destructive banner when loading a conversation's history is
  // rejected (403 — typically the conversation belongs to another account that
  // used this browser; 404 — deleted). Cached messages stay on screen.
  const [convoAccessError, setConvoAccessError] = useState<{ convoId: string; reason: string } | null>(null)
  const [dynamicGreeting, setDynamicGreeting] = useState<string>('Agent Ochuko')
  const [isEditingNickname, setIsEditingNickname] = useState(false)
  const [nicknameInput, setNicknameInput] = useState('')

  const [isLocked, setIsLocked] = useState(() => !!localStorage.getItem('app_lock_pin'))
  const [lockMode, setLockMode] = useState<'unlock' | 'setup' | 'change' | 'disable' | null>(null)

  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(min-width: 1024px)').matches
  })
  const [viewportHeight, setViewportHeight] = useState<number | null>(() => {
    return typeof window !== 'undefined' && window.visualViewport ? window.visualViewport.height : null
  })
  useEffect(() => {
    if (typeof window === 'undefined' || !window.visualViewport) return

    const handleViewportResize = () => {
      if (window.visualViewport) {
        setViewportHeight(window.visualViewport.height)
      }
    }

    window.visualViewport.addEventListener('resize', handleViewportResize)
    window.visualViewport.addEventListener('scroll', handleViewportResize)
    handleViewportResize()

    return () => {
      window.visualViewport?.removeEventListener('resize', handleViewportResize)
      window.visualViewport?.removeEventListener('scroll', handleViewportResize)
    }
  }, [])
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('sidebar_width')
    if (saved) return parseInt(saved, 10)
    // Default to 90% of viewport width, constrained between 220px and 480px
    const defaultWidth = Math.floor(window.innerWidth * 0.9)
    return Math.max(220, Math.min(480, defaultWidth))
  })
  const [pageZoom, setPageZoom] = useState(() => {
    if (typeof window === 'undefined') return 1.0
    const isDesk = window.matchMedia('(min-width: 1024px)').matches
    if (!isDesk) return 1.0
    const saved = localStorage.getItem('page_zoom')
    return saved ? parseFloat(saved) : 1.0
  })
  const isResizingRef = useRef(false)
  const [isDraggingSidebar, setIsDraggingSidebar] = useState(false)

  useEffect(() => {
    const handleResize = () => {
      const newIsDesktop = window.matchMedia('(min-width: 1024px)').matches
      setIsDesktop(newIsDesktop)
      if (!newIsDesktop) {
        setIsSidebarOpen(false)
        setIsSidebarHovered(false)
      }
    }
    window.addEventListener('resize', handleResize)
    window.addEventListener('orientationchange', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('orientationchange', handleResize)
    }
  }, [])

  // Update dynamic greeting when user data changes
  useEffect(() => {
    const greeting = getDynamicGreeting(preferredName, userEmail)
    setDynamicGreeting(greeting)
  }, [preferredName, userEmail])

  // Apply zoom to document (Desktop only: never zoom root on mobile, as CSS zoom forces Chromium/WebKit into desktop viewport scaling)
  useEffect(() => {
    if (isDesktop && pageZoom !== 1.0) {
      document.documentElement.style.zoom = pageZoom.toString()
      try { localStorage.setItem('page_zoom', pageZoom.toString()) } catch {}
    } else {
      document.documentElement.style.zoom = ''
      if (!isDesktop) {
        try { localStorage.removeItem('page_zoom') } catch {}
      }
    }
    return () => {
      document.documentElement.style.zoom = ''
    }
  }, [pageZoom, isDesktop])

  const startResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isResizingRef.current = true
    setIsDraggingSidebar(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return
      const newWidth = Math.max(220, Math.min(480, e.clientX - 12))
      setSidebarWidth(newWidth)
    }
    const handleMouseUp = () => {
      if (!isResizingRef.current) return
      isResizingRef.current = false
      setIsDraggingSidebar(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      localStorage.setItem('sidebar_width', sidebarWidth.toString())
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [sidebarWidth])

  // Auto-lock after 5 minutes of idle time
  useEffect(() => {
    if (!localStorage.getItem('app_lock_pin') || isLocked) return

    let idleTimeout: any

    const resetTimer = () => {
      clearTimeout(idleTimeout)
      idleTimeout = setTimeout(() => {
        setIsLocked(true)
      }, 5 * 60 * 1000)
    }

    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']
    events.forEach(e => window.addEventListener(e, resetTimer))
    resetTimer()

    return () => {
      clearTimeout(idleTimeout)
      events.forEach(e => window.removeEventListener(e, resetTimer))
    }
  }, [isLocked])

  // Messages start empty — hydrated from the user-scoped cache ONLY after
  // getUser() resolves so we never accidentally show another user's data.
  const [messages, setMessages] = useState<Message[]>([])
  const [expandedCompactionIndices, setExpandedCompactionIndices] = useState<Set<number>>(new Set())

  const [input, setInput] = useState('')

  // Capability-page handoff tracking: when Capabilities navigates here with
  // /?prompt=...&mode=..., the auth-hydration effect below must NOT clobber
  // the URL-provided mode (it defaults fresh sessions to 'discuss') nor
  // hydrate a stale cached conversation under the new prompt.
  const urlModeRef = useRef<'think' | 'solve' | 'discuss' | 'agent' | null>(null)
  const capabilityHandoffRef = useRef(false)

  // Read prompt and mode from URL parameter (e.g., from capabilities page play buttons)
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search)
    const promptParam = searchParams.get('prompt')
    const modeParam = searchParams.get('mode')
    if (modeParam && ['think', 'solve', 'discuss', 'agent'].includes(modeParam)) {
      urlModeRef.current = modeParam as 'think' | 'solve' | 'discuss' | 'agent'
      setMode(modeParam as any)
    }
    if (promptParam) {
      capabilityHandoffRef.current = true
      setInput(decodeURIComponent(promptParam))
      // Capability prompts always start a fresh chat — never resume the cached one
      setActiveConversationId('00000000-0000-0000-0000-000000000000')
      setMessages([])
      // Clear the URL parameter to prevent re-triggering
      window.history.replaceState({}, '', window.location.pathname)
      // Focus on input so user can easily send
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [location.search])

  const [isStreaming, setIsStreaming] = useState(false)

  // Mode also deferred — will be restored in the getUser() useEffect below.
  const [mode, setMode] = useState<'think' | 'solve' | 'discuss' | 'agent'>('discuss')

  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const [isSidebarHovered, setIsSidebarHovered] = useState(false)

  const [isOnline, setIsOnline] = useState(navigator.onLine)

  const [isShareModalOpen, setIsShareModalOpen] = useState(false)
  const [isModeSheetOpen, setIsModeSheetOpen] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [showCapabilitiesNote, setShowCapabilitiesNote] = useState(() => !localStorage.getItem('dismissed_capabilities_note'))

  const handleShareToggle = async (shouldShare: boolean) => {
    if (!activeConversationId || activeConversationId === '00000000-0000-0000-0000-000000000000') return
    setSharing(true)
    try {
      const token = await getEffectiveToken()
      if (!token) return

      const res = await fetch(`${API_BASE}/v1/conversations/${activeConversationId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ is_shared: shouldShare })
      })

      if (res.ok) {
        const data = await res.json()
        setConversations(prev => prev.map(c => 
          c.id === activeConversationId 
            ? { ...c, is_shared: shouldShare, share_token: data.share_token }
            : c
        ))
        if (shouldShare && data.share_token) {
          const shareUrl = `${window.location.origin}/shared/?token=${data.share_token}`
          await navigator.clipboard.writeText(shareUrl)
          showToast('Link copied!', 'info')
        } else {
          showToast('Sharing disabled', 'info')
        }
      } else {
        showToast('Failed to update share status', 'error')
      }
    } catch (err) {
      console.error('Failed to toggle share status:', err)
      showToast('Error updating share status', 'error')
    } finally {
      setSharing(false)
    }
  }

  const [isHeaderSettingsOpen, setIsHeaderSettingsOpen] = useState(false)
  const [isWorkstationAccessEnabled, setIsWorkstationAccessEnabled] = useState<boolean>(() => {
    return localStorage.getItem('ochuko_workstation_access_enabled') === 'true'
  })
  const [mountedFolderName, setMountedFolderName] = useState<string | null>(() => {
    return localStorage.getItem('ochuko_mounted_folder_name')
  })
  const headerSettingsRef = useRef<HTMLDivElement>(null)

  // Auto-sync Workstation Access with mode transitions:
  // Automatically turns ON in Agent Mode, and turns OFF when switching to Think/Solve/Discuss.
  const prevModeRef = useRef(mode)
  useEffect(() => {
    if (prevModeRef.current !== mode) {
      const isNowAgent = mode === 'agent'
      setIsWorkstationAccessEnabled(isNowAgent)
      localStorage.setItem('ochuko_workstation_access_enabled', isNowAgent ? 'true' : 'false')
      window.dispatchEvent(new Event('ochuko_workstation_access_changed'))
      if (!isNowAgent) {
        // Pattern B: Proactively shut down bridge daemon on mode exit to preserve laptop battery
        fetch('http://127.0.0.1:3920/shutdown', { method: 'POST', mode: 'no-cors' }).catch(() => {})
      }
      prevModeRef.current = mode
    }
  }, [mode])

  const handleLaunchBridge = () => {
    window.location.href = 'ochuko://start'
    showToast('Launching Workstation Bridge on-demand (Pattern A)...', 'info')
    let attempts = 0
    const interval = setInterval(async () => {
      attempts++
      try {
        const res = await fetch('http://127.0.0.1:3920/health', { signal: AbortSignal.timeout(800) })
        if (res.ok) {
          clearInterval(interval)
          showToast('Workstation Bridge connected on port 3920!', 'info')
          window.dispatchEvent(new Event('ochuko_workstation_access_changed'))
        }
      } catch {}
      if (attempts >= 10) clearInterval(interval)
    }, 600)
  }

  useEffect(() => {
    const handleStorageChange = () => {
      setIsWorkstationAccessEnabled(localStorage.getItem('ochuko_workstation_access_enabled') === 'true')
    }
    const handleFolderMounted = (e: any) => {
      setMountedFolderName(e.detail?.folderName || localStorage.getItem('ochuko_mounted_folder_name'))
    }
    const handleFolderUnmounted = () => {
      setMountedFolderName(null)
    }
    window.addEventListener('storage', handleStorageChange)
    window.addEventListener('ochuko_workstation_access_changed', handleStorageChange)
    window.addEventListener('ochuko_folder_mounted', handleFolderMounted)
    window.addEventListener('ochuko_folder_unmounted', handleFolderUnmounted)

    // Restore persisted folder handle from IndexedDB on page reload
    retrievePersistedDirHandle().then(async (handle) => {
      if (handle) {
        try {
          // Chromium (the only engine that can persist directory handles) always
          // exposes queryPermission — restore when access is granted or re-promptable.
          const perm = await handle.queryPermission({ mode: 'readwrite' })
          if (perm === 'granted' || perm === 'prompt') {
            ;(window as any)._ochuko_dir_handle = handle
            setMountedFolderName(handle.name)
            localStorage.setItem('ochuko_mounted_folder_name', handle.name)
          }
        } catch {
          // Handle expired or browser permission revoked
        }
      }
    })

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      window.removeEventListener('ochuko_workstation_access_changed', handleStorageChange)
      window.removeEventListener('ochuko_folder_mounted', handleFolderMounted)
      window.removeEventListener('ochuko_folder_unmounted', handleFolderUnmounted)
    }
  }, [])

  const handleMountFolder = async () => {
    try {
      if (!('showDirectoryPicker' in window)) {
        showToast('File System Access API is not supported in this browser. Please use Chrome, Edge, or Brave.', 'error')
        return
      }
      const dirHandle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
      if (dirHandle) {
        ;(window as any)._ochuko_dir_handle = dirHandle
        const folderName = dirHandle.name
        setMountedFolderName(folderName)
        localStorage.setItem('ochuko_mounted_folder_name', folderName)
        await persistDirHandle(dirHandle)
        window.dispatchEvent(
          new CustomEvent('ochuko_folder_mounted', { detail: { folderName, dirHandle } })
        )
        showToast(`Full PC directory access granted: '${folderName}'`, 'info')
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Failed to mount folder:', err)
        showToast('Could not mount folder', 'error')
      }
    }
  }

  const handleUnmountFolder = async () => {
    delete (window as any)._ochuko_dir_handle
    setMountedFolderName(null)
    localStorage.removeItem('ochuko_mounted_folder_name')
    await clearPersistedDirHandle()
    window.dispatchEvent(new Event('ochuko_folder_unmounted'))
    showToast('Local folder unmounted', 'info')
  }

  useEffect(() => {
    if (!isHeaderSettingsOpen) return
    const handler = (e: MouseEvent | TouchEvent) => {
      if (headerSettingsRef.current && !headerSettingsRef.current.contains(e.target as Node)) {
        setIsHeaderSettingsOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('touchstart', handler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('touchstart', handler)
    }
  }, [isHeaderSettingsOpen])

  // Legacy `open-artifact` events (code-block "View as Artifact") route into the
  // unified ArtifactPanel via open-file-preview — no separate sidebar anymore.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail || {}
      const name = detail.filename || 'Artifact'
      dispatchOpenFilePreview({
        name,
        type: mimeFromName(name),
        content: typeof detail.content === 'string' ? detail.content : undefined,
      })
    }
    window.addEventListener('open-artifact', handler)
    return () => window.removeEventListener('open-artifact', handler)
  }, [])



  const [searchQuery, setSearchQuery] = useState('')

  const [searchResults, setSearchResults] = useState<any[] | null>(null)

  const searchInputRef = useRef<HTMLInputElement>(null)

  // Online/Offline status monitoring

  useEffect(() => {

    const handleOnline = () => setIsOnline(true)

    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)

    window.addEventListener('offline', handleOffline)

    return () => {

      window.removeEventListener('online', handleOnline)

      window.removeEventListener('offline', handleOffline)

    }

  }, [])

  // Client-side search effect is placed after conversations state declaration (see below)
  // to avoid TypeScript TDZ error. searchQuery drives it via conversationsRef.

  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  const [webSearchStatus, setWebSearchStatus] = useState<'idle' | 'searching' | 'done'>('idle')

  const [activityLabel, setActivityLabel] = useState<string>('')

  const [, setAgentStep] = useState<number>(0)

  // agentMaxSteps is intentionally write-only: the OODA loop is uncapped and
  // per-message, so the UI never renders a global "of M" ceiling.
  const [, setAgentMaxSteps] = useState<number>(0)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const isAutoScrollEnabledRef = useRef<boolean>(true)

  // Prevents auto-scroll from triggering during history fetch / cache hydration.
  // Set to true while messages are being loaded from the DB, false once settled.
  const isLoadingHistoryRef = useRef<boolean>(false)

  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)

  const [editingMessageText, setEditingMessageText] = useState("")

  const abortControllerRef = useRef<AbortController | null>(null)

  interface AttachedFile {
    name: string
    type: string
    blobUrl: string
    fileId: string
    localObjectUrl?: string
    sizeBytes?: number
  }

  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])

  const [previewingFile, setPreviewingFile] = useState<{
    name: string
    type: string
    url?: string
    localObjectUrl?: string
    content?: string
    sizeBytes?: number
    siteSlug?: string
    projectFiles?: Record<string, string> | Array<{ name: string; content?: string; url?: string; sizeBytes?: number; type?: string }>
    siblingFiles?: Array<{ name: string; content?: string; url?: string; sizeBytes?: number; type?: string }>
  } | null>(null)

  const [loadedPreviewContent, setLoadedPreviewContent] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  // Markdown files open in rendered Preview mode; user can switch to Raw source
  const [previewView, setPreviewView] = useState<'preview' | 'raw'>('preview')

  useEffect(() => {
    const handleOpenPreview = (e: Event) => {
      const customEvent = e as CustomEvent
      setPreviewingFile(customEvent.detail)
    }
    window.addEventListener('open-file-preview', handleOpenPreview)
    return () => window.removeEventListener('open-file-preview', handleOpenPreview)
  }, [])

  // Re-poll image_gen jobs that were still pending when history was hydrated.
  // Without this, a page refresh during generation left an infinite shimmer -
  // the job completes server-side but nothing was listening for it anymore.
  const rePolledImageJobsRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    messages.forEach((m) => {
      if (!m.imagePending || !m.imageJobId || rePolledImageJobsRef.current.has(m.imageJobId)) return
      rePolledImageJobsRef.current.add(m.imageJobId)
      const staleJobId = m.imageJobId
      const stalePoll = setInterval(async () => {
        try {
          const session = await supabase.auth.getSession()
          const token = session.data.session?.access_token
          if (!token) return
          const response = await fetch(`${API_BASE}/v1/agents/job/${staleJobId}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (!response.ok) return
          const jobData = await response.json()
          if (jobData.status === 'done' && jobData.result_blob_url) {
            setMessages((prev) =>
              prev.map((mm) =>
                mm.imagePending && mm.imageJobId === staleJobId
                  ? { ...mm, imagePending: false, imageUrl: jobData.result_blob_url, imageJobId: undefined }
                  : mm
              )
            )
            clearInterval(stalePoll)
          } else if (jobData.status === 'failed') {
            setMessages((prev) =>
              prev.map((mm) =>
                mm.imagePending && mm.imageJobId === staleJobId
                  ? { ...mm, imagePending: false, imageJobId: undefined, content: mm.content + `\n\nImage generation failed: ${jobData.error_message || 'Please try again.'}` }
                  : mm
              )
            )
            clearInterval(stalePoll)
          }
        } catch {
          // transient network error - keep polling
        }
      }, 5000)
    })
  }, [messages])

  useEffect(() => {
    setPreviewView('preview')
    if (!previewingFile) {
      setLoadedPreviewContent(null)
      setPreviewLoading(false)
      return
    }
    if (previewingFile.content) {
      setLoadedPreviewContent(previewingFile.content)
      setPreviewLoading(false)
      return
    }
    const targetUrl = previewingFile.localObjectUrl || previewingFile.url
    if (!targetUrl) return

    const nameLower = previewingFile.name.toLowerCase()
    const hasRepoContext = Boolean(
      previewingFile.siteSlug ||
      (previewingFile.siblingFiles && previewingFile.siblingFiles.length > 1) ||
      previewingFile.projectFiles
    )
    const isImage = (previewingFile.type || '').startsWith('image/') || /\.(png|jpe?g|webp|gif|svg)$/i.test(nameLower)
    const isPdf = previewingFile.type === 'application/pdf' || nameLower.endsWith('.pdf')
    const isBinaryDoc = /\.(docx?|xlsx?|pptx?|zip|rar|tar|gz|7z|exe|bin)$/i.test(nameLower)

    if (!isImage && !isPdf && (!isBinaryDoc || hasRepoContext)) {
      setPreviewLoading(true)
      fetch(targetUrl)
        .then(res => res.text())
        .then(text => {
          setLoadedPreviewContent(text)
          setPreviewLoading(false)
        })
        .catch(err => {
          console.warn('Failed to load text preview:', err)
          setLoadedPreviewContent('Unable to fetch file preview.')
          setPreviewLoading(false)
        })
    }
  }, [previewingFile])

  // Collect all generated deliverables and artifacts from conversation history for repo explorer
  const allRecentFiles = useMemo(() => {
    const files: Array<{ name: string; type?: string; url?: string; content?: string; sizeBytes?: number }> = []
    const seen = new Set<string>()
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.generatedFiles) {
        for (const gf of m.generatedFiles) {
          if (!seen.has(gf.filename)) {
            seen.add(gf.filename)
            files.push({
              name: gf.filename,
              type: mimeFromName(gf.filename),
              url: gf.download_url,
              sizeBytes: gf.size_bytes,
            })
          }
        }
      }
      if (m.agentTaskData?.artifacts) {
        for (const a of (m.agentTaskData.artifacts as any[])) {
          const fn = a.filename || a.title
          if (fn && !seen.has(fn)) {
            seen.add(fn)
            files.push({
              name: fn,
              type: mimeFromName(fn),
              url: a.download_url || a.url,
              sizeBytes: a.size_bytes,
            })
          }
        }
      }
    }
    return files
  }, [messages])

  // Pre-warm the Mermaid chunk during idle time (no cold-start lag on the
  // first diagram).
  useEffect(() => {
    preWarmMermaid()
  }, [])

  const [pastedSnippets, setPastedSnippets] = useState<Array<{
    id: string
    content: string
    name: string
    sizeBytes: number
  }>>([])

  const [expandedPastedMessages, setExpandedPastedMessages] = useState<Record<string | number, boolean>>({})

  const [copiedPastedKey, setCopiedPastedKey] = useState<string | number | null>(null)
  const [copiedModalPreview, setCopiedModalPreview] = useState(false)

  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  const [uploading, setUploading] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Voice-to-text hook ─────────────────────────────────────────────────────
  const voice = useVoice((text: string) => setInput(prev => prev + text))

  // toggleVoiceRef — stable ref so keyboard handler can call toggleVoice before it is declared
  const toggleVoiceRef = useRef<(() => Promise<void>) | null>(null)

  // ── Inline rename state ─────────────────────────────────────────────────────

  const [renamingConvoId, setRenamingConvoId] = useState<string | null>(null)

  const [renameValue, setRenameValue] = useState('')

  const renameInputRef = useRef<HTMLInputElement>(null)



  // Focus the rename input when it appears

  useEffect(() => {

    if (renamingConvoId) {

      setTimeout(() => renameInputRef.current?.focus(), 30)

    }

  }, [renamingConvoId])

  // ── KaTeX — activate when any message contains '$' ──────────────────────────

  const hasLatex = useMemo(() => messages.some(m => m.content.includes('$')), [messages])

  useKaTeX(hasLatex)

  useEffect(() => {
    const el = inputRef.current
    if (el && el.tagName === 'TEXTAREA') {
      const handle = requestAnimationFrame(() => {
        el.style.height = 'auto'
        el.style.height = `${el.scrollHeight}px`
      })
      return () => cancelAnimationFrame(handle)
    }
  }, [input])

  // activeConversationId starts as null sentinel until auth resolves.
  const [activeConversationId, setActiveConversationId] = useState<string>('00000000-0000-0000-0000-000000000000')

  useEffect(() => {
    if (activeConversationId && activeConversationId !== '00000000-0000-0000-0000-000000000000') {
      (window as any).__activeConversationId = activeConversationId
    }
  }, [activeConversationId])

  const uploadFile = async (file: File) => {
    const allowedExts = [
      // Documents & PDF
      '.pdf', '.docx', '.doc', '.pptx', '.ppt', '.odp', '.odt', '.rtf', '.epub', '.tex',
      // Tabular & Spreadsheets
      '.xlsx', '.xls', '.xlsm', '.csv', '.tsv', '.ods', '.parquet',
      // Compressed Archives & Disk Images
      '.zip', '.tar', '.gz', '.tgz', '.bz2', '.tbz2', '.xz', '.txz', '.7z', '.rar', '.zst', '.lzma', '.cab', '.iso', '.dmg',
      // Images & Multimodal Vision
      '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tiff', '.tif', '.ico', '.heic', '.heif', '.avif',
      // Audio & Media (including WhatsApp voice notes & recordings)
      '.mp3', '.wav', '.m4a', '.ogg', '.opus', '.oga', '.amr', '.flac', '.aac',
      // Web & Scripting
      '.html', '.htm', '.css', '.js', '.mjs', '.ts', '.tsx', '.jsx', '.vue', '.svelte',
      // Code & Languages
      '.py', '.ipynb', '.java', '.c', '.cpp', '.cc', '.h', '.hpp', '.cs', '.rs', '.go', '.rb', '.php',
      '.kt', '.swift', '.scala', '.r', '.lua', '.dart', '.zig', '.sol', '.wasm',
      // Shell & System
      '.sh', '.bash', '.bat', '.cmd', '.ps1', '.sql',
      // Config & Markup & ML Models
      '.json', '.md', '.yaml', '.yml', '.xml', '.toml', '.ini', '.cfg', '.properties', '.gradle', '.env', '.dockerfile', '.graphql', '.gql', '.proto', '.pb', '.diff', '.patch', '.log', '.txt'
    ]
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
    if (!allowedExts.includes(ext)) {
      // alert() is suppressed/silent in iOS standalone PWA mode — use the toast.
      showToast(`Unsupported file type. Allowed extensions: ${allowedExts.join(', ')}`, 'error')
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
        // safeRandomUUID: crypto.randomUUID is undefined on older iOS/non-HTTPS
        convoId = safeRandomUUID()
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
          mime_type: file.type || mimeFromName(file.name),
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
        xhr.setRequestHeader('Content-Type', file.type || mimeFromName(file.name))
        xhr.upload.onprogress = (evt) => {
          if (evt.lengthComputable) {
            const pct = Math.round((evt.loaded / evt.total) * 100)
            setUploadProgress(pct)
          }
        }
        xhr.onload = () => {
          if (xhr.status === 201 || xhr.status === 200) {
            // Trigger background sync to user's Google Drive account
            fetch(`${API_BASE}/v1/files/sync-google`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`
              },
              body: JSON.stringify({
                file_id: file_id,
                filename: file.name,
                conversation_id: convoId
              })
            }).catch(syncErr => console.warn('Background Google Drive sync request failed:', syncErr))
            resolve()
          } else {
            reject(new Error(`Storage upload returned status ${xhr.status}`))
          }
        }
        xhr.onerror = () => reject(new Error('Network error during upload to storage'))
        xhr.send(file)
      })

      const inferredType = file.type || mimeFromName(file.name) || 'application/octet-stream'

      const localUrl = URL.createObjectURL(file)

      setAttachedFiles(prev => [
        ...prev,
        {
          name: file.name,
          type: inferredType,
          blobUrl: blob_url,
          fileId: file_id,
          localObjectUrl: localUrl,
          sizeBytes: file.size
        }
      ])
    } catch (err: any) {
      console.error('File upload error:', err)
      // alert() is suppressed/silent in iOS standalone PWA mode — use the toast.
      showToast(`File upload failed: ${err.message || err}`, 'error')
    } finally {
      setUploading(false)
      setUploadProgress(null)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }

  const handlePaste = async (e: React.ClipboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    // 1. Check for files (images, PDFs, documents)
    const files = e.clipboardData.files
    const items = e.clipboardData.items
    const fileList: File[] = []

    if (files && files.length > 0) {
      for (let i = 0; i < files.length; i++) {
        fileList.push(files[i])
      }
    } else if (items && items.length > 0) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
          const f = items[i].getAsFile()
          if (f) fileList.push(f)
        }
      }
    }

    if (fileList.length > 0) {
      e.preventDefault()
      for (const f of fileList) {
        await uploadFile(f)
      }
      return
    }

    // 2. Check for text
    const text = e.clipboardData.getData('text')
    if (text.length > 400 || text.includes('\n')) {
      e.preventDefault()
      const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
      let title = 'Pasted Text'
      if (lines.length > 0) {
        const firstLine = lines[0]
        title = firstLine.length > 25 ? `${firstLine.substring(0, 25)}...` : firstLine
      }
      setPastedSnippets(prev => [
        ...prev,
        {
          id: safeRandomUUID(),
          content: text,
          name: title,
          sizeBytes: new Blob([text]).size,
        }
      ])
    }
  }

  const [conversations, setConversations] = useState<any[]>([])
  // Conversations are loaded from the user-scoped cache after auth resolves

  // ── Client-side conversation search (offline-capable, instant) ──────────────
  // Filters the already-loaded `conversations` array in memory — no network call,
  // works offline, results appear in ~120ms as you type.
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    const q = searchQuery.trim().toLowerCase()
    const timer = setTimeout(() => {
      const matched = conversations.filter(c => {
        const title = (c.title || '').toLowerCase()
        const mode  = (c.mode  || '').toLowerCase()
        return title.includes(q) || mode.includes(q) || c.id?.toLowerCase().startsWith(q)
      })
      setSearchResults(matched.length > 0 ? matched : [])
    }, 120)
    return () => clearTimeout(timer)
  }, [searchQuery, conversations])

  const [convoToDelete, setConvoToDelete] = useState<string | null>(null)

  // ── Toast notifications ────────────────────────────────────────────────────

  const [toasts, setToasts] = useState<{ id: string; message: string; type: 'info' | 'error' }[]>([])

  const showToast = useCallback((message: string, type: 'info' | 'error' = 'info') => {

    const id = Date.now().toString()

    setToasts(prev => [...prev, { id, message, type }])

    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000)

  }, [])

  // Surface voice hook errors as toasts (placed after showToast declaration)
  useEffect(() => {
    if (voice.error === 'permission_denied') {
      showToast('Microphone access required for voice input', 'error')
    } else if (voice.error === 'transcription_failed') {
      showToast('Transcription failed — please try again', 'error')
    } else if (voice.error === 'browser_incompatible') {
      showToast('Voice input is not supported in this browser', 'info')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice.error])

  const fetchConversations = async () => {

    try {

      const token = await getEffectiveToken()

      if (!token) return

      const res = await fetch(`${API_BASE}/v1/conversations`, {

        headers: {

          Authorization: `Bearer ${token}`,

        },

      })

      if (res.ok) {

        const data = await res.json()

        setConversations(data)

        const uid = userIdRef.current
        if (uid) {
          localStorage.setItem(userCacheKey(uid, 'local_conversations'), JSON.stringify(data))
        }

      }

    } catch (e) {

      console.error("Failed to fetch conversations:", e)

    }

  }

  const handleNewSession = () => {
    // Abort any active stream before starting new session
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    // Reset all streaming and search states
    setIsStreaming(false)
    setWebSearchStatus('idle')
    setActivityLabel('')
    
    // Clear messages and reset conversation ID
    setMessages([])
    setExpandedCompactionIndices(new Set())
    setActiveConversationId('00000000-0000-0000-0000-000000000000')
    const uid = userIdRef.current
    if (uid) localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), '00000000-0000-0000-0000-000000000000')
    
    // Reset mode to discuss
    setMode('discuss')
    
    // Close sidebar on mobile/tablet, preserve pinned state on desktop
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false)
      setIsSidebarHovered(false)
    }
    
    // Clear any preview state
    setPreviewingFile(null)
    
    // Focus input after state updates
    setTimeout(() => inputRef.current?.focus(), 100)
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

    // Don't warmup when selecting existing conversations - container should already be warm
    // Warmup only happens for truly new conversations (handleNewSession with shouldWarmup=true)

    setIsFetchingHistory(true)

    setExpandedCompactionIndices(new Set())

    // Auto-close sidebar on mobile when a conversation is chosen
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false)
      setIsSidebarHovered(false)
    }

    // --- SWR Cache Read ---
    // Load cached messages first to make switching instant and avoid skeleton/blank screen flash
    const uid = userIdRef.current
    const cacheKey = uid ? userCacheKey(uid, `convo_cache_${id}`) : `convo_cache_${id}`
    const cachedData = localStorage.getItem(cacheKey)
    let hasLoadedFromCache = false
    if (cachedData) {
      try {
        const parsed = JSON.parse(cachedData)
        if (parsed && Array.isArray(parsed.messages)) {
          isLoadingHistoryRef.current = true  // suppress auto-scroll during cache hydration
          setMessages(parsed.messages)
          setMode(convoMode)
          setActiveConversationId(id)
          hasLoadedFromCache = true
          if (uid) localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), id)
        }
      } catch (e) {
        console.warn("Failed to load cached conversation:", e)
      }
    }

    if (!hasLoadedFromCache) {
      setMessages([])
    }

    try {

      const session = await supabase.auth.getSession()

      const token = session.data.session?.access_token

      if (!token) return

      // Fetch messages and generated files in parallel

      const [msgRes, filesRes] = await Promise.all([

        fetch(`${API_BASE}/v1/conversations/${id}/messages`, {

          headers: { Authorization: `Bearer ${token}` },

        }),

        fetch(`${API_BASE}/v1/conversations/${id}/files`, {

          headers: { Authorization: `Bearer ${token}` },

        }).catch(() => null),  // non-fatal if table doesn't exist yet

      ])

      // ── Explicit rejection handling (Fix 2) ──
      // 403: the conversation belongs to a different account (commonly a second
      // Google account used in this browser). 404: it was deleted. Surface a
      // visible, non-destructive banner instead of failing silently — cached
      // messages remain on screen and nothing is wiped.
      if (msgRes.status === 403 || msgRes.status === 404) {
        const reason = msgRes.status === 403
          ? 'This conversation belongs to a different account signed in on this device.'
          : 'This conversation no longer exists.'
        setConvoAccessError({ convoId: id, reason })
        showToast(
          msgRes.status === 403 ? "Can't open this conversation — different account." : 'Conversation not found.',
          'error'
        )
        return
      }

      // Successful (or non-403/404) load — clear any stale banner
      setConvoAccessError(null)

      if (msgRes.ok) {

        const data = await msgRes.json()

        const mapped: Message[] = []
        const systemUrls: string[] = []

        for (let idx = 0; idx < data.length; idx++) {

          const m = data[idx]

          if (m.role === 'system') {

            // Match R2 / Azure Blob URLs which may have query strings
            const match = m.content.match(/File URL:\s*(https?:\/\/\S+)/i)

            if (match) {

              // Strip trailing punctuation (not query strings)
              const url = match[1].replace(/[),.'"]+$/, '')
              systemUrls.push(url)

            }

            continue

          }

          const msgObj: Message = {

            role: m.role,

            content: m.is_summary ? '' : m.content,

            isCompactionMarker: m.is_summary || undefined,

            compactionSummary: m.is_summary ? m.content.replace(/^Summary of earlier conversation:\n/i, '') : undefined,

            isArchived: m.is_archived_msg || undefined,

            routing_mode: m.routing_mode,

            routing_reason: m.routing_reason,

            sources: Array.isArray(m.content_parts?.sources) ? m.content_parts.sources : undefined,

            imageUrl: m.content_parts?.image_jobs?.[0]?.image_url || undefined,

            imagePrompt: m.content_parts?.image_jobs?.[0]?.prompt || undefined,

            imageJobId: m.content_parts?.image_jobs?.[0]?.job_id || undefined,

            imagePending: m.content_parts?.image_jobs?.[0]?.status === 'pending' || undefined,

            thinkingContent: m.content_parts?.thinking_content || undefined,

            generatedFiles: Array.isArray(m.content_parts?.generated_files) ? m.content_parts.generated_files : undefined,

            widgetData: Array.isArray(m.content_parts?.widgets) ? m.content_parts.widgets.map((w: any) => ({

              code: w.code,

              title: w.title,

              widgetType: w.widget_type || w.widgetType || 'diagram',

              widgetLoading: false,

            })) : undefined,
            displayCards: Array.isArray(m.content_parts?.display_cards) ? m.content_parts.display_cards : undefined,

          }

          if (m.role === 'user') {
            if (m.content_parts?.attachments && Array.isArray(m.content_parts.attachments) && m.content_parts.attachments.length > 0) {
              msgObj.fileAttachments = m.content_parts.attachments.map((att: any) => {
                const isPdf = att.mime_type === 'application/pdf' || att.filename?.toLowerCase().endsWith('.pdf')
                const isImg = att.mime_type?.startsWith('image/') || /\.(png|jpe?g|webp|gif|svg|bmp)$/i.test(att.filename || '')
                const jobType = isPdf ? 'ocr' : (isImg ? 'vision' : 'code')
                return {
                  name: att.filename,
                  jobType,
                  url: att.url,
                }
              })
            } else {
              const isOcr = m.content.startsWith('[Document Analysis:')
              const isVision = m.content.startsWith('[Image Analysis:')
              const isMulti = m.content.startsWith('[Analysis for:')

              if (isOcr || isVision) {
                const jobType = isOcr ? 'ocr' : 'vision'
                const nameMatch = m.content.match(/^\[(?:Document|Image) Analysis:\s*([^\]]+)\]/)
                const name = nameMatch ? nameMatch[1] : (isOcr ? 'document.pdf' : 'image.png')
                msgObj.fileAttachment = { name, jobType }
              } else if (isMulti) {
                const namesMatch = m.content.match(/^\[Analysis for:\s*([^\]]+)\]/)
                if (namesMatch) {
                  const names = namesMatch[1].split(',').map((n: string) => n.trim())
                  msgObj.fileAttachments = names.map((name: string) => {
                    const isPdf = name.toLowerCase().endsWith('.pdf')
                    return {
                      name,
                      jobType: isPdf ? 'ocr' : 'vision'
                    }
                  })
                }
              }
            }
          }

          mapped.push(msgObj)

        }

        // Map system URLs to user message attachments by matching filenames
        for (const url of systemUrls) {
          try {
            // Extract filename from URL (stripping the 32-hex UUID prefix if present)
            const rawFilename = url.split('/').pop() || ''
            const cleanFilename = decodeURIComponent(rawFilename).replace(/^[a-f0-9]{32}_/i, '').toLowerCase().trim()

            // Find the user message attachment matching this filename
            for (let i = mapped.length - 1; i >= 0; i--) {
              const msg = mapped[i]
              if (msg.role === 'user') {
                if (msg.fileAttachment && msg.fileAttachment.name.toLowerCase().trim() === cleanFilename) {
                  msg.fileAttachment.url = url
                  break
                }
                if (msg.fileAttachments) {
                  const att = msg.fileAttachments.find(a => a.name.toLowerCase().trim() === cleanFilename)
                  if (att) {
                    att.url = url
                    break
                  }
                }
              }
            }
          } catch (err) {
            console.error('Error matching system file URL:', err)
          }
        }

        // Attach generated files from the /files endpoint ONLY as a fallback.
        // If any assistant message already has generatedFiles (from content_parts.generated_files),
        // those are already correctly placed per-message — skip the /files endpoint to prevent duplication.
        const anyMsgHasFiles = mapped.some(
          (m: any) => m.role === 'assistant' && m.generatedFiles && m.generatedFiles.length > 0
        )

        if (!anyMsgHasFiles && filesRes?.ok) {
          const files: any[] = await filesRes.json()

          if (files.length > 0) {
            // Find the last assistant message to attach files to (fallback path)
            const lastAssistIdx = mapped.map((m: any) => m.role).lastIndexOf('assistant')

            if (lastAssistIdx >= 0) {
              mapped[lastAssistIdx] = {
                ...mapped[lastAssistIdx],
                generatedFiles: files.map((f: any) => ({
                  filename: f.filename,
                  download_url: f.r2_url,
                  size_bytes: f.size_bytes || 0,
                })),
              }
            }
          }
        }

        // De-duplicate generatedFiles within each message (guard against double SSE events on same turn)
        for (const m of mapped) {
          if (m.generatedFiles && m.generatedFiles.length > 1) {
            const seen = new Set<string>()
            m.generatedFiles = m.generatedFiles.filter((f: any) => {
              const key = f.filename + '_' + f.size_bytes
              if (seen.has(key)) return false
              seen.add(key)
              return true
            })
          }
        }

        // Reconcile database messages with local cache to avoid overwriting complete streamed messages
        let localMessages: Message[] = []
        if (cachedData) {
          try {
            const parsed = JSON.parse(cachedData)
            if (parsed && Array.isArray(parsed.messages)) {
              localMessages = parsed.messages
            }
          } catch (_) {}
        }

        const reconciled = mapped.map((serverMsg, idx) => {
          const localMsg = localMessages[idx]
          if (localMsg && localMsg.role === serverMsg.role) {
            const content = (localMsg.content?.length > serverMsg.content?.length)
              ? localMsg.content
              : serverMsg.content

            return {
              ...localMsg,
              ...serverMsg,
              content,
              imageUrl: localMsg.imageUrl || serverMsg.imageUrl,
              imagePrompt: localMsg.imagePrompt || serverMsg.imagePrompt,
              generatedFiles: ((localMsg.generatedFiles?.length ?? 0) > (serverMsg.generatedFiles?.length ?? 0))
                ? localMsg.generatedFiles
                : serverMsg.generatedFiles,
              sources: localMsg.sources || serverMsg.sources,
            }
          }
          return serverMsg
        })

        isLoadingHistoryRef.current = true  // suppress auto-scroll during DB fetch
        setMessages(reconciled)

        setActiveConversationId(id)

        const uid2 = userIdRef.current
        if (uid2) localStorage.setItem(userCacheKey(uid2, 'active_conversation_id'), id)

        setMode(convoMode)

        // --- SWR Cache Write ---
        saveConvoCache(userIdRef.current, id, reconciled, convoMode)

        setIsSidebarOpen(false)

        setTimeout(() => inputRef.current?.focus(), 0)

      }

    } catch (e) {

      console.error("Failed to load message history:", e)

    } finally {

      setIsFetchingHistory(false)
      // Re-enable auto-scroll a tick after messages settle.
      // This prevents the history load from forcing the view to the bottom.
      setTimeout(() => { isLoadingHistoryRef.current = false }, 100)

    }

  }

  const handleModeChange = async (newMode: 'think' | 'solve' | 'discuss' | 'agent') => {

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

    setTimeout(() => inputRef.current?.focus(), 0)

  }

  useEffect(() => {

    // Zero-cost cold-start warm-up: with the backend scaled to 0, the first
    // request after inactivity refuses connections until the container starts.
    // Ping /health with backoff on mount so the container is warm before the
    // user sends a message (the ping is the request that wakes it anyway).
    wakeBackend().then((ok) => {
      if (!ok) console.warn('[warm-up] Backend still unreachable after wake cycle')
    })

    supabase.auth.getUser().then(({ data: { user } }) => {

      if (user) {

        const uid = user.id
        userIdRef.current = uid
        setUserEmail(user.email || 'User')

        const metadata = user.user_metadata || {}
        const name = metadata.preferred_name || metadata.full_name || metadata.name || user.email?.split('@')[0] || 'User'
        setPreferredName(name)

        // ── Capability-page handoff: honor /?prompt=&mode= without overrides ──
        // Runs AFTER the URL-param effect, so without this early return the
        // hydration below would reset mode to 'discuss' (or to the previous
        // conversation's mode) and load the cached conversation's messages,
        // burying the capability prompt inside a stale chat.
        if (capabilityHandoffRef.current) {
          sessionStorage.setItem('session_started', 'true')
          localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), '00000000-0000-0000-0000-000000000000')
          setActiveConversationId('00000000-0000-0000-0000-000000000000')
          setMessages([])
          // Still hydrate the sidebar list from cache for instant load
          try {
            const cachedConvos = localStorage.getItem(userCacheKey(uid, 'local_conversations'))
            if (cachedConvos) setConversations(JSON.parse(cachedConvos))
          } catch {}
          fetchConversations()
          return
        }

        // Clear active conversation cache if this is a brand new login/tab session
        const isFreshSession = !sessionStorage.getItem('session_started')
        const pendingConvoId = sessionStorage.getItem('pending_active_convo_id') || localStorage.getItem('pending_active_convo_id')

        if (isFreshSession && !pendingConvoId) {
          sessionStorage.setItem('session_started', 'true')
          localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), '00000000-0000-0000-0000-000000000000')
        }

        if (pendingConvoId) {
          sessionStorage.setItem('session_started', 'true')
          sessionStorage.removeItem('pending_active_convo_id')
          localStorage.removeItem('pending_active_convo_id')
          localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), pendingConvoId)
        }

        // ── Hydrate from user-scoped cache (safe now that we know who this is) ──
        try {
          const cachedId = localStorage.getItem(userCacheKey(uid, 'active_conversation_id'))
          if (cachedId && cachedId !== '00000000-0000-0000-0000-000000000000') {
            setActiveConversationId(cachedId)
            const raw = localStorage.getItem(userCacheKey(uid, `convo_cache_${cachedId}`))
            let hydratedConvoMode: 'think' | 'solve' | 'discuss' = 'discuss'
            if (raw) {
              const parsed = JSON.parse(raw)
              isLoadingHistoryRef.current = true   // suppress auto-scroll during startup hydration
              if (Array.isArray(parsed.messages)) setMessages(parsed.messages)
              if (parsed.mode) {
                setMode(parsed.mode)
                hydratedConvoMode = parsed.mode
              }
            }
            // Trigger background sync to verify history matches database
            handleSelectConversation(cachedId, hydratedConvoMode)
          } else {
            // Start fresh session by default on new login.
            // Keep the URL-provided mode if the capabilities page handed one off.
            setActiveConversationId('00000000-0000-0000-0000-000000000000')
            setMessages([])
            if (!urlModeRef.current) setMode('discuss')
          }
          // Also hydrate sidebar conversations from cache for instant load
          try {
            const cachedConvos = localStorage.getItem(userCacheKey(uid, 'local_conversations'))
            if (cachedConvos) setConversations(JSON.parse(cachedConvos))
          } catch {}
        } catch {}

        fetchConversations()
      }
    }).catch((err) => {
      console.warn('Supabase auth connection offline or closed:', err)
    })

  }, [])

  // ── Session-identity guard (Fix 1) ────────────────────────────────────────
  // supabase-js syncs the session across tabs via shared localStorage, so a
  // sign-in in another tab (or an OAuth #access_token fragment in this one) can
  // silently replace the active user mid-session. React explicitly instead of
  // letting ownership-checked API calls fail with opaque 403s.
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT') return
      // Only react once the boot-time identity is known AND the incoming
      // session actually belongs to a different user. INITIAL_SESSION and
      // routine TOKEN_REFRESHED events never change the user, so they no-op.
      if (!session?.user) return
      if (!userIdRef.current) return
      if (session.user.id === userIdRef.current) return
      console.warn('[Auth] Session identity changed:', userIdRef.current, '→', session.user.id)
      setSessionSwitchPrompt({
        newUserId: session.user.id,
        newEmail: session.user.email ?? null,
      })
    })
    return () => subscription.unsubscribe()
  }, [])

  // Auto-focus input on mount

  useEffect(() => {

    inputRef.current?.focus()

  }, [])

  // ── Global keyboard shortcuts ────────────────────────────────────────────

  useEffect(() => {

    const handler = (e: KeyboardEvent) => {

      const mod = e.ctrlKey || e.metaKey

      // Standard page reloads (Ctrl+R / Ctrl+Shift+R) are allowed.

      // Ctrl/Cmd + Shift + N → new session

      if (mod && e.shiftKey && e.key === 'N') {

        e.preventDefault()

        handleNewSession()

        return

      }

      // Ctrl/Cmd + Shift + V → toggle voice dictation

      if (mod && e.shiftKey && e.key === 'V') {

        e.preventDefault()

        toggleVoiceRef.current?.()

        return

      }

      // Ctrl/Cmd + 1/2/3 → switch mode

      if (mod && !e.shiftKey) {

        if (e.key === '1') { e.preventDefault(); handleModeChange('think'); return }

        if (e.key === '2') { e.preventDefault(); handleModeChange('solve'); return }

        if (e.key === '3') { e.preventDefault(); handleModeChange('discuss'); return }

        if (e.key === '4') { e.preventDefault(); handleModeChange('agent'); return }

      }

      // Ctrl/Cmd + K → focus search

      if (mod && !e.shiftKey && e.key.toLowerCase() === 'k') {

        e.preventDefault()

        setIsSidebarOpen(true)

        searchInputRef.current?.focus()

        return

      }

      if (e.key === 'Escape') {

        setPreviewingFile(null)

        setIsSidebarOpen(false)

        setIsSidebarHovered(false)

        setIsModeSheetOpen(false)

      }

    }

    window.addEventListener('keydown', handler)

    return () => window.removeEventListener('keydown', handler)

  }, [handleModeChange])

  // Check scroll position to determine if we should stay locked to the bottom

  const handleScroll = () => {

    const container = scrollContainerRef.current

    if (container) {

      const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150

      isAutoScrollEnabledRef.current = isAtBottom

    }

  }


  // Auto-scroll on new content only if user is at the bottom AND we're not
  // in the middle of a history load (which would incorrectly snap to bottom).

  useEffect(() => {

    const container = scrollContainerRef.current

    if (container && isAutoScrollEnabledRef.current && !isLoadingHistoryRef.current) {

      const handle = requestAnimationFrame(() => {

        container.scrollTop = container.scrollHeight

      })

      return () => cancelAnimationFrame(handle)

    }

  }, [messages])

  const handleSignOut = async () => {

    try {

      await supabase.auth.signOut()

    } catch (err) {

      console.error('Sign out failed:', err)

    } finally {

      // Clear all local storage so no stale session or cache lingers
      localStorage.clear()
      sessionStorage.clear()

      window.location.assign('/login')

    }

  }

  // ── Conversation rename ─────────────────────────────────────────────────────

  const handleRenameCommit = useCallback(async () => {

    if (!renamingConvoId) return

    const trimmed = renameValue.trim()

    setRenamingConvoId(null)

    if (!trimmed) return

    // Optimistic update in local state

    setConversations(prev =>

      prev.map(c => c.id === renamingConvoId ? { ...c, title: trimmed } : c)

    )

    // Persist to localStorage for instant next-load

    try {

      const cacheKey = `convo_title_${renamingConvoId}`

      localStorage.setItem(cacheKey, trimmed)

    } catch {}

    // Persist to backend

    try {

      const session = await supabase.auth.getSession()

      const token = session.data.session?.access_token

      await fetch(`${API_BASE}/v1/conversations/${renamingConvoId}`, {

        method: 'PATCH',

        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },

        body: JSON.stringify({ title: trimmed }),

      })

    } catch (e) {

      console.error('Rename failed:', e)

    }

  }, [renamingConvoId, renameValue])

  const handleRenameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {

    if (e.key === 'Enter') { e.preventDefault(); handleRenameCommit() }

    if (e.key === 'Escape') { setRenamingConvoId(null) }

  }

  const handleCopy = async (text: string, index: number) => {

    try {

      await navigator.clipboard.writeText(text)

      setCopiedIndex(index)

      setTimeout(() => setCopiedIndex(null), 2000)

    } catch (_) {}

  }

  // ── Shared agent-task SSE event updater ────────────────────────────────────
  // Consumed by BOTH the main chat stream and the approve-resume stream, so
  // plan/step/artifact/approval state updates live in exactly one place.
  const applyAgentTaskEvent = (data: any) => {
    const findTargetIndex = (arr: Message[]): number => {
      if (data.task_id) {
        const idx = arr.findIndex(
          (m) => m.agentTaskData?.id === data.task_id || m.agentTaskData?.task_id === data.task_id
        )
        if (idx !== -1) return idx
      }
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i].agentTaskData) return i
      }
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i].role === 'assistant') return i
      }
      return arr.length - 1
    }

    if (data.type === 'agent_plan') {
      const planData: PlanStepItem[] = data.plan || []
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          const existingData = targetMsg.agentTaskData
          const mergedPlan = planData.map((step) => {
            const existingStep = existingData?.plan?.find((s) => s.index === step.index)
            return existingStep ? { ...step, ...existingStep } : step
          })
          targetMsg.agentTaskData = {
            ...existingData,
            id: data.task_id || existingData?.id,
            task_id: data.task_id || existingData?.task_id,
            state: data.state || 'executing',
            plan: mergedPlan.length > 0 ? mergedPlan : (existingData?.plan || planData),
            current_step: existingData?.current_step || 1,
          }
          updated[targetIdx] = targetMsg
        }
        return updated
      })
    } else if (data.type === 'agent_plan_reoriented') {
      // Phase 8: dynamic plan re-orientation mid-execution. Render rule:
      // keep completed/failed/skipped steps in place with their original
      // index labels and state; replace everything else with the re-oriented plan.
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          const existingData = targetMsg.agentTaskData
          if (existingData) {
            const planData: PlanStepItem[] = data.plan || []
            const mergedPlan = planData.map((step) => {
              const existing = existingData.plan?.find((s) => s.index === step.index)
              if (existing && (existing.status === 'completed' || existing.status === 'failed' || existing.status === 'skipped')) {
                return existing
              }
              return step
            })
            targetMsg.agentTaskData = {
              ...existingData,
              plan: mergedPlan,
              reoriented: true,
              replan_count: data.replan_count ?? 1,
              // Phase 8.1: forward divergence trigger + reason. Both are
              // undefined-safe so events predating this phase still render.
              replan_trigger: data.trigger || 'failure',
              replan_reason: typeof data.reason === 'string' ? data.reason : undefined,
            }
            updated[targetIdx] = targetMsg
          }
        }
        return updated
      })
    } else if (data.type === 'agent_step_start') {
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          if (targetMsg.agentTaskData) {
            const plan = [...(targetMsg.agentTaskData.plan || [])]
            const stepIdx = data.step_index
            const step = plan.find((s) => s.index === stepIdx)
            if (step) {
              step.status = 'running'
            }
            targetMsg.agentTaskData = {
              ...targetMsg.agentTaskData,
              current_step: stepIdx,
              plan,
            }
            updated[targetIdx] = targetMsg
          }
        }
        return updated
      })
    } else if (data.type === 'agent_step_adapted') {
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          if (targetMsg.agentTaskData) {
            const plan = [...(targetMsg.agentTaskData.plan || [])]
            const stepIdx = data.step_index
            const step = plan.find((s) => s.index === stepIdx)
            if (step) {
              step.tool_name = data.tool_name
              step.description = data.description || step.description
              step.status = 'running'
              step.adapted_reasoning = data.reasoning
              step.previous_tool = data.previous_tool
            }
            targetMsg.agentTaskData = {
              ...targetMsg.agentTaskData,
              current_step: stepIdx,
              plan,
            }
            updated[targetIdx] = targetMsg
          }
        }
        return updated
      })
    } else if (data.type === 'agent_step_ooda') {
      // Phase 4: per-step mini-OODA orient stream from the task manager.
      if (data.status === 'cap_extended') {
        setMessages((prev) => {
          const updated = [...prev]
          const targetIdx = findTargetIndex(updated)
          if (targetIdx >= 0) {
            const targetMsg = { ...updated[targetIdx] }
            if (targetMsg.agentTaskData) {
              const plan = [...(targetMsg.agentTaskData.plan || [])]
              const step = plan.find((s) => s.index === data.step_index)
              if (step) {
                step.ooda_extensions = (step.ooda_extensions || 0) + 1
              }
              targetMsg.agentTaskData = { ...targetMsg.agentTaskData, plan }
              updated[targetIdx] = targetMsg
            }
          }
          return updated
        })
      } else {
        setMessages((prev) => {
          const updated = [...prev]
          const targetIdx = findTargetIndex(updated)
          if (targetIdx >= 0) {
            const targetMsg = { ...updated[targetIdx] }
            if (targetMsg.agentTaskData) {
              const plan = [...(targetMsg.agentTaskData.plan || [])]
              const step = plan.find((s) => s.index === data.step_index)
              if (step) {
                step.ooda_attempts = data.attempt
                if (data.reasoning) step.ooda_reasoning = data.reasoning
                if (typeof data.pivot === 'boolean') step.ooda_pivot = data.pivot
                step.ooda_stall_breaker = !!data.stall_breaker
              }
              targetMsg.agentTaskData = { ...targetMsg.agentTaskData, plan }
              updated[targetIdx] = targetMsg
            }
          }
          return updated
        })
      }
    } else if (data.type === 'agent_step_complete') {
      // Auto-open newly produced step artifact in the ArtifactPanel
      if (data.artifacts && data.artifacts.length > 0) {
        const arts = data.artifacts.map((a: any) => ({
          filename: a.filename || a.title || 'artifact',
          download_url: a.download_url || a.url,
          size_bytes: a.size_bytes || 0,
        }))
        const entry = pickEntryFile(arts)
        if (entry?.download_url) {
          dispatchOpenFilePreview({
            name: entry.filename,
            type: mimeFromName(entry.filename),
            url: entry.download_url,
            sizeBytes: entry.size_bytes,
            siblingFiles: arts.map((a: any) => ({
              name: a.filename,
              type: mimeFromName(a.filename),
              url: a.download_url,
              sizeBytes: a.size_bytes,
            })),
          })
        }
      }
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          if (targetMsg.agentTaskData) {
            const plan = [...(targetMsg.agentTaskData.plan || [])]
            const stepIdx = data.step_index
            const step = plan.find((s) => s.index === stepIdx)
            if (step) {
              step.status = data.status === 'failed' ? 'failed' : 'completed'
              step.result_summary = data.result_summary || step.result_summary || null
              step.duration_ms = data.duration_ms || step.duration_ms
              step.token_spend = data.token_spend || step.token_spend
              // Phase 4: persist final mini-OODA record onto the step card
              if (data.ooda && typeof data.ooda === 'object') {
                step.ooda_attempts = data.ooda.attempts ?? step.ooda_attempts
                step.ooda_extensions = data.ooda.extensions ?? step.ooda_extensions
                step.ooda_stall_breaker = !!data.ooda.stall_breaker
              }
              if (data.artifacts) {
                step.artifacts = data.artifacts
              }
            }
            const newArtifacts = data.artifacts || []
            const currentArtifacts = targetMsg.agentTaskData.artifacts || []
            targetMsg.agentTaskData = {
              ...targetMsg.agentTaskData,
              plan,
              artifacts: [...currentArtifacts, ...newArtifacts],
              total_token_spend: (targetMsg.agentTaskData.total_token_spend || 0) + (data.token_spend || 0),
            }
            updated[targetIdx] = targetMsg
          }
        }
        return updated
      })
    } else if (data.type === 'agent_approval_required') {
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          targetMsg.agentApprovalRequired = {
            step: data.step,
            taskId: data.task_id,
            reason: data.reason,
          }
          updated[targetIdx] = targetMsg
        }
        return updated
      })
    } else if (data.type === 'agent_ask_user_input' || data.type === 'ask_user_input') {
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          targetMsg.agentUserInputRequired = {
            taskId: data.task_id || activeConversationId || 'chat',
            stepIndex: data.step_index !== undefined ? data.step_index : 0,
            question: data.question || 'Input required',
            options: Array.isArray(data.options) ? data.options : [],
            selectType: data.select_type || 'single_select',
          }
          updated[targetIdx] = targetMsg
        }
        return updated
      })
    } else if (data.type === 'agent_task_complete') {
      // Auto-open the final deliverable (entry file first) in the ArtifactPanel
      if (data.artifacts && data.artifacts.length > 0) {
        const arts = data.artifacts.map((a: any) => ({
          filename: a.filename || a.title || 'artifact',
          download_url: a.download_url || a.url,
          size_bytes: a.size_bytes || 0,
        }))
        const entry = pickEntryFile(arts)
        if (entry?.download_url) {
          dispatchOpenFilePreview({
            name: entry.filename,
            type: mimeFromName(entry.filename),
            url: entry.download_url,
            sizeBytes: entry.size_bytes,
            siblingFiles: arts.map((a: any) => ({
              name: a.filename,
              type: mimeFromName(a.filename),
              url: a.download_url,
              sizeBytes: a.size_bytes,
            })),
          })
        }
      }
      setMessages((prev) => {
        const updated = [...prev]
        const targetIdx = findTargetIndex(updated)
        if (targetIdx >= 0) {
          const targetMsg = { ...updated[targetIdx] }
          if (targetMsg.agentTaskData) {
            const plan: PlanStepItem[] = (targetMsg.agentTaskData.plan || []).map((s) => ({
              ...s,
              status: s.status === 'failed' ? ('failed' as const) : ('completed' as const),
            }))
            targetMsg.agentTaskData = {
              ...targetMsg.agentTaskData,
              plan,
              state: 'completed',
              current_step: plan.length,
              total_token_spend: data.total_token_spend || targetMsg.agentTaskData.total_token_spend,
              artifacts: data.artifacts || targetMsg.agentTaskData.artifacts,
              elapsed_seconds: data.duration_seconds || targetMsg.agentTaskData.elapsed_seconds,
            }
            targetMsg.agentApprovalRequired = undefined
            targetMsg.agentUserInputRequired = undefined
            updated[targetIdx] = targetMsg
          }
        }
        return updated
      })
    } else if (data.type === 'agent_time_warning') {
      showToast(data.message || 'Approaching task time limit...', 'info')
    }
  }

  // ── Approve/resume stream ──────────────────────────────────────────────────
  // The /approve endpoint returns an SSE stream that resumes execution.
  // Reading it here keeps steps, approvals, artifacts and the final synthesis
  // flowing into the SAME message bubble (this was the old approve-stall bug).
  const streamApproval = async (
    taskId: string,
    stepIndex: number | undefined,
    action: 'approve' | 'skip' | 'cancel' | 'respond',
    userResponse?: string
  ) => {
    try {
      const token = (await supabase.auth.getSession()).data.session?.access_token
      if (!token) return
      const res = await fetch(`${API_BASE}/v1/agent-tasks/${taskId}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ action, step_index: stepIndex, user_response: userResponse }),
      })

      const contentType = res.headers.get('content-type') || ''
      if (!res.ok || !contentType.includes('text/event-stream')) {
        // Cancel (JSON) or an error — surface a plain toast, no stream.
        let detail = ''
        try {
          const j = await res.json()
          detail = j?.detail || ''
        } catch { /* non-JSON */ }
        if (action === 'cancel') showToast('Task cancelled.', 'info')
        else if (detail) showToast(detail, 'error')
        return
      }

      setIsStreaming(true)
      const reader = res.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()
          if (!raw || raw === '[DONE]') continue
          try {
            const data = JSON.parse(raw)
            if (data.type === 'content_block_delta') {
              const chunk = data?.delta?.text || ''
              if (chunk) {
                setMessages((prev) => {
                  const updated = [...prev]
                  const last = updated[updated.length - 1]
                  if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = { ...last, content: (last.content || '') + chunk }
                  }
                  return updated
                })
              }
            } else if (typeof data.type === 'string' && data.type.startsWith('agent_')) {
              applyAgentTaskEvent(data)
            } else if (data.type === 'display_card') {
              setMessages((prev) => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last && last.role === 'assistant') {
                  const existing = last.displayCards || []
                  updated[updated.length - 1] = {
                    ...last,
                    displayCards: [
                      ...existing,
                      {
                        card_type: data.card_type,
                        payload: data.payload,
                        summary: data.summary,
                      },
                    ],
                  }
                }
                return updated
              })
            } else if (data.type === 'error') {
              showToast(`Agent error: ${data.error || 'unknown'}`, 'error')
            }
          } catch { /* partial JSON chunk — ignore */ }
        }
      }
    } catch (e) {
      console.error('Failed to process approval action:', e)
      showToast('Failed to continue the task. Try again.', 'error')
    } finally {
      setIsStreaming(false)
    }
  }

  const handleApproveHITL = async (taskId: string, stepIndex: number, action: 'approve' | 'skip' | 'cancel') => {
    // Clear approval card from message
    setMessages((prev) =>
      prev.map((m) =>
        m.agentApprovalRequired?.taskId === taskId
          ? { ...m, agentApprovalRequired: undefined }
          : m
      )
    )
    showToast(
      action === 'approve'
        ? 'Action approved! Continuing...'
        : action === 'skip'
        ? 'Step skipped.'
        : 'Task cancelled.',
      'info'
    )
    await streamApproval(taskId, stepIndex, action)
  }

  const handleUserInputSubmit = async (taskId: string, stepIndex: number, answer: string) => {
    // Clear user input card from message
    setMessages((prev) =>
      prev.map((m) =>
        m.agentUserInputRequired?.taskId === taskId
          ? { ...m, agentUserInputRequired: undefined }
          : m
      )
    )

    let finalAnswer = answer

    if (answer.toLowerCase().includes('mount local folder') || answer.toLowerCase().includes('mount folder')) {
      try {
        if ('showDirectoryPicker' in window) {
          showToast('Select local folder to mount...', 'info')
          const dirHandle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
          if (dirHandle) {
            ;(window as any)._ochuko_dir_handle = dirHandle
            const folderName = dirHandle.name
            localStorage.setItem('ochuko_mounted_folder_name', folderName)

            const fileSummaries: { name: string; size: number; isDir: boolean; mtime: number }[] = []
            let totalCount = 0
            for await (const [name, handle] of (dirHandle as any).entries()) {
              if (name.startsWith('.') && name !== '.env') continue
              totalCount++
              const isDir = handle.kind === 'directory'
              let sz = 0
              let mt = Date.now()
              if (!isDir) {
                try {
                  const f = await handle.getFile()
                  sz = f.size
                  mt = f.lastModified
                } catch {}
              }
              fileSummaries.push({ name, size: sz, isDir, mtime: mt })
            }

            // Sort newest first
            fileSummaries.sort((a, b) => b.mtime - a.mtime)

            // Format compact representation (max 25 items, zero blind uploads)
            const compactLines = fileSummaries.slice(0, 25).map(item => {
              if (item.isDir) return `[DIR] ${item.name}`
              const szStr = item.size < 1024 ? `${item.size}B` : item.size < 1024 * 1024 ? `${Math.round(item.size / 1024)}KB` : `${(item.size / (1024 * 1024)).toFixed(1)}MB`
              return `${item.name} (${szStr})`
            })

            const countNotice = totalCount > 25 ? ` (showing 25 of ${totalCount} items)` : ` (${totalCount} items)`
            finalAnswer = `Mounted local folder '${folderName}'${countNotice}. Accessible files: ${compactLines.join(', ')}. Zero blind uploads enabled; files will be streamed on-demand if read.`
          }
        } else {
          showToast('Directory picker not supported in this browser. Please upload files directly.', 'info')
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          console.error('Folder mount error:', err)
        }
      }
    } else if (answer.toLowerCase().includes('upload file') || answer.toLowerCase().includes('select and upload')) {
      if (fileInputRef && fileInputRef.current) {
        fileInputRef.current.click()
        return
      }
    } else if (answer.toLowerCase().includes('workstation bridge')) {
      try {
        const res = await fetch('http://127.0.0.1:3920/health', { signal: AbortSignal.timeout(1500) })
        if (res.ok) {
          const bInfo = await res.json()
          finalAnswer = `Local companion bridge active on port 3920 (${bInfo.platform || 'Host'}). Proceeding with workstation access.`
        }
      } catch {
        showToast('Bridge not running on 127.0.0.1:3920. Run: python -m app.connectors.workstation_bridge', 'info')
      }
    }

    showToast('Response submitted! Continuing...', 'info')
    if (taskId && taskId !== 'chat' && taskId !== activeConversationId) {
      await streamApproval(taskId, stepIndex, 'respond', finalAnswer)
    } else {
      await triggerStream(messages, finalAnswer)
    }
  }

  const triggerStream = async (history: Message[], newUserMessage: string | Message, overrideConvoId?: string, attachments?: any[]) => {

    // 1. Abort any active stream before launching a new one

    if (abortControllerRef.current) {

      abortControllerRef.current.abort()

    }

    const abortController = new AbortController()

    abortControllerRef.current = abortController

    setIsStreaming(true)

    setWebSearchStatus('idle')

    setActivityLabel('')

    let currentConvoId = overrideConvoId || activeConversationId

    const userMessageObj: Message = typeof newUserMessage === 'string'

      ? { role: 'user', content: newUserMessage }

      : newUserMessage

    // Append the new user message and an assistant placeholder

    const nextMessages: Message[] = [...history, userMessageObj]

    // No timestamp on the placeholder — it will be stamped when the stream completes
    // so the "just now" / "3m ago" indicator never shows mid-stream.
    setMessages([...nextMessages, { role: 'assistant', content: '' }])

    try {

      let token = (await getEffectiveToken()) || ''

      // Pre-fetch local files and directory listings via companion bridge if paths are referenced and Workstation Access is active
      const workstationFiles: { path: string; content: string }[] = []
      const workstationDirs: { path: string; resolved_path: string; total_count: number; entries: any[] }[] = []
      if (isWorkstationAccessEnabled) {
        try {
          const userMsgStr = typeof newUserMessage === 'string' ? newUserMessage : (newUserMessage?.content || '')
          // Include recent messages so follow-ups like "I gave you access for autonomy" or "inspect that folder" retain context
          const historyText = (nextMessages || []).slice(-4).map((m) => m.content || '').join('\n')
          const combinedMsgContext = `${userMsgStr}\n${historyText}`

          // 1. Quoted paths (single, double, backticks)
          const quotedMatches = Array.from(combinedMsgContext.matchAll(/["'`]((?:[A-Za-z]:[\\/]|\/(?:Users|home)[\\/])[^"'`\n\r]+)["'`]/g)).map((m) => m[1].trim())
          // 2. Unquoted paths (Windows or Unix paths, allowing spaces in directory names)
          const rawPathMatches = Array.from(combinedMsgContext.matchAll(/(?:[A-Za-z]:[\\/]|\/(?:Users|home)[\\/])[^<>:"|?*\n\r`']+/g)).map((m) => m[0].trim().replace(/[.,;!?)\]]+$/, ''))
          // 3. Folder aliases and natural phrases
          const aliasMatches: string[] = []
          if (/\b(?:my\s+)?downloads\b/i.test(combinedMsgContext)) aliasMatches.push('downloads')
          if (/\b(?:my\s+)?documents\b/i.test(combinedMsgContext)) aliasMatches.push('documents')
          if (/\b(?:my\s+)?desktop\b/i.test(combinedMsgContext)) aliasMatches.push('desktop')

          // Extract patterns like "books folder in documents", "books in documents"
          const inFolderMatches = Array.from(combinedMsgContext.matchAll(/(?:my\s+)?([a-zA-Z0-9_\-\s]{2,25}?)(?:\s+folder|\s+directory)?\s+(?:in|under|inside)\s+(documents|downloads|desktop)\b/gi))
          for (const m of inFolderMatches) {
            const sub = m[1].trim()
            const parent = m[2].trim().toLowerCase()
            aliasMatches.push(`${parent}/${sub}`)
            aliasMatches.push(sub)
          }

          // Extract patterns like "<name> folder" or "folder <name>"
          const namedFolderMatches = Array.from(combinedMsgContext.matchAll(/(?:my\s+)?([a-zA-Z0-9_-]{2,25})\s+(?:folder|directory)\b/gi))
          for (const m of namedFolderMatches) {
            aliasMatches.push(m[1].trim())
          }

          const candidatePaths = Array.from(new Set([...quotedMatches, ...rawPathMatches, ...aliasMatches]))

          // ── Tier 1: HTML5 File System Access API (window.showDirectoryPicker) ──
          // Directly read from user's mounted folder handle in the browser (Zero local python daemon needed)
          const mountedHandle = (window as any)._ochuko_dir_handle
          if (mountedHandle) {
            try {
              const rootEntries: any[] = []
              let totalFolderItems = 0
              for await (const [eName, h] of (mountedHandle as any).entries()) {
                totalFolderItems++
                if (totalFolderItems <= 120) {
                  let isDir = false
                  try {
                    isDir = h.kind === 'directory'
                  } catch {}
                  let sz = 0
                  let mt = Date.now()
                  if (!isDir) {
                    try {
                      const f = await h.getFile()
                      sz = f.size
                      mt = f.lastModified
                    } catch {}
                  }
                  rootEntries.push({
                    name: eName,
                    is_dir: isDir,
                    size: sz,
                    modified: new Date(mt).toISOString(),
                    relative_time: 'local disk',
                    size_formatted: sz < 1024 ? `${sz}B` : sz < 1024 * 1024 ? `${Math.round(sz / 1024)}KB` : `${(sz / (1024 * 1024)).toFixed(1)}MB`,
                  })
                }
              }
              workstationDirs.push({
                path: mountedHandle.name,
                resolved_path: `[Mounted Local Folder] ${mountedHandle.name}`,
                total_count: totalFolderItems,
                entries: rootEntries,
              })
              const entryLines = rootEntries.map((e: any) => {
                const prefix = e.is_dir ? '[DIR]' : '[FILE]'
                return `${prefix} ${e.name} (${e.size_formatted}, modified: ${e.modified})`
              }).join('\n')
              const countNotice = totalFolderItems > 100 ? ` (showing 100 of ${totalFolderItems} items)` : ` (${totalFolderItems} items)`
              workstationFiles.push({
                path: `workstation_folder_inventory.txt`,
                content: `=== WORKSTATION DIRECTORY INVENTORY: ${mountedHandle.name} (HTML5 File System Access API) ===\nTotal items: ${totalFolderItems}${countNotice}\n\n${entryLines}`,
              })

              // If candidate paths or referenced filenames match any file in mountedHandle, read content directly
              for (const candPath of candidatePaths) {
                const cleanBase = candPath.split(/[\\/]/).pop()?.trim()
                if (cleanBase) {
                  try {
                    const fh = await mountedHandle.getFileHandle(cleanBase)
                    const f = await fh.getFile()
                    if (f.size <= 500000) { // Max 500KB text pre-fetch
                      const txt = await f.text()
                      workstationFiles.push({ path: cleanBase, content: txt })
                    }
                  } catch {}
                }
              }
            } catch (mErr) {
              console.warn('Mounted folder handle read error:', mErr)
            }
          }

          if (candidatePaths.length > 0) {
            for (const candPath of candidatePaths.slice(0, 6)) {
              try {
                // First try /list in case it's a directory
                const lCtrl = new AbortController()
                const lTimeout = setTimeout(() => lCtrl.abort(), 2000)
                const lRes = await fetch(`http://127.0.0.1:3920/list?path=${encodeURIComponent(candPath)}`, {
                  signal: lCtrl.signal,
                })
                clearTimeout(lTimeout)
                if (lRes.ok) {
                  const lJson = await lRes.json()
                  if (lJson && lJson.success && Array.isArray(lJson.entries)) {
                    workstationDirs.push({
                      path: candPath,
                      resolved_path: lJson.resolved_path || candPath,
                      total_count: lJson.total_count || lJson.entries.length,
                      entries: lJson.entries,
                    })
                    // Create formatted directory inventory text file so it is placed in sandbox and injected into agent context
                    const entryLines = lJson.entries.map((e: any) => {
                      const prefix = e.is_dir ? '[DIR]' : '[FILE]'
                      return `${prefix} ${e.name} (${e.size_formatted || e.size + 'B'}, modified: ${e.relative_time || e.modified})`
                    }).join('\n')
                    const invContent = `=== WORKSTATION DIRECTORY INVENTORY: ${lJson.resolved_path || candPath} ===\nTotal items: ${lJson.total_count || lJson.entries.length}\n\n${entryLines}`
                    workstationFiles.push({
                      path: `workstation_folder_inventory.txt`,
                      content: invContent,
                    })
                    continue
                  }
                }

                // If not a directory, try /read for file
                const bCtrl = new AbortController()
                const bTimeout = setTimeout(() => bCtrl.abort(), 2000)
                const bRes = await fetch(`http://127.0.0.1:3920/read?path=${encodeURIComponent(candPath)}`, {
                  signal: bCtrl.signal,
                })
                clearTimeout(bTimeout)
                if (bRes.ok) {
                  const bJson = await bRes.json()
                  if (bJson && bJson.content) {
                    workstationFiles.push({ path: candPath, content: bJson.content })
                  }
                }
              } catch {
                // Bridge not reachable or timeout — non-blocking
              }
            }
          }

          // ── Persistent Full PC Access on Toggle ──
          // If Workstation Access is active and no specific directory was queried yet,
          // automatically probe the bridge for the user's primary folders (Documents, Downloads, Desktop)
          // so the agent ALWAYS has full visibility into the PC file structure.
          if (workstationDirs.length === 0) {
            try {
              const hCtrl = new AbortController()
              const hTimeout = setTimeout(() => hCtrl.abort(), 1200)
              const hRes = await fetch('http://127.0.0.1:3920/health', { signal: hCtrl.signal })
              clearTimeout(hTimeout)
              if (hRes.ok) {
                const bInfo = await hRes.json()
                // Fetch Documents overview by default
                const dRes = await fetch('http://127.0.0.1:3920/list?path=documents', { signal: AbortSignal.timeout(1800) })
                if (dRes.ok) {
                  const dJson = await dRes.json()
                  if (dJson && dJson.success && Array.isArray(dJson.entries)) {
                    workstationDirs.push({
                      path: 'documents',
                      resolved_path: dJson.resolved_path,
                      total_count: dJson.total_count || dJson.entries.length,
                      entries: dJson.entries,
                    })
                    const entryLines = dJson.entries.map((e: any) => {
                      const prefix = e.is_dir ? '[DIR]' : '[FILE]'
                      return `${prefix} ${e.name} (${e.size_formatted || e.size + 'B'}, modified: ${e.relative_time || e.modified})`
                    }).join('\n')
                    workstationFiles.push({
                      path: `workstation_folder_inventory.txt`,
                      content: `=== WORKSTATION DIRECTORY INVENTORY: ${dJson.resolved_path} (Host PC Documents Root) ===\nTotal items: ${dJson.total_count || dJson.entries.length}\nPlatform: ${bInfo.platform || 'Host'} | User: ${bInfo.username || 'Current'}\n\n${entryLines}`,
                    })
                  }
                }
              }
            } catch {
              // Bridge not reachable or timeout — non-blocking
            }
          }
        } catch {
          // Ignore pre-fetch failures
        }
      }

      const sendStreamRequest = () => fetch(`${API_BASE}/v1/responses/stream`, {

        method: 'POST',

        headers: {

          'Content-Type': 'application/json',

          Authorization: `Bearer ${token}`,

        },

        body: JSON.stringify({

          conversation_id: overrideConvoId || activeConversationId,

          mode,

          messages: nextMessages.map((m) => ({ role: m.role, content: m.content })),

          attachments: attachments || [],

          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,

          local_time: new Date().toString(),

          viewport: window.innerWidth < 640 ? 'mobile' : 'desktop',

          workstation_access_enabled: isWorkstationAccessEnabled,

          workstation_files: workstationFiles,

          workstation_dirs: workstationDirs,

          review_policy: localStorage.getItem('ochuko_review_policy') || 'always_ask',

        }),

        signal: abortController.signal,

      })

      // Retry transient failures (cold-start / network blips) with backoff so the
      // first message doesn't fall through while the server is waking up.
      const MAX_STREAM_ATTEMPTS = 3

      let response: Response | undefined

      for (let attempt = 1; attempt <= MAX_STREAM_ATTEMPTS; attempt++) {

        try {

          response = await sendStreamRequest()

          if ([502, 503, 504].includes(response.status) && attempt < MAX_STREAM_ATTEMPTS) {

            throw new TypeError(`Server unavailable (status ${response.status})`)

          }

          break

        } catch (attemptErr: any) {

          if (attemptErr.name === 'AbortError') throw attemptErr

          const isTransient = attemptErr instanceof TypeError ||
            /failed to fetch|networkerror|load failed|network request failed|server unavailable/i.test(attemptErr.message || '')

          if (!isTransient || attempt === MAX_STREAM_ATTEMPTS) throw attemptErr

          setMessages((prev) => {

            const updated = [...prev]

            updated[updated.length - 1] = {

              ...updated[updated.length - 1],

              content: 'Waking up the server, one moment...'

            }

            return updated

          })

          await new Promise((resolve) => setTimeout(resolve, 2000 * attempt))

        }

      }

      if (!response) throw new Error('No response from server')

      if (!response.ok) {

        let errMsg = `HTTP error! status: ${response.status}`

        try {

          const errData = await response.json()

          if (errData?.error?.message) {

            errMsg = errData.error.message

          } else if (errData?.detail) {

            errMsg = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)

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
      let sseBuffer = ''  // Accumulates partial lines across chunk boundaries

      while (true) {

        const { done, value } = await reader.read()

        if (done) break

        sseBuffer += decoder.decode(value, { stream: true })

        // Process only complete lines (terminated by \n).
        // The last segment after the final \n is an incomplete line — keep it in the buffer.
        const lastNewline = sseBuffer.lastIndexOf('\n')
        if (lastNewline === -1) continue  // no complete line yet, wait for more data

        const completePart = sseBuffer.slice(0, lastNewline)
        sseBuffer = sseBuffer.slice(lastNewline + 1)  // carry forward the unterminated tail

        for (const line of completePart.split('\n')) {

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

            } else if (data.type === 'clear_content') {

              accumulatedText = ''

              setMessages((prev) => {

                const updated = [...prev]

                if (updated.length > 0) {

                  updated[updated.length - 1] = {

                    ...updated[updated.length - 1],

                    content: '',

                    sources: undefined,

                    generatedFiles: undefined

                  }

                }

                return updated

              })

            } else if (data.type === 'clear_thinking') {

              setMessages((prev) => {

                const updated = [...prev]

                if (updated.length > 0) {

                  updated[updated.length - 1] = {

                    ...updated[updated.length - 1],

                    thinkingContent: ''

                  }

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

              currentConvoId = data.conversation_id
              setActiveConversationId(data.conversation_id)


              // ── Auto-title: generate from first user message client-side ─────
              // Find the first user message in the current history to build the title.
              // Update the sidebar immediately (optimistic), then patch server in background.
              const convId = data.conversation_id as string
              const firstUserMsg = userMessageObj.content
              const defaultServerTitle = firstUserMsg.slice(0, 30) + (firstUserMsg.length > 30 ? '...' : '')

              setConversations(prev => {
                const existing = prev.find(c => c.id === convId)
                const isDefaultTitle = !existing || !existing.title || existing.title === 'New Chat' || existing.title === defaultServerTitle
                if (existing && !isDefaultTitle) return prev
                const autoTitle = generateAutoTitle(firstUserMsg)
                // Optimistic update in sidebar
                if (existing) {
                  return prev.map(c => c.id === convId ? { ...c, title: autoTitle } : c)
                }
                return prev
              })

              // Patch title on server in the background (non-blocking)
              setTimeout(async () => {
                try {
                  const existing = conversations.find(c => c.id === convId)
                  const isDefaultTitle = !existing || !existing.title || existing.title === 'New Chat' || existing.title === defaultServerTitle
                  if (existing && !isDefaultTitle) return // already has a custom user-supplied title
                  const autoTitle = generateAutoTitle(firstUserMsg)
                  const token = (await supabase.auth.getSession()).data.session?.access_token
                  if (!token) return
                  await fetch(`${API_BASE}/v1/conversations/${convId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                    body: JSON.stringify({ title: autoTitle }),
                  })
                } catch {
                  // Non-fatal: title will be set next time conversations load
                }
              }, 800)

              // Fire-and-forget: don't block streaming for conversation list sync
              setTimeout(() => {
                fetchConversations().catch(err => {
                  console.warn('Background conversation sync failed:', err)
                })
              }, 0)

            } else if (data.type === 'activity_status') {

              setActivityLabel(data.label || 'Generating task...')

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

                  // Accumulate sources from ALL search iterations (multi-step loop).
                  // De-duplicate by URL so the same source never appears twice.

                  setMessages((prev) => {

                    const updated = [...prev]

                    if (updated.length > 0) {

                      const lastMsg = updated[updated.length - 1]

                      if (lastMsg.role === 'assistant') {

                        const existing: Source[] = lastMsg.sources || []
                        const existingUrls = new Set(existing.map((s: Source) => s.url))
                        const incoming: Source[] = (data.sources as Source[]).filter(
                          (s: Source) => s.url && !existingUrls.has(s.url)
                        )
                        updated[updated.length - 1] = {
                          ...lastMsg,
                          sources: [...existing, ...incoming],
                        }

                      }

                    }

                    return updated

                  })

                }

              } else if (data.status === 'error') {

                setWebSearchStatus('idle')

                setActivityLabel(data.label || 'Search failed.')

              }

            } else if (data.type === 'context_compacted') {

              // Context was compacted by the backend — insert a transparent marker
              // so the user knows what happened and what was summarised.

              // CRITICAL: the marker must be inserted BEFORE the trailing
              // assistant placeholder, never appended after it. Appending made
              // the marker the "last message", so every subsequent
              // content_block_delta wrote the streamed response into the marker
              // (whose content is never rendered) — the response appeared halted.

              const buildCompactionMarker = (): Message => ({
                role: 'assistant' as const,
                content: '',
                isCompactionMarker: true,
                compactionSummary: data.summary || '',
              })

              const insertMarker = (base: Message[]): Message[] => {
                const last = base[base.length - 1]
                // Insert before the streaming assistant placeholder if present
                if (last && last.role === 'assistant' && !last.isCompactionMarker && !last.isArchived) {
                  return [...base.slice(0, -1), buildCompactionMarker(), last]
                }
                return [...base, buildCompactionMarker()]
              }

              setMessages((prev) => {
                const activeIndices: number[] = []
                prev.forEach((m, idx) => {
                  if (!m.isCompactionMarker && !m.isArchived) {
                    activeIndices.push(idx)
                  }
                })
                 if (activeIndices.length > 20) {
                  const indicesToArchive = activeIndices.slice(0, -20)
                  const archived = prev.map((m, idx) =>
                    indicesToArchive.includes(idx) ? { ...m, isArchived: true } : m
                  )
                  return insertMarker(archived)
                }
                return insertMarker(prev)
              })

            } else if (data.type === 'image_gen_queued') {

              // AI decided to generate an image — show pending bubble and subscribe

              const imgJobId: string = data.job_id

              const imgPrompt: string = data.prompt || ''

              // Append a pending image bubble after the (possibly still-streaming) text

              // Append a pending image bubble status to the active assistant message

              setMessages((prev) => {

                const updated = [...prev]

                if (updated.length > 0) {

                  const lastMsg = updated[updated.length - 1]

                  if (lastMsg.role === 'assistant') {

                    return updated.map((m, idx) =>

                      idx === updated.length - 1

                        ? { ...m, imagePending: true, imagePrompt: imgPrompt, imageJobId: imgJobId }

                        : m

                    )

                  }

                }

                // Fallback if no assistant message exists

                return [

                  ...prev,

                  { role: 'assistant', content: '', imagePending: true, imagePrompt: imgPrompt, imageJobId: imgJobId }

                ]

              })

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

                          m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                            ? { ...m, imagePending: false, imageUrl: j.result.image_url, imageJobId: undefined }

                            : m

                        )

                      )

                      cleanupJob()

                    } else if (j.status === 'failed') {

                      console.error("Image generation job failed:", j.error)

                      setMessages((prev) =>

                        prev.map((m) =>

                          m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                            ? { ...m, imagePending: false, imageJobId: undefined, content: m.content + `\n\nImage generation failed: ${j.error || 'Please try again.'}` }

                            : m

                        )

                      )

                      cleanupJob()

                    }

                  }

                )

                .subscribe()

              // Polling fallback check interval in case WebSocket connection fails

              let isCleanedUp = false

              const pollInterval = setInterval(async () => {

                if (isCleanedUp) return

                try {

                  const session = await supabase.auth.getSession()

                  const token = session.data.session?.access_token

                  if (!token) return

                  const response = await fetch(`${API_BASE}/v1/agents/job/${imgJobId}`, {

                    headers: { 'Authorization': `Bearer ${token}` }

                  })

                  if (response.ok) {

                    const jobData = await response.json()

                    if (jobData.status === 'done' && jobData.result_blob_url) {

                      setMessages((prev) =>

                        prev.map((m) =>

                          m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                            ? { ...m, imagePending: false, imageUrl: jobData.result_blob_url, imageJobId: undefined }

                            : m

                        )

                      )

                      cleanupJob()

                    } else if (jobData.status === 'failed') {

                      console.error("Image generation job polled fail:", jobData.error_message)

                      setMessages((prev) =>

                        prev.map((m) =>

                          m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                            ? { ...m, imagePending: false, imageJobId: undefined, content: m.content + `\n\nImage generation failed: ${jobData.error_message || 'Please try again.'}` }

                            : m

                        )

                      )

                      cleanupJob()

                    }

                  }

                } catch (pollErr) {

                  console.warn("Error polling image generation job status:", pollErr)

                }

              }, 4000)

              // Unified cleanup function for subscription, polling, and timers

              const cleanupJob = () => {

                if (isCleanedUp) return

                isCleanedUp = true

                clearInterval(pollInterval)

                clearTimeout(stallTimeout)

                clearTimeout(hardTimeout)

                imgChannel.unsubscribe()

              }

              // Stall handling - FLUX on HuggingFace routinely takes 2-5 minutes
              // (120s per-request timeout across a fallback model chain), so the
              // old 90s guard declared "timed out" and CANCELLED polling while the
              // job was still running - the finished image landed in the DB with no
              // way to reach the UI. Now: soft notice at 2 min (polling + Realtime
              // stay active so the image still arrives), hard give-up at 10 min.

              const stallTimeout = setTimeout(() => {

                setMessages((prev) =>

                  prev.map((m) =>

                    m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                      ? { ...m, content: m.content + '\n\nStill generating - image models can take a few minutes. The image will appear here automatically.' }

                      : m

                  )

                )

              }, 120_000)

              const hardTimeout = setTimeout(() => {

                setMessages((prev) =>

                  prev.map((m) =>

                    m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                      ? { ...m, imagePending: false, imageJobId: undefined, content: m.content + '\n\nImage generation timed out after 10 minutes. Please try again.' }

                      : m

                  )

                )

                cleanupJob()

              }, 600_000)

            } else if (data.type === 'agent_step') {

              // OODA loop iteration counter — update the streaming assistant message

              setAgentStep(data.step || 0)

              setAgentMaxSteps(data.max_steps || 10)

              setMessages((prev) => {

                const updated = [...prev]

                if (updated.length > 0) {

                  updated[updated.length - 1] = {

                    ...updated[updated.length - 1],

                    agentStep: data.step,

                    agentMaxSteps: data.max_steps,

                    agentLabel: data.label || undefined,

                  }

                }

                return updated

              })

            } else if (data.type === 'agent_todo') {

              // Phase 3: live checklist (TodoWrite analog) — attach to the
              // streaming assistant message; AgentTodoChecklist renders it.
              setMessages((prev) => {

                const updated = [...prev]

                if (updated.length > 0) {

                  updated[updated.length - 1] = {

                    ...updated[updated.length - 1],

                    agentTodos: Array.isArray(data.todos) ? data.todos : undefined,

                  }

                }

                return updated

              })

            } else if (data.type === 'agent_orient') {

              // Phase 2: per-iteration Observe block. cap_extended notices
              // carry no observations — the soft cap self-extends silently;
              // ordinary orient records replace the message's orient state.
              if (data.status !== 'cap_extended') {

                setMessages((prev) => {

                  const updated = [...prev]

                  if (updated.length > 0) {

                    updated[updated.length - 1] = {

                      ...updated[updated.length - 1],

                      agentOrient: {

                        iteration: data.iteration,

                        progressed: data.progressed,

                        observations: Array.isArray(data.observations) ? data.observations : [],

                      },

                    }

                  }

                  return updated

                })

              }

            } else if (data.type === 'widget_loading') {

              // Pre-signal: show animated loading placeholder while the model finishes code generation
              setMessages((prev) => {
                const updated = [...prev]
                if (updated.length > 0) {
                  const last = { ...updated[updated.length - 1] }
                  const existingWidgets = last.widgetData || []
                  last.widgetData = [
                    ...existingWidgets,
                    {
                      code: '',
                      title: data.title || 'widget',
                      loadingMessages: data.loading_messages || ['Assembling visual...'],
                      widgetType: data.widget_type || 'diagram',
                      widgetLoading: true,
                    },
                  ]
                  updated[updated.length - 1] = last
                }
                return updated
              })

            } else if (data.type === 'widget') {

              // Full widget payload — replace the loading placeholder (last widgetLoading item)
              setMessages((prev) => {
                const updated = [...prev]
                if (updated.length > 0) {
                  const last = { ...updated[updated.length - 1] }
                  const existingWidgets = [...(last.widgetData || [])]
                  // Find the last loading placeholder and replace it
                  const placeholderIdx = existingWidgets.map(w => w.widgetLoading).lastIndexOf(true)
                  const newEntry = {
                    code: data.code,
                    title: data.title,
                    loadingMessages: data.loading_messages || [],
                    widgetType: data.widget_type || 'diagram',
                    widgetLoading: false,
                  }
                  if (placeholderIdx !== -1) {
                    existingWidgets[placeholderIdx] = newEntry
                  } else {
                    existingWidgets.push(newEntry)
                  }
                  last.widgetData = existingWidgets
                  updated[updated.length - 1] = last
                }
                return updated
              })

            } else if (data.type === 'memory_written') {

              // Agent stored a fact — show a transient toast so the user sees it

              showToast(`Remembered: ${data.key}`, 'info')

            } else if (data.type === 'thinking_start') {

              // Model started reasoning — open the thinking panel (initialise empty)
              setMessages((prev) => {
                const updated = [...prev]
                if (updated.length > 0) {
                  const last = updated[updated.length - 1]
                  const existing = last.thinkingContent
                  const newThinking = existing ? existing + '\n\n' : ''
                  updated[updated.length - 1] = { ...last, thinkingContent: newThinking }
                }
                return updated
              })

            } else if (data.type === 'thinking_delta') {

              // Append streaming reasoning chunk to thinkingContent
              const thoughtText: string = data.delta?.text ?? ''
              if (thoughtText) {
                setMessages((prev) => {
                  const updated = [...prev]
                  if (updated.length > 0) {
                    const last = updated[updated.length - 1]
                    updated[updated.length - 1] = {
                      ...last,
                      thinkingContent: (last.thinkingContent ?? '') + thoughtText,
                    }
                  }
                  return updated
                })
              }

            } else if (data.type === 'thinking_done') {

              // Thinking block complete — no state change needed, panel stays visible

            } else if (data.type === 'agent_file') {

              // Code executor produced a file — append download card to current message

              setMessages((prev) => {

                const updated = [...prev]

                if (updated.length > 0) {

                  const last = updated[updated.length - 1]

                  updated[updated.length - 1] = {

                    ...last,

                    generatedFiles: [

                      ...(last.generatedFiles || []),

                      {

                        filename: data.filename,

                        download_url: data.download_url,

                        size_bytes: data.size_bytes || 0,

                      },

                    ],

                  }

                }

                return updated

              })

            } else if (data.type === 'generated_files') {

              // execute_code sandbox produced one or more files — append all as download cards
              const newFiles: { filename: string; download_url: string; size_bytes: number }[] = (data.files || []).map(
                (f: any) => ({
                  filename: f.filename,
                  download_url: f.download_url,
                  size_bytes: f.size_bytes || 0,
                })
              )
              if (newFiles.length > 0) {
                // Auto-open the entry file (index.html for multi-file sites) in the ArtifactPanel
                const entry = pickEntryFile(newFiles)
                if (entry) {
                  dispatchOpenFilePreview({
                    name: entry.filename,
                    type: mimeFromName(entry.filename),
                    url: entry.download_url,
                    sizeBytes: entry.size_bytes,
                    siblingFiles: newFiles.map((f) => ({
                      name: f.filename,
                      type: mimeFromName(f.filename),
                      url: f.download_url,
                      sizeBytes: f.size_bytes,
                    })),
                  })
                }
                setMessages((prev) => {
                  const updated = [...prev]
                  if (updated.length > 0) {
                    const last = updated[updated.length - 1]
                    const existing = last.generatedFiles || []
                    const existingKeys = new Set(existing.map((f: any) => f.filename + '_' + f.size_bytes))
                    const filteredNew = newFiles.filter((f: any) => !existingKeys.has(f.filename + '_' + f.size_bytes))
                    if (filteredNew.length > 0) {
                      updated[updated.length - 1] = {
                        ...last,
                        generatedFiles: [...existing, ...filteredNew],
                      }
                    }
                  }
                  return updated
                })
              }

            } else if (data.type === 'display_card') {
              setMessages((prev) => {
                const updated = [...prev]
                if (updated.length > 0) {
                  const last = { ...updated[updated.length - 1] }
                  const existing = last.displayCards || []
                  last.displayCards = [
                    ...existing,
                    {
                      card_type: data.card_type,
                      payload: data.payload,
                      summary: data.summary,
                    },
                  ]
                  updated[updated.length - 1] = last
                }
                return updated
              })
            } else if (typeof data.type === 'string' && (data.type.startsWith('agent_') || data.type === 'ask_user_input')) {
              // Shared agent-task event path — also used by the approve-resume stream
              applyAgentTaskEvent(data)
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

        setAgentStep(0)

        abortControllerRef.current = null

        // Persist conversation to localStorage after the stream completes successfully (asynchronously)
        const completionTimestamp = Date.now()
        setMessages(prev => {
          const updated = [...prev]
          if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              timestamp: completionTimestamp
            }
          }
          if (currentConvoId && currentConvoId !== '00000000-0000-0000-0000-000000000000') {
            const uid = userIdRef.current
            // Defer localStorage writes to the event loop so they never block React's render thread or cut message flow
            setTimeout(() => {
              try {
                if (uid) {
                  localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), currentConvoId)
                }
                saveConvoCache(uid, currentConvoId, updated, mode)
              } catch (err) {
                console.warn('Deferred cache write failed:', err)
              }
            }, 0)
          }
          return updated
        })

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

  const toggleVoice = useCallback(async () => {

    if (voice.error === 'permission_denied') {
      showToast('Microphone access required for voice input', 'error')
      return
    }
    if (voice.isRecording) {
      voice.stopRecording()
    } else {
      await voice.startRecording()
    }

  }, [voice, showToast])

  // Keep ref in sync so keyboard shortcut can call toggleVoice without forward-reference issues
  toggleVoiceRef.current = toggleVoice

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length == 0) return
    for (let i = 0; i < files.length; i++) {
      await uploadFile(files[i])
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const triggerAgentJobs = async (files: AttachedFile[], promptText?: string) => {
    const historyBeforeJobs = [...messages]
    setIsStreaming(true)

    const convoId = activeConversationId && activeConversationId !== '00000000-0000-0000-0000-000000000000'
      ? activeConversationId
      : undefined

    const imgExts = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tiff', '.tif', '.ico', '.heic', '.heif', '.avif']

    const attachments = files.map(f => {
      const nameLower = f.name.toLowerCase()
      const isPdf = f.type === 'application/pdf' || nameLower.endsWith('.pdf')
      const isImg = f.type.startsWith('image/') || imgExts.some(ext => nameLower.endsWith(ext))
      const jobType = isPdf ? 'ocr' : (isImg ? 'vision' : 'code')

      return {
        name: f.name,
        jobType: jobType as 'ocr' | 'vision' | 'code',
        url: f.blobUrl
      }
    })

    const fileNames = files.map(f => f.name).join(', ')
    const userMsgText = promptText
      ? promptText
      : (files.length === 1 ? `Please analyze and describe this attached file: ${fileNames}` : `Please analyze and describe these attached files: ${fileNames}`)

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: userMsgText, fileAttachments: attachments },
      { role: 'assistant', content: '' }
    ])

    try {
      const backendAttachments = attachments.map(a => {
        return {
          filename: a.name,
          url: a.url || '',
          mime_type: mimeFromName(a.name),
        }
      })

      await triggerStream(historyBeforeJobs, {
        role: 'user',
        content: userMsgText,
        fileAttachments: attachments
      }, convoId, backendAttachments)

    } catch (err: any) {
      console.error('Agent file trigger failed:', err)
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
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }

  // ── Hybrid Search (Google grounding + Azure synthesis) ───────────────────

  // Patterns that should bypass the normal stream and use the grounding endpoint

  const SEARCH_INTENT_PATTERNS = [

    /^(search|look up|find|what('s| is) (happening|the latest|new)|latest|news|current|today|right now|who (is|are|won)|when (is|did|will)|where (is|are)|how much (is|does))/i,

    /^\/(search|web|google)\s+/i,

  ]

  const triggerHybridSearch = async (userPrompt: string, historyOverride?: Message[]) => {

    let convoId = activeConversationId

    const isNewConvo = !convoId || convoId === '00000000-0000-0000-0000-000000000000'

    if (isNewConvo) {

      convoId = safeRandomUUID()

      setActiveConversationId(convoId)

      const uidB = userIdRef.current
      if (uidB) localStorage.setItem(userCacheKey(uidB, 'active_conversation_id'), convoId)

    }

    const currentHistory = historyOverride || messages

    const nextMessages: Message[] = [...currentHistory, { role: 'user', content: userPrompt }]

    setMessages([...nextMessages, { role: 'assistant', content: '' }])

    setIsStreaming(true)

    setWebSearchStatus('searching')

    try {

      const session = await supabase.auth.getSession()

      const token = session.data.session?.access_token

      const userId = session.data.session?.user?.id

      if (!token) throw new Error('Authentication session not found.')

      if (isNewConvo && userId) {

        try {

          const title = userPrompt.slice(0, 30) + (userPrompt.length > 30 ? '...' : '')

          await supabase.from('conversations').insert([

            {

              id: convoId,

              user_id: userId,

              title: title,

              mode: mode,

              agent_type: 'chat',

            }

          ])

          fetchConversations()

        } catch (dbErr) {

          console.error('Failed to create new conversation for search:', dbErr)

        }

      }

      // Save user message to database

      if (userId) {

        try {

          await supabase.from('messages').insert([

            {

              conversation_id: convoId,

              role: 'user',

              content: userPrompt,

            }

          ])

        } catch (dbErr) {

          console.error('Failed to save user search message to DB:', dbErr)

        }

      }

      const res = await fetch(`${API_BASE}/v1/search/ask-hybrid`, {

        method: 'POST',

        headers: {

          'Content-Type': 'application/json',

          Authorization: `Bearer ${token}`,

        },

        body: JSON.stringify({

          prompt: userPrompt,

          conversation_id: convoId,

          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,

          local_time: new Date().toString(),

        }),

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

      // Save assistant response to database

      if (userId) {

        try {

          await supabase.from('messages').insert([

            {

              conversation_id: convoId,

              role: 'assistant',

              content: answer,

              routing_mode: 'solve',

              routing_reason: 'Hybrid Search Engine Response',

              content_parts: sources.length > 0 ? { sources } : null,

              model: data.model || 'gpt-5.4-mini',

              tokens_input: data.tokens_input || 0,

              tokens_output: data.tokens_output || 0,

            }

          ])

        } catch (dbErr) {

          console.error('Failed to save assistant search response to DB:', dbErr)

        }

      }

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

    if (uploading) return

    let historyClean = messages

    if (isStreaming) {

      // Abort active stream

      if (abortControllerRef.current) {

        abortControllerRef.current.abort()

      }

      const lastMsg = messages[messages.length - 1]

      if (lastMsg && lastMsg.role === 'assistant') {

        if (lastMsg.content.length > 0) {

          historyClean = [

            ...messages.slice(0, -1),

            { ...lastMsg, content: lastMsg.content + '\n\n*— stopped —*' }

          ]

        } else {

          historyClean = messages.slice(0, -1)

        }

      }

      setMessages(historyClean)

    }

    const pastedBlocks = pastedSnippets.length > 0
      ? pastedSnippets.map(s => `[Pasted Content: ${s.name}]\n\`\`\`\n${s.content}\n\`\`\``).join('\n\n')
      : ''

    if (attachedFiles.length > 0) {
      const filesToProcess = [...attachedFiles]
      let promptText = input.trim()
      if (pastedBlocks) {
        promptText = promptText ? `${promptText}\n\n${pastedBlocks}` : pastedBlocks
        setPastedSnippets([])
      }

      setInput('')

      // Revoke local object URLs to free memory before clearing state
      filesToProcess.forEach(f => {
        if (f.localObjectUrl) URL.revokeObjectURL(f.localObjectUrl)
      })

      setAttachedFiles([])

      setTimeout(() => inputRef.current?.focus(), 0)

      await triggerAgentJobs(filesToProcess, promptText)

      return
    }

    if (!input.trim() && !pastedBlocks) return

    let userMessage = input.trim()

    setInput('')

    if (pastedBlocks) {
      userMessage = userMessage
        ? `${userMessage}\n\n${pastedBlocks}`
        : pastedBlocks
      setPastedSnippets([])
    }

    setTimeout(() => inputRef.current?.focus(), 0)

    // Route to hybrid search if the message matches a web-search intent pattern

    if (SEARCH_INTENT_PATTERNS.some((p) => p.test(userMessage))) {

      await triggerHybridSearch(userMessage, historyClean)

      return

    }

    await triggerStream(historyClean, userMessage)

  }

  const handleEditSubmit = async (index: number) => {

    const newText = editingMessageText.trim()

    if (!newText || isStreaming) return

    setEditingMessageIndex(null)

    setEditingMessageText("")

    const convoId = activeConversationId
    if (convoId && convoId !== '00000000-0000-0000-0000-000000000000') {
      try {
        // Query the database for message IDs ordered by creation time
        const { data: dbMsgs } = await supabase
          .from('messages')
          .select('id')
          .eq('conversation_id', convoId)
          .order('created_at', { ascending: true })

        if (dbMsgs && dbMsgs.length > index) {
          const idsToDelete = dbMsgs.slice(index).map(m => m.id)
          if (idsToDelete.length > 0) {
            await supabase.from('messages').delete().in('id', idsToDelete)
          }
        }
      } catch (dbErr) {
        console.error('Failed to delete truncated messages from DB:', dbErr)
      }
    }

    // Truncate messages list up to the edited user message
    const truncatedHistory = messages.slice(0, index)

    await triggerStream(truncatedHistory, newText)

  }

  const renderInputConsole = (isCentered = false) => (
    <div className="max-w-2xl w-full mx-auto">
      <form
        ref={formRef}
        onSubmit={handleSend}
        className={`w-full max-w-full bg-[#0d0f11]/95 border ${
          isCentered
            ? 'border-[#262a33] shadow-[0_8px_30px_rgba(0,0,0,0.45)] rounded-xl p-2.5 sm:p-3.5'
            : 'border-[#1e2025] rounded-xl py-1.5 px-2.5 sm:px-3 shadow-xl'
        } flex flex-col gap-1 relative z-10 backdrop-blur-xl transition-all duration-200 focus-within:border-[#ffffff]/25 pointer-events-auto overflow-hidden box-border`}
      >
        {/* Uploading progress indicator */}
        {uploading && (
          <div className="flex items-center justify-between p-2 bg-[#0d0f11]/80 border border-[#1e2025]/50 rounded-lg animate-pulse mb-1">
            <div className="flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 text-brand-text animate-spin shrink-0" />
              <span className="text-[11px] text-brand-text font-semibold tracking-wide">
                Uploading to secure storage... {uploadProgress !== null ? `${uploadProgress}%` : ''}
              </span>
            </div>
          </div>
        )}

        {/* Voice recording status strip */}
        {voice.isRecording && (
          <div className="flex items-center justify-between p-2 bg-[#0d0f11]/80 border border-[#1e2025]/50 rounded-lg animate-pulse mb-1">
            <div className="flex items-center gap-2.5">
              <VoiceWaveform volume={voice.currentVolume} />
              <span className="text-[10px] font-bold text-brand-text tracking-widest uppercase">Listening...</span>
              {voice.isTranscribing && <Loader2 className="w-3 h-3 text-brand-muted animate-spin" />}
            </div>
            <button
              type="button"
              onClick={() => voice.stopRecording()}
              className="text-[9px] text-brand-muted hover:text-red-400 font-bold tracking-widest uppercase transition"
            >
              Stop
            </button>
          </div>
        )}

        {/* Attached Files Deck — positioned prominently above textarea */}
        {(attachedFiles.length > 0 || pastedSnippets.length > 0) && (
          <div className="flex flex-wrap items-center gap-2 px-1 py-1.5 border-b border-white/[0.08] mb-1 max-w-full overflow-x-auto">
            {attachedFiles.map((file, idx) => {
              const isImg = file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|svg)$/i.test(file.name)
              const ext = file.name.split('.').pop()?.toUpperCase() || 'FILE'
              const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
              const sizeLabel = file.sizeBytes ? (
                file.sizeBytes > 1024 * 1024 ? `${(file.sizeBytes / (1024 * 1024)).toFixed(1)} MB`
                : file.sizeBytes > 1024 ? `${(file.sizeBytes / 1024).toFixed(0)} KB`
                : `${file.sizeBytes} B`
              ) : ''

              if (isImg) {
                return (
                  <div
                    key={idx}
                    onClick={() => setPreviewingFile({
                      name: file.name,
                      type: file.type,
                      url: file.blobUrl,
                      localObjectUrl: file.localObjectUrl,
                      sizeBytes: file.sizeBytes
                    })}
                    className="relative group w-24 h-18 sm:w-32 sm:h-24 rounded-lg overflow-hidden border border-white/15 bg-[#121418] cursor-pointer hover:border-white/35 transition shrink-0 shadow-md animate-fadeIn select-none"
                    title="Click to preview image"
                  >
                    <img
                      src={file.localObjectUrl || file.blobUrl}
                      alt={file.name}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex items-end p-1.5 pointer-events-none">
                      <span className="text-[10px] text-white/90 font-medium truncate w-full">{file.name}</span>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (file.localObjectUrl) URL.revokeObjectURL(file.localObjectUrl)
                        setAttachedFiles(prev => prev.filter((_, i) => i !== idx))
                      }}
                      className="absolute top-1 right-1 min-w-[28px] min-h-[28px] touch:min-w-[36px] touch:min-h-[36px] flex items-center justify-center rounded-full bg-black/70 hover:bg-red-500 active:bg-red-600 text-white/80 hover:text-white transition shadow z-10 touch-manipulation"
                      title="Remove image"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )
              }

              const extBadgeBg = isPdf ? 'bg-red-500/15 text-red-400 border-red-500/30'
                : 'bg-white/10 text-white/80 border-white/15'

              return (
                <div
                  key={idx}
                  onClick={() => setPreviewingFile({
                    name: file.name,
                    type: file.type,
                    url: file.blobUrl,
                    localObjectUrl: file.localObjectUrl,
                    sizeBytes: file.sizeBytes
                  })}
                  className="relative group flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[#14161b] hover:bg-[#1a1d24] border border-white/15 hover:border-white/30 transition cursor-pointer shadow-md w-full max-w-full sm:w-auto sm:max-w-[240px] shrink-0 animate-fadeIn select-none"
                  title="Click to preview file"
                >
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-black text-[9px] tracking-tight border ${extBadgeBg} shrink-0`}>
                    {ext.slice(0, 4)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-medium text-white/90 truncate leading-tight">{file.name}</p>
                    <p className="text-[10px] text-white/50 mt-0.5">{sizeLabel || (isPdf ? 'PDF document' : 'File')}</p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (file.localObjectUrl) URL.revokeObjectURL(file.localObjectUrl)
                      setAttachedFiles(prev => prev.filter((_, i) => i !== idx))
                    }}
                    className="min-w-[28px] min-h-[28px] touch:min-w-[36px] touch:min-h-[36px] flex items-center justify-center p-1 rounded-full text-white/40 hover:text-red-400 hover:bg-white/10 active:bg-white/20 transition shrink-0 touch-manipulation"
                    title="Remove file"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )
            })}
            {pastedSnippets.map((snippet) => (
              <div
                key={snippet.id}
                onClick={() => setPreviewingFile({
                  name: snippet.name,
                  type: 'text/plain',
                  content: snippet.content,
                  sizeBytes: snippet.sizeBytes
                })}
                className="relative group flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[#14161b] hover:bg-[#1a1d24] border border-white/15 hover:border-white/30 transition cursor-pointer shadow-md w-full max-w-full sm:w-auto sm:max-w-[240px] shrink-0 animate-fadeIn select-none"
                title="Click to preview pasted text"
              >
                <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-[9px] tracking-tight border bg-blue-500/15 text-blue-400 border-blue-500/30 shrink-0">
                  TXT
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] font-medium text-white/90 truncate leading-tight">{snippet.name}</p>
                  <p className="text-[10px] text-white/50 mt-0.5">Pasted snippet</p>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setPastedSnippets(prev => prev.filter(s => s.id !== snippet.id))
                  }}
                  className="min-w-[28px] min-h-[28px] touch:min-w-[36px] touch:min-h-[36px] flex items-center justify-center p-1 rounded-full text-white/40 hover:text-red-400 hover:bg-white/10 active:bg-white/20 transition shrink-0 touch-manipulation"
                  title="Remove pasted text"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Middle Row: Textarea input - Compact, lean height */}
        <div className="relative flex-1">
          <textarea
            ref={inputRef as any}
            rows={1}
            value={input}
            onPaste={handlePaste}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                if (!uploading) {
                  formRef.current?.requestSubmit()
                }
              }
            }}
            onChange={(e) => {
              setInput(e.target.value)
              if (voice.isRecording) voice.clearTranscript()
            }}
            placeholder={
              voice.isRecording ? 'Listening...' :
              mode === 'agent' ? 'Describe your goal — Agent Ochuko will plan and execute it...' :
              attachedFiles.length > 0 ? 'Add prompt details for the agent...' :
              pastedSnippets.length > 0 ? (pastedSnippets.length > 1 ? `Add prompt details for ${pastedSnippets.length} pasted snippets...` : 'Add prompt details for the pasted text...') :
              "Let's talk"
            }
            className={`w-full bg-transparent text-base sm:text-sm leading-snug text-brand-text placeholder-brand-muted/40 placeholder:text-base sm:placeholder:text-sm focus:outline-none resize-none max-h-36 touch:max-h-[30dvh] overflow-y-auto py-0 ${
              isCentered ? 'min-h-[38px] sm:min-h-[34px]' : 'h-[24px] min-h-[22px] sm:h-[20px] sm:min-h-[18px]'
            }`}
          />
        </div>

        {/* Bottom Row: Attachments status & action buttons - Compact and sleek */}
        <div className="flex items-center justify-between gap-1 pt-0.5 sm:pt-1 w-full min-w-0">
          {/* Left Side: Attach File, Voice, Mode selector */}
          <div className="flex items-center gap-1 min-w-0 shrink">

            <button
              type="button"
              onClick={handleTriggerUpload}
              disabled={uploading}
              className="h-8 w-8 sm:h-7.5 sm:w-7.5 touch:h-11 touch:w-11 p-1 touch:p-1.5 text-brand-muted hover:text-brand-text hover:bg-white/5 active:bg-white/10 rounded-md flex items-center justify-center transition duration-150 active:scale-95 disabled:opacity-20 shrink-0 cursor-pointer touch-manipulation"
              title="Attach document or image"
              aria-label="Attach file"
            >
              <Paperclip className="w-3.5 h-3.5 touch:w-5 touch:h-5" />
            </button>

            {/* Voice mic button */}
            {voice.isSupported && (
              <button
                id="voice-mic-button"
                type="button"
                onClick={toggleVoice}
                disabled={isStreaming}
                className={`h-8 w-8 sm:h-7.5 sm:w-7.5 touch:h-11 touch:w-11 p-1 touch:p-1.5 transition-all duration-150 active:scale-95 rounded-md flex items-center justify-center disabled:opacity-20 shrink-0 cursor-pointer touch-manipulation ${
                  voice.isRecording
                    ? 'text-[#ffffff] voice-pulse-ring'
                    : 'text-brand-muted hover:text-brand-text hover:bg-white/5 active:bg-white/10'
                }`}
                title={voice.isRecording ? 'Stop recording' : 'Voice input'}
                aria-label="Voice input"
              >
                <Mic className="w-3.5 h-3.5 touch:w-5 touch:h-5" />
              </button>
            )}

            {/* Mobile & Compact Mode Selector Button: [Icon Mode ▾] */}
            <button
              type="button"
              onClick={() => setIsModeSheetOpen(true)}
              className={`lg:hidden h-8 sm:h-7.5 touch:h-11 px-2 touch:px-3 py-0.5 rounded-md border text-[10.5px] touch:text-xs font-semibold flex items-center gap-1 transition duration-150 active:scale-95 select-none shrink-0 cursor-pointer touch-manipulation ${
                mode === 'agent'
                  ? 'bg-brand-accent/20 border-brand-accent/40 text-brand-accent shadow-sm shadow-brand-accent/20'
                  : mode === 'think'
                  ? 'bg-purple-500/20 border-purple-500/40 text-purple-300 shadow-sm shadow-purple-500/20'
                  : mode === 'solve'
                  ? 'bg-blue-500/20 border-blue-500/40 text-blue-300 shadow-sm shadow-blue-500/20'
                  : 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300 shadow-sm shadow-emerald-500/20'
              }`}
              aria-label={`Current mode: ${mode}. Tap to change mode`}
              title="Change interaction mode"
            >
              {mode === 'agent' ? (
                <Bot className="w-3 h-3 touch:w-4 touch:h-4 text-brand-accent shrink-0" />
              ) : mode === 'think' ? (
                <Brain className="w-3 h-3 touch:w-4 touch:h-4 text-purple-400 shrink-0" />
              ) : mode === 'solve' ? (
                <Cpu className="w-3 h-3 touch:w-4 touch:h-4 text-blue-400 shrink-0" />
              ) : (
                <MessageSquare className="w-3 h-3 touch:w-4 touch:h-4 text-emerald-400 shrink-0" />
              )}
              <span className="capitalize font-medium text-[10px] touch:text-[11px] tracking-wide hidden xs:inline touch:inline">
                {mode}
              </span>
              <ChevronDown className="w-2.5 h-2.5 text-[#8e95a2] shrink-0" />
            </button>

            {/* Desktop Mode Selector Pill Group */}
            <div className="hidden lg:flex items-center gap-0.5 bg-[#ffffff]/5 p-0.5 rounded-md border border-brand-border/60 shrink-0 select-none">
              {([
                { id: 'think', label: 'Think', icon: Brain, activeClass: 'bg-purple-500/25 text-purple-200 border-purple-500/60 shadow-sm shadow-purple-500/25', inactiveClass: 'text-purple-300/60 hover:text-purple-200 hover:bg-purple-500/10' },
                { id: 'solve', label: 'Solve', icon: Cpu, activeClass: 'bg-blue-500/25 text-blue-200 border-blue-500/60 shadow-sm shadow-blue-500/25', inactiveClass: 'text-blue-300/60 hover:text-blue-200 hover:bg-blue-500/10' },
                { id: 'discuss', label: 'Discuss', icon: MessageSquare, activeClass: 'bg-emerald-500/25 text-emerald-200 border-emerald-500/60 shadow-sm shadow-emerald-500/25', inactiveClass: 'text-emerald-300/60 hover:text-emerald-200 hover:bg-emerald-500/10' },
                { id: 'agent', label: 'Agent', icon: Bot, activeClass: 'bg-brand-accent/30 text-brand-accent border-brand-accent/60 shadow-sm shadow-brand-accent/25', inactiveClass: 'text-brand-accent/70 hover:text-brand-accent hover:bg-brand-accent/10' },
              ] as const).map(({ id, label, icon: Icon, activeClass, inactiveClass }) => {
                const active = mode === id
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => handleModeChange(id)}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded text-[9.5px] font-bold transition-all duration-150 tracking-wider uppercase cursor-pointer border ${
                      active
                        ? activeClass
                        : `border-transparent ${inactiveClass}`
                    }`}
                    title={`Switch to ${label} mode`}
                  >
                    <Icon className="w-3 h-3" />
                    <span>{label}</span>
                  </button>
                )
              })}
            </div>
            {mode === 'agent' && (
              <button
                type="button"
                onClick={mountedFolderName ? handleUnmountFolder : handleMountFolder}
                className={`hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold border transition active:scale-95 cursor-pointer select-none ${
                  mountedFolderName
                    ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300 shadow-sm shadow-cyan-500/20'
                    : 'bg-white/[0.05] border-white/[0.1] text-[#8e95a2] hover:text-white hover:bg-white/[0.08]'
                }`}
                title={mountedFolderName ? `Mounted: ${mountedFolderName}. Click to unmount.` : "Mount local folder via HTML5 File System Access API (Zero setup)"}
              >
                <Folder className="w-3 h-3 text-cyan-400 shrink-0" />
                <span className="truncate max-w-[110px]">
                  {mountedFolderName || 'Mount Folder'}
                </span>
                {mountedFolderName ? (
                  <X className="w-2.5 h-2.5 text-cyan-400/70 hover:text-white ml-0.5" />
                ) : (
                  <FolderPlus className="w-2.5 h-2.5 text-[#8e95a2] ml-0.5" />
                )}
              </button>
            )}
            {mode === 'agent' && (
              <button
                type="button"
                onClick={handleLaunchBridge}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold border transition active:scale-95 cursor-pointer select-none bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
                title="Launch Workstation Bridge on-demand (Pattern A: ochuko://start). Shuts down automatically when idle (Pattern B)."
              >
                <Terminal className="w-3 h-3 text-indigo-400 shrink-0" />
                <span>Bridge</span>
              </button>
            )}
          </div>

          {/* Right Side: Stop/Send Actions */}
          <div className="flex items-center gap-1 shrink-0">
            {isStreaming && (
              <button
                type="button"
                onClick={handleStop}
                className="h-8 w-8 sm:h-7.5 sm:w-7.5 touch:h-11 touch:w-11 bg-brand-surface border border-brand-border text-red-400 rounded-md flex items-center justify-center hover:bg-red-950/15 active:bg-red-950/30 transition active:scale-95 shadow shrink-0 cursor-pointer touch-manipulation"
                aria-label="Stop generation"
              >
                <Square className="w-3 h-3 touch:w-4 touch:h-4 fill-red-400" />
              </button>
            )}

            <button
              type="submit"
              disabled={uploading || (!input.trim() && attachedFiles.length === 0 && pastedSnippets.length === 0)}
              className="h-8 sm:h-7.5 touch:h-11 px-2.5 xs:px-3 touch:px-4 py-1 bg-brand-text text-brand-bg text-[11px] touch:text-xs font-bold rounded-md flex items-center justify-center gap-1 hover:opacity-90 active:opacity-80 transition disabled:opacity-20 active:scale-95 shadow shrink-0 cursor-pointer touch-manipulation"
              aria-label="Send message"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 touch:w-4 touch:h-4 animate-spin shrink-0" />
                  <span className="text-[10px] hidden xs:inline touch:inline">Uploading...</span>
                </>
              ) : (
                <>
                  <span className="hidden xs:inline touch:inline">Send</span>
                  <Send className="w-3.5 h-3.5 touch:w-4 touch:h-4 shrink-0" />
                </>
              )}
            </button>
          </div>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileChange}
          accept=".pdf,.docx,.doc,.pptx,.ppt,.odp,.odt,.rtf,.epub,.tex,.xlsx,.xls,.xlsm,.csv,.tsv,.ods,.parquet,.zip,.tar,.gz,.tgz,.bz2,.tbz2,.xz,.txz,.7z,.rar,.zst,.lzma,.cab,.iso,.dmg,.png,.jpg,.jpeg,.webp,.gif,.svg,.bmp,.tiff,.tif,.ico,.heic,.heif,.avif,.mp3,.wav,.m4a,.ogg,.opus,.oga,.amr,.flac,.aac,.html,.htm,.css,.js,.mjs,.ts,.tsx,.jsx,.vue,.svelte,.py,.ipynb,.java,.c,.cpp,.cc,.h,.hpp,.cs,.rs,.go,.rb,.php,.kt,.swift,.scala,.r,.lua,.dart,.zig,.sol,.wasm,.sh,.bash,.bat,.cmd,.ps1,.sql,.json,.md,.yaml,.yml,.xml,.toml,.ini,.cfg,.properties,.gradle,.env,.dockerfile,.graphql,.gql,.proto,.pb,.diff,.patch,.log,.txt"
          className="hidden"
        />
        {!voice.isRecording && voice.isTranscribing && (
          <div className="input-loading-bar" />
        )}
      </form>

      {/* Mysterious One-Line Micro-Footer - Hidden on mobile */}
      <div className="hide-short-vh hidden sm:block pt-1 pb-0.5 text-center select-none pointer-events-none">
        <p className="text-[10px] font-mono text-brand-muted/30 tracking-[0.2em] uppercase transition-colors duration-300">
          Beyond the prompt lies the pattern.
        </p>
      </div>
    </div>
  )

  return (

    <div
      style={viewportHeight ? { height: `${viewportHeight}px`, maxHeight: `${viewportHeight}px` } : undefined}
      className="flex h-screen h-[100dvh] max-h-[100dvh] bg-brand-bg text-brand-text font-sans antialiased overflow-hidden relative selection:bg-brand-accent/20"
    >

      {/* Left-edge hover zone */}

      <div

        onMouseEnter={() => setIsSidebarHovered(true)}

        className="absolute left-0 top-0 w-3 h-full z-20"

      />

      {/* Backdrop */}

      {(isSidebarOpen || isSidebarHovered) && !isDesktop && (

        <div

          onClick={() => { setIsSidebarOpen(false); setIsSidebarHovered(false) }}

          className="fixed inset-0 bg-black/60 backdrop-blur-[2px] z-30 transition-opacity duration-300"

        />

      )}

      {/* Slide-out Sidebar Drawer */}

      <aside
        onClick={() => {
          // Promote sidebar to pinned open only when user interacts inside it while hovered on desktop
          if (isSidebarHovered && !isSidebarOpen) {
            setIsSidebarOpen(true)
          }
        }}
        onMouseLeave={() => {
          // Keep sidebar open if search input is focused or query is typed
          if (searchInputRef.current && document.activeElement === searchInputRef.current) return
          if (searchQuery && searchQuery.trim().length > 0) return
          setIsSidebarHovered(false)
        }}

        style={{
          width: (isSidebarOpen || isSidebarHovered)
            ? (isDesktop ? `${sidebarWidth}px` : 'min(320px, 100vw)')
            : '256px',
          maxWidth: isDesktop ? undefined : '320px',
        }}

        className={`fixed top-0 left-0 h-[100dvh] max-h-[100dvh] sm:top-3 sm:left-3 sm:h-[calc(100dvh-24px)] bg-[#0d0f11]/98 border-r sm:border border-[#1e2025] rounded-none sm:rounded-lg z-40 flex flex-col justify-between px-4 sm:px-5 pt-[max(1rem,env(safe-area-inset-top,1rem))] pb-[max(1.25rem,env(safe-area-inset-bottom,1.25rem))] sm:py-6 backdrop-blur-xl shadow-2xl shadow-black/80 ${
          isDraggingSidebar ? 'transition-none' : 'transition-all duration-300 ease-out'
        } overflow-y-auto overflow-x-hidden custom-scrollbar ${
          isSidebarOpen || isSidebarHovered ? 'translate-x-0 opacity-100 pointer-events-auto' : '-translate-x-[calc(100%+24px)] opacity-0 pointer-events-none'
        }`}
      >

        {/* ── 1. Top Section (Pinned Header, New Session, Search) ─────── */}
        <div className="shrink-0">

          <div className="flex items-center justify-between gap-3 mb-4 pb-4 border-b border-[#1e2025]">

            <div className="flex items-center gap-3 min-w-0">

              <div className="w-9 h-9 rounded-lg overflow-hidden border border-[#ffffff]/15 bg-brand-bg shrink-0">

                <img src="/favicon.png" alt="Ochuko" className="w-full h-full object-cover" />

              </div>

              <div className="min-w-0">

                <p className="font-semibold text-[13px] text-brand-text tracking-tight truncate">Agent Ochuko</p>

              </div>

            </div>

            {/* Close Button (X) */}
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setIsSidebarOpen(false)
                setIsSidebarHovered(false)
              }}
              className="min-h-[44px] min-w-[44px] -mr-1 flex items-center justify-center rounded-lg text-[#8e95a2] hover:text-white hover:bg-white/10 active:bg-white/15 transition-colors cursor-pointer touch-manipulation relative z-20"
              aria-label="Close navigation sidebar"
              title="Close Sidebar"
            >
              <X className="w-5 h-5 pointer-events-none" />
            </button>

          </div>

          <button

            type="button"

            onClick={() => handleNewSession()}

            className="w-full h-11 min-h-[44px] border border-brand-border bg-brand-card hover:bg-[#2e2e2c] active:bg-[#383835] text-brand-text hover:border-[#ffffff]/30 transition duration-150 rounded-lg text-xs font-semibold flex items-center justify-center tracking-wide mb-3 shadow-sm"

          >

            New Session

          </button>

          {/* Search Input */}

          <div className="relative mb-1">

            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8e95a2]/50 pointer-events-none">

              <Search className="w-4 h-4" />

            </span>

            <input

              ref={searchInputRef}

              type="text"

              value={searchQuery}

              onFocus={() => {
                setIsSidebarOpen(true)
              }}

              onChange={(e) => {
                setIsSidebarOpen(true)
                setSearchQuery(e.target.value)
              }}

              placeholder="Search chats (Ctrl+K)..."

              className="w-full h-11 min-h-[44px] bg-white/[0.03] focus:bg-white/[0.05] border border-white/[0.08] focus:border-white/20 rounded-lg pl-9 pr-9 text-base sm:text-xs text-[#f3f4f6] placeholder-[#8e95a2]/50 focus:outline-none transition"

            />

            {searchQuery && (

              <button

                type="button"

                onClick={() => setSearchQuery('')}

                className="absolute right-2 top-1/2 -translate-y-1/2 min-h-[36px] min-w-[36px] flex items-center justify-center text-[#8e95a2]/70 hover:text-white"

                aria-label="Clear search"

              >

                <X className="w-4 h-4" />

              </button>

            )}

          </div>

        </div>

        {/* ── 2. Independent Scrollable Conversation History Container ─── */}

        <div className="flex-1 min-h-0 overflow-y-auto pr-1 my-2 custom-scrollbar">

          {searchResults !== null ? (

            searchResults.length === 0 ? (

              <p className="text-[10px] text-[#8e95a2]/40 italic pl-1 py-2">No results found</p>

            ) : (

              <div className="space-y-1">

                <p className="text-[9px] font-bold tracking-widest text-[#8e95a2]/40 uppercase mb-1.5 px-1">

                  Search Results

                </p>

                {searchResults.map((convo) => {

                  const active = convo.id === activeConversationId

                  return (

                    <div key={convo.id} className="group relative flex items-center w-full min-h-[44px]">

                      {renamingConvoId === convo.id ? (

                        <input

                          ref={renameInputRef}

                          value={renameValue}

                          onChange={e => setRenameValue(e.target.value)}

                          onBlur={handleRenameCommit}

                          onKeyDown={handleRenameKeyDown}

                          className="flex-1 min-h-[40px] px-3 py-2 rounded-lg text-xs font-medium bg-[#ffffff]/10 border border-[#ffffff]/40 text-brand-text outline-none pr-8"

                          maxLength={80}

                          placeholder="Conversation title…"

                        />

                      ) : (

                        <button

                          type="button"

                          onClick={() => {

                            handleSelectConversation(convo.id, convo.mode)

                            setSearchQuery('')

                          }}

                          onDoubleClick={e => {

                            e.stopPropagation()

                            setRenamingConvoId(convo.id)

                            setRenameValue(convo.title || '')

                          }}

                          title="Double-click to rename"

                          className={`flex-1 text-left min-h-[44px] py-2.5 px-3 rounded-lg text-xs font-medium transition duration-150 flex items-center pr-14 ${

                            active

                              ? 'bg-[#ffffff]/10 text-brand-text border border-[#ffffff]/20'

                              : 'text-[#8e95a2] hover:text-brand-text hover:bg-white/5 border border-transparent'

                          }`}

                        >

                          <span className="truncate block w-full">

                            {convo.title || 'Untitled Session'}

                          </span>

                        </button>

                      )}

                      {renamingConvoId !== convo.id && (

                        <>

                          <button

                            type="button"

                            onClick={e => {

                              e.stopPropagation()

                              setRenamingConvoId(convo.id)

                              setRenameValue(convo.title || '')

                            }}

                            className="absolute right-8 opacity-70 sm:opacity-0 group-hover:opacity-100 min-h-[36px] min-w-[36px] flex items-center justify-center text-[#8e95a2]/50 hover:text-brand-accent transition duration-150 rounded hover:bg-white/5"

                            title="Rename"

                          >

                            <Pencil className="w-3.5 h-3.5" />

                          </button>

                          <button

                            type="button"

                            onClick={e => {

                              e.stopPropagation()

                              setConvoToDelete(convo.id)

                            }}

                            className="absolute right-1 opacity-70 sm:opacity-0 group-hover:opacity-100 min-h-[36px] min-w-[36px] flex items-center justify-center text-[#8e95a2] hover:text-red-400 transition duration-150 rounded hover:bg-white/5"

                            title="Delete Session"

                          >

                            <Trash className="w-3.5 h-3.5" />

                          </button>

                        </>

                      )}

                    </div>

                  )

                })}

              </div>

            )

          ) : conversations.length === 0 ? (

            <p className="text-[10px] text-[#8e95a2]/40 italic pl-1 py-2">No past sessions</p>

          ) : (() => {

            const startOfToday = new Date(); startOfToday.setHours(0,0,0,0)

            const startOfYesterday = new Date(startOfToday); startOfYesterday.setDate(startOfYesterday.getDate() - 1)

            const startOfWeek = new Date(startOfToday); startOfWeek.setDate(startOfWeek.getDate() - 7)

            const groups: { label: string; items: any[] }[] = [

              { label: 'Today', items: [] },

              { label: 'Yesterday', items: [] },

              { label: 'This Week', items: [] },

              { label: 'Older', items: [] },

            ]

            for (const convo of conversations) {

              const ts = convo.created_at ? new Date(convo.created_at).getTime() : 0

              if (ts >= startOfToday.getTime()) groups[0].items.push(convo)

              else if (ts >= startOfYesterday.getTime()) groups[1].items.push(convo)

              else if (ts >= startOfWeek.getTime()) groups[2].items.push(convo)

              else groups[3].items.push(convo)

            }

            return groups.filter(g => g.items.length > 0).map(group => (

              <div key={group.label} className="mb-3.5">

                <p className="text-[9px] font-bold tracking-widest text-[#8e95a2]/70 uppercase mb-1.5 px-2">

                  {group.label}

                </p>

                <div className="space-y-1">

                  {group.items.map((convo) => {

                    const active = convo.id === activeConversationId

                    return (

                      <div key={convo.id} className="group relative flex items-center w-full min-h-[44px]">

                        {renamingConvoId === convo.id ? (

                          // Rename mode — inline input

                          <input

                            ref={renameInputRef}

                            value={renameValue}

                            onChange={e => setRenameValue(e.target.value)}

                            onBlur={handleRenameCommit}

                            onKeyDown={handleRenameKeyDown}

                            className="flex-1 min-h-[40px] px-3 py-2 rounded-lg text-xs font-medium bg-[#ffffff]/10 border border-[#ffffff]/40 text-brand-text outline-none pr-8"

                            maxLength={80}

                            placeholder="Conversation title…"

                          />

                        ) : (

                          <button

                            type="button"

                            onClick={() => {
                              handleSelectConversation(convo.id, convo.mode)
                            }}

                            onDoubleClick={e => {

                              e.stopPropagation()

                              setRenamingConvoId(convo.id)

                              setRenameValue(convo.title || '')

                            }}

                            title="Double-click to rename"

                            className={`flex-1 text-left min-h-[44px] py-2.5 px-3 rounded-lg text-[11.5px] font-medium transition duration-150 flex items-center pr-14 ${

                              active

                                ? 'bg-white/[0.08] text-white border-l-2 border-white/50 rounded-l-none pl-2.5'

                                : 'text-[#b0b7c3] hover:text-white hover:bg-white/[0.04] border-0'

                            }`}

                          >

                            <span className="truncate block w-full">

                              {convo.title || 'Untitled Session'}

                            </span>

                          </button>

                        )}

                        {renamingConvoId !== convo.id && (

                          <>

                            <button

                              type="button"

                              onClick={e => {

                                e.stopPropagation()

                                setRenamingConvoId(convo.id)

                                setRenameValue(convo.title || '')

                              }}

                              className="absolute right-8 opacity-70 sm:opacity-0 group-hover:opacity-100 min-h-[36px] min-w-[36px] flex items-center justify-center text-[#8e95a2]/50 hover:text-brand-accent transition duration-150 rounded hover:bg-white/5"

                              title="Rename"

                            >

                              <Pencil className="w-3.5 h-3.5" />

                            </button>

                            <button

                              type="button"

                              onClick={e => {

                                e.stopPropagation()

                                setConvoToDelete(convo.id)

                              }}

                              className="absolute right-1 opacity-70 sm:opacity-0 group-hover:opacity-100 min-h-[36px] min-w-[36px] flex items-center justify-center text-[#8e95a2] hover:text-red-400 transition duration-150 rounded hover:bg-white/5"

                              title="Delete Session"

                            >

                              <Trash className="w-3.5 h-3.5" />

                            </button>

                          </>

                        )}

                      </div>

                    )

                  })}

                </div>

              </div>

            ))

          })()}

        </div>

        {/* ── 3. Fixed Bottom Section (Profile & Account Actions) ─────── */}

        <div className="shrink-0 border-t border-[#1e2025] pt-3 pb-1 space-y-2 select-none">

          {/* User Profile & Integrated Sign Out */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-full overflow-hidden border border-[#1e2025] bg-brand-bg shrink-0">
                <img src="/favicon.png" alt="User" className="w-full h-full object-cover" />
              </div>
              <div className="truncate">
                <p className="text-[11px] text-brand-text font-bold truncate">{preferredName}</p>
                <p className="text-[9.5px] text-brand-muted truncate mt-0.5">{userEmail}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleSignOut}
              title="Sign Out"
              className="p-2 min-h-[36px] min-w-[36px] text-red-400/70 hover:text-red-300 hover:bg-red-950/20 rounded-lg transition border border-transparent hover:border-red-900/30 shrink-0 flex items-center justify-center cursor-pointer"
              aria-label="Sign Out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>

          {/* App Lock / PIN Row */}
          {localStorage.getItem('app_lock_pin') ? (
            <div className="flex gap-1.5 w-full">
              <button
                type="button"
                onClick={() => setIsLocked(true)}
                className="flex-1 min-h-[34px] text-[#ffffff] hover:text-[#ffffff] hover:bg-[#ffffff]/10 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1.5 border border-[#ffffff]/20 hover:border-[#ffffff]/40 cursor-pointer"
                title="Lock App"
              >
                <Lock className="w-3 h-3" />
                <span>Lock App</span>
              </button>
              <button
                type="button"
                onClick={() => setLockMode('change')}
                className="min-h-[34px] px-2 text-brand-muted hover:text-brand-text hover:bg-white/5 transition duration-150 rounded-lg text-[10px] font-semibold border border-[#1e2025] cursor-pointer"
                title="Change PIN"
              >
                Change
              </button>
              <button
                type="button"
                onClick={() => setLockMode('disable')}
                className="min-h-[34px] px-2 text-red-400/50 hover:text-red-400 hover:bg-red-950/10 transition duration-150 rounded-lg text-[10px] font-semibold border border-transparent hover:border-red-950/20 cursor-pointer"
                title="Disable PIN"
              >
                Disable
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setLockMode('setup')}
              className="w-full min-h-[34px] text-brand-muted hover:text-brand-text hover:bg-white/5 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-2 px-3 border border-[#1e2025] hover:border-white/10 cursor-pointer"
            >
              <Lock className="w-3 h-3" />
              <span>Setup PIN Lock</span>
            </button>
          )}

          {/* Capabilities & Zoom Controls 2-Column Grid */}
          <div className="grid grid-cols-2 gap-1.5 w-full">
            <button
              type="button"
              onClick={() => {
                if (window.innerWidth < 768) {
                  setIsSidebarOpen(false)
                  setIsSidebarHovered(false)
                }
                navigate('/capabilities')
              }}
              className="w-full min-h-[34px] text-brand-text hover:text-white hover:bg-white/10 transition duration-150 rounded-lg text-[10.5px] font-semibold flex items-center justify-center gap-1.5 px-2 border border-[#ffffff]/25 hover:border-[#ffffff]/45 cursor-pointer"
              title="View Agent Capabilities"
            >
              <Cpu className="w-3.5 h-3.5 shrink-0 text-brand-accent" />
              <span className="truncate">Capabilities</span>
            </button>

            {/* Compact Zoom Controls (Desktop only) */}
            {isDesktop && (
              <div className="flex items-center justify-between px-1 bg-white/[0.03] rounded-lg border border-white/10 min-h-[34px]">
                <button
                  type="button"
                  onClick={() => setPageZoom(prev => Math.max(0.5, prev - 0.1))}
                  className="w-7 h-7 flex items-center justify-center text-brand-muted hover:text-white hover:bg-white/10 rounded transition cursor-pointer"
                  title="Zoom out"
                  aria-label="Zoom out"
                >
                  <Minus className="w-3 h-3" />
                </button>
                <span className="text-[10px] text-brand-text font-mono select-none">{Math.round(pageZoom * 100)}%</span>
                <button
                  type="button"
                  onClick={() => setPageZoom(prev => Math.min(1.5, prev + 0.1))}
                  className="w-7 h-7 flex items-center justify-center text-brand-muted hover:text-white hover:bg-white/10 rounded transition cursor-pointer"
                  title="Zoom in"
                  aria-label="Zoom in"
                >
                  <Plus className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>

          {/* Resizing Handle */}
          {isDesktop && (isSidebarOpen || isSidebarHovered) && (
            <div
              onMouseDown={startResizing}
              className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-[#ffffff]/30 active:bg-[#ffffff]/50 transition z-50"
            />
          )}

        </div>

      </aside>

      {/* Chat Workspace */}

      <main
        className={`flex-1 flex flex-col relative bg-brand-bg overflow-hidden z-10 min-w-0 ${
          isDraggingSidebar ? 'transition-none' : 'transition-all duration-300 ease-out'
        }`}
        style={{
          marginLeft: isDesktop && isSidebarOpen ? `${sidebarWidth + 24}px` : '0px',
          width: isDesktop && isSidebarOpen ? `calc(100% - ${sidebarWidth + 24}px)` : '100%',
          maxWidth: isDesktop && isSidebarOpen ? `calc(100% - ${sidebarWidth + 24}px)` : '100%',
        }}
      >

        {/* Header */}

        {/* Floating Top Navigation - Seamless, borderless, and optimized for mobile touch */}

        <header className="relative z-30 h-[calc(3.25rem+env(safe-area-inset-top,0px))] sm:h-14 bg-transparent flex items-center justify-between px-2 sm:px-4 pt-[env(safe-area-inset-top,0px)] shrink-0 select-none">

          <div className="flex items-center gap-1 sm:gap-2 min-w-0">
            {/* Floating Menu Icon Button */}
            <button
              onClick={() => {
                setIsSidebarOpen((prev) => !prev)
                setIsSidebarHovered(false)
              }}
              className="min-h-[44px] min-w-[44px] w-11 h-11 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl text-white/75 hover:text-white hover:bg-white/[0.08] active:bg-white/[0.14] transition duration-150 active:scale-95 cursor-pointer shrink-0 touch-manipulation"
              aria-label="Toggle Sidebar"
            >
              <Menu className="w-5 h-5 sm:w-4 sm:h-4" />
            </button>

            {isFetchingHistory && (
              <span className="flex items-center gap-1.5 text-[10px] text-brand-muted animate-pulse ml-1">
                <Loader2 className="w-3 h-3 animate-spin text-[#ffffff]" />
                <span className="hidden sm:inline">Syncing...</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-0.5 sm:gap-1.5">
            {/* Floating Share Button */}
            {activeConversationId && activeConversationId !== '00000000-0000-0000-0000-000000000000' ? (
              <button
                onClick={() => setIsShareModalOpen(true)}
                className="min-h-[44px] min-w-[44px] w-11 h-11 sm:w-auto sm:min-h-[34px] sm:h-9 sm:px-2.5 flex items-center justify-center rounded-xl text-white/75 hover:text-white hover:bg-white/[0.08] active:bg-white/[0.14] text-[11px] font-semibold transition duration-150 active:scale-95 cursor-pointer shrink-0 touch-manipulation"
                title="Share Conversation"
              >
                <Share2 className="w-5 h-5 sm:w-4 sm:h-4" />
                <span className="hidden sm:inline sm:ml-1.5">Share</span>
              </button>
            ) : (
              <button
                disabled
                className="min-h-[44px] min-w-[44px] w-11 h-11 sm:w-auto sm:min-h-[34px] sm:h-9 sm:px-2.5 flex items-center justify-center rounded-xl text-white/20 cursor-not-allowed select-none shrink-0 touch-manipulation"
                title="Send a message first to share"
              >
                <Share2 className="w-5 h-5 sm:w-4 sm:h-4 opacity-40" />
                <span className="hidden sm:inline sm:ml-1.5 text-[11px] font-semibold">Share</span>
              </button>
            )}


            {/* Floating Settings Button */}
            <div ref={headerSettingsRef} className="relative">
              <button
                onClick={() => setIsHeaderSettingsOpen(o => !o)}
                className="min-h-[44px] min-w-[44px] w-11 h-11 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl text-white/75 hover:text-white hover:bg-white/[0.08] active:bg-white/[0.14] transition duration-150 active:scale-95 cursor-pointer shrink-0 touch-manipulation"
                title="Settings & security"
              >
                <Settings className="w-5 h-5 sm:w-4 sm:h-4" />
              </button>
              {isHeaderSettingsOpen && (
                <div className="absolute right-0 mt-1.5 w-60 sm:w-56 max-h-[calc(100dvh-70px)] sm:max-h-[calc(100vh-80px)] overflow-y-auto rounded-xl border border-brand-border bg-brand-card/95 backdrop-blur-md shadow-2xl z-50 py-1.5 select-none touch-manipulation">
                  {mode === 'agent' && (
                    <>
                      <div
                        role="switch"
                        aria-checked={isWorkstationAccessEnabled}
                        aria-label="Toggle Workstation Access"
                        onClick={() => {
                          const val = !isWorkstationAccessEnabled
                          setIsWorkstationAccessEnabled(val)
                          localStorage.setItem('ochuko_workstation_access_enabled', val ? 'true' : 'false')
                          window.dispatchEvent(new Event('ochuko_workstation_access_changed'))
                          showToast(val ? 'Workstation Access enabled (Agent Mode)' : 'Workstation Access disabled', 'info')
                        }}
                        className="px-3.5 py-3 sm:py-2.5 min-h-[48px] sm:min-h-[40px] flex items-center justify-between gap-3 cursor-pointer hover:bg-white/5 active:bg-white/10 transition-colors select-none"
                      >
                        <div className="flex flex-col min-w-0 pointer-events-none">
                          <span className="text-brand-text text-xs sm:text-[11px] font-semibold flex items-center gap-1.5 truncate">
                            <Cpu className="w-3.5 h-3.5 text-cyan-400 shrink-0" /> Workstation Access
                          </span>
                          <span className="text-[10px] sm:text-[9.5px] text-cyan-400/80 font-medium pl-5">Direct PC File Access</span>
                        </div>
                        <div
                          className={`relative inline-flex h-6 w-11 sm:h-5 sm:w-9 shrink-0 items-center rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out pointer-events-none ${
                            isWorkstationAccessEnabled ? 'bg-cyan-500 shadow-sm shadow-cyan-500/30' : 'bg-white/[0.15]'
                          }`}
                        >
                          <span
                            className={`pointer-events-none inline-block h-5 w-5 sm:h-4 sm:w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                              isWorkstationAccessEnabled ? 'translate-x-5 sm:translate-x-4' : 'translate-x-0'
                            }`}
                          />
                        </div>
                      </div>
                      <div className="border-t border-[#1e2025]/50 my-1" />
                    </>
                  )}
                  {localStorage.getItem('app_lock_pin') ? (
                    <>
                      <button
                        onClick={() => {
                          setIsLocked(true)
                          setIsHeaderSettingsOpen(false)
                        }}
                        className="w-full text-left px-4 py-3 sm:py-2.5 min-h-[44px] text-xs sm:text-[11px] text-brand-text hover:bg-white/5 active:bg-white/10 transition flex items-center gap-2 font-semibold"
                      >
                        <Lock className="w-4 h-4 sm:w-3.5 sm:h-3.5 text-brand-muted shrink-0" />
                        <span>Lock App</span>
                      </button>
                      <button
                        onClick={() => {
                          setLockMode('change')
                          setIsHeaderSettingsOpen(false)
                        }}
                        className="w-full text-left px-4 py-3 sm:py-2.5 min-h-[44px] text-xs sm:text-[11px] text-brand-muted hover:text-brand-text hover:bg-white/5 active:bg-white/10 transition flex items-center gap-2 font-semibold border-t border-[#1e2025]/50"
                      >
                        <KeyRound className="w-4 h-4 sm:w-3.5 sm:h-3.5 text-brand-muted shrink-0" />
                        <span>Change PIN</span>
                      </button>
                      <button
                        onClick={() => {
                          setLockMode('disable')
                          setIsHeaderSettingsOpen(false)
                        }}
                        className="w-full text-left px-4 py-3 sm:py-2.5 min-h-[44px] text-xs sm:text-[11px] text-red-400/70 hover:text-red-400 hover:bg-red-950/10 active:bg-red-950/20 transition flex items-center gap-2 font-semibold border-t border-[#1e2025]/50"
                      >
                        <Unlock className="w-4 h-4 sm:w-3.5 sm:h-3.5 text-red-400/50 shrink-0" />
                        <span>Disable PIN</span>
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => {
                        setLockMode('setup')
                        setIsHeaderSettingsOpen(false)
                      }}
                      className="w-full text-left px-4 py-3 sm:py-2.5 min-h-[44px] text-xs sm:text-[11px] text-brand-text hover:bg-white/5 active:bg-white/10 transition flex items-center gap-2 font-semibold"
                    >
                      <Lock className="w-4 h-4 sm:w-3.5 sm:h-3.5 text-brand-muted shrink-0" />
                      <span>Setup PIN Lock</span>
                    </button>
                  )}
                  <button
                    onClick={() => {
                      handleSignOut()
                      setIsHeaderSettingsOpen(false)
                    }}
                    className="w-full text-left px-4 py-3 sm:py-2.5 min-h-[44px] text-xs sm:text-[11px] text-red-400/75 hover:text-red-450 hover:bg-red-950/15 active:bg-red-950/25 transition flex items-center gap-2 font-semibold border-t border-[#1e2025]"
                  >
                    <LogOut className="w-4 h-4 sm:w-3.5 sm:h-3.5 shrink-0" />
                    <span>Terminate Session</span>
                  </button>
                </div>
              )}
            </div>
          </div>

        </header>

        {!isOnline && (

          <div className="bg-red-500/10 border-b border-red-500/20 text-red-300 px-5 py-2.5 text-[11px] font-semibold flex items-center justify-center gap-2 select-none shadow-md shrink-0">

            <Globe className="w-3.5 h-3.5 animate-pulse" />

            <span>You are currently offline. Some features may be unavailable.</span>

          </div>

        )}

        <div className="flex-1 flex overflow-hidden min-w-0">

          <div className="flex-1 flex flex-col min-w-0 relative">

            <div
              ref={scrollContainerRef}
              onScroll={handleScroll}
              className="flex-1 min-h-0 overflow-y-auto overscroll-contain overflow-x-hidden pt-3 sm:pt-6 pb-4 px-2.5 sm:px-5 md:px-8 relative z-10"
            >

          {isFetchingHistory && messages.length === 0 ? (

            <ChatSkeleton />

          ) : messages.length === 0 ? (

            <div className="min-h-full flex flex-col items-center justify-center max-w-2xl mx-auto px-2 sm:px-4 w-full py-4 sm:py-10 my-auto">

              <div className="flex flex-col items-center text-center space-y-3 sm:space-y-4 mb-4 sm:mb-8 short-tight">

                <div className="hide-short-vh w-12 h-12 sm:w-16 sm:h-16 bg-brand-surface border border-[#1e2025] rounded-2xl overflow-hidden shadow-xl relative group">

                  <div className="absolute inset-0 bg-[#ffffff]/4 opacity-0 group-hover:opacity-100 transition duration-500" />

                  <img

                    src="/favicon.png"

                    alt="Agent Ochuko"

                    className="w-full h-full object-cover transition duration-500 group-hover:scale-105"

                    fetchPriority="high"

                  />

                </div>

                <div className="space-y-1.5 sm:space-y-2">

                  <div className="flex items-center gap-2 justify-center">
                    <h2 className="text-xl sm:text-3xl short-shrink-greeting font-bold tracking-tight text-brand-text">{dynamicGreeting}</h2>
                  </div>

                  {isEditingNickname && (
                    <div className="flex items-center gap-2 justify-center pt-1">
                      <input
                        ref={renameInputRef}
                        type="text"
                        value={nicknameInput}
                        onChange={(e) => setNicknameInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            setPreferredName(nicknameInput.trim())
                            setIsEditingNickname(false)
                          } else if (e.key === 'Escape') {
                            setIsEditingNickname(false)
                          }
                        }}
                        className="bg-[#1e2025] border border-[#ffffff]/20 rounded-lg px-2.5 py-1 text-sm text-brand-text focus:outline-none focus:border-brand-accent w-36"
                        placeholder="Enter nickname"
                        autoFocus
                      />
                      <button
                        onClick={() => {
                          setPreferredName(nicknameInput.trim())
                          setIsEditingNickname(false)
                        }}
                        className="p-1.5 rounded-lg bg-brand-accent/20 hover:bg-brand-accent/30 text-brand-accent transition"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setIsEditingNickname(false)}
                        className="p-1.5 rounded-lg hover:bg-white/10 text-brand-muted transition"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                </div>

              </div>

              {/* Centered Input Console in New Chat */}
              <div className="w-full">
                {renderInputConsole(true)}
              </div>

            </div>

          ) : (

            <div className="max-w-none sm:max-w-3xl mx-auto space-y-4 sm:space-y-5 px-1 sm:px-2">

              {(() => {
                const getArchivedForMarker = (index: number) => {
                  const sliceStart = messages.slice(0, index).reduce((acc, m, idx) => {
                    if (m.isCompactionMarker) return idx + 1;
                    return acc;
                  }, 0);
                  return messages.slice(sliceStart, index).filter(m => m.isArchived);
                };

                return messages.map((msg, i) => {
                  if (msg.isArchived) return null;

                  return (
                    <LazyMessage key={i} estimatedHeight={msg.content.length > 400 ? 200 : 80} turnIndex={i}>

                      {/* ── Compaction Marker Banner ─────────────────────────────────── */}
                      {msg.isCompactionMarker ? (
                        <div className="my-2">
                          <div className="flex items-start gap-3 py-3 px-4 rounded-lg bg-[#1a1d22] border border-[#2e3542] text-xs text-brand-muted select-none">
                            <svg className="w-4 h-4 mt-0.5 shrink-0 text-brand-accent/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h12A2.25 2.25 0 0120.25 6v12A2.25 2.25 0 0118 20.25H6A2.25 2.25 0 013.75 18V6z" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 9h7.5M8.25 12h5.25" />
                            </svg>
                            <div className="flex-1 min-w-0 space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-brand-text/70 tracking-wide uppercase text-[10px]">Context summarised</span>
                                {(() => {
                                  const archived = getArchivedForMarker(i);
                                  const hasDetails = archived.length > 0 || !!msg.compactionSummary;
                                  if (!hasDetails) return null;
                                  const isExpanded = expandedCompactionIndices.has(i);
                                  return (
                                    <button
                                      onClick={() => {
                                        setExpandedCompactionIndices(prev => {
                                          const next = new Set(prev);
                                          if (next.has(i)) next.delete(i);
                                          else next.add(i);
                                          return next;
                                        });
                                      }}
                                      className="flex items-center gap-0.5 text-brand-accent hover:underline text-[10px] font-medium transition cursor-pointer select-none"
                                    >
                                      {isExpanded ? (
                                        <>
                                          <span>Hide details</span>
                                          <ChevronUp className="w-3 h-3" />
                                        </>
                                      ) : (
                                        <>
                                          <span>Show {archived.length > 0 ? `${archived.length} messages` : 'details'}</span>
                                          <ChevronDown className="w-3 h-3" />
                                        </>
                                      )}
                                    </button>
                                  );
                                })()}
                              </div>
                              <p className="text-brand-muted/60 italic">
                                {msg.compactionSummary
                                  ? 'Earlier messages were summarized to free context space. Use "Show details" below to read the summary.'
                                  : 'Older messages were condensed to save context space. The full detail is preserved in your conversation history.'}
                              </p>
                            </div>
                          </div>

                          {/* Collapsible Details */}
                          {(() => {
                            const archived = getArchivedForMarker(i);
                            const isExpanded = expandedCompactionIndices.has(i);
                            if (!isExpanded || (archived.length === 0 && !msg.compactionSummary)) return null;
                            return (
                              <div className="mt-3 pl-4 border-l border-[#2e3542] space-y-4">
                                {msg.compactionSummary && (
                                  <div className="text-xs text-brand-muted/80 leading-relaxed whitespace-pre-wrap">
                                    <div className="text-[9px] text-brand-muted/50 font-medium uppercase tracking-wide mb-1 select-none">Summary</div>
                                    {msg.compactionSummary}
                                  </div>
                                )}
                                {archived.map((archivedMsg, archIdx) => (
                                  <div key={`arch-${archIdx}`} className="opacity-90">
                                    <div className={`flex w-full gap-3 ${archivedMsg.role === 'user' ? 'justify-end' : 'justify-start'} text-xs`}>
                                      {archivedMsg.role !== 'user' && (
                                        <div className="w-5 h-5 rounded bg-brand-surface/20 flex items-center justify-center shrink-0 overflow-hidden mt-0.5 select-none border border-white/10">
                                          <img src="/favicon.png" alt="Ochuko" className="w-full h-full object-cover" />
                                        </div>
                                      )}
                                      <div className={`flex flex-col gap-1 ${archivedMsg.role === 'user' ? 'max-w-[80%] items-end' : 'flex-1 min-w-0'}`}>
                                        <div className="text-[9px] text-brand-muted/50 font-medium select-none">
                                          {archivedMsg.role === 'user' ? 'You' : 'Agent Ochuko'}
                                        </div>
                                        <div className={`rounded-lg px-3 py-2 text-brand-text/90 ${archivedMsg.role === 'user' ? 'bg-[#0d0f11]/95 backdrop-blur-sm border border-[#1e2025] rounded-tr-sm' : 'bg-[#1a1d22]/30 border border-[#2e3542]/50 rounded-tl-sm'}`}>
                                          {archivedMsg.thinkingContent && (
                                            <div className="mb-2 text-[10px] text-brand-muted/70 italic border-l border-[#2e3542] pl-2 py-0.5 select-none">
                                              {archivedMsg.thinkingContent}
                                            </div>
                                          )}
                                          <p className="whitespace-pre-wrap leading-relaxed">{archivedMsg.content}</p>
                                          {Array.isArray(archivedMsg.generatedFiles) && archivedMsg.generatedFiles.length > 0 && (
                                            <div className="mt-2 space-y-1">
                                              {archivedMsg.generatedFiles.map((f, fIdx) => (
                                                <div key={fIdx} className="flex items-center gap-1.5 text-[10px] text-brand-accent/80">
                                                  <FileText className="w-3 h-3" />
                                                  <span>{f.filename}</span>
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            );
                          })()}
                        </div>
                      ) : (

                  <div

                    className={`group relative flex w-full gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}

                  >

                  {/* Avatar only for assistant */}

                  {msg.role !== 'user' && (

                    <div className="hidden sm:flex w-6 h-6 rounded-md border border-white/10 bg-brand-surface/40 items-center justify-center shrink-0 overflow-hidden mt-1 select-none">

                      <img

                        src="/favicon.png"

                        alt="Ochuko"

                        className="w-full h-full object-cover"

                      />

                    </div>

                  )}

                  {/* Right/Left side container: Bubble + Actions */}

                  <div className={`flex flex-col gap-1.5 ${msg.role === 'user' ? 'max-w-[85%] sm:max-w-[80%] items-end' : 'flex-1 min-w-0 w-full max-w-full sm:max-w-[820px]'}`}>

                    {/* Bubble */}

                    <div

                      className={`relative rounded-lg min-w-0 ${

                        msg.role === 'user'

                          ? 'bg-[#0d0f11]/95 backdrop-blur-sm border border-[#1e2025] text-brand-text rounded-tr-sm px-3.5 py-2.5 shadow-sm'

                          : 'bg-transparent border-transparent py-0.5'

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

                              className="w-full bg-[#0d0f11] border border-[#1a1d20] focus:border-[#ffffff]/40 rounded-lg p-3 text-[13.5px] text-brand-text focus:outline-none resize-none font-sans"

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

                                className="px-3 py-1.5 bg-[#ffffff] text-[#1a1a18] hover:bg-[#e9e8e6] rounded-lg text-[11px] font-bold transition duration-150 shadow-md shadow-[#ffffff]/5"

                              >

                                Save & Submit

                              </button>

                            </div>

                          </div>

                        ) : (msg.fileAttachment || (msg.fileAttachments && msg.fileAttachments.length > 0)) ? (

                          /* Agent job — file chip(s) stacked above the prompt text */

                          <div className="flex flex-col items-end gap-2">

                            {/* File thumbnails / chips */}
                            <div className="flex flex-col items-end gap-1.5">

                              {msg.fileAttachment && (

                                <FileAttachmentChip attachment={msg.fileAttachment} />

                              )}

                              {Array.isArray(msg.fileAttachments) && msg.fileAttachments.map((attachment, idx) => (

                                <FileAttachmentChip key={idx} attachment={attachment} />

                              ))}

                            </div>

                            {/* Always show user's prompt text below the file(s), unless it is a default analyse message */}
                            {(() => {
                              const stripped = msg.content.replace(/^(Please (analyze|analyse) and describe (this|these) attached files?: [^\n]+)/i, '').trim()
                              if (!stripped) return null
                              return (
                                <p className="text-[16px] sm:text-[14.5px] text-[#f4f4f5] leading-[1.65] font-normal whitespace-pre-wrap font-sans">
                                  {stripped}
                                </p>
                              )
                            })()}

                          </div>

                        ) : (

                          (() => {

                            const parsed = parsePastedText(msg.content)

                            if (parsed.hasPastedText) {
                              return (
                                <div className="space-y-2">
                                  {parsed.textPrefix && (
                                    <p className="text-[16px] sm:text-[14.5px] text-[#f4f4f5] leading-[1.65] font-normal whitespace-pre-wrap font-sans">
                                      {parsed.textPrefix}
                                    </p>
                                  )}

                                  {parsed.pastedItems.map((item, idx) => {
                                    const itemKey = `${i}-${idx}`
                                    const isExpanded = !!expandedPastedMessages[itemKey] || (idx === 0 && !!expandedPastedMessages[i])
                                    const isCopied = copiedPastedKey === itemKey || (idx === 0 && copiedPastedKey === i)

                                    return (
                                      <div key={idx} className="space-y-2">
                                        <div
                                          onClick={() => setExpandedPastedMessages(prev => ({ ...prev, [itemKey]: !isExpanded }))}
                                          className="flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-lg bg-[#ffffff]/8 border border-[#ffffff]/20 cursor-pointer hover:bg-[#ffffff]/15 transition-all duration-150 select-none max-w-sm"
                                        >
                                          <div className="flex items-center gap-2 min-w-0">
                                            <FileText className="w-4 h-4 text-[#ffffff] shrink-0" />
                                            <div className="min-w-0">
                                              <p className="text-[11px] font-bold text-[#ffffff] uppercase tracking-widest leading-none mb-1">
                                                Pasted Content{parsed.pastedItems.length > 1 ? ` #${idx + 1}` : ''}
                                              </p>
                                              <p className="text-[12px] text-brand-text/90 font-medium truncate">
                                                {item.name}
                                              </p>
                                            </div>
                                          </div>
                                          <div className="text-[#8e95a2] hover:text-[#ffffff] shrink-0">
                                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                          </div>
                                        </div>

                                        {isExpanded && (
                                          <div className="bg-[#0d0f11] border border-[#1e2025] rounded-lg p-3 relative group/panel">
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation()
                                                navigator.clipboard.writeText(item.content || '').catch(() => {})
                                                setCopiedPastedKey(itemKey)
                                                setTimeout(() => setCopiedPastedKey(null), 2000)
                                              }}
                                              className="absolute right-2 top-2 p-1.5 rounded bg-white/5 hover:bg-white/10 text-[#8e95a2] hover:text-brand-text transition opacity-0 group-hover/panel:opacity-100"
                                              title="Copy content"
                                            >
                                              {isCopied ? (
                                                <Check className="w-3 h-3 text-green-400" />
                                              ) : (
                                                <Copy className="w-3 h-3" />
                                              )}
                                            </button>
                                            <pre className="text-[11.5px] font-mono text-brand-text/80 overflow-x-auto max-h-96 whitespace-pre-wrap break-all pr-8 select-text">
                                              {item.content}
                                            </pre>
                                          </div>
                                        )}
                                      </div>
                                    )
                                  })}
                                </div>
                              )
                            }

                            if (msg.content && msg.content.trim().length > 0) {
                              return (
                                <p className="text-[16px] sm:text-[14.5px] text-[#f4f4f5] leading-[1.65] font-normal whitespace-pre-wrap font-sans">
                                  {msg.content}
                                </p>
                              )
                            }
                            return null
                          })()

                        )

                      ) : msg.content === '' && isStreaming && (!msg.widgetData || msg.widgetData.length === 0) && (!msg.generatedFiles || msg.generatedFiles.length === 0) && !msg.imageUrl ? (

                        /* Typing / searching / thinking indicator — appears immediately before first token */

                        <div className="space-y-2">

                          {msg.role === 'assistant' && msg.thinkingContent && msg.thinkingContent.trim().length > 0 && (

                            <ThinkingPanel

                              content={msg.thinkingContent}

                              isStreaming={isStreaming && i === messages.length - 1}

                            />

                          )}

                          {msg.agentStep && msg.agentStep > 0 ? (
                            /* OODA loop active — show step counter */
                            <div className="w-full min-w-0 max-w-full py-0.5">
                              <AgentTodoChecklist todos={msg.agentTodos || []} />
                              <AgentStepIndicator
                                step={msg.agentStep}
                                label={msg.agentLabel || (webSearchStatus === 'searching' ? activityLabel : undefined)}
                              />
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 py-1">
                              {webSearchStatus === 'searching' ? (
                                <div className="inline-flex items-center gap-2 py-1 text-xs text-white/60 select-none">
                                  <Globe className="w-3.5 h-3.5 text-white/70 animate-pulse" />
                                  <span className="text-[12px] font-sans font-normal text-white/70">
                                    {activityLabel || 'Searching the web...'}
                                  </span>
                                </div>
                              ) : activityLabel ? (
                                <div className="inline-flex items-center gap-2 py-1 text-xs text-white/60 select-none">
                                  <span className="w-1.5 h-1.5 rounded-full bg-white/50 animate-pulse" />
                                  <span className="text-[12px] font-sans font-normal text-white/70">
                                    {activityLabel}
                                  </span>
                                </div>
                              ) : msg.thinkingContent ? (
                                <div className="inline-flex items-center gap-2 py-1 text-xs select-none">
                                  <span className="w-1.5 h-1.5 rounded-full bg-white/70 animate-pulse" />
                                  <span className="text-[12px] font-sans font-normal text-white/70 animate-pulse">
                                    Synthesizing answer...
                                  </span>
                                </div>
                              ) : (
                                <div className="flex items-center gap-1.5 py-1.5 px-0.5 select-none">
                                  <span className="w-2 h-2 rounded-full bg-white/40 animate-pulse" />
                                </div>
                              )}
                            </div>
                          )}

                        </div>

                      ) : (

                        /* Rendered markdown — optionally preceded by a step pill while looping */

                        <div className="space-y-3">

                          {msg.role === 'assistant' && msg.thinkingContent && msg.thinkingContent.trim().length > 0 && (

                            <ThinkingPanel

                              content={msg.thinkingContent}

                              isStreaming={isStreaming && i === messages.length - 1}

                            />

                          )}

                          {msg.role === 'assistant' && (msg.agentStep ?? 0) > 1 && msg.content && msg.content.trim().length > 0 && (
                            <div className="w-full min-w-0 max-w-full">
                              <AgentTodoChecklist todos={msg.agentTodos || []} />
                              <AgentStepIndicator
                                step={msg.agentStep!}
                                label={msg.agentLabel || (webSearchStatus === 'searching' && i === messages.length - 1 ? activityLabel : undefined)}
                                isComplete={!isStreaming || i !== messages.length - 1}
                              />
                            </div>
                          )}

                          {/* Autonomous Agent Mode Widgets — rendered ABOVE the streaming text response */}
                          {msg.agentTaskData?.plan && msg.agentTaskData.plan.length > 0 && (
                            <AgentExecutionStepper
                              task={msg.agentTaskData}
                            />
                          )}

                          {/* In-chat HITL Approval Card */}
                          {msg.agentApprovalRequired && (
                            <AgentHITLApprovalCard
                              step={msg.agentApprovalRequired.step}
                              taskId={msg.agentApprovalRequired.taskId}
                              reason={msg.agentApprovalRequired.reason}
                              onApprove={() =>
                                handleApproveHITL(
                                  msg.agentApprovalRequired!.taskId,
                                  msg.agentApprovalRequired!.step.index,
                                  'approve'
                                )
                              }
                              onSkip={() =>
                                handleApproveHITL(
                                  msg.agentApprovalRequired!.taskId,
                                  msg.agentApprovalRequired!.step.index,
                                  'skip'
                                )
                              }
                              onCancel={() =>
                                handleApproveHITL(
                                  msg.agentApprovalRequired!.taskId,
                                  msg.agentApprovalRequired!.step.index,
                                  'cancel'
                                )
                              }
                            />
                          )}

                          {/* In-chat User Input / Clarification Card */}
                          {msg.agentUserInputRequired && (
                            <AgentUserInputCard
                              question={msg.agentUserInputRequired.question}
                              options={msg.agentUserInputRequired.options}
                              selectType={msg.agentUserInputRequired.selectType}
                              onSubmit={(ans) =>
                                handleUserInputSubmit(
                                  msg.agentUserInputRequired!.taskId,
                                  msg.agentUserInputRequired!.stepIndex,
                                  ans
                                )
                              }
                            />
                          )}


                          {msg.content && msg.content.trim().length > 0 && renderRichContent(

                            msg.content,

                            (t) => renderMarkdown(t, msg.generatedFiles),

                            /* Only skip rich rendering if this is the actively streaming message */

                            isStreaming && i === messages.length - 1,

                          )}

                          {/* Instant Site Deployment Preview Cards (from artifacts or content URL) */}
                          {(() => {
                            const artifactSites = (msg.agentTaskData?.artifacts || [])
                              .filter((a: any) => a.type === 'site_preview' || (a.download_url && a.download_url.includes('/v1/sites/')))
                              .map((a: any) => ({
                                title: a.title || 'Live Deployed Web App',
                                url: a.download_url,
                                slug: a.slug,
                              }))

                            const urlMatches = Array.from(
                              (msg.content || '').matchAll(/(https?:\/\/[^\s)\]`"']+\/v1\/sites\/[a-zA-Z0-9\-_]+)/gi)
                            ).map((m) => ({
                              title: 'Live Deployed Web App',
                              url: m[1],
                              slug: m[1].split('/sites/').pop(),
                            }))

                            const allSites = [...artifactSites]
                            for (const s of urlMatches) {
                              if (!allSites.some((ex) => ex.url === s.url)) {
                                allSites.push(s)
                              }
                            }

                            return allSites.map((site, sIdx) => (
                              <AgentSiteDeploymentCard
                                key={sIdx}
                                title={site.title}
                                previewUrl={site.url}
                                slug={site.slug}
                              />
                            ))
                          })()}

                          {/* Compact files-changed chip (Verdent-style) */}
                          {msg.agentTaskData?.artifacts && msg.agentTaskData.artifacts.length > 1 && (
                            <AgentFileChangesCard
                              artifacts={msg.agentTaskData.artifacts.map((a: any) => ({
                                filename: a.filename || a.title || 'artifact',
                                download_url: a.download_url || a.url,
                                size_bytes: a.size_bytes,
                              }))}
                              onOpen={(f) =>
                                f.download_url &&
                                dispatchOpenFilePreview({
                                  name: f.filename,
                                  type: mimeFromName(f.filename),
                                  url: f.download_url,
                                  sizeBytes: f.size_bytes,
                                  siblingFiles: (msg.agentTaskData?.artifacts || []).map((a: any) => ({
                                    name: a.filename || a.title || 'artifact',
                                    type: mimeFromName(a.filename || a.title || 'artifact'),
                                    url: a.download_url || a.url,
                                    sizeBytes: a.size_bytes,
                                  })),
                                })
                              }
                            />
                          )}

                          {/* Generated file download cards / Unified Repository Deliverable Card */}
                          {(() => {
                            let filesToRender = (msg.generatedFiles && msg.generatedFiles.length > 0) ? [...msg.generatedFiles] : []

                            // If generatedFiles was not explicitly attached, synthesize from markdown links in content
                            if (filesToRender.length === 0 && msg.content) {
                              const matches = Array.from((msg.content || '').matchAll(/\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g))
                              const synthetic: any[] = []
                              for (const m of matches) {
                                const lbl = m[1] || 'deliverable'
                                const u = m[2]
                                const lu = u.toLowerCase()
                                if (
                                  lu.endsWith('.zip') ||
                                  lu.endsWith('.html') ||
                                  lu.endsWith('.pdf') ||
                                  lu.endsWith('.docx') ||
                                  lu.endsWith('.xlsx') ||
                                  lu.endsWith('.py') ||
                                  lu.includes('/files/sandbox/') ||
                                  lu.includes('/generated/') ||
                                  lu.includes('r2.dev') ||
                                  lu.includes('blob.core.windows.net') ||
                                  lbl.toLowerCase().includes('download') ||
                                  lbl.toLowerCase().includes('website')
                                ) {
                                  let fn = u.split('/').pop()?.split('?')[0] || lbl
                                  if (!fn.includes('.')) fn = `${lbl.replace(/\s+/g, '_').toLowerCase()}.zip`
                                  synthetic.push({
                                    filename: fn,
                                    download_url: u,
                                    size_bytes: 0,
                                  })
                                }
                              }
                              if (synthetic.length > 0) filesToRender = synthetic
                            }

                            if (!filesToRender || filesToRender.length === 0) return null

                            const isRepoOrBundle = filesToRender.length > 1 ||
                              filesToRender.some((f: any) =>
                                (f.filename || '').includes('/') ||
                                (f.filename || '').endsWith('.html') ||
                                (f.filename || '').endsWith('.zip')
                              )

                            if (isRepoOrBundle) {
                              return (
                                <RepositoryDeliverableCard
                                  files={filesToRender}
                                  onPreview={(file, allFiles) => {
                                    dispatchOpenFilePreview({
                                      name: file.filename,
                                      type: mimeFromName(file.filename),
                                      url: file.download_url,
                                      sizeBytes: file.size_bytes,
                                      siblingFiles: allFiles.map((f) => ({
                                        name: f.filename,
                                        type: mimeFromName(f.filename),
                                        url: f.download_url,
                                        sizeBytes: f.size_bytes,
                                      })),
                                    })
                                  }}
                                  onDownloadSingle={(url, filename) => triggerDirectDownload(url, filename)}
                                />
                              )
                            }

                            return (
                              <div className="mt-3 space-y-2">
                                {filesToRender.map((gf, gfi) => (
                                  <FileDownloadCard
                                    key={gfi}
                                    filename={gf.filename}
                                    download_url={gf.download_url}
                                    size_bytes={gf.size_bytes}
                                    onView={() => dispatchOpenFilePreview({
                                      name: gf.filename,
                                      type: mimeFromName(gf.filename),
                                      url: gf.download_url,
                                      sizeBytes: gf.size_bytes,
                                      siblingFiles: (filesToRender || []).map((f: any) => ({
                                        name: f.filename,
                                        type: mimeFromName(f.filename),
                                        url: f.download_url,
                                        sizeBytes: f.size_bytes,
                                      })),
                                    })}
                                  />
                                ))}
                              </div>
                            )
                          })()}

                          {/* Inline visual widgets (visualize__show_widget) */}

                          {msg.widgetData && msg.widgetData.length > 0 && (

                            <div className="mt-3 space-y-3">

                              {msg.widgetData.map((wData, wIdx) => (

                                <WidgetRenderer

                                  key={wIdx}

                                  code={wData.code}

                                  title={wData.title}

                                  loadingMessages={wData.loadingMessages}

                                  widgetType={wData.widgetType}

                                  widgetLoading={wData.widgetLoading ?? false}

                                />

                              ))}

                            </div>

                          )}

                          {/* Structured Display Cards (e.g. sports match card) */}
                          {Array.isArray(msg.displayCards) && msg.displayCards.length > 0 && (
                            <div className="mt-3 space-y-3">
                              {msg.displayCards.map((card, cIdx) => {
                                if (card.card_type === 'render_sports_card') {
                                  return <SportsMatchCard key={cIdx} {...card.payload} />
                                } else if (card.card_type === 'render_options_card') {
                                  return <OptionsCard key={cIdx} {...card.payload} />
                                }
                                return null
                              })}
                            </div>
                          )}



                          {/* Image pending spinner or resolved image — always below file cards */}

                          {msg.imagePending && (

                            <ImagePending prompt={msg.imagePrompt || undefined} />

                          )}

                          {msg.imageUrl && (

                            <ImageBubble url={msg.imageUrl} prompt={msg.imagePrompt || undefined} />

                          )}

                        </div>

                      )}

                    </div>

                    {/* Overlapping Sources Stack */}

                    {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (

                      <SourcesStack sources={msg.sources} />

                    )}

                    {/* Relative timestamp — visible on hover */}

                    {msg.timestamp && !(isStreaming && i === messages.length - 1) && (

                      <span

                        className="text-[9px] text-[#8e95a2]/30 font-medium px-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 select-none"

                        title={new Date(msg.timestamp).toLocaleString()}

                      >

                        {(() => {

                          const diffMs = Date.now() - msg.timestamp

                          const diffMin = Math.floor(diffMs / 60000)

                          const diffHr = Math.floor(diffMs / 3600000)

                          if (diffMs < 60000) return 'just now'

                          if (diffMin < 60) return `${diffMin}m ago`

                          if (diffHr < 24) return `${diffHr}h ago`

                          return new Date(msg.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

                        })()}

                      </span>

                    )}

                    {/* Actions Row at the bottom (outside the bubble), visible on hover */}

                    {((msg.role === 'assistant' && msg.content.length > 0 && !(isStreaming && i === messages.length - 1)) || (msg.role === 'user' && editingMessageIndex !== i)) && (

                      <div className="flex items-center gap-3.5 px-1.5 opacity-80 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity duration-200">

                        {msg.content.length > 0 && (

                          <button

                            onClick={() => handleCopy(msg.content, i)}

                            title={msg.role === 'user' ? "Copy prompt" : "Copy response"}

                            className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase min-h-[36px] touch:min-h-[40px] px-1.5 -mx-1.5 py-1"

                          >

                            {copiedIndex === i ? (

                              <>

                                <Check className="w-3.5 h-3.5 text-[#ffffff]" />

                                <span className="text-[#ffffff]">Copied</span>

                              </>

                            ) : (

                              <>

                                <Copy className="w-3.5 h-3.5" />

                                <span>Copy</span>

                              </>

                            )}

                          </button>

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

                            className="flex items-center gap-1.5 text-[11px] font-bold text-brand-muted hover:text-brand-accent transition duration-150 tracking-wider uppercase disabled:opacity-30 disabled:cursor-not-allowed min-h-[36px] touch:min-h-[40px] px-1.5 -mx-1.5 py-1"

                          >

                            <Pencil className="w-3.5 h-3.5" />

                            <span>Edit</span>

                          </button>

                        )}

                      </div>

                    )}

                  </div>

                </div>
                )}
                  </LazyMessage>
                )
              })
            })()}

              <div ref={messagesEndRef} />

            </div>

          )}

        </div>

        {/* Right-edge prompt navigator — fixed in viewport, outside scrolling container */}
        <TurnTracker
          turnIndices={messages
            .map((m, i) => (m.role === 'user' && !m.isArchived ? i : -1))
            .filter((i) => i >= 0)}
          scrollRef={scrollContainerRef}
        />


        {/* Pinned Input Area — only displayed when conversation has active messages or history is loading for existing chat */}
        {(messages.length > 0 || (isFetchingHistory && activeConversationId !== '00000000-0000-0000-0000-000000000000')) && (
          <div
            style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom, 0.75rem))' }}
            className="shrink-0 w-full px-2 sm:px-4 md:px-6 pt-1 sm:pt-1.5 z-20"
          >
            {renderInputConsole(false)}
          </div>
        )}

      </div>

          {/* Artifact Preview Panel */}



        </div>

      </main>

      {convoToDelete && (

        <div className="fixed inset-0 bg-black/70 backdrop-blur-[2px] flex items-center justify-center z-50 p-4">

          <div className="bg-[#0d0f11] border border-[#1e2025] rounded-lg w-full max-w-sm p-6 shadow-2xl space-y-6">

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

      {isShareModalOpen && (() => {
        const activeConvo = conversations.find(c => c.id === activeConversationId)
        const isShared = activeConvo?.is_shared
        const shareToken = activeConvo?.share_token
        const shareUrl = shareToken ? `${window.location.origin}/shared/?token=${shareToken}` : ''

        return (
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-end sm:items-center justify-center z-50 p-3 sm:p-4 animate-in fade-in duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget) setIsShareModalOpen(false)
            }}
          >
            <div
              className="bg-[#14161a] border border-white/10 rounded-2xl w-full max-w-md p-5 sm:p-6 shadow-2xl space-y-5 transition-all duration-200"
              style={{ boxShadow: '0 12px 40px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.06)' }}
            >
              <div className="flex items-center justify-between border-b border-white/[0.08] pb-3.5">
                <h3 className="text-sm sm:text-[15px] font-semibold text-white flex items-center gap-2">
                  <Share2 className="w-4 h-4 text-white" />
                  <span>Share Conversation</span>
                </h3>
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    setIsShareModalOpen(false)
                  }}
                  className="min-h-[44px] min-w-[44px] -mr-2 -my-2 flex items-center justify-center rounded-xl text-white/50 hover:text-white hover:bg-white/[0.08] active:bg-white/[0.14] transition-colors touch-manipulation cursor-pointer"
                  title="Close"
                >
                  <X className="w-5 h-5 pointer-events-none" />
                </button>
              </div>

              {isShared ? (
                <div className="space-y-4">
                  <p className="text-xs sm:text-[13px] text-[#9aa0ae] leading-relaxed">
                    Anyone with this link can view the conversation history and export it as JSON.
                  </p>

                  <div className="flex items-center gap-2 bg-[#0d0f11] border border-white/10 rounded-xl p-1.5 focus-within:border-white/30 transition-colors">
                    <input
                      type="text"
                      readOnly
                      value={shareUrl}
                      onClick={(e) => (e.target as HTMLInputElement).select()}
                      className="bg-transparent border-0 outline-none text-xs sm:text-[12.5px] text-[#e2e5eb] font-mono flex-1 px-2.5 py-1.5 select-all truncate"
                    />
                    <button
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(shareUrl)
                          showToast('Link copied to clipboard!', 'info')
                        } catch {
                          // Safari rejects clipboard writes outside user gestures
                          showToast('Could not copy — long-press the link to copy it.', 'info')
                        }
                      }}
                      className="min-h-[38px] px-4 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 active:bg-white/30 border border-white/15 text-xs font-bold text-white transition-all shrink-0 flex items-center gap-1.5 touch-manipulation"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy</span>
                    </button>
                  </div>

                  <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center sm:justify-between gap-2.5 pt-2">
                    <button
                      onClick={() => handleShareToggle(false)}
                      disabled={sharing}
                      className="min-h-[44px] px-4 py-2 rounded-xl bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 active:bg-red-500/30 text-xs sm:text-sm font-semibold text-red-400 transition-colors flex items-center justify-center touch-manipulation disabled:opacity-50"
                    >
                      {sharing ? 'Processing...' : 'Stop Sharing'}
                    </button>
                    <button
                      onClick={() => setIsShareModalOpen(false)}
                      className="min-h-[44px] px-5 py-2 rounded-xl border border-white/10 hover:bg-white/5 active:bg-white/10 text-xs sm:text-sm font-semibold text-[#e2e5eb] transition-colors flex items-center justify-center touch-manipulation"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-xs sm:text-[13px] text-[#9aa0ae] leading-relaxed">
                    Create a public link to share this conversation with others.
                  </p>
                  <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center sm:justify-end gap-2.5 sm:gap-3 pt-2">
                    <button
                      onClick={() => setIsShareModalOpen(false)}
                      className="min-h-[44px] px-4 py-2.5 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.08] active:bg-white/[0.12] text-xs sm:text-sm font-semibold text-[#e2e5eb] transition-colors flex items-center justify-center touch-manipulation"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleShareToggle(true)}
                      disabled={sharing}
                      className="min-h-[44px] px-5 py-2.5 rounded-xl bg-white hover:bg-[#f0f2f5] active:bg-[#e2e5eb] text-black text-xs sm:text-sm font-bold shadow-md transition-all flex items-center justify-center touch-manipulation disabled:opacity-50"
                    >
                      {sharing ? 'Creating Link...' : 'Create Link'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      {/* Conversation access error banner (Fix 2 — non-destructive, cache preserved) */}
      {convoAccessError && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-40 w-[92%] max-w-md px-4 py-3 rounded-xl bg-red-950/90 border border-red-500/30 shadow-xl shadow-black/40 backdrop-blur-md" role="alert">
          <p className="text-[13px] font-bold text-red-200 leading-snug">Can't open this conversation</p>
          <p className="text-[12px] text-red-300/80 mt-0.5 leading-snug">{convoAccessError.reason}</p>
          <div className="flex gap-2 mt-2.5">
            <button
              type="button"
              onClick={() => { setConvoAccessError(null); handleNewSession() }}
              className="px-3 py-1.5 rounded-lg bg-white text-black text-[11px] font-bold shadow transition hover:bg-[#f0f2f5] active:bg-[#e2e5eb] touch-manipulation"
            >
              Start new chat
            </button>
            <button
              type="button"
              onClick={() => setConvoAccessError(null)}
              className="px-3 py-1.5 rounded-lg bg-white/10 border border-white/15 text-white/80 text-[11px] font-semibold hover:bg-white/20 transition touch-manipulation"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Session identity changed modal (Fix 1 — non-destructive, user decides) */}
      {sessionSwitchPrompt && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-sm rounded-2xl border border-white/15 bg-[#0d0f11]/95 shadow-2xl shadow-black/60 p-5">
            <p className="text-sm font-bold text-brand-text">Signed in as a different account</p>
            <p className="mt-2 text-[13px] text-white/60 leading-snug">
              This browser's session switched to{' '}
              <span className="text-white/90 font-semibold break-words">{sessionSwitchPrompt.newEmail || 'another account'}</span>.
              Open conversations belong to the previous account and may fail to load until you reload.
            </p>
            <div className="mt-4 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="min-h-[40px] px-4 rounded-lg bg-white text-black text-xs font-bold shadow transition hover:bg-[#f0f2f5] active:bg-[#e2e5eb]"
              >
                Reload app
              </button>
              <button
                type="button"
                onClick={() => setSessionSwitchPrompt(null)}
                className="min-h-[40px] px-4 rounded-lg bg-white/10 border border-white/15 text-white/80 text-xs font-semibold hover:bg-white/20 transition"
              >
                Continue anyway
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

            className={`px-4 py-2.5 rounded-lg border text-[12px] font-semibold tracking-wide shadow-xl shadow-black/40 backdrop-blur-md ${

              t.type === 'error'

                ? 'bg-red-950/90 border-red-500/20 text-red-300'

                : 'bg-[#0d0f11]/90 border-[#ffffff]/20 text-brand-text'

            }`}

          >

            {t.message}

          </div>

        ))}

      </div>

      {/* Floating Capabilities Popup at Bottom Left (White background, Black text, Minimalist) */}
      {showCapabilitiesNote && (
        <div className="fixed bottom-3 left-3 right-3 w-auto sm:left-6 sm:right-auto sm:w-80 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] rounded-lg border border-black/10 bg-white shadow-2xl flex flex-col gap-2.5 z-50 animate-in fade-in slide-in-from-bottom-4 duration-300 pointer-events-auto select-none">
          <div className="flex items-start justify-between">
            <span className="text-[10px] uppercase tracking-widest text-black/50 font-bold">
              System Notice
            </span>
            <button 
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setShowCapabilitiesNote(false)
                localStorage.setItem('dismissed_capabilities_note', 'true')
              }}
              className="text-black/40 hover:text-black transition p-0.5 rounded hover:bg-black/5"
              title="Dismiss notification"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-[11.5px] text-black leading-relaxed font-semibold">
            Ochuko can run calculations, analyze files, read images, and search the web.
          </p>
          <a 
            href="/capabilities"
            className="text-[11px] text-black hover:text-black/75 font-bold underline align-self-start mt-1"
          >
            Explore Capabilities →
          </a>
        </div>
      )}

      {/* App Lock Overlays */}
      {isLocked && (
        <AppLock
          mode="unlock"
          onSuccess={() => setIsLocked(false)}
        />
      )}

      {lockMode && (
        <AppLock
          mode={lockMode}
          onSuccess={() => {
            const currentMode = lockMode
            setLockMode(null)
            showToast(
              currentMode === 'setup' ? 'Security PIN enabled' :
              currentMode === 'change' ? 'Security PIN changed successfully' :
              'Security PIN disabled'
            )
          }}
          onClose={() => setLockMode(null)}
        />
      )}


      {/* ── Responsive Mode Selector Modal (Mobile Bottom Sheet + Desktop Centered Dialog) ── */}
      <div
        className={`fixed inset-0 z-50 transition-opacity duration-300 sm:flex sm:items-center sm:justify-center sm:p-4 ${
          isModeSheetOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
      >
        {/* Backdrop */}
        <div
          onClick={() => setIsModeSheetOpen(false)}
          className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        />

        {/* Modal / Sheet Card */}
        <div
          className={`absolute bottom-0 left-0 right-0 sm:relative sm:bottom-auto sm:left-auto sm:right-auto sm:max-w-lg sm:w-full bg-[#121418] border-t sm:border border-white/10 sm:border-white/15 rounded-t-2xl sm:rounded-2xl px-5 pt-3 pb-[max(1.5rem,env(safe-area-inset-bottom,1.5rem))] sm:p-6 shadow-2xl transition-all duration-300 ease-out transform ${
            isModeSheetOpen ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-full sm:translate-y-4 sm:scale-95 opacity-0'
          }`}
        >
          {/* Dim drag handle bar (mobile only) */}
          <div className="w-10 h-1 bg-white/25 rounded-full mx-auto mb-4 sm:hidden" />

          {/* Header */}
          <div className="flex items-center justify-between mb-3.5 pb-3 border-b border-white/[0.08]">
            <div>
              <h3 className="text-sm sm:text-base font-bold text-white tracking-wide">Select Execution Mode</h3>
              <p className="text-[11px] sm:text-xs text-[#8e95a2] mt-0.5">Choose how Agent Ochuko processes your prompt</p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setIsModeSheetOpen(false)
              }}
              className="min-h-[44px] min-w-[44px] -mr-1 flex items-center justify-center rounded-lg text-[#8e95a2] hover:text-white hover:bg-white/10 transition cursor-pointer touch-manipulation"
              aria-label="Close mode sheet"
            >
              <X className="w-5 h-5 sm:w-4 sm:h-4 pointer-events-none" />
            </button>
          </div>

          {/* Mode Options List */}
          <div className="space-y-2">
            {([
              {
                id: 'agent',
                name: 'Agent Mode',
                badge: 'Full Automation',
                description: 'Autonomous goal execution, tool orchestration, code sandbox, and site deployment.',
                icon: Bot,
                iconColor: 'text-brand-accent bg-brand-accent/15 border-brand-accent/30',
              },
              {
                id: 'think',
                name: 'Deep Think',
                badge: 'Reasoning',
                description: 'Extended architectural analysis, complex planning, and step-by-step logic.',
                icon: Brain,
                iconColor: 'text-purple-400 bg-purple-500/15 border-purple-500/30',
              },
              {
                id: 'solve',
                name: 'Code & Solve',
                badge: 'Engineering',
                description: 'Hermetic problem solving, debugging, and code generation with verification.',
                icon: Cpu,
                iconColor: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
              },
              {
                id: 'discuss',
                name: 'Discuss & Chat',
                badge: 'Conversational',
                description: 'Fast, interactive discussions, brainstorming, and general inquiries.',
                icon: MessageSquare,
                iconColor: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30',
              },
            ] as const).map(({ id, name, badge, description, icon: Icon, iconColor }) => {
              const active = mode === id
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => {
                    handleModeChange(id)
                    setIsModeSheetOpen(false)
                  }}
                  className={`w-full text-left p-3 rounded-xl border transition flex items-start gap-3 min-h-[56px] active:scale-[0.99] ${
                    active
                      ? 'bg-white/[0.08] border-white/30 shadow-md ring-1 ring-white/20'
                      : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.05] hover:border-white/15'
                  }`}
                >
                  <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 mt-0.5 ${iconColor}`}>
                    <Icon className="w-5 h-5" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`text-xs font-bold tracking-tight ${active ? 'text-white' : 'text-white/90'}`}>
                        {name}
                      </span>
                      <span className="text-[9px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/[0.06] text-[#8e95a2] border border-white/[0.06]">
                        {badge}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#8e95a2] leading-snug mt-1">
                      {description}
                    </p>
                  </div>

                  {active && (
                    <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center shrink-0 self-center">
                      <Check className="w-3.5 h-3.5 text-white" />
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Unified File/Text Preview — Ochuko dock for text artifacts, modal for media */}
      {previewingFile && (
        <ErrorBoundary
          fallback={
            <div
              className="fixed inset-0 bg-[#07080a]/95 z-[100] flex flex-col items-center justify-center gap-4 p-6"
              onClick={() => setPreviewingFile(null)}
            >
              <p className="text-white/80 text-sm text-center">This preview hit an error and could not be rendered.</p>
              <button
                className="min-h-[44px] px-5 rounded-lg bg-white/10 border border-white/20 text-white text-sm font-semibold active:bg-white/20"
                onClick={(e) => { e.stopPropagation(); setPreviewingFile(null) }}
              >
                Close preview
              </button>
            </div>
          }
        >
        {(() => {
        const pn = (previewingFile.name || '').toLowerCase()
        if (pn.endsWith('.zip')) {
          return (
            <ZipAppPreviewer
              file={previewingFile}
              onClose={() => setPreviewingFile(null)}
              onDownload={() => {
                const u = previewingFile.localObjectUrl || previewingFile.url
                if (u) triggerDirectDownload(u, previewingFile.name)
              }}
            />
          )
        }
        const hasRepoContext = Boolean(
          previewingFile.siteSlug ||
          (previewingFile.siblingFiles && previewingFile.siblingFiles.length > 1) ||
          previewingFile.projectFiles ||
          (allRecentFiles && allRecentFiles.length > 1)
        )
        const pIsImg = (previewingFile.type || '').startsWith('image/') || /\.(png|jpe?g|webp|gif|svg)$/i.test(pn)
        const pIsPdf = previewingFile.type === 'application/pdf' || pn.endsWith('.pdf')
        const pIsBin = /\.(docx?|xlsx?|pptx?|rar|tar|gz|7z|exe|bin|iso|dmg)$/i.test(pn)
        if (!pIsPdf && (!pIsBin || hasRepoContext) && (!pIsImg || hasRepoContext || pn.endsWith('.svg'))) {
          return (
            <>
              <div className="fixed inset-0 bg-black/40 z-[99] max-md:bg-[#1a1a18]/95" onClick={() => setPreviewingFile(null)} />
              <ArtifactPanel
                file={previewingFile}
                content={loadedPreviewContent}
                loading={previewLoading}
                renderMarkdown={renderMarkdown}
                onClose={() => setPreviewingFile(null)}
                onPublish={() => showToast('Artifact published successfully!', 'info')}
                allConversationFiles={allRecentFiles}
              />
            </>
          )
        }
        return (
        <div
          className="fixed inset-0 bg-[#07080a]/95 backdrop-blur-md z-[100] flex flex-col items-center justify-between p-4 md:p-6 animate-fadeIn"
          onClick={() => setPreviewingFile(null)}
        >
          {/* Modal Header */}
          <div 
            className="w-full flex items-center justify-between pb-3 border-b border-[#1e2025] mb-3 relative z-10 shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <FileText className="w-5 h-5 text-brand-text/80" />
              <div>
                <h3 className="text-sm font-bold text-white tracking-wide">
                  {previewingFile.name}
                </h3>
                <p className="text-[10px] text-brand-muted/70 uppercase tracking-widest font-semibold mt-0.5">
                  {previewingFile.type}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {previewingFile.type === 'image/svg+xml' && (
                <button
                  type="button"
                  onClick={async () => {
                    const svgSrc = previewingFile.localObjectUrl || previewingFile.url || ''
                    let width = 800
                    let height = 600
                    try {
                      const res = await fetch(svgSrc)
                      const svgText = await res.text()
                      if (svgText) {
                        const parser = new DOMParser()
                        const doc = parser.parseFromString(svgText, 'image/svg+xml')
                        const svgEl = doc.querySelector('svg')
                        if (svgEl) {
                          const viewBox = svgEl.getAttribute('viewBox')
                          if (viewBox) {
                            const parts = viewBox.split(/\s+/).map(Number)
                            if (parts.length === 4 && !isNaN(parts[2]) && !isNaN(parts[3])) {
                              width = parts[2]
                              height = parts[3]
                            }
                          } else {
                            const wAttr = svgEl.getAttribute('width')
                            const hAttr = svgEl.getAttribute('height')
                            if (wAttr && hAttr) {
                              width = parseFloat(wAttr) || width
                              height = parseFloat(hAttr) || height
                            }
                          }
                        }
                      }
                    } catch (e) {
                      console.warn("Failed to parse SVG dimensions:", e)
                    }

                    const img = new Image()
                    img.onload = () => {
                      const canvas = document.createElement('canvas')
                      const scale = 2
                      canvas.width = width * scale
                      canvas.height = height * scale
                      const ctx = canvas.getContext('2d')
                      if (ctx) {
                        ctx.fillStyle = '#0d1117'
                        ctx.fillRect(0, 0, canvas.width, canvas.height)
                        ctx.scale(scale, scale)
                        ctx.drawImage(img, 0, 0, width, height)
                        const pngURL = canvas.toDataURL('image/png')
                        const downloadLink = document.createElement('a')
                        downloadLink.href = pngURL
                        downloadLink.download = `${previewingFile.name.replace(/\s+/g, '_')}_expanded.png`
                        document.body.appendChild(downloadLink);
                        downloadLink.click();
                        document.body.removeChild(downloadLink);
                      }
                    }
                    img.src = svgSrc
                  }}
                  className="px-3 py-1.5 rounded-lg bg-[#ffffff]/5 hover:bg-[#ffffff]/10 text-[11px] font-bold text-brand-text border border-[#ffffff]/10 transition flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download PNG</span>
                </button>
              )}
              {(loadedPreviewContent || previewingFile.content) && (
                <button
                  type="button"
                  onClick={async () => {
                    const toCopy = loadedPreviewContent || previewingFile.content || ''
                    if (toCopy) {
                      await navigator.clipboard.writeText(toCopy)
                      setCopiedModalPreview(true)
                      setTimeout(() => setCopiedModalPreview(false), 2000)
                    }
                  }}
                  className="px-3 py-1.5 rounded-lg bg-[#ffffff]/5 hover:bg-[#ffffff]/10 text-[11px] font-bold text-brand-text border border-[#ffffff]/10 transition flex items-center gap-1.5"
                  title="Copy content"
                >
                  {copiedModalPreview ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedModalPreview ? 'Copied' : 'Copy'}</span>
                </button>
              )}
              {previewingFile && ((previewingFile.name || '').toLowerCase().endsWith('.md') || previewingFile.type === 'text/markdown' || previewingFile.type === 'markdown') && (
                <div className="flex items-center rounded-lg border border-[#ffffff]/10 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setPreviewView('preview')}
                    className={`px-3 py-1.5 text-[11px] font-bold flex items-center gap-1.5 transition ${
                      previewView === 'preview' ? 'bg-white/10 text-white' : 'text-brand-muted hover:text-brand-text'
                    }`}
                    title="Rendered markdown preview"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>Preview</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewView('raw')}
                    className={`px-3 py-1.5 text-[11px] font-bold flex items-center gap-1.5 transition ${
                      previewView === 'raw' ? 'bg-white/10 text-white' : 'text-brand-muted hover:text-brand-text'
                    }`}
                    title="Raw markdown source"
                  >
                    <Code2 className="w-3.5 h-3.5" />
                    <span>Raw</span>
                  </button>
                </div>
              )}
              <button
                type="button"
                onClick={async () => {
                  try {
                    let blob: Blob
                    const contentText = loadedPreviewContent || previewingFile.content
                    const targetUrl = previewingFile.localObjectUrl || previewingFile.url
                    if (contentText) {
                      blob = new Blob([contentText], { type: previewingFile.type || 'text/plain;charset=utf-8' })
                    } else if (targetUrl) {
                      const res = await fetch(targetUrl)
                      blob = await res.blob()
                    } else {
                      return
                    }
                    const blobUrl = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = blobUrl
                    a.download = previewingFile.name ? previewingFile.name.split('/').pop()?.split('\\').pop() || previewingFile.name : 'download'
                    document.body.appendChild(a)
                    a.click()
                    document.body.removeChild(a)
                    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
                  } catch (err) {
                    const fallbackUrl = previewingFile.localObjectUrl || previewingFile.url
                    if (fallbackUrl) window.open(fallbackUrl, '_blank')
                  }
                }}
                className="px-3 py-1.5 rounded-lg bg-[#ffffff]/5 hover:bg-[#ffffff]/10 text-[11px] font-bold text-brand-text border border-[#ffffff]/10 transition flex items-center gap-1.5"
                title="Download file"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download</span>
              </button>
              {previewingFile.url && (
                <a 
                  href={previewingFile.url} 
                  target="_blank" 
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded-lg bg-[#ffffff]/5 hover:bg-[#ffffff]/10 text-[11px] font-bold text-brand-text border border-[#ffffff]/10 transition flex items-center gap-1.5"
                >
                  <span>Open in browser</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
              <button 
                type="button" 
                onClick={(e) => {
                  e.stopPropagation()
                  setPreviewingFile(null)
                }} 
                className="p-1.5 rounded-lg bg-[#ffffff]/5 hover:bg-[#ffffff]/10 hover:text-white text-brand-muted border border-[#ffffff]/10 transition relative z-20"
              >
                <X className="w-4 h-4 pointer-events-none" />
              </button>
            </div>
          </div>

          {/* Modal Content — Full Viewport Screen */}
          <div 
            className="flex-1 w-full h-full flex items-center justify-center overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {(() => {
              const nameLower = (previewingFile.name || '').toLowerCase()
              const isImg = (previewingFile.type || '').startsWith('image/') || /\.(png|jpe?g|webp|gif|svg)$/i.test(nameLower)
              const isHtml = previewingFile.type === 'text/html' || previewingFile.type === 'html' || nameLower.endsWith('.html')
              const isPdf = previewingFile.type === 'application/pdf' || nameLower.endsWith('.pdf')
              const isBinary = /\.(docx?|xlsx?|pptx?|rar|tar|gz|7z|exe|bin|iso|dmg)$/i.test(nameLower)
              const fileUrl = previewingFile.localObjectUrl || previewingFile.url

              if (nameLower.endsWith('.zip')) {
                return (
                  <ZipAppPreviewer
                    file={previewingFile}
                    onClose={() => setPreviewingFile(null)}
                    onDownload={() => {
                      const u = previewingFile.localObjectUrl || previewingFile.url
                      if (u) triggerDirectDownload(u, previewingFile.name)
                    }}
                  />
                )
              }

              if (isImg) {
                return (
                  <img 
                    src={fileUrl} 
                    alt={previewingFile.name} 
                    className="w-auto h-auto max-w-full max-h-[85vh] object-contain rounded-lg border border-white/10 shadow-2xl animate-scaleIn select-none"
                  />
                )
              }

              if (isHtml) {
                return (
                  <div className="w-full h-full min-h-[85vh] bg-white rounded-lg border border-white/10 overflow-hidden shadow-2xl">
                    <iframe 
                      srcDoc={loadedPreviewContent || previewingFile.content || undefined} 
                      src={!previewingFile.content && fileUrl ? fileUrl : undefined} 
                      className="w-full h-full border-0" 
                      sandbox="allow-scripts allow-popups allow-forms allow-modals" 
                      title={previewingFile.name}
                    />
                  </div>
                )
              }

              if (isPdf) {
                return (
                  <div className="w-full h-full min-h-[85vh] flex flex-col rounded-lg overflow-hidden border border-white/10 shadow-2xl bg-[#181a20]">
                    <iframe 
                      src={fileUrl} 
                      className="w-full h-full flex-1 border-0 bg-white" 
                      title={previewingFile.name}
                    />
                  </div>
                )
              }

              if (isBinary) {
                return (
                  <div className="flex flex-col items-center justify-center max-w-md p-8 rounded-lg bg-[#111317] border border-white/15 text-center shadow-2xl space-y-4">
                    <div className="w-16 h-16 rounded-lg bg-white/10 border border-white/15 flex items-center justify-center text-white/90">
                      <FileText className="w-8 h-8" />
                    </div>
                    <div>
                      <h4 className="text-base font-bold text-white">{previewingFile.name}</h4>
                      <p className="text-xs text-white/50 mt-1">{previewingFile.type || 'Binary Document'}</p>
                    </div>
                    <p className="text-xs text-white/70">This binary file format cannot be rendered directly in the web previewer. You can download or open it in your browser.</p>
                    {fileUrl && (
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const res = await fetch(fileUrl)
                            const blob = await res.blob()
                            const blobUrl = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = blobUrl
                            const safeName = previewingFile.name ? previewingFile.name.split('/').pop()?.split('\\').pop() || previewingFile.name : 'download'
                            a.download = safeName
                            document.body.appendChild(a)
                            a.click()
                            document.body.removeChild(a)
                            setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
                          } catch {
                            window.open(fileUrl, '_blank')
                          }
                        }}
                        className="px-4 py-2 rounded-lg bg-white text-black font-bold text-xs hover:bg-white/90 transition flex items-center gap-2 cursor-pointer"
                      >
                        <Download className="w-4 h-4" />
                        <span>Download File</span>
                      </button>
                    )}
                  </div>
                )
              }

              // Markdown: rendered Preview (default) or Raw source via header toggle
              const isMd = nameLower.endsWith('.md') || previewingFile.type === 'text/markdown' || previewingFile.type === 'markdown'
              const mdText = loadedPreviewContent || previewingFile.content || ''

              if (isMd) {
                if (previewLoading) {
                  return (
                    <div className="flex flex-col items-center justify-center p-12 gap-3 text-white/70">
                      <Loader2 className="w-7 h-7 animate-spin text-white/80" />
                      <span className="text-xs font-mono">Loading file contents...</span>
                    </div>
                  )
                }
                if (previewView === 'raw') {
                  return (
                    <pre className="w-full h-full max-h-[85vh] bg-[#0b0c0f] border border-[#1e2025] rounded-lg p-6 text-[#c9d1d9] font-mono text-[13px] overflow-auto whitespace-pre-wrap select-text leading-relaxed shadow-inner">
                      {mdText || "No text content available to display."}
                    </pre>
                  )
                }
                return (
                  <div className="w-full h-full max-h-[85vh] overflow-auto bg-[#0b0c0f] border border-[#1e2025] rounded-lg p-4 sm:p-6 select-text leading-relaxed shadow-inner">
                    {mdText ? renderMarkdown(mdText) : <p className="text-white/40 text-sm">No text content available to display.</p>}
                  </div>
                )
              }

              // Text / Code / JSON / etc.
              return previewLoading ? (
                <div className="flex flex-col items-center justify-center p-12 gap-3 text-white/70">
                  <Loader2 className="w-7 h-7 animate-spin text-white/80" />
                  <span className="text-xs font-mono">Loading file contents...</span>
                </div>
              ) : (
                <pre className="w-full h-full max-h-[85vh] bg-[#0b0c0f] border border-[#1e2025] rounded-lg p-6 text-[#c9d1d9] font-mono text-[13px] overflow-auto whitespace-pre-wrap select-text leading-relaxed shadow-inner">
                  {loadedPreviewContent || previewingFile.content || "No text content available to display."}
                </pre>
              )
            })()}
          </div>


          {/* Footer Info */}
          <div className="pt-4 text-[10px] text-brand-muted/40 font-medium select-none">
            Click outside or press ESC to dismiss preview
          </div>
        </div>
        )
        })()}
        </ErrorBoundary>
      )}

    </div>

  )

}

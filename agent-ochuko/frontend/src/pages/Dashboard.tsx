// @refresh reset
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'

import { supabase } from '../utils/supabaseClient'

import { LogOut, Send, Square, Brain, Cpu, MessageSquare, Menu, Copy, Check, Globe, Pencil, Trash, Paperclip, FileText, Loader2, X, ChevronDown, ChevronUp, Search, Lock, Download, Share2, Settings, Maximize2, Minimize2, RotateCw, ExternalLink, KeyRound, Unlock, Plus, Minus, Mic } from 'lucide-react'

import { useNavigate, useLocation } from 'react-router-dom'
import { AppLock } from '../components/AppLock'
import { useVoice } from '../hooks/useVoice'


import DOMPurify from 'dompurify'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

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
  const honorifics = ['Scholar', 'Strategist', 'Counselor', 'Advisor']
  return honorifics[Math.floor(Math.random() * honorifics.length)]
}

// ─── Time-Based Greetings & Context ──────────────────────────────────────────

function getTimeGreeting(hour: number): string {
  if (hour >= 5  && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  if (hour >= 17 && hour < 21) return 'Good evening'
  return 'Still up'
}

/** Suffix appended after the name — encodes visit context, streak, and time cues. */
function getVisitContext(visitData: VisitData, hour: number): string {
  const now      = Date.now()
  const oneDay   = 24 * 60 * 60 * 1000
  const daysSinceLast = Math.floor((now - visitData.lastVisit) / oneDay)
  const { visitCount, consecutiveDays } = visitData

  // ── First ever visit ─────────────────────────────────────────────────────
  if (visitCount === 1) {
    const opts = ['Good to have you.', "Let's get started.", 'Ready when you are.']
    return opts[Math.floor(Math.random() * opts.length)]
  }

  // ── Long absence (7+ days) ───────────────────────────────────────────────
  if (daysSinceLast >= 14) return "It's been a while — welcome back."
  if (daysSinceLast >= 7)  return "Good to see you again."

  // ── Same-day return (multiple sessions today) ────────────────────────────
  if (daysSinceLast === 0 && visitCount > 1) {
    const opts = [
      'Back for more.',
      'Round two.',
      'Still at it.',
      'Picking up where we left off.',
    ]
    return opts[Math.floor(Math.random() * opts.length)]
  }

  // ── High streak (daily consistency) ─────────────────────────────────────
  if (consecutiveDays >= 14) return `${consecutiveDays} days straight. Impressive.`
  if (consecutiveDays >= 7)  return `${consecutiveDays}-day streak. Keep going.`
  if (consecutiveDays >= 3)  return `${consecutiveDays} days in a row.`

  // ── Time-of-day cues ─────────────────────────────────────────────────────
  if (hour >= 5  && hour < 9)  return 'Early start.'
  if (hour >= 9  && hour < 12) return 'Ready to work.'
  if (hour >= 12 && hour < 14) return 'Midday check-in.'
  if (hour >= 14 && hour < 17) return 'Afternoon focus.'
  if (hour >= 17 && hour < 20) return 'Evening session.'
  if (hour >= 20 && hour < 22) return 'Late push.'
  if (hour >= 22 || hour < 5)  return 'Burning the midnight oil.'

  return 'Welcome back.'
}

function getDynamicGreeting(preferredName: string | null, userEmail: string | null): string {
  const visitData  = updateVisitData()
  const hour       = new Date().getHours()
  const firstName  = getDisplayName(preferredName, userEmail)
  const timeGreet  = getTimeGreeting(hour)
  const context    = getVisitContext(visitData, hour)

  // Late night: collapsed single-line variant
  if (hour >= 22 || hour < 5) {
    return `${timeGreet}, ${firstName}. ${context}`
  }

  // First ever visit: skip time greeting, lead with welcome
  if (visitData.visitCount === 1) {
    return `${context.replace('.', ',')} ${firstName}.`
  }

  return `${timeGreet}, ${firstName}. ${context}`
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
  const STOP = new Set(['a','an','the','is','are','was','were','be','been',
    'i','me','my','we','our','you','your','it','its','and','or','but',
    'so','if','in','on','at','to','of','for','by','with','from','that',
    'this','how','what','why','when','where','who','can','could','should',
    'would','will','do','does','did','have','has','had'])

  const words = text.split(' ').filter(w => w.length > 0)
  const meaningful = words.filter(w => !STOP.has(w.toLowerCase()))

  // Use meaningful words if enough, else fall back to raw words
  const chosen = meaningful.length >= 3 ? meaningful : words
  const title  = chosen.slice(0, 6).join(' ')

  // Capitalise first letter, truncate
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

  fileAttachment?: { name: string; jobType: 'ocr' | 'vision'; url?: string }

  fileAttachments?: { name: string; jobType: 'ocr' | 'vision'; url?: string }[]

  sources?: Source[]

  imageUrl?: string

  imagePending?: boolean

  imagePrompt?: string

  imageJobId?: string

  agentStep?: number

  agentMaxSteps?: number

  agentLabel?: string

  timestamp?: number     // Unix ms — set at send/receive time for relative display

  generatedFiles?: { filename: string; download_url: string; size_bytes: number }[]

  thinkingContent?: string   // Reasoning text from <thinking> blocks (THINK/SOLVE modes)

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
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`)
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(blobUrl)
  } catch (err) {
    console.error("Direct download failed, falling back to window.open:", err)
    window.open(url, '_blank')
  }
}

// ─── Docx Preview Component ───────────────────────────────────────────────────

interface DocxPreviewProps {
  url: string
}

function DocxPreview({ url }: DocxPreviewProps) {
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
    <div className="w-full h-full min-h-[500px] flex flex-col bg-white text-black p-4 rounded-xl overflow-auto select-text relative">
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
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const extLabel = ext.toUpperCase() || 'FILE'
  const sizeLabel = size_bytes > 1024 * 1024
    ? `${(size_bytes / (1024 * 1024)).toFixed(1)} MB`
    : size_bytes > 1024
    ? `${(size_bytes / 1024).toFixed(1)} KB`
    : size_bytes > 0 ? `${size_bytes} B` : ''

  // Determine ext-based accent color
  const extColor: Record<string, string> = {
    py: '#3b82f6', js: '#f59e0b', ts: '#3b82f6', tsx: '#06b6d4', jsx: '#06b6d4',
    pdf: '#ef4444', docx: '#3b82f6', xlsx: '#22c55e', csv: '#22c55e',
    json: '#a78bfa', txt: '#8e95a2', html: '#f97316', css: '#06b6d4',
    png: '#ec4899', jpg: '#ec4899', jpeg: '#ec4899', svg: '#f59e0b', zip: '#8b5cf6',
  }
  const accentColor = extColor[ext] || '#c5a880'

  const hasUrl = download_url && !download_url.startsWith('sandbox:') && !download_url.includes('/mnt/data/')

  return (
    <div className="mt-2 flex items-center gap-3 px-3.5 py-2.5 rounded-xl border border-[#ffffff]/15 bg-[#0d0f11]/60 hover:bg-[#0d0f11]/90 hover:border-[#ffffff]/30 transition-all duration-200 group/dl w-full select-none">
      {/* File type icon */}
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border"
        style={{ background: `${accentColor}18`, borderColor: `${accentColor}30` }}
      >
        <span className="text-[9px] font-black tracking-tight" style={{ color: accentColor }}>{extLabel}</span>
      </div>

      {/* File info */}
      <div className="flex-1 min-w-0">
        <p className="text-[12.5px] font-semibold text-brand-text truncate leading-tight">{filename}</p>
        {sizeLabel && <p className="text-[10px] text-[#8e95a2] mt-0.5">{sizeLabel}</p>}
        {!hasUrl && (
          <p className="text-[10px] text-amber-400/70 mt-0.5">File sync failed — try regenerating</p>
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
            title={`Download ${filename}`}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
        ) : (
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center border border-amber-500/20 bg-amber-500/5 text-amber-500/40 cursor-not-allowed"
            title="File sync failed"
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

// ─── Mermaid block renderer ───────────────────────────────────────────────────

// Lazy-imports mermaid.js on first use. Renders diagram → inline SVG.

// During streaming (isStreaming=true for the last message), skipped.

let _mermaidReady = false

let _mermaidIdCounter = 0

// Validate and clean mermaid code before rendering
function validateMermaidCode(code: string): { valid: boolean, cleanedCode: string, error?: string } {
  if (!code || code.trim().length === 0) {
    return { valid: false, cleanedCode: '', error: 'Empty mermaid code' }
  }

  // Clean up common issues
  let cleaned = code.trim()

  // Remove trailing dashes or other non-mermaid characters at the end
  cleaned = cleaned.replace(/[-]{3,}$/, '')

  // Remove multiple consecutive dashes that might cause parsing errors
  cleaned = cleaned.replace(/[-]{4,}/g, '---')

  // Ensure proper line endings
  cleaned = cleaned.replace(/\r\n/g, '\n')

  // Check for basic mermaid structure
  const validStartPatterns = /^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey|mindmap|gitGraph|C4Context|blockDiagram|architecture|requirementDiagram|objectDiagram|networkDiagram|sankey|xychart|block-beta|timeline|sact|packet|circuit|wireframe|info|piechart|quadrantChart|gitGraph)/i

  if (!validStartPatterns.test(cleaned.split('\n')[0])) {
    return { valid: false, cleanedCode: cleaned, error: 'Invalid mermaid diagram type' }
  }

  // Check for balanced brackets/parentheses (basic check)
  const openBrackets = (cleaned.match(/\[/g) || []).length
  const closeBrackets = (cleaned.match(/\]/g) || []).length
  if (openBrackets !== closeBrackets) {
    return { valid: false, cleanedCode: cleaned, error: 'Unbalanced brackets' }
  }

  const openParens = (cleaned.match(/\(/g) || []).length
  const closeParens = (cleaned.match(/\)/g) || []).length
  if (openParens !== closeParens) {
    return { valid: false, cleanedCode: cleaned, error: 'Unbalanced parentheses' }
  }

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

  const id = useRef(`mermaid-${++_mermaidIdCounter}`).current

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

      setIsLoading(true)

      try {

        // Use validated and cleaned code
        if (!validation.valid) {
          throw new Error(validation.error || 'Invalid mermaid syntax')
        }

        if (!_mermaidReady) {

          const m = await import('mermaid')

          m.default.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' })

          _mermaidReady = true

        }

        const { default: mermaid } = await import('mermaid')

        const { svg } = await mermaid.render(id, validation.cleanedCode)

        if (!cancelled && diagramRef.current) {

          diagramRef.current.innerHTML = svg

        }

      } catch (err: any) {

        console.error('Mermaid rendering error:', err)

        if (!cancelled) {

          if (diagramRef.current) {

            diagramRef.current.innerHTML = `<pre class="text-amber-400 text-xs p-2">Diagram error: ${err?.message || 'invalid syntax'}</pre>`

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

  }, [validation, id, showSource])

  const handleCopy = () => {

    navigator.clipboard.writeText(code).then(() => {

      setCopied(true)

      setTimeout(() => setCopied(false), 1500)

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
      // Clone the SVG and add a dark background
      const svgClone = svgEl.cloneNode(true) as SVGElement
      svgClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

      // Add dark background rectangle
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
      rect.setAttribute('width', '100%')
      rect.setAttribute('height', '100%')
      rect.setAttribute('fill', '#0d1117')
      svgClone.insertBefore(rect, svgClone.firstChild)

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

  if (isLoading) {

    return (

      <div className="my-3 p-4 rounded-xl border border-[#1e2025] bg-[#0d1117]/50">

        <div className="flex items-center gap-2">

          <div className="w-4 h-4 border-2 border-brand-muted/30 border-t-brand-text rounded-full animate-spin" />

          <p className="text-sm text-brand-muted">Rendering diagram...</p>

        </div>

      </div>

    )

  }

  return (

    <div className="group my-3 relative rounded-xl border border-[#1e2025] bg-[#0d1117] overflow-hidden">

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
            className={`p-4 overflow-auto mermaid-diagram-container transition-all duration-300 ${
              isExpanded 
                ? 'min-h-[500px] max-h-[800px]' 
                : 'min-h-[200px] max-h-[400px]'
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
      <div className="my-3 p-3 rounded-xl border border-amber-500/30 bg-amber-500/5 text-amber-400 text-sm">
        Could not render SVG (encoding error).
      </div>
    )
  }

  return (
    <div className="group my-3 relative rounded-xl border border-[#1e2025] bg-[#0d1117] overflow-hidden">
      {/* Controls — top-right, revealed on hover */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        {/* Copy SVG source */}
        <button
          onClick={handleCopy}
          title="Copy SVG source"
          className="flex items-center justify-center w-7 h-7 rounded-md border bg-[#1f1f1f] border-[#30363d] text-[#7d8590] hover:text-[#c9d1d9] hover:border-[#484f58] transition-colors"
        >
          {copied
            ? <svg width="13" height="13" viewBox="0 0 16 16" fill="#3fb950"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>
            : <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 010 1.5h-1.5a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-1.5a.75.75 0 011.5 0v1.5A1.75 1.75 0 019.25 16h-7.5A1.75 1.75 0 010 14.25v-7.5z"/><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0114.25 11h-7.5A1.75 1.75 0 015 9.25v-7.5zm1.75-.25a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25h-7.5z"/></svg>
          }
        </button>
        {/* Fullscreen */}
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

// ─── Thinking block renderer ────────────────────────────────────────────────
// Collapsible panel showing the model's live reasoning trace.
// Only rendered for THINK/SOLVE modes. Streams in real-time, finalised after
// the model emits </thinking>. Content is kept separate from the clean answer.

function ThinkingBlock({ content, streaming }: { content: string; streaming?: boolean }) {
  const [open, setOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (streaming && open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [content, streaming, open])

  return (
    <div className="my-2 rounded-xl border border-purple-500/20 bg-purple-950/20 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-purple-300/80 hover:text-purple-200 transition-colors"
      >
        <Brain className="w-3.5 h-3.5 shrink-0 text-purple-400" />
        <span className="font-medium tracking-wide text-xs uppercase">Reasoning</span>
        {streaming && (
          <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
        )}
        <ChevronDown
          className={`w-3.5 h-3.5 ml-auto transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div
          ref={scrollRef}
          className="px-4 pb-4 pt-3 border-t border-purple-500/10 text-[11px] text-purple-200/60 font-mono whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto"
        >
          {content || '…'}
        </div>
      )}
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

  // During streaming, skip block parsing — use the fast prose renderer

  if (isCurrentlyStreaming) return renderMarkdown(text)

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
  return <span className="font-mono">{displayMode ? `$$${tex}$$` : `$${tex}$`}</span>
}

function renderInline(text: string, keyBase: string, generatedFiles?: any[]): React.ReactNode {

  const pattern = /(\$\$([\s\S]*?)\$\$|\$(?!\s)([^\$]+?)(?<!\s)\$|\*\*(.*?)\*\*|\*(.*?)\*|`(.*?)`|\[(.*?)\]\((.*?)\)|(https?:\/\/[^\s\)<>"]+))/g

  const segments: React.ReactNode[] = []

  let lastIndex = 0

  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {

    if (match.index > lastIndex) {

      segments.push(<span key={`${keyBase}-t${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>)

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

      // Resolve sandbox paths
      if ((url.includes('/mnt/data/') || url.startsWith('sandbox:')) && generatedFiles) {
        const filename = url.split('/').pop() || '';
        const matchingFile = generatedFiles.find(gf =>
          gf.filename?.toLowerCase() === filename.toLowerCase() ||
          gf.filename?.toLowerCase().endsWith(filename.toLowerCase())
        );
        if (matchingFile && matchingFile.download_url) {
          url = matchingFile.download_url;
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

      const isSandboxLink = (url.startsWith('sandbox:') || url.includes('/mnt/data/')) &&
        !(url.startsWith('https://') || url.startsWith('http://'));

      segments.push(

        isSandboxLink ? (

          <a

            key={`${keyBase}-l${match.index}`}

            href="#"

            onClick={(e) => {

              e.preventDefault();

              alert("This file remains in the secure code execution sandbox and could not be synced to public storage. Please try regenerating the file.");

            }}

            className="text-[#ffffff]/50 hover:text-[#ffffff]/40 line-through cursor-not-allowed transition duration-150"

            title="File sync failed"

          >

            {label}

          </a>

        ) : (

          <a

            key={`${keyBase}-l${match.index}`}

            href={url}

            target="_blank"

            rel="noopener noreferrer"

            onClick={(e) => {
              const lowerUrl = url.toLowerCase()
              const isDownloadable = lowerUrl.endsWith('.docx') || lowerUrl.endsWith('.dotx') || lowerUrl.endsWith('.xlsx') || lowerUrl.endsWith('.zip') || lowerUrl.includes('/generated/') || lowerUrl.includes('r2.dev') || lowerUrl.includes('blob.core.windows.net')
              if (isDownloadable) {
                e.preventDefault()
                triggerDirectDownload(url, label || 'download')
              }
            }}

            className="text-[#ffffff] hover:text-[#f3f4f6] underline underline-offset-4 decoration-[#ffffff]/40 transition duration-150"

          >

            {label}

          </a>

        )

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
        className="relative rounded-2xl overflow-hidden border border-[#1e2025] shadow-xl shadow-black/50 w-fit max-w-sm cursor-pointer"
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
            className="opacity-0 group-hover/img:opacity-100 transition-opacity duration-200 flex items-center gap-1.5 px-3 py-1.5 bg-[#ffffff] text-[#08090a] rounded-lg text-[10px] font-bold tracking-wider uppercase shadow-lg"
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

const CodeView: React.FC<{ language: string; content: string }> = ({ language, content }) => {
  const lines = useMemo(() => content.split('\n'), [content])
  const highlightedHtml = useMemo(() => highlightCode(content, language), [content, language])
  const highlightedLines = useMemo(() => highlightedHtml.split('\n'), [highlightedHtml])

  return (
    <div className="flex font-mono text-[11px] sm:text-[11.5px] leading-relaxed select-text overflow-x-auto text-[#abb2bf] bg-[#07080a] p-4.5 rounded-xl border border-[#1e2025]">
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
    <div className="group relative border-l-2 border-[#ffffff]/80 bg-[#ffffff]/4 pl-4 pr-10 py-3.5 my-4 italic text-brand-text/85 rounded-r-lg select-text">
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-lg border border-[#1e2025] bg-[#0d0f11]/60 hover:bg-[#ffffff]/5 text-[#8e95a2] hover:text-brand-text opacity-0 group-hover:opacity-100 transition duration-150 active:scale-95"
        title="Copy template"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-[#3fb950]" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
      <div className="text-[13px] leading-relaxed">
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

    <div className="group relative bg-[#0b0c0e] border border-[#1a1d20]/80 rounded-xl overflow-hidden my-4 shadow-lg">

      {/* Split-button — top-right, reveal on hover */}

      <div ref={menuRef} className="absolute top-2 right-2 z-20 flex items-center opacity-0 group-hover:opacity-100 transition-opacity duration-150">

        {/* Copy */}

        <button

          onClick={handleCopy}

          className="flex items-center gap-1.5 px-2.5 h-7 text-[11px] font-medium rounded-l-md border border-r-0 border-[#30363d] bg-[#161b22] text-[#8b949e] hover:text-[#c9d1d9] hover:bg-[#21262d] transition-colors select-none"

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

            className="flex items-center justify-center px-2 h-7 rounded-r-md border border-[#30363d] bg-[#161b22] text-[#8b949e] hover:text-[#c9d1d9] hover:bg-[#21262d] transition-colors"

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

      <pre className="p-4 pb-7 overflow-x-auto">

        <code className="text-[11.5px] font-mono text-[#d4c5a0]/85 leading-relaxed block whitespace-pre">

          {content}

        </code>

      </pre>

    </div>

  )

}

const SourcesStack: React.FC<{ sources: Source[] }> = ({ sources }) => {

  const [isOpen, setIsOpen] = useState(false)

  // Get unique hosts/domains for the favicons

  const uniqueHosts = React.useMemo(() => {

    const hosts: string[] = []

    const seen = new Set<string>()

    for (const src of sources) {

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

  }, [sources])

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

            {sources.length} {sources.length === 1 ? 'site' : 'sites'}

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

          {sources.map((src, si) => (

            <a

              key={si}

              href={src.url}

              target="_blank"

              rel="noopener noreferrer"

              title={src.title || src.url}

              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-[#1e2025] bg-[#0c0d10]/95 hover:border-[#ffffff]/30 hover:bg-[#ffffff]/5 transition-all duration-200 group/badge max-w-[240px] shadow-sm animate-fadeIn"

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

    }

  }

  return blocks

}

// ─── Block markdown renderer ──────────────────────────────────────────────────

export function renderMarkdown(text: string, generatedFiles?: any[]): React.ReactNode {

  const blocks = parseMarkdownToBlocks(text)

  return (

    <div className="space-y-4">

      {blocks.map((block, index) => {

        const key = `block-${index}`

        switch (block.type) {

          case 'heading': {

            const level = block.level || 1

            const content = renderInline(block.content || '', key, generatedFiles)

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

              <div key={key} className="overflow-x-auto my-5 border border-[#1a1d20]/50 rounded-xl bg-black/20">

                <table className="min-w-full divide-y divide-[#1a1d20]/30 text-left text-[12.5px]">

                  <thead className="bg-[#1c1e22]/50 text-[#f0ece4]">

                    <tr>

                      {block.headers?.map((header, hIdx) => (

                        <th

                          key={hIdx}

                          className="px-4 py-3 font-semibold border-b border-[#1a1d20]/30 tracking-wider text-[11px] uppercase text-[#ffffff]/80"

                        >

                          {renderInline(header, `${key}-th-${hIdx}`, generatedFiles)}

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

                <ol key={key} className="my-3 space-y-2 pl-1">

                  {block.items?.map((item, j) => (

                    <li key={j} className="flex gap-2.5 leading-relaxed items-start">

                      <span className="text-[#ffffff] font-semibold text-[11.5px] shrink-0 min-w-[1.25rem] mt-[1.5px]">

                        {j + 1}.

                      </span>

                      <span className="text-[13px] text-brand-text/85">

                        {renderInline(item, `${key}-oli-${j}`, generatedFiles)}

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

                      <span className="text-[#ffffff] text-[8px] mt-[6.5px] shrink-0 select-none">◆</span>

                      <span className="text-[13px] text-brand-text/85">

                        {renderInline(item, `${key}-uli-${j}`, generatedFiles)}

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

                {renderInline(block.content || '', key, generatedFiles)}

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

const AgentStepIndicator: React.FC<{ step: number; maxSteps: number; label?: string; isComplete?: boolean }> = ({ step, maxSteps, label, isComplete }) => (

  <div className="flex items-center gap-2.5 mb-3 select-none animate-fadeIn">

    {/* Spinning cog / Checkmark */}

    <div className="relative flex-shrink-0">

      {isComplete ? (

        <div className="w-5 h-5 rounded-full bg-green-500/10 border border-green-500/30 flex items-center justify-center animate-fadeIn">

          <Check className="w-3 h-3 text-green-400" />

        </div>

      ) : (

        <div className="w-5 h-5 rounded-full border border-[#ffffff]/30 border-t-[#ffffff] animate-spin" />

      )}

    </div>

    {/* Step pill */}

    <div className="flex items-center gap-2">

      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#ffffff]/10 border border-[#ffffff]/20 text-[10px] font-bold text-[#ffffff] tracking-widest uppercase">

        Step {step}

        {!isComplete && (

          <span className="text-[#ffffff]/40 font-normal">/ {maxSteps}</span>

        )}

      </span>

      {label && (

        <span className="text-[11px] text-[#8e95a2] font-medium truncate max-w-[240px]">{label}</span>

      )}

    </div>

  </div>

)

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
  attachment: { name: string; jobType: 'ocr' | 'vision'; url?: string }
}> = ({ attachment }) => {
  const handlePreview = () => {
    if (!attachment.url) return
    const isPdf = attachment.jobType === 'ocr' || attachment.name.toLowerCase().endsWith('.pdf')
    const event = new CustomEvent('open-file-preview', {
      detail: {
        name: attachment.name,
        type: isPdf ? 'application/pdf' : 'image/png',
        url: attachment.url
      }
    })
    window.dispatchEvent(event)
  }

  return attachment.jobType === 'vision' && attachment.url ? (
    <div 
      onClick={handlePreview}
      className="w-full max-w-sm rounded-xl overflow-hidden border border-[#ffffff]/10 bg-[#111316]/20 cursor-pointer hover:border-[#ffffff]/25 transition"
    >
      <img
        src={attachment.url}
        alt={attachment.name}
        className="w-full h-auto max-h-64 object-contain"
      />
    </div>
  ) : (
    <div 
      onClick={handlePreview}
      className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-[#ffffff]/8 border border-[#ffffff]/20 cursor-pointer hover:bg-[#ffffff]/15 transition"
    >
      <FileText className="w-4 h-4 text-[#ffffff] shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-bold text-[#ffffff] uppercase tracking-widest leading-none">
          {attachment.jobType === 'ocr' ? 'Document Analysis' : 'Image Analysis'}
        </p>
        <p className="text-[13px] text-brand-text/90 font-medium truncate mt-1">
          {attachment.name}
        </p>
      </div>
    </div>
  )
}

const LazyMessage: React.FC<{
  children: React.ReactNode
  estimatedHeight?: number
}> = ({ children, estimatedHeight = 100 }) => {
  const [isVisible, setIsVisible] = useState(false)
  const [hasBeenVisible, setHasBeenVisible] = useState(false)
  const [renderedHeight, setRenderedHeight] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting)
        if (entry.isIntersecting) {
          setHasBeenVisible(true)
        }
      },
      {
        rootMargin: '800px 0px 800px 0px'
      }
    )
    observer.observe(el)
    return () => {
      observer.unobserve(el)
    }
  }, [])

  useEffect(() => {
    if (isVisible && ref.current) {
      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const height = entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height
          if (height > 0) {
            setRenderedHeight(height)
          }
        }
      })
      observer.observe(ref.current)
      return () => {
        observer.disconnect()
      }
    }
  }, [isVisible])

  const heightToUse = renderedHeight !== null ? `${renderedHeight}px` : `${estimatedHeight}px`

  return (
    <div 
      ref={ref} 
      style={{ 
        minHeight: heightToUse,
        height: hasBeenVisible ? undefined : heightToUse 
      }}
    >
      {hasBeenVisible ? children : <div className="h-full w-full" />}
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

export const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [preferredName, setPreferredName] = useState<string | null>(null)
  // Stable ref holding the Supabase userId — set once on auth, used for cache key scoping.
  const userIdRef = useRef<string | null>(null)
  const [isFetchingHistory, setIsFetchingHistory] = useState(false)
  const [dynamicGreeting, setDynamicGreeting] = useState<string>('Agent Ochuko')
  const [isEditingNickname, setIsEditingNickname] = useState(false)
  const [nicknameInput, setNicknameInput] = useState('')

  const [isLocked, setIsLocked] = useState(() => !!localStorage.getItem('app_lock_pin'))
  const [lockMode, setLockMode] = useState<'unlock' | 'setup' | 'change' | 'disable' | null>(null)

  const [isDesktop, setIsDesktop] = useState(() => window.innerWidth >= 1024)
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('sidebar_width')
    if (saved) return parseInt(saved, 10)
    // Default to 90% of viewport width, constrained between 220px and 480px
    const defaultWidth = Math.floor(window.innerWidth * 0.9)
    return Math.max(220, Math.min(480, defaultWidth))
  })
  const [pageZoom, setPageZoom] = useState(() => {
    const saved = localStorage.getItem('page_zoom')
    return saved ? parseFloat(saved) : 1.0
  })
  const isResizingRef = useRef(false)

  useEffect(() => {
    const handleResize = () => {
      setIsDesktop(window.innerWidth >= 1024)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Update dynamic greeting when user data changes
  useEffect(() => {
    const greeting = getDynamicGreeting(preferredName, userEmail)
    setDynamicGreeting(greeting)
  }, [preferredName, userEmail])

  // Apply zoom to document
  useEffect(() => {
    document.documentElement.style.zoom = pageZoom.toString()
    localStorage.setItem('page_zoom', pageZoom.toString())
  }, [pageZoom])

  const startResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isResizingRef.current = true
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

  const [input, setInput] = useState('')

  // Read prompt from URL parameter (e.g., from capabilities page play buttons)
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search)
    const promptParam = searchParams.get('prompt')
    if (promptParam) {
      setInput(decodeURIComponent(promptParam))
      // Clear the URL parameter to prevent re-triggering
      window.history.replaceState({}, '', window.location.pathname)
      // Focus on input so user can easily send
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [location.search])

  const [isStreaming, setIsStreaming] = useState(false)

  // Mode also deferred — will be restored in the getUser() useEffect below.
  const [mode, setMode] = useState<'think' | 'solve' | 'discuss'>('discuss')

  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const [isSidebarHovered, setIsSidebarHovered] = useState(false)

  const [isOnline, setIsOnline] = useState(navigator.onLine)

  const [isShareModalOpen, setIsShareModalOpen] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [showCapabilitiesNote, setShowCapabilitiesNote] = useState(() => !localStorage.getItem('dismissed_capabilities_note'))

  const handleShareToggle = async (shouldShare: boolean) => {
    if (!activeConversationId || activeConversationId === '00000000-0000-0000-0000-000000000000') return
    setSharing(true)
    try {
      const token = localStorage.getItem('supabase_token') || (await supabase.auth.getSession()).data.session?.access_token
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
          const shareUrl = `${window.location.origin}/shared/${data.share_token}`
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

  interface Artifact {
    filename: string
    downloadUrl?: string
    content?: string
    sizeBytes?: number
  }

  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null)
  const [artifactTab, setArtifactTab] = useState<'preview' | 'code'>('preview')
  const [artifactContent, setArtifactContent] = useState<string>('')
  const [loadingArtifact, setLoadingArtifact] = useState(false)
  const [artifactError, setArtifactError] = useState<string | null>(null)
  const [artifactWidth, setArtifactWidth] = useState(480)
  const isArtifactResizingRef = useRef(false)

  const [isArtifactExpanded, setIsArtifactExpanded] = useState(false)
  const [copiedArtifact, setCopiedArtifact] = useState(false)
  const [isHeaderSettingsOpen, setIsHeaderSettingsOpen] = useState(false)
  const [isArtifactCopyOpen, setIsArtifactCopyOpen] = useState(false)
  const headerSettingsRef = useRef<HTMLDivElement>(null)
  const artifactCopyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isHeaderSettingsOpen) return
    const handler = (e: MouseEvent) => {
      if (headerSettingsRef.current && !headerSettingsRef.current.contains(e.target as Node)) {
        setIsHeaderSettingsOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isHeaderSettingsOpen])

  useEffect(() => {
    if (!isArtifactCopyOpen) return
    const handler = (e: MouseEvent) => {
      if (artifactCopyRef.current && !artifactCopyRef.current.contains(e.target as Node)) {
        setIsArtifactCopyOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isArtifactCopyOpen])

  const startArtifactResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isArtifactResizingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isArtifactResizingRef.current) return
      const newWidth = Math.max(320, Math.min(window.innerWidth - 300, window.innerWidth - e.clientX))
      setArtifactWidth(newWidth)
    }
    const handleMouseUp = () => {
      if (!isArtifactResizingRef.current) return
      isArtifactResizingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  useEffect(() => {
    if (!activeArtifact) {
      setArtifactContent('')
      setArtifactError(null)
      return
    }
    const ext = activeArtifact.filename.toLowerCase().split('.').pop() || ''
    const isPreviewable = ['html', 'htm', 'svg', 'md', 'markdown', 'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt'].includes(ext)
    setArtifactTab(isPreviewable ? 'preview' : 'code')

    if (activeArtifact.content !== undefined) {
      setArtifactContent(activeArtifact.content)
      setArtifactError(null)
      return
    }
    if (activeArtifact.downloadUrl) {
      if (isBinaryFile(activeArtifact.filename) || activeArtifact.filename.toLowerCase().endsWith('.pdf')) {
        setArtifactContent('')
        setArtifactError(null)
        setLoadingArtifact(false)
        return
      }
      setLoadingArtifact(true)
      setArtifactError(null)
      fetch(activeArtifact.downloadUrl)
        .then(res => {
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`)
          }
          return res.text()
        })
        .then(text => {
          setArtifactContent(text)
          setLoadingArtifact(false)
        })
        .catch((err) => {
          setArtifactError(err.message || 'Failed to load artifact content')
          setLoadingArtifact(false)
        })
    }
  }, [activeArtifact])

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      setActiveArtifact({
        filename: detail.filename,
        content: detail.content,
        downloadUrl: ''
      })
    }
    window.addEventListener('open-artifact', handler)
    return () => window.removeEventListener('open-artifact', handler)
  }, [])



  const isBinaryFile = (filename: string) => {
    const ext = filename.toLowerCase().split('.').pop() || ''
    return ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'zip', 'tar', 'gz', '7z', 'rar', 'exe', 'bin'].includes(ext)
  }

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

  const [agentMaxSteps, setAgentMaxSteps] = useState<number>(10)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const isAutoScrollEnabledRef = useRef<boolean>(true)

  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)

  const [editingMessageText, setEditingMessageText] = useState("")

  const abortControllerRef = useRef<AbortController | null>(null)

  interface AttachedFile {
    name: string
    type: string
    blobUrl: string
    fileId: string
  }

  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])

  const [previewingFile, setPreviewingFile] = useState<{
    name: string
    type: string
    url?: string
    content?: string
  } | null>(null)

  useEffect(() => {
    const handleOpenPreview = (e: Event) => {
      const customEvent = e as CustomEvent
      setPreviewingFile(customEvent.detail)
    }
    window.addEventListener('open-file-preview', handleOpenPreview)
    return () => window.removeEventListener('open-file-preview', handleOpenPreview)
  }, [])

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

  // ── Voice-to-text hook ─────────────────────────────────────────────────────
  const voice = useVoice((text: string) => setInput(prev => prev + text))

  // toggleVoiceRef — stable ref so keyboard handler can call toggleVoice before it is declared
  const toggleVoiceRef = useRef<(() => Promise<void>) | null>(null)

  // ── Inline rename state ─────────────────────────────────────────────────────

  const [renamingConvoId, setRenamingConvoId] = useState<string | null>(null)

  const [renameValue, setRenameValue] = useState('')

  const renameInputRef = useRef<HTMLInputElement>(null)

  const hasRestoredRef = useRef(false)

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
      el.style.height = 'auto'
      el.style.height = `${el.scrollHeight}px`
    }
  }, [input])

  // activeConversationId starts as null sentinel until auth resolves.
  const [activeConversationId, setActiveConversationId] = useState<string>('00000000-0000-0000-0000-000000000000')

  const uploadFile = async (file: File) => {
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

      setAttachedFiles(prev => [
        ...prev,
        {
          name: file.name,
          type: file.type,
          blobUrl: blob_url,
          fileId: file_id
        }
      ])
    } catch (err: any) {
      console.error('File upload error:', err)
      alert(`File upload failed: ${err.message || err}`)
    } finally {
      setUploading(false)
      setUploadProgress(null)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }

  const handlePaste = async (e: React.ClipboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const files = e.clipboardData.files
    if (files && files.length > 0) {
      e.preventDefault()
      for (let i = 0; i < files.length; i++) {
        await uploadFile(files[i])
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
      setPastedText({
        content: text,
        name: title,
        sizeBytes: new Blob([text]).size,
      })
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
    setActiveConversationId('00000000-0000-0000-0000-000000000000')
    const uid = userIdRef.current
    if (uid) localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), '00000000-0000-0000-0000-000000000000')
    
    // Reset mode to discuss
    setMode('discuss')
    
    // Close sidebar
    setIsSidebarOpen(false)
    
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

    // --- SWR Cache Read ---
    const uid = userIdRef.current
    const cacheKey = uid ? userCacheKey(uid, `convo_cache_${id}`) : `convo_cache_${id}`
    const cachedData = localStorage.getItem(cacheKey)
    if (cachedData) {
      try {
        const parsed = JSON.parse(cachedData)
        if (parsed && Array.isArray(parsed.messages)) {
          setMessages(parsed.messages)
          setMode(convoMode)
          setActiveConversationId(id)
          if (uid) localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), id)
        }
      } catch (e) {
        console.warn("Failed to load cached conversation:", e)
      }
    } else {
      // Clear if no cache to avoid flicker
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

      if (msgRes.ok) {

        const data = await msgRes.json()

        const mapped: Message[] = []

        for (let idx = 0; idx < data.length; idx++) {

          const m = data[idx]

          if (m.role === 'system') {

            // Match R2 / Azure Blob URLs which may have query strings
            const match = m.content.match(/File URL:\s*(https?:\/\/\S+)/i)

            if (match && mapped.length > 0) {

              // Strip trailing punctuation (not query strings)
              const url = match[1].replace(/[),.'"]+$/, '')

              // Walk backwards to find the nearest user message to map this URL to
              for (let mi = mapped.length - 1; mi >= 0; mi--) {

                const candidate = mapped[mi]

                if (candidate.role === 'user') {

                  // 1. Single attachment compatibility
                  if (candidate.fileAttachment && !candidate.fileAttachment.url) {
                    candidate.fileAttachment.url = url
                    break
                  }

                  // 2. Multiple attachments
                  if (candidate.fileAttachments && candidate.fileAttachments.length > 0) {
                    // Try to match by filename in URL
                    const matchingAttachment = candidate.fileAttachments.find(
                      att => !att.url && url.toLowerCase().includes(att.name.toLowerCase())
                    )
                    if (matchingAttachment) {
                      matchingAttachment.url = url
                      break
                    }
                    // Fallback to the first empty URL slot
                    const emptyAttachment = candidate.fileAttachments.find(att => !att.url)
                    if (emptyAttachment) {
                      emptyAttachment.url = url
                      break
                    }
                  }

                }

              }

            }

            continue

          }

          const msgObj: Message = {

            role: m.role,

            content: m.content,

            routing_mode: m.routing_mode,

            routing_reason: m.routing_reason,

            sources: m.content_parts?.sources || undefined,

            imageUrl: m.content_parts?.image_jobs?.[0]?.image_url || undefined,

            imagePrompt: m.content_parts?.image_jobs?.[0]?.prompt || undefined,

            imagePending: m.content_parts?.image_jobs?.[0]?.status === 'pending' || undefined,

          }

          if (m.role === 'user') {

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

          mapped.push(msgObj)

        }

        // Attach generated files to the last assistant message (best-effort)

        if (filesRes?.ok) {

          const files: any[] = await filesRes.json()

          if (files.length > 0) {

            // Find the last assistant message to attach files to

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

        setMessages(mapped)

        setActiveConversationId(id)

        const uid2 = userIdRef.current
        if (uid2) localStorage.setItem(userCacheKey(uid2, 'active_conversation_id'), id)

        setMode(convoMode)

        // --- SWR Cache Write ---
        saveConvoCache(userIdRef.current, id, mapped, convoMode)

        setIsSidebarOpen(false)

        setTimeout(() => inputRef.current?.focus(), 0)

      }

    } catch (e) {

      console.error("Failed to load message history:", e)

    } finally {

      setIsFetchingHistory(false)

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

    setTimeout(() => inputRef.current?.focus(), 0)

  }

  useEffect(() => {

    supabase.auth.getUser().then(({ data: { user } }) => {

      if (user) {

        const uid = user.id
        userIdRef.current = uid
        setUserEmail(user.email || 'User')

        const metadata = user.user_metadata || {}
        const name = metadata.preferred_name || metadata.full_name || metadata.name || user.email?.split('@')[0] || 'User'
        setPreferredName(name)

        // Clear active conversation cache if this is a brand new login/tab session
        const isFreshSession = !sessionStorage.getItem('session_started')
        if (isFreshSession) {
          sessionStorage.setItem('session_started', 'true')
          localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), '00000000-0000-0000-0000-000000000000')
        }

        // ── Hydrate from user-scoped cache (safe now that we know who this is) ──
        try {
          const cachedId = localStorage.getItem(userCacheKey(uid, 'active_conversation_id'))
          if (cachedId && cachedId !== '00000000-0000-0000-0000-000000000000') {
            setActiveConversationId(cachedId)
            const raw = localStorage.getItem(userCacheKey(uid, `convo_cache_${cachedId}`))
            if (raw) {
              const parsed = JSON.parse(raw)
              if (Array.isArray(parsed.messages)) setMessages(parsed.messages)
              if (parsed.mode) setMode(parsed.mode)
            }
          } else {
            // Start fresh session by default on new login
            setActiveConversationId('00000000-0000-0000-0000-000000000000')
            setMessages([])
            setMode('discuss')
          }
          // Also hydrate sidebar conversations from cache for instant load
          try {
            const cachedConvos = localStorage.getItem(userCacheKey(uid, 'local_conversations'))
            if (cachedConvos) setConversations(JSON.parse(cachedConvos))
          } catch {}
        } catch {}

        fetchConversations()

      }

    })

  }, [])

  useEffect(() => {
    if (hasRestoredRef.current || conversations.length === 0) return
    const uid = userIdRef.current
    const cachedIdKey = uid ? userCacheKey(uid, 'active_conversation_id') : null
    const cachedId = cachedIdKey ? localStorage.getItem(cachedIdKey) : null
    if (cachedId && cachedId !== '00000000-0000-0000-0000-000000000000') {
      const cachedConvo = conversations.find(c => c.id === cachedId)
      if (cachedConvo) {
        hasRestoredRef.current = true
        handleSelectConversation(cachedConvo.id, cachedConvo.mode || 'discuss')
      }
    }
  }, [conversations])

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


  // Auto-scroll on new content only if user is already at the bottom

  useEffect(() => {

    const container = scrollContainerRef.current

    if (container && isAutoScrollEnabledRef.current) {

      container.scrollTop = container.scrollHeight

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

  const triggerStream = async (history: Message[], newUserMessage: string | Message, overrideConvoId?: string) => {

    // 1. Abort any active stream before launching a new one

    if (abortControllerRef.current) {

      abortControllerRef.current.abort()

    }

    const abortController = new AbortController()

    abortControllerRef.current = abortController

    setIsStreaming(true)

    setWebSearchStatus('idle')

    let currentConvoId = overrideConvoId || activeConversationId

    const userMessageObj: Message = typeof newUserMessage === 'string'

      ? { role: 'user', content: newUserMessage }

      : newUserMessage

    // Append the new user message and an assistant placeholder

    const nextMessages: Message[] = [...history, userMessageObj]

    setMessages([...nextMessages, { role: 'assistant', content: '', timestamp: Date.now() }])

    try {

      const session = await supabase.auth.getSession()

      const token = session.data.session?.access_token

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

          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,

          local_time: new Date().toString(),

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
              setConversations(prev => {
                const existing = prev.find(c => c.id === convId)
                // Only auto-title if this is genuinely a new/untitled conversation
                if (existing && existing.title) return prev
                const firstUserMsg = userMessageObj.content
                const autoTitle = generateAutoTitle(firstUserMsg)
                // Optimistic update in sidebar
                if (existing) {
                  return prev.map(c => c.id === convId ? { ...c, title: autoTitle } : c)
                }
                // New convo not yet in list — will appear after fetchConversations
                return prev
              })

              // Patch title on server in the background (non-blocking)
              setTimeout(async () => {
                try {
                  const existing = conversations.find(c => c.id === convId)
                  if (existing?.title) return // already has a real title
                  const firstUserMsg = userMessageObj.content
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

                imgChannel.unsubscribe()

              }

              // 90s stall guard timeout

              const stallTimeout = setTimeout(() => {

                setMessages((prev) =>

                  prev.map((m) =>

                    m.imagePending && (m.imageJobId === imgJobId || m.imagePrompt === imgPrompt)

                      ? { ...m, imagePending: false, imageJobId: undefined, content: m.content + '\n\nImage generation timed out. Please try again.' }

                      : m

                  )

                )

                cleanupJob()

              }, 90_000)

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

            } else if (data.type === 'memory_written') {

              // Agent stored a fact — show a transient toast so the user sees it

              showToast(`Remembered: ${data.key}`, 'info')

            } else if (data.type === 'thinking_start') {

              // Model started reasoning — open the thinking panel (initialise empty)
              setMessages((prev) => {
                const updated = [...prev]
                if (updated.length > 0) {
                  const last = updated[updated.length - 1]
                  updated[updated.length - 1] = { ...last, thinkingContent: '' }
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
                setMessages((prev) => {
                  const updated = [...prev]
                  if (updated.length > 0) {
                    const last = updated[updated.length - 1]
                    updated[updated.length - 1] = {
                      ...last,
                      generatedFiles: [...(last.generatedFiles || []), ...newFiles],
                    }
                  }
                  return updated
                })
              }

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
        if (currentConvoId && currentConvoId !== '00000000-0000-0000-0000-000000000000') {
          const uid = userIdRef.current
          setMessages(prev => {
            // Defer localStorage writes to the event loop so they never block React's render thread or cut message flow
            setTimeout(() => {
              try {
                if (uid) {
                  localStorage.setItem(userCacheKey(uid, 'active_conversation_id'), currentConvoId)
                }
                saveConvoCache(uid, currentConvoId, prev, mode)
              } catch (err) {
                console.warn('Deferred cache write failed:', err)
              }
            }, 0)
            return prev
          })
        }

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
    if (!files || files.length === 0) return
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

    let convoId = activeConversationId

    const isNewConvo = !convoId || convoId === '00000000-0000-0000-0000-000000000000'

    if (isNewConvo) {

      convoId = crypto.randomUUID()

      setActiveConversationId(convoId)

      const uidA = userIdRef.current
      if (uidA) localStorage.setItem(userCacheKey(uidA, 'active_conversation_id'), convoId)

    }

    const attachments = files.map(f => {

      const isPdf = f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')

      return {

        name: f.name,

        jobType: (isPdf ? 'ocr' : 'vision') as 'ocr' | 'vision',

        url: f.blobUrl

      }

    })

    const fileNames = files.map(f => f.name).join(', ')

    const userMsgText = promptText

      ? `[Analysis for: ${fileNames}] ${promptText}`

      : `[Analysis for: ${fileNames}]`

    setMessages((prev) => [

      ...prev,

      { role: 'user', content: userMsgText, fileAttachments: attachments },

      { role: 'assistant', content: 'Cognitive model preparing backend analysis tasks...' }

    ])

    try {

      const session = await supabase.auth.getSession()

      const token = session.data.session?.access_token

      if (!token) throw new Error('Authentication session not found.')

      // 1. Launch all jobs in parallel

      const jobPromises = files.map(async (file) => {

        const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')

        const jobType = isPdf ? 'ocr' : 'vision'

        const endpoint = isPdf ? '/v1/agents/ocr' : '/v1/agents/vision'

        const requestBody = isPdf

          ? { conversation_id: convoId, blob_url: file.blobUrl }

          : { conversation_id: convoId, blob_url: file.blobUrl, prompt: promptText || 'Describe the content in this image.' }

        const res = await fetch(`${API_BASE}${endpoint}`, {

          method: 'POST',

          headers: {

            'Content-Type': 'application/json',

            Authorization: `Bearer ${token}`

          },

          body: JSON.stringify(requestBody)

        })

        if (!res.ok) {

          let errDetail = `The document analysis service failed for ${file.name}.`

          try {

            const errBody = await res.json()

            errDetail = errBody?.detail || errBody?.message || errDetail

          } catch (_) {

            try {

              errDetail = (await res.text()) || errDetail

            } catch (_) {}

          }

          throw new Error(errDetail)

        }

        const { job_id } = await res.json()

        return { file, job_id, jobType }

      })

      const queuedJobs = await Promise.all(jobPromises)

      // 2. Track status of all jobs

      const results: { file: AttachedFile; text: string; success: boolean }[] = []

      const pollJobs = queuedJobs.map(async ({ file, job_id }) => {

        return new Promise<void>((resolve) => {

          // Stall timer per job (90 seconds)

          const stallTimer = setTimeout(() => {

            channel.unsubscribe()

            results.push({ file, text: 'Analysis job timeout.', success: false })

            resolve()

          }, 90_000)

          const channel = supabase

            .channel(`job-${job_id}`)

            .on(

              'postgres_changes',

              { event: 'UPDATE', schema: 'public', table: 'jobs', filter: `id=eq.${job_id}` },

              async (payload) => {

                const updatedJob = payload.new

                if (updatedJob.status === 'processing') {

                   setMessages((prev) => {

                     const next = [...prev]

                     next[next.length - 1] = {

                       role: 'assistant',

                       content: `Analyzing ${file.name}: processing layouts and extracting content...`

                     }

                     return next

                   })

                } else if (updatedJob.status === 'done') {

                  clearTimeout(stallTimer)

                  const textResult = updatedJob.result?.text || 'No result data returned by the agent.'

                  channel.unsubscribe()

                  try {

                    await supabase.from('messages').insert([

                      {

                        conversation_id: convoId,

                        role: 'system',

                        content: `[System Context: The user has attached a file. File URL: ${file.blobUrl}. Analysis result: ${textResult}]`,

                        routing_mode: 'discuss'

                      }

                    ])

                  } catch (dbErr) {

                    console.error('Failed to commit system context to history:', dbErr)

                  }

                  results.push({ file, text: textResult, success: true })

                  resolve()

                } else if (updatedJob.status === 'failed') {

                  clearTimeout(stallTimer)

                  channel.unsubscribe()

                  results.push({ file, text: updatedJob.error || 'Background analysis encountered an error.', success: false })

                  resolve()

                }

              }

            )

          channel.subscribe()

        })

      })

      // Wait for all analyses to complete

      await Promise.all(pollJobs)

      const failedJobs = results.filter(r => !r.success)

      if (failedJobs.length > 0) {

        console.warn('Some file analysis jobs failed:', failedJobs)

      }

      // 3. Trigger the LLM stream response

      await triggerStream(historyBeforeJobs, {

        role: 'user',

        content: userMsgText,

        fileAttachments: attachments

      }, convoId)

    } catch (err: any) {

      console.error('Agent job trigger failed:', err)

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

      convoId = crypto.randomUUID()

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

    if (attachedFiles.length > 0) {

      const filesToProcess = [...attachedFiles]

      const promptText = input.trim()

      setInput('')

      setAttachedFiles([])

      setTimeout(() => inputRef.current?.focus(), 0)

      await triggerAgentJobs(filesToProcess, promptText)

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

      {(isSidebarOpen || isSidebarHovered) && !isDesktop && (

        <div

          onClick={() => { setIsSidebarOpen(false); setIsSidebarHovered(false) }}

          className="absolute inset-0 bg-black/55 backdrop-blur-[2px] z-20 transition-opacity duration-300"

        />

      )}

      {/* Slide-out Sidebar Drawer */}

      <aside

        onMouseLeave={() => setIsSidebarHovered(false)}

        style={{ width: (isSidebarOpen || isSidebarHovered) ? `${sidebarWidth}px` : '256px' }}

        className={`absolute top-3 left-3 h-[calc(100vh-24px)] bg-[#0d0f11]/95 border border-[#1e2025] rounded-2xl z-30 flex flex-col justify-between px-6 py-7 backdrop-blur-xl shadow-2xl shadow-black/80 transition-all duration-300 ease-out ${

          isSidebarOpen || isSidebarHovered ? 'translate-x-0 opacity-100' : '-translate-x-[calc(100%+24px)] opacity-0 pointer-events-none'

        }`}

      >

        <div>

          <div className="flex items-center gap-3 mb-8 pb-6 border-b border-[#1e2025]">

            <div className="w-9 h-9 rounded-xl overflow-hidden border border-[#ffffff]/15 bg-brand-bg shrink-0">

              <img src="/favicon.png" alt="Ochuko" className="w-full h-full object-cover" />

            </div>

            <div>

              <p className="font-semibold text-[13px] text-brand-text tracking-tight">Agent Ochuko</p>

              <p className="text-[9px] text-[#ffffff] font-bold tracking-widest uppercase mt-0.5">System Active</p>

            </div>

          </div>

          <button

            onClick={() => handleNewSession()}

            className="w-full h-10 border border-[#1e2025] bg-black/30 hover:bg-black/50 text-brand-text hover:border-[#ffffff]/30 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center tracking-wide mb-4"

          >

            New Session

          </button>

          {/* Search Input */}

          <div className="relative mb-5">

            <span className="absolute left-3 top-2.5 text-[#8e95a2]/50">

              <Search className="w-3.5 h-3.5" />

            </span>

            <input

              ref={searchInputRef}

              type="text"

              value={searchQuery}

              onChange={(e) => setSearchQuery(e.target.value)}

              placeholder="Search chats (Ctrl+K)..."

              className="w-full h-9 bg-black/20 border border-[#1e2025] rounded-lg pl-9 pr-8 text-[11px] text-brand-text placeholder-[#8e95a2]/30 focus:outline-none focus:border-[#ffffff]/20 focus:ring-0 transition"

            />

            {searchQuery && (

              <button

                onClick={() => setSearchQuery('')}

                className="absolute right-3 top-2.5 text-[#8e95a2]/50 hover:text-brand-text"

              >

                <X className="w-3.5 h-3.5" />

              </button>

            )}

          </div>

          {/* Conversation List — grouped by date */}

          <div className="flex-1 overflow-y-auto max-h-[calc(100vh-320px)] pr-1 custom-scrollbar">

            {searchResults !== null ? (

              searchResults.length === 0 ? (

                <p className="text-[10px] text-[#8e95a2]/40 italic pl-1">No results found</p>

              ) : (

                <div className="space-y-1">

                  <p className="text-[9px] font-bold tracking-widest text-[#8e95a2]/40 uppercase mb-1.5 px-1">

                    Search Results

                  </p>

                  {searchResults.map((convo) => {

                    const active = convo.id === activeConversationId

                    return (

                      <div key={convo.id} className="group relative flex items-center w-full">

                        {renamingConvoId === convo.id ? (

                          <input

                            ref={renameInputRef}

                            value={renameValue}

                            onChange={e => setRenameValue(e.target.value)}

                            onBlur={handleRenameCommit}

                            onKeyDown={handleRenameKeyDown}

                            className="flex-1 px-3 py-2 rounded-lg text-[11px] font-medium bg-[#ffffff]/10 border border-[#ffffff]/40 text-brand-text outline-none pr-8"

                            maxLength={80}

                            placeholder="Conversation title…"

                          />

                        ) : (

                          <button

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

                            className={`flex-1 text-left px-3 py-2 rounded-lg text-[11px] font-medium truncate transition duration-150 block pr-14 ${

                              active

                                ? 'bg-[#ffffff]/10 text-brand-text border border-[#ffffff]/20'

                                : 'text-[#8e95a2] hover:text-brand-text hover:bg-white/5 border border-transparent'

                            }`}

                          >

                            {convo.title || 'Untitled Session'}

                          </button>

                        )}

                        {renamingConvoId !== convo.id && (

                          <>

                            <button

                              onClick={e => {

                                e.stopPropagation()

                                setRenamingConvoId(convo.id)

                                setRenameValue(convo.title || '')

                              }}

                              className="absolute right-7 opacity-0 group-hover:opacity-100 p-1 text-[#8e95a2]/50 hover:text-brand-accent transition duration-150 rounded hover:bg-white/5"

                              title="Rename"

                            >

                              <Pencil className="w-3.5 h-3.5" />

                            </button>

                            <button

                              onClick={e => {

                                e.stopPropagation()

                                setConvoToDelete(convo.id)

                              }}

                              className="absolute right-2 opacity-0 group-hover:opacity-100 p-1 text-[#8e95a2] hover:text-red-400 transition duration-150 rounded hover:bg-white/5"

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

              <p className="text-[10px] text-[#8e95a2]/40 italic pl-1">No past sessions</p>

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

                <div key={group.label} className="mb-4">

                  <p className="text-[9px] font-bold tracking-widest text-[#8e95a2]/40 uppercase mb-1.5 px-1">

                    {group.label}

                  </p>

                  <div className="space-y-1">

                    {group.items.map((convo) => {

                      const active = convo.id === activeConversationId

                      return (

                        <div key={convo.id} className="group relative flex items-center w-full">

                          {renamingConvoId === convo.id ? (

                            // Rename mode — inline input

                            <input

                              ref={renameInputRef}

                              value={renameValue}

                              onChange={e => setRenameValue(e.target.value)}

                              onBlur={handleRenameCommit}

                              onKeyDown={handleRenameKeyDown}

                              className="flex-1 px-3 py-2 rounded-lg text-[11px] font-medium bg-[#ffffff]/10 border border-[#ffffff]/40 text-brand-text outline-none pr-8"

                              maxLength={80}

                              placeholder="Conversation title…"

                            />

                          ) : (

                            <button

                              onClick={() => {
                                if (active) {
                                  setRenamingConvoId(convo.id)
                                  setRenameValue(convo.title || '')
                                } else {
                                  handleSelectConversation(convo.id, convo.mode)
                                }
                              }}

                              onDoubleClick={e => {

                                e.stopPropagation()

                                setRenamingConvoId(convo.id)

                                setRenameValue(convo.title || '')

                              }}

                              title="Double-click to rename"

                              className={`flex-1 text-left px-3 py-2 rounded-lg text-[11px] font-medium truncate transition duration-150 block pr-14 ${

                                active

                                  ? 'bg-[#ffffff]/10 text-brand-text border border-[#ffffff]/20'

                                  : 'text-[#8e95a2] hover:text-brand-text hover:bg-white/5 border border-transparent'

                              }`}

                            >

                              {convo.title || 'Untitled Session'}

                            </button>

                          )}

                          {renamingConvoId !== convo.id && (

                            <>

                              <button

                                onClick={e => {

                                  e.stopPropagation()

                                  setRenamingConvoId(convo.id)

                                  setRenameValue(convo.title || '')

                                }}

                                className="absolute right-7 opacity-0 group-hover:opacity-100 p-1 text-[#8e95a2]/50 hover:text-brand-accent transition duration-150 rounded hover:bg-white/5"

                                title="Rename"

                              >

                                <Pencil className="w-3 h-3" />

                              </button>

                              <button

                                onClick={e => {

                                  e.stopPropagation()

                                  setConvoToDelete(convo.id)

                                }}

                                className="absolute right-2 opacity-0 group-hover:opacity-100 p-1 text-[#8e95a2] hover:text-red-400 transition duration-150 rounded hover:bg-white/5"

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

        </div>

        <div className="border-t border-[#1e2025] pt-5 space-y-4">

          <div className="flex items-center gap-3">

            <div className="w-8 h-8 rounded-full overflow-hidden border border-[#1e2025] bg-brand-bg shrink-0">

              <img src="/favicon.png" alt="User" className="w-full h-full object-cover" />

            </div>

            <div className="truncate">

              <p className="text-[11px] text-brand-text font-bold truncate">{preferredName}</p>

              <p className="text-[9.5px] text-brand-muted truncate mt-0.5">{userEmail}</p>

            </div>

          </div>

          {localStorage.getItem('app_lock_pin') ? (
            <div className="flex gap-2 w-full">
              <button
                onClick={() => setIsLocked(true)}
                className="flex-1 h-9 text-[#ffffff] hover:text-[#ffffff] hover:bg-[#ffffff]/10 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1.5 border border-[#ffffff]/20 hover:border-[#ffffff]/40"
                title="Lock App"
              >
                <Lock className="w-3 h-3" />
                <span>Lock App</span>
              </button>
              <button
                onClick={() => setLockMode('change')}
                className="h-9 px-2.5 text-brand-muted hover:text-brand-text hover:bg-white/5 transition duration-150 rounded-lg text-[10px] font-semibold border border-[#1e2025]"
                title="Change PIN"
              >
                Change
              </button>
              <button
                onClick={() => setLockMode('disable')}
                className="h-9 px-2.5 text-red-400/50 hover:text-red-400 hover:bg-red-950/10 transition duration-150 rounded-lg text-[10px] font-semibold border border-transparent hover:border-red-950/20"
                title="Disable PIN"
              >
                Disable
              </button>
            </div>
          ) : (
            <button
              onClick={() => setLockMode('setup')}
              className="w-full h-9 text-brand-muted hover:text-brand-text hover:bg-white/5 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center gap-2 px-3 border border-[#1e2025] hover:border-white/10"
            >
              <Lock className="w-3 h-3" />
              <span>Setup PIN Lock</span>
            </button>
          )}

          <button
            onClick={() => navigate('/capabilities')}
            className="w-full h-9 text-brand-text hover:text-white hover:bg-white/10 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center gap-2 px-3 border border-[#ffffff]/30 hover:border-[#ffffff]/50 mb-1"
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>Agent Capabilities</span>
          </button>

          {/* Zoom Controls */}
          <div className="flex items-center gap-2 w-full mb-1">
            <button
              onClick={() => setPageZoom(prev => Math.max(0.5, prev - 0.1))}
              className="flex-1 h-9 text-brand-text hover:text-white hover:bg-white/10 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1.5 border border-[#ffffff]/30 hover:border-[#ffffff]/50"
              title="Zoom out"
            >
              <Minus className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] text-brand-muted font-mono w-12 text-center">{Math.round(pageZoom * 100)}%</span>
            <button
              onClick={() => setPageZoom(prev => Math.min(1.5, prev + 0.1))}
              className="flex-1 h-9 text-brand-text hover:text-white hover:bg-white/10 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1.5 border border-[#ffffff]/30 hover:border-[#ffffff]/50"
              title="Zoom in"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          <button

            onClick={handleSignOut}

            className="w-full h-10 text-red-400 hover:text-red-300 hover:bg-red-950/30 transition duration-150 rounded-lg text-[11px] font-semibold flex items-center gap-2.5 px-3 border border-red-900/30 hover:border-red-900/50"

          >

            <LogOut className="w-3.5 h-3.5" />

            <span>Terminate Session</span>

          </button>

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
        className="flex-1 flex flex-col relative bg-brand-bg overflow-hidden z-10 min-w-0 transition-all duration-300 ease-out"
        style={{
          marginLeft: '0px'
        }}
      >

        {/* Header */}

        <header className="relative z-30 h-14 border-b border-[#1a1c1f] bg-[#0a0b0d]/80 backdrop-blur-md flex items-center justify-between px-5 shrink-0">

          <div className="flex items-center gap-3.5">

            <button

              onClick={() => setIsSidebarOpen(!isSidebarOpen)}

              onMouseEnter={() => setIsSidebarHovered(true)}

              className="p-[7px] rounded-lg border border-[#1e2025] bg-brand-surface/20 hover:bg-brand-surface text-brand-muted hover:text-brand-text hover:border-[#ffffff]/25 transition duration-150 active:scale-95"

              aria-label="Toggle Sidebar"

            >

              <Menu className="w-4 h-4" />

            </button>

            <div className="w-px h-4 bg-[#1e2025]" />

            <span className="font-semibold text-[13px] text-brand-text tracking-tight">Agent Ochuko</span>

            <span className="text-[9px] uppercase tracking-widest px-2 py-[3px] rounded border border-[#ffffff]/15 text-[#ffffff]/70 font-bold hidden sm:inline-block">

              {mode}

            </span>

            {isFetchingHistory && (
              <span className="flex items-center gap-1.5 text-[10px] text-brand-muted animate-pulse ml-1">
                <Loader2 className="w-3 h-3 animate-spin text-[#ffffff]" />
                <span className="hidden sm:inline">Syncing...</span>
              </span>
            )}

          </div>

          <div className="flex items-center gap-3">
            {activeConversationId && activeConversationId !== '00000000-0000-0000-0000-000000000000' && (
              <button
                onClick={() => setIsShareModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#1e2025] hover:border-[#ffffff]/20 bg-brand-surface/10 hover:bg-[#ffffff]/5 text-[11px] font-bold text-[#8e95a2] hover:text-brand-text transition duration-150 active:scale-95 mr-1"
                title="Share Conversation"
              >
                <Share2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Share</span>
              </button>
            )}

            <div ref={headerSettingsRef} className="relative">
              <button
                onClick={() => setIsHeaderSettingsOpen(o => !o)}
                className="p-1.5 rounded-lg border border-[#1e2025] bg-brand-surface/10 hover:bg-[#ffffff]/5 text-brand-muted hover:text-brand-text hover:border-[#ffffff]/20 transition duration-150 active:scale-95 flex items-center justify-center mr-1"
                title="Settings & security"
              >
                <Settings className="w-3.5 h-3.5" />
              </button>
              {isHeaderSettingsOpen && (
                <div className="absolute right-0 mt-1.5 w-48 rounded-xl border border-[#1e2025] bg-[#0d0f11]/95 backdrop-blur-md shadow-2xl overflow-hidden z-50 py-1 select-none">
                  {localStorage.getItem('app_lock_pin') ? (
                    <>
                      <button
                        onClick={() => {
                          setIsLocked(true)
                          setIsHeaderSettingsOpen(false)
                        }}
                        className="w-full text-left px-4 py-2.5 text-[11px] text-brand-text hover:bg-white/5 transition flex items-center gap-2 font-semibold"
                      >
                        <Lock className="w-3.5 h-3.5 text-brand-muted" />
                        <span>Lock App</span>
                      </button>
                      <button
                        onClick={() => {
                          setLockMode('change')
                          setIsHeaderSettingsOpen(false)
                        }}
                        className="w-full text-left px-4 py-2.5 text-[11px] text-brand-muted hover:text-brand-text hover:bg-white/5 transition flex items-center gap-2 font-semibold border-t border-[#1e2025]/50"
                      >
                        <KeyRound className="w-3.5 h-3.5 text-brand-muted" />
                        <span>Change PIN</span>
                      </button>
                      <button
                        onClick={() => {
                          setLockMode('disable')
                          setIsHeaderSettingsOpen(false)
                        }}
                        className="w-full text-left px-4 py-2.5 text-[11px] text-red-400/70 hover:text-red-400 hover:bg-red-950/10 transition flex items-center gap-2 font-semibold border-t border-[#1e2025]/50"
                      >
                        <Unlock className="w-3.5 h-3.5 text-red-400/50" />
                        <span>Disable PIN</span>
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => {
                        setLockMode('setup')
                        setIsHeaderSettingsOpen(false)
                      }}
                      className="w-full text-left px-4 py-2.5 text-[11px] text-brand-text hover:bg-white/5 transition flex items-center gap-2 font-semibold"
                    >
                      <Lock className="w-3.5 h-3.5 text-brand-muted" />
                      <span>Setup PIN Lock</span>
                    </button>
                  )}
                  <button
                    onClick={() => {
                      handleSignOut()
                      setIsHeaderSettingsOpen(false)
                    }}
                    className="w-full text-left px-4 py-2.5 text-[11px] text-red-400/75 hover:text-red-450 hover:bg-red-950/15 transition flex items-center gap-2 font-semibold border-t border-[#1e2025]"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Terminate Session</span>
                  </button>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 ml-1">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ffffff] opacity-50" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#ffffff]" />
              </span>
              <span className="text-[9px] font-bold tracking-widest text-brand-muted uppercase hidden sm:block">Auth Synced</span>
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

              className="flex-1 overflow-y-auto overflow-x-hidden pt-8 pb-24 px-5 md:px-10 relative z-10"

            >

          {isFetchingHistory && messages.length === 0 ? (

            <ChatSkeleton />

          ) : messages.length === 0 ? (

            <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center space-y-7">

              <div className="w-16 h-16 bg-brand-surface border border-[#1e2025] rounded-2xl overflow-hidden shadow-xl relative group">

                <div className="absolute inset-0 bg-[#ffffff]/4 opacity-0 group-hover:opacity-100 transition duration-500" />

                <img

                  src="/favicon.png"

                  alt="Agent Ochuko"

                  className="w-full h-full object-cover transition duration-500 group-hover:scale-105"

                  fetchPriority="high"

                />

              </div>

              <div className="space-y-3">

                <div className="flex items-center gap-2 justify-center">
                  <h2 className="text-[21px] font-bold tracking-tight text-brand-text">{dynamicGreeting}</h2>
                </div>

                {isEditingNickname && (
                  <div className="flex items-center gap-2 justify-center">
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
                      className="bg-[#1e2025] border border-[#ffffff]/20 rounded px-2 py-1 text-sm text-brand-text focus:outline-none focus:border-brand-accent w-32"
                      placeholder="Enter nickname"
                      autoFocus
                    />
                    <button
                      onClick={() => {
                        setPreferredName(nicknameInput.trim())
                        setIsEditingNickname(false)
                      }}
                      className="p-1 rounded bg-brand-accent/20 hover:bg-brand-accent/30 text-brand-accent transition"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setIsEditingNickname(false)}
                      className="p-1 rounded hover:bg-white/10 text-brand-muted transition"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}



              </div>

            </div>

          ) : (

            <div className="max-w-2xl mx-auto space-y-6">

              {messages.map((msg, i) => (

                <LazyMessage key={i} estimatedHeight={msg.content.length > 400 ? 200 : 80}>

                  <div

                    className={`group relative flex w-full gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}

                  >

                  {/* Avatar only for assistant */}

                  {msg.role !== 'user' && (

                    <div className="w-8 h-8 rounded-lg border border-[#ffffff]/15 bg-brand-surface/30 flex items-center justify-center shrink-0 overflow-hidden mt-1 select-none">

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

                                className="px-3 py-1.5 bg-[#ffffff] text-[#08090a] hover:bg-[#f3f4f6] rounded-lg text-[11px] font-bold transition duration-150 shadow-md shadow-[#ffffff]/5"

                              >

                                Save & Submit

                              </button>

                            </div>

                          </div>

                        ) : (msg.fileAttachment || (msg.fileAttachments && msg.fileAttachments.length > 0)) ? (

                          /* Agent job — render as file chip(s) + optional prompt text */

                          <div className="space-y-2">

                            {msg.fileAttachment && (

                              <FileAttachmentChip attachment={msg.fileAttachment} />

                            )}

                            {msg.fileAttachments && msg.fileAttachments.map((attachment, idx) => (

                              <FileAttachmentChip key={idx} attachment={attachment} />

                            ))}

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

                                    className="flex items-center justify-between gap-2.5 px-3 py-2.5 rounded-lg bg-[#ffffff]/8 border border-[#ffffff]/20 cursor-pointer hover:bg-[#ffffff]/15 transition-all duration-150 select-none max-w-sm"

                                  >

                                    <div className="flex items-center gap-2 min-w-0">

                                      <FileText className="w-4 h-4 text-[#ffffff] shrink-0" />

                                      <div className="min-w-0">

                                        <p className="text-[11px] font-bold text-[#ffffff] uppercase tracking-widest leading-none mb-1">

                                          Pasted Content

                                        </p>

                                        <p className="text-[12px] text-brand-text/90 font-medium truncate">

                                          {parsed.pastedName}

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

                        /* Typing / searching indicator — appears immediately before first token */

                        <div className="flex items-center gap-2 h-6">

                          {msg.agentStep && msg.agentStep > 0 ? (

                            /* OODA loop active — show step counter */

                            <AgentStepIndicator

                              step={msg.agentStep}

                              maxSteps={msg.agentMaxSteps || agentMaxSteps}

                              label={msg.agentLabel || (webSearchStatus === 'searching' ? activityLabel : undefined)}

                            />

                          ) : webSearchStatus === 'searching' ? (

                            <>

                              <Globe className="w-3.5 h-3.5 text-[#ffffff] animate-pulse" />

                              <span className="text-[11px] text-[#ffffff]/70 font-semibold tracking-wide">

                                {activityLabel || 'Searching the web...'}

                              </span>

                            </>

                          ) : (

                            [0, 150, 300].map((delay, d) => (

                              <span

                                key={d}

                                className={`w-1.5 h-1.5 rounded-full bg-[#ffffff]/50 animate-bounce dot-bounce-${delay}`}

                              />

                            ))

                          )}

                        </div>

                      ) : (

                        /* Rendered markdown — optionally preceded by a step pill while looping */

                        <div className="space-y-3">

                          {msg.role === 'assistant' && (msg.agentStep ?? 0) > 1 && msg.content.length > 0 && (

                            <AgentStepIndicator

                              step={msg.agentStep!}

                              maxSteps={msg.agentMaxSteps || agentMaxSteps}

                              label={msg.agentLabel || (webSearchStatus === 'searching' && i === messages.length - 1 ? activityLabel : undefined)}

                              isComplete={!isStreaming || i !== messages.length - 1}

                            />

                          )}

                          {/* Thinking panel — shown above answer in THINK/SOLVE modes */}
                          {msg.thinkingContent && (
                            <ThinkingBlock
                              content={msg.thinkingContent}
                              streaming={isStreaming && i === messages.length - 1}
                            />
                          )}

                          {msg.content.length > 0 && renderRichContent(

                            msg.content,

                            (t) => renderMarkdown(t, msg.generatedFiles),

                            /* Only skip rich rendering if this is the actively streaming message */

                            isStreaming && i === messages.length - 1,

                          )}

                          {/* Generated file download cards — shown BEFORE image so files are always reachable */}

                          {msg.generatedFiles && msg.generatedFiles.length > 0 && (

                            <div className="mt-3 space-y-2">

                              {msg.generatedFiles.map((gf, gfi) => (

                                <FileDownloadCard

                                  key={gfi}

                                  filename={gf.filename}

                                  download_url={gf.download_url}

                                  size_bytes={gf.size_bytes}

                                  onView={() => setActiveArtifact({
                                    filename: gf.filename,
                                    downloadUrl: gf.download_url,
                                    sizeBytes: gf.size_bytes
                                  })}

                                />

                              ))}

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

                    {msg.timestamp && !isStreaming && (

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

                </LazyMessage>

              ))}

              <div ref={messagesEndRef} />

            </div>

          )}

        </div>

        {/* Pinned Input Area (Unified Console Card) */}
        <div className="absolute bottom-6 left-0 right-0 px-5 md:px-10 z-20">
          <div className="max-w-2xl mx-auto">
            <form
              ref={formRef}
              onSubmit={handleSend}
              className="bg-[#0d0f11]/95 border border-[#1e2025] rounded-xl pt-2 px-3 pb-1 shadow-2xl flex flex-col gap-1.5 relative z-10 backdrop-blur-xl transition-all duration-200 focus-within:border-[#ffffff]/15 pointer-events-auto"
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

            {/* Middle Row: Textarea input */}
            <div className="relative flex-1">
              <textarea
                ref={inputRef as any}
                rows={1}
                value={input}
                onPaste={handlePaste}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    formRef.current?.requestSubmit()
                  }
                }}
                onChange={(e) => {
                  setInput(e.target.value)
                  if (voice.isRecording) voice.clearTranscript()
                }}
                disabled={uploading}
                placeholder={
                  voice.isRecording ? 'Listening...' :
                  attachedFiles.length > 0 ? 'Add prompt details for the agent...' :
                  pastedText ? 'Add prompt details for the pasted text...' : "Let's talk"
                }
                className="w-full h-[22px] bg-transparent text-[13.5px] text-brand-text placeholder-brand-muted/40 focus:outline-none resize-none max-h-48 overflow-y-auto py-0.5"
              />
            </div>

            {/* Bottom Row: Attachments status & action buttons */}
            <div className="flex items-center justify-between pt-2">
              {/* Left Side: Attach File, File previews */}
              <div className="flex items-center gap-2">

                <button
                  type="button"
                  onClick={handleTriggerUpload}
                  disabled={uploading}
                  className="p-1.5 text-brand-muted hover:text-brand-text hover:bg-white/5 rounded transition duration-150 active:scale-95 disabled:opacity-20"
                  title="Attach document or image"
                >
                  <Paperclip className="w-4 h-4" />
                </button>

                {/* Voice mic button */}
                {voice.isSupported && (
                  <button
                    id="voice-mic-button"
                    type="button"
                    onClick={toggleVoice}
                    disabled={isStreaming || uploading}
                    className={`p-1.5 transition-all duration-150 active:scale-95 rounded disabled:opacity-20 ${
                      voice.isRecording
                        ? 'text-[#ffffff] voice-pulse-ring'
                        : 'text-brand-muted hover:text-brand-text hover:bg-white/5'
                    }`}
                    title={voice.isRecording ? 'Stop recording' : 'Voice input'}
                  >
                    <Mic className="w-4 h-4" />
                  </button>
                )}

                {/* Mode Selector Pill Group */}
                <div className="flex items-center gap-0.5 bg-[#ffffff]/3 p-0.5 rounded-lg border border-brand-border/40 ml-1 select-none">
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
                        className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[9px] font-bold transition-all duration-150 tracking-wider uppercase ${
                          active
                            ? 'bg-[#ffffff]/8 text-[#ffffff] shadow-sm'
                            : 'text-brand-muted hover:text-brand-text/75'
                        }`}
                      >
                        <Icon className="w-3 h-3" />
                        <span className="hidden sm:inline">{label}</span>
                      </button>
                    )
                  })}
                </div>

                {/* Inline File Previews */}
                {(attachedFiles.length > 0 || pastedText) && (
                  <div className="flex flex-wrap items-center gap-2 ml-2">
                    {attachedFiles.map((file, idx) => (
                      file.type.startsWith('image/') ? (
                        <div 
                          key={idx} 
                          className="relative w-8 h-8 rounded border border-brand-border shrink-0 animate-fadeIn group"
                        >
                          <img 
                            src={file.blobUrl} 
                            alt={file.name} 
                            onClick={() => setPreviewingFile({ name: file.name, type: file.type, url: file.blobUrl })}
                            className="w-full h-full object-cover cursor-pointer rounded" 
                            title="Click to view image"
                          />
                          <button 
                            type="button" 
                            onClick={(e) => {
                              e.stopPropagation()
                              setAttachedFiles(prev => prev.filter((_, i) => i !== idx))
                            }} 
                            className="absolute -top-1.5 -right-1.5 p-0.5 rounded-full bg-red-500 hover:bg-red-600 text-white shadow-md transition z-20 flex items-center justify-center"
                            title="Delete image"
                          >
                            <X className="w-2.5 h-2.5" />
                          </button>
                        </div>
                      ) : (
                        <div 
                          key={idx} 
                          onClick={() => setPreviewingFile({ name: file.name, type: file.type, url: file.blobUrl })}
                          className="flex items-center gap-1 pl-2 pr-6 py-1 rounded bg-brand-bg/50 border border-brand-border animate-fadeIn cursor-pointer hover:bg-[#ffffff]/5 transition relative group"
                          title="Click to view document"
                        >
                          <FileText className="w-3.5 h-3.5 text-brand-muted" />
                          <span className="text-[10px] text-brand-text max-w-[80px] truncate">{file.name}</span>
                          <button 
                            type="button" 
                            onClick={(e) => {
                              e.stopPropagation()
                              setAttachedFiles(prev => prev.filter((_, i) => i !== idx))
                            }} 
                            className="absolute right-1 text-brand-muted hover:text-red-400 p-0.5 hover:bg-[#ffffff]/10 rounded-full transition z-20 flex items-center justify-center"
                            title="Delete file"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      )
                    ))}
                    {pastedText && (
                      <div 
                        onClick={() => setPreviewingFile({ name: pastedText.name, type: 'text/plain', content: pastedText.content })}
                        className="flex items-center gap-1 pl-2 pr-6 py-1 rounded bg-brand-bg/50 border border-brand-border animate-fadeIn cursor-pointer hover:bg-[#ffffff]/5 transition relative group"
                        title="Click to view pasted text"
                      >
                        <FileText className="w-3.5 h-3.5 text-brand-muted" />
                        <span className="text-[10px] text-brand-text max-w-[80px] truncate">{pastedText.name}</span>
                        <button 
                          type="button" 
                          onClick={(e) => {
                            e.stopPropagation()
                            setPastedText(null)
                          }} 
                          className="absolute right-1 text-brand-muted hover:text-red-400 p-0.5 hover:bg-[#ffffff]/10 rounded-full transition z-20 flex items-center justify-center"
                          title="Delete pasted text"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Right Side: Stop/Send Actions */}
              <div className="flex items-center gap-2">
                {isStreaming && (
                  <button
                    type="button"
                    onClick={handleStop}
                    className="w-8 h-8 bg-brand-surface border border-brand-border text-red-400 rounded-lg flex items-center justify-center hover:bg-red-950/15 transition active:scale-95 shadow shrink-0"
                  >
                    <Square className="w-3 h-3 fill-red-400" />
                  </button>
                )}

                 <button
                  type="submit"
                  disabled={uploading || (!input.trim() && attachedFiles.length === 0 && !pastedText)}
                  className="px-3.5 py-1.5 bg-brand-text text-brand-bg text-[12px] font-bold rounded-lg flex items-center justify-center gap-1.5 hover:opacity-90 transition disabled:opacity-20 active:scale-95 shadow"
                >
                  <span>Send</span>
                  <Send className="w-3 h-3" />
                </button>
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileChange}
              accept=".pdf,.png,.jpg,.jpeg,.webp,.gif"
              className="hidden"
            />
          </form>
          </div>
        </div>

      </div>

          {/* Artifact Preview Panel */}

          {activeArtifact && (() => {
            const parts = activeArtifact.filename.split('.')
            const ext = parts.length > 1 ? parts.pop()?.toUpperCase() || '' : ''
            const name = parts.join('.')
            const titleDisplay = ext ? `${name} · ${ext}` : activeArtifact.filename.toUpperCase()

            const handleCopyArtifactContent = async () => {
              try {
                await navigator.clipboard.writeText(artifactContent)
                setCopiedArtifact(true)
                setTimeout(() => setCopiedArtifact(false), 2000)
              } catch (_) {}
            }

            const handleDownloadArtifact = async () => {
              if (!activeArtifact.downloadUrl) return
              await triggerDirectDownload(activeArtifact.downloadUrl, activeArtifact.filename)
              setIsArtifactCopyOpen(false)
            }

            const handlePublishArtifact = () => {
              showToast('Artifact published successfully!', 'info')
              setIsArtifactCopyOpen(false)
            }

            const handleReloadArtifact = () => {
              if (activeArtifact.downloadUrl) {
                setLoadingArtifact(true)
                setArtifactError(null)
                fetch(activeArtifact.downloadUrl)
                  .then(res => {
                    if (!res.ok) {
                      throw new Error(`HTTP ${res.status}`)
                    }
                    return res.text()
                  })
                  .then(text => {
                    setArtifactContent(text)
                    setLoadingArtifact(false)
                    showToast('Refreshed content', 'info')
                  })
                  .catch((err) => {
                    setArtifactError(err.message || 'Failed to load artifact content')
                    setLoadingArtifact(false)
                    showToast('Failed to refresh', 'error')
                  })
              } else {
                showToast('Refreshed content', 'info')
              }
            }

            return (
              <div
                style={{ width: isArtifactExpanded ? '100%' : `${artifactWidth}px` }}
                className="border-l border-[#1a1c1f] bg-[#0b0c0e] flex flex-col relative shrink-0 z-20 transition-all duration-150"
              >
                {/* Resizing Handle */}
                {!isArtifactExpanded && (
                  <div
                    onMouseDown={startArtifactResizing}
                    className="absolute top-0 left-0 w-1.5 h-full cursor-col-resize hover:bg-[#ffffff]/30 active:bg-[#ffffff]/50 transition z-50"
                  />
                )}

                {/* Header */}
                <div className="h-14 border-b border-[#1a1c1f] bg-[#0d0f11]/80 backdrop-blur-md flex items-center justify-between px-5 shrink-0 select-none">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="w-4 h-4 text-[#ffffff] shrink-0" />
                    <span className="font-semibold text-[13px] text-brand-text truncate mr-2">
                      {titleDisplay}
                    </span>
                    {(() => {
                      const ext = activeArtifact.filename.toLowerCase().split('.').pop() || ''
                      const showTabs = ['html', 'htm', 'svg', 'md', 'markdown'].includes(ext)
                      if (!showTabs) return null
                      return (
                        <div className="flex items-center bg-[#07080a] border border-[#1e2025] rounded-lg p-0.5 ml-2">
                          <button
                            onClick={() => setArtifactTab('preview')}
                            className={`px-3 py-1 text-[11px] font-medium rounded-md transition duration-150 ${artifactTab === 'preview' ? 'bg-[#1e2025] text-white shadow-sm' : 'text-[#8e95a2] hover:text-white'}`}
                          >
                            Preview
                          </button>
                          <button
                            onClick={() => setArtifactTab('code')}
                            className={`px-3 py-1 text-[11px] font-medium rounded-md transition duration-150 ${artifactTab === 'code' ? 'bg-[#1e2025] text-white shadow-sm' : 'text-[#8e95a2] hover:text-white'}`}
                          >
                            Code
                          </button>
                        </div>
                      )
                    })()}
                  </div>
                  <div className="flex items-center gap-2">
                    {/* Copy Split Dropdown */}
                    <div ref={artifactCopyRef} className="relative flex items-center">
                      <button
                        onClick={handleCopyArtifactContent}
                        className="flex items-center gap-1.5 px-2.5 h-7 text-[10.5px] font-semibold rounded-l-lg border border-r-0 border-[#1e2025] bg-[#0d0f11]/60 hover:bg-[#ffffff]/5 text-[#8e95a2] hover:text-brand-text transition duration-150 select-none"
                      >
                        {copiedArtifact ? (
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
                      <button
                        onClick={() => setIsArtifactCopyOpen(o => !o)}
                        className="flex items-center justify-center px-1.5 h-7 rounded-r-lg border border-[#1e2025] bg-[#0d0f11]/60 hover:bg-[#ffffff]/5 text-[#8e95a2] hover:text-brand-text transition duration-150"
                      >
                        <ChevronDown className="w-3 h-3" />
                      </button>

                      {isArtifactCopyOpen && (
                        <div className="absolute top-8 right-0 mt-1 w-44 rounded-lg border border-[#1e2025] bg-[#0d0f11]/95 backdrop-blur-md shadow-2xl overflow-hidden z-50 py-1">
                          <button
                            onClick={handleDownloadArtifact}
                            className="w-full text-left px-3 py-2 text-[11px] text-brand-text hover:bg-white/5 transition flex items-center gap-2"
                          >
                            <Download className="w-3.5 h-3.5 text-brand-muted" />
                            <span>Download as {ext || 'FILE'}</span>
                          </button>
                          <button
                            onClick={handlePublishArtifact}
                            className="w-full text-left px-3 py-2 text-[11px] text-brand-text hover:bg-white/5 transition flex items-center gap-2 border-t border-[#1e2025]/50"
                          >
                            <Globe className="w-3.5 h-3.5 text-brand-muted" />
                            <span>Publish artifact</span>
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Reload Button */}
                    <button
                      onClick={handleReloadArtifact}
                      className="p-1.5 rounded-lg border border-[#1e2025] hover:border-white/10 hover:bg-white/5 text-[#8e95a2] hover:text-brand-text transition"
                      title="Reload"
                    >
                      <RotateCw className="w-3.5 h-3.5" />
                    </button>

                    {/* Expand/Minimize Toggle */}
                    <button
                      onClick={() => setIsArtifactExpanded(!isArtifactExpanded)}
                      className="p-1.5 rounded-lg border border-[#1e2025] hover:border-white/10 hover:bg-white/5 text-[#8e95a2] hover:text-brand-text transition"
                      title={isArtifactExpanded ? "Minimize panel" : "Maximize panel"}
                    >
                      {isArtifactExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                    </button>

                    {/* Close Button */}
                    <button
                      onClick={() => {
                        setActiveArtifact(null)
                        setIsArtifactExpanded(false)
                      }}
                      className="p-1.5 rounded-lg border border-[#1e2025] hover:border-white/10 hover:bg-white/5 text-[#8e95a2] hover:text-brand-text transition"
                      title="Close Preview"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-auto p-6 bg-[#08090b]">
                  {artifactError ? (
                    <div className="h-full flex items-center justify-center">
                      <div className="max-w-md w-full p-6 rounded-xl border border-red-500/30 bg-red-500/10 flex flex-col items-center text-center space-y-4">
                        <div className="p-3 rounded-full bg-red-500/20 text-red-400">
                          <X className="w-6 h-6" />
                        </div>
                        <div>
                          <h3 className="text-red-400 font-semibold text-sm">Failed to load artifact</h3>
                          <p className="text-red-300/70 text-xs mt-1">{artifactError}</p>
                        </div>
                        <button
                          onClick={handleReloadArtifact}
                          className="flex items-center gap-2 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-xs font-medium transition"
                        >
                          <RotateCw className="w-3.5 h-3.5" /> Try Again
                        </button>
                      </div>
                    </div>
                  ) : loadingArtifact ? (
                    <div className="h-full flex items-center justify-center">
                      <Loader2 className="w-6 h-6 text-[#ffffff] animate-spin" />
                    </div>
                  ) : (() => {
                    const ext = activeArtifact.filename.toLowerCase().split('.').pop() || ''
                    const isHtml = ['html', 'htm'].includes(ext)
                    const isMd = ['md', 'markdown'].includes(ext)
                    const isDocx = ext === 'docx'
                    const isOffice = ['doc', 'xlsx', 'xls', 'pptx', 'ppt'].includes(ext)
                    const isPdf = ext === 'pdf'
                    const isImg = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'].includes(ext)

                    if (artifactTab === 'preview') {
                      if (isImg) {
                        return (
                          <div className="h-full flex items-center justify-center p-4 bg-[#0a0b0d]/50 rounded-xl border border-[#1e2025]">
                            <img
                              src={activeArtifact.downloadUrl || `data:image/svg+xml;utf8,${encodeURIComponent(artifactContent)}`}
                              alt={activeArtifact.filename}
                              className="max-w-full max-h-full object-contain rounded"
                            />
                          </div>
                        )
                      }
                      if (isPdf) {
                        return (
                          <div className="w-full h-[calc(100vh-8.5rem)] bg-[#0a0b0d]/50 rounded-xl border border-[#1e2025] overflow-hidden">
                            <iframe
                              src={activeArtifact.downloadUrl}
                              className="w-full h-full border-0"
                              title={activeArtifact.filename}
                            />
                          </div>
                        )
                      }
                      if (isDocx) {
                        return (
                          <div className="w-full h-[calc(100vh-8.5rem)] bg-[#0a0b0d]/30 rounded-xl border border-[#1e2025] overflow-hidden">
                            <DocxPreview url={activeArtifact.downloadUrl || ''} />
                          </div>
                        )
                      }
                      if (isOffice) {
                        return (
                          <div className="w-full h-[calc(100vh-8.5rem)] bg-white rounded-xl border border-[#1e2025] overflow-hidden">
                            <iframe
                              src={`https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(activeArtifact.downloadUrl || '')}`}
                              className="w-full h-full border-0"
                              title={activeArtifact.filename}
                            />
                          </div>
                        )
                      }
                      if (isHtml) {
                        return (
                          <div className="w-full h-[calc(100vh-8.5rem)] bg-white rounded-xl border border-[#1e2025] overflow-hidden">
                            <iframe
                              srcDoc={artifactContent}
                              sandbox="allow-scripts allow-popups"
                              className="w-full h-full border-0"
                              title="HTML Preview"
                            />
                          </div>
                        )
                      }
                      if (isMd) {
                        return (
                          <div className="rounded-xl border border-[#1e2025] bg-[#07080a] overflow-hidden">
                            <div className="p-6 text-brand-text prose prose-invert max-w-none text-[13px] leading-relaxed">
                              {renderMarkdown(artifactContent)}
                            </div>
                          </div>
                        )
                      }
                      if (isBinaryFile(activeArtifact.filename)) {
                        return (
                          <div className="h-full flex items-center justify-center p-8 bg-[#0a0b0d]/30 rounded-xl border border-[#1e2025]">
                            <div className="max-w-md w-full p-6 rounded-2xl bg-[#0a0b0d] border border-[#1e2025] flex flex-col items-center text-center space-y-4 shadow-xl">
                              <div className="p-4 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                                <FileText className="w-10 h-10" />
                              </div>
                              <div>
                                <h3 className="text-white font-semibold text-lg truncate max-w-xs">{activeArtifact.filename}</h3>
                                <p className="text-[#8e95a2] text-xs mt-1">Binary Document File ({(activeArtifact.filename.split('.').pop() || '').toUpperCase()})</p>
                              </div>
                              <div className="w-full pt-4 border-t border-[#1e2025] flex flex-col items-center gap-2">
                                <button
                                  onClick={async () => {
                                    if (activeArtifact.downloadUrl) {
                                      await triggerDirectDownload(activeArtifact.downloadUrl, activeArtifact.filename)
                                    }
                                  }}
                                  className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-medium text-sm transition shadow-lg shadow-blue-600/15"
                                >
                                  <Download className="w-4 h-4" /> Download File
                                </button>
                                <p className="text-[#626875] text-[11px] mt-1">Binary files cannot be rendered directly in the editor</p>
                              </div>
                            </div>
                          </div>
                        )
                      }
                      // Fallback for code/text files with no preview
                      return (
                        <div className="rounded-xl border border-[#1e2025] bg-[#07080a] overflow-hidden">
                          <CodeView
                            language={activeArtifact.filename.split('.').pop() || 'text'}
                            content={artifactContent}
                          />
                        </div>
                      )
                    } else {
                      // activeTab === 'code'
                      return (
                        <div className="rounded-xl border border-[#1e2025] bg-[#07080a] overflow-hidden">
                          <CodeView
                            language={ext === 'md' ? 'markdown' : ext}
                            content={artifactContent}
                          />
                        </div>
                      )
                    }
                  })()}
                </div>
              </div>
            )
          })()}

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

      {isShareModalOpen && (() => {
        const activeConvo = conversations.find(c => c.id === activeConversationId)
        const isShared = activeConvo?.is_shared
        const shareToken = activeConvo?.share_token
        const shareUrl = shareToken ? `${window.location.origin}/shared/${shareToken}` : ''

        return (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-[2px] flex items-center justify-center z-50 p-4">
            <div className="bg-[#0d0f11] border border-[#1e2025] rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-6">
              <div className="flex items-center justify-between border-b border-[#1c1e22] pb-3">
                <h3 className="text-sm font-semibold text-brand-text flex items-center gap-2">
                  <Share2 className="w-4 h-4 text-[#ffffff]" />
                  <span>Share Conversation</span>
                </h3>
                <button
                  onClick={() => setIsShareModalOpen(false)}
                  className="text-brand-muted hover:text-brand-text transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {isShared ? (
                <div className="space-y-4">
                  <p className="text-[12px] text-[#8e95a2] leading-relaxed">
                    Anyone with this link can view the conversation history and export it as JSON.
                  </p>
                  
                  <div className="flex items-center gap-2 bg-[#08090a] border border-[#1e2025] rounded-lg p-2">
                    <input
                      type="text"
                      readOnly
                      value={shareUrl}
                      onClick={(e) => (e.target as HTMLInputElement).select()}
                      className="bg-transparent border-0 outline-none text-[11px] text-brand-text font-mono flex-1 px-1 select-all"
                    />
                    <button
                      onClick={async () => {
                        await navigator.clipboard.writeText(shareUrl)
                        showToast('Link copied!', 'info')
                      }}
                      className="px-2.5 py-1 rounded bg-[#ffffff]/10 hover:bg-[#ffffff]/20 border border-[#ffffff]/20 text-[10px] font-bold text-[#ffffff] transition"
                    >
                      Copy
                    </button>
                  </div>

                  <div className="flex items-center justify-between pt-2">
                    <button
                      onClick={() => handleShareToggle(false)}
                      disabled={sharing}
                      className="px-3.5 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 text-[11px] font-semibold text-red-450 transition disabled:opacity-50"
                    >
                      {sharing ? 'Processing...' : 'Stop Sharing'}
                    </button>
                    <button
                      onClick={() => setIsShareModalOpen(false)}
                      className="px-3.5 py-1.5 rounded-lg border border-[#1e2025] hover:bg-white/5 text-[11px] font-semibold text-brand-text transition"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-[12px] text-[#8e95a2] leading-relaxed">
                    Create a public link to share this conversation with others.
                  </p>
                  <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                      onClick={() => setIsShareModalOpen(false)}
                      className="px-3.5 py-1.5 rounded-lg border border-[#1e2025] hover:bg-white/5 text-[11px] font-semibold text-brand-text transition"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleShareToggle(true)}
                      disabled={sharing}
                      className="px-3.5 py-1.5 rounded-lg bg-[#ffffff] hover:bg-[#e2e8f0] text-black text-[11px] font-semibold transition disabled:opacity-50"
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

      {/* Toast notification container — top-right, non-blocking */}

      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none" aria-live="polite">

        {toasts.map(t => (

          <div

            key={t.id}

            className={`px-4 py-2.5 rounded-xl border text-[12px] font-semibold tracking-wide shadow-xl shadow-black/40 backdrop-blur-md ${

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
        <div className="fixed bottom-3 left-6 w-80 p-4 rounded-xl border border-black/10 bg-white shadow-2xl flex flex-col gap-2.5 z-50 animate-in fade-in slide-in-from-bottom-4 duration-300 pointer-events-auto select-none">
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
      {/* Unified File/Text Preview Modal */}
      {previewingFile && (
        <div 
          className="fixed inset-0 bg-[#07080a]/95 backdrop-blur-md z-[100] flex flex-col items-center justify-between p-4 md:p-6 animate-fadeIn"
          onClick={() => setPreviewingFile(null)}
        >
          {/* Modal Header */}
          <div 
            className="w-full max-w-5xl flex items-center justify-between pb-4 border-b border-[#1e2025] mb-4 relative z-10"
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
                    let width = 800
                    let height = 600
                    try {
                      const res = await fetch(previewingFile.url || '')
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
                    img.src = previewingFile.url || ''
                  }}
                  className="px-3 py-1.5 rounded-lg bg-[#ffffff]/5 hover:bg-[#ffffff]/10 text-[11px] font-bold text-brand-text border border-[#ffffff]/10 transition flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download PNG</span>
                </button>
              )}
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

          {/* Modal Content */}
          <div 
            className="flex-1 w-full max-w-5xl flex items-center justify-center overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {previewingFile.type.startsWith('image/') ? (
              <img 
                src={previewingFile.url} 
                alt={previewingFile.name} 
                className="max-w-full max-h-[75vh] object-contain rounded-xl border border-[#ffffff]/10 shadow-2xl animate-scaleIn"
              />
            ) : previewingFile.type === 'application/pdf' ? (
              <embed 
                src={previewingFile.url} 
                type="application/pdf" 
                className="w-full h-full max-h-[75vh] rounded-xl border border-[#ffffff]/10 shadow-2xl bg-[#0b0c0e]" 
              />
            ) : (
              <pre className="w-full h-full max-h-[75vh] bg-[#0b0c0f] border border-[#1e2025] rounded-xl p-5 text-[#8b949e] font-mono text-[13px] overflow-auto whitespace-pre-wrap select-text leading-relaxed shadow-inner">
                {previewingFile.content || "No text content available to display."}
              </pre>
            )}
          </div>

          {/* Footer Info */}
          <div className="pt-4 text-[10px] text-brand-muted/40 font-medium select-none">
            Click outside or press ESC to dismiss preview
          </div>
        </div>
      )}

    </div>

  )

}

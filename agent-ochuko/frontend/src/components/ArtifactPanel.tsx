import { useState, useRef, useEffect, useCallback } from 'react'
import { FileText, X, Download, Code2, Eye, Globe, Monitor, Smartphone, Copy, Check } from 'lucide-react'

export interface ArtifactFile {
  name: string
  type: string
  url?: string
  localObjectUrl?: string
  content?: string
  sizeBytes?: number
}

interface ArtifactPanelProps {
  file: ArtifactFile
  content: string | null
  loading: boolean
  renderMarkdown: (text: string, generatedFiles?: any[]) => React.ReactNode
  onClose: () => void
  onPublish?: () => void
}

const MIN_WIDTH = 380
const DEFAULT_WIDTH = 560

function kindOf(file: ArtifactFile): 'html' | 'svg' | 'md' | 'csv' | 'code' {
  const n = file.name.toLowerCase()
  const t = file.type || ''
  if (t === 'image/svg+xml' || n.endsWith('.svg')) return 'svg'
  if (t === 'text/html' || t === 'html' || n.endsWith('.html') || n.endsWith('.htm')) return 'html'
  if (n.endsWith('.md') || n.endsWith('.markdown') || t === 'text/markdown') return 'md'
  if (n.endsWith('.csv') || t === 'text/csv') return 'csv'
  return 'code'
}

function parseCsv(raw: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let inQuotes = false
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i]
    if (c === '"') {
      if (inQuotes && raw[i + 1] === '"') { cell += '"'; i++ }
      else { inQuotes = !inQuotes }
    } else if (c === ',' && !inQuotes) {
      row.push(cell.trim())
      cell = ''
    } else if ((c === '\n' || c === '\r') && !inQuotes) {
      if (c === '\r' && raw[i + 1] === '\n') i++
      row.push(cell.trim())
      if (row.some(Boolean)) rows.push(row)
      row = []
      cell = ''
    } else {
      cell += c
    }
  }
  if (cell || row.length) {
    row.push(cell.trim())
    if (row.some(Boolean)) rows.push(row)
  }
  return rows
}

function CsvTable({ text }: { text: string }) {
  const lines = parseCsv(text)
  if (!lines.length) return <p className="text-white/40 text-xs p-4">Empty CSV</p>
  const [header, ...rows] = lines.slice(0, 200)
  return (
    <div className="overflow-auto max-h-full">
      <table className="w-full text-left text-[11px] font-mono border-collapse">
        <thead className="bg-white/5 sticky top-0 border-b border-white/10">
          <tr>
            {header.map((col, i) => (
              <th key={i} className="px-3 py-2 text-white/80 font-bold whitespace-nowrap">{col || `Col ${i + 1}`}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-white/[0.02]">
              {r.map((cell, j) => (
                <td key={j} className="px-3 py-1.5 text-white/70 whitespace-nowrap max-w-[260px] truncate">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {lines.length >= 200 && (
        <p className="text-[10px] text-white/30 px-3 py-2">Showing first 200 rows — download for the full file.</p>
      )}
    </div>
  )
}

export function ArtifactPanel({ file, content, loading, renderMarkdown, onClose, onPublish }: ArtifactPanelProps) {
  const kind = kindOf(file)
  const canRender = kind === 'html' || kind === 'svg' || kind === 'md' || kind === 'csv'
  const [tab, setTab] = useState<'render' | 'code'>('render')
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const [device, setDevice] = useState<'desktop' | 'mobile'>('desktop')
  const [copied, setCopied] = useState(false)
  const dragging = useRef(false)

  const startDrag = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    e.preventDefault()
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const w = window.innerWidth - e.clientX
      setWidth(Math.min(Math.max(w, MIN_WIDTH), Math.min(1100, window.innerWidth - 60)))
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const text = content ?? file.content ?? ''
  const fileUrl = file.localObjectUrl || file.url

  const handleCopy = async () => {
    let toCopy = text
    if (!toCopy && fileUrl) {
      try {
        const res = await fetch(fileUrl)
        toCopy = await res.text()
      } catch (err) {
        console.warn('Failed to fetch file text for copy:', err)
      }
    }
    if (toCopy) {
      await navigator.clipboard.writeText(toCopy)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownload = async () => {
    try {
      let blob: Blob
      if (text) {
        blob = new Blob([text], { type: file.type || 'text/plain;charset=utf-8' })
      } else if (fileUrl) {
        const res = await fetch(fileUrl)
        blob = await res.blob()
      } else {
        return
      }
      const safeName = file.name ? file.name.split('/').pop()?.split('\\').pop() || file.name : 'download'
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = safeName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
    } catch (err) {
      console.warn('Direct download failed, falling back to direct link:', err)
      if (fileUrl) {
        const a = document.createElement('a')
        a.href = fileUrl
        a.download = file.name ? file.name.split('/').pop()?.split('\\').pop() || file.name : 'download'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      }
    }
  }

  return (
    <div
      className="fixed top-0 right-0 h-full bg-[#0d0f11] border-l border-white/10 z-[100] flex flex-col animate-[slideInRight_0.2s_ease-out] max-md:w-full"
      style={{ width: `min(${width}px, 100vw)` }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Drag handle */}
      <div
        className="absolute left-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-white/10 transition max-md:hidden"
        onMouseDown={startDrag}
      />

      {/* Header — safe-area padding for mobile full-screen sheet */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08] shrink-0 max-md:pt-[max(0.75rem,env(safe-area-inset-top))]"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <FileText className="w-4 h-4 text-white/50 shrink-0" />
          <div className="min-w-0">
            <h3 className="text-[13px] font-semibold text-white truncate leading-tight">{file.name}</h3>
            <p className="text-[9px] text-white/35 uppercase tracking-widest font-semibold mt-0.5">
              {file.sizeBytes ? `${(file.sizeBytes / 1024).toFixed(1)} KB · ` : ''}{file.type || 'text'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={handleCopy}
            title={copied ? "Copied to clipboard!" : "Copy content"}
            className="p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
          {onPublish && (
            <button
              type="button"
              onClick={onPublish}
              title="Publish artifact"
              className="p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <Globe className="w-3.5 h-3.5" />
            </button>
          )}
          {(text || fileUrl) && (
            <button
              type="button"
              onClick={handleDownload}
              title="Download file"
              className="p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            title="Close (Esc)"
            className="p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tabs + viewport toggle */}
      {canRender && (
        <div className="flex items-center gap-1 px-3 pt-2.5 shrink-0">
          <button
            type="button"
            onClick={() => setTab('render')}
            className={`px-3 py-1.5 rounded-md text-[11px] font-semibold flex items-center gap-1.5 transition ${
              tab === 'render' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
            }`}
          >
            <Eye className="w-3 h-3" />
            Render
          </button>
          <button
            type="button"
            onClick={() => setTab('code')}
            className={`px-3 py-1.5 rounded-md text-[11px] font-semibold flex items-center gap-1.5 transition ${
              tab === 'code' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
            }`}
          >
            <Code2 className="w-3 h-3" />
            Code
          </button>
          {/* Claude-style viewport toggle for live HTML (desktop vs 390px mobile) */}
          {kind === 'html' && tab === 'render' && fileUrl && (
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={() => setDevice('desktop')}
                title="Desktop viewport"
                className={`p-1.5 rounded-md transition ${device === 'desktop' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'}`}
              >
                <Monitor className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setDevice('mobile')}
                title="Mobile viewport (390px)"
                className={`p-1.5 rounded-md transition ${device === 'mobile' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'}`}
              >
                <Smartphone className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {loading ? (
          <div className="h-full flex items-center justify-center text-white/50 text-xs font-mono">Loading…</div>
        ) : canRender && tab === 'render' ? (
          kind === 'html' ? (
            fileUrl ? (
              /* Real URL → relative assets (css/js/images) resolve correctly */
              <div className={`h-full flex justify-center bg-[#0b0c0f] ${device === 'mobile' ? 'items-stretch py-3' : ''}`}>
                <iframe
                  src={fileUrl}
                  className={`h-full border-0 bg-white rounded-md ${device === 'mobile' ? 'w-[390px] max-w-full' : 'w-full'}`}
                  sandbox="allow-scripts allow-popups allow-forms allow-modals allow-same-origin"
                  title={file.name}
                />
              </div>
            ) : (
              <iframe
                srcDoc={text || undefined}
                className="w-full h-full border-0 bg-white"
                sandbox="allow-scripts allow-popups allow-forms allow-modals"
                title={file.name}
              />
            )
          ) : kind === 'svg' ? (
            <div className="h-full overflow-auto p-4 flex items-start justify-center">
              <iframe
                srcDoc={text || undefined}
                src={!text && fileUrl ? fileUrl : undefined}
                className="w-full min-h-[300px] border-0"
                sandbox="allow-scripts"
                title={file.name}
              />
            </div>
          ) : kind === 'csv' ? (
            <CsvTable text={text} />
          ) : (
            <div className="h-full overflow-auto px-5 py-4">
              {renderMarkdown(text)}
            </div>
          )
        ) : (
          <pre className="h-full overflow-auto bg-[#0b0c0f] p-4 text-[#c9d1d9] font-mono text-[12px] whitespace-pre-wrap select-text leading-relaxed">
            {text || 'No text content available.'}
          </pre>
        )}
      </div>
    </div>
  )
}

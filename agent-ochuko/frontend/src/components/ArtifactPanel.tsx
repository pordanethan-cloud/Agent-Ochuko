import { useState, useRef, useEffect, useCallback } from 'react'
import { FileText, X, Download, Code2, Eye } from 'lucide-react'

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
}

const MIN_WIDTH = 380
const DEFAULT_WIDTH = 560

function kindOf(file: ArtifactFile): 'html' | 'svg' | 'md' | 'csv' | 'code' {
  const n = file.name.toLowerCase()
  const t = file.type || ''
  if (t === 'image/svg+xml' || n.endsWith('.svg')) return 'svg'
  if (t === 'text/html' || t === 'html' || n.endsWith('.html') || n.endsWith('.htm')) return 'html'
  if (n.endsWith('.md') || n.endsWith('.markdown') || t === 'text/markdown') return 'md'
  if (n.endsWith('.csv') || n.endsWith('.tsv') || t === 'text/csv') return 'csv'
  return 'code'
}

function CsvTable({ text }: { text: string }) {
  const lines = text.replace(/\r/g, '').split('\n').filter(l => l.trim()).slice(0, 200)
  if (lines.length === 0) return <p className="text-xs text-white/40 p-4">Empty file.</p>
  const delim = lines[0].includes('\t') ? '\t' : ','
  const rows = lines.map(l => l.split(delim).map(c => c.trim()))
  const header = rows[0]
  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-[12px] border-collapse">
        <thead>
          <tr className="bg-white/[0.04] sticky top-0">
            {header.map((h, i) => (
              <th key={i} className="text-left font-semibold text-white/70 px-3 py-2 border-b border-white/10 whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(1).map((r, ri) => (
            <tr key={ri} className="hover:bg-white/[0.02]">
              {header.map((_, ci) => (
                <td key={ci} className="px-3 py-1.5 text-white/60 border-b border-white/[0.05] whitespace-nowrap max-w-[240px] truncate">{r[ci] ?? ''}</td>
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

export function ArtifactPanel({ file, content, loading, renderMarkdown, onClose }: ArtifactPanelProps) {
  const kind = kindOf(file)
  const canRender = kind === 'html' || kind === 'svg' || kind === 'md' || kind === 'csv'
  const [tab, setTab] = useState<'render' | 'code'>('render')
  const [width, setWidth] = useState(DEFAULT_WIDTH)
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

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08] shrink-0">
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
          {fileUrl && (
            <a
              href={fileUrl}
              download={file.name}
              target="_blank"
              rel="noreferrer"
              title="Download"
              className="p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <Download className="w-3.5 h-3.5" />
            </a>
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

      {/* Tabs */}
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
        </div>
      )}

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {loading ? (
          <div className="h-full flex items-center justify-center text-white/50 text-xs font-mono">Loading…</div>
        ) : canRender && tab === 'render' ? (
          kind === 'html' ? (
            <iframe
              srcDoc={text || undefined}
              src={!text && fileUrl ? fileUrl : undefined}
              className="w-full h-full border-0 bg-white"
              sandbox="allow-scripts allow-popups allow-forms allow-modals"
              title={file.name}
            />
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

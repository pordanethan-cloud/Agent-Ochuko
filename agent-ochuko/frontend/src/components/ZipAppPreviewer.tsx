import React, { useState, useEffect, useRef } from 'react'
import JSZip from 'jszip'
import {
  Globe, Eye, Code2, Download, ExternalLink, RotateCw, Monitor, Tablet,
  Smartphone, X, FileText, Check, Copy, FileCode, Loader2, AlertCircle
} from 'lucide-react'

export interface ZipFileEntry {
  path: string
  name: string
  isDir: boolean
  size: number
  text?: string
  blobUrl?: string
  mimeType?: string
}

export interface ZipAppPreviewerProps {
  file: {
    name: string
    url?: string
    localObjectUrl?: string
    sizeBytes?: number
    type?: string
  }
  onClose: () => void
  onDownload?: () => void
}

function guessMimeType(filename: string): string {
  const n = filename.toLowerCase()
  if (n.endsWith('.html') || n.endsWith('.htm')) return 'text/html'
  if (n.endsWith('.css')) return 'text/css'
  if (n.endsWith('.js') || n.endsWith('.mjs')) return 'application/javascript'
  if (n.endsWith('.json')) return 'application/json'
  if (n.endsWith('.svg')) return 'image/svg+xml'
  if (n.endsWith('.png')) return 'image/png'
  if (n.endsWith('.jpg') || n.endsWith('.jpeg')) return 'image/jpeg'
  if (n.endsWith('.gif')) return 'image/gif'
  if (n.endsWith('.webp')) return 'image/webp'
  if (n.endsWith('.ico')) return 'image/x-icon'
  if (n.endsWith('.txt')) return 'text/plain'
  if (n.endsWith('.md')) return 'text/markdown'
  if (n.endsWith('.csv')) return 'text/csv'
  return 'application/octet-stream'
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const ZipAppPreviewer: React.FC<ZipAppPreviewerProps> = ({
  file,
  onClose,
  onDownload,
}) => {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [entries, setEntries] = useState<ZipFileEntry[]>([])
  const [htmlBlobUrl, setHtmlBlobUrl] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'preview' | 'files'>('preview')
  const [selectedFile, setSelectedFile] = useState<ZipFileEntry | null>(null)
  const [viewMode, setViewMode] = useState<'desktop' | 'tablet' | 'mobile'>('desktop')
  const [iframeKey, setIframeKey] = useState(0)
  const [copied, setCopied] = useState(false)
  const [projectTitle, setProjectTitle] = useState<string>(file.name.replace(/\.zip$/i, '').replace(/[-_]/g, ' '))

  const createdUrlsRef = useRef<string[]>([])

  // Cleanup created object URLs on unmount
  useEffect(() => {
    return () => {
      createdUrlsRef.current.forEach((url) => {
        try {
          URL.revokeObjectURL(url)
        } catch {
          // ignore
        }
      })
    }
  }, [])

  // Load and unpack ZIP
  useEffect(() => {
    let isCancelled = false

    async function loadZip() {
      setLoading(true)
      setError(null)

      const fileUrl = file.localObjectUrl || file.url
      if (!fileUrl) {
        setError('No download or local URL available for this archive.')
        setLoading(false)
        return
      }

      try {
        const response = await fetch(fileUrl)
        if (!response.ok) {
          throw new Error(`Failed to load archive: HTTP ${response.status}`)
        }
        const blob = await response.blob()
        const zip = await JSZip.loadAsync(blob)

        if (isCancelled) return

        const extractedEntries: ZipFileEntry[] = []
        const assetUrlMap: Record<string, string> = {}
        const cssMap: Record<string, string> = {}
        const jsMap: Record<string, string> = {}

        // 1. First pass: extract all files
        for (const [relativePath, zipEntry] of Object.entries(zip.files)) {
          if (zipEntry.dir) continue

          const cleanPath = relativePath.replace(/\\/g, '/').replace(/^\/+/, '')
          const fileName = cleanPath.split('/').pop() || cleanPath
          const mime = guessMimeType(cleanPath)

          let textContent: string | undefined
          let blobUrl: string | undefined

          if (mime.startsWith('text/') || mime === 'application/javascript' || mime === 'application/json' || mime === 'image/svg+xml') {
            textContent = await zipEntry.async('text')
          }

          const fileBlob = await zipEntry.async('blob')
          blobUrl = URL.createObjectURL(new Blob([fileBlob], { type: mime }))
          createdUrlsRef.current.push(blobUrl)

          // Register in asset map for relative path resolution
          assetUrlMap[cleanPath] = blobUrl
          assetUrlMap['./' + cleanPath] = blobUrl
          assetUrlMap['/' + cleanPath] = blobUrl
          assetUrlMap[fileName] = blobUrl

          if (cleanPath.endsWith('.css') && textContent) {
            cssMap[cleanPath] = textContent
            cssMap[fileName] = textContent
          }
          if ((cleanPath.endsWith('.js') || cleanPath.endsWith('.mjs')) && textContent) {
            jsMap[cleanPath] = textContent
            jsMap[fileName] = textContent
          }

          extractedEntries.push({
            path: cleanPath,
            name: fileName,
            isDir: false,
            size: (zipEntry as any)._data?.uncompressedSize || fileBlob.size,
            text: textContent,
            blobUrl,
            mimeType: mime,
          })
        }

        if (isCancelled) return
        setEntries(extractedEntries)

        // 2. Find primary HTML entrypoint
        const htmlEntry =
          extractedEntries.find((e) => /index\.html?$/i.test(e.path)) ||
          extractedEntries.find((e) => /\.html?$/i.test(e.path))

        if (htmlEntry && htmlEntry.text) {
          let html = htmlEntry.text

          // Parse page title if present
          const titleMatch = html.match(/<title>([^<]+)<\/title>/i)
          if (titleMatch && titleMatch[1]) {
            setProjectTitle(titleMatch[1].trim())
          }

          // Inline local CSS <link rel="stylesheet" href="...">
          html = html.replace(/<link\s+[^>]*rel=["']stylesheet["'][^>]*href=["']([^"']+)["'][^>]*>/gi, (match, href) => {
            const cleanHref = href.replace(/^[./]+/, '')
            const inlined = cssMap[cleanHref] || cssMap[href]
            if (inlined) {
              return `<style data-inlined-from="${href}">\n${inlined}\n</style>`
            }
            const blobHref = assetUrlMap[cleanHref] || assetUrlMap[href]
            return blobHref ? `<link rel="stylesheet" href="${blobHref}">` : match
          })

          // Inline local scripts <script src="..."></script>
          html = html.replace(/<script\s+[^>]*src=["']([^"']+)["'][^>]*>\s*<\/script>/gi, (match, src) => {
            if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('//')) {
              return match
            }
            const cleanSrc = src.replace(/^[./]+/, '')
            const inlined = jsMap[cleanSrc] || jsMap[src]
            if (inlined) {
              return `<script data-inlined-from="${src}">\n${inlined}\n</script>`
            }
            const blobSrc = assetUrlMap[cleanSrc] || assetUrlMap[src]
            return blobSrc ? `<script src="${blobSrc}"></script>` : match
          })

          // Replace image and media src attributes with Blob URLs
          html = html.replace(/(src|href)=["'](?!http:\/\/|https:\/\/|data:|#|\/\/)([^"']+)["']/gi, (match, attr, path) => {
            const cleanPath = path.replace(/^[./]+/, '')
            const mapped = assetUrlMap[cleanPath] || assetUrlMap[path]
            return mapped ? `${attr}="${mapped}"` : match
          })

          // Ensure base tag allows local relative resolution
          if (!html.includes('<meta name="viewport"')) {
            html = html.replace(/<head>/i, '<head>\n<meta name="viewport" content="width=device-width, initial-scale=1.0">')
          }

          const pageBlob = new Blob([html], { type: 'text/html;charset=utf-8' })
          const pageUrl = URL.createObjectURL(pageBlob)
          createdUrlsRef.current.push(pageUrl)

          setHtmlBlobUrl(pageUrl)
          setActiveTab('preview')
          setSelectedFile(htmlEntry)
        } else {
          // No HTML found; fall back to files explorer tab
          setActiveTab('files')
          setSelectedFile(extractedEntries[0] || null)
        }
      } catch (err: any) {
        if (!isCancelled) {
          console.error('Error unpacking ZIP preview:', err)
          setError(err.message || 'Failed to read ZIP contents')
        }
      } finally {
        if (!isCancelled) {
          setLoading(false)
        }
      }
    }

    loadZip()

    return () => {
      isCancelled = true
    }
  }, [file])

  const handleCopyCode = async () => {
    if (!selectedFile?.text) return
    try {
      await navigator.clipboard.writeText(selectedFile.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }

  const handleDirectDownload = () => {
    if (onDownload) {
      onDownload()
      return
    }
    const downloadUrl = file.localObjectUrl || file.url
    if (downloadUrl) {
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = file.name
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  const handleDownloadSingleFile = (entry: ZipFileEntry) => {
    if (!entry.blobUrl) return
    const a = document.createElement('a')
    a.href = entry.blobUrl
    a.download = entry.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  return (
    <div
      className="fixed inset-0 bg-[#07080a]/95 backdrop-blur-md z-[100] flex flex-col items-center justify-between p-2 sm:p-4 md:p-6 animate-fadeIn select-none"
      onClick={onClose}
    >
      {/* ── Top Header Navigation Bar ────────────────────────────── */}
      <div
        className="w-full max-w-7xl flex items-center justify-between pb-3 border-b border-[#1e2025] mb-2 sm:mb-3 relative z-10 shrink-0 gap-2 sm:gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Project Title & Status */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 shadow-inner">
            {htmlBlobUrl ? <Globe className="w-4 h-4 text-indigo-300" /> : <FileCode className="w-4 h-4 text-indigo-300" />}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-[13px] sm:text-[14px] font-bold text-white tracking-tight truncate capitalize">
                {projectTitle}
              </h3>
              <span className="px-2 py-0.5 rounded-full text-[9px] font-semibold tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 uppercase shrink-0">
                {htmlBlobUrl ? 'Live Website' : 'Archive'}
              </span>
            </div>
            <p className="text-[10px] text-white/50 flex items-center gap-1.5 truncate">
              <span className="font-mono">{file.name}</span>
              {entries.length > 0 && (
                <>
                  <span>•</span>
                  <span>{entries.length} files</span>
                </>
              )}
              {file.sizeBytes && (
                <>
                  <span>•</span>
                  <span>{formatBytes(file.sizeBytes)}</span>
                </>
              )}
            </p>
          </div>
        </div>

        {/* Center Mode Switcher & Viewport Toggles (Desktop only) */}
        <div className="flex items-center gap-1 sm:gap-2">
          {htmlBlobUrl && (
            <div className="flex items-center p-0.5 rounded-lg bg-white/[0.05] border border-white/[0.1]">
              <button
                type="button"
                onClick={() => setActiveTab('preview')}
                className={`px-2.5 sm:px-3 py-1 rounded-md text-[11px] font-semibold flex items-center gap-1.5 transition ${
                  activeTab === 'preview'
                    ? 'bg-white text-black shadow-sm'
                    : 'text-white/70 hover:text-white hover:bg-white/[0.05]'
                }`}
              >
                <Eye className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Preview App</span>
                <span className="sm:hidden">App</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('files')}
                className={`px-2.5 sm:px-3 py-1 rounded-md text-[11px] font-semibold flex items-center gap-1.5 transition ${
                  activeTab === 'files'
                    ? 'bg-white text-black shadow-sm'
                    : 'text-white/70 hover:text-white hover:bg-white/[0.05]'
                }`}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Project Files</span>
                <span className="sm:hidden">Files</span>
              </button>
            </div>
          )}

          {activeTab === 'preview' && htmlBlobUrl && (
            <div className="hidden md:flex items-center gap-1 p-0.5 rounded-lg bg-white/[0.04] border border-white/[0.08]">
              <button
                type="button"
                onClick={() => setViewMode('desktop')}
                className={`p-1.5 rounded text-xs transition ${
                  viewMode === 'desktop' ? 'bg-white/20 text-white' : 'text-white/40 hover:text-white'
                }`}
                title="Desktop View (100%)"
              >
                <Monitor className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('tablet')}
                className={`p-1.5 rounded text-xs transition ${
                  viewMode === 'tablet' ? 'bg-white/20 text-white' : 'text-white/40 hover:text-white'
                }`}
                title="Tablet View (768px)"
              >
                <Tablet className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('mobile')}
                className={`p-1.5 rounded text-xs transition ${
                  viewMode === 'mobile' ? 'bg-white/20 text-white' : 'text-white/40 hover:text-white'
                }`}
                title="Mobile View (375px)"
              >
                <Smartphone className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        {/* Right Action Icons */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          {activeTab === 'preview' && htmlBlobUrl && (
            <>
              <button
                type="button"
                onClick={() => setIframeKey((prev) => prev + 1)}
                className="p-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-white/70 hover:text-white border border-white/10 transition"
                title="Reload Preview"
              >
                <RotateCw className="w-3.5 h-3.5" />
              </button>

              <a
                href={htmlBlobUrl}
                target="_blank"
                rel="noreferrer"
                className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-[11px] font-semibold text-white/80 hover:text-white border border-white/10 transition"
                title="Open in new window"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open in Tab</span>
              </a>
            </>
          )}

          <button
            type="button"
            onClick={handleDirectDownload}
            className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 text-[11px] font-semibold transition shadow-sm"
            title="Download ZIP archive"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Download ZIP</span>
          </button>

          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onClose()
            }}
            className="p-1.5 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-white/70 hover:text-white border border-white/10 transition ml-1 cursor-pointer touch-manipulation"
            title="Close Preview (Esc)"
          >
            <X className="w-4 h-4 pointer-events-none" />
          </button>
        </div>
      </div>

      {/* ── Main Content Area ─────────────────────────────────────── */}
      <div
        className="flex-1 w-full max-w-7xl h-[calc(100%-60px)] min-h-0 flex items-center justify-center overflow-hidden relative rounded-xl bg-[#0c0d11] border border-white/[0.08] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex flex-col items-center justify-center gap-3 text-white/70">
            <Loader2 className="w-8 h-8 animate-spin text-brand-accent" />
            <span className="text-xs font-mono">Unpacking website bundle...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center max-w-md p-6 text-center space-y-3">
            <AlertCircle className="w-10 h-10 text-amber-400" />
            <h4 className="text-sm font-bold text-white">Could not preview archive</h4>
            <p className="text-xs text-white/60">{error}</p>
            <button
              type="button"
              onClick={handleDirectDownload}
              className="px-4 py-2 rounded-lg bg-white text-black font-bold text-xs hover:bg-white/90 transition flex items-center gap-2 mt-2"
            >
              <Download className="w-4 h-4" />
              <span>Download File Instead</span>
            </button>
          </div>
        ) : activeTab === 'preview' && htmlBlobUrl ? (
          /* Live Website Iframe View */
          <div className="w-full h-full flex items-center justify-center bg-[#07080a] p-1 sm:p-3 overflow-hidden">
            <div
              style={{
                width: viewMode === 'mobile' ? '375px' : viewMode === 'tablet' ? '768px' : '100%',
                maxWidth: '100%',
                transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
              className="h-full bg-white rounded-lg overflow-hidden shadow-2xl border border-white/10 relative"
            >
              <iframe
                key={iframeKey}
                src={htmlBlobUrl}
                className="w-full h-full border-0 bg-white"
                sandbox="allow-scripts allow-forms allow-modals allow-popups allow-same-origin"
                title={projectTitle}
              />
            </div>
          </div>
        ) : (
          /* Project Files & Code Explorer */
          <div className="w-full h-full flex flex-col md:flex-row min-h-0 overflow-hidden divide-y md:divide-y-0 md:divide-x divide-white/[0.08]">
            {/* File List Drawer */}
            <div className="w-full md:w-72 lg:w-80 h-48 md:h-full flex flex-col bg-[#101216] shrink-0 min-h-0">
              <div className="p-3 border-b border-white/[0.08] flex items-center justify-between">
                <span className="text-[11px] font-bold text-white/70 uppercase tracking-wider">
                  Files ({entries.length})
                </span>
                <span className="text-[10px] text-white/40 font-mono">
                  {formatBytes(entries.reduce((acc, e) => acc + e.size, 0))}
                </span>
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-0.5 custom-scrollbar">
                {entries.map((entry) => {
                  const isSelected = selectedFile?.path === entry.path
                  return (
                    <button
                      key={entry.path}
                      type="button"
                      onClick={() => setSelectedFile(entry)}
                      className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left text-xs transition ${
                        isSelected
                          ? 'bg-white/15 text-white font-semibold'
                          : 'text-white/70 hover:text-white hover:bg-white/[0.05]'
                      }`}
                    >
                      <FileCode className={`w-3.5 h-3.5 shrink-0 ${isSelected ? 'text-indigo-400' : 'text-white/40'}`} />
                      <span className="truncate flex-1 font-mono text-[11.5px]">{entry.path}</span>
                      <span className="text-[10px] text-white/30 font-mono shrink-0">{formatBytes(entry.size)}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Code / Content Viewer */}
            <div className="flex-1 h-full flex flex-col bg-[#0b0c0f] min-h-0 overflow-hidden">
              {selectedFile ? (
                <>
                  <div className="p-2.5 sm:p-3 border-b border-white/[0.08] flex items-center justify-between bg-white/[0.02]">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      <span className="text-xs font-mono font-bold text-white truncate">{selectedFile.path}</span>
                      <span className="text-[10px] text-white/40 font-mono">({formatBytes(selectedFile.size)})</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {selectedFile.text && (
                        <button
                          type="button"
                          onClick={handleCopyCode}
                          className="flex items-center gap-1 px-2.5 py-1 rounded bg-white/[0.05] hover:bg-white/[0.1] text-[11px] text-white/80 transition"
                          title="Copy file contents"
                        >
                          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                          <span>{copied ? 'Copied' : 'Copy'}</span>
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => handleDownloadSingleFile(selectedFile)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-white/[0.05] hover:bg-white/[0.1] text-[11px] text-white/80 transition"
                        title="Download file"
                      >
                        <Download className="w-3 h-3" />
                        <span>Save</span>
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 overflow-auto p-4 custom-scrollbar">
                    {selectedFile.mimeType?.startsWith('image/') ? (
                      <div className="w-full h-full flex items-center justify-center p-6">
                        <img
                          src={selectedFile.blobUrl}
                          alt={selectedFile.name}
                          className="max-w-full max-h-[70vh] object-contain rounded border border-white/10 shadow-lg"
                        />
                      </div>
                    ) : selectedFile.text ? (
                      <pre className="font-mono text-xs text-[#c9d1d9] leading-relaxed whitespace-pre-wrap select-text">
                        {selectedFile.text}
                      </pre>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-center p-8 text-white/50 space-y-2">
                        <FileText className="w-8 h-8 opacity-40" />
                        <p className="text-xs">Binary file cannot be viewed as text.</p>
                        <button
                          type="button"
                          onClick={() => handleDownloadSingleFile(selectedFile)}
                          className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-semibold"
                        >
                          Download {selectedFile.name}
                        </button>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-white/40 text-xs font-mono">
                  Select a file from the left to view its contents
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="mt-2 text-center text-[10.5px] text-white/30 shrink-0">
        Press <span className="text-white/60 font-mono">ESC</span> or click outside to close preview
      </div>
    </div>
  )
}

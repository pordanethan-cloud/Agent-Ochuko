import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  FileText, X, Download, Code2, Eye, Globe, Monitor, Smartphone, Copy, Check,
  Folder, FolderOpen, ChevronRight, ChevronDown, Search, PanelLeftClose, PanelLeftOpen,
  FileCode, FileSpreadsheet, Image as ImageIcon, FileArchive, Terminal, ExternalLink,
  Layers
} from 'lucide-react'

export interface NavigatableFile {
  name: string
  type?: string
  url?: string
  localObjectUrl?: string
  content?: string
  sizeBytes?: number
}

export interface ArtifactFile {
  name: string
  type: string
  url?: string
  localObjectUrl?: string
  content?: string
  sizeBytes?: number
  siteSlug?: string
  projectFiles?: Record<string, string> | NavigatableFile[]
  siblingFiles?: NavigatableFile[]
}

export interface ArtifactPanelProps {
  file: ArtifactFile
  content: string | null
  loading: boolean
  renderMarkdown: (text: string, generatedFiles?: any[]) => React.ReactNode
  onClose: () => void
  onPublish?: () => void
  allConversationFiles?: NavigatableFile[]
}

const MIN_WIDTH = 380
const DEFAULT_WIDTH = 560
const REPO_WIDTH = 840

function normalizePath(p: string): string {
  if (!p) return ''
  return p.replace(/\\/g, '/').replace(/^\/+/, '').trim()
}

function kindOf(file: { name: string; type?: string }): 'html' | 'svg' | 'md' | 'csv' | 'image' | 'code' {
  const n = (file.name || '').toLowerCase()
  const t = (file.type || '').toLowerCase()
  if (t === 'image/svg+xml' || n.endsWith('.svg')) return 'svg'
  if (t === 'text/html' || t === 'html' || n.endsWith('.html') || n.endsWith('.htm')) return 'html'
  if (n.endsWith('.md') || n.endsWith('.markdown') || t === 'text/markdown') return 'md'
  if (n.endsWith('.csv') || t === 'text/csv') return 'csv'
  if (t.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|ico)$/i.test(n)) return 'image'
  return 'code'
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getFileIcon(filename: string) {
  const n = filename.toLowerCase()
  if (n.endsWith('.html') || n.endsWith('.htm')) {
    return <Globe className="w-3.5 h-3.5 text-amber-400 shrink-0" />
  }
  if (n.endsWith('.css') || n.endsWith('.scss') || n.endsWith('.sass') || n.endsWith('.less')) {
    return <Code2 className="w-3.5 h-3.5 text-sky-400 shrink-0" />
  }
  if (n.endsWith('.js') || n.endsWith('.jsx') || n.endsWith('.mjs')) {
    return <FileCode className="w-3.5 h-3.5 text-yellow-400 shrink-0" />
  }
  if (n.endsWith('.ts') || n.endsWith('.tsx')) {
    return <FileCode className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
  }
  if (n.endsWith('.json')) {
    return <FileCode className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
  }
  if (n.endsWith('.py')) {
    return <Terminal className="w-3.5 h-3.5 text-blue-400 shrink-0" />
  }
  if (n.endsWith('.md') || n.endsWith('.markdown') || n.endsWith('.txt')) {
    return <FileText className="w-3.5 h-3.5 text-purple-400 shrink-0" />
  }
  if (/\.(png|jpe?g|webp|gif|svg|ico)$/i.test(n)) {
    return <ImageIcon className="w-3.5 h-3.5 text-pink-400 shrink-0" />
  }
  if (/\.(csv|tsv|xlsx?)$/i.test(n)) {
    return <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
  }
  if (/\.(zip|tar|gz|7z|rar)$/i.test(n)) {
    return <FileArchive className="w-3.5 h-3.5 text-amber-500 shrink-0" />
  }
  return <FileText className="w-3.5 h-3.5 text-white/50 shrink-0" />
}

interface FileTreeNode {
  name: string
  path: string
  isFolder: boolean
  children?: FileTreeNode[]
  file?: NavigatableFile
  itemCount?: number
}

function buildFileTree(files: NavigatableFile[]): FileTreeNode[] {
  const rootNodes: FileTreeNode[] = []

  for (const file of files) {
    const rawPath = normalizePath(file.name)
    if (!rawPath) continue
    const parts = rawPath.split('/').filter(Boolean)
    if (parts.length === 0) continue

    let currentLevel = rootNodes
    let accumulatedPath = ''

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      accumulatedPath = accumulatedPath ? `${accumulatedPath}/${part}` : part
      const isLast = i === parts.length - 1

      if (isLast) {
        currentLevel.push({
          name: part,
          path: accumulatedPath,
          isFolder: false,
          file: { ...file, name: accumulatedPath },
        })
      } else {
        let folderNode = currentLevel.find((n) => n.isFolder && n.name === part)
        if (!folderNode) {
          folderNode = {
            name: part,
            path: accumulatedPath,
            isFolder: true,
            children: [],
          }
          currentLevel.push(folderNode)
        }
        currentLevel = folderNode.children!
      }
    }
  }

  function finalizeNodes(nodes: FileTreeNode[]): FileTreeNode[] {
    nodes.sort((a, b) => {
      if (a.isFolder && !b.isFolder) return -1
      if (!a.isFolder && b.isFolder) return 1
      return a.name.localeCompare(b.name)
    })
    for (const node of nodes) {
      if (node.isFolder && node.children) {
        finalizeNodes(node.children)
        let count = 0
        const countFiles = (list: FileTreeNode[]) => {
          for (const item of list) {
            if (item.isFolder && item.children) countFiles(item.children)
            else count++
          }
        }
        countFiles(node.children)
        node.itemCount = count
      }
    }
    return nodes
  }

  return finalizeNodes(rootNodes)
}

function filterTree(nodes: FileTreeNode[], query: string): FileTreeNode[] {
  if (!query.trim()) return nodes
  const q = query.toLowerCase()

  function filterNodes(list: FileTreeNode[]): FileTreeNode[] {
    const result: FileTreeNode[] = []
    for (const node of list) {
      if (node.isFolder && node.children) {
        const filteredChildren = filterNodes(node.children)
        if (filteredChildren.length > 0 || node.name.toLowerCase().includes(q)) {
          result.push({
            ...node,
            children: filteredChildren,
          })
        }
      } else if (!node.isFolder) {
        if (node.name.toLowerCase().includes(q) || node.path.toLowerCase().includes(q)) {
          result.push(node)
        }
      }
    }
    return result
  }

  return filterNodes(nodes)
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

export function ArtifactPanel({
  file,
  content,
  loading,
  renderMarkdown,
  onClose,
  onPublish,
  allConversationFiles,
}: ArtifactPanelProps) {
  // ── Active File & Content State ──────────────────────────────────────────
  const [activeFile, setActiveFile] = useState<NavigatableFile>(file)
  const [contentCache, setContentCache] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    const p = normalizePath(file.name)
    if (content) init[p] = content
    if (file.content) init[p] = file.content
    return init
  })
  const [activeContentLoading, setActiveContentLoading] = useState(false)
  const [siteFetchedFiles, setSiteFetchedFiles] = useState<NavigatableFile[]>([])

  // ── Repo Tree / Sidebar UI State ─────────────────────────────────────────
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [openFolders, setOpenFolders] = useState<Set<string>>(new Set())
  const [mobileTab, setMobileTab] = useState<'files' | 'preview'>('preview')

  // ── Viewer Controls State ────────────────────────────────────────────────
  const [tab, setTab] = useState<'render' | 'code'>('render')
  const [device, setDevice] = useState<'desktop' | 'mobile'>('desktop')
  const [copied, setCopied] = useState(false)
  const dragging = useRef(false)

  // Keep activeFile updated if the incoming parent file prop changes
  useEffect(() => {
    setActiveFile(file)
    const p = normalizePath(file.name)
    if (content || file.content) {
      setContentCache((prev) => ({
        ...prev,
        [p]: (content ?? file.content) || '',
      }))
    }
  }, [file, content])

  // ── Fetch Deployed Site Manifest if Available ───────────────────────────
  useEffect(() => {
    const slugMatch = (file.siteSlug || file.url || '').match(/\/sites\/([a-zA-Z0-9\-_]+)/)
    const slug = file.siteSlug || (slugMatch ? slugMatch[1] : undefined)
    if (!slug) return

    let cancelled = false
    const fetchSiteManifest = async () => {
      try {
        const rawUrl = `/v1/sites/${slug}/raw`
        const res = await fetch(rawUrl)
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return

        const filesMap = data.files || {}
        const filesUrls = data.files_urls || {}
        const fetched: NavigatableFile[] = []
        const newCache: Record<string, string> = {}

        for (const [relPath, fileContent] of Object.entries(filesMap)) {
          const norm = normalizePath(relPath)
          const fileUrl = filesUrls[relPath] || `/v1/sites/${slug}/${relPath}`
          fetched.push({
            name: norm,
            content: typeof fileContent === 'string' ? fileContent : undefined,
            url: fileUrl,
            sizeBytes: typeof fileContent === 'string' ? new Blob([fileContent]).size : undefined,
            type: norm.endsWith('.html')
              ? 'text/html'
              : norm.endsWith('.css')
              ? 'text/css'
              : norm.endsWith('.js')
              ? 'application/javascript'
              : 'text/plain',
          })
          if (typeof fileContent === 'string') {
            newCache[norm] = fileContent
          }
        }

        if (fetched.length > 0) {
          setSiteFetchedFiles(fetched)
          setContentCache((prev) => ({ ...prev, ...newCache }))
        }
      } catch (err) {
        console.warn('Could not fetch site repo manifest:', err)
      }
    }
    fetchSiteManifest()
    return () => {
      cancelled = true
    }
  }, [file.siteSlug, file.url])

  // ── Aggregate All Available Files in the Project ────────────────────────
  const allFiles = useMemo<NavigatableFile[]>(() => {
    const map = new Map<string, NavigatableFile>()

    const addFile = (f: NavigatableFile) => {
      const p = normalizePath(f.name)
      if (!p) return
      if (!map.has(p)) {
        map.set(p, { ...f, name: p })
      } else {
        const existing = map.get(p)!
        map.set(p, {
          ...existing,
          ...f,
          name: p,
          content: f.content || existing.content,
          url: f.url || existing.url,
          sizeBytes: f.sizeBytes || existing.sizeBytes,
        })
      }
    }

    // Always include current parent file and active file
    addFile(file)
    if (activeFile) addFile(activeFile)

    // A. Project files map or list
    if (file.projectFiles) {
      if (Array.isArray(file.projectFiles)) {
        for (const pf of file.projectFiles) addFile(pf)
      } else {
        for (const [path, c] of Object.entries(file.projectFiles)) {
          addFile({
            name: path,
            content: typeof c === 'string' ? c : undefined,
            type: typeof c === 'string' ? 'text/plain' : undefined,
          })
        }
      }
    }

    // B. Sibling files passed from task or turn
    if (file.siblingFiles && file.siblingFiles.length > 0) {
      for (const sf of file.siblingFiles) addFile(sf)
    }

    // C. Files fetched from deployed site manifest
    if (siteFetchedFiles.length > 0) {
      for (const sf of siteFetchedFiles) addFile(sf)
    }

    // D. All conversation generated files fallback
    if (map.size <= 1 && allConversationFiles && allConversationFiles.length > 0) {
      for (const cf of allConversationFiles) addFile(cf)
    }

    return Array.from(map.values())
  }, [file, activeFile, siteFetchedFiles, allConversationFiles])

  // Automatically expand all directory folders on initial load
  useEffect(() => {
    const allFolderPaths = new Set<string>()
    for (const f of allFiles) {
      const parts = normalizePath(f.name).split('/')
      let cur = ''
      for (let i = 0; i < parts.length - 1; i++) {
        cur = cur ? `${cur}/${parts[i]}` : parts[i]
        allFolderPaths.add(cur)
      }
    }
    setOpenFolders(allFolderPaths)
  }, [allFiles])

  // Determine initial panel width based on multi-file presence
  const [width, setWidth] = useState(() => (allFiles.length > 1 ? REPO_WIDTH : DEFAULT_WIDTH))

  // Update default width if multiple files become discovered
  useEffect(() => {
    if (allFiles.length > 1 && width < 720) {
      setWidth(REPO_WIDTH)
    }
  }, [allFiles.length])

  // Drag resizing logic
  const startDrag = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    e.preventDefault()
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const w = window.innerWidth - e.clientX
      setWidth(Math.min(Math.max(w, MIN_WIDTH), Math.min(1300, window.innerWidth - 40)))
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  // Keyboard shortcut Esc to close, Ctrl+B / Cmd+B to toggle sidebar
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        setIsSidebarOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // ── Active File Attributes & Render Kind ────────────────────────────────
  const activeNormalizedPath = normalizePath(activeFile.name)
  const activeKind = kindOf(activeFile)
  const canRender = activeKind === 'html' || activeKind === 'svg' || activeKind === 'md' || activeKind === 'csv' || activeKind === 'image'
  const activeText = contentCache[activeNormalizedPath] ?? activeFile.content ?? (activeNormalizedPath === normalizePath(file.name) ? (content ?? file.content ?? '') : '')
  const activeFileUrl = activeFile.localObjectUrl || activeFile.url || (activeNormalizedPath === normalizePath(file.name) ? (file.localObjectUrl || file.url) : undefined)

  // ── Handle Selecting File From Tree ─────────────────────────────────────
  const handleSelectFile = async (selected: NavigatableFile) => {
    const norm = normalizePath(selected.name)
    setActiveFile(selected)
    setMobileTab('preview')

    // If text content is not yet in cache, fetch it dynamically
    const cached = contentCache[norm] || selected.content
    if (!cached && selected.url) {
      const k = kindOf(selected)
      if (k !== 'image') {
        setActiveContentLoading(true)
        try {
          const res = await fetch(selected.url)
          if (res.ok) {
            const fetched = await res.text()
            setContentCache((prev) => ({ ...prev, [norm]: fetched }))
          }
        } catch (err) {
          console.warn('Failed to load file content:', err)
        } finally {
          setActiveContentLoading(false)
        }
      }
    }
  }

  // ── Folder Collapse / Expand Toggle ────────────────────────────────────
  const toggleFolder = (folderPath: string) => {
    setOpenFolders((prev) => {
      const next = new Set(prev)
      if (next.has(folderPath)) next.delete(folderPath)
      else next.add(folderPath)
      return next
    })
  }

  // ── Copy Active File Content ────────────────────────────────────────────
  const handleCopy = async () => {
    let toCopy = activeText
    if (!toCopy && activeFileUrl) {
      try {
        const res = await fetch(activeFileUrl)
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

  // ── Download Active File ────────────────────────────────────────────────
  const handleDownloadActive = async () => {
    try {
      let blob: Blob
      if (activeText) {
        blob = new Blob([activeText], { type: activeFile.type || 'text/plain;charset=utf-8' })
      } else if (activeFileUrl) {
        const res = await fetch(activeFileUrl)
        blob = await res.blob()
      } else {
        return
      }
      const safeName = activeFile.name ? activeFile.name.split('/').pop() || activeFile.name : 'download'
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
      if (activeFileUrl) {
        const a = document.createElement('a')
        a.href = activeFileUrl
        a.download = activeFile.name ? activeFile.name.split('/').pop() || activeFile.name : 'download'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      }
    }
  }

  // Check if a project ZIP archive is available among the files
  const projectZipFile = useMemo(() => {
    return allFiles.find((f) => f.name.toLowerCase().endsWith('.zip') || f.name.toLowerCase() === 'project.zip')
  }, [allFiles])

  // Build and filter file tree
  const fileTree = useMemo(() => {
    const rawTree = buildFileTree(allFiles)
    return filterTree(rawTree, searchQuery)
  }, [allFiles, searchQuery])

  // Breadcrumbs representation: e.g. [ "repo", "src", "components", "Header.tsx" ]
  const breadcrumbParts = useMemo(() => {
    const norm = normalizePath(activeFile.name)
    return ['repo', ...norm.split('/')]
  }, [activeFile.name])

  // ── Recursive Tree Renderer ─────────────────────────────────────────────
  const renderTreeNodes = (nodes: FileTreeNode[], depth = 0) => {
    return nodes.map((node) => {
      if (node.isFolder) {
        const isOpen = openFolders.has(node.path)
        return (
          <div key={`folder-${node.path}`} className="select-none">
            <button
              type="button"
              onClick={() => toggleFolder(node.path)}
              style={{ paddingLeft: `${depth * 14 + 10}px` }}
              className="w-full flex items-center gap-1.5 py-1.5 pr-2 rounded hover:bg-white/[0.04] text-left transition group/f"
            >
              <span className="text-white/40 group-hover/f:text-white/70 transition-transform shrink-0">
                {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </span>
              <span className="text-amber-400/90 shrink-0">
                {isOpen ? <FolderOpen className="w-3.5 h-3.5" /> : <Folder className="w-3.5 h-3.5" />}
              </span>
              <span className="text-[12px] font-medium text-white/80 truncate">{node.name}</span>
              {node.itemCount !== undefined && (
                <span className="ml-auto text-[9.5px] font-mono text-white/30 shrink-0">
                  {node.itemCount}
                </span>
              )}
            </button>
            {isOpen && node.children && node.children.length > 0 && (
              <div className="relative">
                {/* Visual directory nesting guideline */}
                <div
                  className="absolute top-0 bottom-0 border-l border-white/[0.06]"
                  style={{ left: `${depth * 14 + 16}px` }}
                />
                {renderTreeNodes(node.children, depth + 1)}
              </div>
            )}
          </div>
        )
      }

      // File Node
      const isSelected = normalizePath(node.path) === activeNormalizedPath
      return (
        <button
          key={`file-${node.path}`}
          type="button"
          onClick={() => node.file && handleSelectFile(node.file)}
          style={{ paddingLeft: `${depth * 14 + 18}px` }}
          className={`w-full flex items-center gap-2 py-1.5 pr-2.5 rounded text-left transition relative group/file ${
            isSelected
              ? 'bg-brand-primary/20 text-white font-semibold'
              : 'hover:bg-white/[0.04] text-white/70 hover:text-white'
          }`}
        >
          {isSelected && (
            <div className="absolute left-0 top-1 bottom-1 w-0.5 bg-brand-primary rounded-r" />
          )}
          {getFileIcon(node.name)}
          <span className="text-[11.5px] font-mono truncate min-w-0 flex-1">{node.name}</span>
          {node.file?.sizeBytes ? (
            <span className="text-[9px] font-mono text-white/30 shrink-0">
              {formatBytes(node.file.sizeBytes)}
            </span>
          ) : null}
        </button>
      )
    })
  }

  return (
    <div
      className="fixed top-0 right-0 h-[100dvh] max-h-[100dvh] bg-[#0d0f11] border-l border-white/10 z-[100] flex flex-col animate-[slideInRight_0.2s_ease-out] max-md:w-full shadow-2xl"
      style={{ width: `min(${width}px, 100vw)` }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Resizing Drag Handle (Desktop) */}
      <div
        className="absolute left-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-brand-primary/50 transition max-md:hidden z-10"
        onMouseDown={startDrag}
        title="Drag to resize panel"
      />

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-white/[0.08] shrink-0 bg-[#0f1115] max-md:pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div className="flex items-center gap-2 min-w-0">
          {/* Toggle Sidebar Button */}
          {allFiles.length > 1 && (
            <button
              type="button"
              onClick={() => setIsSidebarOpen((prev) => !prev)}
              title={isSidebarOpen ? "Hide File Tree (Ctrl+B)" : "Show File Tree (Ctrl+B)"}
              className="p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition shrink-0 max-md:hidden"
            >
              {isSidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4 text-brand-primary" />}
            </button>
          )}

          {/* Breadcrumbs Navigation */}
          <div className="flex items-center gap-1 text-[11px] font-mono text-white/50 overflow-hidden text-ellipsis whitespace-nowrap min-w-0">
            {breadcrumbParts.map((part, idx) => {
              const isLast = idx === breadcrumbParts.length - 1
              return (
                <span key={idx} className="flex items-center gap-1 shrink-0">
                  {idx > 0 && <span className="text-white/20">/</span>}
                  <span className={isLast ? 'text-white font-semibold flex items-center gap-1.5' : 'text-white/40 hover:text-white/60'}>
                    {isLast && getFileIcon(part)}
                    {part}
                  </span>
                </span>
              )
            })}
          </div>

          {/* Active File Badge */}
          {activeFile.sizeBytes ? (
            <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-white/40 border border-white/10 shrink-0 hidden sm:inline-block">
              {formatBytes(activeFile.sizeBytes)}
            </span>
          ) : null}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1 shrink-0 ml-2">
          {/* Copy Active File Content */}
          <button
            type="button"
            onClick={handleCopy}
            title={copied ? "Copied to clipboard!" : "Copy active file content"}
            className="p-1.5 min-w-[34px] min-h-[34px] flex items-center justify-center rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          {/* Download Active File */}
          {(activeText || activeFileUrl) && (
            <button
              type="button"
              onClick={handleDownloadActive}
              title={`Download ${activeFile.name.split('/').pop()}`}
              className="p-1.5 min-w-[34px] min-h-[34px] flex items-center justify-center rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Download Project ZIP if available */}
          {projectZipFile && projectZipFile.url && (
            <a
              href={projectZipFile.url}
              download={projectZipFile.name}
              title="Download Full Project ZIP"
              className="px-2 py-1 min-h-[34px] rounded-md bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 text-[10px] font-mono font-semibold flex items-center gap-1 transition"
            >
              <FileArchive className="w-3 h-3" />
              <span className="hidden sm:inline">ZIP</span>
            </a>
          )}

          {/* External Site Link if active file has URL */}
          {activeFileUrl && activeFileUrl.startsWith('http') && (
            <a
              href={activeFileUrl}
              target="_blank"
              rel="noopener noreferrer"
              title="Open in new tab"
              className="p-1.5 min-w-[34px] min-h-[34px] flex items-center justify-center rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}

          {/* Publish Action */}
          {onPublish && (
            <button
              type="button"
              onClick={onPublish}
              title="Publish artifact"
              className="p-1.5 min-w-[34px] min-h-[34px] flex items-center justify-center rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <Globe className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Close Panel */}
          <button
            type="button"
            onClick={onClose}
            title="Close Preview (Esc)"
            className="p-1.5 min-w-[34px] min-h-[34px] flex items-center justify-center rounded-md text-white/50 hover:text-white hover:bg-white/10 transition ml-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Mobile View Switcher Tab (Only on small screens when multi-file) ── */}
      {allFiles.length > 1 && (
        <div className="md:hidden flex items-center border-b border-white/10 bg-[#0a0c0e]">
          <button
            type="button"
            onClick={() => setMobileTab('files')}
            className={`flex-1 py-2.5 min-h-[44px] text-xs font-semibold text-center transition flex items-center justify-center gap-1.5 ${
              mobileTab === 'files' ? 'text-white border-b-2 border-brand-primary bg-white/5' : 'text-white/40'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Files ({allFiles.length})
          </button>
          <button
            type="button"
            onClick={() => setMobileTab('preview')}
            className={`flex-1 py-2.5 min-h-[44px] text-xs font-semibold text-center transition flex items-center justify-center gap-1.5 ${
              mobileTab === 'preview' ? 'text-white border-b-2 border-brand-primary bg-white/5' : 'text-white/40'
            }`}
          >
            <Eye className="w-3.5 h-3.5" />
            Preview
          </button>
        </div>
      )}

      {/* ── Main Workspace Body: File Tree + Preview Canvas ────────────────── */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* ── Left Sidebar: Repository File Tree ───────────────────────────── */}
        {allFiles.length > 1 && isSidebarOpen && (
          <div
            className={`w-[230px] sm:w-[250px] shrink-0 border-r border-white/[0.08] bg-[#0c0e12] flex flex-col ${
              mobileTab === 'preview' ? 'max-md:hidden' : 'max-md:w-full'
            }`}
          >
            {/* Repo Header & Filter Input */}
            <div className="p-2.5 border-b border-white/[0.06] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider font-bold text-white/60 flex items-center gap-1.5">
                  <Folder className="w-3.5 h-3.5 text-brand-primary" />
                  Repository Files
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-white/40 border border-white/5">
                  {allFiles.length}
                </span>
              </div>

              {/* Quick Filter */}
              <div className="relative">
                <Search className="w-3 h-3 text-white/30 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter files..."
                  className="w-full pl-7 pr-6 py-1 bg-white/5 border border-white/10 rounded text-[11px] text-white placeholder-white/25 focus:outline-none focus:border-brand-primary/50 font-mono transition"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-white/30 hover:text-white"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Tree File List */}
            <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5 scrollbar-thin">
              {fileTree.length > 0 ? (
                renderTreeNodes(fileTree)
              ) : (
                <p className="text-[11px] text-white/30 p-3 text-center">No matching files</p>
              )}
            </div>
          </div>
        )}

        {/* ── Right Content Area: Active File Viewer / Canvas ──────────────── */}
        <div
          className={`flex-1 min-w-0 flex flex-col bg-[#0b0c0f] ${
            allFiles.length > 1 && mobileTab === 'files' ? 'max-md:hidden' : ''
          }`}
        >
          {/* Sub-header: Render / Code Tabs & Viewport Switcher */}
          {canRender && (
            <div className="flex items-center justify-between px-3 pt-2.5 pb-2 border-b border-white/[0.04] bg-[#0d0f13] shrink-0">
              <div className="flex items-center gap-1">
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

              {/* Viewport Toggle for HTML */}
              {activeKind === 'html' && tab === 'render' && activeFileUrl && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setDevice('desktop')}
                    title="Desktop Viewport"
                    className={`p-1.5 rounded-md transition ${
                      device === 'desktop' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
                    }`}
                  >
                    <Monitor className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDevice('mobile')}
                    title="Mobile Viewport (390px)"
                    className={`p-1.5 rounded-md transition ${
                      device === 'mobile' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
                    }`}
                  >
                    <Smartphone className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Canvas Body */}
          <div className="flex-1 min-h-0 overflow-hidden relative">
            {loading || activeContentLoading ? (
              <div className="h-full flex flex-col items-center justify-center gap-2 text-white/50 text-xs font-mono">
                <div className="w-5 h-5 border-2 border-brand-primary border-t-transparent rounded-full animate-spin" />
                Loading {activeFile.name}...
              </div>
            ) : canRender && tab === 'render' ? (
              activeKind === 'html' ? (
                activeFileUrl ? (
                  <div
                    className={`h-full flex justify-center bg-[#07080a] ${
                      device === 'mobile' ? 'items-stretch py-3' : ''
                    }`}
                  >
                    <iframe
                      src={activeFileUrl}
                      className={`h-full border-0 bg-white transition-all duration-200 ${
                        device === 'mobile' ? 'w-[390px] max-w-full rounded-lg shadow-2xl' : 'w-full'
                      }`}
                      sandbox="allow-scripts allow-popups allow-forms allow-modals allow-same-origin"
                      title={activeFile.name}
                    />
                  </div>
                ) : (
                  <iframe
                    srcDoc={activeText || undefined}
                    className="w-full h-full border-0 bg-white"
                    sandbox="allow-scripts allow-popups allow-forms allow-modals"
                    title={activeFile.name}
                  />
                )
              ) : activeKind === 'image' ? (
                <div className="h-full flex items-center justify-center p-6 bg-[#07080a] overflow-auto">
                  <img
                    src={activeFileUrl || (activeText.startsWith('data:') ? activeText : undefined)}
                    alt={activeFile.name}
                    className="max-w-full max-h-full object-contain rounded-md shadow-2xl border border-white/10"
                  />
                </div>
              ) : activeKind === 'svg' ? (
                <div className="h-full overflow-auto p-4 flex items-center justify-center bg-[#07080a]">
                  <iframe
                    srcDoc={activeText || undefined}
                    src={!activeText && activeFileUrl ? activeFileUrl : undefined}
                    className="w-full min-h-[360px] border-0"
                    sandbox="allow-scripts"
                    title={activeFile.name}
                  />
                </div>
              ) : activeKind === 'csv' ? (
                <CsvTable text={activeText} />
              ) : (
                <div className="h-full overflow-auto px-6 py-5 leading-relaxed">
                  {renderMarkdown(activeText)}
                </div>
              )
            ) : (
              /* Code / Text View */
              <div className="h-full overflow-auto bg-[#07080a] p-4 select-text">
                <pre className="text-[#c9d1d9] font-mono text-[12px] leading-relaxed whitespace-pre-wrap">
                  {activeText || (activeFileUrl ? `Loading content from ${activeFileUrl}...` : 'No text content available.')}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

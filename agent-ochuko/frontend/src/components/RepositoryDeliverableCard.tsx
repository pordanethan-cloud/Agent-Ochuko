import React, { useState, useMemo, useEffect } from 'react'
import {
  Folder, FolderOpen, ChevronRight, ChevronDown, Download, Eye, Globe,
  Search, Loader2
} from 'lucide-react'
import JSZip from 'jszip'

export interface DeliverableFile {
  filename: string
  download_url: string
  size_bytes?: number
}

export interface RepositoryDeliverableCardProps {
  files: DeliverableFile[]
  projectName?: string
  onPreview: (file: DeliverableFile, allFiles: DeliverableFile[]) => void
  onDownloadSingle?: (url: string, filename: string) => void
}

interface TreeNode {
  name: string
  path: string
  isFolder: boolean
  children?: TreeNode[]
  file?: DeliverableFile
  sizeBytes?: number
}

function normalizePath(p: string): string {
  if (!p) return ''
  return p.replace(/\\/g, '/').replace(/^\/+/, '').trim()
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getFileBadge(filename: string): { label: string; bg: string; text: string } {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  switch (ext) {
    case 'html':
    case 'htm':
      return { label: 'HTML', bg: 'bg-amber-500/10 border-amber-500/30', text: 'text-amber-400' }
    case 'css':
    case 'scss':
      return { label: 'CSS', bg: 'bg-sky-500/10 border-sky-500/30', text: 'text-sky-400' }
    case 'js':
    case 'jsx':
    case 'mjs':
      return { label: 'JS', bg: 'bg-yellow-500/10 border-yellow-500/30', text: 'text-yellow-400' }
    case 'ts':
    case 'tsx':
      return { label: 'TS', bg: 'bg-cyan-500/10 border-cyan-500/30', text: 'text-cyan-400' }
    case 'svg':
      return { label: 'SVG', bg: 'bg-orange-500/10 border-orange-500/30', text: 'text-orange-400' }
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'webp':
      return { label: 'IMG', bg: 'bg-pink-500/10 border-pink-500/30', text: 'text-pink-400' }
    case 'md':
    case 'markdown':
      return { label: 'MD', bg: 'bg-purple-500/10 border-purple-500/30', text: 'text-purple-400' }
    case 'csv':
    case 'xlsx':
      return { label: 'CSV', bg: 'bg-emerald-500/10 border-emerald-500/30', text: 'text-emerald-400' }
    case 'json':
      return { label: 'JSON', bg: 'bg-indigo-500/10 border-indigo-500/30', text: 'text-indigo-400' }
    case 'py':
      return { label: 'PY', bg: 'bg-blue-500/10 border-blue-500/30', text: 'text-blue-400' }
    case 'zip':
      return { label: 'ZIP', bg: 'bg-amber-600/10 border-amber-600/30', text: 'text-amber-500' }
    default:
      return { label: ext.toUpperCase() || 'FILE', bg: 'bg-white/10 border-white/20', text: 'text-white/70' }
  }
}

function buildTree(files: DeliverableFile[]): TreeNode[] {
  const roots: TreeNode[] = []

  for (const f of files) {
    const norm = normalizePath(f.filename)
    if (!norm) continue
    const parts = norm.split('/')
    let currentLevel = roots
    let accumulated = ''

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      accumulated = accumulated ? `${accumulated}/${part}` : part
      const isLast = i === parts.length - 1

      if (isLast) {
        currentLevel.push({
          name: part,
          path: accumulated,
          isFolder: false,
          file: f,
          sizeBytes: f.size_bytes,
        })
      } else {
        let folderNode = currentLevel.find((n) => n.isFolder && n.name === part)
        if (!folderNode) {
          folderNode = {
            name: part,
            path: accumulated,
            isFolder: true,
            children: [],
          }
          currentLevel.push(folderNode)
        }
        currentLevel = folderNode.children!
      }
    }
  }

  function sortNodes(nodes: TreeNode[]): TreeNode[] {
    nodes.sort((a, b) => {
      if (a.isFolder && !b.isFolder) return -1
      if (!a.isFolder && b.isFolder) return 1
      return a.name.localeCompare(b.name)
    })
    for (const node of nodes) {
      if (node.isFolder && node.children) {
        sortNodes(node.children)
      }
    }
    return nodes
  }

  return sortNodes(roots)
}

export const RepositoryDeliverableCard: React.FC<RepositoryDeliverableCardProps> = ({
  files,
  projectName,
  onPreview,
  onDownloadSingle,
}) => {
  const [treeExpanded, setTreeExpanded] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [zipping, setZipping] = useState(false)
  const [unpackedFiles, setUnpackedFiles] = useState<DeliverableFile[] | null>(null)

  // Separate any existing zip file from individual content files
  const { zipFile, contentFiles } = useMemo(() => {
    let zip: DeliverableFile | null = null
    const regular: DeliverableFile[] = []

    for (const f of files) {
      if (f.filename.toLowerCase().endsWith('.zip')) {
        if (!zip || f.filename.toLowerCase() === 'project.zip') {
          zip = f
        }
      } else {
        regular.push(f)
      }
    }

    // If all files were just a single zip file, regular is empty, keep zip as regular
    if (regular.length === 0 && zip) {
      return { zipFile: zip, contentFiles: [zip] }
    }

    return { zipFile: zip, contentFiles: regular }
  }, [files])

  // Automatically unpack zip contents in-memory to populate the file tree and app title
  useEffect(() => {
    let isCancelled = false
    const regular = files.filter((f) => !f.filename.toLowerCase().endsWith('.zip'))
    const zip = files.find((f) => f.filename.toLowerCase().endsWith('.zip'))

    if (regular.length === 0 && zip && zip.download_url && !zip.download_url.startsWith('sandbox:')) {
      fetch(zip.download_url)
        .then((r) => r.blob())
        .then((blob) => JSZip.loadAsync(blob))
        .then((unzipped) => {
          if (isCancelled) return
          const extracted: DeliverableFile[] = []
          for (const [path, entry] of Object.entries(unzipped.files)) {
            if (entry.dir) continue
            const clean = path.replace(/\\/g, '/').replace(/^\/+/, '')
            extracted.push({
              filename: clean,
              download_url: zip.download_url,
              size_bytes: (entry as any)._data?.uncompressedSize || 0,
            })
          }
          if (extracted.length > 0 && !isCancelled) {
            setUnpackedFiles(extracted)
          }
        })
        .catch((err) => {
          console.warn('RepositoryDeliverableCard: could not unpack zip archive:', err)
        })
    }
    return () => {
      isCancelled = true
    }
  }, [files])

  const effectiveContentFiles = useMemo(() => {
    if (unpackedFiles && unpackedFiles.length > 0) {
      return unpackedFiles
    }
    return contentFiles
  }, [unpackedFiles, contentFiles])

  // Derive project title
  const derivedTitle = useMemo(() => {
    if (projectName) return projectName
    // Try finding index.html or first entry
    const entry = effectiveContentFiles.find((f) => f.filename.toLowerCase().endsWith('index.html'))
    if (entry) {
      const parts = normalizePath(entry.filename).split('/')
      if (parts.length > 1) return `${parts[0]} Application`
    }
    const md = effectiveContentFiles.find((f) => f.filename.toLowerCase().endsWith('.md'))
    if (md) {
      const base = md.filename.replace(/\.md$/i, '').replace(/[-_]/g, ' ')
      return base.charAt(0).toUpperCase() + base.slice(1)
    }
    if (zipFile && zipFile.filename) {
      const base = zipFile.filename.replace(/\.zip$/i, '').replace(/[-_]/g, ' ')
      return base.charAt(0).toUpperCase() + base.slice(1)
    }
    return 'Repository Deliverable'
  }, [projectName, effectiveContentFiles, zipFile])

  // Determine primary preview file (index.html, or app.html, or first html, or zip)
  const primaryEntry = useMemo(() => {
    const htmlIndex = effectiveContentFiles.find((f) => /index\.html?$/i.test(f.filename))
    if (htmlIndex) return htmlIndex
    const anyHtml = effectiveContentFiles.find((f) => /\.html?$/i.test(f.filename))
    if (anyHtml) return anyHtml
    const readme = effectiveContentFiles.find((f) => /readme\.md$/i.test(f.filename))
    if (readme) return readme
    if (zipFile) return zipFile
    return effectiveContentFiles[0] || files[0]
  }, [effectiveContentFiles, files, zipFile])

  // Total size calculation
  const totalSizeBytes = useMemo(() => {
    return effectiveContentFiles.reduce((acc, f) => acc + (f.size_bytes || 0), 0)
  }, [effectiveContentFiles])

  // Build tree
  const treeNodes = useMemo(() => buildTree(effectiveContentFiles), [effectiveContentFiles])

  // Collect all folder paths for multi-folder expand
  const allFolderPaths = useMemo(() => {
    const paths = new Set<string>()
    const traverse = (nodes: TreeNode[]) => {
      for (const n of nodes) {
        if (n.isFolder) {
          paths.add(n.path)
          if (n.children) traverse(n.children)
        }
      }
    }
    traverse(treeNodes)
    return paths
  }, [treeNodes])

  // Open folders set (supports multi-folder opening)
  const [openFolders, setOpenFolders] = useState<Set<string>>(() => new Set(allFolderPaths))

  const toggleFolder = (folderPath: string) => {
    setOpenFolders((prev) => {
      const next = new Set(prev)
      if (next.has(folderPath)) {
        next.delete(folderPath)
      } else {
        next.add(folderPath)
      }
      return next
    })
  }

  const toggleAllFolders = () => {
    if (openFolders.size === allFolderPaths.size) {
      setOpenFolders(new Set())
    } else {
      setOpenFolders(new Set(allFolderPaths))
    }
  }

  // Handle Download ZIP
  const handleDownloadZip = async () => {
    if (zipFile && zipFile.download_url && !zipFile.download_url.startsWith('sandbox:')) {
      if (onDownloadSingle) {
        onDownloadSingle(zipFile.download_url, zipFile.filename || `${derivedTitle.toLowerCase().replace(/\s+/g, '_')}.zip`)
      } else {
        const a = document.createElement('a')
        a.href = zipFile.download_url
        a.download = zipFile.filename || 'project.zip'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      }
      return
    }

    // Client-side dynamic ZIP bundling with JSZip
    setZipping(true)
    try {
      const zip = new JSZip()
      const fetchPromises = contentFiles.map(async (file) => {
        const norm = normalizePath(file.filename)
        if (!file.download_url || file.download_url.startsWith('sandbox:')) return
        try {
          const res = await fetch(file.download_url)
          if (res.ok) {
            const blob = await res.blob()
            zip.file(norm, blob)
          }
        } catch (fetchErr) {
          console.warn(`Could not fetch ${norm} for client zip:`, fetchErr)
        }
      })

      await Promise.all(fetchPromises)
      const zipBlob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
      const blobUrl = URL.createObjectURL(zipBlob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `${derivedTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_')}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      console.error('Error generating project ZIP:', err)
    } finally {
      setZipping(false)
    }
  }

  // Filter tree based on search
  const filteredNodes = useMemo(() => {
    if (!searchQuery.trim()) return treeNodes
    const q = searchQuery.toLowerCase()

    function filterNodeList(list: TreeNode[]): TreeNode[] {
      const res: TreeNode[] = []
      for (const n of list) {
        if (n.isFolder && n.children) {
          const matchedKids = filterNodeList(n.children)
          if (matchedKids.length > 0 || n.name.toLowerCase().includes(q)) {
            res.push({ ...n, children: matchedKids })
          }
        } else if (!n.isFolder) {
          if (n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q)) {
            res.push(n)
          }
        }
      }
      return res
    }

    return filterNodeList(treeNodes)
  }, [treeNodes, searchQuery])

  // Count total folders
  const totalFoldersCount = allFolderPaths.size

  // Render a node recursively
  const renderTreeNode = (node: TreeNode, depth: number = 0) => {
    if (node.isFolder) {
      const isOpen = openFolders.has(node.path) || searchQuery.trim().length > 0
      return (
        <div key={node.path} className="flex flex-col select-none">
          <button
            type="button"
            onClick={() => toggleFolder(node.path)}
            style={{ paddingLeft: `${depth * 14 + 10}px` }}
            className="w-full flex items-center gap-2 py-1.5 pr-3 text-left rounded-md hover:bg-white/[0.04] transition group"
          >
            <span className="text-white/40 group-hover:text-white/70 transition">
              {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </span>
            <span className="text-amber-400/90 shrink-0">
              {isOpen ? <FolderOpen className="w-4 h-4" /> : <Folder className="w-4 h-4" />}
            </span>
            <span className="text-[12px] font-medium text-white/85 tracking-tight truncate flex-1">
              {node.name}
            </span>
            <span className="text-[10px] font-mono text-white/30 shrink-0">
              {node.children?.length || 0} items
            </span>
          </button>
          {isOpen && node.children && (
            <div className="flex flex-col">
              {node.children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      )
    }

    // File item
    const badge = getFileBadge(node.name)
    const hasUrl = node.file?.download_url && !node.file.download_url.startsWith('sandbox:')

    return (
      <div
        key={node.path}
        style={{ paddingLeft: `${depth * 14 + 10}px` }}
        className="w-full flex items-center justify-between gap-3 py-1.5 pr-2.5 rounded-md hover:bg-white/[0.03] transition group select-none border-l border-white/[0.04]"
      >
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <span className={`px-1.5 py-0.5 rounded text-[8.5px] font-bold border ${badge.bg} ${badge.text} shrink-0`}>
            {badge.label}
          </span>
          <span className="text-[11.5px] font-mono text-white/80 truncate group-hover:text-white transition">
            {node.name}
          </span>
          {node.sizeBytes && node.sizeBytes > 0 && (
            <span className="text-[10px] font-mono text-white/35 shrink-0 hidden sm:inline">
              {formatBytes(node.sizeBytes)}
            </span>
          )}
        </div>

        {/* Action buttons for single file */}
        <div className="flex items-center gap-1 shrink-0 opacity-80 group-hover:opacity-100 transition">
          {primaryEntry && (
            <button
              type="button"
              onClick={() => node.file && onPreview(node.file, contentFiles)}
              className="px-2 py-0.5 rounded text-[10px] font-medium text-white/60 hover:text-white hover:bg-white/10 border border-white/10 transition"
              title={`Preview ${node.name}`}
            >
              View
            </button>
          )}

          {hasUrl && (
            <button
              type="button"
              onClick={() => {
                if (node.file && onDownloadSingle) {
                  onDownloadSingle(node.file.download_url, node.file.filename)
                } else if (node.file) {
                  const a = document.createElement('a')
                  a.href = node.file.download_url
                  a.download = node.name
                  document.body.appendChild(a)
                  a.click()
                  document.body.removeChild(a)
                }
              }}
              className="w-6 h-6 rounded flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 border border-white/5 hover:border-white/20 transition"
              title={`Download ${node.name}`}
            >
              <Download className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="w-full my-3 rounded-xl bg-gradient-to-b from-[#1c1c22] to-[#141418] border border-white/[0.12] shadow-xl overflow-hidden animate-fadeIn">
      {/* ── Top Header & Hero Action Bar ──────────────────────── */}
      <div className="p-3.5 sm:p-4 border-b border-white/[0.08] bg-white/[0.02]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Project Identity */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 shadow-inner">
              <Globe className="w-5 h-5 text-indigo-300" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-[13.5px] sm:text-[14px] font-semibold text-white tracking-tight truncate">
                  {derivedTitle}
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[9.5px] font-semibold tracking-wide bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0">
                  Ready
                </span>
              </div>
              <p className="text-[11px] text-white/50 flex items-center gap-2 mt-0.5">
                <span>{effectiveContentFiles.length} files</span>
                {totalSizeBytes > 0 && (
                  <>
                    <span>•</span>
                    <span>{formatBytes(totalSizeBytes)}</span>
                  </>
                )}
                {totalFoldersCount > 0 && (
                  <>
                    <span>•</span>
                    <span>{totalFoldersCount} {totalFoldersCount === 1 ? 'folder' : 'folders'}</span>
                  </>
                )}
              </p>
            </div>
          </div>

          {/* Primary Action Buttons (Claude-style prominent CTA) */}
          <div className="flex items-center gap-2 w-full sm:w-auto shrink-0 mt-1 sm:mt-0">
            {primaryEntry && (
              <button
                type="button"
                onClick={() => {
                  if (zipFile) {
                    onPreview(zipFile, effectiveContentFiles)
                  } else {
                    onPreview(primaryEntry, effectiveContentFiles)
                  }
                }}
                className="flex-1 sm:flex-initial min-h-[38px] px-3.5 py-1.5 rounded-lg text-[12px] font-semibold bg-white text-black hover:bg-white/90 active:scale-[0.98] flex items-center justify-center gap-1.5 shadow-md hover:shadow-lg transition duration-150 cursor-pointer"
                title="Open live website preview"
              >
                <Eye className="w-3.5 h-3.5 text-black shrink-0" />
                <span>View App</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleDownloadZip}
              disabled={zipping}
              className="flex-1 sm:flex-initial min-h-[38px] px-3.5 py-1.5 rounded-lg text-[12px] font-semibold bg-white/[0.08] hover:bg-white/[0.14] border border-white/20 hover:border-white/35 text-white active:scale-[0.98] flex items-center justify-center gap-1.5 transition duration-150 disabled:opacity-50"
              title="Download full project repository as ZIP"
            >
              {zipping ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-white/80 shrink-0" />
              ) : (
                <Download className="w-3.5 h-3.5 text-white/80 shrink-0" />
              )}
              <span>{zipping ? 'Zipping...' : 'Download ZIP'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* ── Collapsible Repository File Explorer ────────────────── */}
      <div className="bg-[#121216]/70">
        <div className="px-3.5 py-2 flex items-center justify-between gap-2 border-b border-white/[0.05] text-[11px] text-white/50">
          <button
            type="button"
            onClick={() => setTreeExpanded((prev) => !prev)}
            className="flex items-center gap-1.5 hover:text-white transition"
          >
            {treeExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            <span className="font-medium text-white/70">Repository Files ({contentFiles.length})</span>
          </button>

          {treeExpanded && (
            <div className="flex items-center gap-3">
              {totalFoldersCount > 1 && (
                <button
                  type="button"
                  onClick={toggleAllFolders}
                  className="text-[10px] text-white/40 hover:text-white/80 transition underline"
                >
                  {openFolders.size === allFolderPaths.size ? 'Collapse Folders' : 'Expand All'}
                </button>
              )}
            </div>
          )}
        </div>

        {treeExpanded && (
          <div className="p-2 space-y-1">
            {contentFiles.length > 5 && (
              <div className="px-2 pb-1.5">
                <div className="relative">
                  <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Filter repository files..."
                    className="w-full pl-7 pr-2.5 py-1 text-[11px] rounded bg-white/[0.04] border border-white/[0.08] text-white placeholder-white/30 focus:outline-none focus:border-white/25 transition"
                  />
                </div>
              </div>
            )}

            <div className="max-h-[300px] overflow-y-auto space-y-0.5 pr-1 scrollbar-thin">
              {filteredNodes.map((node) => renderTreeNode(node, 0))}
              {filteredNodes.length === 0 && (
                <div className="py-4 text-center text-[11px] text-white/30">
                  No files match &quot;{searchQuery}&quot;
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

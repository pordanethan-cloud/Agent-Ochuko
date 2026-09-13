import React, { useState, useEffect, useRef } from 'react'
import {
  X,
  Check,
  ChevronDown,
  Folder,
  FolderPlus,
  Terminal,
  Copy,
  Cpu,
  RefreshCw,
  Shield,
  Trash2,
} from 'lucide-react'
import { supabase } from '../utils/supabaseClient'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

interface ConnectorSettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export const ConnectorSettingsModal: React.FC<ConnectorSettingsModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [reviewPolicy, setReviewPolicy] = useState<'always_ask' | 'always_proceed'>(() => {
    return (localStorage.getItem('ochuko_review_policy') as any) || 'always_ask'
  })
  const [isReviewDropdownOpen, setIsReviewDropdownOpen] = useState<boolean>(false)
  const [activeTab, setActiveTab] = useState<'workstation' | 'policies'>('workstation')
  const [bridgeOnline, setBridgeOnline] = useState<boolean | null>(null)
  const [checkingBridge, setCheckingBridge] = useState<boolean>(false)
  const [mountedFolderName, setMountedFolderName] = useState<string | null>(
    localStorage.getItem('ochuko_mounted_folder_name')
  )
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null)
  const [isWorkstationAccessEnabled, setIsWorkstationAccessEnabled] = useState<boolean>(() => {
    return localStorage.getItem('ochuko_workstation_access_enabled') === 'true'
  })
  const [autoReflexion, setAutoReflexion] = useState<boolean>(() => {
    return localStorage.getItem('ochuko_auto_reflexion') !== 'false'
  })

  const dropdownRef = useRef<HTMLDivElement>(null)

  const checkBridge = async () => {
    setCheckingBridge(true)
    try {
      const res = await fetch('http://127.0.0.1:3920/health', {
        method: 'GET',
        signal: AbortSignal.timeout(1500),
      })
      if (res.ok) {
        setBridgeOnline(true)
        return
      }
    } catch {
      // Bridge offline or not reachable
    } finally {
      setCheckingBridge(false)
    }
    setBridgeOnline(false)
  }

  useEffect(() => {
    if (!isOpen) return
    setIsWorkstationAccessEnabled(localStorage.getItem('ochuko_workstation_access_enabled') === 'true')
    setMountedFolderName(localStorage.getItem('ochuko_mounted_folder_name'))
    checkBridge()
  }, [isOpen])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsReviewDropdownOpen(false)
      }
    }
    if (isReviewDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isReviewDropdownOpen])

  if (!isOpen) return null

  const handleToggleWorkstationAccess = () => {
    const nextVal = !isWorkstationAccessEnabled
    setIsWorkstationAccessEnabled(nextVal)
    localStorage.setItem('ochuko_workstation_access_enabled', nextVal ? 'true' : 'false')
    window.dispatchEvent(new Event('ochuko_workstation_access_changed'))
  }

  const handleToggleAutoReflexion = () => {
    const nextVal = !autoReflexion
    setAutoReflexion(nextVal)
    localStorage.setItem('ochuko_auto_reflexion', nextVal ? 'true' : 'false')
  }

  const handleMountFolder = async () => {
    try {
      if (!('showDirectoryPicker' in window)) {
        alert(
          'File System Access API is not supported in this browser. Please use Chrome, Edge, or Brave.'
        )
        return
      }
      const dirHandle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
      if (dirHandle) {
        ;(window as any)._ochuko_dir_handle = dirHandle
        const folderName = dirHandle.name
        setMountedFolderName(folderName)
        localStorage.setItem('ochuko_mounted_folder_name', folderName)
        window.dispatchEvent(
          new CustomEvent('ochuko_folder_mounted', { detail: { folderName, dirHandle } })
        )
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Failed to mount folder:', err)
      }
    }
  }

  const handleUnmountFolder = () => {
    delete (window as any)._ochuko_dir_handle
    setMountedFolderName(null)
    localStorage.removeItem('ochuko_mounted_folder_name')
    window.dispatchEvent(new Event('ochuko_folder_unmounted'))
  }

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text)
    setCopiedCmd(key)
    setTimeout(() => setCopiedCmd(null), 2000)
  }

  const handleUpdateReviewPolicy = async (policy: 'always_ask' | 'always_proceed') => {
    setReviewPolicy(policy)
    setIsReviewDropdownOpen(false)
    localStorage.setItem('ochuko_review_policy', policy)

    try {
      const session = (await supabase.auth.getSession()).data.session
      const token = session?.access_token
      if (!token) return

      await fetch(`${API_BASE}/v1/connectors/workstation_access/permissions`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          review_policy: policy,
        }),
      })
    } catch (e) {
      console.error('Failed to update review policy:', e)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-xl bg-[#0d0f14] border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-[15px] font-semibold text-white">Workstation Computer Access (Cowork)</h3>
              <p className="text-[12px] text-[#8e95a2]">
                Configure local folder mounting and host companion bridge for unconstrained cowork autonomy
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onClose()
            }}
            className="p-2 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-lg text-[#8e95a2] hover:text-white hover:bg-white/5 transition cursor-pointer touch-manipulation"
            aria-label="Close modal"
          >
            <X className="w-5 h-5 pointer-events-none" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center px-4 sm:px-5 border-b border-white/[0.06] bg-[#090b0e]/50">
          <button
            onClick={() => setActiveTab('workstation')}
            className={`py-3 px-3 text-[12.5px] font-medium border-b-2 transition ${
              activeTab === 'workstation'
                ? 'border-cyan-400 text-white'
                : 'border-transparent text-[#8e95a2] hover:text-brand-text'
            }`}
          >
            Workstation Setup & Bridge
          </button>
          <button
            onClick={() => setActiveTab('policies')}
            className={`py-3 px-3 text-[12.5px] font-medium border-b-2 transition ${
              activeTab === 'policies'
                ? 'border-cyan-400 text-white'
                : 'border-transparent text-[#8e95a2] hover:text-brand-text'
            }`}
          >
            Safety & Review Policies
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {activeTab === 'workstation' ? (
            <>
              {/* Master Access Switch Card */}
              <div className="p-4 rounded-xl bg-gradient-to-r from-cyan-950/20 via-[#131622] to-blue-950/20 border border-cyan-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-white">Workstation Access (Agent Mode)</span>
                    {isWorkstationAccessEnabled ? (
                      <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[10px] font-mono text-cyan-400">
                        Enabled
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full bg-white/[0.06] border border-white/[0.1] text-[10px] font-mono text-[#8e95a2]">
                        Disabled
                      </span>
                    )}
                  </div>
                  <p className="text-[11.5px] text-[#8e95a2] leading-relaxed">
                    Allow Agent Ochuko to read local code, write generated files directly to disk, and execute approved commands.
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <button
                    type="button"
                    onClick={handleToggleWorkstationAccess}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      isWorkstationAccessEnabled ? 'bg-cyan-500 shadow-sm shadow-cyan-500/30' : 'bg-white/[0.12]'
                    }`}
                    aria-label="Toggle Workstation Access"
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                        isWorkstationAccessEnabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Dual-Tier Workstation Cowork Cards */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono font-medium tracking-wider text-[#8e95a2] uppercase">
                    Connection Tiers
                  </span>
                  <span className="text-[11px] text-cyan-400/80 font-mono">Dual-Tier Cowork</span>
                </div>

                {/* Tier 1: Browser Native Folder Mount */}
                <div className="p-4 rounded-xl bg-[#13151d]/70 border border-white/[0.06] space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shrink-0">
                        <Folder className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="text-[13px] font-medium text-white">Tier 1: Browser Folder Mount (Zero Install)</h4>
                          <span className="px-1.5 py-0.2 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[9.5px] font-mono text-cyan-400">
                            Zero Install
                          </span>
                        </div>
                        <p className="text-[11.5px] text-[#8e95a2] leading-relaxed mt-0.5">
                          Mount your project directory, Downloads, or Desktop via the HTML5 File System Access API. Zero background daemons required.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Mounted Folder State */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg bg-black/40 border border-white/[0.06]">
                    <div className="flex items-center gap-2 min-w-0">
                      <Folder className="w-4 h-4 text-cyan-400 shrink-0" />
                      <span className="text-[12px] text-white truncate">
                        {mountedFolderName ? (
                          <>
                            <span className="text-[#8e95a2]">Mounted: </span>
                            <span className="font-mono text-cyan-300 font-medium">{mountedFolderName}</span>
                          </>
                        ) : (
                          <span className="text-[#8e95a2]">No local folder mounted yet</span>
                        )}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {mountedFolderName && (
                        <button
                          type="button"
                          onClick={handleUnmountFolder}
                          className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[11.5px] font-medium transition cursor-pointer flex items-center gap-1"
                          title="Unmount current folder"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>Unmount</span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={handleMountFolder}
                        className="px-3.5 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[11.5px] font-medium transition active:scale-95 flex items-center gap-1.5 cursor-pointer"
                      >
                        <FolderPlus className="w-3.5 h-3.5" />
                        <span>{mountedFolderName ? 'Change Folder' : 'Mount Local Folder'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Tier 2: Workstation Companion Bridge */}
                <div className="p-4 rounded-xl bg-[#13151d]/70 border border-white/[0.06] space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 shrink-0">
                        <Terminal className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="text-[13px] font-medium text-white">Tier 2: Workstation Companion Bridge</h4>
                          {bridgeOnline === true ? (
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-mono text-emerald-400">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                              Active (Port 3920)
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-[10px] font-mono text-amber-400">
                              Bridge Offline
                            </span>
                          )}
                        </div>
                        <p className="text-[11.5px] text-[#8e95a2] leading-relaxed mt-0.5">
                          Enables direct disk file access anywhere on your machine and terminal command execution via a local HTTP bridge daemon on port 3920.
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={checkBridge}
                      disabled={checkingBridge}
                      className="p-1.5 rounded-lg text-[#8e95a2] hover:text-white hover:bg-white/5 transition shrink-0 cursor-pointer"
                      title="Re-check bridge status"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${checkingBridge ? 'animate-spin' : ''}`} />
                    </button>
                  </div>

                  {/* Launch Commands */}
                  <div className="space-y-2 pt-1">
                    <div className="space-y-1">
                      <span className="text-[10.5px] text-[#8e95a2] font-mono">
                        Windows (Silent Background Daemon - No Terminal Window):
                      </span>
                      <div className="flex items-center gap-2 bg-[#090a0d] border border-white/10 rounded-lg px-2.5 py-1.5 font-mono text-[11px] text-cyan-300 overflow-x-auto">
                        <span className="flex-1 truncate select-all">run_workstation_bridge.bat background</span>
                        <button
                          type="button"
                          onClick={() => handleCopy('run_workstation_bridge.bat background', 'win')}
                          className="p-1 rounded text-[#8e95a2] hover:text-white hover:bg-white/[0.06] transition shrink-0 cursor-pointer"
                          title="Copy command"
                        >
                          {copiedCmd === 'win' ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="space-y-1">
                      <span className="text-[10.5px] text-[#8e95a2] font-mono">
                        Cross-Platform / Direct Python:
                      </span>
                      <div className="flex items-center gap-2 bg-[#090a0d] border border-white/10 rounded-lg px-2.5 py-1.5 font-mono text-[11px] text-cyan-300 overflow-x-auto">
                        <span className="flex-1 truncate select-all">python -m app.connectors.workstation_bridge</span>
                        <button
                          type="button"
                          onClick={() => handleCopy('python -m app.connectors.workstation_bridge', 'py')}
                          className="p-1 rounded text-[#8e95a2] hover:text-white hover:bg-white/[0.06] transition shrink-0 cursor-pointer"
                          title="Copy command"
                        >
                          {copiedCmd === 'py' ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            /* Tab 2: Safety & Execution Policies */
            <div className="space-y-5">
              <div className="p-4 rounded-xl bg-[#13151d]/70 border border-white/[0.06] space-y-3">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 shrink-0">
                    <Shield className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-[13px] font-medium text-white">Review & Human-In-The-Loop Policy</h4>
                    <p className="text-[11.5px] text-[#8e95a2] leading-relaxed mt-0.5">
                      Specifies Agent's behavior when asking for approval on artifacts and filesystem operations.
                    </p>
                  </div>
                </div>

                <div className="relative pt-2" ref={dropdownRef}>
                  <button
                    type="button"
                    onClick={() => setIsReviewDropdownOpen(!isReviewDropdownOpen)}
                    className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-[#1a1d28] border border-white/[0.08] hover:border-white/[0.16] text-[12px] text-white transition cursor-pointer"
                  >
                    <span>
                      {reviewPolicy === 'always_ask'
                        ? 'Always Ask (Recommended - Asks before high-risk changes)'
                        : 'Always Proceed (Autonomous execution without confirmation)'}
                    </span>
                    <ChevronDown className="w-4 h-4 text-[#8e95a2]" />
                  </button>

                  {isReviewDropdownOpen && (
                    <div className="absolute top-full left-0 right-0 mt-1.5 py-1 bg-[#1a1d28] border border-white/10 rounded-xl shadow-2xl z-20 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => handleUpdateReviewPolicy('always_ask')}
                        className="w-full px-3.5 py-2.5 text-left text-[12px] hover:bg-white/5 flex items-center justify-between text-white transition cursor-pointer"
                      >
                        <div className="space-y-0.5">
                          <p className="font-medium text-white">Always Ask</p>
                          <p className="text-[11px] text-[#8e95a2]">
                            Agent always asks for user review on high-risk operations, terminal execution, and deliverable changes.
                          </p>
                        </div>
                        {reviewPolicy === 'always_ask' && <Check className="w-4 h-4 text-cyan-400 shrink-0" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleUpdateReviewPolicy('always_proceed')}
                        className="w-full px-3.5 py-2.5 text-left text-[12px] hover:bg-white/5 flex items-center justify-between text-white transition cursor-pointer border-t border-white/[0.04]"
                      >
                        <div className="space-y-0.5">
                          <p className="font-medium text-white">Always Proceed</p>
                          <p className="text-[11px] text-[#8e95a2]">
                            Agent proceeds autonomously without stopping for confirmation. Maximizes speed, with higher autonomy.
                          </p>
                        </div>
                        {reviewPolicy === 'always_proceed' && <Check className="w-4 h-4 text-cyan-400 shrink-0" />}
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Card 2: Auto-Reflexion */}
              <div className="p-4 rounded-xl bg-[#13151d]/70 border border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1 max-w-md">
                  <h4 className="text-[13px] font-medium text-white">Agent Auto-Reflexion</h4>
                  <p className="text-[11.5px] text-[#8e95a2] leading-relaxed">
                    When enabled, Agent automatically reflects and self-corrects failed code or tool steps without requiring explicit user prompting.
                  </p>
                </div>

                <div className="flex items-center justify-between sm:justify-end pt-2 sm:pt-0 border-t sm:border-t-0 border-white/[0.04]">
                  <button
                    type="button"
                    onClick={handleToggleAutoReflexion}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      autoReflexion ? 'bg-cyan-500 shadow-sm shadow-cyan-500/30' : 'bg-white/[0.12]'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ease-in-out ${
                        autoReflexion ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Host Isolation Notice */}
              <div className="p-4 rounded-xl bg-cyan-950/20 border border-cyan-500/10 space-y-2">
                <h5 className="text-[12px] font-semibold text-cyan-300">Workstation Safety Boundary</h5>
                <p className="text-[11px] text-[#8e95a2] leading-relaxed">
                  Browser native folder mounting is strictly restricted by browser origin sandbox policies. The local companion bridge runs exclusively on localhost:3920 and accepts requests with human-in-the-loop oversight.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 sm:p-5 border-t border-white/[0.06] bg-[#090b0e] flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] text-[#8e95a2]">
            <Shield className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Local host isolation & sandboxed tool execution</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-white/[0.08] hover:bg-white/[0.14] text-[12px] font-medium text-white transition cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

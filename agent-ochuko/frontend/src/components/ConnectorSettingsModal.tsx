import React, { useState, useEffect, useRef } from 'react'
import {
  X,
  Check,
  ChevronDown,
  Mail,
  Calendar,
  Image as ImageIcon,
  RefreshCw,
  Shield,
  Sliders,
} from 'lucide-react'
import { supabase } from '../utils/supabaseClient'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export interface ConnectorItem {
  name: string
  title: string
  description: string
  type: string
  category: string
  icon?: string
  is_connected: boolean
  permissions: string[]
  review_policy: 'always_ask' | 'always_proceed'
  last_used_at?: string
  connected_at?: string
}

interface ConnectorSettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

// Approved first-party integrations only
const ALLOWED_CONNECTOR_NAMES = new Set(['gmail', 'google_calendar', 'google_photos'])

export const ConnectorSettingsModal: React.FC<ConnectorSettingsModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [connectors, setConnectors] = useState<ConnectorItem[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [reviewPolicy, setReviewPolicy] = useState<'always_ask' | 'always_proceed'>('always_ask')
  const [isReviewDropdownOpen, setIsReviewDropdownOpen] = useState<boolean>(false)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'connectors' | 'policies'>('connectors')

  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch user connectors on open
  useEffect(() => {
    if (!isOpen) return

    const loadData = async () => {
      setLoading(true)
      try {
        const session = (await supabase.auth.getSession()).data.session
        const token = session?.access_token
        if (!token) return

        const res = await fetch(`${API_BASE}/v1/connectors`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
        if (res.ok) {
          const data = await res.json()
          const fetched: ConnectorItem[] = (data.connectors || []).filter((c: ConnectorItem) =>
            ALLOWED_CONNECTOR_NAMES.has(c.name)
          )
          setConnectors(fetched)
          const savedPolicy =
            (localStorage.getItem('ochuko_review_policy') as any) ||
            (fetched[0]?.review_policy || 'always_ask')
          setReviewPolicy(savedPolicy)
        }
      } catch (err) {
        console.error('Failed to load connectors:', err)
      } finally {
        setLoading(false)
      }
    }

    loadData()
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

  const handleToggleConnector = async (connector: ConnectorItem) => {
    setSavingKey(connector.name)
    const newActiveState = !connector.is_connected
    try {
      const session = (await supabase.auth.getSession()).data.session
      const token = session?.access_token
      if (!token) return

      if (newActiveState) {
        // Connect
        await fetch(`${API_BASE}/v1/connectors/${connector.name}/connect`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            connector_type: connector.type,
            permissions: connector.permissions || ['read', 'write'],
            review_policy: reviewPolicy,
          }),
        })
      } else {
        // Disconnect
        await fetch(`${API_BASE}/v1/connectors/${connector.name}`, {
          method: 'DELETE',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
      }

      setConnectors((prev) =>
        prev.map((c) =>
          c.name === connector.name ? { ...c, is_connected: newActiveState } : c
        )
      )
    } catch (e) {
      console.error('Failed to toggle connector:', e)
    } finally {
      setSavingKey(null)
    }
  }

  const handleUpdateReviewPolicy = async (policy: 'always_ask' | 'always_proceed') => {
    setReviewPolicy(policy)
    setIsReviewDropdownOpen(false)
    localStorage.setItem('ochuko_review_policy', policy)

    try {
      const session = (await supabase.auth.getSession()).data.session
      const token = session?.access_token
      if (!token) return

      // Update policy across connectors
      for (const c of connectors) {
        if (c.is_connected) {
          await fetch(`${API_BASE}/v1/connectors/${c.name}/permissions`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              review_policy: policy,
            }),
          })
        }
      }
    } catch (e) {
      console.error('Failed to update review policy:', e)
    }
  }

  const handleConnectGoogle = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      })
      if (error) throw error
    } catch (err: any) {
      console.error('Google OAuth connection error:', err)
    }
  }

  const renderIcon = (name: string) => {
    switch (name) {
      case 'gmail':
        return <Mail className="w-4 h-4 text-rose-400" />
      case 'google_calendar':
        return <Calendar className="w-4 h-4 text-blue-400" />
      case 'google_photos':
        return <ImageIcon className="w-4 h-4 text-amber-400" />
      default:
        return <Shield className="w-4 h-4 text-white/70" />
    }
  }

  const isGoogleConnected = connectors.some(
    (c) =>
      (c.name === 'gmail' || c.name === 'google_calendar' || c.name === 'google_photos') &&
      c.is_connected
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-xl bg-[#0d0f14] border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-[15px] font-semibold text-white">Agent Settings</h3>
              <p className="text-[12px] text-[#8e95a2]">
                Configure autonomous execution policies and Google Workspace integrations
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-[#8e95a2] hover:text-white hover:bg-white/5 transition"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center px-4 sm:px-5 border-b border-white/[0.06] bg-[#090b0e]/50">
          <button
            onClick={() => setActiveTab('connectors')}
            className={`py-3 px-3 text-[12.5px] font-medium border-b-2 transition ${
              activeTab === 'connectors'
                ? 'border-white text-white'
                : 'border-transparent text-[#8e95a2] hover:text-brand-text'
            }`}
          >
            Connected Apps & Tools
          </button>
          <button
            onClick={() => setActiveTab('policies')}
            className={`py-3 px-3 text-[12.5px] font-medium border-b-2 transition ${
              activeTab === 'policies'
                ? 'border-white text-white'
                : 'border-transparent text-[#8e95a2] hover:text-brand-text'
            }`}
          >
            Safety & Review Policies
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-6">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center space-y-3">
              <RefreshCw className="w-6 h-6 text-white/40 animate-spin" />
              <p className="text-[12px] text-[#8e95a2]">Loading configurations...</p>
            </div>
          ) : activeTab === 'connectors' ? (
            <>
              {/* Google Workspace & Photos Direct Connect Card */}
              <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/20 via-[#131622] to-indigo-950/20 border border-blue-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-white">Google Workspace & Photos</span>
                    {isGoogleConnected ? (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-mono text-emerald-400">
                        OAuth Connected
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-[10px] font-mono text-blue-400">
                        Single Sign-On Available
                      </span>
                    )}
                  </div>
                  <p className="text-[11.5px] text-[#8e95a2] leading-relaxed">
                    Link Gmail, Google Calendar, and Google Photos to empower Agent Ochuko to search correspondence, schedule meetings, and retrieve photo assets.
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={handleConnectGoogle}
                    className="inline-flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl bg-white hover:bg-white/90 text-black font-semibold text-[12px] transition shadow-sm cursor-pointer"
                  >
                    <svg className="w-4 h-4" viewBox="0 0 24 24">
                      <path
                        fill="#4285F4"
                        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                      />
                      <path
                        fill="#34A853"
                        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                      />
                      <path
                        fill="#FBBC05"
                        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                      />
                      <path
                        fill="#EA4335"
                        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                      />
                    </svg>
                    <span>{isGoogleConnected ? 'Re-auth Google' : 'Connect via Google'}</span>
                  </button>
                </div>
              </div>

              {/* Connected Tools Section */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono font-medium tracking-wider text-[#8e95a2] uppercase">
                    Available Connectors
                  </span>
                  <span className="text-[11px] text-white/40 font-mono">
                    {connectors.filter((c) => c.is_connected).length} active
                  </span>
                </div>

                <div className="space-y-2.5">
                  {connectors.map((c) => {
                    const isBusy = savingKey === c.name
                    return (
                      <div
                        key={c.name}
                        className="p-3.5 sm:p-4 rounded-xl bg-[#13151d]/70 border border-white/[0.06] hover:border-white/[0.12] transition flex flex-col gap-3"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                          <div className="flex items-start gap-3 min-w-0">
                            <div className="p-2 rounded-lg bg-[#1a1d28] border border-white/[0.05] shrink-0 mt-0.5 sm:mt-0">
                              {renderIcon(c.name)}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <h4 className="text-[13px] font-medium text-white truncate">
                                  {c.title}
                                </h4>
                                {c.is_connected && (
                                  <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[9.5px] font-mono text-emerald-400">
                                    Active
                                  </span>
                                )}
                              </div>
                              <p className="text-[11.5px] text-[#8e95a2] leading-relaxed mt-0.5">
                                {c.description}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center justify-between sm:justify-end gap-3 pt-2 sm:pt-0 border-t sm:border-t-0 border-white/[0.04]">
                            <div className="text-[10.5px] font-mono text-[#8e95a2]/70 sm:hidden">
                              {c.is_connected ? 'Enabled' : 'Disabled'}
                            </div>

                            {/* Sleek Toggle */}
                            <button
                              type="button"
                              disabled={isBusy}
                              onClick={() => handleToggleConnector(c)}
                              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                                c.is_connected ? 'bg-blue-600' : 'bg-white/[0.12]'
                              } ${isBusy ? 'opacity-50 cursor-wait' : ''}`}
                              aria-label={`Toggle ${c.title}`}
                            >
                              <span
                                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                                  c.is_connected ? 'translate-x-5' : 'translate-x-0'
                                }`}
                              />
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
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
                    <h4 className="text-[13px] font-medium text-white">Review & Approval Policy</h4>
                    <p className="text-[11.5px] text-[#8e95a2] leading-relaxed mt-0.5">
                      Determine whether Ochuko must explicitly ask for your approval before writing external changes (e.g. sending emails or creating calendar events).
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
                        ? 'Always ask before writing external changes'
                        : 'Proceed autonomously without asking'}
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
                          <p className="font-medium">Always ask before writing external changes</p>
                          <p className="text-[11px] text-[#8e95a2]">
                            Requires confirmation before sending emails or updating schedules.
                          </p>
                        </div>
                        {reviewPolicy === 'always_ask' && <Check className="w-4 h-4 text-blue-400 shrink-0" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleUpdateReviewPolicy('always_proceed')}
                        className="w-full px-3.5 py-2.5 text-left text-[12px] hover:bg-white/5 flex items-center justify-between text-white transition cursor-pointer border-t border-white/[0.04]"
                      >
                        <div className="space-y-0.5">
                          <p className="font-medium">Proceed autonomously without asking</p>
                          <p className="text-[11px] text-[#8e95a2]">
                            High speed autonomous execution without confirmation cards.
                          </p>
                        </div>
                        {reviewPolicy === 'always_proceed' && <Check className="w-4 h-4 text-blue-400 shrink-0" />}
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-500/10 space-y-2">
                <h5 className="text-[12px] font-semibold text-blue-300">Security Architecture</h5>
                <p className="text-[11px] text-[#8e95a2] leading-relaxed">
                  Agent Ochuko uses short-lived tokens and Azure Key Vault encryption for external connections. Tool permissions are strictly scoped to the active session.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 sm:p-5 border-t border-white/[0.06] bg-[#090b0e] flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] text-[#8e95a2]">
            <Shield className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Azure-encrypted credentials & RLS protected</span>
          </div>
          <button
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

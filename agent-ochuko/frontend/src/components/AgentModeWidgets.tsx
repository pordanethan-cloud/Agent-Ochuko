import React, { useState, useEffect, useRef } from 'react'
import {
  Bot,
  Check,
  AlertTriangle,
  Pencil,
  Loader2,
  X,
  Play,
  Zap,
  ChevronDown,
  ChevronUp,
  FileText,
} from 'lucide-react'

export interface PlanStepItem {
  index: number
  description: string
  tool_name?: string | null
  risk_level?: 'low' | 'medium' | 'high'
  requires_approval?: boolean
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  result_summary?: string | null
  artifacts?: Array<{ filename: string; download_url?: string; size_bytes?: number }>
  duration_ms?: number
  token_spend?: number
  error?: string
}

export interface AgentTaskData {
  id?: string
  task_id?: string
  goal?: string
  state?: 'planning' | 'awaiting_approval' | 'executing' | 'paused_for_hitl' | 'completed' | 'failed' | 'cancelled'
  plan?: PlanStepItem[]
  current_step?: number
  artifacts?: Array<{ filename: string; download_url?: string; size_bytes?: number }>
  total_token_spend?: number
  elapsed_seconds?: number
  max_seconds?: number
  error_message?: string
}

/* ───────────────────────────────────────────────────────────────────────────
   1. PLAN REVIEW CARD (Before execution)
   ─────────────────────────────────────────────────────────────────────────── */
interface AgentPlanReviewProps {
  plan: PlanStepItem[]
  taskId?: string
  isExecuting?: boolean
  onApprove: () => void
  onEditStep?: (stepIndex: number, newDesc: string) => void
  onCancel?: () => void
}

export const AgentPlanReviewCard: React.FC<AgentPlanReviewProps> = ({
  plan,
  taskId: _taskId,
  isExecuting = false,
  onApprove,
  onEditStep,
  onCancel,
}) => {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editText, setEditText] = useState('')

  const handleStartEdit = (step: PlanStepItem) => {
    setEditingIndex(step.index)
    setEditText(step.description)
  }

  const handleSaveEdit = (stepIndex: number) => {
    if (onEditStep && editText.trim()) {
      onEditStep(stepIndex, editText.trim())
    }
    setEditingIndex(null)
  }

  return (
    <div className="w-full my-3 rounded-2xl bg-brand-card border border-brand-border p-4 sm:p-5 shadow-xl relative overflow-hidden animate-fadeIn select-none">
      {/* Background ambient glow */}
      <div className="absolute top-0 right-0 w-48 h-48 bg-white/[0.02] rounded-full blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.08] mb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-brand-accent/15 border border-brand-accent/30 flex items-center justify-center text-brand-accent">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-[13px] font-semibold text-white/95 tracking-tight flex items-center gap-2">
              Autonomous Execution Plan
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand-accent/15 text-brand-accent border border-brand-accent/30 font-medium">
                {plan.length} Steps
              </span>
            </h4>
            <p className="text-[11px] text-white/50">Review task roadmap. Step-by-step verification active.</p>
          </div>
        </div>
      </div>

      {/* Plan Steps List */}
      <div className="space-y-2 mb-4">
        {plan.map((step) => {
          const isHighRisk = step.risk_level === 'high'
          const isMedRisk = step.risk_level === 'medium'

          return (
            <div
              key={step.index}
              className="flex items-start gap-3 p-2.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.05] transition group"
            >
              <div className="w-5 h-5 rounded-full bg-white/[0.08] text-white/80 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                {step.index}
              </div>

              <div className="flex-1 min-w-0">
                {editingIndex === step.index ? (
                  <div className="flex items-center gap-2 mt-0.5">
                    <input
                      type="text"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSaveEdit(step.index)}
                      className="flex-1 bg-black/50 border border-white/20 rounded px-2 py-1 text-[12px] text-white focus:outline-none focus:border-brand-accent"
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveEdit(step.index)}
                      className="px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-[11px] text-white font-medium"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingIndex(null)}
                      className="p-1 text-white/40 hover:text-white"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[12.5px] text-white/90 leading-snug">{step.description}</p>
                    {!isExecuting && onEditStep && (
                      <button
                        onClick={() => handleStartEdit(step)}
                        className="opacity-0 group-hover:opacity-100 p-1 text-white/40 hover:text-white transition"
                        title="Edit step description"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                )}

                {/* Badges */}
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  {step.tool_name && (
                    <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-white/[0.06] text-white/60 border border-white/[0.06]">
                      {step.tool_name}
                    </span>
                  )}
                  {isHighRisk && (
                    <span className="text-[9.5px] font-medium px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 flex items-center gap-1">
                      <AlertTriangle className="w-2.5 h-2.5" /> Approval Required
                    </span>
                  )}
                  {isMedRisk && (
                    <span className="text-[9.5px] font-medium px-1.5 py-0.5 rounded bg-white/[0.07] text-white/70 border border-white/15">
                      Compute Step
                    </span>
                  )}
                  {!isHighRisk && !isMedRisk && (
                    <span className="text-[9.5px] font-medium px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                      Auto-execute
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Action Footer */}
      {!isExecuting && (
        <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-white/[0.08]">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-3.5 py-2 rounded-xl text-[11.5px] font-medium text-white/60 hover:text-white hover:bg-white/5 transition"
            >
              Cancel
            </button>
          )}
          <button
            type="button"
            onClick={onApprove}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-[12px] font-semibold bg-emerald-500 hover:bg-emerald-400 text-black shadow-lg shadow-emerald-500/20 transition active:scale-95 cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            Approve & Execute Plan
          </button>
        </div>
      )}
    </div>
  )
}

/* ───────────────────────────────────────────────────────────────────────────
   2. EXECUTION STEPPER & PROGRESS WIDGET (During execution)
   ─────────────────────────────────────────────────────────────────────────── */
interface AgentExecutionStepperProps {
  task: AgentTaskData
  onPause?: () => void
  onCancel?: () => void
}

/* ───────────────────────────────────────────────────────────────────────────
   2. EXECUTION STEPPER — Verdent-style activity log.
   "Working for Xm Ys" live header + OODA-labelled collapsible step rows.
   Labels are derived client-side from tool_name/description: zero tokens.
   ─────────────────────────────────────────────────────────────────────────── */
interface AgentExecutionStepperProps {
  task: AgentTaskData
  onPause?: () => void
  onCancel?: () => void
}

const formatElapsed = (ms: number): string => {
  const totalSec = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  if (m === 0) return `${s}s`
  return `${m}m ${s}s`
}

// Task-based OODA loop: classify each step into Observe/Orient/Decide/Act
// from its tool and description (deterministic, client-side, zero cost).
const oodaPhase = (step: PlanStepItem): string => {
  const hay = `${step.tool_name || ''} ${step.description || ''}`.toLowerCase()
  if (/\b(plan|decide|select|choose|strateg|design|determine|identify)\b/.test(hay)) return 'Decide'
  if (/\b(analy[sz]e|analy[sz]ing|compare|synthesi[sz]e|evaluat|review|summar|extract|compute|calculate)\b/.test(hay)) return 'Orient'
  if (/\b(search|research|fetch|read|browse|observe|list|check|monitor|gather|find|scan|look)\b/.test(hay)) return 'Observe'
  return 'Act'
}

// Two-colour discipline: neutrals carry the UI; emerald (success) and rose
// (failure) are the only semantic accents. OODA phase labels stay monochrome.
const OODA_LABEL_CLASS = 'text-white/55 font-medium'

export const AgentExecutionStepper: React.FC<AgentExecutionStepperProps> = ({
  task,
  onPause: _onPause,
  onCancel: _onCancel,
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set())
  const [, forceTick] = useState(0)
  const startRef = useRef<number | null>(null)
  const plan = task.plan || []
  const currentStep = task.current_step || 1
  const completedCount = plan.filter((s) => s.status === 'completed').length
  const progressPct = plan.length > 0 ? Math.round((completedCount / plan.length) * 100) : 0

  const isTaskDone = task.state === 'completed' || (plan.length > 0 && completedCount === plan.length)

  // Live client-side timer: counts while executing, freezes on completion.
  useEffect(() => {
    if (isTaskDone) return
    if (startRef.current === null) {
      startRef.current = Date.now() - (task.elapsed_seconds ? task.elapsed_seconds * 1000 : 0)
    }
    const t = window.setInterval(() => forceTick((n) => n + 1), 1000)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTaskDone])

  const elapsedMs = isTaskDone
    ? (task.elapsed_seconds ? task.elapsed_seconds * 1000 : 0)
    : startRef.current !== null
      ? Date.now() - startRef.current
      : 0

  const toggleExpand = (idx: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  return (
    <div className="w-full my-3 rounded-xl bg-brand-card border border-brand-border p-3.5 sm:p-4 shadow-lg relative overflow-hidden animate-fadeIn select-none">
      {/* Header — "Working for 2m 41s" */}
      <div className="flex items-center justify-between pb-2.5 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {isTaskDone ? (
            <div className="w-5 h-5 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
              <Check className="w-3 h-3 stroke-[3]" />
            </div>
          ) : (
            <Loader2 className="w-4 h-4 text-brand-muted animate-spin shrink-0" />
          )}
          <span className={`text-[13px] font-medium tracking-tight ${isTaskDone ? 'text-white/90' : 'text-white/75'}`}>
            {isTaskDone ? 'Completed' : 'Working'} {elapsedMs > 0 && (
              <span className="font-mono text-[11.5px] text-white/45">
                {isTaskDone ? 'in' : 'for'} {formatElapsed(elapsedMs)}
              </span>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          {task.total_token_spend && task.total_token_spend > 0 ? (
            <span className="text-[10px] font-mono text-white/35">
              ~{task.total_token_spend.toLocaleString()} tok
            </span>
          ) : null}
          <span className="text-[10.5px] font-mono text-white/40">{progressPct}%</span>
        </div>
      </div>

      {/* Steps — collapsible activity rows */}
      <div className="space-y-1">
        {plan.map((step) => {
          const isDone = step.status === 'completed'
          const isSkipped = step.status === 'skipped'
          const isFailed = step.status === 'failed'
          const isRunning = step.status === 'running' || (!isDone && !isFailed && !isSkipped && step.index === currentStep && task.state === 'executing')
          const isExpanded = expandedSteps.has(step.index)
          const phase = oodaPhase(step)

          return (
            <div
              key={step.index}
              className={`rounded-lg border transition ${
                isRunning
                  ? 'bg-white/[0.045] border-white/[0.09]'
                  : isDone
                  ? 'bg-transparent border-transparent hover:bg-white/[0.02]'
                  : isFailed
                  ? 'bg-rose-500/[0.05] border-rose-500/25'
                  : 'bg-transparent border-transparent'
              }`}
            >
              <div
                onClick={() => (step.result_summary ? toggleExpand(step.index) : undefined)}
                className={`px-2 py-[7px] flex items-center gap-2.5 rounded-lg ${
                  step.result_summary ? 'cursor-pointer hover:bg-white/[0.03]' : ''
                } ${isSkipped ? 'opacity-45' : ''}`}
              >
                {/* Status icon */}
                <div className="w-4 flex items-center justify-center shrink-0">
                  {isRunning ? (
                    <Loader2 className="w-3.5 h-3.5 text-white/70 animate-spin" />
                  ) : isDone ? (
                    <Check className="w-3.5 h-3.5 text-emerald-400/90 stroke-[3]" />
                  ) : isFailed ? (
                    <X className="w-3.5 h-3.5 text-rose-400/90 stroke-[3]" />
                  ) : (
                    <span className="text-[10px] font-mono text-white/30">{step.index}</span>
                  )}
                </div>

                {/* Activity line: OODA phase + description — wraps to 2 lines on
                    mobile so context is readable; single line + truncate on desktop */}
                <p className={`text-[12.5px] leading-snug line-clamp-2 sm:truncate flex-1 min-w-0 ${
                  isRunning ? 'text-white/90' : isDone ? 'text-white/65' : isFailed ? 'text-rose-300/90' : 'text-white/40'
                }`}>
                  <span className={`mr-1.5 ${OODA_LABEL_CLASS}`}>{phase}</span>
                  {isDone && step.result_summary ? step.result_summary.split('\n')[0] : step.description}
                </p>

                {/* Right: duration + chevron */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {step.duration_ms ? (
                    <span className="text-[9.5px] font-mono text-white/30">{formatElapsed(step.duration_ms)}</span>
                  ) : null}
                  {step.result_summary && (
                    <span className="text-white/35 hover:text-white/70">
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </span>
                  )}
                </div>
              </div>

              {/* Collapsible step detail */}
              {isExpanded && step.result_summary && (
                <div className="px-2 pb-2.5 pt-0.5">
                  <p className="text-[11.5px] text-white/60 leading-relaxed whitespace-pre-wrap border-l-2 border-white/10 pl-2.5 ml-[7px]">
                    {step.result_summary}
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ───────────────────────────────────────────────────────────────────────────
   3. IN-CHAT HITL APPROVAL CARD (When step pauses for human approval)
   ─────────────────────────────────────────────────────────────────────────── */
interface AgentHITLApprovalProps {
  step: PlanStepItem
  taskId: string
  reason?: string
  onApprove: () => void
  onSkip: () => void
  onCancel: () => void
}

export const AgentHITLApprovalCard: React.FC<AgentHITLApprovalProps> = ({
  step,
  taskId: _taskId,
  reason,
  onApprove,
  onSkip,
  onCancel,
}) => {
  return (
    <div className="w-full my-3.5 rounded-2xl bg-brand-card border border-white/15 p-4 sm:p-5 shadow-2xl relative overflow-hidden animate-fadeIn select-none">
      {/* Background ambient flare — neutral */}
      <div className="absolute top-0 right-0 w-36 h-36 bg-white/[0.03] rounded-full blur-2xl pointer-events-none" />

      <div className="flex items-start gap-3 mb-3">
        <div className="w-8 h-8 rounded-xl bg-white/[0.07] border border-white/15 flex items-center justify-center text-white/80 shrink-0 mt-0.5">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[13px] font-semibold text-white tracking-tight">
              Action Approval Required
            </h4>
            <span className="text-[9.5px] px-2 py-0.5 rounded-full bg-white/[0.07] text-white/70 border border-white/15 font-bold uppercase tracking-wider">
              Step {step.index}
            </span>
          </div>
          <p className="text-[12px] text-white/70 mt-1 font-medium leading-snug">
            {step.description}
          </p>
          {reason && (
            <p className="text-[11px] text-white/50 mt-1 leading-relaxed">
              {reason}
            </p>
          )}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/[0.08]">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-xl text-[11px] font-medium text-white/50 hover:text-white hover:bg-white/5 transition"
        >
          Cancel Task
        </button>
        <button
          type="button"
          onClick={onSkip}
          className="px-3 py-1.5 rounded-xl text-[11px] font-medium text-white/80 hover:text-white bg-white/10 hover:bg-white/15 transition"
        >
          Skip Step
        </button>
        <button
          type="button"
          onClick={onApprove}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-[11.5px] font-bold bg-emerald-500 hover:bg-emerald-400 text-black shadow-md shadow-emerald-500/20 transition active:scale-95 cursor-pointer"
        >
          <Check className="w-3.5 h-3.5 stroke-[3]" />
          Approve Action
        </button>
      </div>
    </div>
  )
}

/* ───────────────────────────────────────────────────────────────────────────
   4. INSTANT STATIC SITE DEPLOYMENT CARD (/sites/:slug) — compact, no inline
   iframe in the thread; preview opens in the ArtifactPanel right dock.
   ─────────────────────────────────────────────────────────────────────────── */
interface AgentSiteDeploymentProps {
  title: string
  previewUrl: string
  slug?: string
}

export const AgentSiteDeploymentCard: React.FC<AgentSiteDeploymentProps> = ({
  title,
  previewUrl,
  slug: _slug,
}) => {
  const openInPanel = () => {
    window.dispatchEvent(new CustomEvent('open-file-preview', {
      detail: {
        name: title || 'Deployed Site',
        type: 'text/html',
        url: previewUrl,
      },
    }))
  }

  return (
    <div className="w-full my-3.5 rounded-lg bg-brand-card border border-white/10 shadow-lg relative overflow-hidden animate-fadeIn select-none">
      <div className="p-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-md bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
            <Zap className="w-3.5 h-3.5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-white truncate">{title || 'Live Deployed Web App'}</span>
              <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0">
                LIVE
              </span>
            </div>
            <span className="text-[10.5px] text-white/45 truncate block font-mono">{previewUrl}</span>
          </div>
        </div>

        {/* Actions: panel preview + external visit */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={openInPanel}
            title="Open preview in the artifact panel"
            className="px-3 py-1.5 rounded-md text-[11px] font-semibold bg-white/5 hover:bg-white/10 text-white/85 border border-white/10 flex items-center gap-1.5 transition"
          >
            <Play className="w-3 h-3" />
            <span>Open preview</span>
          </button>
          <a
            href={previewUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-md text-[11px] font-bold bg-brand-accent hover:bg-brand-accent/90 text-black flex items-center gap-1 transition active:scale-95"
          >
            Visit site
          </a>
        </div>
      </div>
    </div>
  )
}

/* ───────────────────────────────────────────────────────────────────────────
   5. TURN TRACKER — thin rail on the RIGHT edge of the thread.
   One tick per assistant turn; active tick pulses while streaming;
   click jumps to that turn via [data-turn-anchor] elements.
   ─────────────────────────────────────────────────────────────────────────── */
interface TurnTrackerProps {
  /** Message indices of assistant turns, in order */
  turnIndices: number[]
  /** Message index currently streaming (or null when idle) */
  activeIndex: number | null
}

export const TurnTracker: React.FC<TurnTrackerProps> = ({ turnIndices, activeIndex }) => {
  if (turnIndices.length < 2) return null

  const jumpTo = (idx: number) => {
    const el = document.querySelector(`[data-turn-anchor="${idx}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div
      className="hidden md:flex flex-col items-center gap-[7px] absolute right-1 top-1/2 -translate-y-1/2 z-10 py-2 px-1"
      aria-label="Conversation turn tracker"
    >
      {turnIndices.map((idx) => {
        const isActive = idx === activeIndex
        return (
          <button
            key={idx}
            type="button"
            onClick={() => jumpTo(idx)}
            title={`Turn ${(turnIndices.indexOf(idx) || 0) + 1}`}
            className="group/trk flex items-center justify-center w-3 h-3 cursor-pointer"
          >
            <span
              className={`rounded-full transition-all duration-200 ${
                isActive
                  ? 'w-[5px] h-[16px] bg-white/80'
                  : 'w-[4px] h-[4px] bg-white/25 group-hover/trk:bg-white/60'
              } ${isActive ? 'animate-pulse' : ''}`}
            />
          </button>
        )
      })}
    </div>
  )
}

/* ───────────────────────────────────────────────────────────────────────────
   6. FILES-CHANGED CARD — one compact chip for everything the agent produced,
   Verdent-style ("4 files changed"). Rows open in the ArtifactPanel.
   ─────────────────────────────────────────────────────────────────────────── */
export interface AgentArtifactItem {
  filename: string
  download_url?: string
  size_bytes?: number
}

interface AgentFileChangesProps {
  artifacts: AgentArtifactItem[]
  onOpen: (file: AgentArtifactItem) => void
}

export const AgentFileChangesCard: React.FC<AgentFileChangesProps> = ({ artifacts, onOpen }) => {
  const [expanded, setExpanded] = useState(false)

  const files = artifacts.filter((a) => a.filename)
  if (files.length === 0) return null

  const formatSize = (bytes?: number): string => {
    if (!bytes || bytes <= 0) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="w-full my-3 rounded-lg bg-brand-card border border-white/10 shadow-sm animate-fadeIn select-none">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full px-3.5 py-2.5 flex items-center justify-between gap-3 hover:bg-white/[0.02] rounded-lg transition"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-6 h-6 rounded-md bg-white/[0.06] border border-white/10 flex items-center justify-center text-white/70 shrink-0">
            <FileText className="w-3 h-3" />
          </div>
          <span className="text-[12.5px] font-medium text-white/85">
            {files.length} {files.length === 1 ? 'file' : 'files'} changed
          </span>
        </div>
        <span className="text-white/40 hover:text-white/70 shrink-0">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </span>
      </button>

      {expanded && (
        <div className="px-3.5 pb-3 space-y-0.5">
          {files.map((f, i) => (
            <button
              key={`${f.filename}-${i}`}
              type="button"
              onClick={() => f.download_url && onOpen(f)}
              className={`w-full flex items-center justify-between gap-3 px-2 py-1.5 rounded-md text-left ${
                f.download_url ? 'hover:bg-white/[0.04] cursor-pointer' : 'cursor-default'
              } transition`}
            >
              <span className="text-[11.5px] font-mono text-white/70 truncate">{f.filename}</span>
              <span className="text-[10px] font-mono text-white/35 shrink-0">{formatSize(f.size_bytes)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}


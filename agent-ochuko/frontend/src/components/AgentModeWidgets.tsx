import React, { useState, useEffect, useRef, useMemo } from 'react'
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
  HelpCircle,
  Send,
  Folder,
  FolderOpen,
  ChevronRight,
  Route,
} from 'lucide-react'

/* ─────────────────────────────────────────────────────────────────────────────
   AGENT MODE WIDGETS — design language.

   One system, shared by every agent widget:
   · Shell    — flat `brand-card` + hairline `brand-border`; radius-xl cards,
                radius-lg rows, radius-full chips. No glows, no drop shadows:
                tone layering only.
   · Text     — white at graded opacity: /95 titles, /80 body, /50 secondary,
                /35 meta. `brand-muted` for labels.
   · Accent   — ivory (`brand-accent`) is the ONLY action colour: primary
                buttons, progress, active states.
   · Semantic — `brand-ok` (muted sage) success/live; `brand-err` (muted
                terracotta) failure/high-risk. Nothing else is coloured.
   · Mono     — indices, tools, tokens, timings, paths.
   ───────────────────────────────────────────────────────────────────────────── */

// Shared card shell — every widget is built from this one surface.
const CARD = 'w-full my-3 rounded-xl bg-brand-card border border-brand-border animate-fadeIn select-none'

// Shared neutral chip.
const CHIP = 'text-[10px] font-medium px-2 py-0.5 rounded-full border'

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
  adapted_reasoning?: string
  previous_tool?: string
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
  reoriented?: boolean   // Phase 8: plan was dynamically re-oriented mid-execution
  replan_count?: number
  replan_trigger?: 'failure' | 'discovery'  // Phase 8.1: why the plan shifted
  replan_reason?: string  // Phase 8.1: contradiction summary (undefined on pre-8.1 events)
}

/* ─────────────────────────────────────────────────────────────────────────────
   1. PLAN REVIEW CARD (before execution)
   ───────────────────────────────────────────────────────────────────────────── */
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
    <div className={`${CARD} p-3.5 sm:p-5`}>
      {/* Header */}
      <div className="flex items-center gap-2.5 pb-3 border-b border-brand-border mb-3.5">
        <div className="w-7 h-7 rounded-lg bg-white/[0.05] border border-brand-border flex items-center justify-center text-brand-muted shrink-0">
          <Bot className="w-4 h-4" />
        </div>
        <div className="min-w-0">
          <h4 className="text-[13px] font-semibold text-white/95 tracking-tight leading-tight">
            Execution Plan
          </h4>
          <p className="text-[11px] text-white/45 leading-tight">
            {plan.length} steps — approve to begin
          </p>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-1.5 mb-4">
        {plan.map((step) => {
          const needsApproval = step.risk_level === 'high' || step.requires_approval

          return (
            <div
              key={step.index}
              className="flex items-start gap-3 p-2.5 rounded-lg bg-white/[0.02] hover:bg-white/[0.035] hover:border-brand-border border border-transparent transition group"
            >
              <div className="w-5 h-5 rounded-full border border-brand-border text-white/70 flex items-center justify-center text-[10px] font-mono shrink-0 mt-0.5">
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
                      className="flex-1 bg-white/[0.04] border border-brand-border rounded-lg px-2 py-1 text-[12px] text-white focus:outline-none focus:border-brand-accent/60 transition"
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveEdit(step.index)}
                      className="px-2 py-1 bg-white/[0.07] hover:bg-white/[0.12] rounded-lg text-[11px] text-white/85 font-medium transition"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingIndex(null)}
                      className="p-1 text-white/40 hover:text-white/80 transition"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[12.5px] text-white/85 leading-snug">{step.description}</p>
                    {!isExecuting && onEditStep && (
                      <button
                        onClick={() => handleStartEdit(step)}
                        className="opacity-60 sm:opacity-0 group-hover:opacity-100 p-1 text-white/40 hover:text-white/80 transition shrink-0"
                        title="Edit step description"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                )}

                {/* Meta — tool chip is neutral; the only coloured chip is
                    high-risk (approval needed) */}
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  {step.tool_name && (
                    <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-white/[0.05] text-white/55 border border-brand-border">
                      {step.tool_name}
                    </span>
                  )}
                  {needsApproval && (
                    <span className="text-[9.5px] font-medium px-1.5 py-0.5 rounded bg-brand-err/10 text-brand-err border border-brand-err/25 flex items-center gap-1">
                      <AlertTriangle className="w-2.5 h-2.5" /> Approval required
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer actions */}
      <div className="flex items-center justify-end gap-2 pt-3 border-t border-brand-border">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={isExecuting}
            className="px-3 py-1.5 rounded-lg text-[11.5px] font-medium text-white/50 hover:text-white/90 hover:bg-white/[0.05] transition disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          onClick={onApprove}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-[11.5px] font-semibold bg-brand-accent text-brand-bg transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          {isExecuting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          {isExecuting ? 'Running' : 'Approve & Run'}
        </button>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────────────────────
   2. EXECUTION STEPPER — activity log with live elapsed timer.
   OODA phase labels (Observe/Orient/Decide/Act) are derived client-side from
   tool_name/description — deterministic, zero tokens.
   Phase 8: renders `agent_plan_reoriented` state as an ivory "Plan
   re-oriented ×N" chip + re-spliced step list.
   ───────────────────────────────────────────────────────────────────────────── */
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

// Classify each step into the OODA loop from its tool + description.
const oodaPhase = (step: PlanStepItem): string => {
  const hay = `${step.tool_name || ''} ${step.description || ''}`.toLowerCase()
  if (/\b(plan|decide|select|choose|strateg|design|determine|identify)\b/.test(hay)) return 'Decide'
  if (/\b(analy[sz]e|analy[sz]ing|compare|synthesi[sz]e|evaluat|review|summar|extract|compute|calculate)\b/.test(hay)) return 'Orient'
  if (/\b(search|research|fetch|read|browse|observe|list|check|monitor|gather|find|scan|look)\b/.test(hay)) return 'Observe'
  return 'Act'
}

// OODA labels stay monochrome — neutrals carry the UI.
const OODA_LABEL_CLASS = 'text-white/50'

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
    <div className={`${CARD} p-3.5 sm:p-4`}>
      {/* Header — status + live timer + Phase 8 re-orientation chip */}
      <div className="flex items-center justify-between pb-2.5 mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          {isTaskDone ? (
            <div className="w-4 h-4 rounded-full bg-brand-ok/15 border border-brand-ok/30 flex items-center justify-center shrink-0">
              <Check className="w-2.5 h-2.5 text-brand-ok stroke-[3.5]" />
            </div>
          ) : (
            <Loader2 className="w-3.5 h-3.5 text-brand-muted animate-spin shrink-0" />
          )}
          <span className={`text-[13px] font-medium tracking-tight ${isTaskDone ? 'text-white/90' : 'text-white/75'}`}>
            {isTaskDone ? 'Completed' : 'Working'}
            {elapsedMs > 0 && (
              <span className="font-mono text-[11px] text-white/40 ml-1.5">
                {isTaskDone ? 'in' : 'for'} {formatElapsed(elapsedMs)}
              </span>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          {task.reoriented ? (
            <span
              className={`${CHIP} bg-brand-accent/[0.08] border-brand-accent/25 text-brand-accent/85 flex items-center gap-1 whitespace-nowrap`}
              title={
                // Phase 8.1: show the divergence reason when present; fall back
                // to a generic explanation. reason may be undefined on events
                // that predate this phase, so never render the literal "undefined".
                task.replan_reason && task.replan_reason.length > 0
                  ? task.replan_reason
                  : task.replan_trigger === 'discovery'
                    ? 'The agent adapted the remaining steps after discovering new facts'
                    : 'The agent re-planned the remaining steps after a step failure'
              }
            >
              <Route className="w-2.5 h-2.5" />
              {task.replan_trigger === 'discovery' ? 'Plan adapted (Discovery)' : 'Plan re-oriented'}
              {task.replan_count && task.replan_count > 1 ? ` ×${task.replan_count}` : ''}
            </span>
          ) : null}
          {task.total_token_spend && task.total_token_spend > 0 ? (
            <span className="text-[10px] font-mono text-white/30">
              ~{task.total_token_spend.toLocaleString()} tok
            </span>
          ) : null}
          <span className="text-[10.5px] font-mono text-white/40">{progressPct}%</span>
        </div>
      </div>

      {/* Hairline progress track */}
      <div className="h-px bg-white/[0.07] mb-3 overflow-hidden">
        <div
          className="h-full bg-brand-accent/70 transition-all duration-500"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Steps — collapsible activity rows */}
      <div className="space-y-0.5">

        {plan.map((step) => {
          const isDone = step.status === 'completed'
          const isSkipped = step.status === 'skipped'
          const isFailed = step.status === 'failed'
          const isRunning = step.status === 'running' || (!isDone && !isFailed && !isSkipped && step.index === currentStep && task.state === 'executing')
          const isExpanded = expandedSteps.has(step.index)
          const phase = oodaPhase(step)
          const hasDetail = !!(step.result_summary || step.adapted_reasoning)

          return (
            <div
              key={step.index}
              className={`rounded-lg border transition ${
                isRunning
                  ? 'bg-white/[0.035] border-brand-border'
                  : isFailed
                  ? 'bg-brand-err/[0.05] border-brand-err/20'
                  : 'bg-transparent border-transparent'
              }`}
            >
              <div
                onClick={() => (hasDetail ? toggleExpand(step.index) : undefined)}
                className={`px-2 py-[7px] flex items-center gap-2.5 rounded-lg ${
                  hasDetail ? 'cursor-pointer hover:bg-white/[0.03]' : ''
                } ${isSkipped ? 'opacity-45' : ''}`}
              >
                {/* Status glyph — the only coloured dots in the row */}
                <div className="w-4 flex items-center justify-center shrink-0">
                  {isRunning ? (
                    <Loader2 className="w-3.5 h-3.5 text-white/70 animate-spin" />
                  ) : isDone ? (
                    <Check className="w-3.5 h-3.5 text-brand-ok/90 stroke-[3]" />
                  ) : isFailed ? (
                    <X className="w-3.5 h-3.5 text-brand-err/90 stroke-[3]" />
                  ) : (
                    <span className="text-[10px] font-mono text-white/30">{step.index}</span>
                  )}
                </div>

                {/* OODA phase + activity line */}
                <p className={`text-[12.5px] leading-snug line-clamp-2 sm:truncate flex-1 min-w-0 ${
                  isRunning ? 'text-white/90' : isDone ? 'text-white/60' : isFailed ? 'text-brand-err/90' : 'text-white/40'
                }`}>
                  <span className={`mr-1.5 ${OODA_LABEL_CLASS}`}>{phase}</span>
                  {isDone && step.result_summary ? step.result_summary.split('\n')[0] : step.description}
                  {step.adapted_reasoning && (
                    <span className="ml-2 inline-flex items-center text-[10px] text-brand-accent/70 bg-brand-accent/[0.06] px-1.5 py-0.5 rounded border border-brand-accent/15 font-mono">
                      Adapted: {step.previous_tool || 'tool'} → {step.tool_name}
                    </span>
                  )}
                </p>

                {/* Right: duration + chevron */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {step.duration_ms ? (
                    <span className="text-[9.5px] font-mono text-white/30">{formatElapsed(step.duration_ms)}</span>
                  ) : null}
                  {hasDetail && (
                    <span className="text-white/30 hover:text-white/70">
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </span>
                  )}
                </div>
              </div>

              {/* Collapsible step detail */}
              {isExpanded && hasDetail && (
                <div className="px-2 pb-2.5 pt-0.5 space-y-1.5">
                  {step.adapted_reasoning && (
                    <div className="text-[11px] text-white/70 leading-relaxed border-l-2 border-brand-accent/35 pl-2.5 ml-[7px] bg-white/[0.02] py-1 pr-2 rounded-r">
                      <span className="font-semibold text-brand-accent/85">Adapted — </span>
                      {step.adapted_reasoning}
                    </div>
                  )}
                  {step.result_summary && (
                    <p className="text-[11.5px] text-white/55 leading-relaxed whitespace-pre-wrap border-l-2 border-brand-border pl-2.5 ml-[7px]">
                      {step.result_summary}
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────────────────────
   3. IN-CHAT HITL APPROVAL CARD (when a step pauses for human approval)
   ───────────────────────────────────────────────────────────────────────────── */
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
    <div className={`${CARD} p-4 sm:p-5`}>
      <div className="flex items-start gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-brand-err/10 border border-brand-err/25 flex items-center justify-center text-brand-err shrink-0">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[13px] font-semibold text-white/95 tracking-tight">
              Approval required
            </h4>
            <span className={`${CHIP} bg-white/[0.05] border-brand-border text-white/60 font-mono`}>
              Step {step.index}
            </span>
          </div>
          <p className="text-[12.5px] text-white/80 mt-1 leading-snug">
            {step.description}
          </p>
          {reason && (
            <p className="text-[11px] text-white/45 mt-1 leading-relaxed">
              {reason}
            </p>
          )}
        </div>
      </div>

      {/* Actions — ivory is the affirmative choice */}
      <div className="flex flex-wrap sm:flex-nowrap items-center justify-end gap-2 pt-3 border-t border-brand-border">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-white/50 hover:text-white/90 hover:bg-white/[0.05] transition"
        >
          Cancel task
        </button>
        <button
          type="button"
          onClick={onSkip}
          className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-white/75 hover:text-white bg-white/[0.06] hover:bg-white/[0.1] border border-brand-border transition"
        >
          Skip step
        </button>
        <button
          type="button"
          onClick={onApprove}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-[11.5px] font-semibold bg-brand-accent text-brand-bg transition active:scale-95 cursor-pointer"
        >
          <Check className="w-3.5 h-3.5 stroke-[3]" />
          Approve
        </button>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────────────────────
   3b. INTERACTIVE USER INPUT / CLARIFICATION CARD
   ───────────────────────────────────────────────────────────────────────────── */
export interface AgentUserInputProps {
  question: string
  options: string[]
  selectType?: string
  onSubmit: (answer: string) => void
}

export const AgentUserInputCard: React.FC<AgentUserInputProps> = ({
  question,
  options,
  selectType: _selectType,
  onSubmit,
}) => {
  const [customInput, setCustomInput] = useState('')

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (customInput.trim()) {
      onSubmit(customInput.trim())
    }
  }

  return (
    <div className={`${CARD} p-4 sm:p-5`}>
      <div className="flex items-start gap-3 mb-3.5">
        <div className="w-8 h-8 rounded-lg bg-white/[0.05] border border-brand-border flex items-center justify-center text-brand-muted shrink-0">
          <HelpCircle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[13px] font-semibold text-white/95 tracking-tight">
              Input required
            </h4>
            <span className={`${CHIP} bg-white/[0.05] border-brand-border text-white/55 uppercase tracking-wider font-bold`}>
              Clarification
            </span>
          </div>
          <p className="text-[12.5px] text-white/85 mt-1.5 leading-relaxed">
            {question}
          </p>
        </div>
      </div>

      {/* Option pills — neutral, ivory-wash on hover */}
      {options && options.length > 0 && (
        <div className="flex flex-wrap gap-2 pb-1">
          {options.map((opt, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSubmit(opt)}
              className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium bg-white/[0.05] hover:bg-brand-accent/[0.09] hover:text-white border border-brand-border hover:border-brand-accent/35 text-white/85 transition active:scale-95 text-left cursor-pointer"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      {/* Custom write-in response */}
      <form onSubmit={handleCustomSubmit} className="flex items-center gap-2 pt-3 mt-1.5 border-t border-brand-border">
        <input
          type="text"
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          placeholder="Or type your own answer…"
          className="flex-1 bg-white/[0.04] border border-brand-border rounded-lg px-3 py-1.5 text-[12px] text-white placeholder-white/35 focus:outline-none focus:border-brand-accent/50 transition"
        />
        <button
          type="submit"
          disabled={!customInput.trim()}
          className="px-3.5 py-1.5 rounded-lg bg-brand-accent text-brand-bg disabled:bg-white/[0.06] disabled:text-white/30 text-[12px] font-semibold transition active:scale-95 flex items-center gap-1.5 cursor-pointer disabled:cursor-not-allowed"
        >
          <span>Send</span>
          <Send className="w-3 h-3 stroke-[2.5]" />
        </button>
      </form>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────────────────────
   4. INSTANT STATIC SITE DEPLOYMENT CARD (/sites/:slug) — compact, no inline
   iframe in the thread; preview opens in the ArtifactPanel right dock.
   ───────────────────────────────────────────────────────────────────────────── */
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
    const extractedSlug = _slug || (previewUrl ? previewUrl.split('/sites/').pop()?.split(/[?#]/)[0] : undefined)
    window.dispatchEvent(new CustomEvent('open-file-preview', {
      detail: {
        name: title || 'Deployed Site',
        type: 'text/html',
        url: previewUrl,
        siteSlug: extractedSlug,
      },
    }))
  }

  return (
    <div className={CARD}>
      <div className="p-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-white/[0.05] border border-brand-border flex items-center justify-center text-brand-muted shrink-0">
            <Zap className="w-3.5 h-3.5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-white/95 truncate">{title || 'Live Deployed Web App'}</span>
              {/* The one live indicator: a breathing sage dot on a neutral chip */}
              <span className={`${CHIP} bg-white/[0.05] border-brand-border text-white/65 flex items-center gap-1.5 shrink-0`}>
                <span className="w-1.5 h-1.5 rounded-full bg-brand-ok animate-pulse" />
                LIVE
              </span>
            </div>
            <span className="text-[10.5px] text-white/40 truncate block font-mono">{previewUrl}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0 w-full sm:w-auto justify-end">
          <button
            type="button"
            onClick={openInPanel}
            title="Open preview in the artifact panel"
            className="px-3 py-1.5 rounded-lg text-[11px] font-medium bg-white/[0.05] hover:bg-white/[0.1] text-white/85 border border-brand-border transition"
          >
            <span className="flex items-center gap-1.5">
              <Play className="w-3 h-3" />
              Preview
            </span>
          </button>
          <a
            href={previewUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-brand-accent hover:bg-brand-accent/90 text-brand-bg transition active:scale-95"
          >
            Visit site
          </a>
        </div>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────────────────────
   5. TURN TRACKER — thin scrubber rail on the right edge of the thread.
   Line-ticks, one per assistant turn; the active tick is taller and brighter
   while streaming. Tap a tick to jump, or drag along the rail to scrub.
   ───────────────────────────────────────────────────────────────────────────── */
interface TurnTrackerProps {
  /** Message indices of USER prompts, in order */
  turnIndices: number[]
  /** Scroll container ref so we can read/set scrollTop */
  scrollRef: React.RefObject<HTMLDivElement | null>
}

export const TurnTracker: React.FC<TurnTrackerProps> = ({ turnIndices, scrollRef }) => {
  const railRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const [activeIdx, setActiveIdx] = useState<number>(-1)

  // Track which prompt is currently in view
  useEffect(() => {
    const container = scrollRef.current
    if (!container) return
    const onScroll = () => {
      const scrollTop = container.scrollTop
      const scrollH = container.scrollHeight - container.clientHeight
      if (scrollH <= 0) return
      const frac = scrollTop / scrollH
      const i = Math.round(frac * (turnIndices.length - 1))
      setActiveIdx(Math.min(Math.max(i, 0), turnIndices.length - 1))
    }
    container.addEventListener('scroll', onScroll, { passive: true })
    return () => container.removeEventListener('scroll', onScroll)
  }, [scrollRef, turnIndices])

  if (turnIndices.length < 2) return null

  const jumpTo = (idx: number) => {
    const el = document.querySelector(`[data-turn-anchor="${turnIndices[idx]}"]`)
    el?.scrollIntoView({ behavior: dragging ? 'instant' : 'smooth', block: 'start' })
    setActiveIdx(idx)
  }

  const seekFromPointer = (clientY: number) => {
    const rail = railRef.current
    if (!rail) return
    const rect = rail.getBoundingClientRect()
    const frac = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height))
    const i = Math.round(frac * (turnIndices.length - 1))
    jumpTo(i)
  }

  return (
    <div
      ref={railRef}
      onPointerDown={(e) => {
        setDragging(true)
        try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* noop */ }
        seekFromPointer(e.clientY)
      }}
      onPointerMove={(e) => { if (dragging) seekFromPointer(e.clientY) }}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
      className="hidden sm:flex fixed right-2 sm:right-3 top-24 bottom-32 z-30 flex-col items-end justify-between py-6 w-5 touch-none cursor-ns-resize select-none group pointer-events-auto"
      aria-label="Prompt navigator"
      role="slider"
      aria-valuemin={1}
      aria-valuemax={turnIndices.length}
      aria-valuenow={activeIdx + 1}
    >
      {/* Rail line */}
      <div className="absolute right-2 top-6 bottom-6 w-px bg-white/[0.08] pointer-events-none" />

      {turnIndices.map((_, i) => {
        const isActive = i === activeIdx
        return (
          <div
            key={i}
            onClick={() => jumpTo(i)}
            className="relative flex items-center justify-end w-full py-0.5"
          >
            <span
              className={`block rounded-full transition-all duration-200 cursor-pointer ${
                isActive
                  ? 'w-3.5 h-[2px] bg-brand-accent/90'
                  : 'w-2 h-px bg-white/25 group-hover:bg-white/55 hover:w-3 hover:bg-white/70'
              }`}
              title={`Jump to turn ${i + 1}`}
            />
          </div>
        )
      })}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────────────────────
   6. FILES-CHANGED CARD — one compact chip for everything the agent produced.
   Rows open in the ArtifactPanel.
   ───────────────────────────────────────────────────────────────────────────── */
export interface AgentArtifactItem {
  filename: string
  download_url?: string
  size_bytes?: number
}

interface AgentFileChangesProps {
  artifacts: AgentArtifactItem[]
  onOpen: (file: AgentArtifactItem) => void
}

interface AgentFileNode {
  name: string
  path: string
  isFolder: boolean
  children?: AgentFileNode[]
  file?: AgentArtifactItem
}

function buildAgentFileTree(items: AgentArtifactItem[]): AgentFileNode[] {
  const roots: AgentFileNode[] = []
  for (const item of items) {
    const raw = (item.filename || '').replace(/\\/g, '/').replace(/^\/+/, '').trim()
    if (!raw) continue
    const parts = raw.split('/')
    let current = roots
    let acc = ''
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      acc = acc ? `${acc}/${part}` : part
      const isLast = i === parts.length - 1
      if (isLast) {
        current.push({ name: part, path: acc, isFolder: false, file: item })
      } else {
        let folder = current.find((n) => n.isFolder && n.name === part)
        if (!folder) {
          folder = { name: part, path: acc, isFolder: true, children: [] }
          current.push(folder)
        }
        current = folder.children!
      }
    }
  }
  function sortNodes(nodes: AgentFileNode[]): AgentFileNode[] {
    nodes.sort((a, b) => {
      if (a.isFolder && !b.isFolder) return -1
      if (!a.isFolder && b.isFolder) return 1
      return a.name.localeCompare(b.name)
    })
    for (const n of nodes) {
      if (n.isFolder && n.children) sortNodes(n.children)
    }
    return nodes
  }
  return sortNodes(roots)
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

  const tree = useMemo(() => buildAgentFileTree(files), [files])

  const allFolderPaths = useMemo(() => {
    const paths = new Set<string>()
    const traverse = (nodes: AgentFileNode[]) => {
      for (const n of nodes) {
        if (n.isFolder) {
          paths.add(n.path)
          if (n.children) traverse(n.children)
        }
      }
    }
    traverse(tree)
    return paths
  }, [tree])

  // Multi-folder open state: allows multiple folders to be open at once
  const [openFolders, setOpenFolders] = useState<Set<string>>(() => new Set(allFolderPaths))

  // Update open folders when tree changes
  useEffect(() => {
    setOpenFolders(new Set(allFolderPaths))
  }, [allFolderPaths])

  const toggleFolder = (p: string) => {
    setOpenFolders((prev) => {
      const next = new Set(prev)
      if (next.has(p)) next.delete(p)
      else next.add(p)
      return next
    })
  }

  const toggleAll = () => {
    if (openFolders.size === allFolderPaths.size) setOpenFolders(new Set())
    else setOpenFolders(new Set(allFolderPaths))
  }

  const renderNode = (node: AgentFileNode, depth: number = 0) => {
    if (node.isFolder) {
      const isOpen = openFolders.has(node.path)
      return (
        <div key={node.path} className="flex flex-col">
          <button
            type="button"
            onClick={() => toggleFolder(node.path)}
            style={{ paddingLeft: `${depth * 14 + 8}px` }}
            className="w-full flex items-center gap-1.5 py-1 pr-2 text-left rounded hover:bg-white/[0.04] transition group"
          >
            <span className="text-white/40 group-hover:text-white/70 transition">
              {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </span>
            <span className="text-white/45 shrink-0">
              {isOpen ? <FolderOpen className="w-3.5 h-3.5" /> : <Folder className="w-3.5 h-3.5" />}
            </span>
            <span className="text-[11.5px] font-mono font-medium text-white/85 truncate flex-1">
              {node.name}
            </span>
            <span className="text-[9.5px] font-mono text-white/30 shrink-0">
              {node.children?.length || 0} items
            </span>
          </button>
          {isOpen && node.children && (
            <div className="flex flex-col">
              {node.children.map((child) => renderNode(child, depth + 1))}
            </div>
          )}
        </div>
      )
    }

    const f = node.file!
    return (
      <button
        key={node.path}
        type="button"
        style={{ paddingLeft: `${depth * 14 + 14}px` }}
        onClick={() => f.download_url && onOpen(f)}
        className={`w-full flex items-center justify-between gap-2 py-1 pr-2 rounded text-left ${
          f.download_url ? 'hover:bg-white/[0.04] cursor-pointer' : 'cursor-default'
        } transition`}
      >
        <span className="text-[11px] font-mono text-white/70 truncate">{node.name}</span>
        <span className="text-[9.5px] font-mono text-white/35 shrink-0">{formatSize(f.size_bytes)}</span>
      </button>
    )
  }

  return (
    <div className={CARD}>
      <div className="w-full px-3.5 py-2.5 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="flex items-center gap-2.5 min-w-0 flex-1 hover:opacity-85 text-left transition"
        >
          <div className="w-6 h-6 rounded-md bg-white/[0.05] border border-brand-border flex items-center justify-center text-brand-muted shrink-0">
            <FileText className="w-3 h-3" />
          </div>
          <span className="text-[12.5px] font-medium text-white/85 truncate">
            {files.length} {files.length === 1 ? 'file' : 'files'} changed
            {allFolderPaths.size > 0 && ` (${allFolderPaths.size} folders)`}
          </span>
          <span className="text-white/35 hover:text-white/70 shrink-0 ml-auto">
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </span>
        </button>
      </div>

      {expanded && (
        <div className="px-3.5 pb-3 border-t border-brand-border pt-2 space-y-1">
          {allFolderPaths.size > 1 && (
            <div className="flex justify-end pb-1">
              <button
                type="button"
                onClick={toggleAll}
                className="text-[10px] text-white/40 hover:text-white/80 transition underline"
              >
                {openFolders.size === allFolderPaths.size ? 'Collapse Folders' : 'Expand All'}
              </button>
            </div>
          )}
          <div className="space-y-0.5 max-h-[300px] overflow-y-auto scrollbar-thin">
            {tree.map((node: AgentFileNode) => renderNode(node, 0))}
          </div>
        </div>
      )}
    </div>
  )
}

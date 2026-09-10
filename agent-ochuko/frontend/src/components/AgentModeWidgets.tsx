import React, { useState } from 'react'
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
    <div className="w-full my-3 rounded-2xl bg-[#0f1115] border border-brand-accent/30 p-4 sm:p-5 shadow-xl shadow-black/60 relative overflow-hidden animate-fadeIn select-none">
      {/* Background ambient glow */}
      <div className="absolute top-0 right-0 w-48 h-48 bg-brand-accent/5 rounded-full blur-3xl pointer-events-none" />

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
                    <span className="text-[9.5px] font-medium px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
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

export const AgentExecutionStepper: React.FC<AgentExecutionStepperProps> = ({
  task,
  onPause: _onPause,
  onCancel: _onCancel,
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set())
  const plan = task.plan || []
  const currentStep = task.current_step || 1
  const completedCount = plan.filter((s) => s.status === 'completed').length
  const progressPct = plan.length > 0 ? Math.round((completedCount / plan.length) * 100) : 0

  const toggleExpand = (idx: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const isTaskDone = task.state === 'completed' || progressPct === 100

  return (
    <div className="w-full my-3 rounded-2xl bg-[#0c0e12] border border-white/10 p-4 sm:p-5 shadow-2xl relative overflow-hidden animate-fadeIn select-none">
      {/* Header bar */}
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.08] mb-3">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            {isTaskDone ? (
              <div className="w-6 h-6 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
                <Check className="w-3.5 h-3.5 stroke-[3]" />
              </div>
            ) : (
              <>
                <div className="w-6 h-6 rounded-lg bg-brand-accent/20 border border-brand-accent/40 flex items-center justify-center text-brand-accent">
                  <Zap className="w-3.5 h-3.5" />
                </div>
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              </>
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[12.5px] font-semibold text-white/95">
                {isTaskDone ? 'Task Complete' : 'Executing Task'}
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-white/70">
                {isTaskDone ? 'All steps completed' : `Step ${currentStep}/${plan.length}`}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {task.total_token_spend && task.total_token_spend > 0 ? (
            <span className="text-[10px] font-mono text-white/40">
              ~{task.total_token_spend.toLocaleString()} tok
            </span>
          ) : null}
          <div className="flex items-center gap-1 text-[11px] font-medium text-emerald-400">
            <span>{isTaskDone ? '100%' : `${progressPct}%`}</span>
          </div>
        </div>
      </div>

      {/* Progress Track */}
      <div className="w-full h-1.5 rounded-full bg-white/[0.06] overflow-hidden mb-4">
        <div
          className="h-full bg-gradient-to-r from-brand-accent to-emerald-400 transition-all duration-500 ease-out"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Steps List */}
      <div className="space-y-2">
        {plan.map((step) => {
          const isDone = step.status === 'completed'
          const isFailed = step.status === 'failed'
          const isRunning = step.status === 'running' || (!isDone && !isFailed && step.index === currentStep && task.state === 'executing')
          const isExpanded = expandedSteps.has(step.index)

          return (
            <div
              key={step.index}
              className={`rounded-xl border transition ${
                isRunning
                  ? 'bg-brand-accent/[0.06] border-brand-accent/40 shadow-sm shadow-brand-accent/10'
                  : isDone
                  ? 'bg-white/[0.02] border-white/[0.06]'
                  : isFailed
                  ? 'bg-rose-500/[0.05] border-rose-500/30'
                  : 'bg-white/[0.01] border-white/[0.03] opacity-60'
              }`}
            >
              <div
                onClick={() => (step.result_summary ? toggleExpand(step.index) : undefined)}
                className={`p-2.5 flex items-center justify-between gap-3 ${
                  step.result_summary ? 'cursor-pointer hover:bg-white/[0.02]' : ''
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {/* Status icon */}
                  <div className="w-5 h-5 rounded-full flex items-center justify-center shrink-0">
                    {isRunning ? (
                      <Loader2 className="w-3.5 h-3.5 text-brand-accent animate-spin" />
                    ) : isDone ? (
                      <div className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                        <Check className="w-2.5 h-2.5 stroke-[3]" />
                      </div>
                    ) : isFailed ? (
                      <div className="w-4 h-4 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center">
                        <X className="w-2.5 h-2.5 stroke-[3]" />
                      </div>
                    ) : (
                      <span className="text-[10px] font-mono text-white/30">{step.index}</span>
                    )}
                  </div>

                  <p
                    className={`text-[12px] font-medium truncate ${
                      isRunning
                        ? 'text-white'
                        : isDone
                        ? 'text-white/80'
                        : isFailed
                        ? 'text-rose-300'
                        : 'text-white/40'
                    }`}
                  >
                    {step.description}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {step.duration_ms && (
                    <span className="text-[9.5px] font-mono text-white/30">
                      {(step.duration_ms / 1000).toFixed(1)}s
                    </span>
                  )}
                  {step.result_summary && (
                    <div className="text-white/40 hover:text-white">
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </div>
                  )}
                </div>
              </div>

              {/* Collapsible Step Result Summary */}
              {isExpanded && step.result_summary && (
                <div className="px-3 pb-3 pt-1 border-t border-white/[0.04] text-[11px] text-white/70 leading-relaxed font-sans">
                  <p className="bg-black/40 rounded-lg p-2.5 border border-white/[0.06]">
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
    <div className="w-full my-3.5 rounded-2xl bg-[#14100c] border border-amber-500/40 p-4 sm:p-5 shadow-2xl relative overflow-hidden animate-fadeIn select-none">
      {/* Background ambient amber flare */}
      <div className="absolute top-0 right-0 w-36 h-36 bg-amber-500/10 rounded-full blur-2xl pointer-events-none" />

      <div className="flex items-start gap-3 mb-3">
        <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0 mt-0.5">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[13px] font-semibold text-white tracking-tight">
              Action Approval Required
            </h4>
            <span className="text-[9.5px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold uppercase tracking-wider">
              Step {step.index}
            </span>
          </div>
          <p className="text-[12px] text-white/70 mt-1 font-medium leading-snug">
            {step.description}
          </p>
          {reason && (
            <p className="text-[11px] text-amber-200/60 mt-1 leading-relaxed">
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
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-[11.5px] font-bold bg-amber-400 hover:bg-amber-300 text-black shadow-md shadow-amber-500/20 transition active:scale-95 cursor-pointer"
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
    <div className="w-full my-3.5 rounded-lg bg-[#0d0f14] border border-white/10 shadow-lg relative overflow-hidden animate-fadeIn select-none">
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


import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Play,
  Cpu,
  FileText,
  Code,
  Globe,
  HelpCircle,
  Terminal,
  BarChart,
  FileEdit,
  Check,
  Copy,
  Sparkles,
  Brain,
  Layout,
  Database,
  ShieldCheck,
  Zap,
  Layers,
} from 'lucide-react'

interface CapabilityCard {
  id: string
  title: string
  icon: React.ComponentType<{ className?: string }>
  tools: string[]
  recommendedMode: 'think' | 'solve' | 'discuss' | 'agent'
  description: string
  prompt: string
  expectedOutcome: string
}

const CAPABILITY_SECTIONS: CapabilityCard[] = [
  {
    id: 'quantitative',
    title: 'Quantitative Modeling & Algorithmic Valuation',
    icon: Terminal,
    tools: ['execute_code', 'sandbox_write'],
    recommendedMode: 'think',
    description:
      'Directly executes numerical simulations, capitalization table calculations, and financial valuations in the persistent Python sandbox. Produces exact figures and metrics rather than passive formulas.',
    prompt:
      'Execute a multi-scenario quantitative valuation of a high-growth SaaS business at $15M ARR: calculate Burn Multiple, CAC Payback Period, Net Dollar Retention, and Rule of 40 across conservative, base, and expansion scenarios. Generate a sensitivity table comparing capital efficiency against runway months.',
    expectedOutcome:
      'Ochuko executes Python in the sandbox, computes exact financial ratios, and presents a formatted sensitivity matrix.',
  },
  {
    id: 'file-parsing',
    title: 'Forensic Document & Financial Statement Audit',
    icon: FileText,
    tools: ['sandbox_read', 'execute_code', 'multimodal_vision'],
    recommendedMode: 'think',
    description:
      'Extracts structured data from multi-page quarterly 10-Q disclosures, PDFs, spreadsheets, and scanned documents. Reconciles line items and detects accounting variances.',
    prompt:
      'Audit our quarterly 10-Q financial disclosure: extract all revenue breakdown line items, reconcile operating cash flow against GAAP net income, flag any deferred revenue timing discrepancies, and generate an executive summary table highlighting gross margin compression.',
    expectedOutcome:
      'Dissects balance sheet and cash flow statements, performs reconciliation checks, and surfaces accounting insights.',
  },
  {
    id: 'cohort-analytics',
    title: 'Predictive Cohort Retention & Churn Decay Analysis',
    icon: BarChart,
    tools: ['execute_code', 'visualize__show_widget'],
    recommendedMode: 'think',
    description:
      'Performs statistical cohort analyses across customer subscription vintages. Identifies churn acceleration points and quantifies revenue preservation impact.',
    prompt:
      'Perform an end-to-end cohort retention and churn analysis on our annualized subscriber cohorts: compute monthly retention percentages, pinpoint the exact retention decay inflection point, and model the compounding ARR impact of reducing net churn by 200 basis points over 24 months.',
    expectedOutcome:
      'Executes statistical cohort algorithms in Python and presents a retention decay breakdown with financial impact modeling.',
  },
  {
    id: 'code-generation',
    title: 'Full-Stack Architecture & Autonomous Refactoring',
    icon: Code,
    tools: ['sandbox_write', 'terminal', 'sandbox_ls'],
    recommendedMode: 'agent',
    description:
      'Architects production-grade microservices and middleware with zero-trust token handling, distributed rate limiting, and complete unit test coverage.',
    prompt:
      'Architect and implement a production-grade FastAPI authentication service with zero-trust JWT token rotation, Redis-backed sliding window rate-limiting, comprehensive audit logging middleware, and write accompanying pytest test suites validating 100% boundary edge cases.',
    expectedOutcome:
      'Produces fully implemented, production-ready backend code files and verification tests without stubs or placeholders.',
  },
  {
    id: 'interactive-widgets',
    title: 'Interactive Visual UI Components & Dynamic Calculators',
    icon: Layout,
    tools: ['visualize__read_me', 'visualize__show_widget'],
    recommendedMode: 'solve',
    description:
      'Renders live interactive UI widgets directly in chat, featuring real-time sliders, tabs, responsive charts, and instant parameter recalculation.',
    prompt:
      'Render an interactive mortgage amortization and refinancing calculator widget with dynamic interest rate sliders, extra principal payment toggles, and real-time payoff schedule comparison charts directly in the chat interface.',
    expectedOutcome:
      'Renders a live, fully interactive React/HTML widget directly into the conversation panel.',
  },
  {
    id: 'deep-research',
    title: 'Deep Multi-Source Intelligence & Frontier Benchmarking',
    icon: Globe,
    tools: ['deep_research', 'search_web', 'fetch_url'],
    recommendedMode: 'think',
    description:
      'Fires parallel multi-query web searches and deep page scrapes to compile comprehensive, authoritative comparative intelligence with inline citations.',
    prompt:
      'Conduct a deep multi-source research investigation comparing leading open-weights frontier LLMs: analyze architectural trade-offs, inference throughput (tokens/sec/GPU), KV-cache quantization benchmarks, and context-window fidelity across enterprise production workloads.',
    expectedOutcome:
      'Executes multi-query deep research, verifies conflicting benchmarks across official sources, and provides cited comparative tables.',
  },
  {
    id: 'document-writing',
    title: 'Institutional Memorandums & Strategic Briefings',
    icon: FileEdit,
    tools: ['sandbox_write', 'deep_research'],
    recommendedMode: 'think',
    description:
      'Drafts executive investment memos, board proposals, and technical whitepapers with rigorous analytical depth, clear thesis articulation, and actionable risk matrices.',
    prompt:
      'Synthesize an institutional investment memorandum for a Series A AI infrastructure startup: provide an in-depth market landscape analysis, competitive moat assessment against hyperscalers, unit economics breakdown, defensibility matrix, and key underwriting risks.',
    expectedOutcome:
      'Delivers an institutional-grade investment brief with structured thesis, market positioning, and defensibility framework.',
  },
  {
    id: 'imaging',
    title: 'Studio-Grade Generative Imaging & Concept Art',
    icon: Sparkles,
    tools: ['generate_image'],
    recommendedMode: 'solve',
    description:
      'Synthesizes photorealistic 8K imagery, cinematic concept renders, and visual assets using the FLUX generation engine with precise lighting and spatial direction.',
    prompt:
      'Generate a hyper-realistic, cinematic 8K architectural concept render of a sustainable deep-sea research station with illuminated observation domes, bioluminescent deep-ocean marine life, volumetric water caustics, and sleek titanium structural framing.',
    expectedOutcome:
      'Generates and renders a studio-quality visual asset directly in the chat and deliverable media tray.',
  },
  {
    id: 'memory',
    title: 'Persistent Context & Engineering Persona Memory',
    icon: Database,
    tools: ['memory_save', 'memory_recall', 'memory_edit'],
    recommendedMode: 'think',
    description:
      'Preserves technical preferences, styling guidelines, and domain constraints across sessions with versioned, transactional memory storage.',
    prompt:
      'Remember my core engineering stack and standards: TypeScript strict mode, Tailwind CSS with custom warm charcoal tokens, FastAPI with async PostgreSQL sessions, Pydantic v2 validation models, and automated CI/CD integration tests.',
    expectedOutcome:
      'Persists user engineering standards to durable memory, automatically applying them to future turns and projects.',
  },
]

export const Capabilities: React.FC = () => {
  const navigate = useNavigate()
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleTryPrompt = (promptText: string, mode: string) => {
    navigate(`/?prompt=${encodeURIComponent(promptText)}&mode=${encodeURIComponent(mode)}`)
  }

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  return (
    <div className="h-screen w-full overflow-y-auto bg-brand-bg text-brand-text flex flex-col font-sans selection:bg-brand-accent/20 scroll-smooth">
      {/* Top Navigation Bar */}
      <nav className="h-14 border-b border-brand-border bg-brand-surface/95 backdrop-blur-md sticky top-0 z-50 flex items-center justify-between px-6 select-none shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 rounded bg-brand-card flex items-center justify-center border border-brand-border">
            <Cpu className="w-3.5 h-3.5 text-brand-accent" />
          </div>
          <span className="text-[13px] font-bold tracking-wider text-brand-text uppercase">
            Develop AI Agents in Azure
          </span>
          <span className="text-brand-border">|</span>
          <span className="text-[11px] font-medium text-brand-muted tracking-wide">
            Ochuko Frontier Capabilities & System Directory
          </span>
        </div>

        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-muted hover:text-brand-text transition-colors duration-150 rounded-lg px-3 py-1.5 border border-transparent hover:border-brand-border hover:bg-brand-card focus:outline-none focus:ring-1 focus:ring-brand-accent"
          aria-label="Navigate back to chat"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Chat</span>
        </button>
      </nav>

      {/* Main Content Layout */}
      <div className="flex-1 max-w-6xl w-full mx-auto px-6 py-10 flex gap-10">
        {/* Left Side: Table of Contents / Sticky Navigation */}
        <aside className="w-64 hidden md:block shrink-0">
          <div className="sticky top-20 space-y-6">
            <div className="space-y-2">
              <span className="text-[10px] font-bold uppercase tracking-widest text-brand-muted/70 block">
                Capability Directory
              </span>
              <ul className="space-y-1 text-[12px] font-medium">
                <li>
                  <a
                    href="#overview"
                    className="text-brand-muted hover:text-brand-text hover:bg-brand-surface/60 transition px-2.5 py-1.5 rounded-lg block focus:outline-none focus:ring-1 focus:ring-brand-accent"
                  >
                    Overview & Architecture
                  </a>
                </li>
                {CAPABILITY_SECTIONS.map((sec) => (
                  <li key={sec.id}>
                    <a
                      href={`#${sec.id}`}
                      className="text-brand-muted hover:text-brand-text hover:bg-brand-surface/60 transition px-2.5 py-1.5 rounded-lg block truncate focus:outline-none focus:ring-1 focus:ring-brand-accent"
                    >
                      {sec.title}
                    </a>
                  </li>
                ))}
                <li>
                  <a
                    href="#quick-start"
                    className="text-brand-muted hover:text-brand-text hover:bg-brand-surface/60 transition px-2.5 py-1.5 rounded-lg block focus:outline-none focus:ring-1 focus:ring-brand-accent"
                  >
                    Quick Start & Modes
                  </a>
                </li>
              </ul>
            </div>

            {/* Agent Engine Status Box */}
            <div className="p-4 rounded-xl border border-brand-border bg-brand-surface space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-[11px] text-brand-text font-bold uppercase tracking-wider">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span>Agent Ochuko</span>
                </div>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-brand-card text-brand-muted border border-brand-border">
                  v1.2.0
                </span>
              </div>
              <p className="text-[11px] text-brand-muted leading-relaxed">
                Autonomous multi-tool execution enabled. Deep reasoning with live Python sandbox, web
                grounding, and Azure security boundaries.
              </p>
            </div>
          </div>
        </aside>

        {/* Right Side: Main Documentation & Prompts */}
        <article className="flex-1 max-w-3xl space-y-10 pb-24">
          {/* Header Section */}
          <div className="space-y-4 border-b border-brand-border pb-8" id="overview">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-brand-border bg-brand-surface text-xs text-brand-muted">
              <Sparkles className="w-3.5 h-3.5 text-brand-accent" />
              <span>Frontier Agentic Intelligence</span>
            </div>

            <h1 className="text-3xl font-semibold tracking-tight text-brand-text">
              Autonomous Capabilities & Prompt Directory
            </h1>

            <p className="text-base text-brand-muted leading-7">
              Agent Ochuko is engineered to operate with full task ownership. Rather than outputting passive
              instructions or requiring manual user steps, Ochuko autonomously plans, invokes sandbox tools,
              executes live code, queries real-time databases, and delivers finished, production-grade outcomes.
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <div className="flex items-center gap-2 text-[11px] text-brand-muted font-medium bg-brand-surface border border-brand-border px-3 py-1.5 rounded-lg">
                <Brain className="w-3.5 h-3.5 text-brand-accent" />
                <span>Autonomous OODA Execution Loop</span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-brand-muted font-medium bg-brand-surface border border-brand-border px-3 py-1.5 rounded-lg">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Isolated Azure Sandbox</span>
              </div>
            </div>
          </div>

          {/* Autonomous Execution Note */}
          <blockquote className="p-4 rounded-xl border-l-2 border-brand-accent bg-brand-surface border border-brand-border space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-brand-text">
              <Zap className="w-3.5 h-3.5 text-brand-accent" />
              <span>Intelligent Tool Execution Guarantee</span>
            </div>
            <p className="text-xs text-brand-muted leading-relaxed">
              In <strong>Think</strong> and <strong>Agent</strong> modes, Ochuko does not stop to request approval
              for routine computational analysis, document extraction, or deliverable creation. The engine
              intelligently decides when tools are required and executes them autonomously.
            </p>
          </blockquote>

          {/* Capability Cards List */}
          <div className="space-y-8">
            {CAPABILITY_SECTIONS.map((sec) => {
              const Icon = sec.icon
              const isCopied = copiedId === sec.id

              return (
                <section
                  key={sec.id}
                  id={sec.id}
                  className="p-6 rounded-xl border border-brand-border bg-brand-surface space-y-5 hover:border-brand-muted/30 transition-all duration-150"
                >
                  {/* Card Title & Badges */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-brand-card flex items-center justify-center border border-brand-border shrink-0">
                        <Icon className="w-5 h-5 text-brand-accent" />
                      </div>
                      <div>
                        <h2 className="text-lg font-semibold text-brand-text tracking-tight">
                          {sec.title}
                        </h2>
                        <div className="flex flex-wrap items-center gap-2 mt-1">
                          <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-brand-card text-brand-accent border border-brand-border/60">
                            Mode: {sec.recommendedMode}
                          </span>
                          {sec.tools.map((t) => (
                            <span
                              key={t}
                              className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#ffffff]/5 text-brand-muted border border-brand-border/40"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-sm text-brand-muted leading-relaxed">{sec.description}</p>

                  {/* Prompt Box */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-brand-muted uppercase tracking-wider font-mono">
                      <span className="flex items-center gap-1.5">
                        <Layers className="w-3 h-3" />
                        <span>Executive Prompt</span>
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleCopy(sec.id, sec.prompt)}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-brand-card text-brand-muted hover:text-brand-text hover:bg-brand-card/80 border border-brand-border text-[10px] font-mono transition active:scale-95"
                          title="Copy prompt text"
                        >
                          {isCopied ? (
                            <>
                              <Check className="w-3 h-3 text-emerald-400" />
                              <span className="text-emerald-400">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3 h-3" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="relative group bg-brand-card/90 rounded-lg p-4 border border-brand-border/80">
                      <p className="text-xs text-brand-text font-mono leading-relaxed pr-12">
                        "{sec.prompt}"
                      </p>

                      <button
                        onClick={() => handleTryPrompt(sec.prompt, sec.recommendedMode)}
                        className="absolute right-3 top-3 p-2 rounded-md bg-brand-accent text-black hover:bg-white active:scale-95 transition-all shadow-sm flex items-center gap-1.5 text-xs font-semibold"
                        title="Open this prompt in chat"
                        aria-label={`Try ${sec.title} prompt in chat`}
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span className="hidden sm:inline text-[11px]">Run</span>
                      </button>
                    </div>
                  </div>

                  {/* Expected Outcome */}
                  <div className="pt-1 flex items-start gap-2 text-xs text-brand-muted/90 bg-brand-card/40 p-3 rounded-lg border border-brand-border/40">
                    <span className="font-semibold text-brand-accent shrink-0">Output:</span>
                    <span>{sec.expectedOutcome}</span>
                  </div>
                </section>
              )
            })}
          </div>

          {/* Quick Start Guide */}
          <section
            id="quick-start"
            className="p-6 rounded-xl border border-brand-border bg-brand-surface space-y-4"
          >
            <div className="flex items-center gap-2.5 border-b border-brand-border pb-3">
              <HelpCircle className="w-5 h-5 text-brand-accent" />
              <h2 className="text-lg font-semibold text-brand-text">Quick Start Guide & Modes</h2>
            </div>

            <p className="text-sm text-brand-muted leading-relaxed">
              Agent Ochuko adapts its reasoning depth and tool invocation behavior based on your selected mode:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
              <div className="p-3.5 rounded-lg bg-brand-card border border-brand-border space-y-1.5">
                <div className="flex items-center gap-2 text-xs font-bold text-brand-text uppercase tracking-wider">
                  <Brain className="w-3.5 h-3.5 text-brand-accent" />
                  <span>Think Mode</span>
                </div>
                <p className="text-xs text-brand-muted leading-relaxed">
                  Deep multi-step reasoning with expanded tokens. Deconstructs complex goals, formulates
                  execution strategies, and autonomously triggers calculations and web research.
                </p>
              </div>

              <div className="p-3.5 rounded-lg bg-brand-card border border-brand-border space-y-1.5">
                <div className="flex items-center gap-2 text-xs font-bold text-brand-text uppercase tracking-wider">
                  <Cpu className="w-3.5 h-3.5 text-brand-accent" />
                  <span>Solve Mode</span>
                </div>
                <p className="text-xs text-brand-muted leading-relaxed">
                  Fast, targeted execution. Ideal for rapid data conversions, interactive widget rendering,
                  and focused numerical solutions with minimal preamble.
                </p>
              </div>

              <div className="p-3.5 rounded-lg bg-brand-card border border-brand-border space-y-1.5">
                <div className="flex items-center gap-2 text-xs font-bold text-brand-text uppercase tracking-wider">
                  <Layers className="w-3.5 h-3.5 text-brand-accent" />
                  <span>Agent Mode</span>
                </div>
                <p className="text-xs text-brand-muted leading-relaxed">
                  Full OODA loop autonomy. Plans multi-stage tasks, manages state across steps, generates
                  complete codebases, and deploys live web applications.
                </p>
              </div>

              <div className="p-3.5 rounded-lg bg-brand-card border border-brand-border space-y-1.5">
                <div className="flex items-center gap-2 text-xs font-bold text-brand-text uppercase tracking-wider">
                  <Sparkles className="w-3.5 h-3.5 text-brand-accent" />
                  <span>Discuss Mode</span>
                </div>
                <p className="text-xs text-brand-muted leading-relaxed">
                  Direct conversational dialogue. Fast latency, zero tool overhead, perfect for brainstorming,
                  writing critique, and conceptual exploration.
                </p>
              </div>
            </div>

            <div className="pt-4 flex justify-end">
              <button
                onClick={() => navigate('/')}
                className="px-4 py-2 rounded-lg bg-brand-accent text-black hover:bg-white text-xs font-bold uppercase tracking-wider transition-all active:scale-95 shadow-sm"
              >
                Launch Ochuko Chat →
              </button>
            </div>
          </section>
        </article>
      </div>
    </div>
  )
}

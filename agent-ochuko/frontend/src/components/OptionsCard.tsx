import { useState } from 'react'

export interface OptionAttribute {
  label: string
  value: string
}

export interface OptionItem {
  name: string
  price?: string
  url?: string
  blurb?: string
  attributes?: OptionAttribute[]
}

export interface OptionsCardProps {
  mode: 'single_pick' | 'compare' | 'carousel'
  summary: string
  options: OptionItem[]
}

const MODE_META: Record<string, { badge: string; accent: string }> = {
  single_pick: { badge: 'BEST PICK', accent: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' },
  compare: { badge: 'COMPARE', accent: 'text-indigo-400 bg-indigo-400/10 border-indigo-400/20' },
  carousel: { badge: 'EXPLORE', accent: 'text-amber-400 bg-amber-400/10 border-amber-400/20' },
}

function safeHref(url?: string): string | undefined {
  return url && /^https?:\/\//i.test(url.trim()) ? url.trim() : undefined
}

function PricePill({ price }: { price?: string }) {
  if (!price) return null
  return (
    <span className="flex-shrink-0 text-[11px] font-mono font-semibold text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 rounded-md px-1.5 py-0.5 whitespace-nowrap">
      {price}
    </span>
  )
}

function ViewLink({ url }: { url?: string }) {
  const href = safeHref(url)
  if (!href) return null
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 mt-2 text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 transition-colors duration-150"
    >
      View
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M7 17L17 7M9 7h8v8" />
      </svg>
    </a>
  )
}

function AttributeRows({ attributes }: { attributes?: OptionAttribute[] }) {
  if (!attributes || attributes.length === 0) return null
  return (
    <div className="mt-2.5">
      {attributes.map((a, i) => (
        <div
          key={`${a.label}-${i}`}
          className="flex items-baseline justify-between gap-3 py-1.5 border-b border-white/[0.05] last:border-0"
        >
          <span className="text-[10px] uppercase tracking-wider text-[#8c92a0] flex-shrink-0">
            {a.label}
          </span>
          <span className="text-[12px] text-[#e2e5eb] font-medium text-right leading-snug">
            {a.value}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Featured treatment for mode='single_pick' — one richly presented option. */
function SinglePick({ option }: { option: OptionItem }) {
  return (
    <div className="rounded-xl bg-[#23262d] border border-white/[0.08] p-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[14px] font-semibold text-white leading-snug">{option.name}</span>
        <PricePill price={option.price} />
      </div>
      {option.blurb && (
        <p className="text-[12px] text-[#a0a6b2] mt-1.5 leading-relaxed">{option.blurb}</p>
      )}
      <AttributeRows attributes={option.attributes} />
      <ViewLink url={option.url} />
    </div>
  )
}

/** Side-by-side columns for mode='compare' (2-3 options, aligned attribute rows). */
function CompareGrid({ options }: { options: OptionItem[] }) {
  const colsClass = options.length === 2 ? 'sm:grid-cols-2' : 'sm:grid-cols-3'
  return (
    <div className={`grid grid-cols-1 ${colsClass} gap-2.5`}>
      {options.map((o, i) => (
        <div
          key={i}
          className="rounded-xl bg-[#23262d] border border-white/[0.08] p-3 min-w-0"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="text-[13px] font-semibold text-white leading-snug">{o.name}</span>
            <PricePill price={o.price} />
          </div>
          {o.blurb && (
            <p className="text-[11px] text-[#a0a6b2] mt-1.5 leading-relaxed">{o.blurb}</p>
          )}
          <AttributeRows attributes={o.attributes} />
          <ViewLink url={o.url} />
        </div>
      ))}
    </div>
  )
}

/**
 * Horizontal snap-scrolling cards for mode='carousel' (1-6 options).
 * Chrome-specific hardening: the global index.css ::-webkit-scrollbar rules
 * give this rail a thin 5px scrollbar; overscroll-behavior-x:'contain' stops
 * Chrome's back/forward touchpad swipe navigation from hijacking rail scroll.
 */
function Carousel({ options }: { options: OptionItem[] }) {
  return (
    <div
      className="flex gap-2.5 overflow-x-auto pb-1.5 -mx-1 px-1 snap-x snap-mandatory"
      style={{ overscrollBehaviorX: 'contain' } as React.CSSProperties}
    >
      {options.map((o, i) => (
        <div
          key={i}
          className="min-w-[195px] max-w-[230px] snap-start rounded-xl bg-[#23262d] border border-white/[0.08] p-3 flex-shrink-0"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="text-[13px] font-semibold text-white leading-snug">{o.name}</span>
            <PricePill price={o.price} />
          </div>
          {o.blurb && (
            <p className="text-[11px] text-[#a0a6b2] mt-1.5 leading-relaxed line-clamp-3">{o.blurb}</p>
          )}
          <AttributeRows attributes={o.attributes} />
          <ViewLink url={o.url} />
        </div>
      ))}
    </div>
  )
}

/**
 * Native renderer for the backend `render_options_card` display-card tool
 * (Phase 6 consolidated structured display layer).
 *
 * Payload contract (see backend/app/core/agent_tools.py + verification_gates.py):
 *   { mode: 'single_pick' | 'compare' | 'carousel',
 *     summary: string,
 *     options: [{ name, price?, url?, blurb?, attributes?: [{ label, value }] }] }
 */
export function OptionsCard({ mode, summary, options = [] }: OptionsCardProps) {
  const [activeIdx] = useState(0)
  if (!options || options.length === 0) return null

  const meta = MODE_META[mode] || MODE_META.carousel
  const featured = mode === 'single_pick' ? options[Math.min(activeIdx, options.length - 1)] : undefined

  return (
    <div
      className="my-3 w-full max-w-[440px] sm:max-w-[600px] rounded-2xl border border-white/[0.08] bg-[#1e2025] p-3.5 sm:p-4 shadow-xl font-sans select-none"
      style={{
        boxShadow: '0 8px 30px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
      }}
    >
      {/* ── HEADER: mode badge + summary ───────────────────────────────── */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`flex-shrink-0 text-[10px] font-mono font-semibold uppercase tracking-widest px-2 py-0.5 rounded-full border ${meta.accent}`}
        >
          {meta.badge}
        </span>
        {summary && (
          <p className="text-[12px] text-[#a0a6b2] leading-snug min-w-0">{summary}</p>
        )}
      </div>

      {/* ── BODY: layout per mode ──────────────────────────────────────── */}
      {featured ? (
        <SinglePick option={featured} />
      ) : mode === 'compare' ? (
        <CompareGrid options={options} />
      ) : (
        <Carousel options={options} />
      )}
    </div>
  )
}

export default OptionsCard
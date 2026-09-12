import { useState } from 'react'

export interface SportsEventItem {
  team: 'home' | 'away'
  player: string
  minute: string
  type: 'goal' | 'yellow_card' | 'red_card' | 'substitution' | 'penalty' | 'own_goal'
  detail?: string
}

export interface SportsMatchStats {
  possession?: [number, number]
  shots?: [number, number]
  shots_on_target?: [number, number]
  corners?: [number, number]
  fouls?: [number, number]
}

export interface SportsMatchCardProps {
  home_team: string
  away_team: string
  home_score: string | number
  away_score: string | number
  status: string
  competition: string
  home_team_logo?: string
  away_team_logo?: string
  events?: SportsEventItem[]
  stats?: SportsMatchStats
  summary?: string
}

// Known club badge color schemes and initials
const KNOWN_CLUBS: Record<string, { bg: string; text: string; short: string; accent: string; crestUrl?: string }> = {
  chelsea: {
    bg: '#034694',
    text: '#ffffff',
    short: 'CFC',
    accent: '#d1a153',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/c/cc/Chelsea_FC.svg',
  },
  hull: {
    bg: '#f5971d',
    text: '#111111',
    short: 'HULL',
    accent: '#000000',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/5/54/Hull_City_A.F.C._logo.svg',
  },
  'hull city': {
    bg: '#f5971d',
    text: '#111111',
    short: 'HULL',
    accent: '#000000',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/5/54/Hull_City_A.F.C._logo.svg',
  },
  arsenal: {
    bg: '#ef0107',
    text: '#ffffff',
    short: 'ARS',
    accent: '#9c824a',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg',
  },
  liverpool: {
    bg: '#c8102e',
    text: '#ffffff',
    short: 'LIV',
    accent: '#00b2a9',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/0/0c/Liverpool_FC.svg',
  },
  'manchester city': {
    bg: '#6cabdd',
    text: '#1c2c5b',
    short: 'MCI',
    accent: '#ffffff',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/e/eb/Manchester_City_FC_badge.svg',
  },
  'man city': {
    bg: '#6cabdd',
    text: '#1c2c5b',
    short: 'MCI',
    accent: '#ffffff',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/e/eb/Manchester_City_FC_badge.svg',
  },
  'manchester united': {
    bg: '#da291c',
    text: '#ffe500',
    short: 'MUN',
    accent: '#000000',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/7/7a/Manchester_United_FC_crest.svg',
  },
  'man utd': {
    bg: '#da291c',
    text: '#ffe500',
    short: 'MUN',
    accent: '#000000',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/7/7a/Manchester_United_FC_crest.svg',
  },
  'real madrid': {
    bg: '#ffffff',
    text: '#111111',
    short: 'RMA',
    accent: '#febe10',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/5/56/Real_Madrid_CF.svg',
  },
  barcelona: {
    bg: '#004d98',
    text: '#edbb00',
    short: 'BAR',
    accent: '#a50044',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/4/47/FC_Barcelona_%28crest%29.svg',
  },
  'bayern munich': {
    bg: '#dc052d',
    text: '#ffffff',
    short: 'BAY',
    accent: '#0066b2',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/commons/1/1b/FC_Bayern_M%C3%BCnchen_logo_%282017%29.svg',
  },
  psg: {
    bg: '#004170',
    text: '#ffffff',
    short: 'PSG',
    accent: '#da291c',
    crestUrl: 'https://upload.wikimedia.org/wikipedia/en/a/a7/Paris_Saint-Germain_F.C..svg',
  },
}

function resolveClubInfo(teamName: string) {
  const norm = (teamName || '').toLowerCase().trim()
  for (const [key, data] of Object.entries(KNOWN_CLUBS)) {
    if (norm === key || norm.includes(key) || key.includes(norm)) {
      return data
    }
  }
  // Fallback generation based on initials
  const parts = teamName.trim().split(/\s+/)
  const short = parts.length > 1 ? (parts[0][0] + parts[1][0]).toUpperCase() : teamName.slice(0, 3).toUpperCase()
  return {
    bg: '#252932',
    text: '#e2e5eb',
    short,
    accent: '#6366f1',
    crestUrl: undefined,
  }
}

export function SportsMatchCard({
  home_team,
  away_team,
  home_score,
  away_score,
  status,
  competition,
  home_team_logo,
  away_team_logo,
  events = [],
  stats,
  summary,
}: SportsMatchCardProps) {
  const [activeTab, setActiveTab] = useState<'events' | 'stats'>('events')
  const [homeImgError, setHomeImgError] = useState(false)
  const [awayImgError, setAwayImgError] = useState(false)

  const homeInfo = resolveClubInfo(home_team)
  const awayInfo = resolveClubInfo(away_team)

  const finalHomeLogo = !homeImgError ? (home_team_logo || homeInfo.crestUrl) : undefined
  const finalAwayLogo = !awayImgError ? (away_team_logo || awayInfo.crestUrl) : undefined

  // Determine if match is currently live
  const isLive = (() => {
    const s = (status || '').toLowerCase()
    return (
      s.includes("'") ||
      s.includes('live') ||
      s.includes('+') ||
      s.includes('1st') ||
      s.includes('2nd') ||
      s.includes('ht') ||
      s.includes('half')
    ) && !s.includes('ft') && !s.includes('final') && !s.includes('postponed')
  })()

  // Check if meaningful stats exist (not all zeroes, dummy placeholders, or undefined)
  const hasValidStats = Boolean(
    stats && (
      (stats.possession && (Number(stats.possession[0]) > 0 || Number(stats.possession[1]) > 0)) ||
      (stats.shots && (Number(stats.shots[0]) > 0 || Number(stats.shots[1]) > 0)) ||
      (stats.shots_on_target && (Number(stats.shots_on_target[0]) > 0 || Number(stats.shots_on_target[1]) > 0)) ||
      (stats.corners && (Number(stats.corners[0]) > 0 || Number(stats.corners[1]) > 0)) ||
      (stats.fouls && (Number(stats.fouls[0]) > 0 || Number(stats.fouls[1]) > 0))
    )
  )

  // Smart event organizer:
  // 1. Group repeated goals for the same player (e.g. "28'" and "34'" -> "28', 34'")
  // 2. Pair up goals across teams with a central ⚽
  // 3. Give cards (🟨, 🟥) and substitutions (🔄) dedicated rows with their own distinct icon
  const formatPlayerName = (name: string) => {
    const trimmed = (name || '').trim()
    const parts = trimmed.split(/\s+/)
    if (parts.length >= 2 && trimmed.length > 15) {
      return `${parts[0][0]}. ${parts.slice(1).join(' ')}`
    }
    return trimmed
  }

  const homeGoals: { player: string; minute: string }[] = []
  const awayGoals: { player: string; minute: string }[] = []
  const otherEvents: { team: 'home' | 'away'; player: string; minute: string; type: string }[] = []

  for (const ev of events) {
    const formattedPlayer = formatPlayerName(ev.player)
    if (ev.type === 'goal' || ev.type === 'penalty' || ev.type === 'own_goal') {
      const target = ev.team === 'home' ? homeGoals : awayGoals
      const existing = target.find((g) => g.player.toLowerCase() === formattedPlayer.toLowerCase())
      if (existing) {
        const cleanMinute = ev.minute.replace(/[',]/g, '').trim() + "'"
        if (!existing.minute.includes(cleanMinute)) {
          existing.minute = `${existing.minute}, ${ev.minute}`
        }
      } else {
        target.push({ player: formattedPlayer, minute: ev.minute })
      }
    } else {
      otherEvents.push({
        team: ev.team,
        player: formattedPlayer,
        minute: ev.minute,
        type: ev.type,
      })
    }
  }

  const eventRows: {
    home?: { player: string; minute: string }
    away?: { player: string; minute: string }
    middleType: string
  }[] = []

  // Pair up goals
  const goalRowsCount = Math.max(homeGoals.length, awayGoals.length)
  for (let i = 0; i < goalRowsCount; i++) {
    eventRows.push({
      home: homeGoals[i],
      away: awayGoals[i],
      middleType: 'goal',
    })
  }

  // Append disciplinary cards and substitutions with their dedicated icons
  for (const ev of otherEvents) {
    if (ev.team === 'home') {
      eventRows.push({
        home: { player: ev.player, minute: ev.minute },
        middleType: ev.type,
      })
    } else {
      eventRows.push({
        away: { player: ev.player, minute: ev.minute },
        middleType: ev.type,
      })
    }
  }

  // Ensure active tab stays on 'events' if no valid stats exist
  const currentTab = hasValidStats ? activeTab : 'events'

  return (
    <div
      className="my-3 w-full max-w-[420px] rounded-2xl border border-white/[0.08] bg-[#1e2025] p-3.5 sm:p-5 shadow-xl font-sans select-none transition-all duration-200"
      style={{
        boxShadow: '0 8px 30px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
      }}
    >
      {/* ── TOP SCOREBOARD HEADER ────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-2 sm:gap-3">
        {/* Home Team */}
        <div className="flex flex-col items-center flex-1 min-w-0">
          <div className="w-12 h-12 sm:w-16 sm:h-16 rounded-2xl bg-[#282b33]/90 border border-white/[0.08] flex items-center justify-center p-2 sm:p-2.5 shadow-inner overflow-hidden relative group">
            {finalHomeLogo ? (
              <img
                src={finalHomeLogo}
                alt={home_team}
                onError={() => setHomeImgError(true)}
                className="w-full h-full object-contain filter drop-shadow-md transition-transform duration-200 group-hover:scale-105"
              />
            ) : (
              <div
                className="w-full h-full rounded-xl flex items-center justify-center font-bold text-xs sm:text-sm tracking-wider shadow-sm"
                style={{ backgroundColor: homeInfo.bg, color: homeInfo.text }}
              >
                {homeInfo.short}
              </div>
            )}
          </div>
          <span className="text-[11px] sm:text-[13px] font-semibold text-[#e2e5eb] mt-1.5 sm:mt-2 text-center line-clamp-2 max-w-[85px] sm:max-w-[105px] leading-tight">
            {home_team}
          </span>
        </div>

        {/* Score & Match Status Center */}
        <div className="flex items-center justify-center gap-1.5 sm:gap-3 flex-shrink-0">
          {/* Home Score */}
          <span className="text-2xl sm:text-4xl font-extrabold font-mono text-white tracking-tight tabular-nums">
            {home_score}
          </span>

          {/* Center Column: Status Pill & Competition */}
          <div className="flex flex-col items-center mx-1 sm:mx-1.5">
            <div className="inline-flex items-center gap-1.5 px-2 sm:px-2.5 py-0.5 rounded-full bg-[#2a2d35] border border-white/[0.08] shadow-sm">
              {isLive && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              )}
              <span className="text-[10px] sm:text-xs font-mono font-medium text-[#cbd0dc] whitespace-nowrap">
                {status}
              </span>
            </div>
            <span className="text-[10px] sm:text-[12px] font-medium text-[#8c92a0] mt-1 sm:mt-1.5 whitespace-nowrap tracking-wide">
              {competition}
            </span>
          </div>

          {/* Away Score */}
          <span className="text-2xl sm:text-4xl font-extrabold font-mono text-white tracking-tight tabular-nums">
            {away_score}
          </span>
        </div>

        {/* Away Team */}
        <div className="flex flex-col items-center flex-1 min-w-0">
          <div className="w-12 h-12 sm:w-16 sm:h-16 rounded-2xl bg-[#282b33]/90 border border-white/[0.08] flex items-center justify-center p-2 sm:p-2.5 shadow-inner overflow-hidden relative group">
            {finalAwayLogo ? (
              <img
                src={finalAwayLogo}
                alt={away_team}
                onError={() => setAwayImgError(true)}
                className="w-full h-full object-contain filter drop-shadow-md transition-transform duration-200 group-hover:scale-105"
              />
            ) : (
              <div
                className="w-full h-full rounded-xl flex items-center justify-center font-bold text-xs sm:text-sm tracking-wider shadow-sm"
                style={{ backgroundColor: awayInfo.bg, color: awayInfo.text }}
              >
                {awayInfo.short}
              </div>
            )}
          </div>
          <span className="text-[11px] sm:text-[13px] font-semibold text-[#e2e5eb] mt-1.5 sm:mt-2 text-center line-clamp-2 max-w-[85px] sm:max-w-[105px] leading-tight">
            {away_team}
          </span>
        </div>
      </div>

      {/* ── OPTIONAL TAB SWITCHER (Events vs Stats) ───────────────────────── */}
      {hasValidStats && eventRows.length > 0 && (
        <div className="mt-3 sm:mt-3.5 flex items-center justify-center">
          <div className="inline-flex rounded-lg bg-[#14161a] p-0.5 border border-white/[0.06]">
            <button
              onClick={() => setActiveTab('events')}
              className={`min-h-[30px] sm:min-h-[34px] px-3 py-1 rounded-md text-[11px] font-medium transition-all ${
                currentTab === 'events'
                  ? 'bg-[#282b33] text-white shadow-sm'
                  : 'text-[#8c92a0] hover:text-white/80'
              }`}
            >
              Events
            </button>
            <button
              onClick={() => setActiveTab('stats')}
              className={`min-h-[30px] sm:min-h-[34px] px-3 py-1 rounded-md text-[11px] font-medium transition-all ${
                currentTab === 'stats'
                  ? 'bg-[#282b33] text-white shadow-sm'
                  : 'text-[#8c92a0] hover:text-white/80'
              }`}
            >
              Match Stats
            </button>
          </div>
        </div>
      )}

      {/* ── MATCH EVENTS INSET CONTAINER ─────────────────────────────────── */}
      {currentTab === 'events' && eventRows.length > 0 && (
        <div className="mt-3 sm:mt-3.5 rounded-xl bg-[#14161a]/95 border border-white/[0.06] overflow-hidden divide-y divide-white/[0.04]">
          {eventRows.map((row, idx) => {
            const middleType = row.middleType || 'goal'

            return (
              <div
                key={idx}
                className="grid grid-cols-12 items-center px-3 sm:px-4 py-2 sm:py-2.5 hover:bg-white/[0.02] transition-colors"
              >
                {/* Home Event Description */}
                <div className="col-span-5 flex items-center justify-start gap-1 sm:gap-1.5 min-w-0">
                  {row.home ? (
                    <>
                      <span className="truncate text-[#d2d6df] font-semibold text-[11px] sm:text-xs" title={row.home.player}>
                        {row.home.player}
                      </span>
                      <span className="shrink-0 text-[#8c92a0] text-[10px] sm:text-[11px] font-mono whitespace-nowrap">
                        {row.home.minute}
                      </span>
                    </>
                  ) : null}
                </div>

                {/* Central Event Icon */}
                <div className="col-span-2 flex items-center justify-center shrink-0">
                  {middleType === 'goal' || middleType === 'penalty' || middleType === 'own_goal' ? (
                    <span className="text-sm select-none" title="Goal">
                      ⚽
                    </span>
                  ) : middleType === 'yellow_card' ? (
                    <span
                      className="w-2.5 h-3.5 rounded-[2px] bg-[#eab308] inline-block shadow-sm ring-1 ring-yellow-300/30"
                      title="Yellow Card"
                    />
                  ) : middleType === 'red_card' ? (
                    <span
                      className="w-2.5 h-3.5 rounded-[2px] bg-[#ef4444] inline-block shadow-sm ring-1 ring-red-400/30"
                      title="Red Card"
                    />
                  ) : middleType === 'substitution' ? (
                    <span className="text-xs text-emerald-400" title="Substitution">
                      🔄
                    </span>
                  ) : (
                    <span className="text-xs text-white/50">•</span>
                  )}
                </div>

                {/* Away Event Description */}
                <div className="col-span-5 flex items-center justify-end gap-1 sm:gap-1.5 min-w-0 text-right">
                  {row.away ? (
                    <>
                      <span className="truncate text-[#d2d6df] font-semibold text-[11px] sm:text-xs" title={row.away.player}>
                        {row.away.player}
                      </span>
                      <span className="shrink-0 text-[#8c92a0] text-[10px] sm:text-[11px] font-mono whitespace-nowrap">
                        {row.away.minute}
                      </span>
                    </>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── MATCH STATS INSET CONTAINER ──────────────────────────────────── */}
      {currentTab === 'stats' && hasValidStats && stats && (
        <div className="mt-3.5 rounded-xl bg-[#14161a]/95 border border-white/[0.06] p-3.5 space-y-3">
          {/* Possession Bar */}
          {stats.possession && (Number(stats.possession[0]) > 0 || Number(stats.possession[1]) > 0) && (() => {
            const h = Number(stats.possession[0]) || 0
            const a = Number(stats.possession[1]) || 0
            const total = (h + a) > 0 ? (h + a) : 100
            const hPct = Math.round((h / total) * 100)
            const aPct = 100 - hPct
            return (
              <div>
                <div className="flex justify-between text-xs font-semibold text-[#cbd0dc] mb-1">
                  <span>{hPct}%</span>
                  <span className="text-[11px] text-[#8c92a0] font-normal uppercase tracking-wider">Ball Possession</span>
                  <span>{aPct}%</span>
                </div>
                <div className="h-1.5 w-full bg-white/[0.08] rounded-full overflow-hidden flex">
                  <div
                    className="h-full bg-emerald-500 transition-all duration-500"
                    style={{ width: `${hPct}%` }}
                  />
                  <div
                    className="h-full bg-amber-500 transition-all duration-500"
                    style={{ width: `${aPct}%` }}
                  />
                </div>
              </div>
            )
          })()}

          {/* Shots */}
          {stats.shots && (Number(stats.shots[0]) > 0 || Number(stats.shots[1]) > 0) && (
            <div className="flex justify-between text-xs text-[#a0a6b2] pt-1">
              <span className="font-semibold text-white font-mono">{stats.shots[0]}</span>
              <span className="text-[11px] text-[#8c92a0]">Total Shots</span>
              <span className="font-semibold text-white font-mono">{stats.shots[1]}</span>
            </div>
          )}

          {/* Shots on Target */}
          {stats.shots_on_target && (Number(stats.shots_on_target[0]) > 0 || Number(stats.shots_on_target[1]) > 0) && (
            <div className="flex justify-between text-xs text-[#a0a6b2]">
              <span className="font-semibold text-white font-mono">{stats.shots_on_target[0]}</span>
              <span className="text-[11px] text-[#8c92a0]">Shots on Target</span>
              <span className="font-semibold text-white font-mono">{stats.shots_on_target[1]}</span>
            </div>
          )}

          {/* Corners */}
          {stats.corners && (Number(stats.corners[0]) > 0 || Number(stats.corners[1]) > 0) && (
            <div className="flex justify-between text-xs text-[#a0a6b2]">
              <span className="font-semibold text-white font-mono">{stats.corners[0]}</span>
              <span className="text-[11px] text-[#8c92a0]">Corner Kicks</span>
              <span className="font-semibold text-white font-mono">{stats.corners[1]}</span>
            </div>
          )}

          {/* Fouls */}
          {stats.fouls && (Number(stats.fouls[0]) > 0 || Number(stats.fouls[1]) > 0) && (
            <div className="flex justify-between text-xs text-[#a0a6b2]">
              <span className="font-semibold text-white font-mono">{stats.fouls[0]}</span>
              <span className="text-[11px] text-[#8c92a0]">Fouls</span>
              <span className="font-semibold text-white font-mono">{stats.fouls[1]}</span>
            </div>
          )}
        </div>
      )}

      {/* ── SUMMARY FOOTER NOTE ─────────────────────────────────────────── */}
      {summary && (
        <p className="text-[11px] text-[#8c92a0] text-center mt-3 italic leading-relaxed px-1">
          {summary}
        </p>
      )}
    </div>
  )
}
export default SportsMatchCard

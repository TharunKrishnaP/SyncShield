import React, { useEffect, useState } from 'react'
import { Waves, ArrowUpRight, ArrowDownRight, Satellite, TrendingUp } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import Sparkline from './Sparkline.jsx'

const STATUS_STYLE = {
  EXTREME: { chip: 'bg-red-500/20 text-red-300 border-red-500/40', bar: '#ef4444', label: 'Danger' },
  SEVERE: { chip: 'bg-orange-500/20 text-orange-300 border-orange-500/40', bar: '#f97316', label: 'Warning' },
  ABOVE_NORMAL: { chip: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40', bar: '#eab308', label: 'Watch' },
  NORMAL: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', bar: '#22c55e', label: 'Normal' },
}

const RELEVANCE_STYLE = [
  { min: 7.5, chip: 'bg-red-500/15 text-red-300 border-red-500/40', label: 'Critical' },
  { min: 4.5, chip: 'bg-orange-500/15 text-orange-300 border-orange-500/30', label: 'High' },
  { min: 2.0, chip: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/25', label: 'Moderate' },
  { min: 0, chip: 'bg-slate-600/20 text-slate-400 border-slate-600/30', label: 'Low' },
]

function RelevanceBadge({ score }) {
  if (typeof score !== 'number') return null
  const s = RELEVANCE_STYLE.find((x) => score >= x.min) || RELEVANCE_STYLE[RELEVANCE_STYLE.length - 1]
  return (
    <span title={`Flood relevance ${score.toFixed(1)}/10 (severity + rate of rise + live flow)`} className={`text-[8px] px-1 py-0.5 rounded border font-bold ${s.chip}`}>
      {s.label} · {score.toFixed(1)}
    </span>
  )
}

export default function WaterLevelPanel() {
  const { waterLevels, api, updatedAt } = useApp()
  const [showAll, setShowAll] = useState(false)
  const [trends, setTrends] = useState({})

  const critical = (waterLevels || []).filter((s) => s.status === 'SEVERE' || s.status === 'EXTREME')
  const shown = showAll ? waterLevels || [] : (critical.length ? critical : (waterLevels || []).slice(0, 8))

  const ids = (shown || []).map((s) => s.station_id).filter(Boolean)
  useEffect(() => {
    if (!ids.length) return
    let live = true
    api
      .waterHistory(ids, 24)
      .then((res) => {
        if (!live) return
        const out = {}
        for (const [sid, pts] of Object.entries(res.series || {})) {
          out[sid] = (pts || []).map((p) => p.water_level)
        }
        setTrends(out)
      })
      .catch(() => {})
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [updatedAt, ids.join('|')])

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="flex items-center justify-between px-3 py-2 border-b border-eoc-border">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Waves size={12} className="text-sky-400" /> River Water Levels
        </h3>
        <span className="text-[9px] text-slate-500">{(waterLevels || []).length} CWC stations</span>
      </div>

      <div className="p-2 space-y-1.5">
        {shown.length === 0 && (
          <p className="text-[10px] text-slate-500 px-1 py-2">No river readings received yet.</p>
        )}
        {shown.map((s) => {
          const st = STATUS_STYLE[s.status] || STATUS_STYLE.NORMAL
          const dl = s.danger_level || 1
          const wl = s.warning_level || dl * 0.9
          const level = s.water_level || 0
          const pct = Math.min((level / (dl * 1.15)) * 100, 100)
          const warnPct = Math.min((wl / (dl * 1.15)) * 100, 100)
          const dangerPct = Math.min((dl / (dl * 1.15)) * 100, 100)
          const rising = (s.rate_of_rise || 0) > 0

          return (
            <div key={s.station_id} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[11px] font-bold text-slate-100 truncate">
                    {s.river}
                    <span className="font-normal text-slate-500"> · {s.state}</span>
                  </div>
                  <div className="text-[9px] text-slate-500 truncate">{s.station_id} · {s.basin} basin</div>
                </div>
                <div className="flex flex-col items-end shrink-0">
                  <div className="flex items-center gap-1">
                    <RelevanceBadge score={s.flood_relevance} />
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold ${st.chip}`}>
                      {st.label}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-300 mt-0.5">{level} m</span>
                </div>
              </div>

              <div className="relative h-1.5 mt-1.5 rounded-full bg-slate-700/60 overflow-hidden">
                <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${pct}%`, background: st.bar }} />
                <div className="absolute top-[-2px] bottom-[-2px] w-px bg-yellow-400/70" style={{ left: `${warnPct}%` }} />
                <div className="absolute top-[-2px] bottom-[-2px] w-px bg-red-500" style={{ left: `${dangerPct}%` }} />
              </div>

              <div className="flex items-center justify-between mt-1.5">
                <div className="flex items-center gap-1 text-[9px] text-slate-500">
                  <TrendingUp size={9} className="text-slate-500" />
                  24h trend
                  {trends[s.station_id] ? (
                    <Sparkline values={trends[s.station_id]} width={84} height={18} stroke={st.bar} />
                  ) : (
                    <span className="italic">building…</span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-[9px] text-slate-500 shrink-0">
                  <span>
                    warn {wl}m · danger {dl}m
                  </span>
                  {s.discharge ? (
                    <span className="flex items-center gap-0.5 text-sky-300">
                      <Satellite size={9} /> {Math.round(s.discharge)} m³/s
                      {s.flow_ratio ? ` (${s.flow_ratio}× normal)` : ''}
                    </span>
                  ) : (
                    <span>{s.flow_plain}</span>
                  )}
                  {s.rate_of_rise !== undefined && (
                    <span className={rising ? 'text-orange-400 flex items-center' : 'text-slate-500 flex items-center'}>
                      {rising ? <ArrowUpRight size={9} /> : <ArrowDownRight size={9} />}
                      {Math.abs(s.rate_of_rise)} cm/h
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {(waterLevels || []).length > 8 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="w-full text-[10px] text-sky-400 hover:text-sky-300 py-1.5 border-t border-eoc-border"
        >
          {showAll ? 'Show only rivers at risk' : `Show all ${waterLevels.length} stations`}
        </button>
      )}
    </div>
  )
}

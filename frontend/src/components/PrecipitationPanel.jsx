import React, { useEffect, useState } from 'react'
import { CloudRain, Wind, TrendingUp } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import Sparkline from './Sparkline.jsx'

const CATEGORY_STYLE = {
  'Extremely heavy': 'bg-red-500/20 text-red-300 border-red-500/40',
  'Very heavy': 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  Heavy: 'bg-orange-500/15 text-orange-200 border-orange-500/30',
  'Rather heavy': 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  Moderate: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  Light: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
  'No rain': 'bg-slate-600/20 text-slate-400 border-slate-600/30',
}

const RELEVANCE_STYLE = [
  { min: 4.5, chip: 'bg-red-500/15 text-red-300 border-red-500/40', label: 'Flood-prone' },
  { min: 2.0, chip: 'bg-orange-500/10 text-orange-300 border-orange-500/25', label: 'Watch' },
  { min: 0, chip: 'bg-slate-600/20 text-slate-400 border-slate-600/30', label: 'Ok' },
]

export default function PrecipitationPanel() {
  const { precipitation, api, updatedAt } = useApp()
  const [showAll, setShowAll] = useState(false)
  const [trends, setTrends] = useState({})
  const rows = precipitation || []
  const wet = rows.filter((r) => r.next_24h_mm > 0.5 || r.rain_now_mm > 0.5)
  const shown = showAll ? rows : (wet.length ? wet : rows).slice(0, 8)

  const ids = (shown || []).map((r) => r.zone_id).filter(Boolean)
  useEffect(() => {
    if (!ids.length) return
    let live = true
    api
      .precipHistory(ids, 24)
      .then((res) => {
        if (!live) return
        const out = {}
        for (const [zid, pts] of Object.entries(res.series || {})) {
          out[zid] = (pts || []).map((p) => p.rain_now_mm ?? p.next_6h_mm ?? 0)
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
          <CloudRain size={12} className="text-cyan-400" /> Rainfall Records
        </h3>
        <span className="text-[9px] text-slate-500">{rows.length} districts</span>
      </div>

      <div className="p-2 space-y-1.5">
        {shown.length === 0 && (
          <p className="text-[10px] text-slate-500 px-1 py-2">No rainfall readings received yet.</p>
        )}
        {shown.map((r) => (
          <div key={r.zone_id} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[11px] font-bold text-slate-100 truncate">
                  {r.name}
                  <span className="font-normal text-slate-500"> · {r.state}</span>
                </div>
                <div className="text-[9px] text-slate-500">
                  now <span className="text-slate-300 font-semibold">{r.rain_now_mm} mm</span> · next 6h{' '}
                  <span className="text-slate-300">{r.next_6h_mm} mm</span>
                </div>
              </div>
              <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold shrink-0 ${CATEGORY_STYLE[r.category] || CATEGORY_STYLE['No rain']}`}>
                {r.category}
              </span>
              {(typeof r.flood_relevance === 'number' && r.flood_relevance >= 2.0) && (
                <span title={`Flood relevance ${r.flood_relevance.toFixed(1)}/10 (rain × district flood risk × forecast)`} className={`shrink-0 text-[8px] px-1 py-0.5 rounded border font-bold ${RELEVANCE_STYLE.find((x) => r.flood_relevance >= x.min)?.chip || RELEVANCE_STYLE[RELEVANCE_STYLE.length - 1].chip}`}>
                  {RELEVANCE_STYLE.find((x) => r.flood_relevance >= x.min)?.label}
                </span>
              )}
            </div>
            <div className="flex items-center justify-between mt-1">
              <div className="flex items-center gap-1 text-[9px] text-slate-500">
                <TrendingUp size={9} className="text-slate-500" />
                24h
                {trends[r.zone_id] ? (
                  <Sparkline values={trends[r.zone_id]} width={84} height={18} stroke="#22d3ee" />
                ) : (
                  <span className="italic">building…</span>
                )}
              </div>
              <div className="flex items-center gap-2 text-[9px] text-slate-500">
                <span>24h <b className="text-slate-300">{r.next_24h_mm} mm</b></span>
                <span>{Math.round(r.probability_pct || 0)}%</span>
                {r.wind_kmph !== undefined && (
                  <span className="flex items-center gap-0.5">
                    <Wind size={9} /> {Math.round(r.wind_kmph)} km/h
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {rows.length > 8 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="w-full text-[10px] text-sky-400 hover:text-sky-300 py-1.5 border-t border-eoc-border"
        >
          {showAll ? 'Show only rainy districts' : `Show all ${rows.length} districts`}
        </button>
      )}
    </div>
  )
}

import React from 'react'
import { TrendingUp } from 'lucide-react'

function barColor(score) {
  if (score > 80) return 'bg-red-500'
  if (score > 60) return 'bg-orange-500'
  if (score > 40) return 'bg-yellow-500'
  if (score > 20) return 'bg-green-500'
  return 'bg-sky-500'
}

export default function RegionBars({ zones }) {
  return (
    <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
        <TrendingUp size={12} /> Regional Zone Scores
      </h3>
      <div className="space-y-1.5">
        {zones.map((z) => (
          <div key={z.zone_id} className="flex items-center gap-2 text-[10px]">
            <span className="w-20 truncate text-slate-300" title={z.zone_name}>
              {z.zone_name}
            </span>
            <span className="text-slate-500 w-8 truncate">{z.district}</span>
            <div className="flex-1 h-2 bg-slate-800 rounded-sm overflow-hidden">
              <div
                className={`h-full ${barColor(z.overall_score)}`}
                style={{ width: `${z.overall_score}%`, transition: 'width 0.5s ease' }}
              />
            </div>
            <span
              className={`font-mono font-semibold ${
                z.overall_score > 60 ? 'text-red-400' : z.overall_score > 40 ? 'text-yellow-400' : 'text-green-400'
              }`}
            >
              {z.overall_score}
            </span>
          </div>
        ))}
        {zones.length === 0 && <p className="text-[10px] text-slate-500 text-center py-2">No zone data</p>}
      </div>
    </div>
  )
}
import React from 'react'
import { AlertTriangle, ShieldAlert, Waves, CloudRain } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const TYPE_ICONS = {
  SATELLITE_NO_RAIN: Waves,
  RAIN_NO_RIVER_RISE: CloudRain,
  RIVER_HIGH_SATELLITE_DRY: Waves,
  MODALITY_DIVERGENCE: ShieldAlert,
}

export default function ConflictCard() {
  const { conflicts } = useApp()
  if (!conflicts || conflicts.length === 0) {
    return (
      <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3 opacity-60">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-1">
          <AlertTriangle size={12} /> Data Conflict Monitor
        </h3>
        <p className="text-[11px] text-green-400">✓ No cross-modal conflicts detected.</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5 mb-2">
        <AlertTriangle size={12} /> Data Conflict Warnings ({conflicts.length})
      </h3>
      <div className="space-y-2">
        {conflicts.map((c) => {
          const Icon = TYPE_ICONS[c.conflict_type] || AlertTriangle
          return (
            <div key={c.id} className="rounded-lg bg-slate-900/60 border border-amber-500/20 p-2.5">
              <div className="flex items-start gap-2">
                <Icon size={14} className="text-amber-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-[11px] font-semibold text-amber-300">{c.conflict_type.replace(/_/g, ' ')}</p>
                  <p className="text-[10px] text-slate-300 mt-0.5">{c.description}</p>
                  <p className="text-[9px] text-slate-500 mt-1">
                    {c.modality_a} vs {c.modality_b} · penalty {c.confidence_penalty}
                  </p>
                  <p className="text-[9px] text-sky-300 mt-1">{c.diagnosis}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
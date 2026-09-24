import React, { useState } from 'react'
import { ShieldAlert, Target, CloudRain, CheckCircle, Database, ChevronDown, ChevronUp } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const CAT_ICON = {
  TACTICAL_DEPLOYMENT: ShieldAlert,
  MEDICAL_STAGING: Target,
  EVACUATION: Target,
  EARLY_WARNING: CloudRain,
  DATA_QUALITY: Database,
}
const PRI_COLOR = {
  1: 'text-red-400 bg-red-500/10 border-red-500/30',
  2: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
  3: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  4: 'text-slate-400 bg-slate-500/10 border-slate-500/30',
}
const PRI_LABEL = { 1: 'CRITICAL', 2: 'HIGH', 3: 'MONITOR', 4: 'LOW' }

export default function RecommendationList() {
  const { recommendations } = useApp()
  const recs = recommendations || []
  const [expanded, setExpanded] = useState({})
  const toggle = (id) => setExpanded((s) => ({ ...s, [id]: !s[id] }))

  return (
    <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
        <Target size={12} /> AI Response Recommendations ({recs.length})
      </h3>
      <div className="space-y-2">
        {recs.slice(0, 15).map((r) => {
          const Icon = CAT_ICON[r.category] || ShieldAlert
          const isExpanded = !!expanded[r.id]
          return (
            <div
              key={r.id}
              className={`rounded-lg border p-2.5 cursor-pointer transition-colors hover:bg-slate-800/40 ${PRI_COLOR[r.priority] || PRI_COLOR[4]}`}
              onClick={() => toggle(r.id)}
            >
              <div className="flex items-start gap-2">
                <Icon size={14} className="mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold rounded px-1 py-0.5 bg-slate-900/40">
                      P{r.priority} · {PRI_LABEL[r.priority]}
                    </span>
                    <span className="text-[9px] text-slate-500">{r.category.replace(/_/g, ' ')}</span>
                  </div>
                  <p className="text-[11px] font-semibold mt-1 leading-snug">{r.title}</p>
                </div>
                {isExpanded ? <ChevronUp size={12} className="text-slate-500 mt-1" /> : <ChevronDown size={12} className="text-slate-500 mt-1" />}
              </div>
              {isExpanded && (
                <div className="mt-2 ml-5 space-y-1">
                  <p className="text-[10px] text-slate-300 leading-relaxed">{r.description}</p>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {r.affected_zones?.map((z) => (
                      <span key={z} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-900/40 text-slate-300">{z}</span>
                    ))}
                  </div>
                  <p className="text-[9px] text-slate-500">
                    {r.responsible_agency} · Confidence {(r.confidence * 100).toFixed(0)}%
                  </p>
                  {Object.keys(r.estimated_resources || {}).length > 0 && (
                    <div className="text-[9px] text-slate-400 flex gap-2 flex-wrap">
                      {Object.entries(r.estimated_resources).map(([k, v]) => (
                        <span key={k} className="bg-slate-900/30 px-1.5 py-0.5 rounded">
                          {k}: {v}
                        </span>
                      ))}
                    </div>
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
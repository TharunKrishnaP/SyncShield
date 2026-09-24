import React, { useMemo } from 'react'
import { BrainCircuit } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

export default function ExplanationCard() {
  const { priorities, explanations, zones } = useApp()
  const top = priorities?.[0]
  const expl = top ? explanations?.[top.zone_id] : null
  const zoneScore = top ? zones?.[top.zone_id] : null

  const evidence = useMemo(() => {
    if (!expl) return []
    return [...(expl.evidence_points || [])].sort((a, b) => b.contribution_pct - a.contribution_pct)
  }, [expl])

  if (!expl) {
    return (
      <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-1">
          <BrainCircuit size={12} /> Explainable AI
        </h3>
        <p className="text-[11px] text-slate-500">Select a zone on the map to inspect its evidence breakdown.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-3">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-sky-300 flex items-center gap-1.5 mb-2">
        <BrainCircuit size={12} /> Why is {expl.zone_name} Critical?
      </h3>
      <p className="text-[11px] text-slate-300 leading-snug mb-2">{expl.natural_language_summary}</p>

      {evidence.map((e) => (
        <div key={e.factor} className="mb-2">
          <div className="flex items-center justify-between text-[10px] mb-0.5">
            <span className="text-slate-300 font-medium">{e.factor}</span>
            <span className="text-slate-400 font-mono">{e.contribution_pct}%</span>
          </div>
          <div className="h-1.5 bg-slate-800 rounded-sm overflow-hidden">
            <div
              className={`h-full ${e.contribution_pct >= 40 ? 'bg-red-500' : e.contribution_pct >= 20 ? 'bg-amber-500' : 'bg-sky-500'}`}
              style={{ width: `${Math.min(e.contribution_pct, 100)}%`, transition: 'width .5s ease' }}
            />
          </div>
          <p className="text-[9px] text-slate-500 mt-0.5">{e.description}</p>
        </div>
      ))}

      {zoneScore && (
        <div className="mt-2 pt-2 border-t border-sky-500/20">
          <p className="text-[9px] text-slate-400">
            Severity: <b>{zoneScore.severity_level}</b> ({zoneScore.overall_score}/100) · Trend{' '}
            {zoneScore.trend > 0 ? `+${zoneScore.trend}` : zoneScore.trend} pts/hr
          </p>
        </div>
      )}
    </div>
  )
}
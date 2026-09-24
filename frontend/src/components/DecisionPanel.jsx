import React from 'react'
import { LifeBuoy, ShieldCheck, Route, Radio } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import RecommendationList from './RecommendationList.jsx'
import ExplanationCard from './ExplanationCard.jsx'
import RouteEvaluator from './RouteEvaluator.jsx'
import IncidentFeed from './IncidentFeed.jsx'

export default function DecisionPanel() {
  const { priorities } = useApp()
  const topPriority = priorities?.[0]

  return (
    <aside className="w-[360px] flex flex-col border-l border-eoc-border bg-eoc-panel/70 min-h-0">
      <div className="px-4 py-3 border-b border-eoc-border shrink-0 flex items-center justify-between">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <LifeBuoy size={14} /> Emergency Decision Support
        </h2>
        {topPriority && (
          <span className="text-[9px] px-2 py-0.5 rounded bg-red-500/15 text-red-400 font-bold">
            TOP: {topPriority.zone_name}
          </span>
        )}
      </div>
      <div className="overflow-y-auto flex-1 min-h-0 flex flex-col gap-3 p-3">
        <RecommendationList />
        <ExplanationCard />
        <RouteEvaluator />
        <IncidentFeed />
      </div>
    </aside>
  )
}
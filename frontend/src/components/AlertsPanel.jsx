import React from 'react'
import { Siren, ShieldCheck, ExternalLink } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const LEVEL = {
  Red: 'bg-red-500/20 text-red-300 border-red-500/40',
  Orange: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  Green: 'bg-green-500/15 text-green-300 border-green-500/30',
}

export default function AlertsPanel() {
  const { alerts } = useApp()
  const list = alerts || []

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="flex items-center justify-between px-3 py-2 border-b border-eoc-border">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Siren size={12} className="text-red-400" /> Official Flood Alerts
        </h3>
        <span className="text-[9px] text-slate-500">{list.length} verified</span>
      </div>
      <div className="p-2 space-y-1.5">
        {list.length === 0 && (
          <p className="text-[10px] text-slate-500 px-1 py-2 flex items-center gap-1.5">
            <ShieldCheck size={11} className="text-green-500" /> No active official flood alerts for India.
          </p>
        )}
        {list.slice(0, 8).map((a) => {
          const chip = LEVEL[a.alert_level] || LEVEL.Green
          return (
            <div key={a.id} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="flex items-start justify-between gap-2">
                <span className="text-[11px] font-semibold text-slate-100 leading-snug">{a.title}</span>
                <span className={`text-[8px] px-1 py-0.5 rounded border font-bold shrink-0 ${chip}`}>
                  {a.alert_level}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1 text-[9px] text-slate-500">
                <span className="text-slate-400">{a.source_full || a.source}</span>
                {a.from_date && <span>{String(a.from_date).slice(0, 10)}</span>}
                {a.url && (
                  <a href={a.url} target="_blank" rel="noreferrer" className="ml-auto text-sky-400 hover:text-sky-300 flex items-center gap-0.5">
                    Details <ExternalLink size={9} />
                  </a>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

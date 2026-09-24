import React from 'react'
import { History, Radio, Snowflake, AlertOctagon, RotateCcw } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const TYPE_STYLE = {
  PLAY: { color: 'text-sky-400', bg: 'bg-sky-500/10' },
  PAUSE: { color: 'text-slate-400', bg: 'bg-slate-500/10' },
  SURGE: { color: 'text-red-400', bg: 'bg-red-500/10' },
  RESET: { color: 'text-slate-400', bg: 'bg-slate-500/10' },
  INCIDENT: { color: 'text-amber-400', bg: 'bg-amber-500/10' },
  SYSTEM: { color: 'text-green-400', bg: 'bg-green-500/10' },
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString('en-IN', { hour12: false })
}

export default function TimelineList() {
  const { timeline, simulation } = useApp()
  const events = timeline || []

  return (
    <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3 flex-1">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
        <History size={12} /> Situation Progression Timeline
        <span className="ml-auto text-sky-300">{simulation?.time_label || ''}</span>
      </h3>
      <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
        {events.length === 0 && (
          <p className="text-[10px] text-slate-500 text-center py-3">
            Event log is empty. Start the scenario player.
          </p>
        )}
        {events.map((evt, i) => {
          const st = TYPE_STYLE[evt.type] || TYPE_STYLE.SYSTEM
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="font-mono text-[9px] text-slate-500 pt-0.5 w-14 shrink-0">{fmtTime(evt.timestamp)}</span>
              <span className={`mt-0.5 px-1.5 py-0.5 rounded text-[8px] font-bold ${st.color} ${st.bg} shrink-0`}>
                {evt.type}
              </span>
              <p className="text-[11px] text-slate-300 leading-snug">{evt.message}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
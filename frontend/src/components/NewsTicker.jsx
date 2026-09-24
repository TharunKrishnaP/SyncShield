import React, { useState } from 'react'
import { Newspaper, ChevronDown, MapPin } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const SEV_COLOR = {
  LOW: 'text-slate-400 border-slate-500/40 bg-slate-500/10',
  MODERATE: 'text-sky-300 border-sky-500/40 bg-sky-500/10',
  HIGH: 'text-yellow-300 border-yellow-500/40 bg-yellow-500/10',
  VERY_HIGH: 'text-orange-300 border-orange-500/40 bg-orange-500/10',
  CRITICAL: 'text-red-300 border-red-500/40 bg-red-500/10',
}

const SEV_DOT = {
  LOW: 'bg-slate-400',
  MODERATE: 'bg-sky-400',
  HIGH: 'bg-yellow-400',
  VERY_HIGH: 'bg-orange-400',
  CRITICAL: 'bg-red-500',
}

function age(ts) {
  if (!ts) return ''
  const d = new Date(ts).getTime()
  if (Number.isNaN(d)) return ''
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000))
  if (s < 5) return 'now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function NewsTicker() {
  const { news } = useApp()
  const [open, setOpen] = useState(false)
  const items = news || []
  if (!items.length) return null

  const head = items[0]
  const sev = head.severity || 'MODERATE'
  const chip = SEV_COLOR[sev] || SEV_COLOR.MODERATE

  return (
    <div className="relative shrink-0 border-b border-eoc-border bg-eoc-panel/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-slate-800/30 transition-colors"
        title="Click for the latest updates"
      >
        <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-sky-400 shrink-0">
          <Newspaper size={12} /> Live
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500" />
          </span>
        </span>

        <span className={`flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-bold shrink-0 ${chip}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${SEV_DOT[sev] || SEV_DOT.MODERATE}`} />
          {head.label || head.type}
        </span>

        <span className="min-w-0 truncate text-[11px] text-slate-300">{head.headline}</span>
        <span className="text-[9px] text-slate-500 shrink-0 hidden sm:block">{age(head.published_at)}</span>
        <ChevronDown size={13} className={`ml-auto shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-[1900] max-h-[46vh] overflow-y-auto border-b border-eoc-border bg-eoc-panel shadow-2xl border-x">
          <div className="px-3 py-2 border-b border-eoc-border text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Real-time updates · {items.length} latest
          </div>
          <ul className="divide-y divide-eoc-border/60">
            {items.map((n, i) => {
              const c = SEV_COLOR[n.severity] || SEV_COLOR.MODERATE
              return (
                <li key={`${n.id}-${i}`} className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold shrink-0 ${c}`}>{n.type}</span>
                    <span className="text-[10px] text-slate-300 flex-1 min-w-0 truncate">{n.headline}</span>
                    <span className="text-[9px] text-slate-500 shrink-0">{age(n.published_at)}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-500">
                    <span className="flex items-center gap-0.5 min-w-0 truncate">
                      <MapPin size={9} className="shrink-0" /> {n.zone_name || 'India'}
                    </span>
                    <span className="shrink-0">{n.source}</span>
                  </div>
                  {n.body && <div className="mt-0.5 text-[10px] text-slate-400 leading-snug line-clamp-2">{n.body}</div>}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
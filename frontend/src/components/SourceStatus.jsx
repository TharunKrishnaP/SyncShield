import React, { useMemo, useState } from 'react'
import { Database, ExternalLink, CheckCircle2, ChevronDown, Clock } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

function ago(iso) {
  if (!iso) return '—'
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  return `${Math.round(secs / 3600)}h ago`
}

export default function SourceStatus() {
  const { sources } = useApp()
  const [showOffline, setShowOffline] = useState(false)
  const list = sources?.sources || []

  const { live, offline } = useMemo(() => {
    // Only genuinely real-time feeds are "streaming"; reference portals,
    // key-gated APIs and modelled estimates are listed as offline instead.
    const live = (list || []).filter((s) => s.status === 'LIVE' && s.realtime)
    const offline = (list || []).filter((s) => !(s.status === 'LIVE' && s.realtime))
    return { live, offline }
  }, [list])

  if (!list.length) return null

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="flex items-center justify-between px-3 py-2 border-b border-eoc-border">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Database size={12} className="text-emerald-400" /> Live Data Sources
        </h3>
        <span className="text-[9px] text-green-400 font-semibold">{live.length} streaming</span>
      </div>
      <div className="p-2 space-y-1.5">
        {live.length === 0 && (
          <p className="text-[10px] text-slate-500 px-1">No feeds are live right now — telemetry will reconnect automatically.</p>
        )}
        {live.map((s) => (
          <a
            key={s.key}
            href={s.url}
            target="_blank"
            rel="noreferrer"
            title={s.url}
            className="flex items-start gap-2 rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5 hover:border-sky-500/40 hover:bg-slate-900/80 transition-colors"
          >
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1 text-[10px] font-semibold text-sky-300 underline decoration-dotted underline-offset-2 truncate">
                {s.plain_name || s.name}
                <ExternalLink size={9} className="shrink-0" />
              </div>
              {s.what_it_gives && (
                <div className="text-[9px] text-slate-500 leading-snug mt-0.5 line-clamp-2">{s.what_it_gives}</div>
              )}
              <div className="flex items-center gap-2 text-[9px] text-slate-500 mt-0.5">
                {s.is_indian_govt && <span className="text-orange-400/80 font-semibold">Govt of India</span>}
                {s.records > 0 && <span>{s.records} records</span>}
                {s.latency_ms != null && <span>{Math.round(s.latency_ms)} ms</span>}
                <span className="ml-auto flex items-center gap-1">
                  <Clock size={8} /> {ago(s.last_success)}
                </span>
              </div>
            </div>
          </a>
        ))}

        {offline.length > 0 && (
          <button
            onClick={() => setShowOffline((v) => !v)}
            className="w-full flex items-center justify-center gap-1 text-[9px] text-slate-500 hover:text-slate-300 py-1"
          >
            <ChevronDown size={10} className={`transition-transform ${showOffline ? 'rotate-180' : ''}`} />
            {offline.length} more sources are offline / require govt login
          </button>
        )}
        {showOffline && (
          <div className="space-y-1 pt-0.5">
            {offline.map((s) => (
              <div key={s.key} className="flex items-center gap-2 px-2 py-1 text-[9px] text-slate-600">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-600 shrink-0" />
                <span className="truncate">{s.plain_name || s.name}</span>
                <span className="ml-auto shrink-0">{s.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
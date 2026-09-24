import React from 'react'
import {
  Activity,
  Wifi,
  WifiOff,
  Play,
  Pause,
  SkipForward,
  Zap,
  RotateCcw,
  Clock,
  Satellite,
  RefreshCw,
} from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import { useNow, ageSeconds } from '../hooks/useNow.js'

export default function Header() {
  const { regional, simulation, connection, api, updatedAt, refreshIntervalSeconds } = useApp()
  const now = useNow(1000)
  const score = regional?.score ?? 0
  const status = regional?.status ?? 'NORMAL'
  const running = simulation?.running ?? false

  const ist = new Date(now).toLocaleTimeString('en-IN', { hour12: false })
  const updated = updatedAt ? new Date(updatedAt).toLocaleTimeString('en-IN', { hour12: false }) : '—'
  const interval = refreshIntervalSeconds || 60
  const age = ageSeconds(now, updatedAt)

  let fresh = 'connecting'
  if (age !== null) {
    fresh = age <= interval * 1.5 ? 'live' : age <= interval * 8 ? 'delayed' : 'stale'
  }
  const freshness = {
    live: { chip: 'bg-green-500/10 text-green-300 border-green-500/30', dot: 'bg-green-400', label: 'LIVE' },
    delayed: { chip: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30', dot: 'bg-yellow-400', label: 'DELAYED' },
    stale: { chip: 'bg-red-500/10 text-red-300 border-red-500/30', dot: 'bg-red-500', label: 'STALE' },
    connecting: { chip: 'bg-slate-700/20 text-slate-300 border-slate-600/40', dot: 'bg-slate-500', label: 'CONNECTING' },
  }[fresh]

  const nextIn = age === null ? null : Math.max(0, interval - (age % interval))

  const statusColor = {
    LOW: 'text-green-400',
    MODERATE: 'text-yellow-400',
    HIGH: 'text-orange-400',
    VERY_HIGH: 'text-red-400',
    CRITICAL: 'text-red-500',
  }[status] ?? 'text-slate-300'

  const act = async (action) => {
    try {
      await api.simulationStep(action)
    } catch (err) {
      console.error(err)
    }
  }

  const SimBtn = ({ action, icon: Icon, title, className = '' }) => (
    <button
      onClick={() => act(action)}
      title={title}
      className={`p-1.5 rounded-md border border-eoc-border hover:bg-slate-700/40 transition-colors ${className}`}
    >
      <Icon size={16} />
    </button>
  )

  return (
    <header className="flex items-center gap-3 px-4 py-2 bg-eoc-panel border-b border-eoc-border shrink-0">
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-sky-500/20 border border-sky-500/40 flex items-center justify-center shrink-0">
          <Satellite size={19} className="text-sky-400" />
        </div>
        <div className="min-w-0">
          <h1 className="text-sm font-bold leading-tight tracking-tight truncate">
            AI Multimodal Flood Disaster Response DataLake
          </h1>
          <p className="text-[10px] text-slate-400 leading-tight truncate">
            All-India Flood EOC · IMD · CWC · ISRO · NDMA · live satellite &amp; radar
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-900/60 border border-eoc-border shrink-0">
        <Clock size={14} className="text-slate-400" />
        <span className="font-mono text-xs tabular-nums">{ist} IST</span>
      </div>

      <div className={`flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-900/60 border border-eoc-border shrink-0`}>
        <Activity size={14} className={statusColor} />
        <span className="text-[11px] font-semibold">{status}</span>
        <span className={`font-mono text-sm font-extrabold tabular-nums ${statusColor}`}>{score}</span>
        <span className="text-[10px] text-slate-500">/ 100</span>
        {simulation?.time_label && (
          <span className="text-[10px] text-sky-300 bg-sky-500/10 px-1.5 py-0.5 rounded">
            {simulation.time_label}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5 ml-auto shrink-0">
        <span className="text-[10px] text-slate-500 mr-1">SCENARIO</span>
        <SimBtn action="toggle" icon={running ? Pause : Play} title={running ? 'Pause' : 'Play'} />
        <SimBtn action="next" icon={SkipForward} title="Step Next" />
        <SimBtn action="surge" icon={Zap} title="Surge Event" className="text-amber-400" />
        <SimBtn action="reset" icon={RotateCcw} title="Reset" />
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <span
          className={`flex items-center gap-1.5 text-[10px] border px-2 py-1 rounded font-semibold tabular-nums ${freshness.chip}`}
          title={`Data as of ${updated} · refresh every ${interval}s`}
        >
          <span className="relative flex w-2 h-2">
            <span className={`pulse-ring absolute w-full h-full rounded-full ${freshness.dot}`} />
            <span className={`w-2 h-2 rounded-full ${freshness.dot}`} />
          </span>
          {freshness.label}
          {age !== null && <span className="font-semibold">{age}s</span>}
          {nextIn !== null && fresh === 'live' && (
            <span className="text-[9px] text-slate-400">refresh {nextIn}s</span>
          )}
        </span>
        {connection === 'connected' ? (
          <Wifi size={13} className="text-green-400" />
        ) : connection === 'connecting' ? (
          <Wifi size={13} className="text-yellow-400" />
        ) : (
          <WifiOff size={13} className="text-red-400" />
        )}
      </div>
    </header>
  )
}
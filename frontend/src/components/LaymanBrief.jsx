import React from 'react'
import {
  ShieldCheck,
  AlertTriangle,
  Siren,
  Users,
  CloudRain,
  MapPin,
  Radio,
  RefreshCw,
} from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import { useNow, ageSeconds, fmtAge } from '../hooks/useNow.js'

const TRAFFIC = {
  green: { bg: 'bg-green-500/15', border: 'border-green-500/40', text: 'text-green-400', dot: 'bg-green-400', Icon: ShieldCheck },
  yellow: { bg: 'bg-yellow-500/15', border: 'border-yellow-500/40', text: 'text-yellow-400', dot: 'bg-yellow-400', Icon: AlertTriangle },
  orange: { bg: 'bg-orange-500/15', border: 'border-orange-500/40', text: 'text-orange-400', dot: 'bg-orange-400', Icon: AlertTriangle },
  red: { bg: 'bg-red-500/15', border: 'border-red-500/40', text: 'text-red-400', dot: 'bg-red-400', Icon: Siren },
}

const LEVEL_CHIP = {
  MODERATE: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  HIGH: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  VERY_HIGH: 'bg-red-500/15 text-red-300 border-red-500/30',
  CRITICAL: 'bg-red-600/20 text-red-200 border-red-500/50',
  LOW: 'bg-green-500/15 text-green-300 border-green-500/30',
}

export default function LaymanBrief() {
  const { brief, updatedAt } = useApp()
  const now = useNow(2000)
  if (!brief) {
    return (
      <div className="rounded-xl border border-eoc-border bg-eoc-panel/80 p-3 text-[11px] text-slate-400 flex items-center gap-2">
        <RefreshCw size={13} className="animate-spin" /> Connecting to live government feeds…
      </div>
    )
  }

  const t = TRAFFIC[brief.traffic_light] || TRAFFIC.green
  const Icon = t.Icon

  return (
    <div className={`rounded-xl border ${t.border} ${t.bg} p-3`}>
      <div className="flex items-start gap-2">
        <div className={`mt-0.5 ${t.text}`}>
          <Icon size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] font-extrabold uppercase tracking-wider ${t.text}`}>
              {brief.traffic_plain}
            </span>
            <span className={`w-2 h-2 rounded-full ${t.dot}`} />
            <span className="text-[10px] text-slate-400">{brief.level_plain}</span>
          </div>
          <p className="text-[13px] font-semibold leading-snug mt-1 text-slate-100">{brief.headline}</p>
          <p className="text-[11px] text-slate-300 leading-relaxed mt-1.5">{brief.what_it_means}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-1.5 mt-3">
        <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
          <div className="flex items-center gap-1 text-[9px] uppercase text-slate-500 font-bold">
            <Users size={10} /> At risk
          </div>
          <div className="text-[11px] font-bold text-slate-200 leading-tight">{brief.people_at_risk_text}</div>
        </div>
        <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
          <div className="flex items-center gap-1 text-[9px] uppercase text-slate-500 font-bold">
            <MapPin size={10} /> Areas
          </div>
          <div className="text-[11px] font-bold text-slate-200 leading-tight">
            {brief.areas_needing_help} need help
          </div>
        </div>
        <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
          <div className="flex items-center gap-1 text-[9px] uppercase text-slate-500 font-bold">
            <Radio size={10} /> Alerts
          </div>
          <div className="text-[11px] font-bold text-slate-200 leading-tight">
            {brief.verified_alerts} official
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-lg bg-slate-900/50 border border-eoc-border p-2">
        <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">
          What you should do
        </div>
        <ul className="space-y-1">
          {(brief.what_to_do || []).map((step, i) => (
            <li key={i} className="text-[11px] text-slate-300 flex gap-1.5 leading-snug">
              <span className={`mt-1 w-1.5 h-1.5 rounded-full ${t.dot} shrink-0`} />
              {step}
            </li>
          ))}
        </ul>
      </div>

      {(brief.top_areas || []).length > 0 && (
        <div className="mt-3">
          <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">
            Worst affected areas
          </div>
          <div className="space-y-1.5">
            {brief.top_areas.slice(0, 5).map((a) => (
              <div key={a.zone_id} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-bold text-slate-100 truncate">
                    {a.name}
                    <span className="font-normal text-slate-500"> · {a.state}</span>
                  </span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold shrink-0 ${LEVEL_CHIP[a.level] || LEVEL_CHIP.LOW}`}>
                    {a.level_plain}
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 leading-snug mt-0.5">{a.reason}</div>
                <div className="flex items-center gap-2 mt-1 text-[9px] text-slate-500">
                  <span className="flex items-center gap-1">
                    <Users size={9} /> {a.people_text}
                  </span>
                  {a.rising && <span className="text-orange-400 font-semibold">▲ rising</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-start gap-1.5 mt-3 text-[9px] text-slate-500 leading-snug">
        <CloudRain size={10} className="mt-0.5 shrink-0" />
        <span>{brief.rain_outlook}</span>
      </div>
      <div className="flex items-center justify-between mt-1.5 text-[9px] text-slate-600">
        <span className="flex items-center gap-1">
          <Radio size={9} /> {brief.source_note}
        </span>
        <span>updated {fmtAge(ageSeconds(now, updatedAt || brief.updated_at))}</span>
      </div>
    </div>
  )
}

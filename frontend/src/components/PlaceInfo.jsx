import React, { useEffect, useState } from 'react'
import { MapPin, X, Loader2, ShieldAlert, Radio, Tent, Hospital, LifeBuoy, Phone, ExternalLink, ChevronRight } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../utils/api.js'

const RISK_CHIP = {
  LOW: 'text-green-300 border-green-500/40 bg-green-500/10',
  MODERATE: 'text-sky-300 border-sky-500/40 bg-sky-500/10',
  HIGH: 'text-yellow-300 border-yellow-500/40 bg-yellow-500/10',
  VERY_HIGH: 'text-orange-300 border-orange-500/40 bg-orange-500/10',
  CRITICAL: 'text-red-300 border-red-500/40 bg-red-500/10',
}
const RISK_BAR = { LOW: '#22c55e', MODERATE: '#38bdf8', HIGH: '#eab308', VERY_HIGH: '#f97316', CRITICAL: '#ef4444' }
const STATUS_COLOR = { NORMAL: 'text-green-400', ABOVE_NORMAL: 'text-yellow-300', SEVERE: 'text-orange-400', EXTREME: 'text-red-400' }

function relevantSources(sources, state, basin) {
  const live = (sources || []).filter((s) => s.status === 'LIVE' && s.realtime && s.url)
  if (!live.length) return []
  const tags = `${(state || '')} ${(basin || '')}`.toLowerCase()
  const matched = live.filter((s) => (s.what_it_gives || '').toLowerCase().includes(tags) || (s.plain_name || '').toLowerCase().includes(state?.toLowerCase() || ''))
  return (matched.length ? matched : live).slice(0, 4)
}

export default function PlaceInfo() {
  const { selectedPlace, setSelectedPlace, sources, zones, regional } = useApp()
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!selectedPlace || typeof selectedPlace.lat !== 'number') return
    let alive = true
    setBusy(true)
    setErr('')
    api
      .areaCheck({ latitude: selectedPlace.lat, longitude: selectedPlace.lon })
      .then((d) => alive && setInfo(d))
      .catch(() => alive && setErr('Could not evaluate this location right now.'))
      .finally(() => alive && setBusy(false))
    return () => {
      alive = false
    }
  }, [selectedPlace?.lat, selectedPlace?.lon, selectedPlace?.name])

  if (!selectedPlace) {
    return null
  }

  const zoneScore = (zid) => {
    const z = zones?.[zid]
    return z ? `${z.overall_score ?? z.severity ?? '—'}/100` : '—'
  }

  return (
    <div className="rounded-xl border border-sky-500/30 bg-sky-500/5">
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-sky-500/20">
        <MapPin size={12} className="text-sky-400 shrink-0" />
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-300 truncate flex-1">
          {selectedPlace.name || 'Picked point'}
        </h3>
        <button onClick={() => setSelectedPlace(null)} title="Dismiss" className="shrink-0 text-slate-500 hover:text-slate-200">
          <X size={13} />
        </button>
      </div>

      {busy && !info && (
        <div className="p-4 flex items-center justify-center gap-2 text-[10px] text-slate-500">
          <Loader2 size={13} className="animate-spin" /> Evaluating flood risk…
        </div>
      )}
      {err && <div className="p-3 text-[10px] text-red-400">{err}</div>}

      {info && !busy && (
        <div className="p-2.5 space-y-2">
          <div className="flex items-center justify-between gap-2 rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
            <div className="flex items-center gap-1.5 min-w-0">
              <ShieldAlert size={11} className="shrink-0 text-slate-400" />
              <div className="min-w-0">
                <div className="text-[10px] text-slate-300 truncate">
                  {info.location.region_name} · {info.location.district}, {info.location.state}
                </div>
                <div className="text-[9px] text-slate-500">
                  {info.location.region_type.replace('_', ' ')} · basin {info.basin} · {info.location.distance_km} km from registry
                  {info.confidence != null && ` · coverage ${info.confidence}%`}
                </div>
              </div>
            </div>
            <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold shrink-0 ${RISK_CHIP[info.risk.level] || RISK_CHIP.LOW}`}>
              {info.risk.level_plain}
            </span>
          </div>

          <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
            <div className="flex items-center justify-between text-[9px] text-slate-500 mb-1">
              <span>Flood risk · blended from {info.coverage.monitored_points_considered} monitored points</span>
              <b className="font-mono text-slate-200">{info.risk.score}</b>
            </div>
            <div className="h-1.5 rounded-full bg-slate-700/60 overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${info.risk.score}%`, background: RISK_BAR[info.risk.level] || '#22c55e' }}
              />
            </div>
            <div className="text-[9px] text-slate-500 mt-1">
              National: <b className="text-slate-300">{info.coverage.national_score}</b> · zone blend:{' '}
              <b className="text-slate-300">{info.coverage.blended}</b> · nearest:{' '}
              <b className="text-slate-300">{info.coverage.nearest_point}</b> ({info.coverage.nearest_point_km} km)
            </div>
          </div>

          {info.closest_zones?.length > 0 && (
            <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="text-[9px] text-slate-500 font-bold uppercase mb-1">Nearest monitoring zones</div>
              <div className="space-y-0.5">
                {info.closest_zones.map((z, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-300 truncate">{z.name}</span>
                    <span className="font-mono text-[9px] text-slate-400 shrink-0">
                      {z.score} <span className={`${RISK_CHIP[z.level]?.split(' ')[0] || 'text-slate-400'}`}>{z.level_plain || z.level}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {info.nearby_rivers?.length > 0 && (
            <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="text-[9px] text-slate-500 font-bold uppercase mb-1 flex items-center gap-1">
                <Radio size={9} /> Nearby river gauges (live CWC)
              </div>
              <div className="space-y-1">
                {info.nearby_rivers.map((r, i) => (
                  <div key={i} className="text-[9px]">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-300">{r.station || r.river} ({r.river || ''})</span>
                      <span className={`font-bold shrink-0 ${STATUS_COLOR[r.status] || 'text-slate-400'}`}>{r.status || '—'}</span>
                    </div>
                    {r.water_level != null && (
                      <div className="text-slate-500">
                        {r.water_level} m (warning {r.warning_level} m) · {r.distance_km} km{r.rate_of_rise ? ` · rising ${r.rate_of_rise} cm/hr` : ''}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {['shelters', 'hospitals', 'rescue_bases'].filter((k) => info[k]?.length).length > 0 && (
            <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5 space-y-1.5">
              <div className="text-[9px] text-slate-500 font-bold uppercase">Nearby relief assets</div>
              {info.shelters?.map((s, i) => (
                <div key={`s${i}`} className="flex items-center gap-1.5 text-[9px] text-slate-300">
                  <Tent size={9} className="text-violet-400 shrink-0" />
                  <span className="truncate">{s.name}</span>
                  <span className="ml-auto shrink-0 text-slate-500">cap {s.capacity || '—'}</span>
                </div>
              ))}
              {info.hospitals?.map((h, i) => (
                <div key={`h${i}`} className="flex items-center gap-1.5 text-[9px] text-slate-300">
                  <Hospital size={9} className="text-rose-400 shrink-0" />
                  <span className="truncate">{h.name}</span>
                  <span className="ml-auto shrink-0 text-slate-500">{h.capacity_status || `${h.beds} beds`}</span>
                </div>
              ))}
              {info.rescue_bases?.map((b, i) => (
                <div key={`b${i}`} className="flex items-center gap-1.5 text-[9px] text-slate-300">
                  <LifeBuoy size={9} className="text-blue-400 shrink-0" />
                  <span className="truncate">{b.name}</span>
                  <span className="ml-auto shrink-0 text-slate-500">{b.agency || `${b.personnel || ''}`}</span>
                </div>
              ))}
            </div>
          )}

          {info.helplines?.length > 0 && (
            <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="text-[9px] text-slate-500 font-bold uppercase mb-1 flex items-center gap-1">
                <Phone size={9} /> Emergency helplines
              </div>
              <div className="space-y-1">
                {info.helplines.map((h, i) => (
                  <a key={i} href={`tel:${String(h.number).replace(/\s+/g, '')}`} className="flex items-center justify-between text-[9px] text-slate-300 hover:text-sky-300">
                    <span className="truncate">{h.label}</span>
                    <span className="font-mono shrink-0 text-sky-400">{h.number}</span>
                  </a>
                ))}
              </div>
            </div>
          )}

          {info.guidance && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-2 py-1.5 text-[10px] text-amber-100 leading-snug">
              {info.guidance}
            </div>
          )}

          {relevantSources(sources.sources, info.state, info.basin).length > 0 && (
            <div className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
              <div className="text-[9px] text-slate-500 font-bold uppercase mb-1">Relevant real-time feeds</div>
              <div className="space-y-1">
                {relevantSources(sources.sources, info.state, info.basin).map((s) => (
                  <a key={s.key} href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-[9px] text-slate-300 hover:text-sky-300">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
                    <span className="truncate underline decoration-dotted underline-offset-2">{s.plain_name}</span>
                    <ExternalLink size={9} className="shrink-0" />
                    <span className="ml-auto shrink-0 text-slate-500">
                      {s.latency_ms != null && `${Math.round(s.latency_ms)} ms`}
                    </span>
                  </a>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between text-[9px] text-slate-500">
            <span className="flex items-center gap-1">
              Zone score <ChevronRight size={8} />
            </span>
            <span className="font-mono text-slate-300">{zoneScore(info.zone_id)} (national {regional?.score ?? '—'})</span>
          </div>
        </div>
      )}
    </div>
  )
}
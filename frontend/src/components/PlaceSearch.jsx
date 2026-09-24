import React, { useEffect, useRef, useState } from 'react'
import { Search, Loader2, Plus, Minus, Locate, X, MapPin } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../utils/api.js'

export default function PlaceSearch() {
  const { pickPlace, focus, setFocus, mapConfig } = useApp()
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const timer = useRef(null)

  useEffect(() => {
    setError('')
    if (q.trim().length < 2) {
      setOpen(false)
      setResults([])
      return
    }
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      setBusy(true)
      try {
        const r = await api.searchPlaces(q.trim(), 9)
        setResults(r.results || [])
        setOpen(true)
      } catch (e) {
        setError('Search unavailable right now.')
        setResults([])
      } finally {
        setBusy(false)
      }
    }, 350)
    return () => clearTimeout(timer.current)
  }, [q])

  const choose = (p) => {
    setQ('')
    setOpen(false)
    pickPlace({ name: p.name, district: p.district, state: p.state, basin: p.basin, lat: p.lat, lon: p.lon, zoom: 15, kind: p.region_type, source: p.source })
  }

  const zoomBy = (d) => setFocus((prev) => ({ lat: prev?.lat ?? mapConfig?.india_center?.[0] ?? 22.5, lon: prev?.lon ?? mapConfig?.india_center?.[1] ?? 79, zoom: Math.min(20, Math.max(4, (prev?.zoom ?? 5) + d)), seq: (prev?.seq || 0) + 1 }))
  const resetView = () => setFocus((prev) => ({ lat: mapConfig?.india_center?.[0] ?? 22.5, lon: mapConfig?.india_center?.[1] ?? 79, zoom: mapConfig?.india_zoom || 5, seq: (prev?.seq || 0) + 1 }))

  return (
    <div className="absolute top-2 left-1/2 -translate-x-1/2 z-[1150] w-[min(460px,92vw)]">
      <div className="flex items-center gap-1.5 rounded-xl border border-eoc-border bg-eoc-panel/95 shadow-2xl px-2.5 py-1.5 backdrop-blur">
        <Search size={14} className="text-sky-400 shrink-0" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search any place in India — village, town, district, river…"
          className="flex-1 min-w-0 bg-transparent text-[12px] text-slate-200 placeholder:text-slate-500 outline-none"
        />
        {busy ? (
          <Loader2 size={13} className="text-slate-500 animate-spin shrink-0" />
        ) : (
          q && (
            <button onClick={() => { setQ(''); setOpen(false) }} className="shrink-0 text-slate-500 hover:text-slate-200">
              <X size={13} />
            </button>
          )
        )}
        {error && <span className="text-[9px] text-red-400 shrink-0">{error}</span>}
        <div className="flex items-center gap-0.5 border-l border-eoc-border pl-1.5 shrink-0">
          <button onClick={() => zoomBy(1)} title="Zoom in" className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-700/50">
            <Plus size={13} />
          </button>
          <button onClick={() => zoomBy(-1)} title="Zoom out" className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-700/50">
            <Minus size={13} />
          </button>
          <button onClick={resetView} title="Reset to all-India view" className="p-1 rounded-md text-slate-400 hover:text-sky-300 hover:bg-slate-700/50">
            <Locate size={13} />
          </button>
        </div>
      </div>

      {open && results.length > 0 && (
        <div className="mt-1.5 rounded-xl border border-eoc-border bg-eoc-panel/95 shadow-2xl backdrop-blur overflow-hidden">
          <div className="px-3 py-1.5 border-b border-eoc-border text-[9px] uppercase tracking-wider text-slate-500">
            {results.length} place{results.length === 1 ? '' : 's'} · click to inspect
          </div>
          <ul className="max-h-[46vh] overflow-y-auto divide-y divide-eoc-border/60">
            {results.map((p, i) => (
              <li key={`${p.name}-${i}`}>
                <button onClick={() => choose(p)} className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-slate-800/40">
                  <MapPin size={12} className="mt-0.5 shrink-0 text-sky-400" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[11px] font-semibold text-slate-200 truncate">{p.name}</span>
                    <span className="block text-[9px] text-slate-500 truncate">
                      {p.full_name || [p.district, p.state].filter(Boolean).join(', ') || 'India'}
                      {p.distance_km != null && ` · ~${p.distance_km} km`}
                    </span>
                  </span>
                  <span className="shrink-0 text-[8px] uppercase tracking-wide text-slate-500 border border-eoc-border rounded px-1 py-0.5">
                    {p.region_type || p.source}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
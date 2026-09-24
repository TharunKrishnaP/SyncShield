import React, { useEffect, useMemo, useState } from 'react'
import { Home, Users, ChevronDown, ChevronRight, ChevronLeft, LifeBuoy, Tent, AlertTriangle, Search, X } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const LEVEL_CHIP = {
  CRITICAL: 'bg-red-600/20 text-red-200 border-red-500/50',
  VERY_HIGH: 'bg-red-500/15 text-red-300 border-red-500/30',
  HIGH: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  MODERATE: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  LOW: 'bg-green-500/15 text-green-300 border-green-500/30',
}

const PAGE_SIZE = 8

function fmtPop(n) {
  if (!n) return '—'
  if (n >= 10000000) return `${(n / 10000000).toFixed(2)} crore`
  if (n >= 100000) return `${(n / 100000).toFixed(2)} lakh`
  return n.toLocaleString('en-IN')
}

function matchesQuery(rec, q) {
  if (!q) return true
  const hay = `${rec.name} ${rec.state} ${rec.district || ''} ${rec.zone || ''}`.toLowerCase()
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => hay.includes(token))
}

function PagedList({ rows }) {
  const [page, setPage] = useState(0)
  const total = rows.length
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const cur = Math.min(page, pages - 1)
  const slice = rows.slice(cur * PAGE_SIZE, cur * PAGE_SIZE + PAGE_SIZE)
  const from = total === 0 ? 0 : cur * PAGE_SIZE + 1
  const to = Math.min((cur + 1) * PAGE_SIZE, total)

  useEffect(() => setPage(0), [total])

  return (
    <>
      <div className="space-y-1">
        {slice.length === 0 && <p className="text-[9px] text-slate-600 px-1 py-1">No matches found.</p>}
        {slice}
      </div>
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between pt-1">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={cur === 0}
            className="flex items-center gap-0.5 rounded border border-eoc-border bg-slate-900/60 px-1.5 py-0.5 text-[9px] font-bold text-slate-300 disabled:opacity-30"
          >
            <ChevronLeft size={10} /> Prev
          </button>
          <span className="text-[9px] text-slate-500">
            {from}–{to} of {total}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
            disabled={cur >= pages - 1}
            className="flex items-center gap-0.5 rounded border border-eoc-border bg-slate-900/60 px-1.5 py-0.5 text-[9px] font-bold text-slate-300 disabled:opacity-30"
          >
            Next <ChevronRight size={10} />
          </button>
        </div>
      )}
    </>
  )
}

function SearchBox({ value, onChange, placeholder }) {
  return (
    <div className="relative">
      <Search size={10} className="absolute left-1.5 top-1/2 -translate-y-1/2 text-slate-500" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-eoc-border bg-slate-900/70 pl-6 pr-6 py-1 text-[10px] text-slate-200 placeholder-slate-600"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-1 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
          aria-label="Clear search"
        >
          <X size={10} />
        </button>
      )}
    </div>
  )
}

export default function EvacuationPanel() {
  const { evacuation } = useApp()
  const [openGuide, setOpenGuide] = useState(false)
  const [shelterQ, setShelterQ] = useState('')
  const [baseQ, setBaseQ] = useState('')

  // Read all data + run all hooks BEFORE any early return so the hook order
  // stays constant across renders (a conditional hook breaks React and blanks
  // the whole app).
  const zones = evacuation?.at_risk_zones || []
  const allShelters = evacuation?.shelters || []
  const allBases = evacuation?.rescue_bases || []
  const guidance = evacuation?.guidance || []

  const shelterRows = useMemo(
    () =>
      allShelters
        .filter((s) => matchesQuery(s, shelterQ))
        .map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
            <div className="min-w-0">
              <div className="text-[10px] font-semibold text-slate-100 truncate">{s.name}</div>
              <div className="text-[9px] text-slate-500">
                {s.state}
                {s.district ? ` · ${s.district}` : ''}
              </div>
            </div>
            <span className="text-[9px] text-green-300 font-semibold shrink-0">{fmtPop(s.capacity)} cap.</span>
          </div>
        )),
    [allShelters, shelterQ],
  )

  const baseRows = useMemo(
    () =>
      allBases
        .filter((b) => matchesQuery(b, baseQ))
        .map((b) => (
          <div key={b.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
            <div className="min-w-0">
              <div className="text-[10px] font-semibold text-slate-100 truncate">{b.name}</div>
              <div className="text-[9px] text-slate-500">
                {b.agency} · {b.state}
                {b.district ? ` · ${b.district}` : ''}
              </div>
            </div>
            <span className="text-[9px] text-sky-300 shrink-0">
              {b.boats} boats · {b.personnel}
            </span>
          </div>
        )),
    [allBases, baseQ],
  )

  // All hooks ran above — an early return here is safe (conditonal hooks would not be).
  if (!evacuation) return null

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="flex items-center justify-between px-3 py-2 border-b border-eoc-border">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Home size={12} className="text-amber-400" /> Evacuation
        </h3>
        <span className="text-[9px] text-amber-300 font-semibold">{zones.length} zones need action</span>
      </div>

      <div className="p-2 space-y-2">
        <div>
          <div className="text-[9px] font-bold uppercase text-slate-500 mb-1 flex items-center gap-1">
            <AlertTriangle size={9} className="text-orange-400" /> Areas to evacuate first
          </div>
          {zones.length === 0 && (
            <p className="text-[10px] text-slate-500 px-1">No zone has crossed the evacuation threshold.</p>
          )}
          <div className="space-y-1">
            {zones.slice(0, 6).map((z) => (
              <div key={z.zone_id} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-bold text-slate-100 truncate">
                    {z.name}
                    <span className="font-normal text-slate-500"> · {z.state}</span>
                  </span>
                  <span className={`text-[8px] px-1 py-0.5 rounded border font-bold shrink-0 ${LEVEL_CHIP[z.level] || LEVEL_CHIP.LOW}`}>
                    {z.score}/100
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[9px] text-slate-500 mt-0.5">
                  <span className="flex items-center gap-1">
                    <Users size={9} /> {fmtPop(z.population)} people
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[9px] font-bold uppercase text-slate-500 mb-1 flex items-center gap-1">
            <Tent size={9} className="text-green-400" /> Relief shelters ({evacuation.shelter_count})
          </div>
          <SearchBox value={shelterQ} onChange={setShelterQ} placeholder="Search district / state…" />
          <div className="mt-1">
            <PagedList rows={shelterRows} />
          </div>
        </div>

        <div>
          <div className="text-[9px] font-bold uppercase text-slate-500 mb-1 flex items-center gap-1">
            <LifeBuoy size={9} className="text-sky-400" /> Rescue teams ready
          </div>
          <SearchBox value={baseQ} onChange={setBaseQ} placeholder="Search NDRF / SDRF / state…" />
          <div className="mt-1">
            <PagedList rows={baseRows} />
          </div>
        </div>

        <div className="rounded-lg bg-slate-900/50 border border-eoc-border">
          <button
            onClick={() => setOpenGuide((v) => !v)}
            className="w-full flex items-center justify-between px-2 py-1.5 text-[10px] font-bold text-slate-300"
          >
            <span className="flex items-center gap-1">
              {openGuide ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              How to evacuate safely
            </span>
            <span className="text-[9px] text-slate-500 font-normal">NDMA guidance</span>
          </button>
          {openGuide && (
            <div className="px-2 pb-2 space-y-2">
              {guidance.map((g) => (
                <div key={g.title}>
                  <div className="text-[9px] font-bold uppercase text-slate-400 mb-0.5">{g.title}</div>
                  <ul className="space-y-0.5">
                    {g.steps.map((s, i) => (
                      <li key={i} className="text-[10px] text-slate-400 flex gap-1.5 leading-snug">
                        <span className="mt-1 w-1 h-1 rounded-full bg-amber-400 shrink-0" />
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
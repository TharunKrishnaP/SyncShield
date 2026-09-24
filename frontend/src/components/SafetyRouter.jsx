import React, { useMemo, useState } from 'react'
import { Route, Navigation, Crosshair, Loader2, ShieldCheck, AlertTriangle, XCircle, Tent, Hospital, LifeBuoy } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

const STATUS = {
  SAFE: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', bar: '#22c55e', Icon: ShieldCheck },
  CAUTION: { chip: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', bar: '#eab308', Icon: AlertTriangle },
  UNSAFE: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', bar: '#ef4444', Icon: XCircle },
}

export default function SafetyRouter() {
  const { zoneMeta, evacuation, layers, api, addRoute, selectedPlace } = useApp()
  const [origin, setOrigin] = useState('')
  const [dest, setDest] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [locating, setLocating] = useState(false)

  const options = useMemo(() => {
    const groups = []
    const zones = (zoneMeta?.zones || [])
      .filter((z) => Array.isArray(z.centroid) && z.centroid.length === 2)
      .map((z) => ({
        key: `z:${z.id}`,
        label: `${z.name}, ${z.state}`,
        kind: 'Zone',
        lat: z.centroid[1],
        lon: z.centroid[0],
        name: z.name,
      }))
    groups.push({ group: 'Districts / cities', items: zones })

    const infra = layers?.infrastructure || {}
    const shelters = (infra.shelters || evacuation?.shelters || []).map((s) => ({
      key: `s:${s.id}`,
      label: `${s.name}, ${s.state}`,
      kind: 'Shelter',
      lat: s.lat,
      lon: s.lon,
      name: s.name,
    }))
    const hospitals = (infra.hospitals || []).map((h) => ({
      key: `h:${h.id}`,
      label: `${h.name}, ${h.state}`,
      kind: 'Hospital',
      lat: h.lat,
      lon: h.lon,
      name: h.name,
    }))
    const bases = (infra.rescue_bases || []).map((b) => ({
      key: `r:${b.id}`,
      label: `${b.name}, ${b.state}`,
      kind: 'Rescue',
      lat: b.lat,
      lon: b.lon,
      name: b.name,
    }))
    if (shelters.length) groups.push({ group: 'Relief shelters', items: shelters })
    if (hospitals.length) groups.push({ group: 'Hospitals', items: hospitals })
    if (bases.length) groups.push({ group: 'Rescue bases', items: bases })
    return groups
  }, [zoneMeta, layers, evacuation])

  const all = useMemo(() => options.flatMap((g) => g.items), [options])
  const find = (key) => all.find((o) => o.key === key)

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setError('Your browser does not allow location access.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        setOrigin(`gps:${latitude}:${longitude}`)
        setLocating(false)
      },
      () => {
        setError('Location permission denied. Choose a city instead.')
        setLocating(false)
      },
      { timeout: 10000 },
    )
  }

  const mapPickKey = selectedPlace && typeof selectedPlace.lat === 'number' ? `pick:${selectedPlace.lat}:${selectedPlace.lon}` : null

  const resolve = (key) => {
    if (!key) return null
    if (key.startsWith('gps:')) {
      const [, lat, lon] = key.split(':')
      return { name: 'My location', lat: parseFloat(lat), lon: parseFloat(lon) }
    }
    if (key.startsWith('pick:')) {
      const [, lat, lon] = key.split(':')
      return { name: selectedPlace?.name || 'Picked point', lat: parseFloat(lat), lon: parseFloat(lon) }
    }
    return find(key)
  }

  const check = async () => {
    const o = resolve(origin)
    const d = resolve(dest)
    if (!o || !d) {
      setError('Choose both a starting point and a destination.')
      return
    }
    setError('')
    setBusy(true)
    setResult(null)
    try {
      const res = await api.evaluateRoute({
        origin_lat: o.lat,
        origin_lon: o.lon,
        dest_lat: d.lat,
        dest_lon: d.lon,
        origin_name: o.name,
        dest_name: d.name,
      })
      setResult(res)
      addRoute(res)
    } catch (e) {
      setError('Could not check the route. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="px-3 py-2 border-b border-eoc-border flex items-center gap-1.5">
        <Route size={12} className="text-sky-400" />
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Safe Route Planner</h3>
      </div>

      <div className="p-2 space-y-1.5">
        <div className="flex gap-1.5">
          <select
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            className="flex-1 min-w-0 bg-slate-900/70 border border-eoc-border rounded px-1.5 py-1 text-[10px] text-slate-200"
          >
            <option value="">Starting point…</option>
            {origin.startsWith('gps:') && <option value={origin}>My location (GPS)</option>}
            {mapPickKey && <option value={mapPickKey}>📍 {selectedPlace.name} (map pick)</option>}
            {options.map((g) => (
              <optgroup key={g.group} label={g.group}>
                {g.items.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <button
            onClick={useMyLocation}
            title="Use my location"
            className="shrink-0 px-1.5 rounded border border-eoc-border bg-slate-900/70 text-slate-400 hover:text-sky-300"
          >
            {locating ? <Loader2 size={12} className="animate-spin" /> : <Crosshair size={12} />}
          </button>
        </div>

        <select
          value={dest}
          onChange={(e) => setDest(e.target.value)}
          className="w-full bg-slate-900/70 border border-eoc-border rounded px-1.5 py-1 text-[10px] text-slate-200"
        >
          <option value="">Destination (shelter, hospital, rescue base)…</option>
          {mapPickKey && <option value={mapPickKey}>📍 {selectedPlace.name} (map pick)</option>}
          {options.map((g) => (
            <optgroup key={g.group} label={g.group}>
              {g.items.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>

        <button
          onClick={check}
          disabled={busy}
          className="w-full flex items-center justify-center gap-1.5 rounded bg-sky-500/20 hover:bg-sky-500/30 border border-sky-500/40 text-sky-200 text-[10px] font-bold py-1.5 disabled:opacity-50"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Navigation size={12} />}
          {busy ? 'Checking flood exposure…' : 'Check safest route'}
        </button>

        {error && <p className="text-[9px] text-red-400 px-0.5">{error}</p>}

        {result && (
          <div className="space-y-1.5 pt-1">
            <div className="flex items-start gap-1.5 rounded-lg bg-sky-500/10 border border-sky-500/30 px-2 py-1.5">
              <Navigation size={11} className="mt-0.5 text-sky-300 shrink-0" />
              <p className="text-[10px] text-slate-200 leading-snug">{result.recommendation}</p>
            </div>
            {['direct_route', 'alternative_route'].map((k) => {
              const r = result[k]
              const st = STATUS[r.status] || STATUS.CAUTION
              const Icon = st.Icon
              const label = k === 'direct_route' ? 'Direct route' : 'Alternative route'
              return (
                <div key={k} className="rounded-lg bg-slate-900/50 border border-eoc-border px-2 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1 text-[10px] font-bold text-slate-200">
                      <Icon size={11} className={st.chip.split(' ')[1]} /> {label}
                    </span>
                    <span className={`text-[8px] px-1 py-0.5 rounded border font-bold ${st.chip}`}>{r.status}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-700/60 mt-1.5 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${r.risk_score}%`, background: st.bar }} />
                  </div>
                  <div className="grid grid-cols-4 gap-1 mt-1.5 text-[9px] text-slate-500">
                    <span>
                      Risk<br />
                      <b className="text-slate-200">{r.risk_score}</b>
                    </span>
                    <span>
                      Distance<br />
                      <b className="text-slate-200">{r.distance_km} km</b>
                    </span>
                    <span>
                      Flood<br />
                      <b className="text-slate-200">{r.flood_exposure}</b>
                    </span>
                    <span>
                      Blocked<br />
                      <b className="text-slate-200">{r.road_blockages}</b>
                    </span>
                  </div>
                </div>
              )
            })}
            <div className="flex items-center gap-2 text-[9px] text-slate-500 px-0.5">
              <Tent size={9} /> {evacuation?.shelter_count || 0} shelters
              <Hospital size={9} /> {(layers?.infrastructure?.hospitals || []).length} hospitals
              <LifeBuoy size={9} /> {(layers?.infrastructure?.rescue_bases || []).length} rescue bases
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

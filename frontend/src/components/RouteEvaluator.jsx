import React, { useState, useEffect } from 'react'
import { Route } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

export default function RouteEvaluator() {
  const { zones, api, priorities } = useApp()
  const [origin, setOrigin] = useState('')
  const [dest, setDest] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const zoneOptions = Object.values(zones).map((z) => ({
    id: z.zone_id,
    name: z.zone_name,
    state: z.state,
    centroid: null,
  }))

  // Priority zones are the natural rescue destinations
  const destOptions = (priorities || []).map((p) => ({
    id: p.zone_id,
    name: p.zone_name,
    state: p.state,
    priority: p.priority_label,
  }))

  const getCoords = (id, isDest) => {
    const zone = zones?.[id]
    if (zone) return null
    return null
  }

  useEffect(() => {
    if (destOptions.length && !dest) setDest(destOptions[0]?.id)
  }, [destOptions, dest])

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      // Use zone centroids from priorities (first zone with that id)
      const findCentroid = (id) => {
        const p = (priorities || []).find((z) => z.zone_id === id)
        if (p && p.centroid) return { lat: p.centroid[1], lon: p.centroid[0], name: p.zone_name }
        const z = zones?.[id]
        if (z) return null
        return null
      }
      const o = findCentroid(origin)
      const d = findCentroid(dest)
      if (!o || !d) {
        setError('Cannot locate coordinates for the chosen zones. Pick zones from the priority list.')
        setLoading(false)
        return
      }
      const res = await api.evaluateRoute({
        origin_lat: o.lat,
        origin_lon: o.lon,
        dest_lat: d.lat,
        dest_lon: d.lon,
        origin_name: o.name,
        dest_name: d.name,
      })
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const riskColor = (r) =>
    r > 60 ? 'text-red-400' : r > 35 ? 'text-yellow-400' : 'text-green-400'
  const riskBg = (r) =>
    r > 60 ? 'bg-red-500/10 border-red-500/30' : r > 35 ? 'bg-yellow-500/10 border-yellow-500/30' : 'bg-green-500/10 border-green-500/30'

  return (
    <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-3">
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
        <Route size={12} /> Emergency Route Risk Evaluator
      </h3>
      <div className="space-y-2">
        <div>
          <label className="text-[9px] text-slate-500 uppercase">Origin</label>
          <select
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            className="w-full mt-0.5 bg-slate-800 border border-eoc-border rounded-md px-2 py-1.5 text-[11px] text-slate-200 focus:outline-none focus:border-sky-500"
          >
            <option value="">— Select origin —</option>
            <option value="AS-GUWAHATI">NDRF Guwahati HQ (Assam)</option>
            <option value="DL-DELHI">NDRF Ghaziabad (Delhi)</option>
            <option value="BR-PATNA">SDRF Patna</option>
            <option value="OD-CUTTACK">SDRF Cuttack</option>
            <option value="GJ-AHMEDABAD">SDRF Ahmedabad</option>
            <option value="KL-KOCHI">Ernakulam Fire & Rescue</option>
          </select>
        </div>
        <div>
          <label className="text-[9px] text-slate-500 uppercase">Destination (critical zone)</label>
          <select
            value={dest}
            onChange={(e) => setDest(e.target.value)}
            className="w-full mt-0.5 bg-slate-800 border border-eoc-border rounded-md px-2 py-1.5 text-[11px] text-slate-200 focus:outline-none focus:border-sky-500"
          >
            <option value="">— Select destination —</option>
            {destOptions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.state} ({d.priority})
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={run}
          disabled={!origin || !dest || loading}
          className="w-full py-1.5 rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-[11px] font-semibold transition-colors"
        >
          {loading ? 'Evaluating…' : 'Evaluate Route'}
        </button>
        {error && <p className="text-[10px] text-red-400">{error}</p>}

        {result && (
          <div className="space-y-2 pt-1">
            <div className="flex justify-between items-end">
              <div>
                <p className="text-[9px] text-slate-500">{result.origin.name} → {result.destination.name}</p>
                <p className="text-[10px] text-slate-400">{result.recommendation.slice(0, 90)}…</p>
              </div>
            </div>
            {['direct_route', 'alternative_route'].map((key) => {
              const r = result[key]
              return (
                <div key={key} className={`rounded-lg border p-2 ${riskBg(r.risk_score)}`}>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold uppercase">
                      {key === 'direct_route' ? 'Direct Route' : 'AI Recommended'}
                    </span>
                    <span className={`text-xs font-mono font-bold ${riskColor(r.risk_score)}`}>
                      RISK {r.risk_score} · {r.status}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1 mt-1.5 text-[9px] text-slate-400">
                    <span>Distance: {r.distance_km} km</span>
                    <span>Flood exposure: {r.flood_exposure}/100</span>
                    <span>Blockages: {r.road_blockages}</span>
                    <span>Incidents: {r.incident_density}</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
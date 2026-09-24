import React, { useEffect, useState } from 'react'
import { Polygon, Popup, useMap } from 'react-leaflet'
import { useApp } from '../../context/AppContext.jsx'

const PRIORITY_COLORS = {
  1: '#ef4444',
  2: '#f97316',
  3: '#eab308',
  4: '#22c55e',
}

export default function PriorityZones() {
  const { priorities, explanations } = useApp()
  const map = useMap()
  const [zoom, setZoom] = useState(map.getZoom())
  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom())
    map.on('zoomend', onZoom)
    return () => map.off('zoomend', onZoom)
  }, [map])
  if (!priorities || priorities.length === 0) return null

  // At the all-India view only the actionable CRITICAL/HIGH polygons are
  // drawn; zoom in to reveal every district's polygon.
  const visible = zoom >= 6 ? priorities : priorities.filter((p) => p.priority <= 2)

  return (
    <>
      {visible.map((p) => {
        const coords = (p.coordinates || []).map(([lon, lat]) => [lat, lon])
        const color = PRIORITY_COLORS[p.priority] || '#94a3b8'
        const expl = explanations?.[p.zone_id]
        return (
          <Polygon
            key={p.zone_id}
            positions={coords}
            pathOptions={{
              color,
              weight: 1.5,
              fillColor: color,
              fillOpacity: 0.18,
              dashArray: p.priority === 1 ? '6 3' : undefined,
            }}
          >
            <Popup>
              <div className="text-slate-900 text-xs leading-relaxed" style={{ minWidth: 220 }}>
                <div className="font-bold text-sm mb-1">
                  Priority {p.priority_label} — {p.zone_name}
                </div>
                <table className="w-full">
                  <tbody>
                    <tr><td className="text-slate-500">State</td><td className="font-semibold">{p.state}</td></tr>
                    <tr><td className="text-slate-500">Basin</td><td className="font-semibold">{p.basin}</td></tr>
                    <tr><td className="text-slate-500">District</td><td className="font-semibold">{p.district}</td></tr>
                    <tr><td className="text-slate-500">Severity</td><td className="font-semibold">{p.severity}/100</td></tr>
                    <tr><td className="text-slate-500">Population exposed</td><td className="font-semibold">{p.population_exposure?.toLocaleString()}</td></tr>
                    <tr><td className="text-slate-500">Vulnerable</td><td className="font-semibold">{p.vulnerable_population?.toLocaleString()}</td></tr>
                    <tr><td className="text-slate-500">Priority score</td><td className="font-semibold">{p.priority_score}</td></tr>
                    {p.rate_of_change !== undefined && (
                      <tr><td className="text-slate-500">Rate of change</td><td className="font-semibold">{p.rate_of_change} pts/hr</td></tr>
                    )}
                  </tbody>
                </table>
                {expl && (
                  <div className="mt-2 p-1.5 bg-slate-100 rounded text-[11px]">
                    {expl.natural_language_summary}
                  </div>
                )}
              </div>
            </Popup>
          </Polygon>
        )
      })}
    </>
  )
}
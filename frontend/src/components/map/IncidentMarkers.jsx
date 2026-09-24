import React from 'react'
import { Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import { useApp } from '../../context/AppContext.jsx'

const incidentIcon = (severity) =>
  L.divIcon({
    html: `<div style="
      width: 14px; height: 14px; border-radius: 50%;
      background: ${severity > 0.6 ? '#f43f5e' : severity > 0.35 ? '#f59e0b' : '#38bdf8'};
      border: 2px solid #0b1220; box-shadow: 0 0 6px rgba(0,0,0,.6);"></div>`,
    className: 'leaflet-div-icon',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })

export default function IncidentMarkers() {
  const { incidents } = useApp()
  const recent = incidents?.slice(0, 30) || []
  if (!recent.length) return null

  return (
    <>
      {recent.map((inc, i) => {
        if (!inc.latitude || !inc.longitude) return null
        return (
          <Marker
            key={inc.id ? `${inc.id}-${i}` : i}
            position={[inc.latitude, inc.longitude]}
            icon={incidentIcon(inc.severity || 0.5)}
          >
            <Popup>
              <div className="text-slate-900 text-xs min-w-[180px]">
                <div className="font-bold">{inc.category} — Severity {(inc.severity * 100).toFixed(0)}%</div>
                <div className="text-slate-500 mb-1">{inc.location_name} · {inc.state}</div>
                <p className="leading-snug">{inc.description}</p>
                <div className="mt-1 text-slate-500">Confidence {inc.confidence} · {inc.source}</div>
              </div>
            </Popup>
          </Marker>
        )
      })}
    </>
  )
}
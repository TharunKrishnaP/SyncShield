import React from 'react'
import { CircleMarker, Tooltip, Popup } from 'react-leaflet'
import { useApp } from '../../context/AppContext.jsx'

function statusColor(status) {
  if (status === 'EXTREME') return '#ef4444'
  if (status === 'SEVERE') return '#f97316'
  if (status === 'ABOVE_NORMAL') return '#eab308'
  return '#22c55e'
}

export default function RiverMarkers() {
  const { layers } = useApp()
  const stations = layers?.river_stations || []
  if (!stations.length) return null

  return (
    <>
      {stations.map((s) => {
        const status = s.status || 'NORMAL'
        const color = statusColor(status)
        const critical = status === 'EXTREME' || (s.danger_level && s.water_level >= s.danger_level)
        return (
          <CircleMarker
            key={s.id}
            center={[s.latitude, s.longitude]}
            radius={critical ? 9 : 6}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.9, weight: 2 }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              <div className="text-[10px] font-semibold">{s.name}</div>
            </Tooltip>
            <Popup>
              <div className="text-slate-900 text-xs leading-relaxed min-w-[180px]">
                <div className="font-bold text-sm">{s.name}</div>
                <div className="text-slate-500 mb-1">{s.river} · {s.state} · {s.basin} basin</div>
                {s.water_level !== undefined && (
                  <>
                    <div>Water level: <b className="font-mono">{s.water_level} m</b></div>
                    <div>Warning level: {s.warning_level} m</div>
                    <div>Danger level: {s.danger_level} m</div>
                    {s.highest_flood_level && <div>HFL: {s.highest_flood_level} m</div>}
                    {s.rate_of_rise !== undefined && <div>Rate of rise: {s.rate_of_rise} cm/hr</div>}
                  </>
                )}
                <div className="mt-1">
                  <span className={`font-bold ${critical ? 'text-red-600' : 'text-green-600'}`}>
                    {status}
                  </span>
                </div>
                <div className="text-slate-500 mt-1">Source: CWC · {s.station_type}</div>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </>
  )
}
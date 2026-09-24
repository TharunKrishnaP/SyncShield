import React, { useMemo } from 'react'
import { Polygon, Popup } from 'react-leaflet'
import { useApp } from '../../context/AppContext.jsx'

export default function SatelliteOverlay() {
  const { layers } = useApp()
  const extents = layers?.satellite_extents || []

  const recent = useMemo(() => {
    const byZone = {}
    for (const e of extents) {
      byZone[e.zone_id] = e
    }
    return Object.values(byZone)
  }, [extents])

  if (!recent.length) return null

  return (
    <>
      {recent.map((e) => (
        <Polygon
          key={e.id || e.zone_id}
          positions={(e.flood_polygons?.[0] || []).map(([lon, lat]) => [lat, lon])}
          pathOptions={{
            color: '#38bdf8',
            weight: 1,
            fillColor: '#0ea5e9',
            fillOpacity: 0.28,
            className: 'flood-glow',
          }}
        >
          <Popup>
            <div className="text-slate-900 text-xs">
              <div className="font-bold">Sentinel-1 SAR Flood Extent</div>
              <div>{e.zone_id}</div>
              <div>Area: {e.flood_area_km2} km²</div>
              <div>Avg depth: {e.water_depth_avg} m</div>
              <div>Status: {e.flood_status}</div>
              <div className="text-slate-500">Source: {e.satellite} · {e.sensor}</div>
            </div>
          </Popup>
        </Polygon>
      ))}
    </>
  )
}
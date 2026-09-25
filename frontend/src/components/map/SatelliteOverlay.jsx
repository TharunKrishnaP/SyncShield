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
              <div className="font-bold">
                {e.data_source?.startsWith('ML_SAR')
                  ? 'ML U-Net Flood Extent (Sentinel-1)'
                  : 'Sentinel-1 SAR Flood Extent'}
              </div>
              <div>{e.zone_id}</div>
              <div>Area: {e.flood_area_km2} km²</div>
              <div>Avg depth: {e.water_depth_avg} m</div>
              <div>Status: {e.flood_status}</div>
              <div className="text-slate-500">
                {e.data_source?.startsWith('ML_SAR')
                  ? `Source: trained U-Net · confidence ${e.confidence}`
                  : `Source: ${e.satellite} · ${e.sensor}`}
              </div>
              <div className="text-slate-400 italic mt-1">
                Coarse estimate: extent derived at {e.resolution_m || '~38'} m
                pixel resolution from the full {e.source_scene || 'scene'} chip
                (flood pixel fraction {e.flood_pixel_ratio?.toFixed?.(3) ?? e.flood_pixel_ratio}),
                not surveyed ground truth — treat as indicative, not measured.
              </div>
            </div>
          </Popup>
        </Polygon>
      ))}
    </>
  )
}
import React from 'react'
import { Polyline, Popup } from 'react-leaflet'
import { useApp } from '../../context/AppContext.jsx'

export default function RouteLines() {
  const { routes } = useApp()
  if (!routes || routes.length === 0) return null

  return (
    <>
      {routes.map((r, i) => {
        const directWp = r.direct_route?.waypoints || []
        const altWp = r.alternative_route?.waypoints || []
        const directPos = directWp.map(([lon, lat]) => [lat, lon])
        const altPos = altWp.map(([lon, lat]) => [lat, lon])
        return (
          <React.Fragment key={i}>
            <Polyline
              positions={directPos}
              pathOptions={{
                color: '#ef4444',
                weight: 2,
                dashArray: '8 6',
                opacity: 0.75,
              }}
            >
              <Popup>
                <div className="text-slate-900 text-xs">
                  <div className="font-bold text-red-600">Direct Route — {r.direct_route.status}</div>
                  <div>{r.origin.name} → {r.destination.name}</div>
                  <div>Distance: {r.direct_route.distance_km} km</div>
                  <div>Risk: {r.direct_route.risk_score}/100</div>
                  <div>Flood exposure: {r.direct_route.flood_exposure}</div>
                  <div>Blockages: {r.direct_route.road_blockages}</div>
                </div>
              </Popup>
            </Polyline>
            <Polyline
              positions={altPos}
              pathOptions={{
                color: '#22c55e',
                weight: 3,
                opacity: 0.9,
              }}
            >
              <Popup>
                <div className="text-slate-900 text-xs">
                  <div className="font-bold text-green-600">Recommended Route — {r.alternative_route.status}</div>
                  <div>{r.origin.name} → {r.destination.name}</div>
                  <div>Distance: {r.alternative_route.distance_km} km</div>
                  <div>Risk: {r.alternative_route.risk_score}/100</div>
                  <div>Flood exposure: {r.alternative_route.flood_exposure}</div>
                  <div>Blockages: {r.alternative_route.road_blockages}</div>
                  <div className="mt-1 text-slate-600">{r.recommendation}</div>
                </div>
              </Popup>
            </Polyline>
          </React.Fragment>
        )
      })}
    </>
  )
}
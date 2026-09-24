import React, { useMemo } from 'react'
import { Marker } from 'react-leaflet'
import L from 'leaflet'
import { useApp } from '../../context/AppContext.jsx'

function windIcon(speed) {
  const intensity = Math.min((speed || 0) / 60, 1)
  const color = intensity > 0.6 ? '#ef4444' : intensity > 0.35 ? '#f97316' : '#38bdf8'
  const size = 18 + Math.round(intensity * 14)
  return { color, size }
}

export default function WindLayer() {
  const { windGrid } = useApp()
  const points = windGrid || []

  const icons = useMemo(
    () =>
      points.map((p) => {
        const { color, size } = windIcon(p.wind_speed_kmph)
        const deg = ((p.wind_direction_deg || 0) + 180) % 360
        const html = `
          <div style="transform: rotate(${deg}deg); width:${size}px; height:${size}px; display:flex; align-items:center; justify-content:center;">
            <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none">
              <path d="M12 2 L12 20" stroke="${color}" stroke-width="2.2" stroke-linecap="round"/>
              <path d="M6 12 L12 20 L18 12" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            </svg>
          </div>`
        return L.divIcon({
          html,
          className: 'wind-arrow-icon',
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        })
      }),
    [points],
  )

  if (!points.length) return null

  return (
    <>
      {points.map((p, i) => (
        <Marker key={`${p.latitude}-${p.longitude}`} position={[p.latitude, p.longitude]} icon={icons[i]} interactive={false} />
      ))}
    </>
  )
}

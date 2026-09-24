import React, { useEffect, useState } from 'react'
import { CircleMarker, Popup, useMap } from 'react-leaflet'
import { useApp } from '../../context/AppContext.jsx'

const ICON_COLORS = {
  hospital: '#f43f5e',
  rescue_base: '#3b82f6',
  shelter: '#8b5cf6',
}

export default function InfraMarkers() {
  const { layers } = useApp()
  const map = useMap()
  const [zoom, setZoom] = useState(map.getZoom())
  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom())
    map.on('zoomend', onZoom)
    return () => map.off('zoomend', onZoom)
  }, [map])

  const infra = layers?.infrastructure || {}
  const hospitals = infra.hospitals || []
  const bases = infra.rescue_bases || []
  const shelters = infra.shelters || []

  // Progressive disclosure as you zoom in: strategic rescue bases always,
  // shelters once the region is in view, hospitals only at street level.
  // At the country view only flood-prone district shelters are shown, so all
  // of India's rescue coverage stays visible without marker clutter.
  const showShelters = zoom >= 6
  const showHospitals = zoom >= 8
  const visibleShelters = showShelters ? shelters : shelters.filter((s) => s.flood_prone)
  const shelterRadius = zoom < 6 ? 5 : 8

  const renderMarker = (item, type, radius) => {
    if (!item.lat || !item.lon) return null
    let title = item.name
    let detail = {}
    if (type === 'hospital') {
      detail = {
        State: item.state,
        District: item.district,
        Beds: item.beds,
        Status: item.capacity_status,
      }
    } else if (type === 'rescue_base') {
      detail = {
        State: item.state,
        District: item.district,
        Agency: item.agency,
        Boats: item.boats,
        Personnel: item.personnel,
      }
    } else {
      detail = {
        State: item.state,
        District: item.district,
        Capacity: item.capacity,
      }
    }
    return (
      <CircleMarker
        key={item.id}
        center={[item.lat, item.lon]}
        radius={radius}
        pathOptions={{
          color: ICON_COLORS[type],
          fillColor: ICON_COLORS[type],
          fillOpacity: 0.5,
          weight: 1.5,
        }}
      >
        <Popup>
          <div className="text-slate-900 text-xs min-w-[160px]">
            <div className="font-bold">{title}</div>
            <div className="text-slate-500 mb-1">{type.replace('_', ' ')}</div>
            {Object.entries(detail).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-slate-500">{k}</span>
                <b>{v}</b>
              </div>
            ))}
          </div>
        </Popup>
      </CircleMarker>
    )
  }

  return (
    <>
      {bases.map((b) => renderMarker(b, 'rescue_base', 12))}
      {visibleShelters.map((s) => renderMarker(s, 'shelter', shelterRadius))}
      {showHospitals && hospitals.map((h) => renderMarker(h, 'hospital', 10))}
    </>
  )
}
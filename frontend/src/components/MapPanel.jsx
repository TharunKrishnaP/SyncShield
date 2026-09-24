import React, { useEffect } from 'react'
import { MapContainer, TileLayer, useMap, useMapEvents, Marker, Popup } from 'react-leaflet'
import { divIcon } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Satellite, RefreshCw } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../utils/api.js'
import PriorityZones from './map/PriorityZones.jsx'
import SatelliteOverlay from './map/SatelliteOverlay.jsx'
import RiverMarkers from './map/RiverMarkers.jsx'
import InfraMarkers from './map/InfraMarkers.jsx'
import RouteLines from './map/RouteLines.jsx'
import MapLegend from './map/MapLegend.jsx'
import IncidentMarkers from './map/IncidentMarkers.jsx'
import WindLayer from './map/WindLayer.jsx'
import FloodEventMarkers from './map/FloodEventMarkers.jsx'

const FALLBACK_BASEMAPS = [
  {
    id: 'satellite',
    name: 'Satellite imagery (Esri)',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri, Maxar, Earthstar Geographics',
    max_native_zoom: 19,
    is_default: true,
  },
  { id: 'streets', name: 'Streets (OSM)', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: 'OpenStreetMap', max_native_zoom: 19, is_default: false },
]

function MapRecenter({ center, zoom }) {
  const map = useMap()
  useEffect(() => {
    if (center) map.setView(center, zoom || map.getZoom())
  }, [center, zoom, map])
  return null
}

function MapFocus({ focus }) {
  const map = useMap()
  useEffect(() => {
    if (focus && typeof focus.lat === 'number') {
      map.flyTo([focus.lat, focus.lon], focus.zoom || Math.max(map.getZoom(), 15), { duration: 1.1 })
    }
  }, [focus?.seq]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

const PIN_ICON = divIcon({
  className: '',
  html: '<div style="width:22px;height:22px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid #fff;background:#f43f5e;box-shadow:0 1px 6px rgba(0,0,0,.6)"><div style="width:6px;height:6px;border-radius:50%;background:#fff;margin:6px auto"/></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 22],
})

function MapEvents({ onPick }) {
  useMapEvents({
    click: (e) => onPick && onPick(e.latlng.lat, e.latlng.lng),
  })
  return null
}

function frameTime(epoch) {
  if (!epoch) return ''
  return new Date(epoch * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

export default function MapPanel() {
  const { mapConfig, priorities, alerts, windGrid, updatedAt, connection, baseId, overlayState, pickPlace, selectedPlace, focus } = useApp()

  const basemaps = mapConfig?.basemaps?.length ? mapConfig.basemaps : FALLBACK_BASEMAPS
  const overlays = mapConfig?.overlays || []
  const base = basemaps.find((b) => b.id === baseId) || basemaps[0]
  const radar = overlays.find((o) => o.id === 'rain-radar')
  const imerg = overlays.find((o) => o.id === 'nasa-imerg')
  const daily = basemaps.find((b) => b.id === 'nasa-daily')
  const center = mapConfig?.india_center || [22.5, 79.0]
  const zoom = mapConfig?.india_zoom || 5

  const onPick = async (lat, lon) => {
    pickPlace({ name: `Point ${lat.toFixed(3)}, ${lon.toFixed(3)}`, lat, lon, zoom: 15, kind: 'map_point', source: 'map', state: '', district: '' })
    try {
      const n = await api.nearby(lat, lon, 1)
      const nearest = n.places?.[0]
      if (nearest) pickPlace({ ...nearest, lat, lon, zoom: 15, kind: 'place', source: nearest.source })
    } catch {
      /* keep generic point name */
    }
  }

  return (
    <main className="absolute inset-0 isolate">
      <MapContainer
        center={center}
        zoom={zoom}
        minZoom={4}
        maxZoom={20}
        worldCopyJump={true}
        className="h-full w-full"
        zoomControl={false}
      >
        {base && (
          <TileLayer
            key={base.url}
            url={base.url}
            attribution={base.attribution}
            maxNativeZoom={base.max_native_zoom || 19}
            maxZoom={20}
          />
        )}
        {overlayState.daily && daily && (
          <TileLayer key={daily.url} url={daily.url} attribution={daily.attribution} opacity={0.85} maxNativeZoom={9} maxZoom={20} />
        )}
        {overlayState.imerg && imerg && (
          <TileLayer key={imerg.url} url={imerg.url} attribution={imerg.attribution} opacity={imerg.opacity || 0.55} maxNativeZoom={6} maxZoom={20} />
        )}
        {overlayState.radar && radar && (
          <TileLayer key={radar.url} url={radar.url} attribution={radar.attribution} opacity={radar.opacity || 0.6} maxNativeZoom={10} maxZoom={20} />
        )}

        {overlayState.wind && <WindLayer />}
        {overlayState.priority && <PriorityZones />}
        {overlayState.flood && <SatelliteOverlay />}
        {overlayState.rivers && <RiverMarkers />}
        {overlayState.infra && <InfraMarkers />}
        {overlayState.routes && <RouteLines />}
        {overlayState.incidents && <IncidentMarkers />}
        <FloodEventMarkers />

        {selectedPlace && typeof selectedPlace.lat === 'number' && (
          <Marker position={[selectedPlace.lat, selectedPlace.lon]} icon={PIN_ICON}>
            <Popup>
              <div className="text-slate-900 text-xs leading-relaxed min-w-[160px]">
                <div className="font-bold">{selectedPlace.name || 'Picked point'}</div>
                {selectedPlace.district && <div className="text-slate-500">{selectedPlace.district}, {selectedPlace.state}</div>}
                {selectedPlace.basin && <div className="text-slate-500">{selectedPlace.basin} basin</div>}
                <div className="font-mono text-[10px] text-slate-600 mt-0.5">{selectedPlace.lat.toFixed(4)}, {selectedPlace.lon.toFixed(4)}</div>
              </div>
            </Popup>
          </Marker>
        )}

        <MapEvents onPick={onPick} />
        <MapRecenter center={center} zoom={zoom} />
        <MapFocus focus={focus} />
      </MapContainer>

      <MapLegend />

      <div className="absolute top-2 right-2 z-[500] bg-eoc-panel/85 border border-eoc-border rounded-lg px-2.5 py-1.5 text-[9px] text-slate-400 shadow space-y-0.5 backdrop-blur">
        <div className="flex items-center gap-1">
          <Satellite size={10} className="text-sky-400" /> Pan-India · {priorities?.length || 0} priority zones ·{' '}
          {(alerts || []).length} official alerts
        </div>
        <div className="flex items-center gap-1 text-slate-500">
          <RefreshCw size={9} /> {connection === 'connected' ? 'Live updates' : connection} ·{' '}
          {updatedAt ? new Date(updatedAt).toLocaleTimeString('en-IN', { hour12: false }) : '—'}
        </div>
        <div className="text-slate-500">Click anywhere on the map to inspect that place</div>
      </div>
    </main>
  )
}
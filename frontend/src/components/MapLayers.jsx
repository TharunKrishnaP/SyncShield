import React from 'react'
import { Layers, Globe2, CloudRain, Wind } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

export default function MapLayers() {
  const { mapConfig, overlayState, toggleOverlay, baseId, setBaseId, windGrid, alerts } = useApp()

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
  const basemaps = mapConfig?.basemaps?.length ? mapConfig.basemaps : FALLBACK_BASEMAPS
  const overlays = mapConfig?.overlays || []
  const radar = overlays.find((o) => o.id === 'rain-radar')
  const imerg = overlays.find((o) => o.id === 'nasa-imerg')
  const daily = basemaps.find((b) => b.id === 'nasa-daily')
  const frameTime = (epoch) => (epoch ? new Date(epoch * 1000).toLocaleTimeString('en-IN', { hour12: false }) : '')

  return (
    <div className="rounded-xl border border-eoc-border bg-eoc-panel/80">
      <div className="px-3 py-2 border-b border-eoc-border flex items-center gap-1.5">
        <Layers size={12} className="text-sky-400" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Satellite &amp; Weather Layers</span>
      </div>
      <div className="p-2 space-y-2">
        <div>
          <div className="text-[9px] text-slate-500 font-bold uppercase mb-1 flex items-center gap-1">
            <Globe2 size={9} /> Base imagery
          </div>
          <div className="grid grid-cols-1 gap-0.5">
            {basemaps.map((b) => (
              <button
                key={b.id}
                onClick={() => setBaseId(b.id)}
                className={`w-full text-left text-[10px] px-2 py-1 rounded ${
                  baseId === b.id ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-700/40'
                }`}
              >
                {b.name}
              </button>
            ))}
          </div>
        </div>

        <div className="pt-1 border-t border-eoc-border">
          <div className="text-[9px] text-slate-500 font-bold uppercase mb-1 flex items-center gap-1">
            <CloudRain size={9} /> Precipitation &amp; wind
          </div>
          {radar && (
            <Toggle label="Live rain radar" hint={frameTime(radar.frame_time)} on={overlayState.radar} onClick={() => toggleOverlay('radar')} />
          )}
          {imerg && (
            <Toggle label="NASA satellite rainfall (IMERG)" hint="24h" on={overlayState.imerg} onClick={() => toggleOverlay('imerg')} />
          )}
          {daily && (
            <Toggle label="NASA daily satellite image" on={overlayState.daily} onClick={() => toggleOverlay('daily')} />
          )}
          <Toggle
            label="Rain-carrying winds"
            hint={`${(windGrid || []).length} vectors`}
            on={overlayState.wind}
            onClick={() => toggleOverlay('wind')}
            icon={Wind}
          />
        </div>

        <div className="pt-1 border-t border-eoc-border">
          <div className="text-[9px] text-slate-500 font-bold uppercase mb-1">Flood &amp; response</div>
          <Toggle label={`Official alerts (${(alerts || []).length})`} on onClick={() => {}} locked />
          <Toggle label="Flood risk zones" on={overlayState.priority} onClick={() => toggleOverlay('priority')} />
          <Toggle label="Flood extent (modelled SAR)" on={overlayState.flood} onClick={() => toggleOverlay('flood')} />
          <Toggle label="River gauges" on={overlayState.rivers} onClick={() => toggleOverlay('rivers')} />
          <Toggle label="Evacuation routes" on={overlayState.routes} onClick={() => toggleOverlay('routes')} />
          <Toggle label="Incident reports" on={overlayState.incidents} onClick={() => toggleOverlay('incidents')} />
          <Toggle label="Hospitals &amp; shelters" on={overlayState.infra} onClick={() => toggleOverlay('infra')} />
        </div>
      </div>
    </div>
  )
}

function Toggle({ label, hint, on, onClick, icon: Icon, locked }) {
  return (
    <button
      onClick={locked ? undefined : onClick}
      className={`w-full flex items-center justify-between text-[10px] px-2 py-1 rounded ${
        on ? 'text-slate-200' : 'text-slate-500'
      } ${locked ? 'cursor-default' : 'hover:bg-slate-700/40'}`}
    >
      <span className="flex items-center gap-1.5 truncate">
        <span className={`w-2 h-2 rounded-sm shrink-0 ${on ? 'bg-sky-400' : 'bg-slate-600'}`} />
        {Icon && <Icon size={9} />}
        {label}
      </span>
      {hint && <span className="text-[8px] text-slate-500 shrink-0 ml-1">{hint}</span>}
    </button>
  )
}
import React from 'react'
import { CircleMarker, Popup, Tooltip } from 'react-leaflet'
import { useApp } from '../../context/AppContext.jsx'

const LEVEL = {
  Red: { color: '#ef4444', radius: 13 },
  Orange: { color: '#f97316', radius: 10 },
  Green: { color: '#22c55e', radius: 7 },
}

export default function FloodEventMarkers() {
  const { alerts } = useApp()
  const list = (alerts || []).filter((a) => a.latitude && a.longitude)
  if (!list.length) return null

  return (
    <>
      {list.map((a) => {
        const style = LEVEL[a.alert_level] || LEVEL.Green
        return (
          <CircleMarker
            key={a.id}
            center={[a.latitude, a.longitude]}
            radius={style.radius}
            pathOptions={{ color: style.color, fillColor: style.color, fillOpacity: 0.35, weight: 2 }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <span className="text-[10px] font-semibold">{a.alert_level} flood alert</span>
            </Tooltip>
            <Popup>
              <div className="text-slate-900 text-xs leading-relaxed min-w-[190px]">
                <div className="font-bold text-sm">{a.title}</div>
                <div className="text-slate-500 mb-1">{a.country} · {a.source_full || a.source}</div>
                <div>Alert level: <b>{a.alert_level}</b></div>
                {a.from_date && <div>From: {String(a.from_date).slice(0, 10)}</div>}
                {a.description && <p className="mt-1 text-[11px] text-slate-600">{a.description}</p>}
                {a.url && (
                  <a href={a.url} target="_blank" rel="noreferrer" className="text-sky-600 underline mt-1 inline-block">
                    Official alert page
                  </a>
                )}
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </>
  )
}

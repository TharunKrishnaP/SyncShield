import React from 'react'
import { Gauge } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import LaymanBrief from './LaymanBrief.jsx'
import PlaceInfo from './PlaceInfo.jsx'
import MapLayers from './MapLayers.jsx'
import WaterLevelPanel from './WaterLevelPanel.jsx'
import PrecipitationPanel from './PrecipitationPanel.jsx'
import AlertsPanel from './AlertsPanel.jsx'
import SourceStatus from './SourceStatus.jsx'
import TimelineList from './TimelineList.jsx'

export default function SituationPanel() {
  const { regional } = useApp()

  return (
    <div className="flex flex-col min-h-0">
      <div className="px-2 pt-0.5 pb-2 flex items-center justify-between">
        <h2 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <Gauge size={13} className="text-sky-400" /> Flood Situation · All India
        </h2>
        <span className="text-[9px] text-slate-500">
          National index <b className="text-slate-300">{regional?.score ?? '—'}</b>/100
        </span>
      </div>
      <div className="flex flex-col gap-3">
        <PlaceInfo />
        <LaymanBrief />
        <MapLayers />
        <WaterLevelPanel />
        <PrecipitationPanel />
        <AlertsPanel />
        <SourceStatus />
        <TimelineList />
      </div>
    </div>
  )
}
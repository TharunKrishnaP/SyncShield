import React, { useCallback, useEffect, useRef, useState } from 'react'
import Header from './components/Header.jsx'
import NewsTicker from './components/NewsTicker.jsx'
import SituationPanel from './components/SituationPanel.jsx'
import MapPanel from './components/MapPanel.jsx'
import EmergencyPanel from './components/EmergencyPanel.jsx'
import PlaceSearch from './components/PlaceSearch.jsx'
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, GripVertical } from 'lucide-react'

function FloatPanel({ side, width, title, icon, color, children, bodyClass = '' }) {
  const [open, setOpen] = useState(true)
  const [pos, setPos] = useState(() => ({ x: 0, y: 0 }))
  const drag = useRef(null)

  const onPointerDown = (e) => {
    if (e.button !== 0) return
    drag.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y, id: e.pointerId }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = useCallback((e) => {
    if (!drag.current) return
    const dx = e.clientX - drag.current.sx
    const dy = e.clientY - drag.current.sy
    const maxX = side === 'left' ? Math.max(0, window.innerWidth - width - 90) : 0
    setPos({
      x: Math.max(0, Math.min(drag.current.ox + dx, maxX)),
      y: Math.max(0, drag.current.oy + dy),
    })
  }, [side, width])
  const endDrag = (e) => {
    if (!drag.current) return
    try {
      e.currentTarget.releasePointerCapture(drag.current.id)
    } catch {
      /* noop */
    }
    drag.current = null
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Open panel"
        className={`absolute top-1/2 -translate-y-1/2 z-[1100] flex items-center gap-1 px-1.5 py-3 rounded-lg border border-eoc-border bg-eoc-panel/95 text-slate-400 hover:text-sky-300 shadow-lg ${
          side === 'left' ? 'left-0' : 'right-0'
        }`}
      >
        {side === 'left' ? <PanelLeftOpen size={14} /> : <PanelRightOpen size={14} />}
      </button>
    )
  }

  return (
    <aside
      className={`absolute top-2 ${side === 'left' ? 'left-2' : 'right-2'} bottom-2 z-[1100] flex flex-col min-h-0 rounded-xl border border-eoc-border bg-eoc-panel/85 backdrop-blur-md shadow-2xl`}
      style={{ width, transform: `translate(${pos.x}px, ${pos.y}px)`, maxHeight: 'calc(100% - 16px)' }}
    >
      <div
        className="flex items-center gap-2 px-2 py-1 border-b border-eoc-border rounded-t-xl shrink-0 cursor-grab active:cursor-grabbing select-none touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <GripVertical size={11} className="text-slate-600 shrink-0" />
        <span className="flex-1 text-[8px] uppercase tracking-[0.25em] text-slate-600">drag to reposition</span>
        <button
          onClick={() => setOpen(false)}
          title="Collapse panel"
          className={`shrink-0 p-0.5 rounded-md text-slate-500 hover:text-slate-200 hover:bg-slate-700/40`}
        >
          {side === 'left' ? <PanelLeftClose size={12} /> : <PanelRightClose size={12} />}
        </button>
      </div>
      <div className={`overflow-y-auto flex-1 min-h-0 rounded-b-xl ${bodyClass}`}>{children}</div>
    </aside>
  )
}

export default function App() {
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-eoc-bg text-slate-200">
      <Header />
      <NewsTicker />
      <div className="flex-1 relative min-h-0 overflow-hidden">
        <MapPanel />

        <FloatPanel side="left" width={352}>
          <SituationPanel />
        </FloatPanel>

        <FloatPanel side="right" width={376}>
          <EmergencyPanel />
        </FloatPanel>

        <PlaceSearch />
      </div>
    </div>
  )
}
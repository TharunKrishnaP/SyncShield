import React from 'react'

const items = [
  { color: '#ef4444', label: 'Priority 1 (Critical)' },
  { color: '#f97316', label: 'Priority 2 (High)' },
  { color: '#eab308', label: 'Priority 3 (Monitor)' },
  { color: '#22c55e', label: 'Priority 4 (Low)' },
  { color: '#38bdf8', label: 'SAR flood extent' },
  { color: '#f43f5e', label: 'Hospital' },
  { color: '#3b82f6', label: 'Rescue base' },
  { color: '#8b5cf6', label: 'Relief shelter' },
  { color: '#ef4444', label: 'Direct route (unsafe)' },
  { color: '#22c55e', label: 'Recommended route' },
]

export default function MapLegend() {
  return (
    <div className="absolute bottom-2 left-2 z-[500] bg-eoc-panel/90 border border-eoc-border rounded-lg p-2.5 w-40 shadow-lg">
      <div className="text-[9px] font-bold uppercase tracking-wider text-slate-400 mb-2">Legend</div>
      <div className="space-y-1">
        {items.map((it) => (
          <div key={it.label} className="flex items-center gap-2 text-[10px] text-slate-300">
            <span className="w-3 h-3 rounded-full shrink-0" style={{ background: it.color, opacity: 0.8 }} />
            {it.label}
          </div>
        ))}
        <div className="flex items-center gap-2 text-[10px] text-slate-300 pt-1 border-t border-eoc-border">
          <span className="text-sky-400 font-bold shrink-0">↓</span>
          Rain-carrying wind (size = speed)
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-300">
          <span className="w-3 h-3 rounded shrink-0" style={{ background: 'linear-gradient(90deg,#22d3ee,#3b82f6,#ef4444)' }} />
          Live rain radar
        </div>
      </div>
    </div>
  )
}

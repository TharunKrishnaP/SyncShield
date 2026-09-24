import React from 'react'
import { useApp } from '../context/AppContext.jsx'

function colorForScore(score) {
  if (score > 80) return '#ef4444'
  if (score > 60) return '#f97316'
  if (score > 40) return '#eab308'
  if (score > 20) return '#22c55e'
  return '#38bdf8'
}

const RADIUS = 66
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export default function SeverityGauge() {
  const { regional, simulation } = useApp()
  const score = regional?.score ?? 0
  const status = regional?.status ?? 'NO DATA'
  const trend = regional?.last_updated ? 'live' : '—'
  const color = colorForScore(score)
  const dash = (score / 100) * CIRCUMFERENCE
  const deteriorating = (regional?.deteriorating_zones?.length ?? 0) > 0

  return (
    <div className="rounded-xl border border-eoc-border bg-slate-900/50 p-4 flex flex-col items-center">
      <div className="relative w-[160px] h-[160px]">
        <svg viewBox="0 0 160 160" className="w-full h-full -rotate-90">
          <circle cx="80" cy="80" r={RADIUS} fill="none" stroke="#1e2a45" strokeWidth="12" />
          <circle
            cx="80"
            cy="80"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${CIRCUMFERENCE}`}
            style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.6s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-4xl font-extrabold" style={{ color }}>
            {score}
          </span>
          <span className="text-[10px] uppercase tracking-widest text-slate-400">/ 100</span>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span
          className="px-3 py-1 rounded-md text-xs font-bold uppercase tracking-wide"
          style={{ background: `${color}22`, color }}
        >
          {status}
        </span>
        {deteriorating && (
          <span className="px-2 py-1 rounded-md text-[10px] font-semibold bg-red-500/15 text-red-400 animate-pulse">
            Δ Deteriorating
          </span>
        )}
      </div>
      <p className="mt-1 text-[10px] text-slate-500">
        All-India regional index · population-weighted · {simulation?.time_label || 'live'}
      </p>
    </div>
  )
}
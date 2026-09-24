import React from 'react'

export default function Sparkline({
  values = [],
  width = 96,
  height = 22,
  stroke = '#38bdf8',
  fillOpacity = 0.15,
  strokeWidth = 1.5,
}) {
  if (!values || values.filter((v) => v !== null && v !== undefined).length < 2) return null
  const nums = values.map((v) => (v === null || v === undefined ? 0 : Number(v)))
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const span = max - min || 1
  const pad = 2
  const step = nums.length > 1 ? (width - pad * 2) / (nums.length - 1) : 0
  const pts = nums.map((v, i) => {
    const x = pad + i * step
    const y = pad + (1 - (v - min) / span) * (height - pad * 2)
    return [x, y]
  })
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${lastX(pts)},${height} L${firstX(pts)},${height} Z`

  function lastX(p) {
    return p[p.length - 1][0].toFixed(1)
  }
  function firstX(p) {
    return p[0][0].toFixed(1)
  }

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0">
      <path d={area} fill={stroke} fillOpacity={fillOpacity} />
      <path d={line} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
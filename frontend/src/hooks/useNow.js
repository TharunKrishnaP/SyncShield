import { useEffect, useState } from 'react'

export function useNow(intervalMs = 2000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

export function ageSeconds(now, iso) {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (isNaN(t)) return null
  return Math.max(0, Math.round((now - t) / 1000))
}

export function fmtAge(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m ago`
}
const API_BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: isForm ? undefined : { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  initialBundle: () => request('/api/initial'),
  situationCurrent: () => request('/api/situation/current'),
  situationZones: () => request('/api/situation/zones'),
  brief: () => request('/api/brief'),
  priorities: () => request('/api/zones/priority'),
  layers: () => request('/api/map/layers'),
  mapConfig: () => request('/api/map/config'),
  waterLevels: (limit = 80) => request(`/api/panel/water-levels?limit=${limit}`),
  precipitation: (limit = 200) => request(`/api/panel/precipitation?limit=${limit}`),
  wind: () => request('/api/panel/wind'),
  alerts: (limit = 25) => request(`/api/panel/alerts?limit=${limit}`),
  floodEvents: () => request('/api/flood-events'),
  contacts: () => request('/api/emergency/contacts'),
  evacuation: () => request('/api/evacuation'),
  incidents: (limit = 50) => request(`/api/incidents?limit=${limit}`),
  submitIncident: (text, source = 'CITIZEN_REPORT', zoneId = null) =>
    request('/api/incidents', {
      method: 'POST',
      body: JSON.stringify({ text, source, zone_id: zoneId }),
    }),
  simulationStep: (action) =>
    request('/api/simulation/step', {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  evaluateRoute: (payload) =>
    request('/api/routing/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  recommendations: () => request('/api/recommendations'),
  conflicts: () => request('/api/conflicts'),
  dataSources: () => request('/api/data-sources'),
  zoneList: () => request('/api/zones/list'),
  refresh: () => request('/api/refresh', { method: 'POST' }),
  historySummary: () => request('/api/history/summary'),
  waterHistory: (ids, hours = 24) => request(`/api/history/water?station_ids=${ids.join(',')}&hours=${hours}`),
  precipHistory: (ids, hours = 24) => request(`/api/history/precip?zone_ids=${ids.join(',')}&hours=${hours}`),
  citizenReport: (formData) => request('/api/citizen/reports', { method: 'POST', body: formData }),
  citizenStatus: (reportId) => request(`/api/citizen/reports/${reportId}`),
  areaCheck: (body) => request('/api/citizen/area-check', { method: 'POST', body: JSON.stringify(body) }),
  officialTemplates: () => request('/api/official/templates'),
  officialIngest: (formData) => request('/api/official/ingest', { method: 'POST', body: formData }),
  news: (limit = 30) => request(`/api/news?limit=${limit}`),
  searchPlaces: (q, limit = 8) => request(`/api/places/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  nearby: (lat, lon, k = 6) => request(`/api/places/nearby?lat=${lat}&lon=${lon}&k=${k}`),
}

export function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  return `${proto}://${host}/api/ws`
}

import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { api, wsUrl } from '../utils/api'

const AppContext = createContext(null)

const INITIAL_STATE = {
  regional: null,
  zones: {},
  priorities: [],
  conflicts: [],
  explanations: {},
  routes: [],
  recommendations: [],
  incidents: [],
  timeline: [],
  simulation: null,
  brief: null,
  waterLevels: [],
  precipitation: [],
  windGrid: [],
  alerts: [],
  sources: { sources: [], summary: {} },
  news: [],
  updatedAt: null,
  refreshIntervalSeconds: 60,
}

export function AppProvider({ children }) {
  const [state, setState] = useState(INITIAL_STATE)
  const [connection, setConnection] = useState('connecting')
  const [layers, setLayers] = useState({ satellite_extents: [], zones_geojson: [], infrastructure: {} })
  const [mapConfig, setMapConfig] = useState(null)
  const [contacts, setContacts] = useState(null)
  const [evacuation, setEvacuation] = useState(null)
  const [zoneMeta, setZoneMeta] = useState({ zones: [], basins: [] })
  const wsRef = useRef(null)
  const reconnectRef = useRef(null)

  const loadInitial = useCallback(async () => {
    try {
      // ONE round trip instead of ~15: /api/initial returns every slice the
      // dashboard needs, gathered server-side from the same handlers the old
      // fan-out called. Each slice carries the exact shape its panel already
      // knows; a failing slice is `{}` and only empties that panel.
      const b = await api.initialBundle()
      const current = b.situation || {}
      setState({
        regional: current.regional ?? null,
        zones: (b.situation_zones || {}).zones || {},
        priorities: (b.zones_priority || {}).priorities || [],
        conflicts: [],
        explanations: {},
        routes: (b.layers || {}).routes || [],
        recommendations: (b.recommendations || {}).recommendations || [],
        incidents: (b.incidents || {}).incidents || [],
        timeline: [],
        simulation: current.simulation ?? null,
        brief: current.brief ?? null,
        waterLevels: (b.water_levels || {}).stations || [],
        precipitation: (b.precipitation || {}).records || [],
        windGrid: (b.wind || {}).wind_grid || [],
        alerts: (b.alerts || {}).alerts || [],
        sources: current.sources ? { sources: [], summary: current.sources } : { sources: [], summary: {} },
        updatedAt: current.updated_at ?? b.updated_at ?? null,
        refreshIntervalSeconds: current.refresh_interval_seconds || 60,
        news: (b.news || {}).news || [],
      })
      setLayers((prev) => ({ ...prev, ...(b.layers || {}) }))
      setMapConfig(b.map_config || null)
      setContacts(b.contacts || null)
      setEvacuation(b.evacuation || null)
      setZoneMeta(b.zones_list || { zones: [], basins: [] })
      if (b.data_sources) {
        setState((prev) => ({
          ...prev,
          sources: { sources: b.data_sources.sources || [], summary: b.data_sources.summary || {} },
        }))
      }
    } catch (err) {
      console.error('Failed to load initial data', err)
    }
  }, [])

  useEffect(() => {
    loadInitial()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      api.evacuation().then(setEvacuation).catch(() => {})
    }, 60000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    let disposed = false
    const connect = () => {
      if (disposed) return
      try {
        const ws = new WebSocket(wsUrl())
        wsRef.current = ws
        ws.onopen = () => setConnection('connected')
        ws.onmessage = (evt) => {
          try {
            const data = JSON.parse(evt.data)
            if (data.type === 'ping') return
            applyState(data)
          } catch (err) {
            /* ignore */
          }
        }
        ws.onclose = () => {
          setConnection('reconnecting')
          if (!disposed) reconnectRef.current = setTimeout(connect, 3000)
        }
        ws.onerror = () => ws.close()
      } catch (err) {
        setConnection('offline')
      }
    }
    connect()
    return () => {
      disposed = true
      clearTimeout(reconnectRef.current)
      if (wsRef.current) wsRef.current.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (connection === 'connected') return
    const id = setInterval(async () => {
      try {
        const [current, water, precip, wind, alerts, ds, newsData] = await Promise.all([
          api.situationCurrent(),
          api.waterLevels(),
          api.precipitation(),
          api.wind(),
          api.alerts(),
          api.dataSources(),
          api.news(30),
        ])
        applyState({
          regional: current.regional,
          simulation: current.simulation,
          brief: current.brief,
          updated_at: current.updated_at,
          refresh_interval_seconds: current.refresh_interval_seconds,
          water_levels: water.stations,
          precipitation: precip.records,
          wind_grid: wind.wind_grid,
          alerts: alerts.alerts,
          sources: { sources: ds.sources || [], summary: ds.summary || {} },
          news: newsData.news || [],
        })
      } catch (err) {
        /* keep last state */
      }
    }, 20000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection])

  function applyState(data) {
    if (!data) return
    setState((prev) => ({
      ...prev,
      regional: data.regional ?? prev.regional,
      zones: data.zones ?? prev.zones,
      priorities: data.priorities ?? prev.priorities,
      conflicts: data.conflicts ?? prev.conflicts,
      explanations: data.explanations ?? prev.explanations,
      routes: data.routes ?? prev.routes,
      recommendations: data.recommendations ?? prev.recommendations,
      incidents: data.incidents ?? prev.incidents,
      timeline: data.timeline ?? prev.timeline,
      simulation: data.simulation ?? prev.simulation,
      brief: data.brief ?? prev.brief,
      waterLevels: data.water_levels ?? prev.waterLevels,
      precipitation: data.precipitation ?? prev.precipitation,
      windGrid: data.wind_grid ?? prev.windGrid,
      alerts: data.alerts ?? prev.alerts,
      sources: data.sources ?? prev.sources,
      news: data.news ?? prev.news,
      updatedAt: data.updated_at ?? prev.updatedAt,
      refreshIntervalSeconds: data.refresh_interval_seconds ?? prev.refreshIntervalSeconds,
    }))
    if (data.zones || data.routes || data.incidents) {
      setLayers((prev) => ({ ...prev, routes: data.routes ?? prev.routes }))
    }
  }

  const addRoute = (route) => {
    if (!route) return
    setLayers((prev) => ({
      ...prev,
      routes: [...(prev.routes || []).filter((r) => r !== route), route].slice(-12),
    }))
  }

  const [selectedPlace, setSelectedPlace] = useState(null)
  const [focus, setFocus] = useState(null) // { lat, lon, zoom, seq }
  const [baseId, setBaseId] = useState('satellite')
  const [overlayState, setOverlayState] = useState({
    radar: true,
    imerg: false,
    daily: false,
    wind: true,
    priority: true,
    flood: true,
    rivers: true,
    infra: false,
    routes: true,
    incidents: true,
  })
  const toggleOverlay = (k) => setOverlayState((prev) => ({ ...prev, [k]: !prev[k] }))

  const pickPlace = (place) => {
    const p =
      typeof place === 'string'
        ? { name: place }
        : place && typeof place.lat === 'number'
          ? place
          : null
    setSelectedPlace(p)
    if (p && typeof p.lat === 'number') {
      setFocus((prev) => ({ lat: p.lat, lon: p.lon, zoom: p.zoom || 15, seq: (prev?.seq || 0) + 1 }))
    }
  }

  const value = {
    ...state,
    connection,
    layers,
    mapConfig,
    contacts,
    evacuation,
    zoneMeta,
    api,
    setLayers,
    applyState,
    loadInitial,
    addRoute,
    selectedPlace,
    setSelectedPlace,
    pickPlace,
    focus,
    setFocus,
    baseId,
    setBaseId,
    overlayState,
    toggleOverlay,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}

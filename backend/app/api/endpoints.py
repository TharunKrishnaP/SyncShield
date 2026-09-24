"""FastAPI REST endpoints for the FDR DataLake backend.

Organised around the three dashboard panels:
  * left  — water levels, precipitation records, flood situation
  * middle — satellite map layers, flood events, wind field
  * right — emergency contacts, evacuation and safety routing
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from ..orchestrator import orchestrator
from ..ingestion.source_registry import registry
from ..ingestion.map_tiles import map_tiles
from ..models.emergency_data import contacts_payload


router = APIRouter()


# ---- Request schemas ----

class IncidentSubmitRequest(BaseModel):
    text: str
    source: str = "CITIZEN_REPORT"
    zone_id: Optional[str] = None

class SimulationActionRequest(BaseModel):
    action: str

class RouteEvalRequest(BaseModel):
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    origin_name: str = "Origin"
    dest_name: str = "Destination"


async def _ensure_state():
    if not orchestrator._current:
        await orchestrator.refresh(force=True)
    return orchestrator._current


# ---- Situation ----

@router.get("/situation/current")
async def situation_current():
    state = await _ensure_state()
    return {
        "regional": state.get("regional"),
        "simulation": state.get("simulation"),
        "brief": state.get("brief"),
        "sources": state.get("sources", {}).get("summary"),
        "updated_at": state.get("updated_at"),
        "refresh_interval_seconds": state.get("refresh_interval_seconds", 60),
    }


@router.get("/brief")
async def situation_brief():
    state = await _ensure_state()
    return {"brief": state.get("brief")}


@router.get("/situation/timeline")
async def situation_timeline():
    return {"timeline": orchestrator.simulation.events(30)}


@router.get("/situation/zones")
async def situation_zones():
    state = await _ensure_state()
    return {"zones": state.get("zones", {}), "updated_at": state.get("updated_at")}


@router.get("/situation/zone/{zone_id}")
async def situation_zone(zone_id: str):
    state = await _ensure_state()
    zone = state.get("zones", {}).get(zone_id)
    if not zone:
        return {"error": f"Zone {zone_id} not found"}
    return {"zone": zone, "explanation": state.get("explanations", {}).get(zone_id)}


# ---- Left panel: water levels, precipitation, flood situation ----

@router.get("/panel/water-levels")
async def panel_water_levels(limit: int = Query(44, ge=1, le=200)):
    state = await _ensure_state()
    rows = state.get("water_levels", [])
    return {"count": len(rows), "stations": rows[:limit], "updated_at": state.get("updated_at")}


@router.get("/panel/precipitation")
async def panel_precipitation(limit: int = Query(20, ge=1, le=200)):
    state = await _ensure_state()
    rows = state.get("precipitation", [])
    return {"count": len(rows), "records": rows[:limit], "updated_at": state.get("updated_at")}


@router.get("/panel/wind")
async def panel_wind():
    state = await _ensure_state()
    return {"wind_grid": state.get("wind_grid", []), "updated_at": state.get("updated_at")}


@router.get("/panel/alerts")
async def panel_alerts(limit: int = Query(25, ge=1, le=200)):
    state = await _ensure_state()
    alerts = state.get("alerts", [])
    return {"count": len(alerts), "alerts": alerts[:limit], "updated_at": state.get("updated_at")}


@router.get("/flood-events")
async def flood_events():
    state = await _ensure_state()
    alerts = state.get("alerts", [])
    zones = state.get("zones", {})
    hot = [
        {
            "zone_id": zid,
            "name": z.get("district") or z.get("zone_name"),
            "state": z.get("state"),
            "level": z.get("severity_level"),
            "score": z.get("overall_score"),
        }
        for zid, z in zones.items()
        if (z.get("overall_score") or 0) >= 40
    ]
    hot.sort(key=lambda z: z["score"], reverse=True)
    return {
        "official_alerts": alerts,
        "affected_zones": hot,
        "alert_count": len(alerts),
        "affected_count": len(hot),
        "updated_at": state.get("updated_at"),
    }


# ---- Zones registry ----

@router.get("/zones/list")
async def zones_list():
    from ..models.india_data import ZONES, BASINS
    return {"zones": ZONES, "basins": BASINS, "count": len(ZONES)}


@router.get("/zones/priority")
async def rescue_priority():
    state = await _ensure_state()
    return {"priorities": state.get("priorities", [])}


# ---- Map ----

@router.get("/map/config")
async def map_config():
    return await map_tiles.config()


@router.get("/map/layers")
async def map_layers():
    state = await _ensure_state()
    dl = orchestrator.datalake

    from ..models.india_data import RIVER_STATIONS
    river_stations = []
    for st in RIVER_STATIONS:
        sid, name, river, basin, st_state, lat, lon, wl, dl_val, hfl, stype = st
        latest = dl.get_river(sid).get("latest") or {}
        river_stations.append({
            "id": sid,
            "name": name,
            "river": river,
            "basin": basin,
            "state": st_state,
            "latitude": lat,
            "longitude": lon,
            "warning_level": wl,
            "danger_level": dl_val,
            "highest_flood_level": hfl,
            "station_type": stype,
            "latest": latest,
            "water_level": latest.get("water_level"),
            "status": latest.get("status", "NORMAL"),
            "rate_of_rise": latest.get("rate_of_rise", 0),
            "flow_ratio": latest.get("flow_ratio"),
            "flow_plain": latest.get("flow_plain"),
            "discharge": latest.get("discharge"),
        })

    infra = dl.list("infrastructure")
    # Modelled/simulated extents fill the most-recent-25 slots; ML U-Net
    # extents are appended LAST so the frontend's per-zone dedupe
    # (last entry wins) always keeps the trained model's prediction.
    all_extents = dl.get_satellite_extents()
    ml_extents = [e for e in all_extents if (e.get("data_source") or "").startswith("ML_SAR")]
    ml_ids = {e.get("id") for e in ml_extents}
    other_extents = [e for e in all_extents if e.get("id") not in ml_ids][-25:]
    return {
        "satellite_extents": other_extents + ml_extents,
        "zones_geojson": dl.zones_all(),
        "infrastructure": infra,
        "routes": state.get("routes", []),
        "river_stations": river_stations,
        "roads": infra.get("roads", []),
        "wind_grid": state.get("wind_grid", []),
        "alerts": state.get("alerts", []),
        "updated_at": state.get("updated_at"),
    }


# ---- Right panel: emergency, evacuation, routing ----

@router.get("/emergency/contacts")
async def emergency_contacts():
    return orchestrator.emergency_contacts()


@router.get("/emergency/helplines")
async def emergency_helplines():
    return {"helplines": contacts_payload()["helplines"]}


@router.get("/evacuation")
async def evacuation():
    return orchestrator.evacuation_info()


@router.post("/routing/evaluate")
async def evaluate_route(req: RouteEvalRequest):
    return orchestrator.evaluate_route(
        origin_lat=req.origin_lat,
        origin_lon=req.origin_lon,
        dest_lat=req.dest_lat,
        dest_lon=req.dest_lon,
        origin_name=req.origin_name,
        dest_name=req.dest_name,
    )


# ---- Incidents ----

@router.get("/incidents")
async def get_incidents(limit: int = Query(50, ge=1, le=500), zone: Optional[str] = None):
    incidents = orchestrator.datalake.get_incidents(limit=limit, zone=zone)
    return {"incidents": incidents, "count": len(incidents)}


@router.post("/incidents")
async def submit_incident(req: IncidentSubmitRequest):
    incident = await orchestrator.submit_incident(
        text=req.text,
        source=req.source,
        explicit_zone=req.zone_id,
    )
    return {"incident": incident}


# ---- Simulation controls ----

@router.post("/simulation/step")
async def simulation_step(req: SimulationActionRequest):
    result = await orchestrator.simulation_step(action=req.action)
    return {"simulation": result.get("simulation"), "regional": result.get("regional")}


# ---- Recommendations & conflicts ----

@router.get("/recommendations")
async def get_recommendations():
    state = await _ensure_state()
    return {"recommendations": state.get("recommendations", [])}


@router.get("/conflicts")
async def get_conflicts():
    state = orchestrator._current
    return {"conflicts": state.get("conflicts", [])}


# ---- Data sources ----

@router.get("/data-sources")
async def data_sources():
    return {"sources": registry.snapshot(), "summary": registry.summary()}


@router.get("/initial")
async def initial_bundle():
    """Everything the dashboard needs for first paint — ONE request.

    The dashboard used to fan out ~15 parallel REST calls on mount. This
    machine's transport serialises requests and adds a flat ~2.1s on top of
    each, so that fan-out literally multiplied the per-feed connect cost
    (on this box every request — even /docs and pure 404s — pays it). Each
    panel therefore painted only after the SLOWEST feed in that fan-out.

    This endpoint returns the same slices in one round trip by delegating to
    the exact same handler functions the separate endpoints use. Every slice
    below is byte-identical in shape to what its /api/... endpoint returns,
    so each panel consumes its own slice with no remapping. A failing slice
    yields an empty dict for its key instead of blocking the rest.
    """
    coros = {
        "situation": situation_current(),
        "situation_brief": situation_brief(),
        "situation_zones": situation_zones(),
        "zones_list": zones_list(),
        "zones_priority": rescue_priority(),
        "map_config": map_config(),
        "layers": map_layers(),
        "water_levels": panel_water_levels(80),
        "precipitation": panel_precipitation(200),
        "wind": panel_wind(),
        "alerts": panel_alerts(25),
        "flood_events": flood_events(),
        "incidents": get_incidents(50),
        "recommendations": get_recommendations(),
        "contacts": emergency_contacts(),
        "evacuation": evacuation(),
        "data_sources": data_sources(),
        "news": _news_slice(),
    }
    keys = list(coros.keys())
    results = await asyncio.gather(*coros.values(), return_exceptions=True)
    return {
        key: (result if isinstance(result, dict) else {})
        for key, result in zip(keys, results)
    }


async def _news_slice():
    """News slice — same shape as /api/news (limit 30, matches old client)."""
    from ..news.feed import news_feed
    items = news_feed.items(100)
    return {"count": len(items), "news": items[:30]}
# ---- Refresh ----

@router.post("/refresh")
async def force_refresh():
    await orchestrator.refresh(force=True)
    return {"status": "refreshed"}


# ---- Health ----

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "2.0.0-india",
        "zones": len(orchestrator._current.get("zones", {})),
        "regional_score": orchestrator._current.get("regional", {}).get("score", 0),
        "live_sources": registry.summary().get("live", 0),
    }


# ---- WebSocket ----

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    queue = await orchestrator.subscribe()
    try:
        while True:
            try:
                state = await asyncio.wait_for(queue.get(), timeout=5.0)
                await ws.send_json(state)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        orchestrator.unsubscribe(queue)

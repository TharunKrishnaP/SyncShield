"""Time-series history endpoints backed by the SQLite history lake.

These power the sparklines in the dashboard so operators can see the last
hours of water level, rainfall and AI risk score per station/zone instead of
just a single snapshot.
"""
from typing import List, Optional

from fastapi import APIRouter, Query

from ..history.history_lake import history_lake

router = APIRouter()


@router.get("/history/summary")
async def history_summary():
    return {"history": history_lake.summary()}


@router.get("/history/water")
async def water_history(
    station_ids: str = Query(..., description="Comma-separated station ids, e.g. BR-PATNA,OD-CUTTACK"),
    hours: int = Query(24, ge=1, le=24 * 30),
):
    ids = [s.strip() for s in station_ids.split(",") if s.strip()]
    data = history_lake.water_history_many(ids, hours=hours)
    return {"hours": hours, "series": data, "count": len(data)}


@router.get("/history/precip")
async def precip_history(
    zone_ids: str = Query(..., description="Comma-separated zone ids, e.g. KL-KOTTAYAM,AS-GUWAHATI"),
    hours: int = Query(24, ge=1, le=24 * 30),
):
    ids = [s.strip() for s in zone_ids.split(",") if s.strip()]
    data = history_lake.precip_history_many(ids, hours=hours)
    return {"hours": hours, "series": data, "count": len(data)}


@router.get("/history/risk")
async def risk_history(
    zone_ids: str = Query(..., description="Comma-separated zone ids"),
    hours: int = Query(24, ge=1, le=24 * 30),
):
    ids = [s.strip() for s in zone_ids.split(",") if s.strip()]
    out = [{"zone_id": zid, "points": history_lake.risk_history(zid, hours=hours)} for zid in ids]
    return {"hours": hours, "series": out, "count": len(out)}


@router.get("/history/top")
async def top_history():
    """Zones/stations with the most recorded history (to warm sparklines quickly)."""
    return {
        "top_river_stations": _top_table("water_levels", "station_id"),
        "top_precip_zones": _top_table("precipitation", "zone_id"),
    }


def _top_table(table: str, key: str, limit: int = 20) -> List[dict]:
    conn = history_lake._connect()
    try:
        rows = conn.execute(
            f"SELECT {key} AS id, COUNT(*) AS samples, MAX(ts) AS newest FROM {table} GROUP BY {key} ORDER BY samples DESC LIMIT {int(limit)}"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
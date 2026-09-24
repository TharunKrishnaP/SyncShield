"""India-wide place search for map & routing.

Search lets users pick *any* place in India — from the offline locator
registry (priority zones, river gauges, flood-prone towns) and, when the
network is available, live OpenStreetMap geography via Nominatim — so routes,
area-checks and map inspection can target every nook and corner of the country.
"""
import asyncio
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Query

from ..models.india_locator import LOCATOR_POINTS
from ..ingestion.source_registry import registry

router = APIRouter()

NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "AIFloodEOC-Dashboard/2.0 (flood-response dashboard; contact: local)"

_nominatim_client: Optional[httpx.AsyncClient] = None

_TOKEN_FIELDS = ("name", "district", "state", "basin", "river")


def _tokens(row: Dict[str, Any]) -> str:
    return " ".join(str(row.get(f) or "") for f in _TOKEN_FIELDS).lower()


def _match_score(q: str, row: Dict[str, Any]) -> int:
    tblob = _tokens(row).split()
    qparts = [p for p in q.lower().split() if p]
    if not qparts:
        return 0
    best = 0
    for p in qparts:
        for t in tblob:
            if t == p:
                best += 10
            elif t.startswith(p):
                best += 6
            elif p in t:
                best += 3
    # prefix match on the place name itself is the strongest signal
    name = (row.get("name") or "").lower()
    if name == q.lower():
        best += 50
    elif name.startswith(q.lower()):
        best += 25
    return best


def _format_offline(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": row.get("name"),
        "full_name": ", ".join(
            str(x) for x in (row.get("name"), row.get("district"), row.get("state")) if x and x != row.get("name")
        ),
        "state": row.get("state", ""),
        "district": row.get("district", ""),
        "basin": row.get("basin", ""),
        "river": row.get("river", ""),
        "region_type": row.get("type", "place"),
        "lat": row["lat"],
        "lon": row["lon"],
        "source": "locator",
        "distance_km": row.get("distance_km"),
    }


def _format_nominatim(rec: Dict[str, Any]) -> Dict[str, Any]:
    name = (rec.get("display_name") or "").split(",")[0].strip()
    parts = [p.strip() for p in (rec.get("display_name") or "").split(",")]
    state = parts[-3] if len(parts) >= 3 else ""
    district = parts[-2] if len(parts) >= 2 else ""
    return {
        "name": name,
        "full_name": ", ".join(p for p in parts[:4]),
        "state": state,
        "district": district,
        "basin": "",
        "river": "",
        "region_type": rec.get("class") or "place",
        "lat": float(rec["lat"]),
        "lon": float(rec["lon"]),
        "source": "osm",
        "importance": rec.get("importance"),
    }


async def _nominatim(q: str, limit: int) -> List[Dict[str, Any]]:
    global _nominatim_client
    if _nominatim_client is None:
        _nominatim_client = httpx.AsyncClient(timeout=8.0, headers={"User-Agent": NOMINATIM_UA})
    try:
        r = await _nominatim_client.get(
            NOMINATIM,
            params={
                "q": q,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": limit,
                "countrycodes": "in",
                "viewbox": "67.5,37.6,97.5,6.5",
                "bounded": 1,
            },
        )
        r.raise_for_status()
        out = r.json()
        registry.record("nominatim", ok=True, latency_ms=None, records=len(out))
        return [_format_nominatim(x) for x in out[:limit]]
    except Exception as exc:
        registry.record("nominatim", ok=False, error=str(exc))
        return []


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        key = (round(it.get("lat", 0), 3), round(it.get("lon", 0), 3), str(it.get("name", "")).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


@router.get("/places/search")
async def search_places(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(8, ge=1, le=20),
) -> Dict[str, Any]:
    """Search any place in India — offline registry first, then live OSM geocoding."""
    offline = []
    if len(q.strip()) >= 2:
        scored = [(row, _match_score(q.strip(), row)) for row in LOCATOR_POINTS]
        scored = [(r, s) for r, s in scored if s > 0]
        scored.sort(key=lambda x: (-x[1], x[0].get("name", "").lower()))
        offline = [_format_offline(r) for r, _ in scored[:limit]]

    online = await _nominatim(q.strip(), max(limit - len(offline), 1))

    results = _dedupe(offline + online)
    return {
        "query": q,
        "count": len(results),
        "results": results,
    }


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.get("/places/nearby")
async def places_nearby(
    lat: float = Query(...),
    lon: float = Query(...),
    k: int = Query(6, ge=1, le=12),
) -> Dict[str, Any]:
    """Nearest monitored places (zones / gauges / towns) to a point."""
    scored = []
    for p in LOCATOR_POINTS:
        row = dict(p)
        row["distance_km"] = round(_haversine(lat, lon, p["lat"], p["lon"]), 1)
        scored.append(row)
    scored.sort(key=lambda x: x["distance_km"])
    return {"lat": lat, "lon": lon, "count": min(k, len(scored)), "places": _dedupe([_format_offline(x) for x in scored[:k]])}
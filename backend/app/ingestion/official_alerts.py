"""Verified official disaster alerts from GDACS and NASA EONET.

GDACS is the Global Disaster Alert and Coordination System run by the European
Commission Joint Research Centre with UN OCHA — the feed humanitarian agencies
actually act on. NASA EONET is NASA's Earth Observatory Natural Event Tracker.

Both are key-free and machine readable. Alerts are filtered to India's
bounding box, normalised, de-duplicated and can be pushed into the incident
stream as *verified* reports.
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from .source_registry import registry

GDACS_KEY = "gdacs"
EONET_KEY = "eonet"

GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"

_ALERT_SCORE = {"Red": 90.0, "Orange": 65.0, "Green": 35.0}


def _in_india(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    return 6.5 <= lat <= 37.6 and 67.5 <= lon <= 97.5


def _first_point(geometry: Optional[Dict[str, Any]]) -> tuple:
    """Return (lat, lon) from any GeoJSON geometry, recursing into wrappers."""
    if not geometry:
        return None, None

    def _walk(coords):
        if isinstance(coords, (list, tuple)):
            if len(coords) >= 2 and all(isinstance(c, (int, float)) for c in coords[:2]):
                return coords[1], coords[0]
            for c in coords:
                lat, lon = _walk(c)
                if lat is not None:
                    return lat, lon
        return None, None

    return _walk(geometry.get("coordinates"))


class OfficialAlertsClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=25.0, headers={"User-Agent": "FDR-India/1.0 (+flood-response-datalake)"}
        )
        registry.register(
            GDACS_KEY,
            "GDACS Flood Alerts (European Commission JRC + UN OCHA)",
            "https://www.gdacs.org/",
            category="international",
            coverage="Global, filtered to India",
            plain_name="Official international flood alerts",
            what_it_gives="Verified flood alerts issued by the UN-backed GDACS alert system",
            realtime=True,
        )
        registry.register(
            EONET_KEY,
            "NASA EONET Natural Events",
            "https://eonet.gsfc.nasa.gov/",
            category="international",
            coverage="Global, filtered to India",
            plain_name="NASA natural event tracker",
            what_it_gives="NASA-tracked flood events observed from space",
            realtime=True,
        )
        registry.set_status(GDACS_KEY, "UNKNOWN")
        registry.set_status(EONET_KEY, "UNKNOWN")

    async def fetch_gdacs(self) -> List[Dict[str, Any]]:
        from_date = (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        params = {"eventlist": "FL", "fromDate": from_date, "toDate": to_date}
        r = await self._client.get(GDACS_URL, params=params)
        r.raise_for_status()
        features = (r.json() or {}).get("features", []) or []

        out: List[Dict[str, Any]] = []
        for f in features:
            props = f.get("properties") or {}
            lat, lon = _first_point(f.get("geometry"))
            if not _in_india(lat, lon):
                continue
            level = props.get("alertlevel") or "Green"
            url = props.get("url")
            if isinstance(url, dict):
                url = url.get("report") or url.get("details")
            out.append({
                "id": "GDACS-{}-{}".format(props.get("eventid"), props.get("episodeid")),
                "source": "GDACS",
                "source_full": "GDACS (EC JRC / UN OCHA)",
                "event_type": "FLOOD",
                "title": props.get("eventname") or "Flood event",
                "country": props.get("country") or "India",
                "alert_level": level,
                "severity": _ALERT_SCORE.get(level, 35.0),
                "latitude": lat,
                "longitude": lon,
                "from_date": props.get("fromdate"),
                "to_date": props.get("todate"),
                "url": url,
                "description": (props.get("htmldescription") or "").replace("<", " ").replace(">", " ")[:400],
                "verified": True,
            })
        return out

    async def fetch_eonet(self) -> List[Dict[str, Any]]:
        params = {"category": "floods", "days": 365}
        r = await self._client.get(EONET_URL, params=params)
        r.raise_for_status()
        events = (r.json() or {}).get("events", []) or []

        out: List[Dict[str, Any]] = []
        for ev in events:
            geoms = ev.get("geometry") or []
            if not geoms:
                continue
            g = geoms[-1]
            lat, lon = _first_point(g)
            if not _in_india(lat, lon):
                continue
            out.append({
                "id": ev.get("id") or "EONET-UNKNOWN",
                "source": "EONET",
                "source_full": "NASA EONET",
                "event_type": "FLOOD",
                "title": ev.get("title") or "Flood event",
                "country": "India",
                "alert_level": "Orange",
                "severity": 55.0,
                "latitude": lat,
                "longitude": lon,
                "from_date": g.get("date"),
                "to_date": None,
                "url": (ev.get("sources") or [{}])[0].get("url")
                if ev.get("sources") else "https://eonet.gsfc.nasa.gov/",
                "description": "Flood event tracked by NASA EONET: {}".format(ev.get("title") or ""),
                "verified": True,
            })
        return out

    async def _timed(self, key: str, coro) -> List[Dict[str, Any]]:
        started = time.perf_counter()
        try:
            out = await coro
            registry.record(key, ok=True, latency_ms=(time.perf_counter() - started) * 1000, records=len(out))
            return out
        except Exception as exc:
            registry.record(key, ok=False, error=str(exc))
            return []

    async def refresh(self) -> List[Dict[str, Any]]:
        gdacs, eonet = await asyncio.gather(
            self._timed(GDACS_KEY, self.fetch_gdacs()),
            self._timed(EONET_KEY, self.fetch_eonet()),
        )
        merged: Dict[str, Dict[str, Any]] = {}
        for a in gdacs + eonet:
            merged[a["id"]] = a
        alerts = sorted(merged.values(), key=lambda a: a.get("severity", 0), reverse=True)
        return alerts

"""Official government data connectors (IMD, CWC/NWDP, NDMA SACHET).

These connectors are fully wired into the refresh cycle but stay key-gated:
the moment an accredited API key is placed in ``.env`` (``IMD_API_KEY``,
``NWDP_API_KEY``, ``SACHET_API_KEY``), each connector flips from NEEDS_KEY to
LIVE/DEGRADED and feeds real official measurements into the datalake instead
of the scenario model.

A keyless ``OfficialBulletinIngestor`` is provided for the many official
datasets that are published as CSV / JSON / GeoJSON bulletins, so genuine
official data can be ingested immediately without waiting for API access.
"""
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings
from ..models.india_data import ZONE_INDEX, STATION_INDEX
from .source_registry import registry, LIVE, DEGRADED, NEEDS_KEY, UNAVAILABLE


@dataclass
class ConnectorResult:
    ok: bool
    records: int = 0
    error: Optional[str] = None


class IMDConnector:
    """India Meteorological Department district rain/forecast connector."""

    key_name = "IMD_API_KEY"

    def __init__(self):
        self.key = settings.IMD_API_KEY
        self.base = settings.IMD_API_BASE_URL
        if not self.key:
            registry.set_status("imd", NEEDS_KEY, "IMD issues API keys only to accredited agencies. Add IMD_API_KEY to .env to live-poll IMD.")

    async def fetch(self, weather_map: Dict[str, Dict[str, Any]]) -> ConnectorResult:
        if not self.key:
            return ConnectorResult(ok=False, error="IMD_API_KEY not configured")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                headers = {"X-API-Key": self.key}
                # IMD district forecast endpoint (accreditation). 52 zone calls
                # fanned out concurrently.
                ids = list(weather_map.keys())
                tasks = []
                for zid in ids:
                    z = ZONE_INDEX.get(zid)
                    if not z:
                        continue
                    url = f"{self.base}/district-forecast"
                    tasks.append(_get(client, headers, url, {"lat": z["lat"], "lon": z["lon"]}))
                responses = await _gather(tasks)
            merged = 0
            for zid, resp in zip(ids, responses):
                if resp is None:
                    continue
                rain = _pick(resp, "rainfall_mm", "precip", "rain")
                if rain is not None:
                    weather_map.setdefault(zid, {})["rain_imd_mm"] = float(rain)
                    weather_map[zid]["imd_live"] = True
                    merged += 1
            ok = merged > 0
            registry.record("imd", ok=ok, records=merged, error=None if ok else "IMD returned no usable rainfall rows", degraded=not ok)
            return ConnectorResult(ok=ok, records=merged)
        except Exception as exc:
            registry.record("imd", ok=False, records=0, error=str(exc))
            return ConnectorResult(ok=False, error=str(exc))


class NWDPConnector:
    """CWC National Water Data Portal river-level connector."""

    key_name = "NWDP_API_KEY"

    def __init__(self):
        self.key = settings.NWDP_API_KEY
        self.base = settings.NWDP_API_BASE_URL
        if not self.key:
            registry.set_status("cwc_nwdp", NEEDS_KEY, "NWDP telemetry needs CWC accreditation. Add NWDP_API_KEY to .env to live-poll CWC gauges.")

    async def fetch(self) -> ConnectorResult:
        if not self.key:
            return ConnectorResult(ok=False, error="NWDP_API_KEY not configured")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                headers = {"Authorization": f"Bearer {self.key}"}
                tasks = []
                for st in STATION_INDEX:
                    tasks.append(_get(client, headers, f"{self.base}/river_level_telemetry", {"station": st, "format": "json"}))
                responses = await _gather(tasks)
            readings: List[Dict[str, Any]] = []
            for st, resp in zip(STATION_INDEX, responses):
                if not resp:
                    continue
                level = _pick(resp, "water_level", "wl", "level")
                if level is None:
                    continue
                idx = STATION_INDEX[st]
                readings.append({
                    "station_id": st,
                    "timestamp": datetime.now().isoformat(),
                    "water_level": float(level),
                    "warning_level": float(_pick(resp, "warning_level", "wl_flag", "warning") or idx[7]),
                    "danger_level": float(_pick(resp, "danger_level", "dl_flag", "danger") or idx[8]),
                    "rate_of_rise": float(_pick(resp, "rate_of_rise", "rise") or 0.0),
                    "discharge": _pick(resp, "discharge", "flow"),
                    "state": idx[4],
                    "river": idx[2],
                    "basin": idx[3],
                    "data_source": "LIVE_CWC",
                    "water_level_source": "CWC_PUBLISHED",
                })
            ok = len(readings) > 0
            self._latest = readings
            registry.record("cwc_nwdp", ok=ok, records=len(readings), error=None if ok else "NWDP returned no water-level rows", degraded=not ok)
            return ConnectorResult(ok=ok, records=len(readings))
        except Exception as exc:
            registry.record("cwc_nwdp", ok=False, records=0, error=str(exc))
            return ConnectorResult(ok=False, error=str(exc))


class SACHETConnector:
    """NDMA SACHET CAP alert connector."""

    key_name = "SACHET_API_KEY"

    def __init__(self):
        self.key = settings.SACHET_API_KEY
        self.base = settings.SACHET_API_BASE_URL
        if not self.key:
            registry.set_status("sachet", NEEDS_KEY, "NDMA opens SACHET APIs to states/agencies on request. Add SACHET_API_KEY to .env for live CAP alerts.")

    async def fetch(self) -> ConnectorResult:
        if not self.key:
            return ConnectorResult(ok=False, error="SACHET_API_KEY not configured")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.get(f"{self.base}/api/cap/alerts", headers={"Authorization": f"Bearer {self.key}"})
                r.raise_for_status()
                payload = r.json()
            alerts = _extract_cap_alerts(payload)
            ok = len(alerts) > 0
            self._latest = alerts
            registry.record("sachet", ok=ok, records=len(alerts), error=None if ok else "No SACHET alerts", degraded=not ok)
            return ConnectorResult(ok=ok, records=len(alerts))
        except Exception as exc:
            registry.record("sachet", ok=False, records=0, error=str(exc))
            return ConnectorResult(ok=False, error=str(exc))


def _extract_cap_alerts(payload: Any) -> List[Dict[str, Any]]:
    alerts = []
    items = payload.get("alerts") or payload.get("features") or payload.get("data") or []
    if isinstance(payload, dict) and not items:
        items = [payload]
    for a in items:
        props = a.get("properties") if isinstance(a, dict) else {}
        if isinstance(a, dict) and "cap" in a:
            props = a["cap"]
        if not isinstance(props, dict):
            continue
        alerts.append({
            "id": str(props.get("identifier") or props.get("id") or ""),
            "title": props.get("headline") or props.get("title") or "NDMA alert",
            "description": props.get("description") or "",
            "alert_level": _cap_level(props.get("severity") or props.get("msgType") or "Unknown"),
            "severity": _severity_from_level(_cap_level(props.get("severity") or "")),
            "latitude": _as_float(props.get("lat") or props.get("latitude")),
            "longitude": _as_float(props.get("lon") or props.get("longitude")),
            "url": props.get("url") or "https://sachet.ndma.gov.in/",
            "source": "NDMA_SACHET",
        })
    return alerts


class OfficialConnectors:
    def __init__(self):
        self.imd = IMDConnector()
        self.cwc = NWDPConnector()
        self.sachet = SACHETConnector()

    @property
    def cwc_readings(self) -> List[Dict[str, Any]]:
        return getattr(self.cwc, "_latest", [])

    @property
    def sachet_alerts(self) -> List[Dict[str, Any]]:
        return getattr(self.sachet, "_latest", [])

    async def fetch_all(self, weather_map: Dict[str, Dict[str, Any]]) -> Dict[str, ConnectorResult]:
        imd = await self.imd.fetch(weather_map)
        cwc = await self.cwc.fetch()
        sachet = await self.sachet.fetch()
        return {"imd": imd, "cwc": cwc, "sachet": sachet}

    async def cwc_sachet_only(self) -> Dict[str, ConnectorResult]:
        """Refresh key-gated connectors without merging IMD rain into zones."""
        cwc = await self.cwc.fetch()
        sachet = await self.sachet.fetch()
        return {"imd": ConnectorResult(ok=False, error="IMD merge needs a full refresh"), "cwc": cwc, "sachet": sachet}


# ----------------------------------------------------------------------
# Keyless official bulletin ingestion (CSV / JSON / GeoJSON)
# ----------------------------------------------------------------------

class OfficialBulletinIngestor:
    """Turn official bulletin files (as published by CWC/IMD/NDMA/state EOCs)
    into datalake records. Format is detected from content; each source kind
    has a documented column/field contract."""

    def __init__(self, datalake):
        self.datalake = datalake

    def ingest(self, source: str, raw: bytes, format_hint: Optional[str] = None) -> Dict[str, Any]:
        text = raw.decode("utf-8-sig", errors="replace")
        if source == "cwc":
            rows = self._parse_cwc(text, format_hint)
            for r in rows:
                self.datalake.put_river_reading(r["station_id"], r)
        elif source == "imd":
            rows = self._parse_imd(text, format_hint)
            for r in rows:
                self.datalake.put_weather(r["zone_id"], r)
        elif source == "ndma":
            rows = self._parse_ndma(text, format_hint)
            for r in rows:
                self.datalake.add_incident(r)
        elif source == "eoc":
            rows = self._parse_eoc(text, format_hint)
            for r in rows:
                self.datalake.add_incident(r)
        else:
            raise ValueError(f"Unknown bulletin source '{source}'; use cwc|imd|ndma|eoc")

        self.datalake.log_event({
            "timestamp": datetime.now().isoformat(),
            "type": "OFFICIAL_BULLETIN",
            "message": f"Ingested {len(rows)} official {source.upper()} records",
        })
        registry.record("official_bulletin", ok=len(rows) > 0, records=len(rows), error=None if rows else "No rows parsed", degraded=False)
        return {"source": source, "rows": len(rows), "kind": source.upper()}

    # -- parsers -------------------------------------------------------
    def _parse_cwc(self, text: str, fmt: Optional[str]) -> List[Dict[str, Any]]:
        rows = []
        records = _parse_records(text, fmt)
        for rec in records:
            sid = rec.get("station_id") or rec.get("STATION_ID") or rec.get("station")
            wl = _as_float(rec.get("water_level") or rec.get("WL"))
            if not sid or wl is None:
                continue
            idx = STATION_INDEX.get(str(sid).upper())
            r = {
                "station_id": str(sid).upper(),
                "timestamp": rec.get("timestamp") or datetime.now().isoformat(),
                "water_level": wl,
                "warning_level": _as_float(rec.get("warning_level") or rec.get("WL_FLAG")) or (idx[7] if idx else None),
                "danger_level": _as_float(rec.get("danger_level") or rec.get("DL_FLAG")) or (idx[8] if idx else None),
                "rate_of_rise": _as_float(rec.get("rate_of_rise") or rec.get("RISE")) or 0.0,
                "discharge": _as_float(rec.get("discharge") or None),
                "state": idx[4] if idx else rec.get("state", ""),
                "river": idx[2] if idx else rec.get("river", ""),
                "basin": idx[3] if idx else rec.get("basin", ""),
                "data_source": "LIVE_CWC",
                "water_level_source": "CWC_BULLETIN",
            }
            if wl >= (r["danger_level"] or 10 ** 9):
                r["status"] = "EXTREME"
            elif wl >= (r["warning_level"] or 10 ** 9):
                r["status"] = "SEVERE"
            else:
                r["status"] = "NORMAL"
            rows.append(r)
        return rows

    def _parse_imd(self, text: str, fmt: Optional[str]) -> List[Dict[str, Any]]:
        rows = []
        records = _parse_records(text, fmt)
        for rec in records:
            zid = rec.get("zone_id") or rec.get("district")
            rain = _as_float(rec.get("rain_mm") or rec.get("rainfall_mm") or rec.get("rain"))
            if not zid or rain is None:
                continue
            z = ZONE_INDEX.get(str(zid).upper()) or _match_zone(str(zid))
            rows.append({
                "zone_id": z["id"] if z else str(zid).upper(),
                "zone_name": z["name"] if z else str(zid),
                "state": z["state"] if z else "",
                "basin": z["basin"] if z else "",
                "latitude": z["lat"] if z else None,
                "longitude": z["lon"] if z else None,
                "precipitation": rain,
                "rain": rain,
                "timestamp": rec.get("timestamp") or datetime.now().isoformat(),
                "data_source": "IMD_BULLETIN",
            })
        return rows

    def _parse_ndma(self, text: str, fmt: Optional[str]) -> List[Dict[str, Any]]:
        rows = []
        features = json.loads(text)["features"] if (fmt == "geojson" or text.lstrip().startswith("{")) else json.loads(text)
        if not isinstance(features, list):
            raise ValueError("NDMA bulletin must be GeoJSON FeatureCollection with a features array")
        for f in features:
            p = f.get("properties", {}) if isinstance(f, dict) else {}
            if not isinstance(p, dict):
                continue
            rows.append({
                "id": f"ndma_{p.get('identifier') or len(rows)}",
                "timestamp": datetime.now().isoformat(),
                "zone_id": _match_zone_id(p.get("district") or p.get("zone")),
                "location_name": p.get("headline") or p.get("title") or "NDMA alert",
                "latitude": _as_float(p.get("lat") or p.get("latitude")),
                "longitude": _as_float(p.get("lon") or p.get("longitude")),
                "state": p.get("state", ""),
                "district": p.get("district", ""),
                "category": "EVACUATION_NEEDED",
                "severity": _severity_from_level(p.get("severity") or "Moderate"),
                "description": p.get("description") or p.get("headline") or "",
                "source": "NDMA_SACHET",
                "confidence": 0.95,
                "verified": True,
                "nlp_extracted": {"official_bulletin": True, "alert_level": p.get("alert_level")},
            })
        return rows

    def _parse_eoc(self, text: str, fmt: Optional[str]) -> List[Dict[str, Any]]:
        rows = []
        records = _parse_records(text, fmt)
        for rec in records:
            zid = rec.get("zone_id") or rec.get("district") or rec.get("place")
            rows.append({
                "id": rec.get("id") or f"eoc_{len(rows)}",
                "timestamp": rec.get("timestamp") or datetime.now().isoformat(),
                "zone_id": _match_zone_id(str(zid)) if zid else None,
                "location_name": rec.get("location") or rec.get("place") or "Field report",
                "latitude": _as_float(rec.get("lat")),
                "longitude": _as_float(rec.get("lon")),
                "state": rec.get("state", ""),
                "district": rec.get("district", ""),
                "category": rec.get("category", "OTHER"),
                "severity": _as_float(rec.get("severity")) or 0.5,
                "description": rec.get("description") or rec.get("text") or "",
                "source": rec.get("source", "STATE_EOC"),
                "confidence": _as_float(rec.get("confidence")) or 0.8,
                "verified": bool(rec.get("verified", True)),
                "nlp_extracted": {"official_bulletin": True},
            })
        return rows


def _match_zone(name: str) -> Optional[Dict[str, Any]]:
    low = name.lower()
    for z in ZONE_INDEX.values():
        if low and low in z["name"].lower():
            return z
    return None


def _match_zone_id(value: str) -> Optional[str]:
    low = (value or "").upper()
    if low in ZONE_INDEX:
        return low
    z = _match_zone(value)
    return z["id"] if z else None


def _severity_from_level(level: str) -> float:
    lvl = str(level).lower()
    if any(w in lvl for w in ("extreme", "red", "critical", "warning")):
        return 0.9
    if any(w in lvl for w in ("severe", "orange", "severe")):
        return 0.7
    if any(w in lvl for w in ("moderate", "yellow", "watch")):
        return 0.5
    return 0.4


def _cap_level(severity: str) -> str:
    sev = str(severity).lower()
    if sev in ("extreme", "serious", "severe"):
        return "Red"
    if sev in ("moderate",):
        return "Orange"
    return "Yellow"


def _as_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None and str(v).strip() not in ("", "null", "None") else None
    except (TypeError, ValueError):
        return None


def _pick(obj: Dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in obj and obj[n] is not None:
            return obj[n]
    return None


async def _get(client, headers, url, params):
    try:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def _gather(tasks):
    if not tasks:
        return []
    r = await asyncio_gather_bounded(tasks)
    return r


async def asyncio_gather_bounded(tasks, concurrency: int = 12):
    import asyncio

    sem = asyncio.Semaphore(concurrency)

    async def wrapped(aw):
        async with sem:
            return await aw

    return await asyncio.gather(*(wrapped(t) for t in tasks))


def _parse_records(text: str, fmt: Optional[str]) -> List[Dict[str, Any]]:
    stripped = text.lstrip()
    if fmt == "csv" or (stripped.startswith(("station", "STATION", "zone", "district", "place")) and fmt != "json"):
        import csv as _csv

        try:
            reader = _csv.DictReader(io.StringIO(text))
            return [dict(row) for row in reader if any(v.strip() for v in row.values())]
        except Exception:
            pass
    try:
        data = json.loads(stripped)
    except Exception as exc:
        raise ValueError(f"Bulletin is neither JSON nor parseable CSV: {exc}")
    if isinstance(data, dict):
        return data.get("records") or data.get("data") or data.get("stations") or [data]
    if isinstance(data, list):
        return data
    raise ValueError("Unrecognised bulletin structure")


official_connectors = OfficialConnectors()
official_bulletin = OfficialBulletinIngestor


def auto_register_bulletin_source():
    registry.register(
        "official_bulletin",
        "Official bulletin ingest (CWC/IMD/NDMA/state EOC)",
        "uploaded bulletins",
        category="official_govt",
        coverage="All India",
        kind="file",
        requires_key=False,
        plain_name="Uploaded official bulletins",
        what_it_gives="Official CSV / JSON / GeoJSON bulletins imported by EOC staff",
        is_indian_govt=True,
        realtime=True,
    )
    registry.set_status("official_bulletin", UNAVAILABLE, "No bulletins uploaded yet — use POST /api/official/ingest to import official data.")
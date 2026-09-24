"""Live river discharge ingestion from the Copernicus GloFAS model.

Open-Meteo exposes the Copernicus Global Flood Awareness System (GloFAS)
river discharge reanalysis + forecast as a key-free JSON API. We query it at
the exact coordinates of every CWC gauge station
in the India registry, so every river marker on the map carries a genuinely
live, modelled discharge value and a flood anomaly ratio versus the local
climatological median.

No API key, no registration: https://open-meteo.com/en/docs/flood-api
"""
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from ..models.india_data import RIVER_STATIONS
from .source_registry import registry

SOURCE_KEY = "open_meteo_flood"
BASE = "https://flood-api.open-meteo.com/v1"
_CHUNK = 100  # stations per multi-point request (Open-Meteo safety ceiling)


class FloodForecastClient:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=20.0)
        registry.register(
            SOURCE_KEY,
            "Copernicus GloFAS River Discharge (via Open-Meteo)",
            "https://open-meteo.com/en/docs/flood-api",
            category="international",
            coverage="Every Indian CWC gauge (modelled)",
            plain_name="River flow (satellite model)",
            what_it_gives="How much water is flowing in each river right now and for the next 10 days",
            realtime=True,
        )

    async def fetch_station(self, lat: float, lon: float) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "river_discharge,river_discharge_mean,river_discharge_median,river_discharge_max",
            "forecast_days": 10,
            "timezone": "Asia/Kolkata",
        }
        r = await self._client.get(f"{BASE}/flood", params=params)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _normalise(station_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        daily = data.get("daily") or {}
        discharge = daily.get("river_discharge") or []
        mean = daily.get("river_discharge_mean") or []
        median = daily.get("river_discharge_median") or []
        peak = daily.get("river_discharge_max") or []
        times = daily.get("time") or []

        current = float(discharge[0]) if discharge and discharge[0] is not None else 0.0
        med = float(median[0]) if median and median[0] is not None else 0.0
        ratio = (current / med) if med > 0.01 else 1.0
        forecast_peak = max([p for p in peak if p is not None], default=None)

        return {
            "station_id": station_id,
            "timestamp": datetime.now().isoformat(),
            "discharge": round(current, 1),
            "discharge_mean": round(float(mean[0]), 1) if mean and mean[0] is not None else None,
            "discharge_median": round(med, 1),
            "discharge_forecast_peak": round(float(forecast_peak), 1) if forecast_peak is not None else None,
            "anomaly_ratio": round(min(ratio, 9.99), 2),
            "forecast": [
                {"date": t, "discharge": (round(float(d), 1) if d is not None else None)}
                for t, d in zip(times, discharge)
            ],
            "data_source": "OPEN_METEO_GLOFAS",
        }

    async def refresh_all(self) -> Dict[str, Dict[str, Any]]:
        """Fetch live GloFAS discharge for every CWC gauge station.

        The gauges are fetched in chunks of up to ``_CHUNK`` coordinates per
        multi-point request, with a bounded semaphore, so the whole network
        refreshes in a handful of parallel calls without exceeding Open-Meteo
        per-request limits. If a chunk response is unusable we fall back to
        per-station requests so the panel never goes cold.
        """
        started = time.perf_counter()

        def _record(ok, records, error=None, degraded=False):
            registry.record(
                SOURCE_KEY,
                ok=ok,
                latency_ms=(time.perf_counter() - started) * 1000,
                records=records,
                error=error,
                degraded=degraded,
            )

        # ---- try: batched multi-point requests ----
        def _slice_location(daily, idx):
            sliced = {}
            for key, val in (daily or {}).items():
                if not isinstance(val, list) or not val or not isinstance(val[0], list):
                    sliced[key] = val
                else:
                    sliced[key] = val[idx] if idx < len(val) else []
            return sliced

        chunks = [
            RIVER_STATIONS[i:i + _CHUNK]
            for i in range(0, len(RIVER_STATIONS), _CHUNK)
        ]
        sem = asyncio.Semaphore(6)

        async def _fetch_chunk(chunk):
            async with sem:
                lats = ",".join(str(st[5]) for st in chunk)
                lons = ",".join(str(st[6]) for st in chunk)
                params = {
                    "latitude": lats,
                    "longitude": lons,
                    "daily": "river_discharge,river_discharge_mean,river_discharge_median,river_discharge_max",
                    "forecast_days": 10,
                    "timezone": "Asia/Kolkata",
                }
                r = await self._client.get(f"{BASE}/flood", params=params)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict):
                    if data.get("error"):
                        raise RuntimeError(data.get("reason", "open-meteo flood multi-point error"))
                    data = [data]
                return chunk, data

        last_error = "multi-point responses covered too few stations"
        out: Dict[str, Dict[str, Any]] = {}
        try:
            results = await asyncio.gather(*[_fetch_chunk(c) for c in chunks])
            for chunk, data in results:
                for idx, st in enumerate(chunk):
                    sid = st[0]
                    try:
                        daily = (data[idx] or {}).get("daily") or {}
                        rec = self._normalise(sid, {"daily": _slice_location(daily, idx)})
                        if rec["discharge"] is not None:
                            out[sid] = rec
                    except Exception:
                        continue
        except Exception as exc:
            last_error = str(exc)

        if len(out) >= max(len(RIVER_STATIONS) // 2, 1):
            _record(True, len(out))
            return out

        # ---- fallback: per-station requests ----
        async def _one(st):
            sid, lat, lon = st[0], st[5], st[6]
            try:
                data = await self.fetch_station(lat, lon)
                return sid, self._normalise(sid, data)
            except Exception:
                return sid, None

        results = await asyncio.gather(*[_one(st) for st in RIVER_STATIONS])
        out = {sid: rec for sid, rec in results if rec}
        _record(bool(out), len(out), error=None if out else last_error,
                degraded=bool(out) and len(out) < len(RIVER_STATIONS) // 2)
        return out

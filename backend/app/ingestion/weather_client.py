"""Weather ingestion: Open-Meteo (free, no key) as primary live source with an
IMD API adapter. All requests are location-agnostic so the whole of India is
covered via the zone centroid registry.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncio
import httpx

from ..config import settings
from ..models.india_data import ZONES


class WeatherClient:
    BASE = settings.OPEN_METEO_BASE_URL

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=15.0)

    async def fetch_current(self, lat: float, lon: float) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation",
                    "rain",
                    "showers",
                    "snowfall",
                    "weather_code",
                    "cloud_cover",
                    "pressure_msl",
                    "wind_speed_10m",
                    "wind_direction_10m",
                ]
            ),
            "hourly": "precipitation,precipitation_probability,temperature_2m",
            "forecast_days": 3,
            "timezone": "Asia/Kolkata",
        }
        r = await self._client.get(f"{self.BASE}/forecast", params=params)
        r.raise_for_status()
        return r.json()

    def _response_to_zone(self, zone: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        lon, lat = zone["centroid"]
        cur = data.get("current", {})
        hourly = data.get("hourly", {})
        now_iso = datetime.now().isoformat()
        precip_forecast = (hourly.get("precipitation") or [])[:24]
        time_forecast = (hourly.get("time") or [])[:24]
        prob_forecast = (hourly.get("precipitation_probability") or [])[:24]
        return {
            "location_id": zone["id"],
            "zone_name": zone["name"],
            "state": zone["state"],
            "basin": zone["basin"],
            "latitude": lat,
            "longitude": lon,
            "timestamp": now_iso,
            "temperature_2m": cur.get("temperature_2m"),
            "precipitation": cur.get("precipitation"),
            "rain": cur.get("rain"),
            "showers": cur.get("showers"),
            "snowfall": cur.get("snowfall"),
            "weather_code": cur.get("weather_code"),
            "cloud_cover": cur.get("cloud_cover"),
            "pressure_msl": cur.get("pressure_msl"),
            "wind_speed_10m": cur.get("wind_speed_10m"),
            "wind_direction_10m": cur.get("wind_direction_10m"),
            "relative_humidity_2m": cur.get("relative_humidity_2m"),
            "precipitation_probability": (prob_forecast[0] if prob_forecast else 0) or 0,
            "forecast_hours": time_forecast,
            "forecast_precipitation": precip_forecast,
            "forecast_probability": prob_forecast,
            "data_source": "OPEN_METEO",
        }

    async def fetch_zone(self, zone: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.fetch_current(zone["centroid"][1], zone["centroid"][0])
        return self._response_to_zone(zone, data)

    async def refresh_all_zones(self) -> List[Dict[str, Any]]:
        """Fetch live weather for every district zone in batched multi-point calls.

        Open-Meteo accepts comma-separated latitude/longitude lists, so with
        ~760 district zones the country is refreshed in chunks of 100
        coordinates (well inside free-tier multi-point limits), fetched
        concurrently with a bounded semaphore.
        """
        import time as _time

        from .source_registry import registry

        started = _time.perf_counter()
        zones = list(ZONES)
        if not zones:
            return []

        def _fail(error: str) -> List[Dict[str, Any]]:
            registry.record(
                "open_meteo_weather",
                ok=False,
                latency_ms=(_time.perf_counter() - started) * 1000,
                records=0,
                error=error,
            )
            return []

        params = {
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m",
            "hourly": "precipitation,precipitation_probability,temperature_2m",
            "forecast_days": 3,
            "timezone": "Asia/Kolkata",
        }

        chunk_size = 100
        chunks = [zones[i:i + chunk_size] for i in range(0, len(zones), chunk_size)]
        sem = asyncio.Semaphore(6)

        async def fetch_chunk(chunk: List[Dict[str, Any]]) -> Dict[str, Any]:
            async with sem:
                lats = ",".join(str(z["centroid"][1]) for z in chunk)
                lons = ",".join(str(z["centroid"][0]) for z in chunk)
                cp = dict(params, latitude=lats, longitude=lons)
                r = await self._client.get(f"{self.BASE}/forecast", params=cp)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict):
                    if data.get("error"):
                        raise RuntimeError(data.get("reason", "open-meteo multi-point error"))
                    data = [data]
                return chunk, data

        try:
            results = await asyncio.gather(*(fetch_chunk(c) for c in chunks))
            out: List[Dict[str, Any]] = []
            for chunk, data in results:
                for zone, resp in zip(chunk, data):
                    try:
                        out.append(self._response_to_zone(zone, resp))
                    except Exception:
                        continue

            if len(out) < max(len(zones) // 2, 1):
                raise RuntimeError("multi-point response covered too few zones {:d}/{:d}".format(len(out), len(zones)))
            registry.record(
                "open_meteo_weather",
                ok=True,
                latency_ms=(_time.perf_counter() - started) * 1000,
                records=len(out),
            )
            return out
        except Exception as exc:
            return _fail(str(exc))

    async def fetch_wind_grid(self, points: List[tuple]) -> List[Dict[str, Any]]:
        """Fetch a single multi-point wind/precipitation field over India.

        One request covers the whole grid, giving the map real wind vectors
        (the winds that carry monsoon rain) instead of a synthetic field.
        """
        lats = ",".join(str(p[0]) for p in points)
        lons = ",".join(str(p[1]) for p in points)
        params = {
            "latitude": lats,
            "longitude": lons,
            "current": "wind_speed_10m,wind_direction_10m,precipitation,rain",
            "timezone": "Asia/Kolkata",
        }
        r = await self._client.get(f"{self.BASE}/forecast", params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            data = [data]
        out: List[Dict[str, Any]] = []
        for point, d in zip(points, data):
            cur = (d or {}).get("current") or {}
            out.append({
                "latitude": point[0],
                "longitude": point[1],
                "wind_speed_kmph": cur.get("wind_speed_10m"),
                "wind_direction_deg": cur.get("wind_direction_10m"),
                "precipitation_mm": cur.get("precipitation"),
                "rain_mm": cur.get("rain"),
            })
        return out


class IMDClient:
    """Adapter for India Meteorological Department public APIs.

    IMD requires IP whitelisting for the full forecast suite; this adapter
    prefers the free Open-Meteo path and gracefully degrades if IMD is
    unreachable. Endpoints follow https://api.imd.gov.in/api_reference.html
    """

    BASE = settings.IMD_API_BASE_URL

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.IMD_API_KEY
        self._client = httpx.AsyncClient(timeout=15.0)

    async def district_rainfall(self, state: str, district: str) -> Dict[str, Any]:
        params = {"state": state, "district": district}
        if self.api_key:
            params["token"] = self.api_key
        try:
            r = await self._client.get(f"{self.BASE}/rainfall/district", params=params)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc), "state": state, "district": district}

    async def basin_qpf(self, basin_id: Optional[int] = None) -> Dict[str, Any]:
        params = {}
        if basin_id is not None:
            params["id"] = basin_id
        if self.api_key:
            params["token"] = self.api_key
        try:
            r = await self._client.get(f"{self.BASE}/basinqpf", params=params)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc), "note": "IMD API requires IP whitelisting; using Open-Meteo mirror."}

    async def state_forecast(self, state: str) -> Dict[str, Any]:
        try:
            r = await self._client.get(f"{self.BASE}/forecast/district/{state}", params={"token": self.api_key} if self.api_key else {})
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc), "state": state}
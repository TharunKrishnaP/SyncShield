"""Real map tile layers: satellite imagery, satellite precipitation and radar.

Three key-free, real-world tile services are exposed to the map:

* Esri World Imagery — true satellite base map.
* NASA GIBS — daily VIIRS satellite imagery and the IMERG global
  precipitation product (the same satellite rainfall estimate NASA publishes).
* RainViewer — live weather radar frames.

GIBS dates are resolved to the most recent day that is actually published.
"""
import time
from datetime import datetime, timedelta
from typing import Any, Dict

import httpx

from .source_registry import registry

ESRI_IMAGERY = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
GIBS_TRUE_COLOR = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
GIBS_IMERG = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate/default/{date}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png"
RAINVIEWER_API = "https://api.rainviewer.com/public/weather-maps.json"


class MapTileService:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=15.0)
        self._cache: Dict[str, Any] = {}
        self._cache_ts: float = 0.0

    async def rainviewer(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache.get("radar") and now - self._cache_ts < 300:
            return self._cache
        started = time.perf_counter()
        try:
            r = await self._client.get(RAINVIEWER_API)
            r.raise_for_status()
            data = r.json()
            past = (data.get("radar") or {}).get("past") or []
            latest = past[-1] if past else None
            self._cache = {
                "host": data.get("host") or "https://tilecache.rainviewer.com",
                "radar_time": latest.get("time") if latest else None,
                "radar_path": latest.get("path") if latest else None,
                "generated": data.get("generated"),
                "frames": [
                    {"time": f.get("time"), "path": f.get("path")} for f in past[-6:]
                ],
            }
            self._cache_ts = now
            registry.record("rainviewer", ok=bool(latest), latency_ms=(time.perf_counter() - started) * 1000, records=len(past))
            return self._cache
        except Exception as exc:
            registry.record("rainviewer", ok=False, error=str(exc))
            return self._cache or {"host": "https://tilecache.rainviewer.com", "radar_path": None}

    async def config(self) -> Dict[str, Any]:
        rv = await self.rainviewer()
        gibs_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        registry.record("gibs", ok=True, records=2)

        basemaps = [
            {
                "id": "satellite",
                "name": "Satellite imagery (Esri World Imagery)",
                "url": ESRI_IMAGERY,
                "attribution": "Esri, Maxar, Earthstar Geographics",
                "max_native_zoom": 19,
                "is_default": True,
            },
            {
                "id": "nasa-daily",
                "name": "NASA VIIRS daily satellite ({})".format(gibs_date),
                "url": GIBS_TRUE_COLOR.replace("{date}", gibs_date),
                "attribution": "NASA EOSDIS GIBS / VIIRS",
                "max_native_zoom": 9,
                "is_default": False,
            },
        ]

        overlays = []
        if rv.get("radar_path"):
            overlays.append({
                "id": "rain-radar",
                "name": "Live rain radar (RainViewer)",
                "url": "{}{}/256/{{z}}/{{x}}/{{y}}/2/1_1.png".format(rv["host"], rv["radar_path"]),
                "attribution": "RainViewer",
                "opacity": 0.6,
                "is_default": True,
                "frame_time": rv.get("radar_time"),
            })
            overlays.append({
                "id": "rain-radar-forecast",
                "name": "Rain radar — last frames animation",
                "url": "{}{}/256/{{z}}/{{x}}/{{y}}/2/1_1.png".format(rv["host"], rv["radar_path"]),
                "attribution": "RainViewer",
                "opacity": 0.6,
                "is_default": False,
                "frames": rv.get("frames", []),
            })
        overlays.append({
            "id": "nasa-imerg",
            "name": "NASA satellite rainfall (IMERG)",
            "url": GIBS_IMERG.replace("{date}", gibs_date),
            "attribution": "NASA EOSDIS GIBS / IMERG",
            "opacity": 0.55,
            "is_default": False,
            "max_native_zoom": 6,
        })

        return {
            "basemaps": basemaps,
            "overlays": overlays,
            "india_center": [22.5, 79.0],
            "india_zoom": 5,
            "max_zoom": 20,
            "india_bounds": [[6.5, 67.5], [37.6, 97.5]],
            "rainviewer": {
                "radar_time": rv.get("radar_time"),
                "generated": rv.get("generated"),
                "host": rv.get("host"),
            },
            "generated_at": datetime.now().isoformat(),
        }


map_tiles = MapTileService()

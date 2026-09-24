"""Sentinel-1 SAR flood inundation processor and simulation generator.

In production, the real pipeline would:
  - Pull GRD products from the NRSC Bhoonidhi STAC catalogue.
  - Threshold backscatter to detect water surface.
  - Polygonise the binary water mask and attach CRS / metadata.

For the DataLake demo, this module synthesises GeoJSON flood polygons that
are physically plausible, aligned to India's flood-prone river corridors,
and grow/shrink with the scenario step to create dynamic map overlays.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import math

from ..config import settings
from ..models.india_data import ZONES


# ---- centre-line offsets (lon offsets) for the simulation polygons by basin ----
_BASIN_LON_OFFSETS = {
    "BRAHMAPUTRA": (89.7, 95.3),
    "BARAK": (92.2, 93.2),
    "GANGA": (78.0, 88.0),
    "YAMUNA": (76.8, 78.5),
    "GODAVARI": (78.5, 82.0),
    "KRISHNA": (76.5, 80.8),
    "CAUVERY": (76.0, 79.8),
    "MAHANADI": (82.0, 85.5),
    "NARMADA": (73.0, 81.0),
    "TAPI": (73.0, 76.0),
    "SABARMATI": (72.0, 73.2),
    "PERIYAR": (76.0, 76.5),
    "SUBARNAREKHA": (86.0, 87.5),
    "DAMODAR": (87.0, 88.0),
    "MAHI": (73.0, 75.5),
    "PENNAR": (77.8, 79.5),
    "INDUS": (73.0, 76.5),
}


def _generate_polygons_for_zone(
    zone: Dict[str, Any],
    step: int,
    surge_factor: float = 1.0,
) -> Dict[str, Any]:
    """Produce a synthetic Sentinel-1-like flood extent polygon for a zone.

    The polygon width is proportional to the surge factor and current step,
    and centred on the zone's centroid.
    """
    lon, lat = zone["centroid"]
    basin = zone.get("basin", "GANGA")
    lon_range = _BASIN_LON_OFFSETS.get(basin, (lon - 1.5, lon + 1.5))

    t = step * 0.15
    monsoon_signal = 0.5 * math.sin(t) + 0.2 * math.sin(3 * t)
    ramp = 0.15 * step
    surge = (surge_factor - 1.0) * 0.5 * (1 + math.sin(t * 0.3))

    # half-width in degrees (approx: 1 deg ≈ 111 km); magnified so the
    # areal extent saturates the coverage ratio during peak surge
    base_half = (0.04 + ramp * 0.006 + surge * 0.03) * 1.6
    half_w = round(base_half, 5)
    half_h = round(half_w * 0.6, 5)

    flood_area_km2 = round((half_w * 2 * 111) * (half_h * 2 * 111), 2)
    water_depth = round(0.6 + surge_factor * 1.1 + ramp * 0.15, 2)

    polygon = [
        [round(lon - half_w, 5), round(lat - half_h, 5)],
        [round(lon + half_w, 5), round(lat - half_h, 5)],
        [round(lon + half_w, 5), round(lat + half_h, 5)],
        [round(lon - half_w, 5), round(lat + half_h, 5)],
        [round(lon - half_w, 5), round(lat - half_h, 5)],
    ]

    status = "EXTREME" if water_depth > 3.0 else "SEVERE" if water_depth > 1.8 else "ABOVE_NORMAL" if water_depth > 0.8 else "NORMAL"

    return {
        "id": f"SAR-{zone['id']}-{step}",
        "timestamp": datetime.now().isoformat(),
        "zone_id": zone["id"],
        "basin": basin,
        "state": zone["state"],
        "district": zone.get("district", zone["name"]),
        "flood_polygons": [polygon],
        "flood_area_km2": flood_area_km2,
        "water_depth_avg": water_depth,
        "confidence": round(0.8 + 0.1 * math.sin(t), 3),
        "satellite": "Sentinel-1A",
        "sensor": "SAR",
        "resolution_m": 10.0,
        "data_source": "SENTINEL1_SAR",
        "processing_level": "L2",
        "flood_status": status,
    }


class SARProcessor:
    def __init__(self):
        self._step = 0
        self._surge_factor = 1.0

    def advance(self, surge_factor: Optional[float] = None):
        self._step += 1
        if surge_factor is not None:
            self._surge_factor = surge_factor

    def set_phase(self, step: int, surge_factor: float):
        self._step = step
        self._surge_factor = surge_factor

    def reset(self):
        self._step = 0
        self._surge_factor = 1.0

    def generate_all(self) -> List[Dict[str, Any]]:
        """Return synthetic Sentinel-1 SAR flood polygons for every active zone."""
        out = []
        for zone in ZONES:
            try:
                out.append(_generate_polygons_for_zone(zone, self._step, self._surge_factor))
            except Exception:
                continue
        return out


# ---- Bhoonidhi / Bhuvan live adapters (production-ready stubs) ----

class BhoonidhiClient:
    """Client for ISRO Bhoonidhi STAC API (Sentinel-1 SAR products).

    Docs: https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/index.html

    The search endpoint at https://bhoonidhi-api.nrsc.gov.in/data/search
    accepts a CQL2 geometry and datetime range. Authentication is JWT-based
    and requires registered credentials.
    """

    BASE = settings.BHOONIDHI_API_URL if hasattr(settings, "BHOONIDHI_API_URL") else "https://bhoonidhi-api.nrsc.gov.in"

    async def search_sar(self, bbox, datetime_range) -> Dict[str, Any]:
        """Stub for production: search Bhoonidhi for Sentinel-1 IW GRD products.

        Returns a STAC collection dict. In production, the token should be
        acquired from /api/v1/auth/login first.
        """
        return {
            "collections": ["Sentinel-1A_SAR-IW_GRD"],
            "bbox": bbox,
            "datetime": datetime_range,
            "items": [],
            "note": "Bhoonidhi requires authentication; falling back to simulation.",
        }


class NDMPortalClient:
    """Client for NDEM / Bhuvan flood inundation overlays.

    These are served as tile overlay services during active flood events.
    In production we pull WMS tile URLs and overlay them on Leaflet.
    """

    BASE = "https://ndem.nrsc.gov.in"
    BHOONIDH_FLOOD_URL = "https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=flood"

    async def get_inundation_layers(self) -> List[Dict[str, Any]]:
        """Return current flood event inundation tiles / GeoJSON for the NDMA NDEM portal."""
        return [
            {
                "name": "NDEM Flood Inundation Layer",
                "type": "WMS_TILE",
                "url": "https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=flood",
                "source": "ISRO/NRSC NDEM v5.0",
                "coverage": "Pan India",
            }
        ]
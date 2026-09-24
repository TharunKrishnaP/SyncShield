"""Flood-aware emergency routing and comparative route risk assessment.

For a given origin → destination pair, computes:
  - Direct route: baseline distance + flood exposure + incident density
  - Alternative route: detour via lower-risk segments
  - Route Risk = FloodExposure × 0.40 + RoadBlockages × 0.30
              + Distance × 0.15 + IncidentDensity × 0.15
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math

from ..models.india_data import (
    ZONE_INDEX,
    VULNERABLE_ROADS,
    INFRASTRUCTURE,
    stations_near,
)


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _route_samples(lat1, lon1, lat2, lon2, n: int = 7):
    """Return n+1 evenly spaced points along the great-circle-ish line, plus midpoint."""
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t))
    if n % 2 == 0 and n > 0:
        pts.append(((lat1 + lat2) / 2, (lon1 + lon2) / 2))
    return pts


def _flood_exposure_points(points, zone_scores: Dict[str, Dict[str, Any]]) -> float:
    """Return 0-100 flood exposure along a set of route points.

    Scores the max flood severity within CLOSE_KM of any point, then discounts
    by the fraction of the route that actually touches flood-adjacent zones.
    """
    if not zone_scores:
        return 0.0
    exposures = []
    for lat, lon in points:
        best = 0.0
        for zid, zs in zone_scores.items():
            z = ZONE_INDEX.get(zid)
            if not z or not z.get("centroid"):
                continue
            clon, clat = z["centroid"]
            d = _haversine_km(lat, lon, clat, clon)
            if d < 25.0:
                best = max(best, zs.get("overall_score", 0))
        exposures.append(best)
    if not exposures:
        return 0.0
    peak = max(exposures)
    touched = sum(1 for e in exposures if e > 15)
    coverage = touched / len(exposures)
    return round(peak * (0.55 + 0.45 * coverage), 1)


def _road_blockages_points(points, radius_km: float = 40.0) -> Tuple[int, float]:
    """Return (count, avg_risk) of vulnerable roads within radius of any route point."""
    seen = set()
    total = 0.0
    for lat, lon in points:
        for rd in VULNERABLE_ROADS:
            if rd["id"] in seen:
                continue
            d = _haversine_km(lat, lon, rd["lat"], rd["lon"])
            if d <= radius_km:
                seen.add(rd["id"])
                total += 1 if rd.get("risk_class") == "HIGH" else 0.5
    return len(seen), (total / len(seen) if seen else 0.0)


def _incident_density_points(points, incidents: List[Dict[str, Any]], radius_km: float = 40.0) -> float:
    seen = set()
    for lat, lon in points:
        for inc in incidents:
            iid = inc.get("id") or (inc.get("latitude"), inc.get("longitude"))
            if iid in seen:
                continue
            if _haversine_km(lat, lon, inc.get("latitude", 0), inc.get("longitude", 0)) <= radius_km:
                seen.add(iid)
    return min(len(seen) / 10.0, 1.0)


def compute_route_risk(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    zone_scores: Dict[str, Dict[str, Any]],
    incidents: List[Dict[str, Any]],
    origin_name: str = "Origin",
    dest_name: str = "Destination",
) -> Dict[str, Any]:
    """Compute and compare direct vs. alternative route risk."""

    # ---- Direct route (straight line + exposure sampled along it) ----
    direct_dist = _haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
    direct_points = _route_samples(origin_lat, origin_lon, dest_lat, dest_lon)

    direct_flood = _flood_exposure_points(direct_points, zone_scores)
    direct_block_count, direct_block_avg = _road_blockages_points(direct_points)
    direct_inc_density = _incident_density_points(direct_points, incidents)

    direct_risk = (
        direct_flood * 0.40
        + direct_block_avg * 30.0 * 0.30
        + min(direct_dist / 200.0, 1.0) * 15.0 * 0.15
        + direct_inc_density * 15.0 * 0.15
    )
    direct_risk = round(min(direct_risk, 100.0), 1)
    direct_status = "UNSAFE" if direct_risk > 60 else "CAUTION" if direct_risk > 35 else "SAFE"

    # ---- Alternative route: offset via low-risk quadrant ----
    mid_lat = (origin_lat + dest_lat) / 2
    mid_lon = (origin_lon + dest_lon) / 2
    offset_lat = mid_lat + 0.5 * (1 if origin_lat < dest_lat else -1)
    offset_lon = mid_lon + 0.5 * (1 if origin_lon < dest_lon else -1)
    offset_lat = max(6.5, min(offset_lat, 35.5))
    offset_lon = max(68.1, min(offset_lon, 97.4))

    alt_dist1 = _haversine_km(origin_lat, origin_lon, offset_lat, offset_lon)
    alt_dist2 = _haversine_km(offset_lat, offset_lon, dest_lat, dest_lon)
    alt_total = alt_dist1 + alt_dist2

    alt_points = _route_samples(origin_lat, origin_lon, offset_lat, offset_lon) + \
        _route_samples(offset_lat, offset_lon, dest_lat, dest_lon)

    alt_flood = _flood_exposure_points(alt_points, zone_scores)
    alt_block_count, alt_block_avg = _road_blockages_points(alt_points)
    alt_inc = _incident_density_points(alt_points, incidents)

    alt_risk = (
        alt_flood * 0.40
        + alt_block_avg * 30.0 * 0.30
        + min(alt_total / 200.0, 1.0) * 15.0 * 0.15
        + alt_inc * 15.0 * 0.15
    )
    alt_risk = round(min(alt_risk, 100.0), 1)
    alt_status = "UNSAFE" if alt_risk > 60 else "CAUTION" if alt_risk > 35 else "SAFE"

    # ---- Recommendation ----
    if alt_risk < direct_risk and direct_risk > 40:
        recommendation = (
            f"RECOMMENDED: Use alternative route ({alt_total:.1f} km, Risk {alt_risk}, {alt_status}). "
            f"Direct route is {direct_status} (Risk {direct_risk}) with {direct_block_count} flood-prone road segments."
        )
    else:
        recommendation = (
            f"Direct route is {direct_status} (Risk {direct_risk}). "
            f"Alternative is {alt_status} (Risk {alt_risk}). Direct route may be used."
        )

    return {
        "origin": {"name": origin_name, "lat": origin_lat, "lon": origin_lon, "type": "ORIGIN"},
        "destination": {"name": dest_name, "lat": dest_lat, "lon": dest_lon, "type": "DESTINATION"},
        "direct_route": {
            "distance_km": round(direct_dist, 1),
            "risk_score": direct_risk,
            "flood_exposure": round(direct_flood, 1),
            "road_blockages": direct_block_count,
            "incident_density": round(direct_inc_density, 2),
            "status": direct_status,
            "waypoints": [[origin_lon, origin_lat], [mid_lon, mid_lat], [dest_lon, dest_lat]],
        },
        "alternative_route": {
            "distance_km": round(alt_total, 1),
            "risk_score": alt_risk,
            "flood_exposure": round(alt_flood, 1),
            "road_blockages": alt_block_count,
            "incident_density": round(alt_inc, 2),
            "status": alt_status,
            "waypoints": [
                [origin_lon, origin_lat],
                [offset_lon, offset_lat],
                [dest_lon, dest_lat],
            ],
        },
        "recommendation": recommendation,
        "timestamp": datetime.now().isoformat(),
    }


def precompute_zone_routes(
    zone_scores: Dict[str, Dict[str, Any]],
    incidents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute routes between rescue bases and the highest-risk zones."""
    bases = INFRASTRUCTURE.get("rescue_bases", [])
    routes = []
    danger_zones = sorted(
        ((zid, zs) for zid, zs in zone_scores.items() if zs.get("overall_score", 0) >= 15 and zid in ZONE_INDEX),
        key=lambda kv: -kv[1].get("overall_score", 0),
    )[:3]
    for base in bases[:3]:
        for zid, zs in danger_zones:
            clon, clat = ZONE_INDEX[zid]["centroid"]
            route = compute_route_risk(
                base["lat"], base["lon"],
                clat, clon,
                zone_scores, incidents,
                origin_name=base["name"],
                dest_name=ZONE_INDEX[zid]["name"],
            )
            routes.append(route)
    return routes
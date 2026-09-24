"""AI Situation Severity Index (0-100) and trend/deterioration tracking.

Formula (zone-level):
  Score = 0.35 * S_satellite + 0.20 * W_rain + 0.20 * R_river
        + 0.15 * I_reports  + 0.10 * P_population

Regional score = population-weighted average of zone scores.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from ..config import settings
from ..models.india_data import ZONE_INDEX, ZONES

WEIGHTS = {
    "satellite": settings.WEIGHT_SATELLITE,
    "weather": settings.WEIGHT_WEATHER,
    "river": settings.WEIGHT_RIVER,
    "incidents": settings.WEIGHT_INCIDENTS,
    "population": settings.WEIGHT_POPULATION,
}

_STATUS_THRESHOLDS = [
    (20, "LOW"),
    (40, "MODERATE"),
    (60, "HIGH"),
    (80, "VERY_HIGH"),
    (100, "CRITICAL"),
]


def _status_label(score: float) -> str:
    for thresh, label in _STATUS_THRESHOLDS:
        if score <= thresh:
            return label
    return "CRITICAL"


def _satellite_score(extent: Optional[Dict[str, Any]], zone: Dict[str, Any]) -> float:
    """Normalise SAR flood extent to 0-100 for the zone."""
    if not extent:
        return 0.0
    area = extent.get("flood_area_km2", 0.0)
    zone_area = max(zone.get("area_km2", 1.0), 1.0)
    ratio = min(area / zone_area, 2.0) / 2.0  # saturate at 200% coverage
    depth = extent.get("water_depth_avg", 0.0)
    depth_factor = min(depth / 4.0, 1.0)  # saturate at 4m
    status = extent.get("flood_status", "NORMAL")
    status_bonus = {"EXTREME": 25, "SEVERE": 15, "ABOVE_NORMAL": 8, "NORMAL": 0}.get(status, 0)
    return min(ratio * 60 + depth_factor * 25 + status_bonus, 100.0)


def _weather_score(weather: Optional[Dict[str, Any]]) -> float:
    if not weather:
        return 0.0
    precip = weather.get("precipitation", 0.0) or 0.0
    rain = weather.get("rain", 0.0) or 0.0
    total = max(precip, rain)
    if total >= 100:
        score = 95.0
    elif total >= 64:
        score = 80.0
    elif total >= 30:
        score = 60.0
    elif total >= 15:
        score = 40.0
    elif total >= 5:
        score = 20.0
    else:
        score = total * 4.0

    wind = weather.get("wind_speed_10m", 0.0) or 0.0
    if wind >= 60:
        score += 10
    elif wind >= 30:
        score += 5
    return min(score, 100.0)


def _river_score(river: Optional[Dict[str, Any]]) -> float:
    if not river:
        return 0.0
    wl = river.get("water_level", 0.0)
    dl = river.get("danger_level", wl + 1.0)
    wl_val = river.get("warning_level", dl - 0.5)
    if dl <= wl_val:
        dl = wl_val + 1.0

    if wl == 0:
        return 0.0
    if wl >= dl:
        return min(95.0 + min((wl - dl) / dl, 0.1) * 50, 100.0)
    if wl >= wl_val:
        return 40.0 + 40.0 * ((wl - wl_val) / max(dl - wl_val, 0.01))
    ratio = wl / dl
    return min(ratio * 35, 35.0)


def _incident_score(incidents: List[Dict[str, Any]]) -> float:
    if not incidents:
        return 0.0
    count = len(incidents)
    avg_sev = sum(i.get("severity", 0.5) for i in incidents) / count
    count_score = min(count * 5, 60.0)
    return min(avg_sev * 40 + count_score, 100.0)


def _population_score(zone: Dict[str, Any]) -> float:
    pop = zone.get("population", 100000)
    vuln = zone.get("vulnerable_population", 0.25)
    pop_factor = min(pop / 1000000, 1.0)
    vuln_factor = min(vuln / 0.4, 1.0)
    return min(pop_factor * 50 + vuln_factor * 50, 100.0)


class SituationScorer:
    """Scores every zone and the all-India aggregate, tracking deterioration."""

    def __init__(self):
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._zone_scores: Dict[str, Dict[str, Any]] = {}
        self._regional_score: Optional[Dict[str, Any]] = None

    def compute_all(
        self,
        weather_map: Dict[str, Dict[str, Any]],
        river_map: Dict[str, Dict[str, Any]],
        satellite_map: Dict[str, Dict[str, Any]],
        incident_map: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        zone_scores = {}
        for zone in ZONES:
            zid = zone["id"]
            sat = satellite_map.get(zid)
            wxt = weather_map.get(zid)
            riv = river_map.get(zid)
            inc = incident_map.get(zid, [])

            s_sat = _satellite_score(sat, zone)
            s_wxt = _weather_score(wxt)
            s_riv = _river_score(riv)
            s_inc = _incident_score(inc)
            s_pop = _population_score(zone)

            overall = (
                s_sat * WEIGHTS["satellite"]
                + s_wxt * WEIGHTS["weather"]
                + s_riv * WEIGHTS["river"]
                + s_inc * WEIGHTS["incidents"]
                + s_pop * WEIGHTS["population"]
            )
            overall = round(min(max(overall, 0.0), 100.0), 2)

            trend, deteriorating = self._compute_trend(zid, overall)

            evidence = {
                "satellite_pct": round(WEIGHTS["satellite"] * 100, 0),
                "weather_pct": round(WEIGHTS["weather"] * 100, 0),
                "river_pct": round(WEIGHTS["river"] * 100, 0),
                "incidents_pct": round(WEIGHTS["incidents"] * 100, 0),
                "population_pct": round(WEIGHTS["population"] * 100, 0),
                "satellite_raw": round(s_sat, 1),
                "weather_raw": round(s_wxt, 1),
                "river_raw": round(s_riv, 1),
                "incidents_raw": round(s_inc, 1),
                "population_raw": round(s_pop, 1),
            }

            zone_scores[zid] = {
                "zone_id": zid,
                "zone_name": zone["name"],
                "basin": zone["basin"],
                "state": zone["state"],
                "district": zone.get("district", zone["name"]),
                "overall_score": overall,
                "severity_level": _status_label(overall),
                "satellite_score": round(s_sat, 1),
                "weather_score": round(s_wxt, 1),
                "river_score": round(s_riv, 1),
                "incident_score": round(s_inc, 1),
                "population_score": round(s_pop, 1),
                "trend": trend,
                "deteriorating": deteriorating,
                "last_updated": datetime.now().isoformat(),
                "evidence_breakdown": evidence,
            }

        self._zone_scores = zone_scores
        self._regional_score = self._aggregate_regional(zone_scores)
        return {"zones": zone_scores, "regional": self._regional_score}

    def get_zone(self, zone_id: str) -> Optional[Dict[str, Any]]:
        return self._zone_scores.get(zone_id)

    def get_regional(self) -> Optional[Dict[str, Any]]:
        return self._regional_score

    def _compute_trend(self, zone_id: str, current_score: float) -> tuple:
        hist = self._history.setdefault(zone_id, [])
        hist.append({"ts": datetime.now().timestamp(), "score": current_score})
        if len(hist) > 120:
            self._history[zone_id] = hist = hist[-120:]
        if len(hist) < 2:
            return 0.0, False
        t1, s1 = hist[-2]["ts"], hist[-2]["score"]
        t2, s2 = hist[-1]["ts"], hist[-1]["score"]
        dt = max(t2 - t1, 1.0)
        trend = round((s2 - s1) / dt * 3600, 2)  # per hour
        deteriorating = trend > 5.0  # >5 pts/hr is deterioration
        return trend, deteriorating

    def _aggregate_regional(self, zone_scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if not zone_scores:
            return {"score": 0, "status": "LOW"}
        total_pop = sum(ZONE_INDEX[z]["population"] for z in zone_scores if z in ZONE_INDEX)
        weighted = 0.0
        vals = []
        for zid, zs in zone_scores.items():
            vals.append(zs["overall_score"])
            if zid in ZONE_INDEX and total_pop:
                weighted += zs["overall_score"] * ZONE_INDEX[zid]["population"] / total_pop

        # National alert posture: blend population-weighted baseline with the
        # worst-affected tail so localised critical zones raise the index.
        top10 = sorted(vals, reverse=True)[:10]
        peak = sum(top10) / len(top10) if top10 else 0
        reg_score = round(0.65 * weighted + 0.35 * peak, 2)

        critical_zones = [zid for zid, zs in zone_scores.items() if zs["overall_score"] >= 80]
        very_high_zones = [zid for zid, zs in zone_scores.items() if 60 <= zs["overall_score"] < 80]
        deteriorating_zones = [zid for zid, zs in zone_scores.items() if zs["deteriorating"]]
        return {
            "score": reg_score,
            "status": _status_label(reg_score),
            "critical_zones": critical_zones,
            "very_high_zones": very_high_zones,
            "deteriorating_zones": deteriorating_zones,
            "zone_count": len(zone_scores),
            "last_updated": datetime.now().isoformat(),
        }
"""Explainable AI breakdown generator.

For every zone, produces a human-readable evidence breakdown explaining
why the zone has its current severity score, including percentage-point
contributions from each modality.
"""
from typing import Any, Dict, List


_EXPLANATION_TEMPLATES = {
    "satellite": "Sentinel-1 SAR flood extent covers {area:.1f} km² of {zone} — contributes {pts:.1f} points.",
    "weather": "Open-Meteo reports {precip:.1f} mm/hr rainfall at {zone} — contributes {pts:.1f} points.",
    "river": "CWC gauge on {river} shows water level {wl:.1f}m vs danger level {dl:.1f}m — contributes {pts:.1f} points.",
    "incidents": "{count} citizen/field reports from {zone} — contributes {pts:.1f} points.",
    "population": "Zone population {pop:,} (vulnerable share {vuln:.0%}) — contributes {pts:.1f} points.",
}


class ExplainabilityEngine:
    def generate_for_zone(
        self,
        zone_meta: Dict[str, Any],
        zone_score: Dict[str, Any],
        weather_data: Dict[str, Any] | None,
        river_data: Dict[str, Any] | None,
        satellite_data: Dict[str, Any] | None,
        incidents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        evidence = []
        overall = zone_score.get("overall_score", 0)
        breakdown = zone_score.get("evidence_breakdown", {})

        # Satellite
        sat_raw = breakdown.get("satellite_raw", 0)
        if sat_raw > 0:
            area = satellite_data.get("flood_area_km2", 0) if satellite_data else 0
            contribution = sat_raw * 0.35
            evidence.append({
                "factor": "Satellite SAR Flood Extent",
                "contribution_pct": round(contribution / max(overall, 0.1) * 100, 1),
                "contribution_pts": round(contribution, 1),
                "description": _EXPLANATION_TEMPLATES["satellite"].format(
                    area=area, zone=zone_meta.get("name", ""), pts=round(contribution, 1)
                ),
                "raw_score": sat_raw,
            })

        # Weather
        wxt_raw = breakdown.get("weather_raw", 0)
        if wxt_raw > 0:
            precip = weather_data.get("precipitation", 0) if weather_data else 0
            contribution = wxt_raw * 0.20
            evidence.append({
                "factor": "IMD / Open-Meteo Rainfall",
                "contribution_pct": round(contribution / max(overall, 0.1) * 100, 1),
                "contribution_pts": round(contribution, 1),
                "description": _EXPLANATION_TEMPLATES["weather"].format(
                    precip=precip, zone=zone_meta.get("name", ""), pts=round(contribution, 1)
                ),
                "raw_score": wxt_raw,
            })

        # River
        riv_raw = breakdown.get("river_raw", 0)
        if riv_raw > 0:
            wl = river_data.get("water_level", 0) if river_data else 0
            dl = river_data.get("danger_level", 0) if river_data else 0
            river = river_data.get("river", "unknown") if river_data else "unknown"
            contribution = riv_raw * 0.20
            evidence.append({
                "factor": "CWC River Gauge",
                "contribution_pct": round(contribution / max(overall, 0.1) * 100, 1),
                "contribution_pts": round(contribution, 1),
                "description": _EXPLANATION_TEMPLATES["river"].format(
                    river=river, wl=wl, dl=dl, pts=round(contribution, 1)
                ),
                "raw_score": riv_raw,
            })

        # Incidents
        inc_raw = breakdown.get("incidents_raw", 0)
        if inc_raw > 0:
            count = len(incidents)
            contribution = inc_raw * 0.15
            evidence.append({
                "factor": "Citizen / Field Reports",
                "contribution_pct": round(contribution / max(overall, 0.1) * 100, 1),
                "contribution_pts": round(contribution, 1),
                "description": _EXPLANATION_TEMPLATES["incidents"].format(
                    count=count, zone=zone_meta.get("name", ""), pts=round(contribution, 1)
                ),
                "raw_score": inc_raw,
            })

        # Population
        pop_raw = breakdown.get("population_raw", 0)
        if pop_raw > 0:
            pop = zone_meta.get("population", 0)
            vuln = zone_meta.get("vulnerable_population", 0.25)
            contribution = pop_raw * 0.10
            evidence.append({
                "factor": "Population Exposure",
                "contribution_pct": round(contribution / max(overall, 0.1) * 100, 1),
                "contribution_pts": round(contribution, 1),
                "description": _EXPLANATION_TEMPLATES["population"].format(
                    pop=pop, vuln=vuln, pts=round(contribution, 1)
                ),
                "raw_score": pop_raw,
            })

        # Primary reason (highest-contribution factor)
        primary = max(evidence, key=lambda e: e["contribution_pct"]) if evidence else {"factor": "Insufficient data", "description": "No data sources reporting."}

        # Natural-language summary
        high_factors = [e["factor"] for e in evidence if e["contribution_pct"] > 25]
        severity_label = zone_score.get("severity_level", "UNKNOWN")
        if high_factors:
            summary = (
                f"{zone_meta.get('name', 'Zone')} is at {severity_label} severity ({overall:.0f}/100). "
                f"Primary driver: {primary['factor']}. "
                f"Contributing factors: {', '.join(high_factors)}."
            )
        else:
            summary = f"{zone_meta.get('name', 'Zone')} is at {severity_label} severity ({overall:.0f}/100)."

        return {
            "zone_id": zone_meta.get("id", ""),
            "zone_name": zone_meta.get("name", ""),
            "primary_reason": primary.get("description", ""),
            "evidence_points": evidence,
            "natural_language_summary": summary,
        }

    def generate_all(
        self,
        zones_meta: List[Dict[str, Any]],
        zone_scores: Dict[str, Dict[str, Any]],
        weather_map: Dict[str, Dict[str, Any]],
        river_map: Dict[str, Dict[str, Any]],
        satellite_map: Dict[str, Dict[str, Any]],
        incident_map: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        out = []
        for z in zones_meta:
            zid = z["id"]
            zs = zone_scores.get(zid, {})
            if zs:
                out.append(self.generate_for_zone(
                    z, zs,
                    weather_map.get(zid), river_map.get(zid),
                    satellite_map.get(zid), incident_map.get(zid, []),
                ))
        return out
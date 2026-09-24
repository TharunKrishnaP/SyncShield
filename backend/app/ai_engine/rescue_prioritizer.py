"""AI Rescue Priority Ranking across all monitoring zones.

Priority = Severity × 0.35 + PopExposure × 0.25 + VulnerablePop × 0.15
         + (1 - Accessibility) × 0.15 + RateOfChange × 0.10
"""
from typing import Any, Dict, List
from ..models.india_data import ZONE_INDEX, ZONES, VULNERABLE_ROADS


def _accessibility_index(zone_id: str) -> float:
    """Lower value = less accessible (more road blockages near the zone)."""
    zone = ZONE_INDEX.get(zone_id)
    if not zone:
        return 0.8
    if not zone.get("centroid"):
        return 0.8
    blocked = sum(
        1 for rd in VULNERABLE_ROADS
        if rd.get("zone") == zone_id
    )
    return max(0.1, 0.9 - blocked * 0.2)


def compute_rescue_priorities(zone_scores: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    priorities = []
    for zid, zs in zone_scores.items():
        zone = ZONE_INDEX.get(zid)
        if not zone:
            continue
        severity = zs.get("overall_score", 0) / 100.0
        pop = zone.get("population", 100000)
        vuln = zone.get("vulnerable_population", 0.25)
        accessibility = _accessibility_index(zid)
        rate_of_change = zs.get("trend", 0.0)
        rate_of_change_norm = min(abs(rate_of_change) / 50.0, 1.0)

        priority_score = (
            severity * 0.35
            + min(pop / 5_000_000, 1.0) * 0.25
            + vuln / 0.4 * 0.15
            + (1 - accessibility) * 0.15
            + rate_of_change_norm * 0.10
        )
        priority_score = round(min(priority_score, 1.0), 4)

        if priority_score >= 0.7:
            plevel = 1
            plabel = "CRITICAL"
        elif priority_score >= 0.45:
            plevel = 2
            plabel = "HIGH"
        elif priority_score >= 0.2:
            plevel = 3
            plabel = "MONITOR"
        else:
            plevel = 4
            plabel = "LOW"

        actions = _recommended_actions(plevel, zs, zone)

        priorities.append({
            "zone_id": zid,
            "zone_name": zone.get("name", zid),
            "basin": zone.get("basin", ""),
            "state": zone.get("state", ""),
            "district": zone.get("district", zone.get("name", "")),
            "priority": plevel,
            "priority_label": plabel,
            "priority_score": priority_score,
            "severity": zs.get("overall_score", 0),
            "population_exposure": pop,
            "vulnerable_population": round(pop * vuln),
            "accessibility_index": accessibility,
            "rate_of_change": rate_of_change,
            "recommended_actions": actions,
            "coordinates": zone.get("coordinates", []),
            "centroid": zone.get("centroid"),
        })

    priorities.sort(key=lambda p: (-p["priority_score"], p["priority"]))
    return priorities


def _recommended_actions(plevel: int, zs: Dict[str, Any], zone: Dict[str, Any]) -> List[str]:
    name = zone.get("name", "this zone")
    basin = zone.get("basin", "")
    severity = zs.get("severity_level", "LOW")
    actions = []

    if plevel == 1:
        actions += [
            f"URGENT: Deploy NDRF/SDRF rescue teams to {name} immediately.",
            f"Evacuate all residents within 2 km of {basin} riverbanks in {name}.",
            f"Set up emergency medical staging near {name} civil hospital.",
            f"Issue NDMA extreme flood alert (RED) for {name} and surrounding areas.",
            f"Activate all relief shelters in {name} district with medical support.",
        ]
    elif plevel == 2:
        actions += [
            f"Pre-position rescue assets at {name} fire/rescue stations.",
            f"Alert {name} civil hospital to prepare for increased patient volume.",
            f"Advise voluntary evacuation for low-lying areas in {name}.",
            f"Close flood-prone NH/SH segments in {name} district.",
        ]
    elif plevel == 3:
        actions += [
            f"Monitor {name} river gauges hourly — prepare evacuation if levels rise.",
            f"Verify emergency equipment readiness in {name} rescue bases.",
        ]
    else:
        actions.append(f"Maintain standard monitoring for {name}. No immediate action required.")

    if zs.get("deteriorating"):
        actions.append(f"WARNING: {name} score is deteriorating — consider advancing response timeline.")

    return actions
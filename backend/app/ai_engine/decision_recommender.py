"""AI Damage Summarizer & Response Recommendation Engine.

Generates operator-ready briefing summaries and prioritized tactical
deployment commands from the situation state.
"""
from datetime import datetime
from typing import Any, Dict, List
import uuid

from ..models.india_data import INFRASTRUCTURE, ZONE_INDEX


class DecisionRecommender:
    def generate(
        self,
        regional: Dict[str, Any],
        zone_scores: Dict[str, Dict[str, Any]],
        priorities: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        recommendations = []

        # --- Tier 1: Critical-zone tactical commands ---
        critical = [p for p in priorities if p["priority"] == 1][:6]
        for p in critical:
            zone = ZONE_INDEX.get(p["zone_id"], {})
            zone_name = p["zone_name"]
            basin = p.get("basin", "")
            agency = _pick_agency(zone.get("state", ""), p["zone_id"])

            recommendations.append({
                "id": f"REC-{uuid.uuid4().hex[:6]}",
                "timestamp": datetime.now().isoformat(),
                "priority": 1,
                "category": "TACTICAL_DEPLOYMENT",
                "title": f"Deploy rescue team to {zone_name}",
                "description": (
                    f"{zone_name} is at CRITICAL severity ({p['severity']:.0f}/100) with {p['population_exposure']:,} "
                    f"people at risk. Assign {agency if agency else 'NDRF'} rescue personnel and boats."
                ),
                "affected_zones": [p["zone_id"]],
                "responsible_agency": agency or "NDRF",
                "confidence": 0.9,
                "estimated_resources": {
                    "boats": 8,
                    "personnel": 60,
                    "vehicles": 4,
                    "shelters": p.get("vulnerable_population", 5000) // 2000 + 2,
                },
            })

        # --- Tier 2: Hospital medical staging ---
        hospitals = INFRASTRUCTURE.get("hospitals", [])
        critical_zones = set(p["zone_id"] for p in critical)
        for hp in hospitals:
            if hp.get("zone") in critical_zones and hp.get("capacity_status") == "STRESSED":
                recommendations.append({
                    "id": f"REC-{uuid.uuid4().hex[:6]}",
                    "timestamp": datetime.now().isoformat(),
                    "priority": 2,
                    "category": "MEDICAL_STAGING",
                    "title": f"Set up medical staging at {hp['name']}",
                    "description": (
                        f"{hp['name']} in a {hp['zone']} critical zone is at STRESSED capacity. "
                        "Pre-position surgical tents, dialysis units, and ICU cots."
                    ),
                    "affected_zones": [hp.get("zone")],
                    "responsible_agency": "State Health Department",
                    "confidence": 0.85,
                    "estimated_resources": {
                        "doctors": 10,
                        "paramedics": 40,
                        "icu_beds": 25,
                        "tents": 6,
                    },
                })

        # --- Tier 3: Evacuation advisories ---
        for p in [x for x in priorities if x["priority"] in (1, 2)][:8]:
            zone_name = p["zone_name"]
            recommendations.append({
                "id": f"REC-{uuid.uuid4().hex[:6]}",
                "timestamp": datetime.now().isoformat(),
                "priority": 2 if p["priority"] == 1 else 3,
                "category": "EVACUATION",
                "title": f"Issue evacuation advisory for {zone_name}",
                "description": (
                    f"Evacuate low-lying areas of {zone_name} (est. {p['vulnerable_population']:,} vulnerable residents). "
                    "Use shelters listed in the datalake and dispatch buses/boats for transport."
                ),
                "affected_zones": [p["zone_id"]],
                "responsible_agency": "District Disaster Management Authority",
                "confidence": 0.8,
                "estimated_resources": {
                    "buses": 4,
                    "boats": 3,
                },
            })

        # --- Tier 4: Rain warnings ----
        rain_zones = [
            (zid, zs) for zid, zs in zone_scores.items()
            if zs.get("weather_score", 0) > 60
            and zs.get("overall_score", 0) < 60
        ]
        for zid, zs in rain_zones[:5]:
            zone = ZONE_INDEX.get(zid, {})
            recommendations.append({
                "id": f"REC-{uuid.uuid4().hex[:6]}",
                "timestamp": datetime.now().isoformat(),
                "priority": 3,
                "category": "EARLY_WARNING",
                "title": f"Heavy rainfall warning for {zone.get('name', zid)}",
                "description": (
                    f"IMD/Open-Meteo indicates heavy rainfall ({zs['weather_score']:.0f}/100) at {zone.get('name', zid)}. "
                    "Activate pre-monsoon readiness drills and emergency communication."
                ),
                "affected_zones": [zid],
                "responsible_agency": "State Disaster Management Authority",
                "confidence": 0.75,
                "estimated_resources": {"communications": 3},
            })

        # --- Tier 5: Data quality advisory ---
        for c in conflicts[:3]:
            zone = ZONE_INDEX.get(c.get("zone_id"), {})
            recommendations.append({
                "id": f"REC-{uuid.uuid4().hex[:6]}",
                "timestamp": datetime.now().isoformat(),
                "priority": 4,
                "category": "DATA_QUALITY",
                "title": f"Verify data conflict in {zone.get('name', c.get('zone_id', ''))}",
                "description": c.get("diagnosis", "Data conflict detected."),
                "affected_zones": [c.get("zone_id")],
                "responsible_agency": "ISRO/NRSC + CWC Data Desk",
                "confidence": 0.7,
                "estimated_resources": {},
            })

        # Sort by priority ascending
        recommendations.sort(key=lambda r: r["priority"])
        return recommendations


def _pick_agency(state: str, zone_id: str) -> str:
    """Heuristic: NDRF for national battalions, SDRF for state forces."""
    if zone_id.startswith("DL-DELHI"):
        return "NDRF 1st Battalion"
    if zone_id.startswith("AS-GUWAHATI"):
        return "NDRF 9th Battalion"
    if zone_id in ("UP-KANPUR", "UP-VARANASI", "UP-PRAYAGRAJ"):
        return "SDRF Uttar Pradesh"
    if zone_id in ("BR-PATNA", "BR-BHAGALPUR"):
        return "SDRF Bihar"
    if zone_id in ("OD-CUTTACK", "OD-SAMBALPUR"):
        return "SDRF Odisha"
    if zone_id in ("GJ-SURAT", "GJ-AHMEDABAD"):
        return "SDRF Gujarat"
    if zone_id in ("TN-CHENNAI", "TN-TRICHY"):
        return "SDRF Tamil Nadu"
    if zone_id.startswith("KL-"):
        return "Kerala Fire & Rescue / SDRF Kerala"
    return f"SDRF {state}" if state else "NDRF"
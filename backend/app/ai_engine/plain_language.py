"""Turns the technical severity index into plain-language citizen guidance.

Everything here is written for a non-expert: no weights, no acronyms, no
scores without a meaning. The output drives the "What this means for you"
panel on the dashboard.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.india_data import ZONE_INDEX

LEVEL_PLAIN = {
    "LOW": "Low risk",
    "MODERATE": "Moderate risk",
    "HIGH": "High risk",
    "VERY_HIGH": "Very high risk",
    "CRITICAL": "Critical risk",
}

LEVEL_ACTION = {
    "LOW": "No action needed. Keep an eye on local news.",
    "MODERATE": "Be prepared. Keep phones charged and important papers in a waterproof bag.",
    "HIGH": "Get ready to move. Pack essentials and agree a meeting point with your family.",
    "VERY_HIGH": "Act now. Move valuables and documents to a higher floor and be ready to evacuate.",
    "CRITICAL": "Emergency. Leave low-lying areas immediately and follow official evacuation routes.",
}

LEVEL_TRAFFIC = {
    "LOW": "green",
    "MODERATE": "yellow",
    "HIGH": "orange",
    "VERY_HIGH": "red",
    "CRITICAL": "red",
}

TRAFFIC_PLAIN = {
    "green": "All clear",
    "yellow": "Stay alert",
    "orange": "Be ready",
    "red": "Take action",
}

RAIN_WORDS = [
    (80, "extremely heavy rain"),
    (40, "very heavy rain"),
    (20, "heavy rain"),
    (8, "steady rain"),
    (1, "light rain"),
    (0, "little or no rain"),
]

_CATEGORY_PLAIN = {
    "FLOODED_ROAD": "roads under water",
    "TRAPPED_RESIDENTS": "people trapped",
    "EVACUATION_NEEDED": "people need evacuation",
    "POWER_OUTAGE": "power cuts",
    "HOSPITAL_ACCESS_BLOCKED": "hospital access blocked",
    "BRIDGE_COLLAPSE": "bridge damage",
    "LANDSLIDE": "landslides",
    "RELIEF_SHELTER_FULL": "shelters full",
    "WATER_CONTAMINATION": "unsafe drinking water",
    "COMMUNICATION_DOWN": "phone networks down",
}


def _rain_phrase(weather: Optional[Dict[str, Any]]) -> str:
    if not weather:
        return "rain data unavailable"
    active = weather.get("rain")
    if active is None:
        active = weather.get("precipitation")
    active = float(active or 0.0)
    for threshold, phrase in RAIN_WORDS:
        if active >= threshold:
            if active < 1:
                return phrase
            return "{} right now ({:.0f} mm)".format(phrase, active)
    return "little or no rain"


def _top_reason(zone: Dict[str, Any], river: Optional[Dict[str, Any]], weather: Optional[Dict[str, Any]]) -> str:
    scores = {
        "river": zone.get("river_score", 0) or 0,
        "rain": zone.get("weather_score", 0) or 0,
        "flooded area seen by satellite": zone.get("satellite_score", 0) or 0,
        "reports from people on the ground": zone.get("incident_score", 0) or 0,
    }
    driver = max(scores, key=scores.get)
    value = scores[driver]

    if driver == "river" and river:
        river_name = river.get("river") or "the river"
        status = (river.get("status") or "NORMAL").replace("_", " ").title()
        return "{} is running {} ({})".format(river_name, _river_plain(status), river.get("state") or "")
    if driver == "rain":
        return "heavy rain in the area — {}".format(_rain_phrase(weather))
    if driver == "flooded area seen by satellite":
        return "flood water has already spread across the area"
    if driver == "reports from people on the ground":
        return "multiple people on the ground are reporting flooding"
    return "rising water levels" if value >= 40 else "conditions are being monitored"


def _river_plain(status: str) -> str:
    s = status.lower()
    if "extreme" in s:
        return "above danger level"
    if "severe" in s:
        return "above warning level"
    if "above normal" in s or "above_normal" in s:
        return "slightly high"
    return "near normal"


def _people_at_risk(zones: Dict[str, Dict[str, Any]], threshold: float = 60.0) -> int:
    total = 0
    for zid, z in zones.items():
        if (z.get("overall_score") or 0) >= threshold:
            total += int(ZONE_INDEX.get(zid, {}).get("population", 0))
    return total


def _format_people(n: int) -> str:
    if n >= 10_000_000:
        return "{:.1f} crore people".format(n / 10_000_000)
    if n >= 100_000:
        return "{:.1f} lakh people".format(n / 100_000)
    if n >= 1_000:
        return "{:.0f} thousand people".format(n / 1_000)
    return "{} people".format(n)


def _headline(level: str, top: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> str:
    if level in ("CRITICAL", "VERY_HIGH"):
        lead = "Danger to life in parts of India"
    elif level == "HIGH":
        lead = "Flood risk is high across several states"
    elif level == "MODERATE":
        lead = "Flood risk is building in some areas"
    else:
        lead = "Flood risk is currently low across India"

    if not top:
        return lead + "."
    names = [t["name"] for t in top[:3]]
    if len(names) == 1:
        where = names[0]
    elif len(names) == 2:
        where = "{} and {}".format(names[0], names[1])
    else:
        where = "{}, {} and {}".format(names[0], names[1], names[2])
    return "{} — worst affected: {}.".format(lead, where)


def build_brief(
    regional: Dict[str, Any],
    zones: Dict[str, Dict[str, Any]],
    weather_map: Dict[str, Dict[str, Any]],
    river_map: Dict[str, Dict[str, Any]],
    incidents: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    source_summary: Dict[str, Any],
    updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    level = ((regional or {}).get("status") or "LOW").upper()
    score = float((regional or {}).get("score") or 0.0)
    traffic = LEVEL_TRAFFIC.get(level, "green")

    ranked = sorted(zones.values(), key=lambda z: z.get("overall_score", 0), reverse=True)
    top_zones = [z for z in ranked if (z.get("overall_score") or 0) >= 40][:8]

    top_areas: List[Dict[str, Any]] = []
    for z in top_zones:
        zid = z["zone_id"]
        pop = int(ZONE_INDEX.get(zid, {}).get("population", 0))
        zlevel = (z.get("severity_level") or "LOW").upper()
        top_areas.append({
            "zone_id": zid,
            "name": z.get("district") or z.get("zone_name"),
            "state": z.get("state"),
            "level": zlevel,
            "level_plain": LEVEL_PLAIN.get(zlevel, zlevel),
            "traffic_light": LEVEL_TRAFFIC.get(zlevel, "green"),
            "score": z.get("overall_score"),
            "people": pop,
            "people_text": _format_people(pop) if pop else "population unknown",
            "reason": _top_reason(z, river_map.get(zid), weather_map.get(zid)),
            "action": LEVEL_ACTION.get(zlevel, LEVEL_ACTION["MODERATE"]),
            "rising": bool(z.get("deteriorating")),
        })

    at_risk = _people_at_risk(zones)
    needs_help = [z for z in ranked if (z.get("overall_score") or 0) >= 60]

    category_counts: Dict[str, int] = {}
    for inc in incidents:
        cat = inc.get("category") or "OTHER"
        category_counts[cat] = category_counts.get(cat, 0) + 1
    main_problems = [
        {"problem": _CATEGORY_PLAIN.get(cat, cat.replace("_", " ").lower()), "count": n}
        for cat, n in sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)[:4]
    ]

    rain_phrases = [_rain_phrase(weather_map.get(z["zone_id"])) for z in top_zones[:4]]
    known = [p for p in rain_phrases if p != "rain data unavailable"]
    dry_now = bool(known) and all("little or no rain" in p for p in known)
    river_led = any(
        (river_map.get(z["zone_id"]) or {}).get("status") in ("EXTREME", "SEVERE")
        for z in top_zones
    )
    if not rain_phrases:
        rain_outlook = "No significant rainfall recorded in the worst-hit areas."
    elif not known:
        rain_outlook = "Rainfall readings are temporarily unavailable for the worst-hit areas."
    elif dry_now and river_led:
        rain_outlook = (
            "Worst-hit areas are seeing little or no rain right now — the danger is coming from rivers "
            "already running above warning or danger level, so water can keep rising without fresh rain."
        )
    else:
        rain_outlook = "Worst-hit areas are seeing " + ", ".join(sorted(set(known)))

    live_count = source_summary.get("streaming", source_summary.get("live", 0))
    source_note = "{} real-time data feed{} connected".format(live_count, "" if live_count == 1 else "s")
    if source_summary.get("streaming_names"):
        source_note += ": " + ", ".join(source_summary["streaming_names"][:4]) + "."
    elif source_summary.get("live_names"):
        source_note += ": " + ", ".join(source_summary["live_names"][:4]) + "."

    what_it_means = LEVEL_ACTION.get(level, LEVEL_ACTION["LOW"])
    if at_risk:
        what_it_means = "{} Currently about {} live in areas at high risk.".format(what_it_means, _format_people(at_risk))

    verified_alerts = [a for a in alerts if a.get("verified")]
    if verified_alerts:
        what_it_means += " {} verified alert{} from official agencies.".format(
            len(verified_alerts), "" if len(verified_alerts) == 1 else "s"
        )

    return {
        "level": level,
        "level_plain": LEVEL_PLAIN.get(level, level),
        "traffic_light": traffic,
        "traffic_plain": TRAFFIC_PLAIN.get(traffic, "Monitoring"),
        "headline": _headline(level, top_areas, alerts),
        "what_it_means": what_it_means,
        "what_to_do": [LEVEL_ACTION.get(level, LEVEL_ACTION["LOW"])] + [
            "Call 112 or 1078 for emergency help.",
            "Never walk or drive through moving flood water.",
            "Move to the nearest relief shelter if your area is asked to evacuate.",
        ][: 2 if level in ("LOW", "MODERATE") else 3],
        "score": score,
        "areas_needing_help": len(needs_help),
        "people_at_risk": at_risk,
        "people_at_risk_text": _format_people(at_risk) if at_risk else "no one in high-risk areas",
        "top_areas": top_areas,
        "main_problems": main_problems,
        "rain_outlook": rain_outlook,
        "verified_alerts": len(verified_alerts),
        "source_note": source_note,
        "updated_at": updated_at,
        "generated_at": datetime.now().isoformat(),
    }

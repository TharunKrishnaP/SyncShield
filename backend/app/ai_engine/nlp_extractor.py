"""Rule-based NLP incident extraction for citizen and field reports.

Extracts location, category, severity, and description from free-text Indian
report strings. Covers all-India place names drawn from the zone registry
and a dictionary of common Indian flood incident terminology in English and
transliterated Hindi/local languages.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from ..models.india_data import ZONE_INDEX, ZONES


# ---- Location lookup ----
_ZONE_NAME_LOOKUP = {}
for _z in ZONES:
    _ZONE_NAME_LOOKUP[_z["name"].lower()] = _z
    _ZONE_NAME_LOOKUP[_z["id"].lower()] = _z
    _ZONE_NAME_LOOKUP[_z["state"].lower()] = _z["state"]

# Neighbourhood / locality aliases (locality -> district zone id).
# Values are district-level zone ids so locality hits keep full precision.
_LOCALITY_MAP = {
    # ---- Assam (Guwahati metro) ----
    "nepal colony": "AS-Kamrup Metropolitan",
    "fancy bazaar": "AS-Kamrup Metropolitan",
    "satgaon": "AS-Kamrup Metropolitan",
    "kamrup": "AS-Kamrup Metropolitan",
    "saraighat": "AS-Kamrup Metropolitan",
    "alambazar": "AS-Kamrup Metropolitan",
    "pan bazaar": "AS-Kamrup Metropolitan",
    # ---- Delhi (NCT districts) ----
    "new delhi": "DL-New Delhi",
    "lutyens": "DL-New Delhi",
    "connaught place": "DL-New Delhi",
    "rk puram": "DL-South West Delhi",
    "safdarjung": "DL-South Delhi",
    "aiims": "DL-South Delhi",
    "jnu campus": "DL-South Delhi",
    "saket": "DL-South Delhi",
    "south delhi": "DL-South Delhi",
    "karol bagh": "DL-Central Delhi",
    "mg road": "DL-Central Delhi",
    "chandni chowk": "DL-Central Delhi",
    "fountain chowk": "DL-Central Delhi",
    "mandi house": "DL-Central Delhi",
    "old delhi": "DL-Central Delhi",
    "ashoka road": "DL-Central Delhi",
    "kuwait city": "DL-Central Delhi",
    "ammu colony": "DL-Central Delhi",
    "okhla": "DL-South East Delhi",
    "badarpur": "DL-South East Delhi",
    "madanpur khadar": "DL-South East Delhi",
    "east delhi": "DL-East Delhi",
    "trans yamuna": "DL-East Delhi",
    "vasundhara enclave": "DL-East Delhi",
    "mayur vihar": "DL-East Delhi",
    "shahdara": "DL-Shahdara",
    "north delhi": "DL-North Delhi",
    "alipur": "DL-North Delhi",
    "burari": "DL-North Delhi",
    "model town": "DL-North Delhi",
    "gtb nagar": "DL-North Delhi",
    "west delhi": "DL-West Delhi",
    "patel nagar": "DL-West Delhi",
    "kathputli colony": "DL-West Delhi",
    "moti nagar": "DL-West Delhi",
    "rohini": "DL-North West Delhi",
    "outer delhi": "DL-North West Delhi",
    "netaji subhash place": "DL-North West Delhi",
    "kanjhawla": "DL-North West Delhi",
    "bawana": "DL-North West Delhi",
    "pitampura": "DL-North West Delhi",
    "shalimar bagh": "DL-North West Delhi",
    "ashok vihar": "DL-North West Delhi",
    "mangolpuri": "DL-North West Delhi",
    "sultanpuri": "DL-North West Delhi",
    "dwarka": "DL-South West Delhi",
    "najafgarh": "DL-South West Delhi",
    "united india colony": "DL-West Delhi",
    # ---- NCR satellite cities (UP districts) ----
    "gautam buddha nagar": "UP-Gautam Buddha Nagar",
    "indirapuram": "UP-Ghaziabad",
    "vasundhara": "UP-Ghaziabad",
    "kaushambi": "UP-Ghaziabad",
    "vaishali": "UP-Ghaziabad",
    "crossings republik": "UP-Ghaziabad",
    "shipra sun city": "UP-Ghaziabad",
    "ahinsa khand": "UP-Ghaziabad",
    "govindpuram": "UP-Ghaziabad",
    "ramprastha": "UP-Ghaziabad",
    # ---- Uttar Pradesh river towns ----
    "varanasi cantt": "UP-Varanasi",
    "ganga ghat": "UP-Varanasi",
    "chunar ghat": "UP-Mirzapur",
    "rahmatpur": "UP-Kanpur Nagar",
    "riverside": "UP-Prayagraj",
    # ---- Gujarat (Ahmedabad metro) ----
    "adalat road": "GJ-Ahmedabad",
    "sarkhej": "GJ-Ahmedabad",
    "vasna": "GJ-Ahmedabad",
    # ---- Bihar (Patna / Bhagalpur) ----
    "railway colony": "BR-Patna",
    "bailey road": "BR-Patna",
    "patna city": "BR-Patna",
    "golghar": "BR-Patna",
    "sri rampur": "BR-Bhagalpur",
    # ---- Tamil Nadu (Chennai metro + Nilgiris) ----
    "nilgiri hills": "TN-Nilgiris",
    "adyar": "TN-Chennai",
    "adyar river": "TN-Chennai",
    "adyar backwaters": "TN-Chennai",
    "tambaram": "TN-Chennai",
    "thiruvanmiyur": "TN-Chennai",
    "perambur": "TN-Chennai",
    "kodambakkam": "TN-Chennai",
    "anna nagar": "TN-Chennai",
    "porur": "TN-Chennai",
    "sholinganallur": "TN-Chennai",
    "guindy": "TN-Chennai",
    "velachery": "TN-Chennai",
    "t nagar": "TN-Chennai",
    "cooum": "TN-Chennai",
    "puzhal": "TN-Chennai",
    "central chennai": "TN-Chennai",
    "chennai central": "TN-Chennai",
    "anna salai": "TN-Chennai",
    "napier bridge": "TN-Chennai",
    "mudichur": "TN-Chennai",
    "chromepet": "TN-Chennai",
    "pallavaram": "TN-Chennai",
    "kotturpuram": "TN-Chennai",
    "mylapore": "TN-Chennai",
    "teynampet": "TN-Chennai",
    "nungambakkam": "TN-Chennai",
    "egmore": "TN-Chennai",
    "royapuram": "TN-Chennai",
    "triplicane": "TN-Chennai",
    "saidapet": "TN-Chennai",
}

# ---- Severity keywords ----
_HIGH_SEVERITY_WORDS = [
    "rescue", "trapped", "stranded", "roof", "submerged", "completely flooded",
    "swept away", "drowning", "body", "dead", "casualty", "hospital",
    "electric shock", "gas leak", "landslide", "collapse", "breach",
]
_MED_SEVERITY_WORDS = [
    "heavy water", "road blocked", "water level rising", "rising water", "water rising",
    "power cut", "drainage overflow", "overflow", "bridge closed", "high water",
    "knee deep", "chest deep", "waist deep", "house flood", "car stuck",
    "cannot drive", "water logged", "waterlogging", "stuck", "families affected",
    "families trapped", "sq km", "kmt2", "water entering",
]
_LOW_SEVERITY_WORDS = [
    "water near", "drainage clogged", "minor flooding", "water on road",
    "slow traffic", "water entering",
]
_CONFIDENCE_WORDS = [
    "saw", "saw with my own eyes", "just now", "happening right now",
    "confirmed", "verified", "definitely", "clearly",
]
UNCERTAINTY_WORDS = ["maybe", "heard", "rumor", "rumour", "unsure", "possibly", "apparently"]

# ---- Category patterns ----
_CATEGORY_PATTERNS = {
    "FLOODED_ROAD": [
        r"flood(ed|ing)\s+road", r"road\s+(submerg|under\s*water|block)",
        r"water\s+(on|log|log?)\s*(ging)?\s+road",
        r"vehicle\s+stuck", r"car\s+(stuck|submerged)",
        r"traffic\s+(jam|stop|disrupt)", r"bridge\s+(close|wash|block|damag)",
        r"underpass\s+(flood|water|close)", r"nh-?\d+",
    ],
    "TRAPPED_RESIDENTS": [
        r"(people|person|men|women|child|children|family|residents?)\s+(trapped|stranded|maroon|stuck)",
        r"trapped\s+(in|on)\s+(house|roof|building|apartment)",
        r"stranded\s+(in|at|near)",
        r"(stuck|trapped)\s+(in|on)\s+(roof|terrace|first\s*floor|upper\s*floor)",
        r"need(?:s)?\s+(immediate|urgent)\s+rescue",
        r"rescue\s+team",
    ],
    "POWER_OUTAGE": [
        r"power\s+(outage|cut|fail|loss|shutdown)",
        r"electric(?:ity)?\s+(cut|loss|gone|fail|down)",
        r"no\s+(power|electricity|light)",
        r"transformer\s+(blow|burst|fire|fail|damag)",
        r"electric\s+(shock|wire|line|pole|fall|danger)",
    ],
    "HOSPITAL_ACCESS_BLOCKED": [
        r"hospital\s+(access|block|close|gate|road)",
        r"ambulance\s+(stuck|delay|cannot|road)",
        r"medical\s+(emergency|block|access)",
    ],
    "BRIDGE_COLLAPSE": [
        r"bridge\s+(collaps|fail|damag|wash|broken|part)",
        r"bridge\s+(water|bent|tilt|danger|fall)",
    ],
    "LANDSLIDE": [
        r"landslide", r"rock\s+fall", r"mudslide", r"soil\s+erosion",
        r"mountain\s+(collaps|slide|fall|crack)", r"hill\s+slip",
    ],
    "EVACUATION_NEEDED": [
        r"evacuat(e|ion|ing)", r"relocat(e|ion|ing)",
        r"shift\s+(people|residents|family|villager)", r"shifted",
        r"flooding\s+(house|home|village)", r"(village|colony|area)\s+flood",
        r"need(?:s|ed)?\s+boats?", r"boats?\s+(needed|required|requested)",
        r"send\s+boats?", r"boats?\s+needed\s+for", r"boats?\s+for\s+families",
    ],
    "RELIEF_SHELTER_FULL": [
        r"shelter\s+(full|overflow|crowd|pack|capac)",
        r"relief\s+camp\s+(full|crowd|overflow)",
        r"no\s+(food|water|medicine|kit)",
    ],
    "WATER_CONTAMINATION": [
        r"water\s+(contaminat|pollut|dirty|unsafe|colou?r|oil|chemical)",
        r"sewage\s+(mix|overflow|enter|pipe|drain|backflow)",
        r"drinking\s+water\s+(shortage|unavail|contaminat|pollut|unsafe)",
    ],
    "COMMUNICATION_DOWN": [
        r"(phone|mobile|net|internet|wifi|telephone)\s+(down|fail|no\s+signal|cut|loss|disrupt)",
        r"telecom\s+(fail|down|disrupt)",
    ],
}

# ---- Entity extraction regex helpers ----
_LOC_CANDIDATES = re.compile(
    r"(?:near|at|in|behind|next to|adjacent to|outside|outside of|beside)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*(?:Road|Street|Colony|Nagar|Marg|Park|Bridge|Underpass|Station|Hospital|Bazaar|Market|Colony|Complex|Road|Hospital))",
    re.IGNORECASE,
)


def _extract_location(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (zone_id, location_name) from free text."""
    low = text.lower()
    # 1. Exact zone id match
    for zid in ZONE_INDEX:
        if zid.lower() in low:
            return zid, ZONE_INDEX[zid]["name"]
    # 2. Zone name match (longest-first to avoid partials)
    for name, z in sorted(_ZONE_NAME_LOOKUP.items(), key=lambda kv: -len(kv[0])):
        if name in low and isinstance(z, dict) and "id" in z:
            return z["id"], z.get("name", name)
    # 3. Locality alias
    for locality, zid in _LOCALITY_MAP.items():
        if locality.lower() in low:
            return zid, locality.title()
    # 4. Regex near-entity
    m = _LOC_CANDIDATES.search(text)
    if m:
        return None, m.group(1).strip()
    return None, None


def _extract_severity(text: str) -> float:
    low = text.lower()
    if any(re.search(p, low) for p in _CATEGORY_PATTERNS.get("TRAPPED_RESIDENTS", [])):
        return 0.95
    if sum(1 for w in _HIGH_SEVERITY_WORDS if w in low) >= 2:
        return 0.9
    if any(w in low for w in _HIGH_SEVERITY_WORDS):
        return 0.8
    if sum(1 for w in _MED_SEVERITY_WORDS if w in low) >= 2:
        return 0.65
    if any(w in low for w in _MED_SEVERITY_WORDS):
        return 0.5
    return 0.3


def _extract_category(text: str) -> str:
    low = text.lower()
    cats = []
    for cat, patterns in _CATEGORY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, low):
                cats.append(cat)
                break
    if "TRAPPED_RESIDENTS" in cats:
        return "TRAPPED_RESIDENTS"
    if "BRIDGE_COLLAPSE" in cats:
        return "BRIDGE_COLLAPSE"
    if "LANDSLIDE" in cats:
        return "LANDSLIDE"
    return cats[0] if cats else "OTHER"


def _confidence_score(text: str, found_zone: bool, found_location: bool) -> float:
    low = text.lower()
    base = 0.6 if found_zone else 0.4 if found_location else 0.3
    if any(w in low for w in _CONFIDENCE_WORDS):
        base = min(base + 0.2, 1.0)
    if any(w in low for w in UNCERTAINTY_WORDS):
        base = max(base - 0.2, 0.1)
    return round(base, 3)


def _extract_coordinates(text: str, zone_id: Optional[str]) -> Optional[List[float]]:
    """Try to extract numeric lat/lon from text like 'at 12.34, 78.90'."""
    m = re.search(r"(\d{1,3}\.\d{2,6})\s*,\s*(\d{1,3}\.\d{2,6})", text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if 5 <= lat <= 38 and 68 <= lon <= 98:
            return [lon, lat]
    if zone_id and zone_id in ZONE_INDEX:
        return ZONE_INDEX[zone_id]["centroid"]
    return [78.0, 20.0]


def extract_incident(
    text: str,
    timestamp: str = "",
    source: str = "CITIZEN_REPORT",
    explicit_zone: Optional[str] = None,
) -> Dict[str, Any]:
    """Full NLP extraction pipeline on a single report string."""
    zone_id = explicit_zone
    location_name = None
    if not zone_id:
        zone_id, location_name = _extract_location(text)
    severity = _extract_severity(text)
    regex_category = _extract_category(text)

    # Trained ML layer (Phase 1): the SVM decides first; the rule engine stays
    # as the rescue + location/severity extractor. Fail-soft by design.
    ml_pred = None
    try:
        from ..ml.text_classifier import ml_text_classifier

        if ml_text_classifier.available:
            ml_pred = ml_text_classifier.classify(text, regex_category=regex_category)
    except Exception:
        ml_pred = None

    category = ml_pred["category"] if ml_pred else regex_category
    zone = ZONE_INDEX.get(zone_id) if zone_id else None
    centroid = _extract_coordinates(text, zone_id)

    # Confidence and explanation
    confidence = _confidence_score(text, bool(zone_id), bool(location_name))

    explanation = {
        "reasoning": f"Classified as {category} with severity {severity:.2f}",
        "location_found": bool(zone_id or location_name),
        "confidence_note": "High confidence (confirmed sources)" if confidence > 0.7 else "Moderate confidence" if confidence > 0.4 else "Low confidence — unverified report",
        "category_signals": [p for p in _CATEGORY_PATTERNS.get(category, []) if re.search(p, text.lower())][:3],
    }
    if ml_pred:
        explanation["ml_classification"] = {
            "model": ml_pred.get("model"),
            "method": ml_pred.get("method"),
            "confidence": ml_pred.get("confidence"),
            "top3": ml_pred.get("top3"),
        }

    return {
        "location_name": location_name or (zone["name"] if zone else "Unknown"),
        "zone_id": zone_id,
        "latitude": centroid[1],
        "longitude": centroid[0],
        "state": zone.get("state", "") if zone else "",
        "district": zone.get("district", zone.get("name", "")) if zone else "",
        "category": category,
        "severity": severity,
        "description": text.strip(),
        "source": source,
        "confidence": confidence,
        "verified": False,
        "nlp_extracted": explanation,
        "centroid": centroid,
    }
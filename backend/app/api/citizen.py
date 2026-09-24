"""Citizen self-service API.

* POST /api/citizen/reports            — report flooding with free text, optional
  geotag, phone number and photo → NLP-parsed into a trackable incident ticket.
* GET  /api/citizen/reports/{id}       — look up a submitted report.
* POST /api/citizen/reports/{id}/status — EOC moderation: NEW→REVIEWING→VERIFIED→RESOLVED.
* POST /api/citizen/area-check         — check risk at a lat/lon: nearest zone
  risk level, shelters, rescue bases and helplines.
* GET  /api/citizen/media/{filename}   — serve an uploaded photo.

Citizen reports land in the same incident stream the AI engine scores, so a
photo-report immediately influences regional risk, exactly as field reports do.
"""
import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import settings
from ..orchestrator import orchestrator
from ..ai_engine.nlp_extractor import extract_incident
from ..ai_engine.situation_scorer import _status_label
from ..models.india_data import ZONES, INFRASTRUCTURE
from ..models.emergency_data import contacts_payload

router = APIRouter()

_ALLOWED_MEDIA = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_MAX_MEDIA_BYTES = 5 * 1024 * 1024

_STATUS_FLOW = ["NEW", "REVIEWING", "VERIFIED", "DISPATCHED", "RESOLVED"]


class AreaCheckRequest(BaseModel):
    latitude: float
    longitude: float
    language: str = "en"


class StatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None


# ----------------------------------------------------------------------
# Report submission
# ----------------------------------------------------------------------

@router.post("/citizen/reports")
async def citizen_report(
    text: str = Form(..., min_length=3),
    contact: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    language: str = Form("en"),
    photo: Optional[UploadFile] = File(None),
):
    report_id = secrets.token_hex(4).upper()
    media_path = None

    if photo and photo.filename:
        if photo.content_type not in _ALLOWED_MEDIA:
            raise HTTPException(415, "Photo must be JPEG/PNG/WebP")
        data = await photo.read()
        if len(data) > _MAX_MEDIA_BYTES:
            raise HTTPException(413, "Photo too large (max 5 MB)")
        os.makedirs(settings.CITIZEN_MEDIA_DIR, exist_ok=True)
        media_name = f"{report_id}{_ALLOWED_MEDIA[photo.content_type]}"
        with open(os.path.join(settings.CITIZEN_MEDIA_DIR, media_name), "wb") as fh:
            fh.write(data)
        media_path = f"/api/citizen/media/{media_name}"

    incident = extract_incident(
        text=text,
        timestamp=datetime.now().isoformat(),
        source="CITIZEN_REPORT",
    )
    if latitude is not None and longitude is not None and 5 <= latitude <= 38 and 68 <= longitude <= 98:
        incident["latitude"] = latitude
        incident["longitude"] = longitude
        zone = orchestrator._nearest_zone(latitude, longitude)
        if zone:
            incident["zone_id"] = zone["id"]
            incident["state"] = zone["state"]
            incident["district"] = zone.get("district", zone["name"])

    incident.update({
        "id": f"cit-{report_id}",
        "report_id": report_id,
        "status": "NEW",
        "contact": contact or None,
        "language": language if language in ("en", "hi") else "en",
        "media": media_path,
        "submitted_at": datetime.now().isoformat(),
    })
    orchestrator.datalake.add_incident(incident)
    orchestrator.datalake.log_event({
        "timestamp": datetime.now().isoformat(),
        "type": "CITIZEN_REPORT",
        "message": "New citizen flood report {} ({}) — zone {}".format(report_id, incident.get("category"), incident.get("zone_id")),
    })
    orchestrator.datalake.persist(force=True)
    return {
        "report_id": report_id,
        "ticket": f"FDR-{report_id}",
        "status": "NEW",
        "zone_id": incident.get("zone_id"),
        "zone_name": incident.get("location_name"),
        "category": incident.get("category"),
        "severity": incident.get("severity"),
        "media": media_path,
        "check_status_url": f"/api/citizen/reports/{report_id}",
    }


@router.get("/citizen/reports/{report_id}")
async def citizen_report_status(report_id: str):
    for inc in orchestrator.datalake.get_incidents(limit=500):
        if inc.get("report_id") == report_id:
            return {
                "report_id": report_id,
                "status": inc.get("status", "NEW"),
                "category": inc.get("category"),
                "zone_id": inc.get("zone_id"),
                "zone_name": inc.get("location_name"),
                "severity": inc.get("severity"),
                "media": inc.get("media"),
                "submitted_at": inc.get("submitted_at"),
                "verified": inc.get("verified", False),
            }
    raise HTTPException(404, "Report not found")


@router.post("/citizen/moderation/{report_id}")
async def citizen_moderate(report_id: str, req: StatusUpdateRequest):
    if req.status not in _STATUS_FLOW:
        raise HTTPException(400, f"status must be one of {_STATUS_FLOW}")
    incidents = orchestrator.datalake.get_incidents(limit=500)
    for i, inc in enumerate(incidents):
        if inc.get("report_id") == report_id:
            inc["status"] = req.status
            if req.status == "VERIFIED":
                inc["verified"] = True
            if req.note:
                inc.setdefault("moderation_log", []).append({"at": datetime.now().isoformat(), "action": req.status, "note": req.note})
            orchestrator.datalake._store["incidents"][i] = inc
            orchestrator.datalake.persist(force=True)
            await orchestrator.refresh(force=True)
            return {"report_id": report_id, "status": req.status, "updated": True}
    raise HTTPException(404, "Report not found")


@router.get("/citizen/media/{filename}")
async def citizen_media(filename: str):
    if not filename.replace(".", "", 1).isalnum() and not filename.endswith((".jpg", ".png", ".webp")):
        raise HTTPException(400, "Invalid media name")
    path = os.path.normpath(os.path.join(settings.CITIZEN_MEDIA_DIR, filename))
    if not path.startswith(os.path.normpath(settings.CITIZEN_MEDIA_DIR)):
        raise HTTPException(400, "Invalid media name")
    if not os.path.exists(path):
        raise HTTPException(404, "Media not found")
    return FileResponse(path)


# ----------------------------------------------------------------------
# Area check
# ----------------------------------------------------------------------

@router.post("/citizen/area-check")
async def area_check(req: AreaCheckRequest):
    if not (5 <= req.latitude <= 38 and 68 <= req.longitude <= 98):
        raise HTTPException(400, "Coordinates must fall within India's range")

    # Nearest monitored point anywhere in India (priority zone / river gauge /
    # flood-prone town) — not restricted to the 52 priority districts.
    locators = orchestrator._locate(req.latitude, req.longitude, k=4)
    if not locators:
        raise HTTPException(422, "No covered location near those coordinates")
    here = locators[0]
    nearest_zone = orchestrator._nearest_zone(req.latitude, req.longitude)
    if not nearest_zone:
        raise HTTPException(422, "No covered zone near those coordinates")

    zones = orchestrator._current.get("zones", {}) or {}

    # Distance-weighted blend of the K nearest priority-zone scores so *any*
    # point gets a continuous estimate; falls back to the national score.
    def zone_dist(z):
        pts = z.get("coordinates") or [z["centroid"]]
        return min(orchestrator._haversine(req.latitude, req.longitude, p[1], p[0]) for p in pts)

    ranked = sorted(ZONES, key=zone_dist)[:3]
    weights, weighted, closest = [], 0.0, []
    for z in ranked:
        d = zone_dist(z)
        zs = zones.get(z["id"]) or {}
        score = float(zs.get("overall_score") or 0.0)
        w = 1.0 / (d + 25.0)
        weights.append(w)
        weighted += w * score
        closest.append({
            "zone_id": z["id"],
            "name": z.get("district") or z["name"],
            "state": z["state"],
            "distance_km": round(d, 1),
            "score": round(score, 1),
            "level": zs.get("severity_level") or "LOW",
            "level_plain": zs.get("severity_plain") or (zs.get("severity_level") or "Low").title(),
        })
    regional_score = float((orchestrator._current.get("regional") or {}).get("score") or 0.0)
    blended = (weighted / sum(weights)) if weights else regional_score
    # Pull toward the national picture when the location is far from any zone.
    influence = max(0.0, min(1.0, 1.0 - here["distance_km"] / 300.0))
    score = blended * influence + regional_score * (1.0 - influence)

    level = _status_label(score)
    level_plain = level.replace("_", " ").title()
    confidence = int(max(20, min(100, round(100 - here["distance_km"] * 1.1))))

    shelters = _nearest_items(INFRASTRUCTURE.get("shelters", []), req.latitude, req.longitude, 3, ["name", "capacity", "zone"])
    bases = _nearest_items(INFRASTRUCTURE.get("rescue_bases", []), req.latitude, req.longitude, 2, ["name", "agency", "personnel", "boats"])
    hospitals = _nearest_items(INFRASTRUCTURE.get("hospitals", []), req.latitude, req.longitude, 2, ["name", "beds", "capacity_status"])

    river_map = {r.get("station_id"): r for r in orchestrator._current.get("water_levels", [])}
    station_rows = [
        {"id": sid, "name": name, "lat": lat, "lon": lon}
        for sid, name, river, basin, st_state, lat, lon, wl, dl, hfl, stype in _river_stations()
    ]
    nearby = _nearest_items(station_rows, req.latitude, req.longitude, 3, [])
    rivers = []
    for st in nearby:
        reading = river_map.get(st.get("id")) or {}
        rivers.append({
            "station": reading.get("station") or st.get("name"),
            "river": reading.get("river"),
            "state": reading.get("state"),
            "distance_km": st.get("distance_km"),
            "water_level": reading.get("water_level"),
            "warning_level": reading.get("warning_level"),
            "status": reading.get("status"),
            "flow_plain": reading.get("flow_plain"),
            "rate_of_rise": reading.get("rate_of_rise"),
        })

    hp = contacts_payload()["helplines"][:5]

    guidance = _area_guidance(level, score, req.language)
    zlon, zlat = nearest_zone["centroid"]
    return {
        "location": {
            "latitude": req.latitude,
            "longitude": req.longitude,
            "region_name": here["name"],
            "region_type": here["type"],
            "district": here.get("district"),
            "state": here.get("state"),
            "basin": here.get("basin"),
            "distance_km": here["distance_km"],
        },
        "zone_id": nearest_zone["id"],
        "zone_name": nearest_zone["name"],
        "state": here.get("state") or nearest_zone["state"],
        "district": here.get("district") or nearest_zone.get("district", nearest_zone["name"]),
        "basin": here.get("basin") or nearest_zone["basin"],
        "distance_km_covered": round(orchestrator._haversine(req.latitude, req.longitude, zlat, zlon), 1),
        "confidence": confidence,
        "coverage": {
            "nearest_point": here["name"],
            "nearest_point_type": here["type"],
            "nearest_point_km": here["distance_km"],
            "monitored_points_considered": len(locators),
            "national_score": round(regional_score, 1),
            "blended": round(blended, 1),
        },
        "risk": {"score": round(score, 1), "level": level, "level_plain": level_plain},
        "closest_zones": closest,
        "nearby_rivers": rivers,
        "shelters": shelters,
        "rescue_bases": bases,
        "hospitals": hospitals,
        "helplines": hp,
        "guidance": guidance,
        "generated_at": datetime.now().isoformat(),
    }


def _river_stations():
    from ..models.india_data import RIVER_STATIONS

    return RIVER_STATIONS


def _nearest_items(items: List[Dict[str, Any]], lat: float, lon: float, n: int, fields: List[str]) -> List[Dict[str, Any]]:
    def dist(it):
        return orchestrator._haversine(lat, lon, it.get("lat"), it.get("lon"))

    ranked = sorted(items, key=dist)[:n]
    out = []
    for it in ranked:
        row = {
            "name": it.get("name"),
            "distance_km": round(dist(it), 1),
            "zone": it.get("zone"),
        }
        for f in fields:
            if it.get(f) is not None:
                row[f] = it.get(f)
        oid = it.get("id")
        if oid:
            row["id"] = oid
        out.append(row)
    return out


def _area_guidance(level: str, score: float, language: str = "en") -> List[str]:
    base = {
        "LOW": "No major flooding expected. Keep emergency numbers saved and watch the river near you.",
        "MODERATE": "Water may exceed warning level. Stay updated, avoid flooded stretches, keep documents packed.",
        "HIGH": "Flooding likely. Prepare to move valuables up, keep boats/elevated areas ready, follow NDMA alerts.",
        "VERY_HIGH": "Situations can escalate fast. Are you near a river, low-lying or embankment? Move to higher ground early.",
        "CRITICAL": "Immediate action needed. Move to the nearest shelter now and help limited-mobility neighbours if it is safe.",
    }[level]
    hi_hints = []
    if score >= 60:
        hi_hints.append("Share your location with family using 'check my area' so they know yours is safe.")
    list = [base] + hi_hints
    if language == "hi":
        list.append("अपने क्षेत्र की सूचनाएँ स्थानीय प्रशासन से भी मिला कर रखें।")
    return list
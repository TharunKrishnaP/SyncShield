"""Official data intake API.

* ``POST /api/official/ingest`` — import an official CWC/IMD/NDMA/state-EOC
  bulletin (CSV, JSON or GeoJSON) so real official measurements enter the
  datalake without waiting for accredited live APIs.
* ``GET /api/official/templates`` and ``GET /api/official/templates/{source}``
  — contract documentation and a downloadable sample for each source.

Works against the live datalake; a successful import is recorded in the
``official_bulletin`` source status and in the event timeline.
"""
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from ..orchestrator import orchestrator
from ..ingestion.official_connectors import OfficialBulletinIngestor
from ..ingestion.source_registry import registry

router = APIRouter()

_SOURCE_LABELS = {
    "cwc": "Central Water Commission river-level bulletin (CSV/JSON)",
    "imd": "IMD district rainfall bulletin (CSV/JSON)",
    "ndma": "NDMA/SACHET CAP alert GeoJSON",
    "eoc": "State EOC field reports (CSV/JSON)",
}

_SAMPLES = {
    "cwc": "STATION_ID,water_level,warning_level,danger_level,rate_of_rise,discharge,timestamp\nBR-PATNA,45.20,46.00,47.00,0.35,1234.5,2026-09-21T06:00:00Z\nOD-CUTTACK,25.10,25.40,26.10,-0.10,890.2,2026-09-21T06:00:00Z\n",
    "imd": "zone_id,rain_mm,timestamp\nKL-KOTTAYAM,24.5,2026-09-21T06:00:00Z\nAS-GUWAHATI,58.2,2026-09-21T06:00:00Z\n",
    "ndma": '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"identifier":"NDMA-2026-001","headline":"Extreme rainfall alert for Patna","state":"Bihar","district":"Patna","severity":"Severe","lat":25.5941,"lon":85.1376}}]}',
    "eoc": '[{"zone_id":"BR-PATNA","text":"Water entering 3 colonies near Digha, boats requested","source":"STATE_EOC","timestamp":"2026-09-21T06:00:00Z"}]',
}


@router.get("/official/templates")
async def official_templates():
    return {
        "sources": [
            {"key": k, "label": v, "format": "csv|json" if k in ("cwc", "imd", "eoc") else "geojson"}
            for k, v in _SOURCE_LABELS.items()
        ],
        "columns": {
            "cwc": ["STATION_ID", "water_level", "(optional) warning_level danger_level rate_of_rise discharge timestamp"],
            "imd": ["zone_id", "rain_mm", "(optional) timestamp"],
            "ndma": ["GeoJSON FeatureCollection with properties.identifier/headline/state/district/severity/lat/lon"],
            "eoc": ["array of segment objects: zone_id, text, (optional) source, lat, lon"],
        },
    }


@router.get("/official/templates/{source}")
async def official_template(source: str):
    if source not in _SAMPLES:
        raise HTTPException(404, f"Unknown source '{source}' — use cwc|imd|ndma|eoc")
    return PlainTextResponse(_SAMPLES[source])


@router.post("/official/ingest")
async def official_ingest(
    file: UploadFile = File(...),
    source: str = Form(...),
    format: Optional[str] = Form(None),
):
    if source not in _SOURCE_LABELS:
        raise HTTPException(400, f"source must be one of {list(_SOURCE_LABELS)}")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    try:
        ingestor = OfficialBulletinIngestor(orchestrator.datalake)
        result = ingestor.ingest(source=source, raw=raw, format_hint=format)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    orchestrator.datalake.persist(force=True)
    status = registry.get("official_bulletin")
    return JSONResponse({"imported": True, "rows": result["rows"], "source": source, "source_status": status})


@router.post("/official/refresh-keys")
async def refresh_official_keys():
    """Re-run the key-gated official connectors (IMD/CWC/SACHET).

    Tells you exactly which sources are live with the keys currently in .env.
    """
    results = await orchestrator.official.cwc_sachet_only()
    return {
        "imd": results["imd"].__dict__,
        "cwc": results["cwc"].__dict__,
        "sachet": results["sachet"].__dict__,
    }
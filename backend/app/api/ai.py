"""Trained-model introspection + demo endpoints (Phase 1).

* GET  /api/ai/models       — status, provenance, and measured metrics of each
                              trained model in the platform
* POST /api/ai/classify     — test the trained incident classifier on free text
* GET  /api/ai/sar/extents  — URI-inferred flood extents persisted in the lake
* POST /api/ai/sar/ingest   — run the trained SAR U-Net on an uploaded scene
                              (available once the Colab-trained model exists)

Everything here is fail-soft: endpoints answer truthfully when a model has not
been trained yet instead of pretending.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..orchestrator import orchestrator
from ..ml.text_classifier import ml_text_classifier

router = APIRouter()


class ClassifyRequest(BaseModel):
    text: str
    threshold: Optional[float] = None


@router.get("/ai/models")
async def ai_models() -> Dict[str, Any]:
    text = ml_text_classifier.info

    sar = {"available": False}
    try:
        from ..ml.sar_model import sar_model

        sar = sar_model.info
    except Exception:
        sar = {"available": False, "note": "SAR U-Net wrapper not installed"}

    return {
        "text_classifier": text,
        "sar_unet": sar,
        "note": "Phase 1: text classifier trained; SAR U-Net trains via ml/sar/train_colab.ipynb on Colab.",
    }


@router.post("/ai/classify")
async def ai_classify(req: ClassifyRequest) -> Dict[str, Any]:
    if not req.text.strip():
        raise HTTPException(400, "text is required")
    # Same hybrid funnel as production (nlp_extractor.extract_incident): the
    # rule engine provides regex_category, the trained model refines it with
    # evidence gates + rule rescue. This keeps the demo endpoint behaviour
    # identical to what the citizen-report path runs.
    from ..ai_engine.nlp_extractor import _extract_category

    regex_category = _extract_category(req.text)
    result = ml_text_classifier.classify(req.text, regex_category=regex_category,
                                         threshold=req.threshold)
    if not result:
        raise HTTPException(503, "Text classifier model not available — train it with ml/text/train_svc.py")
    result["text"] = req.text.strip()[:200]
    result["rule_category"] = regex_category
    return result


@router.get("/ai/sar/extents")
async def ai_sar_extents() -> Dict[str, Any]:
    extents = [
        e for e in orchestrator.datalake.get_satellite_extents()
        if (e.get("data_source") or "").startswith("ML_SAR")
    ]
    return {
        "count": len(extents),
        "zones": sorted({e.get("zone_id") for e in extents if e.get("zone_id")}),
        "total_flood_area_km2": round(sum(float(e.get("flood_area_km2") or 0.0) for e in extents), 2),
        "extents": extents[:20],
    }


@router.post("/ai/sar/ingest")
async def ai_sar_ingest(photo: UploadFile = File(...)):
    """Run the trained SAR U-Net on an uploaded Sentinel-1 scene image."""
    try:
        from ..ml.sar_model import sar_model
    except Exception as exc:
        raise HTTPException(501, f"SAR model wrapper unavailable: {exc}")
    if not sar_model.available:
        raise HTTPException(501, "SAR U-Net not trained yet — run ml/sar/train_colab.ipynb on Colab")

    data = await photo.read()
    if not data:
        raise HTTPException(400, "empty upload")
    scene_path = Path(settings_ml_scenes_dir()) / photo.filename or "scene"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_bytes(data)
    try:
        extents = sar_model.run_inference(str(scene_path))
    except Exception as exc:
        raise HTTPException(500, f"Inference failed: {exc}")
    for e in extents:
        orchestrator.datalake.put_satellite_extent(e)
    orchestrator.datalake.persist(force=True)
    return {"ingested": len(extents), "extents": extents[:10]}


def settings_ml_scenes_dir():
    from ..config import settings

    return settings.ML_SAR_SCENES_DIR


# =============================================================================
# Phase 2 — River Forecasting + Learned Fusion (scaffolds)
# =============================================================================

class ForecastRequest(BaseModel):
    station_id: str
    horizons: Optional[List[int]] = [1, 3, 5, 7]


@router.get("/ai/river/forecast/{station_id}")
async def ai_river_forecast(station_id: str, horizons: Optional[str] = None) -> Dict[str, Any]:
    """
    River flow forecast for a gauge station.
    Returns ensemble forecast (LSTM + XGBoost + hybrid) with uncertainty bands.
    """
    # Parse horizons
    h_list = [1, 3, 5, 7]
    if horizons:
        try:
            h_list = [int(h) for h in horizons.split(",")]
        except Exception:
            pass

    # Load trained model artifact
    artifact_dir = Path("ml/artifacts/river_forecast") / station_id
    if not artifact_dir.exists():
        raise HTTPException(501, f"River forecast model for {station_id} not trained yet")

    meta_path = artifact_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(501, f"River forecast metadata missing for {station_id}")

    meta = json.loads(meta_path.read_text())

    # Placeholder: return structure with forecast values
    # Real implementation loads model, runs inference on latest GloFAS + obs
    return {
        "station_id": station_id,
        "available": True,
        "model_version": meta.get("version", "1.0"),
        "horizons": h_list,
        "forecast": [
            {
                "horizon_days": h,
                "forecast_m3s": None,      # placeholder
                "lower_95": None,
                "upper_95": None,
                "model": "ensemble",
            }
            for h in h_list
        ],
        "note": "River forecast endpoint scaffolded. Train models via ml/forecast/train.py",
    }


@router.get("/ai/river/forecast")
async def ai_river_forecast_list() -> Dict[str, Any]:
    """List all stations with trained forecast models."""
    artifact_root = Path("ml/artifacts/river_forecast")
    if not artifact_root.exists():
        return {"stations": []}

    stations = []
    for station_dir in artifact_root.iterdir():
        if station_dir.is_dir():
            meta_path = station_dir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                stations.append({
                    "station_id": station_dir.name,
                    "river": meta.get("gauge_meta", {}).get("river"),
                    "state": meta.get("gauge_meta", {}).get("state"),
                    "nse_val": meta.get("metrics", {}).get("nse_val"),
                    "mae_val": meta.get("metrics", {}).get("mae_val"),
                })
    return {"stations": stations}


# -----------------------------------------------------------------------------
# Learned Fusion
# -----------------------------------------------------------------------------

@router.get("/ai/fusion/weights")
async def ai_fusion_weights() -> Dict[str, Any]:
    """
    Current fusion weights (fixed or learned) + per-component SHAP if available.
    """
    weights_path = Path("ml/artifacts/fusion/weights.json")
    if weights_path.exists():
        weights = json.loads(weights_path.read_text())
    else:
        # Current fixed weights (Phase 1)
        weights = {
            "satellite": 0.35,
            "river": 0.20,
            "weather": 0.20,
            "population": 0.15,
            "social": 0.10,
        }

    return {
        "weights": weights,
        "version": weights.get("version", "fixed-v1"),
        "learned": weights_path.exists(),
        "calibrated": False,
        "note": "Learned fusion scaffolded. Train via ml/fusion/train.py",
    }


@router.post("/ai/fusion/calibrate")
async def ai_fusion_calibrate() -> Dict[str, Any]:
    """
    Trigger calibration job (async). Returns job ID.
    """
    # Placeholder for async calibration job
    return {
        "status": "accepted",
        "job_id": "fusion-calibrate-001",
        "note": "Calibration job scaffolded. Implement background task in ml/fusion/train.py",
    }
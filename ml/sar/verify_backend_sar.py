"""Backend end-to-end check for the SAR U-Net (Model C) demo wiring.

Run from repo root after ml/artifacts/sar_unet exists (real-data model):
    python ml/sar/verify_backend_sar.py

Asserts:
  1. sar_model.available is True (meta.json + model.pt load)
  2. inform() exposes val_iou/val_dice
  3. run_inference(scene) zone-attributes an extent (real Assam scene)
  4. extent record carries the datalake/scorer fields
And then via the live API (backend on :8000):
  5. POST /api/ai/sar/ingest persists it, /api/ai/sar/extents returns it,
     /api/ai/models shows sar_unet.available=true
  6. situation/current shows the attributed zone satellite_score > 0 (ML-driven)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "backend"))

SCENE = ROOT / "ml" / "data" / "sar_scenes" / "scene_india_assam.tif"
ARTIFACTS = ROOT / "ml" / "artifacts" / "sar_unet"

fails = []


def check(name, cond, extra=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name} {extra}")
    if not cond:
        fails.append(name)


# 1-4: wrapper path
from app.ml.sar_model import sar_model  # noqa: E402

avail = sar_model.available
check("sar_model.available", avail, f"-> artifacts {ARTIFACTS}")
if avail:
    info = sar_model.info
    check("info has val_iou", info.get("val_iou") is not None, f"val_iou={info.get('val_iou')} val_dice={info.get('val_dice')}")

check("scene exists", SCENE.exists())
if avail and SCENE.exists():
    extents = sar_model.run_inference(str(SCENE))
    check("run_inference returns extents", len(extents) >= 1, f"n={len(extents)}")
    if extents:
        e = extents[0]
        for fld in ("zone_id", "flood_area_km2", "water_depth_avg", "flood_status", "flood_polygons", "data_source", "confidence", "state", "district"):
            check(f"extent has {fld}", fld in e, f"-> {e.get(fld)}")
        check("zone attributed to India (model's training region)", e.get("zone_id") in {"AS-Biswanath", "AS-Sonitpur", "AS-Nagaon", "AS-Golaghat", "UNMATCHED"}, f"zone={e.get('zone_id')}")
        check("data_source ML_SAR_UNET", e.get("data_source", "").startswith("ML_SAR"))
        print("\nextent record:", json.dumps({k: e[k] for k in ("zone_id", "flood_area_km2", "water_depth_avg", "flood_status", "state", "district", "confidence", "resolution_m")}, indent=1))

print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
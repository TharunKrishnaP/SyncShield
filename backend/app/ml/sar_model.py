"""Trained SAR U-Net wrapper (Phase 1 model C). Fail-soft.

Loads ``ml/artifacts/sar_unet/{meta.json, model.pt}`` (trained by
``ml/sar/train_unet.py``) and exposes:

    sar_model.available          -> bool
    sar_model.info               -> provenance + measured IoU/Dice
    sar_model.run_inference(scene_path) -> [extent records] with zone attribution

Each extent record matches the datalake satellite-extent shape consumed by the
situation scorer (flood_area_km2, water_depth_avg, flood_status ...) so real,
ML-generated flood extents fill the 0.35 satellite weight instead of 0.
"""
import json
import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings

_ARTIFACTS = Path(settings.ML_SAR_DIR)


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class SARSegmentationModel:
    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._meta: Optional[Dict[str, Any]] = None
        self._load_attempted = False

    # ------------------------------------------------------------------
    def _load(self) -> bool:
        with self._lock:
            if self._load_attempted:
                return self._model is not None
            self._load_attempted = True
            try:
                meta_path = _ARTIFACTS / "meta.json"
                model_path = _ARTIFACTS / "model.pt"
                if not (meta_path.exists() and model_path.exists()):
                    return False
                self._meta = json.loads(meta_path.read_text(encoding="utf-8"))
                import torch

                try:
                    from ml.sar.infer import rebuild_model  # repo-root import
                except Exception:
                    import importlib.util
                    import sys

                    spec = importlib.util.spec_from_file_location(
                        "ml_sar_infer", str(Path(settings.ML_ARTIFACTS_DIR).parent.parent / "ml" / "sar" / "infer.py")
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    rebuild_model = mod.rebuild_model
                self._model = rebuild_model(self._meta, str(_ARTIFACTS))
                self._model.eval()
                return True
            except Exception:
                self._model, self._meta = None, None
                return False

    @property
    def available(self) -> bool:
        return self._load()

    @property
    def info(self) -> Dict[str, Any]:
        if not self._load():
            return {
                "available": False,
                "artifacts_dir": str(_ARTIFACTS),
                "note": "Train the U-Net first: ml/sar/train_colab.ipynb (Colab) or --mode synthetic for a pipeline-certified smoke model.",
            }
        return {
            "available": True,
            "mode": self._meta.get("mode"),
            "encoder": self._meta.get("encoder"),
            "val_iou": self._meta.get("val_iou"),
            "val_dice": self._meta.get("val_dice"),
            "trained_at": self._meta.get("trained_at"),
            "artifacts_dir": str(_ARTIFACTS),
            "note": self._meta.get("note"),
        }

    # ------------------------------------------------------------------
    def zone_attribution(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a scene-level extent into zone records for the datalake/scorer.

        Uses the scene polygon centroid -> nearest priority zone (India-wide).
        A single record is produced per matched zone; unmatched area is
        attributed to the nearest zone overall.
        """
        from ..models.india_data import ZONES

        polys = record.get("flood_polygons") or []
        if not polys:
            zid = None
        else:
            xs = [p[0] for p in polys[0]]
            ys = [p[1] for p in polys[0]]
            clon, clat = sum(xs) / len(xs), sum(ys) / len(ys)
            best, best_d = None, float("inf")
            for z in ZONES:
                lon, lat = z["centroid"]
                d = _haversine(clat, clon, lat, lon)
                if d < best_d:
                    best_d, best = d, z
            if best is None or best_d > 400:
                best = None
            zid = best["id"] if best else None

        out = dict(record)
        out["zone_id"] = zid or "UNMATCHED"
        out["flood_polygons"] = [
            [[round(x, 5), round(y, 5)] for x, y in poly] for poly in polys
        ]
        if zid:
            out["state"] = next((z["state"] for z in ZONES if z["id"] == zid), "")
            out["district"] = next((z.get("district", z["name"]) for z in ZONES if z["id"] == zid), "")
            out["basin"] = next((z.get("basin", "") for z in ZONES if z["id"] == zid), "")
        # scorer needs a plausible estimated depth & status — carried from build_extent
        return [out]

    def run_inference(self, scene_path: str) -> List[Dict[str, Any]]:
        """Run the U-Net on a scene GeoTIFF; returns zone-attributed extents."""
        if not self._load():
            raise RuntimeError("SAR U-Net model not trained")
        try:
            from ml.sar.infer import infer_scene
        except Exception:
            import importlib.util
            import sys

            spec = importlib.util.spec_from_file_location(
                "ml_sar_infer", str(Path(settings.ML_ARTIFACTS_DIR).parent.parent / "ml" / "sar" / "infer.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            infer_scene = mod.infer_scene

        record = infer_scene(self._model, self._meta, scene_path)
        if record is None:
            return []
        return self.zone_attribution(record)


sar_model = SARSegmentationModel()
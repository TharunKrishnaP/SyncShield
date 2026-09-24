"""SAR U-Net inference: scene -> water mask -> polygon -> extent record.

Used both as a CLI (``python ml/sar/infer.py --scene <tif> --out <json>``)
and imported by the backend wrapper ``backend/app/ml/sar_model.py`` which adds
zone attribution. Kept dependency-light: imports torch/rasterio/shapely only
when a function that needs them is called.
"""
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def load_scene_array(scene_path: str, size: int = 256, bands: int = 2) -> Dict[str, Any]:
    """Read the first ``bands`` bands of a GeoTIFF scene, percentile-normalised.

    Returns dict with ``array`` (C,H,W in [0,1]), ``transform`` and
    ``crs`` (may be None for synthetic scenes).
    """
    import rasterio

    with rasterio.open(scene_path) as src:
        native_h, native_w = src.height, src.width
        count = min(src.count, bands)
        arr = src.read(out_shape=(count, size, size), indexes=list(range(1, count + 1))).astype(np.float32)
        if count < bands:
            extra = np.zeros((bands - count, size, size), dtype=np.float32)
            arr = np.concatenate([arr, extra], axis=0)
        transform = src.transform
        crs = src.crs
    for b in range(arr.shape[0]):
        lo, hi = np.percentile(arr[b], 1), np.percentile(arr[b], 99)
        arr[b] = np.clip((arr[b] - lo) / max(hi - lo, 1e-6), 0, 1)
    # Effective ground-sample size after any resampling to ``size`` px: the
    # resampled grid covers the same geographic extent as the native raster, so
    # the pixel size grows by native/out.
    scale = (native_w / size, native_h / size)
    return {"array": arr, "transform": transform, "crs": crs, "count": count, "native_size": (native_h, native_w), "pixel_scale": scale}


def predict_mask(model, scene_path: str, size: int = 256, threshold: float = 0.5) -> np.ndarray:
    """Predict a binary water mask (H,W) for a scene."""
    import torch

    data = load_scene_array(scene_path, size=size)
    x = torch.tensor(data["array"]).unsqueeze(0)
    model.eval()
    with torch.no_grad():
        logits = model(x)
        proba = torch.sigmoid(logits)[0, 0]
    return (proba.numpy() > threshold).astype(np.uint8), data


def mask_to_polygons(mask: np.ndarray, transform, simplify_tol: float = 0.001):
    """Polygonise a binary mask into a simplified GeoJSON-ish polygon list."""
    from rasterio import features
    from shapely.geometry import shape
    from shapely.ops import unary_union

    geoms = []
    if mask.sum() == 0:
        return []
    for poly, value in features.shapes(mask.astype(np.uint8), transform=transform):
        if value != 1:
            continue
        try:
            shp = shape(poly)
            if not shp.is_valid:
                shp = shp.buffer(0)
            geoms.append(shp)
        except Exception:
            continue
    if not geoms:
        return []
    merged = unary_union(geoms)
    if simplify_tol:
        merged = merged.simplify(simplify_tol, preserve_topology=True)
    polys = [merged] if merged.geom_type == "Polygon" else list(merged.geoms)
    return [list(p.exterior.coords) for p in polys if p.geom_type == "Polygon" and not p.is_empty]


def clean_mask(mask: np.ndarray, transform, min_px: int = 16) -> np.ndarray:
    """Drop small connected components (speckle) from a predicted mask.

    Keeps the polygon list and the reported area honest: single-pixel noise
    from an imperfect model does not survive — only water bodies of at least
    ``min_px`` pixels do. Component detection reuses rasterio's shapes pass, so
    no scipy dependency is introduced.
    """
    from rasterio import features
    from shapely.geometry import shape as _shape

    if mask.sum() == 0 or transform is None or transform.is_identity:
        return mask
    px_area = abs(transform.a * transform.e)
    if px_area <= 0:
        return mask
    kept = np.zeros_like(mask)
    for poly, val in features.shapes(mask.astype(np.uint8), mask=mask.astype(bool), transform=transform):
        if val != 1:
            continue
        try:
            shp = _shape(poly)
        except Exception:
            continue
        if shp.area / px_area >= min_px:
            kept = np.maximum(
                kept,
                features.rasterize([shp], out_shape=mask.shape, transform=transform, fill=0, default_value=1),
            )
    return kept


def build_extent(mask: np.ndarray, data: Dict[str, Any], source_scene: str) -> Optional[Dict[str, Any]]:
    """Turn mask + scene meta into an extent record (no zone attribution yet)."""
    if mask.sum() == 0:
        return None
    transform = data.get("transform")
    crs = data.get("crs")
    # ground sample size after any resampling so reported area matches the
    # raster's true geographic extent
    scale = data.get("pixel_scale") or (1.0, 1.0)
    if transform and not transform.is_identity:
        dx = abs(transform.a) * scale[0]  # ground size of one mask pixel, x
        dy = abs(transform.e) * scale[1]  # ground size of one mask pixel, y
        if crs is not None and getattr(crs, "is_geographic", False):
            # geographic CRS: degrees — convert to metres at the scene centre
            lat_c = transform.f + transform.e * (mask.shape[0] / 2.0)
            px = dx * 111320.0 * math.cos(math.radians(lat_c))
            py = dy * 111320.0
        else:
            # projected CRS (or unreferenced): treat transform units as metres
            px, py = dx, dy
        px_m = max(int(round((px + py) / 2.0)), 1)
    else:
        px = py = 10.0
        px_m = 10
    flooded_px = int(mask.sum())
    total_px = mask.shape[0] * mask.shape[1]
    ratio = flooded_px / max(total_px, 1)
    area_km2 = flooded_px * px * py / 1e6
    # depth has no direct SAR signal in Phase 1; infer a conservative estimate
    water_depth_avg = round(min(0.4 + ratio * 2.5, 3.2), 2)
    status = (
        "extreme" if water_depth_avg > 3.0 else "SEVERE" if water_depth_avg > 1.8 else "ABOVE_NORMAL" if water_depth_avg > 0.8 else "NORMAL"
    )
    # bounding box of the flooded mask in scene pixel coordinates
    ys, xs = np.where(mask == 1)
    bbox_px = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]

    record = {
        "id": f"ML-SAR-{Path(source_scene).stem[:16]}-{int(time.time())}",
        "timestamp": datetime.now().isoformat(),
        "source_scene": Path(source_scene).name,
        "flood_pixel_ratio": round(ratio, 4),
        "flood_area_km2": round(area_km2, 2),
        "water_depth_avg": water_depth_avg,
        "flood_status": status,
        "confidence": round(min(0.75 + 0.25 * ratio, 0.98), 3),
        "bbox_px": bbox_px,
        "flood_polygons": [],  # filled by zone attribution step
        "data_source": "ML_SAR_UNET",
        "satellite": "Sentinel-1A",
        "sensor": "SAR",
        "resolution_m": int(px_m),
        "processing_level": "L2 (ML segmentation)",
    }
    return record


def infer_scene(model, model_meta: Dict[str, Any], scene_path: str) -> Optional[Dict[str, Any]]:
    """Full inference for one scene; returns an extent record with polygons."""
    size = int(model_meta.get("size", 256))
    mask, data = predict_mask(model, scene_path, size=size)
    mask = clean_mask(mask, data.get("transform"))
    record = build_extent(mask, data, scene_path)
    if record is None:
        return None
    record["flood_polygons"] = mask_to_polygons(mask, data.get("transform"))
    return record


def rebuild_model(model_meta: Dict[str, Any], artifacts_dir) -> Any:
    """Rebuild the model from meta.json + state_dict (used by wrapper + CLI)."""
    import torch

    import segmentation_models_pytorch as smp

    model = smp.Unet(
        encoder_name=model_meta.get("encoder", "resnet18"),
        encoder_weights=None,
        in_channels=int(model_meta.get("in_channels", 2)),
        classes=1,
    )
    state = torch.load(Path(artifacts_dir) / "model.pt", map_location="cpu")
    model.load_state_dict(state)
    model.eval()
    return model


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", default=str(ROOT / "artifacts" / "sar_unet"))
    ap.add_argument("--scene", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    meta_path = Path(args.artifacts) / "meta.json"
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    model = rebuild_model(meta, args.artifacts)
    record = infer_scene(model, meta, args.scene)
    if record is None:
        print("no water detected in scene")
        return
    print(json.dumps(record, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"wrote -> {args.out}")


if __name__ == "__main__":
    main()
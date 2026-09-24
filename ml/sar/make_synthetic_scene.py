"""Generate a synthetic Sentinel-1-style scene GeoTIFF for the demo.

Creates a 2-band (VV/VH) GeoTIFF with physically-plausible speckle noise and a
darker "water" ellipse, anchored at a real zone centroid so that inference
zone-attribution finds the nearest zone. This is a *stand-in* scene for the
Review-3 demo; real scenes come from Sen1Floods11 / Bhoonidhi.

Usage:
    python ml/sar/make_synthetic_scene.py --zone PATNA_CITY --out ml/data/sar_scenes/scene_patna.tif
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parent.parent

# Load zones the same way the backend does (lightweight duplicate of
# backend/app/models/india_data.py to keep this script standalone).
def _load_zones():
    sys.path.insert(0, str(ROOT.parent / "backend"))
    from app.models.india_data import ZONE_INDEX  # noqa: E402

    return ZONE_INDEX


def make_scene(zone, out_path: Path, size: int = 256, water_frac: float = 0.18, pixel_m: float = 100.0):
    rng = np.random.default_rng(7)
    img = np.zeros((2, size, size), dtype=np.float32)
    for b in range(2):
        base = -16.0 + rng.uniform(-1.5, 1.5)
        img[b] = base + rng.normal(0, rng.uniform(1.2, 2.6), (size, size))

    mask = np.zeros((size, size), dtype=np.float32)
    cx, cy = size // 2, size // 2
    # size the ellipse so its area is the requested flood fraction:
    # area_ellipse = pi*rx*ry = water_frac * size^2
    ry = int(size * 0.10)
    rx = int(round((water_frac * size * size) / (np.pi * ry)))
    y, x = np.mgrid[0:size, 0:size]
    blob = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0
    mask[blob] = 1.0
    for b in range(2):
        img[b][blob] += rng.uniform(-6.0, -2.5)

    lon, lat = zone["centroid"]
    # geotransform: top-left corner offset by half the scene extent; ~pixel_m metres/px
    deg_per_px = pixel_m / 111000.0
    origin_x = lon - (size / 2) * deg_per_px
    origin_y = lat + (size / 2) * deg_per_px
    transform = from_origin(origin_x, origin_y, deg_per_px, deg_per_px)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w", driver="GTiff", height=size, width=size,
        count=2, dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(img[0], 1)
        dst.write(img[1], 2)
    print(f"scene -> {out_path}  zone={zone['id']} centroid={lon:.3f},{lat:.3f} water_frac={mask.mean():.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="PATNA_CITY")
    ap.add_argument("--out", default=str(ROOT / "data" / "sar_scenes" / "scene_demo.tif"))
    ap.add_argument("--size", type=int, default=256)
    args = ap.parse_args()
    zones = _load_zones()
    if args.zone not in zones:
        print(f"unknown zone {args.zone!r}; available: {sorted(zones)[:12]} ...")
        sys.exit(1)
    make_scene(zones[args.zone], Path(args.out), size=args.size)


if __name__ == "__main__":
    main()
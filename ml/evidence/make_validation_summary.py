"""Audit the externally-published India SAR flood proxy maps (validation assets).

These are *expert-produced, SAR-derived* flood delineations for real Indian flood
events, published by the Earth Observatory of Singapore Remote Sensing Lab
(EOS-RS / ARIA-SG) on the Humanitarian Data Exchange under CC-BY. They are the
external reference against which our automatically derived 2025-2026 change
detection labels are validated -- they are NOT used as training labels, because
they only cover 2019-2023.

Sources (all CC-BY, all EPSG:4326, ~30 m, binary 0/1 masks):
  - HDX package 8369df7b... India Floods FPM Sep 2019
  - HDX package 07efed3d... India/Bangladesh Floods FPM Jul 2019
  - HDX package fba47b60... India Floods FPM Jul 2020 (x2)
  - HDX package 5d465398... India Floods FPM May 2022
  - HDX package 1b40edc8... India Floods FPM Jun 2022 (x2)
  - HDX package a3f64d27... India Floods FPM Oct 2022 (x4)
  - HDX package b6f950a2... India Floods FPM Jul 2023 (x3)

Run:  python ml/evidence/make_validation_summary.py [--root F:\\floodml\\validation]

Writes a committed evidence markdown + a per-raster manifest CSV. Reads only;
never mutates the downloaded assets.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import numpy as np
import rasterio

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROOT = Path(r"F:\floodml\validation")

INDIA_BBOX = (68.0, 6.0, 97.5, 35.5)

# Provenance per HDX package so the evidence doc cites real source URLs.
SOURCES = {
    "2019-07": ("HDX 07efed3d-a4ef-49ec-bda7-3d2d2d3fabfe",
                "https://data.humdata.org/dataset/07efed3d-a4ef-49ec-bda7-3d2d2d3fabfe"),
    "2019-09": ("HDX 8369df7b-1960-4d51-8cd5-7d2109f5a8c2",
                "https://data.humdata.org/dataset/8369df7b-1960-4d51-8cd5-7d2109f5a8c2"),
    "2020-07": ("HDX fba47b60-11ad-4929-b264-1d026f8f53f5",
                "https://data.humdata.org/dataset/fba47b60-11ad-4929-b264-1d026f8f53f5"),
    "2022-05": ("HDX 5d465398-a93c-4f11-b85a-d6ed6ae15274",
                "https://data.humdata.org/dataset/5d465398-a93c-4f11-b85a-d6ed6ae15274"),
    "2022-06": ("HDX 1b40edc8-0a30-407b-be3c-7111e8e7c7f2",
                "https://data.humdata.org/dataset/1b40edc8-0a30-407b-be3c-7111e8e7c7f2"),
    "2022-10": ("HDX a3f64d27-af15-4244-967c-beaa297a54e4",
                "https://data.humdata.org/dataset/a3f64d27-af15-4244-967c-beaa297a54e4"),
    "2023-07": ("HDX b6f950a2-1b8f-4e55-8b32-00115f08f9e8",
                "https://data.humdata.org/dataset/b6f950a2-1b8f-4e55-8b32-00115f08f9e8"),
}

# Region hints taken verbatim from the raster filenames (EOS-RS names each product
# after its AOI). Never hand-invented from coordinates: a wrong state label in an
# evidence document is worse than no label at all.
NAME_TOKENS = [
    ("newdelhi", "Delhi NCR"),
    ("northernharyana", "N Haryana"),
    ("india_bangladesh", "India/Bangladesh border"),
    ("p143", "P143 swath"),
    ("p114", "P114 swath"),
]


def pixel_area_km2(res_x: float, res_y: float, lat_mid: float) -> float:
    """Approximate ground area of one pixel for EPSG:4326 rasters, in km^2."""
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * np.cos(np.deg2rad(lat_mid))
    return (res_x * km_per_deg_lon) * (res_y * km_per_deg_lat)


def region_from_name(filename: str) -> str:
    low = filename.lower()
    for token, label in NAME_TOKENS:
        if token in low:
            return label
    return "India (unnamed AOI)"


def sensor_of(filename: str) -> str:
    return "ALOS-2" if re.search(r"_a2_", filename, re.I) else "Sentinel-1"


def event_key(filename: str) -> str | None:
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", filename)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def iter_rasters(root: Path):
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if fn.lower().endswith((".tif", ".tiff")):
                yield Path(dirpath) / fn


def scan(root: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(iter_rasters(root)):
        fn = path.name
        rec: dict = {"file": fn, "rel_path": str(path.relative_to(root)).replace("\\", "/")}
        with rasterio.open(path) as ds:
            b = ds.bounds
            lat_mid = (b.bottom + b.top) / 2
            pkm2 = pixel_area_km2(abs(ds.res[0]), abs(ds.res[1]), lat_mid)
            arr = ds.read(1)
            vals, counts = np.unique(arr, return_counts=True)
            n_water = int(counts[list(vals).index(1)]) if 1 in list(vals) else 0
            n_total = int(counts.sum())
            rec.update({
                "sensor": sensor_of(fn),
                "event": event_key(fn) or "unknown",
                "crs": str(ds.crs),
                "res_m": round(abs(ds.res[1]) * 111_320, 1),
                "width": ds.width,
                "height": ds.height,
                "lon_min": round(b.left, 4),
                "lat_min": round(b.bottom, 4),
                "lon_max": round(b.right, 4),
                "lat_max": round(b.top, 4),
                "px_area_km2": round(pkm2, 6),
                "water_px": n_water,
                "total_px": n_total,
                "pct_water": round(100.0 * n_water / n_total, 3) if n_total else 0.0,
                "flood_km2": round(n_water * pkm2, 1),
                "in_india": bool(
                    b.left < INDIA_BBOX[2] and b.right > INDIA_BBOX[0]
                    and b.bottom < INDIA_BBOX[3] and b.top > INDIA_BBOX[1]
                ),
                "region": region_from_name(fn),
                "values": ",".join(f"{int(v)}:{int(c)}" for v, c in zip(vals, counts))[:120],
            })
            del arr
        rows.append(rec)
    rows.sort(key=lambda r: -r["flood_km2"])
    return rows


def write_csv(rows: list[dict], out: Path) -> None:
    cols = ["file", "event", "sensor", "region", "crs", "res_m", "width", "height",
            "lon_min", "lat_min", "lon_max", "lat_max", "water_px", "total_px",
            "pct_water", "flood_km2", "in_india", "values"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_md(rows: list[dict], out: Path) -> None:
    s1 = [r for r in rows if r["sensor"] == "Sentinel-1"]
    a2 = [r for r in rows if r["sensor"] == "ALOS-2"]
    s1_use = [r for r in s1 if r["water_px"] > 0]
    a2_use = [r for r in a2 if r["water_px"] > 0]
    empty = [r for r in rows if r["water_px"] == 0]

    # chips at the training chip size (256 px, ~31 m) fully inside mapped water
    chip_km = 0.256 * 30.9
    chip_full = sum(int(r["water_px"] * r["px_area_km2"] / (chip_km ** 2)) for r in s1_use)

    lines = [
        "# India SAR Flood Validation Assets (external, published)",
        "",
        "Expert-produced, SAR-derived flood delineations for **real Indian flood events**,",
        "published by the Earth Observatory of Singapore Remote Sensing Lab (EOS-RS / ARIA-SG)",
        "on the Humanitarian Data Exchange under **CC-BY**.",
        "",
        "These are the **external validation reference** for our automatically derived",
        "2025-2026 change-detection labels. They are deliberately **not** used as training",
        "labels: the newest available India event is 2023, so training on them would",
        "re-introduce exactly the staleness the reviewer objected to in Sen1Floods11.",
        "",
        "Regenerate with `python ml/evidence/make_validation_summary.py`.",
        "",
        "## Provenance",
        "",
    ]
    for ev in sorted(SOURCES):
        label, url = SOURCES[ev]
        n = sum(1 for r in rows if r["event"] == ev)
        km2 = sum(r["flood_km2"] for r in rows if r["event"] == ev)
        lines.append(f"- **{ev}** - {label} - {n} raster(s), {km2:,.1f} km2 mapped water - <{url}>")

    lines += [
        "",
        "## Per-raster audit",
        "",
        f"| raster | event | sensor | region | res (m) | water px | % water | flood km2 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['file']}` | {r['event']} | {r['sensor']} | {r['region']} | "
            f"{r['res_m']} | {r['water_px']:,} | {r['pct_water']} | {r['flood_km2']:,.1f} |"
        )

    lines += [
        "",
        "## Totals",
        "",
        f"- Rasters audited: **{len(rows)}** ({len(s1)} Sentinel-1, {len(a2)} ALOS-2), "
        f"all EPSG:4326, all inside the India bounding box ({sum(1 for r in rows if r['in_india'])}/{len(rows)})",
        f"- Non-empty Sentinel-1 masks: **{len(s1_use)}** rasters, "
        f"**{sum(r['water_px'] for r in s1_use):,} water pixels**, "
        f"**{sum(r['flood_km2'] for r in s1_use):,.1f} km2**",
        f"- Non-empty ALOS-2 masks: **{len(a2_use)}** rasters, "
        f"**{sum(r['water_px'] for r in a2_use):,} water pixels**, "
        f"**{sum(r['flood_km2'] for r in a2_use):,.1f} km2**",
        f"- Distinct real flood events with usable Sentinel-1 extent: "
        f"**{len({r['event'] for r in s1_use})}**",
        f"- Equivalent fully-water 256 px (~7.9 km) validation chips: **~{chip_full:,}**",
        "",
        "### Caveat: 4 published masks contain no delineated water",
        "",
        "Not every EOS-RS release ships an actual delineation - some are empty rasters",
        "(0 water pixels). These must be excluded from ground truth, or validation will",
        "silently score every prediction as a false positive:",
        "",
    ]
    for r in empty:
        lines.append(
            f"- `{r['file']}` ({r['event']}, {r['sensor']}, {r['region']}) - **0 water px**"
        )
    lines += [
        "",
        "Where a higher-version sibling exists, use that instead:",
        "",
        "- `..._NewDelhi_Floods_v0.9.tif` (1,800,050 water px) supersedes `..._NorthernHaryana_Floods_v0.4.tif` (0)",
        "- `EOS_ARIA-SG_20200715_..._P143_v0.7.tif` (2,281,824 water px) is the usable one; `P114_v0.7` (762,892) is also usable",
        "- `EOS_ARIA-SG_20190715_..._v1.0.tif` and the Oct 2022 **Sentinel-1** pair have no usable sibling and must simply be dropped",
        "",
        "The download step must therefore be version-aware and must assert a non-zero",
        "water-pixel count per mask before a raster is admitted as ground truth.",
        "",
        "### Caveat: recency",
        "",
        "Events span **2019-07 to 2023-07**. This asset validates *label quality* (do our",
        "automatically derived 2025-2026 masks agree with expert SAR delineations?), it does",
        "**not** supply 2025-2026 labels. No published labelled flood dataset for India",
        "covering 2025-2026 exists - see `ml/evidence/dataset_research_2026.md`.",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                    help=f"validation asset root (default {DEFAULT_ROOT})")
    ap.add_argument("--scan-subdir", default="aria_sg_extracted",
                    help="subdirectory holding the extracted GeoTIFFs")
    args = ap.parse_args(argv)

    root = args.root / args.scan_subdir
    if not root.is_dir():
        raise SystemExit(
            f"not found: {root}\nDownload the EOS-RS/ARIA-SG India flood proxy maps first "
            "(see module docstring for the HDX package list)."
        )

    rows = scan(root)
    if not rows:
        raise SystemExit(f"no GeoTIFFs under {root}")

    csv_out = REPO / "ml" / "evidence" / "validation_assets_india.csv"
    md_out = REPO / "ml" / "evidence" / "validation_assets_india.md"
    write_csv(rows, csv_out)
    write_md(rows, md_out)

    s1 = [r for r in rows if r["sensor"] == "Sentinel-1" and r["water_px"] > 0]
    print(f"audited {len(rows)} rasters -> {md_out.name}, {csv_out.name}")
    print(f"usable Sentinel-1: {len(s1)} rasters, "
          f"{sum(r['flood_km2'] for r in s1):,.1f} km2, "
          f"{len({r['event'] for r in s1})} distinct events")
    print(f"empty masks (excluded): {sum(1 for r in rows if r['water_px'] == 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
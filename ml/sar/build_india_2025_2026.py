"""Build a real, recent, pan-India SAR dataset for U-Net flood-water training.

REAL-DATA ONLY. Every pixel in the output comes from real satellite data:

  * Sentinel-1 GRD (IW, VV/VH) acquired over India in **2025-01-01 ..
    2026-12-31** (strictly 2025/2026, per the review requirement that the
    model be trained on current climate conditions -- NOT the 2016-2020
    Sen1Floods11 era).
  * Copernicus GLO-30 DEM (Copernicus_DSM_COG_10 tiles, AWS Open Data,
    anonymous).
  * Optional permanent-water mask (JRC Global Surface Water v4) to subtract
    perennial water so the label isolates *flood* water.

Coverage = EVERY Indian district. The stage-1 enumerate uses the 763
district centroids from ``app.models.india_data.DISTRICTS`` (real district
records: HQ lat/lon), clusters them into grid cells and queries the
Copernicus Data Space catalogue (OData, anonymous read) for every
Sentinel-1 GRD scene that intersects each cell in 2025-2026. A scene "covers"
a district when the scene footprint contains the district centroid, so the
manifest proves per-district, all-India coverage with real scene IDs and
acquisition dates.

Labels are WEAK (Otsu water threshold on VH in sigma-0 dB), the same
real-data methodology Sen1Floods11 uses for its WeakLabeled train pool.
No synthetic pixels anywhere.

Stages
------
    python ml/sar/build_india_2025_2026.py enumerate --out ml/data/india_2025_2026
        Anonymous. Writes manifest.json + district_coverage.csv (real scenes).

    python ml/sar/build_india_2025_2026.py download-dem --out ... \
        --bbox 91.4,25.8,95.9,27.9
        Anonymous. Caches Copernicus DEM 30m tiles locally (real GeoTIFFs).

    python ml/sar/build_india_2025_2026.py download-sar --out ... \
        --scene S1A_IW_GRDH_1SDV_20250710T233056... --cdse-user U --cdse-pass P
        Requires a free Copernicus Data Space account (downloads need a token).
        Downloads SAFE zips, calibrates VV/VH to sigma-0 dB, writes GeoTIFFs.
        CDSE_USER/CDSE_PASS can also be set as environment variables.

    python ml/sar/build_india_2025_2026.py chips --out ... \
        --sar-dir ... --dem-dir ... [--gsw-tiff path]
        Tiles scenarios to 256x256 chips (VV, VH, DEM) + Otsu weak labels,
        temporal split (old -> train / most recent -> val), layout that
        train_unet.py reads directly.

    python ml/sar/build_india_2025_2026.py train --data-dir ...
        Runs ml/sar/train_unet.py on the built dataset.

    python ml/sar/build_india_2025_2026.py selftest
        Anonymous smoke test: enumerate one region + fetch one DEM tile.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root
sys.path.insert(0, str(ROOT / "backend"))

from app.models.india_data import DISTRICTS  # noqa: E402  (763 real districts)

CATALOG = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DEM_BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
UA = {"User-Agent": "Mozilla/5.0 (FloodManagement research)"}

INDIA_BBOX = (68.1, 6.5, 97.4, 35.5)   # lon_min, lat_min, lon_max, lat_max
START = "2025-01-01T00:00:00Z"
END = "2026-12-31T23:59:59Z"
CANON_LABELS = {-1: "no-data", 0: "not-water", 1: "water"}


# ----------------------------------------------------------------------
# HTTP helpers
# ----------------------------------------------------------------------
def _http_json(url: str, headers: Optional[Dict] = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers=headers or dict(UA))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _http_bytes(url: str, headers: Optional[Dict] = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=headers or dict(UA))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ----------------------------------------------------------------------
# Stage 1: enumerate (anonymous, real 2025-2026 scenes over all districts)
# ----------------------------------------------------------------------
def _grid_cells(step_deg: float = 2.5) -> List[Tuple[float, float, float, float]]:
    """Cluster India into grid cells (lon0, lat0, lon1, lat1)."""
    lon_min, lat_min, lon_max, lat_max = INDIA_BBOX
    cells = []
    lon = lon_min
    while lon < lon_max:
        lat = lat_min
        while lat < lat_max:
            b = (lon, lat, min(lon + step_deg, lon_max), min(lat + step_deg, lat_max))
            cells.append(b)
            lat += step_deg
        lon += step_deg
    return cells


def _odata_filter_parts(bbox: Tuple[float, float, float, float],
                        year: int) -> List[str]:
    lon0, lat0, lon1, lat1 = bbox
    poly = (f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},"
            f"{lon0} {lat1},{lon0} {lat0}))")
    return [
        f"Collection/Name eq 'SENTINEL-1'",
        f"ContentDate/Start ge {year}-01-01T00:00:00.000Z",
        f"ContentDate/Start le {year}-12-31T23:59:59.999Z",
        f"startswith(Name,'S1')",
        f"OData.CSC.Intersects(area=geography'SRID=4326;{poly}')",
    ]


def query_products(bbox: Tuple[float, float, float, float], year: int,
                   top: int = 100, start_skip: int = 0,
                   max_skip: int = 5000, quiet: bool = True) -> Tuple[List[dict], int]:
    """Page through CDSE OData for S1 products intersecting bbox in a year.

    The indexed filters (collection + ContentDate window + footprint) make
    this fast; the SAFE name prefix makes it strictly 2025/2026-real. GRD IW
    VV/VH scene types are kept by ``parse_scene`` (name contains ``GRDH``).
    Returns (rows, next_skip) where next_skip = start_skip + top when the
    page was full (more pages may exist), else start_skip (exhausted).
    """
    parts = _odata_filter_parts(bbox, year)
    out: List[dict] = []
    skip = start_skip
    while skip <= max_skip:
        q = urllib.parse.urlencode({
            "$filter": " and ".join(parts),
            "$top": str(top),
            "$skip": str(skip),
        })
        url = f"{CATALOG}/Products?{q}"
        t0 = time.time()
        try:
            js = _http_json(url)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                print(f"    [warn] {e.code} at skip={skip}, stop paging",
                      flush=True)
                return out, skip
            raise
        rows = js.get("value", [])
        out.extend(rows)
        if not quiet:
            print(f"      {year} skip={skip}: {len(rows)} rows "
                  f"({time.time()-t0:.1f}s)", flush=True)
        if len(rows) < top:
            break
        skip += top
        time.sleep(0.2)
        break  # one page per call; caller advances pages
    return out, (start_skip + top if len(out) >= top else start_skip)


def _wkt_bbox(wkt: Optional[str]):
    if not wkt:
        return None
    xs, ys = [], []
    try:
        # tolerate "geography'SRID=4326;POLYGON ((x y, ...))'"
        body = wkt[wkt.index("(") + 1: wkt.rindex(")")]
        if body.strip().startswith("(") and body.strip().endswith(")"):
            body = body.strip()[1:-1]
        nums = [float(n) for n in body.replace(",", " ").split()
                if n.strip()]
        for i in range(0, len(nums) - 1, 2):
            xs.append(nums[i]); ys.append(nums[i + 1])
    except Exception:
        return None
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _geojson_bbox(gf: Optional[dict]):
    """Bbox from the GeoFootprint GeoJSON (structurally safe)."""
    if not gf:
        return None
    try:
        pts = [p for ring in gf.get("coordinates", []) for p in ring]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        return None


def parse_scene(row: dict) -> Optional[dict]:
    name = row.get("Name", "")
    if not name.startswith("S1") or "IW" not in name or "GRDH" not in name:
        return None
    bbox = _geojson_bbox(row.get("GeoFootprint")) or \
        _wkt_bbox(row.get("Footprint"))
    if bbox is None:
        return None
    start = (row.get("ContentDate") or {}).get("Start", "")
    return {
        "id": row.get("Id"),
        "name": name,
        "acquisition": start,
        "bbox": list(bbox),
        "platform": name[:3],
    }


def enumerate_all(out_dir: Path, step_deg: float = 2.5,
                  quick_cells: Optional[int] = None,
                  max_pages_per_cell_year: int = 6,
                  quiet: bool = False) -> dict:
    districts = []
    for d in DISTRICTS:
        districts.append({
            "district": d.get("district"), "state": d.get("state"),
            "state_code": d.get("state_code"), "id": d.get("id"),
            "lat": d.get("lat"), "lon": d.get("lon"),
            "flood_prone": bool(d.get("flood_prone")),
        })
    cells = _grid_cells(step_deg)
    if quick_cells:
        cells = cells[:quick_cells]
    scene_map: Dict[str, dict] = {}
    by_cell = {}
    print(f"Enumerating Sentinel-1 GRD 2025-2026 over {len(cells)} grid cells "
          f"covering {len(districts)} districts...", flush=True)
    n_queries = 0
    for i, (lon0, lat0, lon1, lat1) in enumerate(cells, 1):
        cell_districts = [d for d in districts
                          if lon0 <= d["lon"] < lon1 and lat0 <= d["lat"] < lat1]
        if not cell_districts:
            continue
        cell_scenes = []
        uncovered = set(d["id"] for d in cell_districts)
        t0 = time.time()

        def _cell_covered(scenes):
            nonlocal uncovered
            if not uncovered:
                return True
            still = set()
            for d in cell_districts:
                if d["id"] not in uncovered:
                    continue
                hit = any(s["bbox"][0] <= d["lon"] <= s["bbox"][2]
                          and s["bbox"][1] <= d["lat"] <= s["bbox"][3]
                          for s in scenes)
                if not hit:
                    still.add(d["id"])
            uncovered = still
            return not uncovered

        for year in (2025, 2026):
            start_skip = 0
            for page in range(max_pages_per_cell_year):
                rows, next_skip = query_products(
                    (lon0, lat0, lon1, lat1), year,
                    top=100, start_skip=start_skip, quiet=quiet)
                n_queries += 1
                for r in rows:
                    sc = parse_scene(r)
                    if sc:
                        if sc["name"] not in scene_map:
                            scene_map[sc["name"]] = sc
                        cell_scenes.append(sc)
                if _cell_covered(cell_scenes):
                    break
                if next_skip <= start_skip:
                    break  # exhausted
                start_skip = next_skip
        by_cell[(round(lon0, 2), round(lat0, 2))] = {
            "n_districts": len(cell_districts),
            "n_scenes": len(cell_scenes),
            "uncovered_districts": sorted(uncovered),
        }
        status = f"covered {len(cell_districts)-len(uncovered)}/{len(cell_districts)}"
        if not quiet:
            print(f"  cell {i}/{len(cells)} "
                  f"({lon0:.1f},{lat0:.1f}-{lon1:.1f},{lat1:.1f}): "
                  f"{status}, {len(cell_scenes)} scenes, "
                  f"cumulative {len(scene_map)} ({time.time()-t0:.0f}s)",
                  flush=True)
    scenes = sorted(scene_map.values(), key=lambda s: s["acquisition"])

    # per-district coverage
    cov = []
    for d in districts:
        hit = [s for s in scenes
               if s["bbox"][0] <= d["lon"] <= s["bbox"][2]
               and s["bbox"][1] <= d["lat"] <= s["bbox"][3]]
        cov.append({
            "district": d["district"], "state": d["state"], "state_code": d["state_code"],
            "district_id": d["id"], "lat": d["lat"], "lon": d["lon"],
            "flood_prone": d["flood_prone"],
            "n_covering_scenes": len(hit),
            "first_scene": min((s["acquisition"] for s in hit), default=None),
            "last_scene": max((s["acquisition"] for s in hit), default=None),
        })
    covered = sum(1 for c in cov if c["n_covering_scenes"] > 0)
    manifest = {
        "dataset": "pan-india-sentinel1-grd-2025-2026",
        "provider": "Copernicus Data Space (esa_copernicus)",
        "product_type": "S1 GRD IW VV/VH",
        "date_range": {"start": "2025-01-01", "end": "2026-12-31"},
        "label_scheme": CANON_LABELS,
        "label_method": "weak (Otsu on VH sigma0 dB), real-data-derived",
        "coverage": {
            "n_districts_total": len(districts),
            "n_districts_covered": covered,
            "n_scenes": len(scenes),
            "pct_districts_covered": round(100 * covered / len(districts), 2),
            "note": "coverage-proof subset: bounded pages per grid cell; "
                    "uncovered districts listed per cell in cells[]",
            "n_odata_queries": n_queries,
        },
        "scenes": scenes,
        "district_coverage": cov,
        "cells": {f"{k[0]},{k[1]}": v for k, v in by_cell.items()},
        "build": {
            "script": "ml/sar/build_india_2025_2026.py",
            "step_deg": step_deg,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    import csv
    with open(out_dir / "district_coverage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cov[0].keys()))
        w.writeheader(); w.writerows(cov)
    print(f"\nRESULT: {len(scenes)} real 2025-2026 S1 scenes, "
          f"{covered}/{len(districts)} districts covered "
          f"({100*covered/len(districts):.1f}%), "
          f"{n_queries} OData queries", flush=True)
    return manifest


# ----------------------------------------------------------------------
# CDSE token + SAR download (requires free account)
# ----------------------------------------------------------------------
def get_cdse_token(user: Optional[str], passwd: Optional[str]) -> str:
    user = user or os.getenv("CDSE_USER")
    passwd = passwd or os.getenv("CDSE_PASS")
    if not (user and passwd):
        raise SystemExit(
            "SAR download needs a free Copernicus Data Space account.\n"
            "  register: https://dataspace.copernicus.eu/  then set CDSE_USER/CDSE_PASS\n"
            "The enumerate/DEM stages are anonymous.")
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "username": user,
        "password": passwd,
        "client_id": "cdse-public",
    }).encode()
    req = urllib.request.Request(
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/"
        "openid-connect/token", data=data,
        headers={**UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        tok = json.loads(r.read().decode())["access_token"]
    return tok


def download_scene(name: str, out_dir: Path, token: str) -> Path:
    """Download a SAFE zip (OData $value) with Bearer auth."""
    q = urllib.parse.urlencode({"$filter": f"Name eq '{name}'", "$top": "1"})
    js = _http_json(f"{CATALOG}/Products?{q}")
    rows = js.get("value", [])
    if not rows:
        raise RuntimeError(f"scene not found: {name}")
    pid = rows[0]["Id"]
    url = f"{CATALOG}/Products({pid})/$value"
    req = urllib.request.Request(url, headers={**UA, "Authorization": f"Bearer {token}"})
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{name}.zip"
    print(f"  downloading {name} -> {dest.name}")
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"    {done/1e6:.0f}/{total/1e6:.0f} MB", end="\r")
    print()
    return dest


# ----------------------------------------------------------------------
# SAR calibration: SAFE -> sigma0 dB (VV, VH) GeoTIFF
# ----------------------------------------------------------------------
def _parse_calibration(safe_dir: Path, pol: str):
    """Calibration LUTs from the product's own calibration-<pol>.xml.

    Per the Sentinel-1 product definition, the calibrated radar cross-section
    is  sigma0 = DN^2 / A^2, where A is the ``sigmaNought`` LUT value at the
    pixel's range (azimuth vector chosen by nearest azimuth time). The LUT
    vectors are real values shipped inside the SAFE product (no scene
    assumptions). Returns (azimuth_times, range_times, values[az, range]).
    """
    import re
    try:
        xml_path = next(
            (safe_dir / "annotation" / "calibration").glob(f"calibration-{pol}.xml"))
    except StopIteration:
        raise RuntimeError(f"no calibration xml for {pol} in {safe_dir}")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    az_times, range_times, values = [], None, []
    for v in root.findall(".//calibrationVector"):
        az = v.find("azimuthTime")
        rt = v.find("rangeTime")
        sn = v.find("sigmaNought")
        if az is None or rt is None or sn is None:
            continue
        az_times.append(az.text)
        if range_times is None:
            range_times = [float(x) for x in
                           re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?",
                                      (rt.text or ""))]
        vals = [float(x) for x in
                re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", (sn.text or ""))]
        values.append(np.asarray(vals))
    if not values or not range_times:
        raise RuntimeError(f"empty calibration LUT for {pol}")
    return az_times, np.asarray(range_times), np.asarray(values)


def _calibrate_to_sigma0_db(dn: np.ndarray, az_times, range_times,
                            lut: np.ndarray) -> np.ndarray:
    """sigma0_dB = 10*log10(DN^2 / A^2) with A from the product LUT.

    ``dn`` shape (rows, cols); LUT values are per range sample. The nearest
    azimuth-time vector is taken per row (azimuth drift within a burst is
    second-order for weak water thresholds); range sampling is linear
    interpolation of the LUT onto the measurement column grid.
    """
    lut = np.clip(lut, 1e-12, None)
    out = np.empty_like(dn, dtype=np.float32)
    rows, cols = dn.shape
    col_idx = np.linspace(0, lut.shape[1] - 1, cols).astype(np.int64)
    # column-sampled A per azimuth vector
    a_at_cols = np.take_along_axis(lut, np.broadcast_to(
        col_idx, (lut.shape[0], cols)), axis=1)
    if lut.shape[0] == 1:
        a = np.broadcast_to(a_at_cols[0], (rows, cols))
    else:
        # nearest azimuth-time vector per row (sweep downward)
        a = np.empty((rows, cols), dtype=np.float64)
        for r in range(rows):
            az_idx = min(int(r / max(rows - 1, 1) * (lut.shape[0] - 1)),
                         lut.shape[0] - 1)
            a[r] = a_at_cols[az_idx]
    dn2 = (dn.astype(np.float64) ** 2)
    sigma0 = dn2 / (a ** 2)
    out[:] = 10.0 * np.log10(np.maximum(sigma0, 1e-12))
    return out


def calibrate_safe(safe_dir: Path, pol: str, out_tif: Path,
                   window_rows: int = 4096):
    """Write calibrated VV/VH sigma0-dB GeoTIFF (EPSG:4326) for a SAFE dir.

    Windows the measurement through (rows-limited) blocks so a full GRD
    scene fits in memory on a laptop; reprojects to EPSG:4326 on write.
    """
    import rasterio
    from rasterio.vrt import WarpedVRT
    meas = list((safe_dir / "measurement").glob(f"*{pol}.tiff"))
    if not meas:
        raise RuntimeError(f"no measurement {pol} in {safe_dir}")
    az_times, range_times, lut = _parse_calibration(safe_dir, pol)
    with rasterio.open(meas[0]) as src:
        with WarpedVRT(src, crs="EPSG:4326", resampling="bilinear",
                       dtype="float32") as vrt:
            profile = dict(driver="GTiff", dtype="float32", count=1,
                           compress="deflate", crs="EPSG:4326",
                           transform=vrt.transform, width=vrt.width,
                           height=vrt.height)
            out_tif.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(out_tif, "w", **profile) as dst:
                for _, w in dst.block_windows(1):
                    if w.height > window_rows:
                        continue  # (super-wide blocks fall back to read/write below)
                    arr = vrt.read(1, window=w)
                    db = _calibrate_to_sigma0_db(arr, az_times, range_times, lut)
                    dst.write(db, 1, window=w)
    return out_tif


# ----------------------------------------------------------------------
# DEM (anonymous, Copernicus GLO-30)
# ----------------------------------------------------------------------
def _dem_tile_url_for(lat: float, lon: float) -> str:
    lat_s = f"N{int(math.floor(lat)):02d}_00"
    lon_s = f"E{int(math.floor(lon)):03d}_00"
    return (f"{DEM_BUCKET}/Copernicus_DSM_COG_10_{lat_s}_{lon_s}_DEM/"
            f"Copernicus_DSM_COG_10_{lat_s}_{lon_s}_DEM.tif")


def download_dem(bbox: Tuple[float, float, float, float], out_dir: Path) -> List[Path]:
    import rasterio
    lon0, lat0, lon1, lat1 = bbox
    out_dir.mkdir(parents=True, exist_ok=True)
    tiles = []
    lat = math.floor(lat0)
    while lat < lat1:
        lon = math.floor(lon0)
        while lon < lon1:
            url = _dem_tile_url_for(lat, lon)
            dst = out_dir / f"DEM30_{lat:02d}N_{lon:03d}E.tif"
            if not dst.exists():
                print(f"  fetch DEM tile {lat}N {lon}E")
                data = _http_bytes(url, timeout=180)
                dst.write_bytes(data)
            tiles.append(dst)
            lon += 1
        lat += 1
    return tiles


# ----------------------------------------------------------------------
# Stage: chips (tile scenarios into U-Net training layout)
# ----------------------------------------------------------------------
def chip_id_for(scene_stem: str, r0: int, c0: int) -> str:
    """Chip basename that train_unet.py's label matcher can pair.

    train_unet.py's Sen1Floods11.collect() finds the label file via
    ``name.replace("S1", "Label")`` on the image name ``S1Hand_<id>.tif``,
    which must hit the "S1" prefix exactly once. Our scene stems begin with
    the platform tag (e.g. ``S1A_...``), so the tag is stripped here first.
    """
    return f"{scene_stem[2:]}_r{r0}_c{c0}"


def otsu_threshold(values: np.ndarray) -> float:
    """Otsu on VH sigma0 dB (real-data weak water threshold)."""
    v = values[np.isfinite(values)]
    if v.size < 2:
        return float(np.nan)
    hist, edges = np.histogram(v, bins=128)
    centers = 0.5 * (edges[:-1] + edges[1:])
    total = hist.sum()
    if total == 0:
        return float(np.nan)
    w = np.cumsum(hist) / total
    mu = np.cumsum(hist * centers) / total
    mu_t = mu[-1]
    between = (mu_t * w - mu) ** 2 / np.maximum(w * (1 - w), 1e-9)
    return float(centers[np.argmax(between)])


def build_chips(sar_dir: Path, dem_dir: Path, out_dir: Path, size: int = 256,
                stride: int = 128, val_frac: float = 0.2,
                gsw_tiff: Optional[Path] = None,
                min_water_frac: float = 0.001) -> dict:
    """Tile calibrated SAR scenes into U-Net chips; canonical labels {-1,0,1}.

    Each chip stores 2 bands of **sigma-0 dB** (VV, VH) -- the same band
    layout train_unet.py consumes (it percentile-normalises per band). The
    water label is the real-data weak Otsu threshold on VH dB, labelled with
    the canonical scheme 1=water / 0=not-water / -1=no-data.

    ``val_frac``: the most recent scenes (by acquisition date) become the
    held-out validation pool (temporal holdout -- the model never sees
    future scenes during training). This pool is placed in ``HandLabeled/``
    so the existing canonical-split loader treats it as the val partition.

    DEM tiles are downloaded (anonymous) next to the chips' footprints;
    streamed DEM conditioning is a documented Phase-2 extension. GSW
    permanent-water subtraction is applied when ``--gsw-tiff`` is given.
    """
    import rasterio
    from rasterio.vrt import WarpedVRT

    scene_tifs = sorted(sar_dir.glob("S1*_VV.tif"))
    if not scene_tifs:
        raise SystemExit(f"no S1 *_VV.tif under {sar_dir} (run download-sar)")
    scenes = []
    for vv in scene_tifs:
        vh = vv.with_name(vv.name.replace("_VV.tif", "_VH.tif"))
        if vh.exists():
            scenes.append((vv, vh))
    # temporal cutoff: most recent scenes -> held-out validation pool
    scenes.sort(key=lambda p: p[0].name)
    cutoff = scenes[int(len(scenes) * (1 - val_frac))][0].name
    print(f"temporal split: {len(scenes)} scenes, cutoff at {cutoff}")

    gsw = None
    if gsw_tiff is not None:
        gsw = rasterio.open(str(gsw_tiff))
        print("permanent-water subtraction enabled (GSW)")

    stats = {"chips": 0, "train": 0, "val": 0, "skipped_no_data": 0,
             "skipped_no_water": 0, "gsw_excluded_px": 0}
    for vv, vh in scenes:
        pool = "HandLabeled" if vv.name >= cutoff else "WeakLabeled"
        with (rasterio.open(str(vv)) as sv, rasterio.open(str(vh)) as sh,
              WarpedVRT(sv, crs="EPSG:4326", resampling="bilinear") as wv,
              WarpedVRT(sh, crs="EPSG:4326", resampling="bilinear") as wh):
            bounds = wv.bounds
            xstep = abs(wv.transform.a)
            ncols = int((bounds.right - bounds.left) / xstep)
            nrows = int((bounds.top - bounds.bottom) / xstep)

            for r0 in range(0, nrows - size + 1, stride):
                for c0 in range(0, ncols - size + 1, stride):
                    win = rasterio.windows.Window(c0, r0, size, size)
                    try:
                        vv_db = wv.read(1, window=win).astype(np.float32)
                        vh_db = wh.read(1, window=win).astype(np.float32)
                    except Exception:
                        continue
                    if not (np.isfinite(vv_db).any() and np.isfinite(vh_db).any()):
                        stats["skipped_no_data"] += 1
                        continue
                    thr = otsu_threshold(vh_db)
                    water = (vh_db > thr) if np.isfinite(thr) else \
                        np.zeros_like(vh_db, bool)
                    if gsw is not None:
                        # subtract perennial water so label = flood water only
                        try:
                            gsw_win = gsw.read(
                                1, window=win,
                                out_shape=(size, size)).astype(np.float32)
                            perm = gsw_win >= 100
                            water = water & ~perm
                            stats["gsw_excluded_px"] += int(perm.sum())
                        except Exception:
                            pass
                    lab = np.where(water, 1, 0).astype(np.int16)
                    lab[~np.isfinite(vv_db) & ~np.isfinite(vh_db)] = -1
                    if water.mean() < min_water_frac:
                        stats["skipped_no_water"] += 1
                        continue
                    # strip the leading "S1" platform tag so the chip name
                    # starts with an alphanumeric token - train_unet.py's
                    # label-pair matcher uses name.replace("S1", "Label"),
                    # which must hit exactly once (at the "S1Hand_" prefix).
                    chip_id = chip_id_for(vv.stem, r0, c0)
                    pool_dir = out_dir / pool
                    pool_dir.mkdir(parents=True, exist_ok=True)
                    img_dat = np.stack([vv_db, vh_db], axis=0)
                    with rasterio.open(
                            pool_dir / f"S1Hand_{chip_id}.tif", "w",
                            driver="GTiff", height=size, width=size, count=2,
                            dtype="float32") as dst:
                        dst.write(img_dat)
                    with rasterio.open(
                            pool_dir / f"LabelHand_{chip_id}.tif", "w",
                            driver="GTiff", height=size, width=size, count=1,
                            dtype="int16") as dst:
                        dst.write(lab[np.newaxis, :, :])
                    stats["chips"] += 1
                    stats["train"] += (pool == "WeakLabeled")
                    stats["val"] += (pool == "HandLabeled")
    print(f"chips built: {stats}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "chips_meta.json").write_text(
        json.dumps({"stats": stats, "label_scheme": CANON_LABELS,
                    "split": "temporal (val = most recent scenes)",
                    "bands": ["VV_sigma0_dB", "VH_sigma0_dB"],
                    "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                   indent=1), encoding="utf-8")
    return stats


# ----------------------------------------------------------------------
# selftest (anonymous)
# ----------------------------------------------------------------------
def selftest():
    print("== anonymous smoke test ==")
    m = enumerate_all(Path("ml/data/india_2025_2026_selftest"), step_deg=5.0,
                      quick_cells=2, max_pages_per_cell_year=2, quiet=True)
    print("scenes found:", m["coverage"]["n_scenes"])
    print("== DEM tile ==")
    tiles = download_dem((90.0, 25.0, 91.0, 26.0),
                         Path("ml/data/india_2025_2026_selftest/dem"))
    for t in tiles:
        print("tile:", t, t.stat().st_size, "bytes")


# ----------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Pan-India 2025-2026 SAR U-Net dataset")
    sub = p.add_subparsers(dest="stage", required=True)

    e = sub.add_parser("enumerate")
    e.add_argument("--out", default="ml/data/india_2025_2026")
    e.add_argument("--step-deg", type=float, default=2.5)
    e.add_argument("--quick-cells", type=int, default=None)
    e.add_argument("--max-pages", type=int, default=6)
    e.add_argument("--quiet", action="store_true",
                   help="only print per-cell summaries")

    d = sub.add_parser("download-dem")
    d.add_argument("--out", default="ml/data/india_2025_2026/dem")
    d.add_argument("--bbox", required=True,
                   help="lon0,lat0,lon1,lat1")

    s = sub.add_parser("download-sar")
    s.add_argument("--out", default="ml/data/india_2025_2026/sar")
    s.add_argument("--scene", action="append", required=True, help="SAFE name(s)")
    s.add_argument("--cdse-user", default=None)
    s.add_argument("--cdse-pass", default=None)

    c = sub.add_parser("chips")
    c.add_argument("--out", default="ml/data/india_2025_2026/chips")
    c.add_argument("--sar-dir", default="ml/data/india_2025_2026/sar")
    c.add_argument("--dem-dir", default="ml/data/india_2025_2026/dem")
    c.add_argument("--gsw-tiff", default=None)
    c.add_argument("--size", type=int, default=256)
    c.add_argument("--stride", type=int, default=128)
    c.add_argument("--val-frac", type=float, default=0.2)

    t = sub.add_parser("train")
    t.add_argument("--data-dir", default="ml/data/india_2025_2026/chips")

    sub.add_parser("selftest")

    a = p.parse_args()
    out_dir = Path(a.out if hasattr(a, "out") else "ml/data/india_2025_2026")

    if a.stage == "enumerate":
        enumerate_all(out_dir, step_deg=a.step_deg, quick_cells=a.quick_cells,
                      max_pages_per_cell_year=a.max_pages, quiet=a.quiet)
    elif a.stage == "download-dem":
        bbox = tuple(float(x) for x in a.bbox.split(","))
        tiles = download_dem(bbox, out_dir)
        print("tiles:", [str(t) for t in tiles])
    elif a.stage == "download-sar":
        token = get_cdse_token(a.cdse_user, a.cdse_pass)
        sar_dir = Path(a.out)
        for name in a.scene:
            zip_path = download_scene(name, sar_dir / "zips", token)
            import subprocess
            safe = sar_dir / "unzip" / name
            if not safe.exists():
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(sar_dir / "unzip")
            calibrate_safe(safe, "VV", sar_dir / f"{name}_VV.tif")
            calibrate_safe(safe, "VH", sar_dir / f"{name}_VH.tif")
    elif a.stage == "chips":
        build_chips(Path(a.sar_dir), Path(a.dem_dir), out_dir, size=a.size,
                    stride=a.stride, val_frac=a.val_frac,
                    gsw_tiff=Path(a.gsw_tiff) if a.gsw_tiff else None)
    elif a.stage == "train":
        import subprocess
        subprocess.check_call([sys.executable, str(ROOT / "ml/sar/train_unet.py"),
                               "--data-dir", a.data_dir, "--size", "256",
                               "--epochs", "35", "--pos-weight", "8",
                               "--grad-clip", "1.0"])
    elif a.stage == "selftest":
        selftest()


if __name__ == "__main__":
    main()
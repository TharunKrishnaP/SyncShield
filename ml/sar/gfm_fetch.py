"""Credential-free Copernicus GFM label access via the EODC STAC API.

Why this exists
---------------
The training labels must be *real, current (2025-2026) and pan-India*. No
published dataset pairs expert flood labels with India in 2025-2026 (CEMS has
zero India activations in that window, so GEOID-Flood / ImpactMesh-Flood
contribute nothing for India). The Copernicus **Global Flood Monitoring** (GFM)
service is the only operational product that does: it processes every Sentinel-1
IW GRDH acquisition over land, in near real time, since 2015-01-01.

The GFM web portal (portal.gfm.eodc.eu) needs an account, but the **data plane
does not**. Verified end-to-end against live services:

  * ``https://stac.eodc.eu/api/v1`` (collection ``GFM``) answers anonymous
    searches -- 1,431 items matched over Assam for Jul-Sep 2025.
  * Every layer file under ``https://data.eodc.eu/collections/...`` returns
    HTTP 200 to an anonymous request, and a 16-byte ranged GET shows a valid
    little-endian TIFF header (``49 49 2a 00``).

No account, no token, no approval queue. This mirrors ``mpc_fetch.py`` (same
idea for Sentinel-1 imagery).

Label semantics (uint8, single band, Equi7 ``AS020M`` grid reprojectable to
EPSG:4326)
---------------------------------------------------------------------------
  * ``ensemble_flood_extent``  0 = not flooded, 1 = flooded (nodata via mask)
  * ``reference_water_mask``   0 = none, 1 = permanent water, 2 = seasonal water
  * ``exclusion_mask``         0/1 analysis-exclusion layer
  * ``advisory_flags``         bit flags (0 = none)
  * ``ensemble_likelihood``    0-100 %, agreement across the three algorithms

GFM combines three independent algorithms (LIST, TUW, DLR) by majority vote, so
it is already an ensemble rather than a single threshold. This module derives
the canonical label ``{-1 no-data, 0 not-water, 1 water}`` from those layers.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

STAC = "https://stac.eodc.eu/api/v1"
COLLECTION = "GFM"
DATA_BASE = "https://data.eodc.eu/collections"
UA = {"User-Agent": "Mozilla/5.0 (FloodManagement research)"}

# Layers downloaded for a label tile. The first two carry the signal; the rest
# are precision controls (exclusion / confidence) kept for filtering.
DEFAULT_LAYERS: Tuple[str, ...] = (
    "ensemble_flood_extent",
    "reference_water_mask",
    "exclusion_mask",
    "advisory_flags",
    "ensemble_likelihood",
)

# Canonical label vocabulary, identical to build_india_2025_2026.CANON_LABELS.
NO_DATA, NOT_WATER, WATER = -1, 0, 1


# ----------------------------------------------------------------------
# STAC search
# ----------------------------------------------------------------------
def search_payload(bbox: Sequence[float], start: str, end: str,
                   limit: int = 200) -> dict:
    """Body for ``POST /search``. Pure, so it is unit-tested directly."""
    return {
        "collections": [COLLECTION],
        "bbox": [float(v) for v in bbox],
        "datetime": f"{start}/{end}",
        "limit": min(int(limit), 10000),
    }


def search_items(bbox: Sequence[float], start: str, end: str,
                 limit: int = 200, timeout: int = 120) -> List[dict]:
    """Anonymous STAC search. Returns normalised GFM items (metadata only)."""
    body = search_payload(bbox, start, end, limit=limit)
    req = urllib.request.Request(
        f"{STAC}/search", data=json.dumps(body).encode(),
        headers={**UA, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode())
    return [item_from_feature(f) for f in payload.get("features", [])]


def item_from_feature(feature: dict) -> dict:
    """Normalise one STAC feature into the schema the rest of this module uses.

    ``bbox`` is taken from the STAC ``bbox`` when present and otherwise
    computed from the geometry, so every item carries an explicit footprint for
    the scene/tile intersection step.
    """
    props = feature.get("properties", {})
    bbox = feature.get("bbox")
    if not bbox:
        geom = feature.get("geometry") or {}
        pts = [p for ring in geom.get("coordinates", []) for p in ring]
        xs = [float(p[0]) for p in pts if len(p) >= 2]
        ys = [float(p[1]) for p in pts if len(p) >= 2]
        bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else None
    return {
        "id": feature.get("id", ""),
        "datetime": props.get("datetime") or props.get("start_datetime", ""),
        "bbox": [float(v) for v in bbox] if bbox else None,
        "assets": {k: (v.get("href") if isinstance(v, dict) else v)
                   for k, v in (feature.get("assets") or {}).items()},
    }


def gfm_tiles_intersecting(scene_bbox: Sequence[float],
                           items: Sequence[dict]) -> List[dict]:
    """GFM tiles whose footprint overlaps ``scene_bbox`` (pure geometry).

    Keeps only items that actually carry the flood-extent asset, so a tile that
    merely touches the bbox but has no label cannot poison the mosaic.
    """
    sx0, sy0, sx1, sy1 = (float(v) for v in scene_bbox)
    hits = []
    for it in items:
        b = it.get("bbox")
        if not b or "ensemble_flood_extent" not in (it.get("assets") or {}):
            continue
        bx0, by0, bx1, by1 = b
        if bx0 <= sx1 and bx1 >= sx0 and by0 <= sy1 and by1 >= sy0:
            hits.append(it)
    return hits


_SCENE_DT = re.compile(r"(\d{8}T\d{6})")


def sensing_datetime_from_name(name: str) -> Optional[datetime]:
    """Parse the acquisition time out of a Sentinel-1 scene name.

    ``S1A_IW_GRDH_1SDV_20250710T233056_...`` -> 2025-07-10T23:30:56Z. The
    ``.SAFE`` suffix (if present) is irrelevant to the scan.
    """
    m = _SCENE_DT.search(name or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


# ----------------------------------------------------------------------
# download (plain, public -- no signing needed)
# ----------------------------------------------------------------------
def download(url: str, dest: Path, retries: int = 4, timeout: int = 300) -> Path:
    """Stream ``url`` to ``dest`` atomically via a ``.part`` file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r, \
                    open(part, "wb") as fh:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
            part.replace(dest)
            return dest
        except Exception as exc:                    # noqa: BLE001
            last = exc
            if part.exists():
                part.unlink()
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed after {retries} attempts: {url}") from last


def asset_filename(item_id: str, key: str) -> str:
    """Deterministic local name for one layer of one GFM item."""
    return f"{item_id}__{key}.tif"


def fetch_item_layers(item: dict, out_dir: Path,
                      layers: Sequence[str] = DEFAULT_LAYERS,
                      skip_existing: bool = True) -> Dict[str, Path]:
    """Download the requested layers for one GFM item. Returns key -> path."""
    assets = item.get("assets") or {}
    out: Dict[str, Path] = {}
    for key in layers:
        href = assets.get(key)
        if not href:
            continue
        dest = Path(out_dir) / asset_filename(item["id"], key)
        if skip_existing and dest.exists() and dest.stat().st_size > 0:
            out[key] = dest
            continue
        download(href, dest)
        out[key] = dest
    missing = [k for k in ("ensemble_flood_extent",) if k not in out]
    if missing:
        raise RuntimeError(
            f"GFM item {item.get('id')} has no {missing[0]} layer")
    return out


# ----------------------------------------------------------------------
# canonical label derivation (pure; unit-tested)
# ----------------------------------------------------------------------
def derive_canonical_label(flood: np.ndarray,
                           refwater: Optional[np.ndarray] = None,
                           valid: Optional[np.ndarray] = None,
                           mode: str = "flood",
                           likelihood: Optional[np.ndarray] = None,
                           min_likelihood: Optional[int] = None) -> np.ndarray:
    """Combine GFM layers into ``{-1,0,1}`` (int16).

    Parameters
    ----------
    flood     : ``ensemble_flood_extent`` (1 == flooded).
    refwater  : ``reference_water_mask`` (1 permanent / 2 seasonal). Only used
                in ``mode="water"``.
    valid     : boolean mask; ``False`` -> ``-1``. Defaults to all-valid.
    mode      : ``"flood"`` labels only the flood extent as water (the review's
                target); ``"water"`` also labels permanent/seasonal water.
    likelihood: ``ensemble_likelihood`` (0-100 %). When ``min_likelihood`` is
                given, flooded pixels below it are demoted to ``-1`` (no-data)
                rather than guessed, so uncertain pixels never train the model.

    The function is deliberately free of I/O and provider types so the label
    contract can be pinned by tests without network access.
    """
    flood = np.asarray(flood)
    if valid is None:
        valid = np.ones(flood.shape, dtype=bool)
    else:
        valid = np.asarray(valid, dtype=bool)

    water = flood == 1
    if mode == "water" and refwater is not None:
        water = water | (np.asarray(refwater) > 0)
    elif mode not in ("flood", "water"):
        raise ValueError(f"unknown label mode: {mode!r}")

    if min_likelihood is not None and likelihood is not None:
        uncertain = (np.asarray(likelihood) < int(min_likelihood)) & flood_mask(flood)
        valid = valid & ~uncertain

    label = np.where(valid, np.where(water, WATER, NOT_WATER), NO_DATA)
    return label.astype(np.int16)


def flood_mask(flood: np.ndarray) -> np.ndarray:
    """Boolean "was considered flooded" mask (tolerates 0/1 or bool input)."""
    return np.asarray(flood) == 1


# ----------------------------------------------------------------------
# raster alignment: GFM tiles -> canonical label on a scene's grid
# ----------------------------------------------------------------------
def _read_warped(path: Path, dst_crs, dst_transform, width: int, height: int,
                 fill):
    """Read ``path`` resampled onto an explicit target grid.

    ``nearest`` resampling is mandatory for categorical layers: bilinear would
    invent class values that do not exist.
    """
    import rasterio
    from rasterio.vrt import WarpedVRT
    with rasterio.open(str(path)) as src:
        with WarpedVRT(src, crs=dst_crs, transform=dst_transform,
                       width=width, height=height, resampling="nearest",
                       src_nodata=src.nodata) as vrt:
            arr = vrt.read(1, masked=True)
            return np.asarray(arr.filled(fill)), np.asarray(~arr.mask)


def build_label_for_scene(scene_vv_tif: Path, gfm_layer_paths: Sequence[Path],
                          out_tif: Path, mode: str = "flood",
                          min_likelihood: Optional[int] = None) -> Path:
    """Mosaic the GFM tiles overlapping a scene onto the scene's grid.

    ``gfm_layer_paths`` are per-item asset paths (from :func:`fetch_item_layers`);
    only items carrying ``ensemble_flood_extent`` are used. Output is an int16
    GeoTIFF (``-1/0/1``) sharing the scene's CRS, transform and size, so
    ``build_chips`` can read it with the exact same window as the imagery.
    """
    import rasterio

    with rasterio.open(str(scene_vv_tif)) as s:
        crs, transform = s.crs, s.transform
        width, height = s.width, s.height

    # group paths by item id so flood + refwater + likelihood stay together
    by_item: Dict[str, Dict[str, Path]] = {}
    for p in gfm_layer_paths:
        stem = Path(p).name
        if "__" not in stem:
            continue
        item_id, _, key = stem[:-4].partition("__")
        by_item.setdefault(item_id, {})[key] = Path(p)

    label = np.full((height, width), NO_DATA, dtype=np.int16)
    used = 0
    for layers in by_item.values():
        if "ensemble_flood_extent" not in layers:
            continue
        flood, fvalid = _read_warped(layers["ensemble_flood_extent"], crs,
                                     transform, width, height, fill=0)
        refwater = likelihood = None
        if "reference_water_mask" in layers:
            refwater, _ = _read_warped(layers["reference_water_mask"], crs,
                                       transform, width, height, fill=0)
        if min_likelihood is not None and "ensemble_likelihood" in layers:
            likelihood, _ = _read_warped(layers["ensemble_likelihood"], crs,
                                         transform, width, height, fill=0)
        lab = derive_canonical_label(flood, refwater, valid=fvalid, mode=mode,
                                     likelihood=likelihood,
                                     min_likelihood=min_likelihood)
        # only overwrite where this tile actually has data
        take = fvalid
        label[take] = lab[take]
        used += 1

    out_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(str(out_tif), "w", driver="GTiff", height=height,
                       width=width, count=1, dtype="int16", crs=crs,
                       transform=transform, compress="deflate",
                       nodata=NO_DATA) as dst:
        dst.write(label, 1)
    if used == 0:
        raise RuntimeError(f"no GFM tiles overlapped scene {scene_vv_tif.name}")
    return out_tif


def scene_bbox_wgs84(scene_tif: Path) -> Tuple[float, float, float, float]:
    """WGS84 (lon0, lat0, lon1, lat1) bounds of a calibrated scene GeoTIFF."""
    import rasterio
    from rasterio.warp import transform_bounds
    with rasterio.open(str(scene_tif)) as s:
        b = s.bounds
        if s.crs and str(s.crs).upper() != "EPSG:4326":
            return tuple(transform_bounds(s.crs, "EPSG:4326", *b))
        return (b.left, b.bottom, b.right, b.top)


def labels_for_scenes(sar_dir: Path, out_dir: Path, cache_dir: Path,
                      mode: str = "flood", layers: Sequence[str] = DEFAULT_LAYERS,
                      min_likelihood: Optional[int] = None, pad_days: int = 1,
                      dry_run: bool = False, limit: int = 400) -> dict:
    """Derive one canonical GFM label GeoTIFF per calibrated SAR scene.

    For each ``S1*_VV.tif`` the scene's acquisition time (parsed from its name)
    and WGS84 bbox select the GFM tiles that actually overlap it; those tiles
    are downloaded once (cached across scenes) and mosaicked onto the scene's
    own grid. ``dry_run`` prints the work without downloading anything.
    """
    scenes = sorted(Path(sar_dir).glob("S1*_VV.tif"))
    if not scenes:
        raise SystemExit(f"no S1*_VV.tif under {sar_dir} (run download-sar first)")
    stats = {"scenes": len(scenes), "built": 0, "no_datetime": 0,
             "no_tiles": 0, "tiles_downloaded": 0, "dry_run": dry_run,
             "mode": mode}
    for vv in scenes:
        dt = sensing_datetime_from_name(vv.name)
        if dt is None:
            stats["no_datetime"] += 1
            print(f"  [skip] {vv.name}: no acquisition time in name", flush=True)
            continue
        bbox = scene_bbox_wgs84(vv)
        start = (dt - timedelta(days=pad_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (dt + timedelta(days=pad_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        items = search_items(bbox, start, end, limit=limit)
        tiles = gfm_tiles_intersecting(bbox, items)
        dest = Path(out_dir) / vv.name.replace("_VV.tif", "_LABEL.tif")
        if not tiles:
            stats["no_tiles"] += 1
            print(f"  [warn] {vv.name}: 0 GFM tiles in {start[:10]}", flush=True)
            continue
        if dry_run:
            print(f"  [dry-run] {vv.name}: {len(tiles)} tile(s) -> {dest.name}",
                  flush=True)
            continue
        paths: List[Path] = []
        for it in tiles:
            got = fetch_item_layers(it, Path(cache_dir), layers)
            stats["tiles_downloaded"] += 1
            paths.extend(got.values())
        build_label_for_scene(vv, paths, dest, mode=mode,
                              min_likelihood=min_likelihood)
        stats["built"] += 1
        print(f"  [ok] {dest.name} from {len(tiles)} tile(s)", flush=True)
    print(f"gfm labels: {stats}")
    return stats


# ----------------------------------------------------------------------
# self-check
# ----------------------------------------------------------------------
def selftest(bbox: Tuple[float, float, float, float] = (89.5, 24.0, 96.0, 28.0),
             start: str = "2025-07-01T00:00:00Z",
             end: str = "2025-09-30T23:59:59Z") -> int:
    """Prove the credential-free path works: search -> open -> ranged GET.

    Reads only the first bytes of one asset; never downloads a whole scene.
    """
    print("searching EODC STAC catalogue (anonymous)...")
    items = search_items(bbox, start, end, limit=50)
    print(f"  {len(items)} GFM item(s) in {start[:10]}..{end[:10]}")
    if not items:
        print("FAIL: no items returned")
        return 1

    it = items[0]
    print(f"  {it['id']}")
    print(f"    acq {it['datetime'][:19]}  bbox "
          f"{[round(v, 3) for v in it['bbox']]}")
    href = it["assets"].get("ensemble_flood_extent")
    if not href:
        print("FAIL: first item has no ensemble_flood_extent asset")
        return 1
    req = urllib.request.Request(href, headers={**UA, "Range": "bytes=0-15"})
    with urllib.request.urlopen(req, timeout=120) as r:
        head = r.read(4)
        cr = r.headers.get("Content-Range", "")
    ok = head[:4] == b"\x49\x49\x2a\x00"
    print(f"  ranged GET -> {r.status}, {cr}")
    print(f"  TIFF magic {'valid' if ok else 'INVALID'}: {head[:4].hex(' ')}")
    print("\nSELFTEST PASSED - no GFM/EODC account required"
          if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())

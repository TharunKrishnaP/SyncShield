"""Credential-free Sentinel-1 GRD access via Microsoft Planetary Computer.

Why this exists
---------------
CDSE registration is gated behind an email-verification link that can fail or
stall, and until it clears there is no way to obtain 2025-2026 pixels for
India. Planetary Computer mirrors the **same ESA products** -- identical SAFE
identifiers, same ``calibration-<pol>.xml`` vectors -- and serves them to
anonymous requests. No account, no key, no approval queue.

Verified end-to-end (see ``tests/test_mpc_fetch.py`` and the module constants):
an anonymous STAC search returns 2025 Bihar scenes, an anonymous SAS request
returns a valid read token, and a signed ranged GET on ``measurement/iw-vv.tiff``
returns ``206`` with a valid little-endian TIFF header.

Reusing the existing calibration path
-------------------------------------
The downloads are written into the same directory layout as a Sentinel-1 SAFE
product::

    <scene_dir>/measurement/s1a-iw-vv.tiff
    <scene_dir>/annotation/calibration/calibration-VV.xml
    <scene_dir>/annotation/noise/noise-VV.xml
    <scene_dir>/annotation/product/product-VV.xml

which is exactly what ``build_india_2025_2026.calibrate_safe`` expects. The
radiometric maths therefore stays single-sourced: one implementation, two
transport routes, no chance of the paths diverging numerically.

Provenance is unchanged. MPC serves ESA's product verbatim; the scene IDs match
the CDSE catalogue. ESA's data terms apply (the STAC collection is labelled
``proprietary``, which is ESA's licensing convention for freely redistributed
open data, not a restriction on research use).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS_BASE = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
COLLECTION = "sentinel-1-grd"
BLOB_ACCOUNT = "sentinel1euwest"
BLOB_CONTAINER = "s1-grd"
UA = {"User-Agent": "Mozilla/5.0 (FloodManagement research)"}

# CDSE allows 4 concurrent connections; MPC's container tolerates the same and
# going higher is a needless courtesy violation on shared infrastructure.
MAX_CONCURRENT_DOWNLOADS = 4

# Refresh a SAS token this long before it actually expires (tokens last ~45 min).
SAS_REFRESH_MARGIN_S = 300
SAS_LIFETIME_S = 1800  # assumed worst case; refreshed early if wrong


# ----------------------------------------------------------------------
# STAC search
# ----------------------------------------------------------------------
def search_scenes(bbox: Sequence[float], start: str, end: str,
                  limit: int = 100) -> List[dict]:
    """Search the MPC catalogue. Anonymous; returns normalised scene records.

    ``bbox`` is (lon_min, lat_min, lon_max, lat_max). ``start``/``end`` are
    ISO datetimes. Scene records carry the SAME fields the CDSE manifest uses
    (``name``, ``acquisition``, ``bbox``, ``platform``) so downstream stages --
    pairing, chipping, train/test split -- are provider-agnostic.
    """
    payload = {
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{start}/{end}",
        "limit": limit,
    }
    req = urllib.request.Request(
        f"{STAC}/search", data=json.dumps(payload).encode(),
        headers={**UA, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read().decode())
    return [scene_from_feature(f) for f in body.get("features", [])]


def scene_from_feature(feature: dict) -> dict:
    """Normalise one STAC feature into our manifest scene schema.

    The ``.SAFE`` suffix is reattached so names are byte-identical to the CDSE
    catalogue's. That matters: ``chip_id_for`` strips the platform tag and the
    label matcher in ``train_unet`` does a literal ``replace("S1", "Label")``,
    so a naming drift here would silently break image/label pairing downstream.
    """
    props = feature.get("properties", {})
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []

    lons: List[float] = []
    lats: List[float] = []
    for ring in coords:
        for pt in ring:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                lons.append(float(pt[0]))
                lats.append(float(pt[1]))

    name = feature.get("id", "")
    if name and not name.endswith(".SAFE"):
        name += ".SAFE"

    return {
        "id": feature.get("id", ""),
        "name": name,
        "acquisition": props.get("start_datetime") or props.get("datetime", ""),
        "bbox": [min(lons), min(lats), max(lons), max(lats)] if lons else None,
        "platform": (props.get("platform") or name[:3]).upper(),
        "product_type": props.get("sar:product_type"),
        "polarizations": props.get("sar:polarizations"),
        "assets": {k: v.get("href") for k, v in (feature.get("assets") or {}).items()},
    }


# ----------------------------------------------------------------------
# anonymous SAS signing
# ----------------------------------------------------------------------
def account_container(href: str) -> Tuple[str, str]:
    """Pull (storage account, container) out of a blob URL."""
    m = re.match(r"https://([^.]+)\.blob\.core\.windows\.net/([^/?]+)", href)
    if not m:
        raise ValueError(f"not a blob href: {href}")
    return m.group(1), m.group(2)


class SasCache:
    """Cache anonymous read tokens per (account, container).

    Tokens are short-lived, and every miss costs a round trip, so one token is
    reused across all scenes hitting the same container. Refresh happens a
    safety margin ahead of expiry so a long download cannot have its stream
    invalidated mid-transfer. Thread-safe because downloads are concurrent.
    """

    def __init__(self, refresh_margin_s: int = SAS_REFRESH_MARGIN_S):
        self._tokens: Dict[Tuple[str, str], Tuple[str, float]] = {}
        self._lock = threading.Lock()
        self.refresh_margin_s = refresh_margin_s

    def token_for(self, href: str, force: bool = False) -> str:
        account, container = account_container(href)
        key = (account, container)
        now = time.time()
        with self._lock:
            hit = self._tokens.get(key)
            if hit and not force and now < (hit[1] - self.refresh_margin_s):
                return hit[0]

        url = f"{SAS_BASE}/{account}/{container}"
        req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode())
        token = payload.get("token")
        if not token:
            raise RuntimeError(f"MPC returned no SAS token for {key}")

        expires = _parse_expiry(payload.get("msft:expiry"))
        lifetime = (expires - time.time()) if expires else SAS_LIFETIME_S
        with self._lock:
            self._tokens[key] = (token, time.time() + lifetime)
        return token


def _parse_expiry(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def signed_url(href: str, cache: SasCache) -> str:
    token = cache.token_for(href)
    sep = "&" if "?" in href else "?"
    return f"{href}{sep}{token}"


# ----------------------------------------------------------------------
# download
# ----------------------------------------------------------------------
def download(url: str, dest: Path, retries: int = 4,
             timeout: int = 300) -> Path:
    """Stream ``url`` to ``dest``. Atomic via a .part file.

    Writes to ``dest.with_suffix(dest.suffix + '.part')`` and renames on
    success, so an interrupted run can never leave a truncated file that later
    stages would silently treat as a complete scene.
    """
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
        except Exception as exc:                    # noqa: BLE001 - retry any failure
            last = exc
            if part.exists():
                part.unlink()
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed after {retries} attempts: {url}") from last


# ----------------------------------------------------------------------
# SAFE-layout assembly
# ----------------------------------------------------------------------
# MPC asset key -> (subdir, filename). Filenames are the official SAFE names so
# the existing calibrate_safe()/measurement glob works unmodified.
_ASSET_LAYOUT = {
    "vv": ("measurement", "s1a-iw-vv.tiff"),
    "vh": ("measurement", "s1a-iw-vh.tiff"),
    "schema-calibration-vv": ("annotation/calibration", "calibration-VV.xml"),
    "schema-calibration-vh": ("annotation/calibration", "calibration-VH.xml"),
    "schema-noise-vv": ("annotation/noise", "noise-VV.xml"),
    "schema-noise-vh": ("annotation/noise", "noise-VH.xml"),
    "schema-product-vv": ("annotation/product", "product-VV.xml"),
    "schema-product-vh": ("annotation/product", "product-VH.xml"),
}


def scene_dir_name(scene: dict) -> str:
    """Directory name for a scene, without the ``.SAFE`` suffix."""
    name = scene.get("name") or scene.get("id") or "scene"
    return name[:-5] if name.endswith(".SAFE") else name


def asset_targets(pol: str) -> Dict[str, Tuple[str, str]]:
    """The asset keys needed for one polarisation, with their SAFE paths."""
    lower = pol.lower()
    return {
        lower: _ASSET_LAYOUT[lower],
        f"schema-calibration-{lower}": _ASSET_LAYOUT[f"schema-calibration-{lower}"],
        f"schema-noise-{lower}": _ASSET_LAYOUT[f"schema-noise-{lower}"],
        f"schema-product-{lower}": _ASSET_LAYOUT[f"schema-product-{lower}"],
    }


def fetch_scene(scene: dict, out_dir: Path, pols: Sequence[str] = ("VV", "VH"),
                cache: Optional[SasCache] = None, skip_existing: bool = True,
                progress: bool = True) -> Path:
    """Download one scene into a SAFE-equivalent directory under ``out_dir``.

    Returns the scene directory, which can be passed straight to
    ``build_india_2025_2026.calibrate_safe``.
    """
    cache = cache or SasCache()
    assets = scene.get("assets") or {}
    if not assets:
        raise RuntimeError(f"scene has no asset hrefs: {scene.get('name')}")

    sdir = Path(out_dir) / scene_dir_name(scene)
    for pol in pols:
        for key, (subdir, fname) in asset_targets(pol).items():
            href = assets.get(key)
            if not href:
                raise RuntimeError(f"scene {scene.get('name')} missing asset {key}")
            dest = sdir / subdir / fname
            if skip_existing and dest.exists() and dest.stat().st_size > 0:
                continue
            if progress:
                print(f"  [{key}] -> {dest.name}")
            download(signed_url(href, cache), dest)
    return sdir


def fetch_and_calibrate(scene: dict, sar_dir: Path, pols: Sequence[str] = ("VV", "VH"),
                        cache: Optional[SasCache] = None,
                        skip_existing: bool = True) -> Dict[str, Path]:
    """Fetch a scene then radiometrically calibrate to sigma0-dB GeoTIFFs.

    Calibration is delegated to ``build_india_2025_2026.calibrate_safe`` so the
    physics is identical to the CDSE route.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_india_2025_2026 import calibrate_safe

    sdir = fetch_scene(scene, sar_dir, pols=pols, cache=cache,
                       skip_existing=skip_existing)
    out: Dict[str, Path] = {}
    for pol in pols:
        tif = Path(sar_dir) / f"{scene_dir_name(scene)}_{pol}.tif"
        if skip_existing and tif.exists() and tif.stat().st_size > 0:
            out[pol] = tif
            continue
        out[pol] = calibrate_safe(sdir, pol, tif)
    return out


# ----------------------------------------------------------------------
# self-check
# ----------------------------------------------------------------------
def selftest(bbox: Tuple[float, float, float, float] = (85.0, 25.0, 87.0, 27.0),
             start: str = "2025-07-01T00:00:00Z",
             end: str = "2025-07-31T23:59:59Z") -> int:
    """Prove the credential-free path works: search -> sign -> ranged GET.

    Reads only the first bytes of one asset; it never downloads a whole scene.
    """
    print("searching MPC catalogue (anonymous)...")
    scenes = search_scenes(bbox, start, end, limit=5)
    print(f"  {len(scenes)} scene(s) in {start[:10]}..{end[:10]}")
    if not scenes:
        print("FAIL: no scenes returned")
        return 1

    s = scenes[0]
    print(f"  {s['name']}")
    print(f"    acq {s['acquisition'][:19]}  bbox {[round(v, 3) for v in s['bbox']]}")

    cache = SasCache()
    href = s["assets"]["vv"]
    print(f"signing (anonymous SAS)...")
    su = signed_url(href, cache)
    print(f"  token cached for {account_container(href)}")

    req = urllib.request.Request(su, headers={**UA, "Range": "bytes=0-1023"})
    with urllib.request.urlopen(req, timeout=120) as r:
        head = r.read(8)
        cr = r.headers.get("Content-Range", "")
    print(f"ranged GET -> {r.status}, {cr}")
    # little-endian TIFF: 49 49 2A 00
    ok = head[:4] == b"\x49\x49\x2a\x00"
    print(f"  TIFF magic {'valid' if ok else 'INVALID'}: {head[:4].hex(' ')}")
    print("\nSELFTEST PASSED - no CDSE account required"
          if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())

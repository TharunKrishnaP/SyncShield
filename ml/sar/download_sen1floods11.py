"""Download Sen1Floods11 event subsets directly from the canonical public GCS bucket.

Why not the Hugging Face mirror (``harshinde/sen1floods``)? The mirror's
single ~35 GB tar started returning HTTP 401 for anonymous downloads (Sept
2025) even though the repo is public. The canonical bucket ``sen1floods11``
(Google Cloud Storage) is public: ``https://storage.googleapis.com/sen1floods11/...``
serves files with NO auth, and the storage JSON API lists objects by prefix —
so we fetch only the exact files we need. A single-event India run is
~0.9 GB on disk, not ~35 GB.

Canonical v1.1 layout (files named ``<EVENT>_<CHIPID>_<LAYER>.tif``):

    v1.1/data/flood_events/HandLabeled/{S1Hand,S2Hand,LabelHand,JRCWaterHand,S1OtsuLabelHand}/
    v1.1/data/flood_events/WeaklyLabeled/{S1Weak,S2Weak,S1OtsuLabelWeak,S2IndexLabelWeak}/

Relevant layers (authors' README layer table):

    S1 imagery       2-band float32, VV/VH, dB (S1Hand for hand-labeled chips;
                     S1Weak for weakly-labeled chips - same format)
    LabelHand        int16  {-1 = no data, 0 = not water, 1 = water}
    S1OtsuLabelWeak  int16  {0, 1} water mask from VH Otsu thresholding

Per the authors' metadata (``Sen1Floods11_Metadata.geojson``), each event is
split into ``train_chip`` (weak-labeled) + ``val_chip`` (hand-labeled); the
India event (2016 Assam) is 467 + 68 = 535 chips. This script fetches BOTH
pools and renames them into the layout ``train_unet.py`` reads:

    <out>/WeakLabeled/S1Hand_India_<id>.tif + LabelHand_India_<id>.tif   (train pool)
    <out>/HandLabeled/S1Hand_India_<id>.tif + LabelHand_India_<id>.tif   (val pool)

``train_unet.py --mode sen1floods11`` then trains on WeakLabeled and validates
on HandLabeled - the dataset's own split, so the reported val IoU is on chips
and labels the model never saw (no leak).

Usage:
    python ml/sar/download_sen1floods11.py --events India --out /content/sen1floods11
    python ml/sar/download_sen1floods11.py --events India Pakistan Sri-Lanka
    python ml/sar/download_sen1floods11.py --out /content/sen1floods11   # all events
"""
import argparse
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BUCKET = "sen1floods11"
ROOT = "v1.1/data/flood_events"
BASE_URL = f"https://storage.googleapis.com/{BUCKET}/"
LIST_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"

# canonical pool folder -> (S1 image layer, water-label layer, local subdir name)
POOLS = [
    ("WeaklyLabeled", "S1Weak", "S1OtsuLabelWeak", "WeakLabeled"),
    ("HandLabeled", "S1Hand", "LabelHand", "HandLabeled"),
]

# from v1.1/Sen1Floods11_Metadata.geojson: event -> (train_chip, val_chip)
EVENTS = {
    "Bolivia": (224, 15),
    "Colombia": (534, 0),
    "Ghana": (181, 53),
    "India": (467, 68),
    "Cambodia": (1353, 30),
    "Nigeria": (109, 18),
    "Pakistan": (249, 28),
    "Paraguay": (316, 67),
    "Somalia": (129, 26),
    "Spain": (146, 30),
    "Sri-Lanka": (190, 42),
    "USA": (486, 69),
}
EVENT_KEYS = {e.lower(): e for e in EVENTS}


def list_objects(prefix: str):
    """All object names under a GCS prefix (paged through the JSON API)."""
    names, token = [], None
    while True:
        params = {"prefix": prefix, "maxResults": "1000"}
        if token:
            params["pageToken"] = token
        url = LIST_URL + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.load(r)
        names += [it["name"] for it in data.get("items", [])]
        token = data.get("nextPageToken")
        if not token:
            break
    return names


def download_one(name: str, dst: Path, urlopen_timeout: int = 120):
    """Fetch one object to ``dst`` (skip if already there and non-empty)."""
    if dst.exists() and dst.stat().st_size > 0:
        return dst, False
    dst.parent.mkdir(parents=True, exist_ok=True)
    url = BASE_URL + urllib.parse.quote(name)
    partial = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(url, timeout=urlopen_timeout) as r:
        with open(partial, "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
    partial.replace(dst)
    return dst, True


def plan(events, out_root: Path):
    """Build (source object name, destination path) jobs for the chosen events."""
    wanted = {e.lower() for e in (events or EVENT_KEYS)}
    jobs = []
    for pool, img_layer, lab_layer, subdir in POOLS:
        for layer, tag in ((img_layer, "image"), (lab_layer, "label")):
            names = list_objects(f"{ROOT}/{pool}/{layer}/")
            for name in names:
                stem = Path(name).name[: -len(".tif")]
                # <EVENT>_<CHIPID>_<LAYER>  (event has no underscores; strip the
                # trailing layer token so chip = the numeric id only)
                event_token, _, rest = stem.partition("_")
                chip = rest.rsplit("_", 1)[0]
                if event_token.lower() not in wanted:
                    continue
                local_layer = "S1Hand" if tag == "image" else "LabelHand"
                dst = out_root / subdir / f"{local_layer}_{event_token}_{chip}.tif"
                jobs.append((name, dst))
    return jobs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/content/sen1floods11",
                    help="Output directory (default: /content/sen1floods11)")
    ap.add_argument("--events", nargs="*", default=None,
                    help="Events to fetch (e.g. --events India). Default: all 12.")
    ap.add_argument("--workers", type=int, default=8,
                    help="Concurrent download workers (default: 8)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Debug: only fetch the first N chips of each pool (0 = all).")
    args = ap.parse_args()
    events = [EVENT_KEYS.get(e.lower(), e) for e in (args.events or [])]
    if args.events:
        unknown = [e for e in events if e not in EVENTS]
        if unknown:
            ap.error(f"unknown event(s): {', '.join(unknown)}; known: {', '.join(EVENTS)}")

    out_root = Path(args.out)
    jobs = plan(events, out_root)
    if args.limit:
        seen = {}
        kept = []
        for name, dst in jobs:
            key = dst.parent.name + ":" + ("img" if dst.name.startswith("S1Hand") else "lab")
            if seen.get(key, 0) >= args.limit:
                continue
            seen[key] = seen.get(key, 0) + 1
            kept.append((name, dst))
        jobs = kept
    print(f"plan: {len(jobs)} files to fetch", end="")
    if events:
        print(f" for event(s): {', '.join(events)}")
    else:
        print(" (all events)")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(download_one, name, dst): dst for name, dst in jobs}
        done = 0
        for fut in futures:
            fut.result()
            done += 1
            if done % 100 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} files")

    print("\nsummary:")
    for sub in ("WeakLabeled", "HandLabeled"):
        s1 = sorted((out_root / sub).glob("S1Hand_*.tif"))
        lab = sorted((out_root / sub).glob("LabelHand_*.tif"))
        print(f"  {sub}: {len(s1)} S1Hand images / {len(lab)} LabelHand labels")
    print(f"  total chips: {len(list(out_root.glob('*/S1Hand_*.tif')))}")

    # verify against the authors' metadata for the requested events
    for ev in events:
        want_tr, want_val = EVENTS[ev]
        tr = len(list((out_root / "WeakLabeled").glob(f"S1Hand_{ev}_*.tif")))
        va = len(list((out_root / "HandLabeled").glob(f"S1Hand_{ev}_*.tif")))
        ok_tr = "OK" if tr in (0, want_tr) else "MISMATCH"
        ok_va = "OK" if va in (0, want_val) else "MISMATCH"
        print(f"  {ev}: train(weak)={tr} (expect {want_tr}) {ok_tr} | "
              f"val(hand)={va} (expect {want_val}) {ok_va}")


if __name__ == "__main__":
    main()
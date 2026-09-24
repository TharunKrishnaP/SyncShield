"""Copy a real Sen1Floods11 India Sentinel-1 tile into ml/data/sar_scenes.

The demo scene must be real data (no synthetic scenes anywhere). This picks a
hand-labeled India tile (S1Hand = real VV/VH backscatter, georeferenced
EPSG:4326) and copies it as the demo scene so `POST /api/ai/sar/ingest` and
`verify_backend_sar.py` run against true satellite imagery.

Usage:
    python ml/sar/mk_real_scene.py --data ml/data/sen1floods11 \
        --tile India_1017769 --out ml/data/sar_scenes/scene_india_assam.tif
"""
import argparse
import shutil
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="ml/data/sen1floods11",
                    help="downloaded Sen1Floods11 root (HasLakes: HandLabeled)")
    ap.add_argument("--tile", default="India_1017769",
                    help="chip id, e.g. India_1017769 (must exist as S1Hand_<id>.tif)")
    ap.add_argument("--out", default="ml/data/sar_scenes/scene_india_assam.tif")
    args = ap.parse_args()

    data = Path(args.data)
    hand = data / "HandLabeled"
    src = None
    for cand in hand.glob(f"S1Hand_{args.tile}.tif"):
        src = cand
        break
    # fall back to searching anywhere under the data dir
    if src is None:
        for cand in data.rglob(f"S1Hand_{args.tile}.tif"):
            src = cand
            break
    if src is None:
        print(f"ERROR: S1Hand_{args.tile}.tif not found under {data}")
        sys.exit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out)
    print(f"OK: real scene <- {src} ({src.stat().st_size} bytes)")
    print(f"    -> {out}")


if __name__ == "__main__":
    main()
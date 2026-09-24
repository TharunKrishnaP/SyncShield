"""Download the Sen1Floods11 subset from the Hugging Face mirror.

Mirror: https://huggingface.co/datasets/harshinde/sen1floods (cc-by-4.0)
Ships as a single ~35 GB tarball (4851 tile images + labels). Meant to run on
Colab (60-70 GB disk free) or any machine with enough space.

Usage:
    python ml/sar/download_sen1floods11.py            # full dataset
    python ml/sar/download_sen1floods11.py --out /content/sen1floods11

Training happens with `train_unet.py --mode sen1floods11 --data-dir <out>`.
"""
import argparse
import os
import shutil
import tarfile
from pathlib import Path

REPO_ID = "harshinde/sen1floods"
ARCHIVE = "sen1floods11.tar.gz"


def safe_path(p: Path) -> Path:
    """Collapse '..' so we never extract outside the target dir."""
    return Path(os.path.normpath(str(p)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/content/sen1floods11",
                    help="Extraction directory (default: /content/sen1floods11)")
    ap.add_argument("--keep-events", nargs="*", default=None,
                    help="Optional: only keep these event folders (e.g. --keep-events TP07_Nepal TP14_India)")
    args = ap.parse_args()

    from huggingface_hub import hf_hub_download

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    archive_path = Path(hf_hub_download(repo_id=REPO_ID, filename=ARCHIVE))

    print(f"extracting {archive_path} (size ~{archive_path.stat().st_size / 1e9:.1f} GB) ...")
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        # Extract with path safety.
        for member in members:
            target = safe_path(out / member.name)
            if not str(target).startswith(str(out.resolve())):
                print(f"skipping unsafe path {member.name}")
                continue
            tar.extract(member, path=out)
    print(f"extracted to {out}")

    if args.keep_events:
        for d in out.iterdir():
            if d.is_dir() and not any(ev in d.name for ev in args.keep_events):
                shutil.rmtree(d, ignore_errors=True)
                print(f"dropped {d.name}")

    tiles = [d for d in out.iterdir() if d.is_dir() and d.name.startswith("TP")]
    count = sum(1 for t in tiles for _ in t.glob("*.tif"))
    print(f"kept {len(tiles)} events, ~{count} .tif files (image/label pairs)")


if __name__ == "__main__":
    main()
"""Download the Sen1Floods11 subset(s) from the Hugging Face mirror.

Mirror: https://huggingface.co/datasets/harshinde/sen1floods (cc-by-4.0)
Ships as a single ~35 GB tarball of ALL events/layers. You usually do NOT need
the whole tar: ``--events`` + ``--layers`` filter the extraction *before* any
bytes hit disk, so a single-event India run keeps only ~1.5 GB (S1Hand +
LabelHand pairs). The tar itself is deleted from the HF cache afterwards to
free the ~35 GB.

Usage:
    # India event only, image+label pairs (what train_unet.py reads):
    python ml/sar/download_sen1floods11.py --events India --layers S1Hand LabelHand
    python ml/sar/download_sen1floods11.py --out /content/sen1floods11
        --events India --layers S1Hand LabelHand
    python ml/sar/download_sen1floods11.py            # full dataset (60-70 GB)
    # multiple events/layers:
    python ml/sar/download_sen1floods11.py --events India Pakistan Sri-Lanka \
        --layers S1Hand LabelHand

Training happens with `train_unet.py --mode sen1floods11 --data-dir <out>`.
Tile names follow ``<Layer>_<Event>_<chipid>.tif`` (mirror layout, e.g.
``S1Hand_India_5.tif``), so matching is done on the underscore tokens.
"""
import argparse
import os
import tarfile
from pathlib import Path

REPO_ID = "harshinde/sen1floods"
ARCHIVE = "sen1floods11.tar.gz"


def safe_path(p: Path) -> Path:
    """Collapse '..' so we never extract outside the target dir."""
    return Path(os.path.normpath(str(p)))


def tokens(file_name: str) -> set:
    """Upper-cased underscore tokens of a tile basename.

    ``S1Hand_India_5.tif`` -> {"S1HAND", "INDIA", "5"}
    """
    stem = Path(file_name).name
    stem = stem[: stem.rfind(".")] if "." in stem else stem
    return {t.upper() for t in stem.split("_") if t}


def wanted(member_name: str, events, layers) -> bool:
    """True when a tar member should be extracted.

    With no filters everything is kept (full-dataset mode). With filters, only
    ``.tif`` files whose name carries every requested event and one of the
    requested layers pass.
    """
    if not events and not layers:
        return True
    if not member_name.lower().endswith(".tif"):
        return False
    toks = tokens(member_name)
    if events and not toks.intersection(set(events)):
        return False
    if layers and not toks.intersection(set(layers)):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/content/sen1floods11",
                    help="Extraction directory (default: /content/sen1floods11)")
    ap.add_argument("--events", nargs="*", default=None,
                    help="Only extract these events (e.g. --events India), matched "
                         "against the EVENT token of each tile name (mirror layout "
                         "'<Layer>_<Event>_<chipid>.tif').")
    ap.add_argument("--layers", nargs="*", default=None,
                    help="Only extract these layers (e.g. --layers S1Hand LabelHand). "
                         "train_unet.py needs S1Hand + LabelHand only.")
    ap.add_argument("--no-delete-tar", action="store_true",
                    help="Keep the downloaded tar in the HF cache (default: delete it "
                         "after extraction to free ~35 GB).")
    args = ap.parse_args()

    from huggingface_hub import hf_hub_download

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    archive_path = Path(hf_hub_download(repo_id=REPO_ID, filename=ARCHIVE))

    events = [e.upper() for e in (args.events or [])]
    layers = [l.upper() for l in (args.layers or [])]
    keep_all = not (events or layers)

    print(f"extracting {archive_path} (size ~{archive_path.stat().st_size / 1e9:.1f} GB) ...")
    extracted = 0
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not (keep_all or wanted(member.name, events, layers)):
                continue
            target = safe_path(out / member.name)
            if not str(target).startswith(str(out.resolve())):
                print(f"skipping unsafe path {member.name}")
                continue
            try:
                tar.extract(member, path=out, filter="data")  # py >= 3.12
            except TypeError:  # pragma: no cover - py < 3.12 has no filter=
                tar.extract(member, path=out)
            extracted += 1
    print(f"extracted {extracted} files to {out}")
    if not keep_all:
        print(f"  filter: events={events or 'any'} layers={layers or 'any'}")

    if not args.no_delete_tar:
        try:
            size_gb = archive_path.stat().st_size / 1e9
            archive_path.unlink()
            print(f"deleted tar {archive_path.name} (~{size_gb:.1f} GB) from HF cache")
        except OSError as exc:  # pragma: no cover - cache may be read-only
            print(f"note: could not delete tar: {exc}")

    s1 = sorted(out.rglob("S1Hand_*.tif"))
    print(f"kept {len(s1)} S1Hand image chips (with label pairs) under {out}")
    if args.layers and "S1Hand" not in args.layers:
        print("  (S1Hand not requested, so the chip count above may be 0)")


if __name__ == "__main__":
    main()
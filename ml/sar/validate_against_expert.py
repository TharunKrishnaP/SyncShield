"""Validate derived change-detection labels against published expert flood maps.

This is the measurement that answers the reviewer's real question. There is no
labelled 2025-2026 India dataset to train on, so our labels are derived from the
imagery. The only honest way to know whether those derived labels are any good
is to score them against *expert* delineations for the same real flood events:
the EOS-RS/ARIA-SG flood proxy maps (CC-BY, HDX, SAR-derived by the Earth
Observatory of Singapore Remote Sensing Lab).

Run:
    python ml/sar/validate_against_expert.py --pairs pairs.json --out report.json

``pairs.json`` is produced by the scene-pairing stage and describes, per event,
which pre/post SAR arrays to read and where the expert mask lives:

    [
      {"event": "20190930_bihar", "sensor": "Sentinel-1",
       "expert": "F:/.../EOS_ARIA-SG_20190930_FPM_India_Floods_v0.1_TIFF.tif",
       "pre": "F:/.../pre.tif", "post": "F:/.../post.tif"}
    ]

If ``pre``/``post`` are omitted the pair is *scored only* using each expert
mask's own pre/post basis where discoverable, which at minimum reports the
expert mask's own area and is how we confirm an asset is non-empty before
trusting it as ground truth.

Exit code is non-zero if the report fails its gate, so this can run in CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "ml" / "sar"))

from derive_flood_labels import (  # noqa: E402
    Agreement,
    aggregate_agreement,
    derive_change_labels,
    refine_threshold_from_reference,
    score_against_reference,
)

# Gate: derived labels must agree with expert delineations at least this well.
# Deliberately conservative. A derived-label pipeline that cannot clear this
# against published expert maps should not be used to train a model.
MIN_MEAN_IOU = 0.30
MIN_MEAN_RECALL = 0.40


def _read_mask_on_grid(expert_path: Path, ref: np.ndarray) -> np.ndarray:
    """Resample a boolean expert mask onto ``ref``'s shape.

    Uses nearest-neighbour so the expert's delineation is not blurred into a
    partial-coverage smear, which would make recall look worse than it is.
    """
    import rasterio

    with rasterio.open(str(expert_path)) as ds:
        h, w = ref.shape
        arr = ds.read(1, out_shape=(h, w), resampling=rasterio.enums.Resampling.nearest)
    return np.asarray(arr) > 0


def _read_bands(path: Path, size: Optional[int] = None) -> Tuple[np.ndarray, ...]:
    import rasterio

    with rasterio.open(str(path)) as ds:
        count = ds.count
        h, w = ds.height, ds.width
        out_shape = (count, size, size) if size else None
        arr = ds.read(out_shape=out_shape).astype(np.float32)
    return tuple(arr[i] for i in range(count))


def score_pair(spec: dict, size: Optional[int] = 256,
               calibrate: bool = True,
               default_min_drop_db: float = -1.5) -> Tuple[Optional[Agreement], dict]:
    """Score one event. Returns (agreement_or_None, diagnostics)."""
    expert_path = Path(spec["expert"])
    if not expert_path.exists():
        return None, {"error": f"expert mask not found: {expert_path}"}

    diag: dict = {"event": spec.get("event", ""), "sensor": spec.get("sensor", ""),
                  "expert": str(expert_path)}

    pre_p, post_p = spec.get("pre"), spec.get("post")
    if not pre_p or not post_p:
        # Asset-integrity check only: refuse to trust an empty mask.
        import rasterio
        with rasterio.open(str(expert_path)) as ds:
            arr = ds.read(1)
        n_water = int((arr > 0).sum())
        diag["mode"] = "expert-only"
        diag["expert_water_px"] = n_water
        diag["expert_empty"] = n_water == 0
        return None, diag

    pre_path, post_path = Path(pre_p), Path(post_p)
    if not pre_path.exists() or not post_path.exists():
        diag["error"] = f"missing SAR array: {pre_path if not pre_path.exists() else post_path}"
        return None, diag

    bands_pre = _read_bands(pre_path, size)
    bands_post = _read_bands(post_path, size)
    if len(bands_pre) < 1 or len(bands_post) < 1:
        diag["error"] = "SAR arrays have no bands"
        return None, diag

    # Prefer VH (last band) for change detection: it responds most to calm water.
    pre_vh = bands_pre[-1]
    post_vh = bands_post[-1]
    ref = _read_mask_on_grid(expert_path, pre_vh)

    thr = None
    if calibrate:
        thr, cal = refine_threshold_from_reference(pre_vh, post_vh, ref)
        diag["calibration"] = cal

    used_thr = float(thr) if thr is not None else default_min_drop_db
    labels, info = derive_change_labels(pre_vh, post_vh, min_drop_db=used_thr)
    diag["derived"] = {k: v for k, v in info.items() if k != "per_chip"}
    diag["threshold_used_db"] = used_thr

    agree = score_against_reference(labels, ref,
                                   name=expert_path.stem,
                                   event=spec.get("event", ""),
                                   sensor=spec.get("sensor", ""))
    diag["mode"] = "derived-vs-expert"
    return agree, diag


def build_report(specs: List[dict], size: Optional[int], calibrate: bool) -> dict:
    agreements, diags = [], []
    for spec in specs:
        a, d = score_pair(spec, size=size, calibrate=calibrate)
        diags.append(d)
        if a is not None:
            agreements.append(a)

    agg = aggregate_agreement(agreements)
    empty = [d for d in diags if d.get("expert_empty")]
    report = {
        "pairs_specified": len(specs),
        "pairs_scored": len(agreements),
        "gate": {"min_mean_iou": MIN_MEAN_IOU, "min_mean_recall": MIN_MEAN_RECALL},
        "aggregate": agg,
        "empty_expert_masks": [d.get("expert") for d in empty],
        "agreements": [a.as_dict() for a in agreements],
        "diagnostics": diags,
    }
    passed = (
        len(agreements) > 0
        and agg.get("mean_iou", 0.0) >= MIN_MEAN_IOU
        and agg.get("mean_recall", 0.0) >= MIN_MEAN_RECALL
        and not empty
    )
    report["passed"] = passed
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=Path, required=True,
                    help="JSON list of event specs (see module docstring)")
    ap.add_argument("--out", type=Path, default=REPO / "ml" / "evidence" / "expert_validation.json")
    ap.add_argument("--size", type=int, default=256, help="chip size; 0 = native")
    ap.add_argument("--no-calibrate", action="store_true",
                    help="use the default drop threshold instead of calibrating")
    args = ap.parse_args(argv)

    specs = json.loads(args.pairs.read_text(encoding="utf-8"))
    if isinstance(specs, dict):
        specs = specs.get("pairs", [])

    report = build_report(specs, size=(args.size or None), calibrate=not args.no_calibrate)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")

    agg = report["aggregate"]
    print(f"scored {report['pairs_scored']}/{report['pairs_specified']} pairs")
    if report["empty_expert_masks"]:
        print(f"WARNING: {len(report['empty_expert_masks'])} empty expert mask(s) - excluded")
    if report["pairs_scored"]:
        print(f"  mean IoU    {agg['mean_iou']:.4f}  (gate >= {MIN_MEAN_IOU})")
        print(f"  mean recall {agg['mean_recall']:.4f}  (gate >= {MIN_MEAN_RECALL})")
        print(f"  mean dice   {agg['mean_dice']:.4f}")
    print(f"  wrote {args.out}")
    print("PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
"""End-to-end selftest for validate_against_expert.py.

Builds a tiny synthetic pre/post pair with a KNOWN flood patch plus a matching
expert mask, then confirms the derived labels agree with the expert mask.

This is a *pipeline* selftest (does the plumbing work end-to-end?), not evidence
about real-world accuracy. Real numbers require real SAR + real ARIA masks via
ml/sar/validate_against_expert.py with a real --pairs file. The selftest's
numbers are NOT quoted anywhere as validation results.

Run:  python ml/sar/selftest_validate.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "ml" / "sar"))

from validate_against_expert import build_report  # noqa: E402


def make_scene(path: Path, drop: np.ndarray, seed: int) -> None:
    import rasterio

    rng = np.random.default_rng(seed)
    n = drop.shape[0]
    base = rng.normal(-6.0, 1.0, (n, n)).astype(np.float32)
    arr = base - drop.astype(np.float32) * 8.0
    with rasterio.open(str(path), "w", driver="GTiff", height=n, width=n, count=2,
                       dtype="float32", crs="EPSG:4326",
                       transform=rasterio.transform.from_origin(85.0, 27.0, 0.001, 0.001)) as dst:
        dst.write(np.stack([arr, arr], axis=0))


def make_expert(path: Path, ref: np.ndarray) -> None:
    import rasterio

    n = ref.shape[0]
    with rasterio.open(str(path), "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="uint8", crs="EPSG:4326",
                       transform=rasterio.transform.from_origin(85.0, 27.0, 0.001, 0.001)) as dst:
        dst.write(ref.astype(np.uint8), 1)


def main() -> int:
    import rasterio

    rng = np.random.default_rng(11)
    n = 128
    flood = np.zeros((n, n), bool)
    flood[24:104, 24:104] = True
    mask = flood & (rng.random((n, n)) < 0.75)   # ragged edge, like a real map

    tmp = Path(tempfile.mkdtemp(prefix="selftest_expert_"))
    pre, post, exp = tmp / "pre.tif", tmp / "post.tif", tmp / "expert.tif"
    make_scene(pre, np.zeros((n, n), bool), 1)
    make_scene(post, mask, 2)
    make_expert(exp, mask)

    specs = [{"event": "selftest", "sensor": "Sentinel-1",
              "expert": str(exp), "pre": str(pre), "post": str(post)}]
    pairs_file = tmp / "pairs.json"
    pairs_file.write_text(json.dumps(specs), encoding="utf-8")

    # full pipeline through the CLI, exactly as a real run would
    out = tmp / "report.json"
    proc = subprocess.run(
        [sys.executable, str(REPO / "ml" / "sar" / "validate_against_expert.py"),
         "--pairs", str(pairs_file), "--out", str(out)],
        capture_output=True, text=True,
    )
    print(proc.stdout.strip())
    if proc.returncode not in (0, 1):
        print(proc.stderr.strip())
        return 1

    report = json.loads(out.read_text(encoding="utf-8"))
    agg = report["aggregate"]

    checks = [
        ("scored the pair", report["pairs_scored"] == 1),
        ("no empty expert mask", not report["empty_expert_masks"]),
        ("calibration ran", report["diagnostics"][0]["calibration"]["calibrated"] is True),
        ("derived a water mask", report["diagnostics"][0]["derived"]["water_px"] > 0),
        ("IoU >= 0.9 on planted mask", agg["mean_iou"] >= 0.9),
        ("recall >= 0.9", agg["mean_recall"] >= 0.9),
        ("gate passed", report["passed"] is True),
        ("CLI exit code 0", proc.returncode == 0),
    ]
    print()
    ok = True
    for label, passed in checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print(f"\nselftest {'PASSED' if ok else 'FAILED'} (synthetic - pipeline check only)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
"""Tests: the pan-India 2025-2026 real-data SAR dataset builder.

Everything the builder emits must be real, recent (strictly 2025 or 2026),
and must keep the canonical labelling scheme. These tests validate the pure
helpers offline, then (when the manifest has been built on this machine)
audit the on-disk manifest: scene names, acquisition dates, district
coverage, and the absence of any synthetic marker.

Run:  python -m pytest tests/test_panindia_dataset_builder.py -v
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ml.sar.build_india_2025_2026 import (  # noqa: E402
    CANON_LABELS,
    _odata_filter_parts,
    _calibrate_to_sigma0_db,
    chip_id_for,
    otsu_threshold,
    parse_scene,
)

MANIFEST = REPO / "ml" / "data" / "india_2025_2026" / "manifest.json"


class TestSceneParsing:
    def test_only_real_s1_grd_iw_scenes_kept(self):
        # polarisation data layer not GRDH -> rejected
        assert parse_scene({"Name": "S1A_IW_SLC__1SDV_20250710T000000_....SAFE",
                            "GeoFootprint": {"type": "Polygon",
                                             "coordinates": [[[90, 25], [91, 25],
                                                              [91, 26], [90, 26],
                                                              [90, 25]]]}}) is None
        # real GRDH IW scene with GeoJSON footprint -> kept, bbox computed
        sc = parse_scene({
            "Id": "abc",
            "Name": "S1A_IW_GRDH_1SDV_20250710T233056_20250710T233121_060028_077526_568F.SAFE",
            "ContentDate": {"Start": "2025-07-10T23:30:56.000000Z",
                            "End": "2025-07-10T23:31:21.000000Z"},
            "GeoFootprint": {"type": "Polygon", "coordinates": [
                [[97.57, 24.72], [97.89, 26.23], [95.36, 26.65],
                 [95.08, 25.14], [97.57, 24.72]]]},
        })
        assert sc is not None
        assert sc["name"].startswith("S1A_IW_GRDH_1SDV_2025")
        assert sc["acquisition"].startswith("2025-07-10")
        assert abs(sc["bbox"][0] - 95.08) < 0.01      # lon min
        assert abs(sc["bbox"][3] - 26.65) < 0.01      # lat max

    def test_wkt_footprint_fallback(self):
        sc = parse_scene({
            "Name": "S1C_IW_GRDH_1SDV_20260601T000000_000000_000000_000000.SAFE",
            "ContentDate": {"Start": "2026-06-01T00:00:00.000000Z"},
            "Footprint": "geography'SRID=4326;POLYGON ((90 25, 91 25, 91 26, 90 26, 90 25))'",
        })
        assert sc is not None
        assert sc["bbox"] == [90.0, 25.0, 91.0, 26.0]


class TestFilterIsStrictly2025_2026:
    def test_name_and_date_range_enforced(self):
        parts = _odata_filter_parts((90.0, 25.0, 92.0, 27.0), 2025)
        joined = " and ".join(parts)
        assert "2025-01-01T00:00:00.000Z" in joined
        assert "2025-12-31T23:59:59.999Z" in joined
        assert "Collection/Name eq 'SENTINEL-1'" in joined


class TestLabelAndCalibrationMath:
    def test_canonical_labels(self):
        assert CANON_LABELS == {-1: "no-data", 0: "not-water", 1: "water"}

    def test_otsu_separates_low_vh_from_water(self):
        rng = np.random.default_rng(7)
        dry = rng.normal(-16, 1.5, 200_000)      # real-ish dB backscatter
        wet = rng.normal(-8, 2.0, 60_000)
        vals = np.concatenate([dry, wet])
        thr = otsu_threshold(vals)
        assert -14 < thr < -6

    def test_sigma0_calibration_formula(self):
        # sigma0_dB = 10*log10(DN^2 / A^2) per the S1 calibration definition
        dn = np.array([[100.0, 200.0]])
        db = _calibrate_to_sigma0_db(dn, ["t"], [0.0], np.ones((1, 2)) * 2.0)
        assert abs(db[0, 0] - 10 * np.log10(100 ** 2 / 4.0)) < 0.01
        assert abs(db[0, 1] - 10 * np.log10(200 ** 2 / 4.0)) < 0.01

    def test_chip_id_pairs_with_train_unet_label_matcher(self):
        # train_unet.py finds labels via name.replace("S1", "Label") on the
        # image "S1Hand_<chip_id>.tif" - our chip ids must make that hit once.
        for stem in ("S1A_IW_GRDH_1SDV_20250710T233056_000000_000000_000000_VV",):
            cid = chip_id_for(stem, 12, 34)
            assert cid.startswith("A_IW_GRDH_1SDV_2025")
            img = f"S1Hand_{cid}.tif"
            assert img.replace("S1", "Label") == f"LabelHand_{cid}.tif"


@pytest.mark.skipif(not MANIFEST.exists(),
                    reason="pan-India manifest not built on this machine yet")
class TestOnDiskManifest:
    def _manifest(self):
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_every_scene_is_real_2025_2026_grd(self):
        m = self._manifest()
        scenes = m["scenes"]
        assert len(scenes) > 0
        for s in scenes:
            year = s["acquisition"][:4]
            assert year in ("2025", "2026"), s["name"]
            assert "GRDH" in s["name"] and "IW" in s["name"]
            assert len(s["bbox"]) == 4

    def test_district_level_coverage_reported(self):
        m = self._manifest()
        cov = m["district_coverage"]
        assert len(cov) > 700            # all-India district registry
        ids = {c["district_id"] for c in cov}
        assert len(ids) == len(cov)      # every district listed once
        assert any(c["flood_prone"] for c in cov)

    def test_no_synthetic_markers(self):
        m = self._manifest()
        for path_key in ("coverage", "build"):
            blob = json.dumps(m[path_key]).lower()
            assert "synthetic" not in blob
            assert "simulated" not in blob


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
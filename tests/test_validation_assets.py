"""Tests: the external India SAR flood validation asset audit.

The EOS-RS/ARIA-SG flood proxy maps are the *only* published expert SAR flood
delineations for India we can obtain. They are used as an external validation
reference for our derived 2025-2026 labels -- never as training labels, because
the newest India event they cover is 2023.

These tests pin down the pure helpers offline, then audit the on-disk audit
output: that masks are real published rasters, that the empty-mask trap is
excluded, and that no synthetic geometry ever enters the evidence.

Run:  python -m pytest tests/test_validation_assets.py -v
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ml.evidence.make_validation_summary import (  # noqa: E402
    INDIA_BBOX,
    SOURCES,
    event_key,
    pixel_area_km2,
    region_from_name,
    scan,
    sensor_of,
)

MANIFEST_CSV = REPO / "ml" / "evidence" / "validation_assets_india.csv"
EVIDENCE_MD = REPO / "ml" / "evidence" / "validation_assets_india.md"
RAW_ROOT = Path(r"F:\floodml\validation\aria_sg_extracted")


class TestHelpers:
    def test_pixel_area_matches_known_ground_distance(self):
        # ~30.9 m per pixel at the equator: one pixel ~ 9.5e-4 km^2
        a = pixel_area_km2(0.000278, 0.000278, 0.0)
        assert 0.00090 < a < 0.00100

    def test_pixel_area_shrinks_with_latitude(self):
        # 1 deg lon is shorter at higher latitude
        assert pixel_area_km2(0.000278, 0.000278, 28.0) < pixel_area_km2(0.000278, 0.000278, 10.0)

    def test_sensor_detection(self):
        assert sensor_of("EOS-RS_20221014_FPM_A2_India_Floods_v0.5.tif") == "ALOS-2"
        assert sensor_of("EOS-RS_20230712_FPM_S1_India_NewDelhi_Floods_v0.9.tif") == "Sentinel-1"

    def test_event_key_from_filename(self):
        assert event_key("EOS-RS_20230712_FPM_S1_India_NewDelhi_Floods_v0.9.tif") == "2023-07"
        assert event_key("EOS_ARIA-SG_20190930_FPM_India_Floods_v0.1_TIFF.tif") == "2019-09"

    def test_region_is_derived_from_name_not_guessed(self):
        assert region_from_name("..._NewDelhi_Floods_v0.9.tif") == "Delhi NCR"
        assert region_from_name("..._NorthernHaryana_Floods_v0.4.tif") == "N Haryana"
        # unknown names must not be given a fabricated region
        assert region_from_name("something_else.tif") == "India (unnamed AOI)"

    def test_provenance_cites_real_hdx_packages(self):
        assert len(SOURCES) == 7
        for _ev, (label, url) in SOURCES.items():
            assert label.startswith("HDX ")
            assert url.startswith("https://data.humdata.org/dataset/")


class TestOnDiskAudit:
    """Audit the committed evidence, if it has been generated on this machine."""

    def test_manifest_exists(self):
        if not MANIFEST_CSV.exists():
            pytest.skip("run ml/evidence/make_validation_summary.py first")
        assert MANIFEST_CSV.exists()

    def test_evidence_md_exists(self):
        if not EVIDENCE_MD.exists():
            pytest.skip("run ml/evidence/make_validation_summary.py first")
        text = EVIDENCE_MD.read_text(encoding="utf-8")
        assert "EOS-RS / ARIA-SG" in text
        # the recency caveat must survive, it is the whole point
        assert "2023-07" in text
        assert "not** supply 2025-2026 labels" in text

    def test_manifest_rows_are_real_and_in_india(self):
        if not MANIFEST_CSV.exists():
            pytest.skip("run ml/evidence/make_validation_summary.py first")
        rows = list(csv.DictReader(MANIFEST_CSV.open(encoding="utf-8")))
        assert len(rows) == 14
        for r in rows:
            assert r["crs"] == "EPSG:4326"
            assert r["in_india"] == "True"
            lon0, lon1 = float(r["lon_min"]), float(r["lon_max"])
            lat0, lat1 = float(r["lat_min"]), float(r["lat_max"])
            assert lon0 < INDIA_BBOX[2] and lon1 > INDIA_BBOX[0]
            assert lat0 < INDIA_BBOX[3] and lat1 > INDIA_BBOX[1]
            assert int(r["water_px"]) >= 0

    def test_usable_masks_are_all_sentinel1_and_nonempty(self):
        if not MANIFEST_CSV.exists():
            pytest.skip("run ml/evidence/make_validation_summary.py first")
        rows = list(csv.DictReader(MANIFEST_CSV.open(encoding="utf-8")))
        usable_s1 = [r for r in rows if r["sensor"] == "Sentinel-1" and int(r["water_px"]) > 0]
        assert len(usable_s1) == 7
        # the documented headline figure
        total_km2 = sum(float(r["flood_km2"]) for r in usable_s1)
        assert 11_000 < total_km2 < 12_000

    def test_empty_masks_are_flagged_not_used(self):
        if not MANIFEST_CSV.exists():
            pytest.skip("run ml/evidence/make_validation_summary.py first")
        rows = list(csv.DictReader(MANIFEST_CSV.open(encoding="utf-8")))
        empty = [r for r in rows if int(r["water_px"]) == 0]
        # the 4 known empty published masks must be present and excluded upstream
        assert len(empty) == 4
        assert all(float(r["flood_km2"]) == 0.0 for r in empty)

    def test_no_synthetic_geometry(self):
        """The audit must only ever see downloaded real rasters."""
        if not RAW_ROOT.exists():
            pytest.skip("validation assets not downloaded on this machine")
        found = list(RAW_ROOT.rglob("*.tif")) + list(RAW_ROOT.rglob("*.tiff"))
        assert found, "expected downloaded GeoTIFFs"
        for p in found:
            assert p.stat().st_size > 0
            # every name must trace back to a published EOS-RS/ARIA product
            assert p.name.startswith(("EOS-RS_", "EOS_ARIA-SG_")), p.name


class TestScanRoundTrip:
    def test_scan_returns_sorted_rows_with_expected_totals(self):
        if not RAW_ROOT.exists():
            pytest.skip("validation assets not downloaded on this machine")
        rows = scan(RAW_ROOT)
        assert len(rows) == 14
        # sorted by descending flood area
        areas = [r["flood_km2"] for r in rows]
        assert areas == sorted(areas, reverse=True)
        s1 = [r for r in rows if r["sensor"] == "Sentinel-1"]
        assert sum(1 for r in s1 if r["water_px"] > 0) == 7
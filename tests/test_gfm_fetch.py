"""Tests: credential-free Copernicus GFM label access via the EODC STAC API.

GFM is the only operational product that pairs real flood labels with India in
2025-2026. Its data plane is anonymous (verified against live services), so
these tests pin the pure logic: the STAC search body, feature normalisation,
tile/scene footprint intersection, acquisition-time parsing, and -- most
importantly -- the canonical ``{-1, 0, 1}`` label derivation from the raw GFM
layers.

Run:  python -m pytest tests/test_gfm_fetch.py -v
"""
import sys
from datetime import timezone
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ml.sar import gfm_fetch  # noqa: E402
from ml.sar.gfm_fetch import (  # noqa: E402
    NO_DATA,
    NOT_WATER,
    WATER,
    derive_canonical_label,
    gfm_tiles_intersecting,
    item_from_feature,
    search_payload,
    sensing_datetime_from_name,
)


class TestCanonicalVocabularyMatchesBuilder:
    def test_same_triplet_as_build_india(self):
        from ml.sar.build_india_2025_2026 import CANON_LABELS
        assert CANON_LABELS == {-1: "no-data", 0: "not-water", 1: "water"}
        assert (NO_DATA, NOT_WATER, WATER) == (-1, 0, 1)
        assert gfm_fetch.DEFAULT_LAYERS[0] == "ensemble_flood_extent"


class TestSearchPayload:
    def test_collection_bbox_and_datetime(self):
        p = search_payload((89.5, 24.0, 96.0, 28.0),
                           "2025-07-01T00:00:00Z", "2025-09-30T23:59:59Z")
        assert p["collections"] == ["GFM"]
        assert p["bbox"] == [89.5, 24.0, 96.0, 28.0]
        assert p["datetime"] == "2025-07-01T00:00:00Z/2025-09-30T23:59:59Z"

    def test_limit_is_capped(self):
        assert search_payload((0, 0, 1, 1), "a", "b", limit=99999)["limit"] == 10000


class TestItemNormalisation:
    def test_bbox_used_when_present(self):
        it = item_from_feature({"id": "x", "bbox": [1, 2, 3, 4],
                                "properties": {"datetime": "2025-07-10T00:00:00Z"},
                                "assets": {"ensemble_flood_extent": {"href": "h"}}})
        assert it["bbox"] == [1.0, 2.0, 3.0, 4.0]
        assert it["assets"]["ensemble_flood_extent"] == "h"

    def test_bbox_fallback_from_geometry(self):
        it = item_from_feature({
            "id": "x",
            "properties": {"datetime": "2025-07-10T00:00:00Z"},
            "geometry": {"type": "Polygon", "coordinates": [
                [[92.6, 22.5], [95.5, 22.5], [95.5, 25.2],
                 [92.6, 25.2], [92.6, 22.5]]]},
            "assets": {}})
        assert it["bbox"] == [92.6, 22.5, 95.5, 25.2]


class TestTileIntersection:
    def _item(self, bbox, keys=("ensemble_flood_extent",)):
        return {"id": "t", "bbox": list(bbox),
                "assets": {k: "href" for k in keys}}

    def test_overlapping_tile_kept(self):
        scene = (90.0, 24.0, 96.0, 28.0)
        assert len(gfm_tiles_intersecting(scene, [self._item((92.6, 22.5, 95.5, 25.2))])) == 1

    def test_far_tile_dropped(self):
        scene = (90.0, 24.0, 96.0, 28.0)
        assert gfm_tiles_intersecting(scene, [self._item((10.0, 10.0, 12.0, 12.0))]) == []

    def test_tile_without_flood_asset_dropped(self):
        scene = (90.0, 24.0, 96.0, 28.0)
        item = self._item((92.6, 22.5, 95.5, 25.2), keys=("reference_water_mask",))
        assert gfm_tiles_intersecting(scene, [item]) == []


class TestSensingDatetime:
    def test_parsed_from_scene_name(self):
        dt = sensing_datetime_from_name(
            "S1A_IW_GRDH_1SDV_20250710T233056_20250710T233121_060028_...")
        assert dt is not None and dt.tzinfo == timezone.utc
        assert (dt.year, dt.month, dt.day) == (2025, 7, 10)

    def test_unparseable_name_returns_none(self):
        assert sensing_datetime_from_name("S1A_IW_GRDH_nodate") is None


class TestCanonicalLabelDerivation:
    def test_flood_mode_labels_only_flood(self):
        flood = np.array([[1, 0]], dtype=np.uint8)
        refwater = np.array([[1, 0]], dtype=np.uint8)  # permanent water, no flood
        lab = derive_canonical_label(flood, refwater, mode="flood")
        assert lab.tolist() == [[1, 0]]                 # permanent water is NOT flood
        assert lab.dtype == np.int16

    def test_water_mode_includes_reference_water(self):
        flood = np.array([[0, 1]], dtype=np.uint8)
        refwater = np.array([[1, 0]], dtype=np.uint8)
        lab = derive_canonical_label(flood, refwater, mode="water")
        assert lab.tolist() == [[1, 1]]

    def test_invalid_pixels_become_no_data(self):
        flood = np.array([[1, 0]], dtype=np.uint8)
        valid = np.array([[True, False]])
        lab = derive_canonical_label(flood, valid=valid, mode="flood")
        assert lab.tolist() == [[1, -1]]

    def test_low_likelihood_flood_demoted_to_no_data(self):
        flood = np.array([[1, 1]], dtype=np.uint8)
        like = np.array([[10, 90]], dtype=np.uint8)
        lab = derive_canonical_label(flood, mode="flood", likelihood=like,
                                     min_likelihood=50)
        assert lab.tolist() == [[-1, 1]]

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="unknown label mode"):
            derive_canonical_label(np.array([[1]]), mode="nonsense")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

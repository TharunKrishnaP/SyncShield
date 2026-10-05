"""Tests: change-detection flood labelling for 2025-2026 pan-India Sentinel-1.

No published labelled flood dataset covers India in 2025-2026 (see
``ml/evidence/dataset_research_2026.md``), so labels are derived from the
imagery via pre/post-event change detection. These tests pin the pure logic
offline: canonical label semantics, pairing geometry, threshold calibration
against expert references, and agreement scoring.

Run:  python -m pytest tests/test_derive_flood_labels.py -v
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ml.sar.derive_flood_labels import (  # noqa: E402
    CANON_LABELS,
    DEFAULT_MAX_DROP_DB,
    DEFAULT_MIN_DROP_DB,
    NO_DATA,
    NOT_WATER,
    WATER,
    FloodEventHint,
    aggregate_agreement,
    db_drop_db,
    derive_change_labels,
    otsu_threshold,
    pair_scenes_for_event,
    refine_threshold_from_reference,
    score_against_reference,
)


def scene(name, acq, bbox=(85.0, 25.0, 87.0, 27.0)):
    return {"name": name, "acquisition": acq, "bbox": list(bbox)}


class TestCanonicalLabels:
    def test_scheme_is_the_repo_canonical_one(self):
        assert CANON_LABELS == {-1: "no-data", 0: "not-water", 1: "water"}
        assert (NO_DATA, NOT_WATER, WATER) == (-1, 0, 1)

    def test_db_drop_is_post_minus_pre(self):
        pre = np.array([[10.0, 10.0]], dtype=np.float32)
        post = np.array([[7.0, 11.0]], dtype=np.float32)
        drop = db_drop_db(pre, post)
        assert drop[0, 0] == pytest.approx(-3.0)
        assert drop[0, 1] == pytest.approx(1.0)

    def test_db_drop_rejects_shape_mismatch(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            db_drop_db(np.zeros((4, 4), np.float32), np.zeros((3, 3), np.float32))

    def test_flooded_pixels_become_water(self):
        pre = np.full((32, 32), 5.0, dtype=np.float32)
        post = np.full((32, 32), 5.0, dtype=np.float32)
        post[8:24, 8:24] = -4.0        # 9 dB drop = flooded
        lab, info = derive_change_labels(pre, post)
        assert set(np.unique(lab)).issubset({NO_DATA, NOT_WATER, WATER})
        assert lab[16, 16] == WATER
        assert lab[0, 0] == NOT_WATER
        assert info["water_px"] == 16 * 16

    def test_unchanged_pixels_are_not_water(self):
        pre = np.full((16, 16), -6.0, dtype=np.float32)
        post = np.full((16, 16), -6.0, dtype=np.float32)
        lab, info = derive_change_labels(pre, post)
        assert not (lab == WATER).any()
        assert info["water_frac"] == 0.0
        assert not info["meets_min_water"]

    def test_darkening_becomes_inundation_growth_and_worsening(self):
        # bright -> less bright is still water; bright -> black is no-data
        pre = np.full((16, 16), 2.0, dtype=np.float32)
        post = np.full((16, 16), 2.0, dtype=np.float32)
        post[:4, :] = -1.0        # 3 dB, above max_drop magnitude -> water
        post[4:8, :] = -20.0      # 22 dB, implausible -> treated as no-data
        lab, info = derive_change_labels(pre, post)
        assert (lab[0, :] == WATER).all()
        assert (lab[5, :] == NO_DATA).all()
        assert info["too_dark_px"] == 4 * 16

    def test_nan_pixels_become_no_data_not_water(self):
        pre = np.full((8, 8), 1.0, dtype=np.float32)
        post = np.full((8, 8), 1.0, dtype=np.float32)
        pre[0, 0] = np.nan
        post[1, 1] = np.nan
        lab, _ = derive_change_labels(pre, post)
        assert lab[0, 0] == NO_DATA
        assert lab[1, 1] == NO_DATA
        assert lab[4, 4] == NOT_WATER

    def test_labels_are_int16_and_canonical_only(self):
        pre = np.zeros((16, 16), np.float32)
        post = np.full((16, 16), -5.0, np.float32)
        lab, _ = derive_change_labels(pre, post)
        assert lab.dtype == np.int16
        assert set(np.unique(lab).tolist()) <= {-1, 0, 1}

    def test_extreme_drop_window_is_the_default(self):
        assert DEFAULT_MIN_DROP_DB > DEFAULT_MAX_DROP_DB
        assert DEFAULT_MIN_DROP_DB < 0 < 30


class TestOtsu:
    def test_separates_bimodal_distribution(self):
        v = np.concatenate([np.full(500, 2.0), np.full(500, 20.0)])
        assert 2.0 < otsu_threshold(v) < 20.0

    def test_nan_and_degenerate_inputs(self):
        assert np.isnan(otsu_threshold(np.array([])))
        assert np.isnan(otsu_threshold(np.array([1.0])))
        assert np.isnan(otsu_threshold(np.array([np.nan, np.nan])))


class TestPairing:
    def test_finds_valid_pre_post_bracket(self):
        ev = FloodEventHint(event_id="E1", date="2025-07-15", lat=26.0, lon=86.0)
        scenes = [
            scene("S1A_PRE", "2025-07-08T05:00:00.000Z"),
            scene("S1A_POST", "2025-07-16T05:00:00.000Z"),
        ]
        pairs = pair_scenes_for_event(scenes, ev)
        assert len(pairs) == 1
        p = pairs[0]
        assert p.pre_name == "S1A_PRE" and p.post_name == "S1A_POST"
        assert p.gap_days == pytest.approx(8.0)

    def test_rejects_baseline_longer_than_max_gap(self):
        ev = FloodEventHint(event_id="E1", date="2025-07-15", lat=26.0, lon=86.0)
        scenes = [
            scene("PRE", "2025-06-01T05:00:00.000Z"),
            scene("POST", "2025-07-16T05:00:00.000Z"),
        ]
        assert pair_scenes_for_event(scenes, ev, max_gap_days=12) == []

    def test_requires_spatial_overlap(self):
        ev = FloodEventHint(event_id="E1", date="2025-07-15", lat=26.0, lon=86.0)
        scenes = [
            scene("PRE", "2025-07-08T05:00:00.000Z", bbox=(85.0, 25.0, 87.0, 27.0)),
            scene("POST", "2025-07-16T05:00:00.000Z", bbox=(70.0, 12.0, 72.0, 14.0)),
        ]
        assert pair_scenes_for_event(scenes, ev, min_overlap=0.6) == []

    def test_respects_event_location_filter(self):
        # neither scene covers the event point
        ev = FloodEventHint(event_id="E1", date="2025-07-15", lat=26.0, lon=86.0)
        scenes = [
            scene("PRE", "2025-07-08T05:00:00.000Z", bbox=(68.0, 8.0, 70.0, 10.0)),
            scene("POST", "2025-07-16T05:00:00.000Z", bbox=(68.0, 8.0, 70.0, 10.0)),
        ]
        assert pair_scenes_for_event(scenes, ev) == []

    def test_pre_scene_must_precede_event_by_at_least_three_days(self):
        ev = FloodEventHint(event_id="E1", date="2025-07-15", lat=26.0, lon=86.0)
        scenes = [
            scene("TOO_CLOSE", "2025-07-14T05:00:00.000Z"),   # 1 day before
            scene("POST", "2025-07-16T05:00:00.000Z"),
        ]
        assert pair_scenes_for_event(scenes, ev) == []

    def test_pairs_sorted_by_shortest_baseline(self):
        # both baselines must fit inside the default 12-day max_gap_days
        ev = FloodEventHint(event_id="E1", date="2025-07-15", lat=26.0, lon=86.0)
        scenes = [
            scene("PRE_FAR", "2025-07-05T05:00:00.000Z"),    # 11-day baseline
            scene("PRE_NEAR", "2025-07-10T05:00:00.000Z"),   # 6-day baseline
            scene("POST", "2025-07-16T05:00:00.000Z"),
        ]
        pairs = pair_scenes_for_event(scenes, ev)
        assert [p.pre_name for p in pairs][0] == "PRE_NEAR"
        assert len(pairs) == 2
        assert pairs[0].gap_days < pairs[1].gap_days

    def test_chip_id_has_single_s1_for_label_pairing(self):
        p = type("P", (), {})()
        ev = FloodEventHint(event_id="E1", date="2025-07-15")
        pair = __import__("ml.sar.derive_flood_labels", fromlist=["ScenePair"]).ScenePair(
            pre_name="S1A_20250708_PRE.SAFE", post_name="S1A_20250716_POST.SAFE",
            pre_acq=datetime(2025, 7, 8, tzinfo=timezone.utc),
            post_acq=datetime(2025, 7, 16, tzinfo=timezone.utc), event=ev,
        )
        cid = pair.chip_id(128, 256)
        assert cid.count("S1") == 0
        assert "evE1" in cid and cid.endswith("_r128_c256")

    def test_missing_fields_are_skipped_not_fatal(self):
        ev = FloodEventHint(event_id="E1", date="2025-07-15")
        scenes = [{"name": "broken"}, scene("PRE", "2025-07-08T05:00:00.000Z"),
                  scene("POST", "2025-07-16T05:00:00.000Z")]
        pairs = pair_scenes_for_event(scenes, ev)
        assert len(pairs) == 1


class TestCalibration:
    def _pair(self):
        rng = np.random.default_rng(7)
        pre = np.full((64, 64), 3.0, dtype=np.float32)
        pre += rng.normal(0, 0.4, pre.shape).astype(np.float32)
        post = pre.copy()
        flood = np.zeros((64, 64), bool)
        flood[16:48, 16:48] = True
        post[flood] -= 7.0 + rng.normal(0, 0.4, flood.sum()).astype(np.float32)
        return pre, post, flood

    def test_recovers_a_planted_threshold(self):
        pre, post, ref = self._pair()
        thr, report = refine_threshold_from_reference(pre, post, ref)
        assert report["calibrated"] is True
        assert -10.0 < thr < -3.0
        assert report["separation_db"] > 3.0

    def test_report_records_achieved_agreement(self):
        pre, post, ref = self._pair()
        _, report = refine_threshold_from_reference(pre, post, ref)
        assert report["best_iou_vs_reference"] > 0.5
        assert report["n_flood_px"] == 32 * 32
        assert report["flood_drop_median_db"] < report["nonflood_drop_median_db"]

    def test_returns_default_when_reference_is_empty(self):
        pre, post, _ = self._pair()
        thr, report = refine_threshold_from_reference(
            pre, post, np.zeros((64, 64), bool))
        assert report["calibrated"] is False
        assert thr == DEFAULT_MIN_DROP_DB

    def test_rejects_shape_mismatch(self):
        pre, post, _ = self._pair()
        with pytest.raises(ValueError, match="shape mismatch"):
            refine_threshold_from_reference(pre, post, np.zeros((8, 8), bool))


class TestAgreementScoring:
    def test_perfect_agreement(self):
        ref = np.zeros((32, 32), bool)
        ref[8:24, 8:24] = True
        a = score_against_reference(np.where(ref, WATER, NOT_WATER).astype(np.int16), ref)
        assert a.iou == pytest.approx(1.0)
        assert a.dice == pytest.approx(1.0)
        assert a.precision == pytest.approx(1.0)
        assert a.recall == pytest.approx(1.0)

    def test_under_segmentation_is_counted_separately(self):
        ref = np.zeros((32, 32), bool)
        ref[0:16, :] = True          # expert says flood here
        pred = np.full((32, 32), NOT_WATER, dtype=np.int16)   # we found nothing
        a = score_against_reference(pred, ref)
        assert a.iou == 0.0
        assert a.ref_only_px == 16 * 32
        assert a.pred_only_px == 0

    def test_over_segmentation_is_counted_separately(self):
        ref = np.zeros((32, 32), bool)
        pred = np.full((32, 32), WATER, dtype=np.int16)
        a = score_against_reference(pred, ref)
        assert a.iou == 0.0
        assert a.pred_only_px == 32 * 32
        assert a.ref_only_px == 0

    def test_no_data_pixels_do_not_inflate_accuracy(self):
        # we predict nothing anywhere; all -1 (no coverage). Must NOT score 1.0
        lab = np.full((16, 16), NO_DATA, dtype=np.int16)
        ref = np.zeros((16, 16), bool)
        a = score_against_reference(lab, ref)
        assert a.iou == 0.0
        assert a.precision == 0.0
        assert a.recall == 0.0

    def test_no_data_excluded_from_water_tallies(self):
        ref = np.zeros((16, 16), bool)
        ref[0:8, :] = True
        lab = np.full((16, 16), NO_DATA, dtype=np.int16)
        lab[0:8, :] = WATER
        lab[8:, :] = NO_DATA
        a = score_against_reference(lab, ref)
        assert a.iou == pytest.approx(1.0)
        assert a.ref_water_px == 8 * 16

    def test_aggregate_reports_both_failure_modes(self):
        ref = np.zeros((16, 16), bool)
        ref[0:8, :] = True
        under = np.full((16, 16), NOT_WATER, dtype=np.int16)
        over = np.full((16, 16), WATER, dtype=np.int16)
        agg = aggregate_agreement([
            score_against_reference(under, ref, name="u"),
            score_against_reference(over, ref, name="o"),
        ])
        assert agg["n"] == 2
        assert agg["mean_ref_only_frac"] > 0
        assert agg["mean_pred_only_frac"] > 0

    def test_aggregate_of_nothing(self):
        assert aggregate_agreement([]) == {"n": 0}

    def test_rejects_shape_mismatch(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            score_against_reference(np.zeros((8, 8), np.int16), np.zeros((4, 4), bool))


class TestNoSyntheticGuard:
    """The labelling path must never invent labels without real inputs."""

    def test_identical_scenes_produce_no_water(self):
        rng = np.random.default_rng(3)
        a = rng.normal(-8, 1.5, (128, 128)).astype(np.float32)
        b = a.copy()
        lab, info = derive_change_labels(a, b)
        assert int((lab == WATER).sum()) == 0
        assert info["meets_min_water"] is False

    def test_water_requires_an_actual_drop(self):
        # scene gets BRIGHTER everywhere: definitely not flooding
        pre = np.full((32, 32), -10.0, dtype=np.float32)
        post = np.full((32, 32), -2.0, dtype=np.float32)
        lab, _ = derive_change_labels(pre, post)
        assert int((lab == WATER).sum()) == 0

    def test_thresholds_are_physically_ordered(self):
        assert DEFAULT_MAX_DROP_DB < DEFAULT_MIN_DROP_DB < 0.0
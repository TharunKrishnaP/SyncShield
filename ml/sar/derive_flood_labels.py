"""Change-detection flood labelling for 2025-2026 pan-India Sentinel-1.

Why this module exists
----------------------
No published labelled flood dataset covers India in 2025-2026 (verified: see
``ml/evidence/dataset_research_2026.md``). So recent labels must be *derived*
from the imagery itself.

Why change detection rather than a scene-level threshold
---------------------------------------------------------
A single-scene Otsu threshold on VH finds *water*, not *flood*: rivers, lakes and
irrigation all light up, so the resulting label is really a water mask wearing a
flood label. Comparing a scene acquired **before** an event against one acquired
**during/after** it isolates the pixels whose backscatter changed, which is a
materially closer approximation to *newly flooded* terrain.

This is the same weak-label philosophy as Sen1Floods11's WeakLabeled split, but
with two improvements we can actually verify: it is restricted to scenes with
independent evidence that a flood occurred (so the pre/post pairing is not
arbitrary), and its accuracy is measurable against published expert delineations
(EOS-RS/ARIA-SG, see ``ml/evidence/validation_assets_india.md``).

Labels use the canonical scheme shared with the rest of the repo:
``-1`` no-data, ``0`` not-water, ``1`` water.

Pure numpy in, numpy out: every function here is unit-testable offline with no
imagery, no network and no CDSE credentials.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

# Canonical label scheme (identical to build_india_2025_2026.CANON_LABELS)
NO_DATA = -1
NOT_WATER = 0
WATER = 1
CANON_LABELS = {NO_DATA: "no-data", NOT_WATER: "not-water", WATER: "water"}

# Floods attenuate C-band backscatter, so flooded pixels move *down* in dB.
# The ratio post/pre is therefore < 1 over water. A generous default window;
# tighten per-scene from the histogram rather than trusting a global constant.
DEFAULT_MIN_DROP_DB = -1.5   # at least this much darker than the pre-event scene
DEFAULT_MAX_DROP_DB = -12.0  # below this we treat the pixel as unclassifiable

# A scene pair whose acquisitions are further apart than this is not a useful
# before/after bracket: seasonal and agricultural change dominate.
DEFAULT_MAX_PAIR_GAP_DAYS = 12


# ----------------------------------------------------------------------
# otsu (kept numerically identical to the builder's so the two agree)
# ----------------------------------------------------------------------
def otsu_threshold(values: np.ndarray) -> float:
    """Otsu threshold on a 1-D float array. NaN-safe; NaN if too few values."""
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size < 2:
        return float("nan")
    hist, edges = np.histogram(v, bins=128)
    centers = 0.5 * (edges[:-1] + edges[1:])
    total = hist.sum()
    if total == 0:
        return float("nan")
    w = np.cumsum(hist) / total
    mu = np.cumsum(hist * centers) / total
    mu_t = mu[-1]
    between = (mu_t * w - mu) ** 2 / np.maximum(w * (1 - w), 1e-9)
    return float(centers[np.argmax(between)])


def db_drop_db(pre_db: np.ndarray, post_db: np.ndarray) -> np.ndarray:
    """Per-pixel backscatter change in dB: ``post - pre`` (negative = darker).

    Water flooding attenuates C-band/VH backscatter, so genuinely flooded pixels
    show a *negative* value here. dB arithmetic (a difference, not a ratio) is
    used because sigma-0 in dB is already log-scaled.
    """
    pre = np.asarray(pre_db, dtype=np.float32)
    post = np.asarray(post_db, dtype=np.float32)
    if pre.shape != post.shape:
        raise ValueError(f"shape mismatch: pre {pre.shape} vs post {post.shape}")
    with np.errstate(invalid="ignore"):
        return (post - pre).astype(np.float32)


# ----------------------------------------------------------------------
# event evidence
# ----------------------------------------------------------------------
@dataclass
class FloodEventHint:
    """Independent evidence that a flood happened somewhere, at a time.

    Sources: GDACS/EM-DAT style catalogues, or manual curation. Only the date
    and (optionally) a location are needed -- the pixel-level label is still
    derived from the imagery, this just tells us *which* scene pairs are worth
    building and stops us labelling arbitrary seasonal pairs as "flood".
    """

    event_id: str
    date: str                      # ISO yyyy-mm-dd
    lat: Optional[float] = None
    lon: Optional[float] = None
    label: Optional[str] = None
    source: Optional[str] = None

    def day(self) -> datetime:
        return datetime.strptime(self.date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _parse_acq(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class ScenePair:
    """A pre-event and post-event scene bracketting one flood event."""

    pre_name: str
    post_name: str
    pre_acq: datetime
    post_acq: datetime
    event: FloodEventHint
    overlap_frac: float = 0.0
    pre_bbox: Optional[Tuple[float, float, float, float]] = None
    post_bbox: Optional[Tuple[float, float, float, float]] = None

    @property
    def gap_days(self) -> float:
        return (self.post_acq - self.pre_acq).total_seconds() / 86400.0

    def chip_id(self, r0: int, c0: int) -> str:
        stem = self.post_name[2:] if self.post_name.startswith("S1") else self.post_name
        return f"{stem}_ev{self.event.event_id}_r{r0}_c{c0}"


def _bbox_overlap_frac(a: Sequence[float], b: Sequence[float]) -> float:
    """Fraction of the smaller box that intersects the other (0..1)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = max(1e-12, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1e-12, (bx1 - bx0) * (by1 - by0))
    return float(inter / min(area_a, area_b))


def _bbox_contains(bbox: Sequence[float], lon: float, lat: float) -> bool:
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def pair_scenes_for_event(
    scenes: Sequence[dict],
    event: FloodEventHint,
    max_gap_days: float = DEFAULT_MAX_PAIR_GAP_DAYS,
    max_pre_days: float = 45.0,
    min_overlap: float = 0.6,
) -> List[ScenePair]:
    """Find (pre, post) scene pairs that bracket ``event``.

    A scene qualifies as *post* when acquired from the event date up to
    ``max_pre_days`` later (flood water persists for days-weeks), and as *pre*
    when acquired between 3 days and ``max_pre_days`` before it. Pairs must
    overlap spatially by at least ``min_overlap`` of the smaller footprint.

    Returns pairs sorted by gap (shortest baseline first: a short baseline is a
    cleaner bracket because less non-flood change can accumulate).
    """
    ev_day = event.day()
    posts, pres = [], []
    for s in scenes:
        if "acquisition" not in s or "bbox" not in s or "name" not in s:
            continue
        acq = _parse_acq(s["acquisition"])
        bbox = tuple(s["bbox"])
        d_days = (acq.date() - ev_day.date()).days

        if 0 <= d_days <= max_pre_days:
            if event.lon is None or _bbox_contains(bbox, event.lon, event.lat):
                posts.append((acq, s, bbox))
        elif -max_pre_days <= d_days <= -3:
            if event.lon is None or _bbox_contains(bbox, event.lon, event.lat):
                pres.append((acq, s, bbox))

    pairs: List[ScenePair] = []
    for acq_p, pre, pb in pres:
        for acq_q, post, qb in posts:
            gap = (acq_q - acq_p).total_seconds() / 86400.0
            if gap <= 0 or gap > max_gap_days:
                continue
            ov = _bbox_overlap_frac(pb, qb)
            if ov < min_overlap:
                continue
            pairs.append(ScenePair(
                pre_name=pre["name"], post_name=post["name"],
                pre_acq=acq_p, post_acq=acq_q, event=event,
                overlap_frac=ov, pre_bbox=pb, post_bbox=qb,
            ))
    pairs.sort(key=lambda p: (p.gap_days, -p.overlap_frac))
    return pairs


# ----------------------------------------------------------------------
# labelling
# ----------------------------------------------------------------------
@dataclass
class LabelStats:
    """Counters describing one labelling run (all real pixel tallies)."""

    total_px: int = 0
    no_data_px: int = 0
    water_px: int = 0
    not_water_px: int = 0
    too_dark_px: int = 0
    chips: int = 0
    rejected_no_change: int = 0
    per_chip: List[dict] = field(default_factory=list)

    def merge(self, other: "LabelStats") -> "LabelStats":
        self.total_px += other.total_px
        self.no_data_px += other.no_data_px
        self.water_px += other.water_px
        self.not_water_px += other.not_water_px
        self.too_dark_px += other.too_dark_px
        self.chips += other.chips
        self.rejected_no_change += other.rejected_no_change
        self.per_chip.extend(other.per_chip)
        return self

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "per_chip"}
        d["water_frac"] = (self.water_px / self.total_px) if self.total_px else 0.0
        return d


def derive_change_labels(
    pre_db: np.ndarray,
    post_db: np.ndarray,
    min_drop_db: float = DEFAULT_MIN_DROP_DB,
    max_drop_db: float = DEFAULT_MAX_DROP_DB,
    min_water_frac: float = 0.001,
) -> Tuple[np.ndarray, dict]:
    """Derive canonical flood/water labels from a pre/post dB pair.

    Pixels whose backscatter dropped between ``min_drop_db`` and
    ``max_drop_db`` are labelled ``1`` (water); a drop beyond
    ``max_drop_db`` is treated as shadow/no-data (``-1``) rather than water,
    because extremely dark change is far more often radar shadow over forest or
    building than deep water. Pixels with no drop are ``0``.

    Returns ``(labels, info)`` where ``labels`` is int16 in ``{-1, 0, 1}``.
    """
    drop = db_drop_db(pre_db, post_db)
    pre = np.asarray(pre_db, dtype=np.float32)
    post = np.asarray(post_db, dtype=np.float32)

    valid = np.isfinite(pre) & np.isfinite(post) & np.isfinite(drop)

    labels = np.full(drop.shape, NOT_WATER, dtype=np.int16)
    water = valid & (drop <= min_drop_db) & (drop >= max_drop_db)
    too_dark = valid & (drop < max_drop_db)

    labels[water] = WATER
    labels[too_dark] = NO_DATA
    labels[~valid] = NO_DATA

    n_valid = int(valid.sum())
    info = {
        "total_px": int(drop.size),
        "valid_px": n_valid,
        "no_data_px": int((labels == NO_DATA).sum()),
        "water_px": int((labels == WATER).sum()),
        "not_water_px": int((labels == NOT_WATER).sum()),
        "too_dark_px": int(too_dark.sum()),
        "water_frac": float((labels == WATER).mean()) if drop.size else 0.0,
        "min_drop_db": float(np.nanmin(drop[valid])) if n_valid else float("nan"),
        "max_drop_db_observed": float(np.nanmax(drop[valid])) if n_valid else float("nan"),
        "median_drop_db": float(np.nanmedian(drop[valid])) if n_valid else float("nan"),
    }
    info["meets_min_water"] = bool(info["water_frac"] >= min_water_frac)
    return labels, info


def refine_threshold_from_reference(
    pre_db: np.ndarray,
    post_db: np.ndarray,
    reference_water: np.ndarray,
    min_drop_db: float = DEFAULT_MIN_DROP_DB,
    max_drop_db: float = DEFAULT_MAX_DROP_DB,
    bins: int = 96,
) -> Tuple[float, dict]:
    """Pick the drop threshold that best separates *known* flood from non-flood.

    ``reference_water`` is an expert delineation (e.g. an EOS-RS/ARIA-SG flood
    proxy map) resampled onto the pre/post pair's grid. This is how the module
    is calibrated against published ground truth rather than against a guess.

    Returns ``(min_drop_db, report)`` where ``report`` records the achieved
    separation, so calibration quality is auditable rather than assumed.
    """
    drop = db_drop_db(pre_db, post_db)
    ref = np.asarray(reference_water).astype(bool)
    if ref.shape != drop.shape:
        raise ValueError(f"shape mismatch: drop {drop.shape} vs ref {ref.shape}")
    valid = np.isfinite(drop) & np.isfinite(np.asarray(pre_db, dtype=np.float32)) \
        & np.isfinite(np.asarray(post_db, dtype=np.float32))

    if not valid.any() or not ref[valid].any() or (~ref[valid]).sum() == 0:
        return min_drop_db, {"calibrated": False, "reason": "no usable reference pixels"}

    d = drop[valid]
    r = ref[valid]
    flood = d[r]
    nonflood = d[~r]

    edges = np.linspace(np.nanmin(d), np.nanmax(d), bins + 1)
    if not np.isfinite(edges).all() or edges[-1] <= edges[0]:
        return min_drop_db, {"calibrated": False, "reason": "degenerate drop range"}

    best_t, best_iou = min_drop_db, -1.0
    for i in range(1, bins):
        thr = float(edges[i])
        pred = d <= thr
        inter = float((pred & r).sum())
        union = float((pred | r).sum())
        iou = inter / union if union else 0.0
        if iou > best_iou:
            best_iou, best_t = iou, thr

    report = {
        "calibrated": True,
        "threshold_db": best_t,
        "best_iou_vs_reference": best_iou,
        "n_flood_px": int(r.sum()),
        "n_nonflood_px": int((~r).sum()),
        "flood_drop_median_db": float(np.median(flood)),
        "nonflood_drop_median_db": float(np.median(nonflood)),
        "flood_drop_p10_db": float(np.percentile(flood, 10)),
        "flood_drop_p90_db": float(np.percentile(flood, 90)),
        "separation_db": float(np.median(nonflood) - np.median(flood)),
    }
    if not (best_t <= max_drop_db):
        report["clamped_to_max_drop_db"] = bool(best_t > max_drop_db)
    return float(best_t), report


# ----------------------------------------------------------------------
# agreement scoring against published expert delineations
# ----------------------------------------------------------------------
@dataclass
class Agreement:
    """Pixel agreement between a derived label and an expert reference."""

    name: str
    event: str
    sensor: str
    iou: float
    dice: float
    precision: float
    recall: float
    ref_water_px: int
    pred_water_px: int
    ref_only_px: int      # expert says flood, we missed it (under-segmentation)
    pred_only_px: int     # we say flood, expert does not (over-segmentation)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def score_against_reference(
    labels: np.ndarray,
    reference: np.ndarray,
    name: str = "",
    event: str = "",
    sensor: str = "",
    ignore_no_data: bool = True,
) -> Agreement:
    """Score canonical labels against a boolean expert reference.

    ``-1`` no-data is excluded from every metric by default: counting it as
    "correctly not-water" would silently inflate accuracy wherever the expert map
    has no coverage.
    """
    lab = np.asarray(labels)
    ref = np.asarray(reference).astype(bool)
    if lab.shape != ref.shape:
        raise ValueError(f"shape mismatch: labels {lab.shape} vs ref {ref.shape}")

    if ignore_no_data:
        valid = lab != NO_DATA
    else:
        valid = np.ones(lab.shape, dtype=bool)

    pred = (lab == WATER) & valid
    truth = ref & valid
    n_pred, n_true = int(pred.sum()), int(truth.sum())

    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())

    iou = tp / (tp + fp + fn) if (tp + fp + fn) else 0.0
    dice = (2 * tp) / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    prec = tp / n_pred if n_pred else 0.0
    rec = tp / n_true if n_true else 0.0

    return Agreement(
        name=name, event=event, sensor=sensor,
        iou=float(iou), dice=float(dice), precision=float(prec), recall=float(rec),
        ref_water_px=n_true, pred_water_px=n_pred,
        ref_only_px=fn, pred_only_px=fp,
    )


def aggregate_agreement(agreements: Sequence[Agreement]) -> dict:
    """Mean/median agreement plus the two failure modes that matter.

    ``mean_ref_only_frac`` is under-segmentation (missing real flood),
    ``mean_pred_only_frac`` is over-segmentation (inventing flood). Reporting
    both separately is what makes an aggregate score interpretable.
    """
    if not agreements:
        return {"n": 0}
    ref_only = np.array([a.ref_only_px for a in agreements], dtype=float)
    pred_only = np.array([a.pred_only_px for a in agreements], dtype=float)
    ref_tot = np.array([max(1, a.ref_water_px) for a in agreements], dtype=float)
    pred_tot = np.array([max(1, a.pred_water_px) for a in agreements], dtype=float)
    return {
        "n": len(agreements),
        "mean_iou": float(np.mean([a.iou for a in agreements])),
        "median_iou": float(np.median([a.iou for a in agreements])),
        "mean_dice": float(np.mean([a.dice for a in agreements])),
        "mean_precision": float(np.mean([a.precision for a in agreements])),
        "mean_recall": float(np.mean([a.recall for a in agreements])),
        "mean_ref_only_frac": float(np.mean(ref_only / ref_tot)),
        "mean_pred_only_frac": float(np.mean(pred_only / pred_tot)),
        "total_ref_water_px": int(sum(a.ref_water_px for a in agreements)),
        "total_pred_water_px": int(sum(a.pred_water_px for a in agreements)),
    }
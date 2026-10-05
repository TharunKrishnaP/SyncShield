# Flood dataset research sweep (October 2026)

Question: can we train the SAR flood U-Net on an **existing published dataset**
instead of building one, while keeping it **real, 2025-2026 and pan-India**?

Short answer: **no published dataset satisfies 2025-2026 + India + pixel labels.**
This file records what was checked, what each source actually provides, and the role
each one can honestly play. All figures below were verified against the live sources
on 2026-10-05, not recalled.

## The binding constraint

There is **no public labelled flood dataset for India covering 2025 or 2026** — not
SAR, not optical, not event metadata. Every credible source tops out at 2020-2023.
Therefore **2025-2026 labels must be derived from the imagery itself**. That is
forced, not a preference, and it should be stated plainly in the paper rather than
papered over.

Given that, the useful question becomes: *which existing datasets can (a) tell us
where real recent floods happened, and (b) let us prove our derived labels are
accurate?*

## Sources evaluated

### 1. Copernicus EMS Rapid Mapping — **0 India activations** (rejected)

Enumerated the full public activation catalogue via the documented endpoint
`https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/`.

| Metric | Value |
|---|---|
| Public activations | **266** |
| By event year | 2023: 54, 2024: 69, 2025: 69, 2026: 73 |
| Distinct countries | **69** |
| **Activations with India** | **0** |
| India flood activations 2025-2026 | **0** |

Verified three independent ways — the `countries` field, a regex over activation
names, and a centroid-inside-India-bbox test. All three return zero. The service is
EU-response oriented (Greece 53, Spain 32, Germany 20, Italy 19); the nearest
neighbours are Nepal, Sri Lanka, Pakistan and Myanmar. Older Indian activations
(e.g. Assam 2013) exist historically but are absent from the API, which starts at 2023.

**Verdict: unusable for India.** This was the pillar of an earlier draft plan and it
does not exist. Do not re-propose it without new evidence.

### 2. EOS-RS / ARIA-SG flood proxy maps on HDX — **adopted, as validation only**

Expert SAR-derived flood delineations for real Indian events, **CC-BY**, anonymous
download. Full audit in [`validation_assets_india.md`](validation_assets_india.md).

- 7 HDX packages, 14 GeoTIFFs, all EPSG:4326, ~26-31 m, binary 0/1
- **7 usable Sentinel-1 masks, 13,414,471 water pixels, 11,479.5 km²**, across
  **5 distinct real flood events** (2019-09 Bihar, 2020-07 Assam P114/P143,
  2022-05, 2022-06, 2023-07 Delhi NCR)
- Plus 3 ALOS-2 masks (18,593.9 km²) usable as secondary reference
- **Trap found:** 4 of the 14 published masks contain **zero** delineated water.
  A version-aware download plus a non-zero-water-pixel assertion is required,
  otherwise validation scores every prediction as a false positive.

Events end **2023-07**, so these are *not* training labels (that would re-introduce
the exact staleness the reviewer objected to). They are the **external accuracy
reference** for our derived 2025-2026 labels.

### 3. INDOFLOODS (Zenodo 14584655) — event catalogue, not labels

Downloaded and audited locally (`F:\floodml\indofloods\`).

| Property | Measured |
|---|---|
| Flood events | 4,548 across 155 gauges |
| Event date range | 1965-07-21 → **2020-09-24** |
| Peak discharge present | 87.8% |
| Flood volume present | 87.3% |
| Flood / Severe Flood | 2,919 / 1,629 |
| Gauge metadata | 214 (155 used), all with lat/lon |
| Reliability flags | 186 Safe, 28 Caution, 59 Restricted (privacy) |
| States | **15**, peninsular-weighted (Karnataka 1,496 · Maharashtra 817 · Kerala 531) |
| Median events/gauge | 10 (max 419) |

CC-BY-4.0, ~2.2 MB, anonymous. Citation: Kuntla & Saharia (2025), *BAMS* 106(2)
E333-E343, doi:10.1175/BAMS-D-24-0008.1.

**Two disqualifying properties for our purpose:** it stops in 2020, and it has **no
pixels** — point gauge records against official warning/danger levels. Also, the
public version **excludes Ganga and Brahmaputra** basin data (confirmed in both the
Zenodo record and the BAMS paper); the supplement is requestable from the authors
but would still end pre-2021.

**Verdict: not a segmentation label source.** Useful only as flood-prone basin
prior knowledge and severity context for the forecasting side.

### 4. India Flood Inventory / IFI-Impacts (Zenodo 4742142 → record 16994648) — partially usable

Best India-specific geospatial flood source found: IMD-sourced events with manual
digitisation, **1967-2023**, plus district flooded area and a District Flood Severity
Index. CC-BY-NC-4.0, published 2025-08-29. Files: `India_Flood_Inventory_v3.csv`,
`District_FloodImpact.csv`, `District_FloodedArea.csv`, `DFSI.csv`.

**Blocked:** Zenodo returned **HTTP 403 on every file-content route** (metadata API
still 200), so the CSVs are not yet on disk. Retry later. Even when retrieved it ends
**2023**, so it informs basin/severity priors, not 2025-26 labels. Note the **NC**
licence — non-commercial.

### 5. WorldFloods / ML4Floods — rejected for this task

509 flood events worldwide, labels curated from Copernicus EMS and UNOSAT (i.e.
genuinely human-curated — the label quality Sen1Floods11's weak labels lack).
Available on HuggingFace (`tacofoundation/worldfloods`) and a GCS bucket.

Rejected because it is **Sentinel-2 optical** (not SAR, so it cannot supervise a SAR
model), **CC-BY-NC-4.0**, and events run to 2023. Its label-curation *method* is
worth citing as precedent, but the pixels are the wrong sensor and the wrong era.

### 6. Others checked and set aside

| Source | Why not |
|---|---|
| NASA MODIS/VIIRS NRT flood (`MCDWD_L3` 2003-2025 + NRT from Jan 2026) | Real and current, but 250 m optical — far too coarse for a ~31 m SAR U-Net; regional sanity check only |
| Global Flood Database (Cloud to Street) | MODIS, events to 2018; CC-BY-NC-ND |
| Sentinel-1 "successor to Sen1Floods11" | **None found.** No 2025-2026 SAR flood segmentation benchmark exists |
| NRSC/Bhuvan flood layers, CWC, India WRIS, National Water Portal | Gauge/forecast text and map renderings; no machine-readable delineations found |
| EM-DAT, GDACS | Event metadata only, no spatial delineation — but still useful for *selecting* 2025-2026 event dates/locations |

## Resulting design

| Role | Source | Why |
|---|---|---|
| Imagery | **CDSE Sentinel-1 GRD, 2025-2026, pan-India** | Real, recent, 2,665 scenes enumerated, 762/763 districts — this is the asset that satisfies the requirement |
| Labels | **Derived: pre/post-event SAR change detection**, minus permanent water | Only option for 2025-26; change detection distinguishes *flood* from merely *water*, unlike scene-level Otsu |
| Where to look | Recent event catalogues (GDACS / EM-DAT) | Supplies real, dated 2025-2026 flood locations to aim the change detection |
| **Validation** | **EOS-RS/ARIA-SG India FPMs** (11,479.5 km², 5 events) | Published expert SAR delineations; measures whether our derived labels are accurate |
| Basin priors | INDOFLOODS, IFI-Impacts | Flood-prone basins and severity context; ends 2020/2023, never a pixel label |

## The honest claim

We cannot say "trained on a recent labelled dataset", because none exists. We can
say:

> Trained on real 2025-2026 pan-India Sentinel-1 (2,665 scenes, 762/763 districts).
> Labels derived by pre/post-event SAR change detection. Label accuracy externally
> validated against published expert SAR flood delineations for real Indian events.

Recent, real, and checkable — which is what the reviewer was actually asking for.

## Reproducing this audit

- Validation assets: `python ml/evidence/make_validation_summary.py`
- EMS enumeration: `GET https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/`
- INDOFLOODS audit: local CSVs under `F:\floodml\indofloods\`
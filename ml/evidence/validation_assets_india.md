# India SAR Flood Validation Assets (external, published)

Expert-produced, SAR-derived flood delineations for **real Indian flood events**,
published by the Earth Observatory of Singapore Remote Sensing Lab (EOS-RS / ARIA-SG)
on the Humanitarian Data Exchange under **CC-BY**.

These are the **external validation reference** for our automatically derived
2025-2026 change-detection labels. They are deliberately **not** used as training
labels: the newest available India event is 2023, so training on them would
re-introduce exactly the staleness the reviewer objected to in Sen1Floods11.

Regenerate with `python ml/evidence/make_validation_summary.py`.

## Provenance

- **2019-07** - HDX 07efed3d-a4ef-49ec-bda7-3d2d2d3fabfe - 1 raster(s), 0.0 km2 mapped water - <https://data.humdata.org/dataset/07efed3d-a4ef-49ec-bda7-3d2d2d3fabfe>
- **2019-09** - HDX 8369df7b-1960-4d51-8cd5-7d2109f5a8c2 - 1 raster(s), 4,541.3 km2 mapped water - <https://data.humdata.org/dataset/8369df7b-1960-4d51-8cd5-7d2109f5a8c2>
- **2020-07** - HDX fba47b60-11ad-4929-b264-1d026f8f53f5 - 2 raster(s), 2,596.5 km2 mapped water - <https://data.humdata.org/dataset/fba47b60-11ad-4929-b264-1d026f8f53f5>
- **2022-05** - HDX 5d465398-a93c-4f11-b85a-d6ed6ae15274 - 1 raster(s), 1,318.2 km2 mapped water - <https://data.humdata.org/dataset/5d465398-a93c-4f11-b85a-d6ed6ae15274>
- **2022-06** - HDX 1b40edc8-0a30-407b-be3c-7111e8e7c7f2 - 2 raster(s), 3,915.3 km2 mapped water - <https://data.humdata.org/dataset/1b40edc8-0a30-407b-be3c-7111e8e7c7f2>
- **2022-10** - HDX a3f64d27-af15-4244-967c-beaa297a54e4 - 4 raster(s), 15,898.2 km2 mapped water - <https://data.humdata.org/dataset/a3f64d27-af15-4244-967c-beaa297a54e4>
- **2023-07** - HDX b6f950a2-1b8f-4e55-8b32-00115f08f9e8 - 3 raster(s), 1,803.9 km2 mapped water - <https://data.humdata.org/dataset/b6f950a2-1b8f-4e55-8b32-00115f08f9e8>

## Per-raster audit

| raster | event | sensor | region | res (m) | water px | % water | flood km2 |
|---|---|---|---|---|---|---|---|
| `EOS-RS_20221014_FPM_A2_India_Floods_v0.5.tif` | 2022-10 | ALOS-2 | India (unnamed AOI) | 26.3 | 18,876,150 | 6.813 | 11,769.8 |
| `EOS_ARIA-SG_20190930_FPM_India_Floods_v0.1_TIFF.tif` | 2019-09 | Sentinel-1 | India (unnamed AOI) | 30.9 | 5,271,628 | 7.374 | 4,541.3 |
| `EOS-RS_20221015_FPM_A2_India_Floods_v0.5.tif` | 2022-10 | ALOS-2 | India (unnamed AOI) | 26.8 | 6,542,726 | 3.377 | 4,128.4 |
| `EOS-RS_20220622_FPM_A2_India_Floods_v0.4_TIFF.tif` | 2022-06 | ALOS-2 | India (unnamed AOI) | 26.4 | 4,298,448 | 1.45 | 2,695.7 |
| `EOS_ARIA-SG_20200715_FPM_India_Floods_P143_v0.7_TIFF.tif` | 2020-07 | Sentinel-1 | P143 swath | 30.9 | 2,281,824 | 9.858 | 1,942.2 |
| `EOS-RS_20230712_FPM_S1_India_NewDelhi_Floods_v0.9.tif` | 2023-07 | Sentinel-1 | Delhi NCR | 30.9 | 1,800,050 | 9.255 | 1,511.9 |
| `EOS-RS_20220518_FPM_S1_India_Floods_v0.4_TIFF.tif` | 2022-05 | Sentinel-1 | India (unnamed AOI) | 30.9 | 1,528,260 | 2.4 | 1,318.2 |
| `EOS-RS_20220621_FPM_S1_India_Floods_v0.3_TIFF.tif` | 2022-06 | Sentinel-1 | India (unnamed AOI) | 30.9 | 1,422,240 | 2.96 | 1,219.6 |
| `EOS_ARIA-SG_20200713_FPM_India_Floods_P114_v0.7_TIFF.tif` | 2020-07 | Sentinel-1 | P114 swath | 30.9 | 762,892 | 11.657 | 654.3 |
| `EOS-RS_20230712_FPM_S1_India_NewDelhi_Floods_v0.4.tif` | 2023-07 | Sentinel-1 | Delhi NCR | 30.9 | 347,577 | 1.31 | 292.0 |
| `EOS-RS_20221015_FPM_S1_India_Floods_v0.5.tif` | 2022-10 | Sentinel-1 | India (unnamed AOI) | 30.9 | 0 | 0.0 | 0.0 |
| `EOS-RS_20221016_FPM_S1_India_Floods_v0.5.tif` | 2022-10 | Sentinel-1 | India (unnamed AOI) | 30.9 | 0 | 0.0 | 0.0 |
| `EOS-RS_20230712_FPM_S1_India_NorthernHaryana_Floods_v0.4.tif` | 2023-07 | Sentinel-1 | N Haryana | 30.9 | 0 | 0.0 | 0.0 |
| `EOS_ARIA-SG_20190715_FPM_India_Bangladesh_Floods_v1.0.tif` | 2019-07 | Sentinel-1 | India/Bangladesh border | 27.4 | 0 | 0.0 | 0.0 |

## Totals

- Rasters audited: **14** (11 Sentinel-1, 3 ALOS-2), all EPSG:4326, all inside the India bounding box (14/14)
- Non-empty Sentinel-1 masks: **7** rasters, **13,414,471 water pixels**, **11,479.5 km2**
- Non-empty ALOS-2 masks: **3** rasters, **29,717,324 water pixels**, **18,593.9 km2**
- Distinct real flood events with usable Sentinel-1 extent: **5**
- Equivalent fully-water 256 px (~7.9 km) validation chips: **~181**

### Caveat: 4 published masks contain no delineated water

Not every EOS-RS release ships an actual delineation - some are empty rasters
(0 water pixels). These must be excluded from ground truth, or validation will
silently score every prediction as a false positive:

- `EOS-RS_20221015_FPM_S1_India_Floods_v0.5.tif` (2022-10, Sentinel-1, India (unnamed AOI)) - **0 water px**
- `EOS-RS_20221016_FPM_S1_India_Floods_v0.5.tif` (2022-10, Sentinel-1, India (unnamed AOI)) - **0 water px**
- `EOS-RS_20230712_FPM_S1_India_NorthernHaryana_Floods_v0.4.tif` (2023-07, Sentinel-1, N Haryana) - **0 water px**
- `EOS_ARIA-SG_20190715_FPM_India_Bangladesh_Floods_v1.0.tif` (2019-07, Sentinel-1, India/Bangladesh border) - **0 water px**

Where a higher-version sibling exists, use that instead:

- `..._NewDelhi_Floods_v0.9.tif` (1,800,050 water px) supersedes `..._NorthernHaryana_Floods_v0.4.tif` (0)
- `EOS_ARIA-SG_20200715_..._P143_v0.7.tif` (2,281,824 water px) is the usable one; `P114_v0.7` (762,892) is also usable
- `EOS_ARIA-SG_20190715_..._v1.0.tif` and the Oct 2022 **Sentinel-1** pair have no usable sibling and must simply be dropped

The download step must therefore be version-aware and must assert a non-zero
water-pixel count per mask before a raster is admitted as ground truth.

### Caveat: recency

Events span **2019-07 to 2023-07**. This asset validates *label quality* (do our
automatically derived 2025-2026 masks agree with expert SAR delineations?), it does
**not** supply 2025-2026 labels. No published labelled flood dataset for India
covering 2025-2026 exists - see `ml/evidence/dataset_research_2026.md`.

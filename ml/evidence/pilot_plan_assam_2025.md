# Pilot plan — Assam / Brahmaputra, 2025 monsoon (GFM labels + Sentinel-1)

Status: **planned, not executed.** No data has been downloaded. Every number
below comes from anonymous STAC *metadata* queries against the live catalogues
(Microsoft Planetary Computer for Sentinel-1, EODC STAC for GFM) — no pixels.

## Why this AOI and source
GFM is the only operational product that pairs real flood labels with India in
2025–2026. Its data plane is credential-free (anonymous STAC + file reads), so
the pipeline needs no account. See `dataset_research_2026.md` for why the
published labelled datasets (GEOID-Flood, ImpactMesh-Flood, Sen1Floods11) do
not cover India in this window.

- AOI bbox (lon,lat): `89.5, 25.0, 95.5, 27.5`
- Window: `2025-07-01 .. 2025-09-30`
- Canonical labels: `-1` no-data / `0` not-water / `1` water
- Label source: GFM `ensemble_flood_extent` (flood mode), permanent water
  removed via `reference_water_mask`

## Feasibility (metadata-only evidence)
| Catalogue | Query | Result |
|---|---|---|
| MPC Sentinel-1 GRD | AOI × Jul–Sep 2025 | ≥200 scenes (limit hit), 49 distinct dates |
| EODC GFM | AOI × Jul–Sep 2025 | 722 items, 76 distinct dates |
| both | intersection | **43 dates are both imaged and labelled** |

## Selecting the flood peak without downloading pixels
GFM STAC items carry `flooded_pixels` / `floodable_pixels` in `properties`, so
the peak can be ranked from metadata. Top dates over the AOI:

| date | flooded km² | GFM tiles | all-3-algorithm agreement |
|---|---|---|---|
| **2025-08-04** | ~13,990 | 11 | 11/11 |
| 2025-07-16 | ~12,703 | 6 | 6/6 |
| **2025-08-06** | ~12,239 | 20 | 20/20 |
| 2025-07-28 | ~11,122 | 6 | 6/6 |
| **2025-08-16** | ~7,915 | 11 | 11/11 |

(`flooded_pixels × 20 m × 20 m` over all tiles returned for the AOI; a relative
ranking, since a T3 tile extends past the AOI.)

## Proposed pilot scenes (3)
Pick one scene per date, on dates with both imagery and labels:

1. **2025-08-04** — flood peak
2. **2025-08-06** — broad coverage (20 tiles)
3. **2025-08-16** — receding limb

MPC returned exactly its 200-item limit for the window, so the specific scene
per date is resolved at run time by `download-sar-mpc` (which searches fresh).

## Commands (all data to `F:`, nothing to `C:`)
```powershell
$SAR  = "F:\floodml\pilot\sar"
$LBL  = "F:\floodml\pilot\labels_gfm"
$GFMC = "F:\floodml\pilot\gfm_tiles"
$DEM  = "F:\floodml\pilot\dem"
$CHIP = "F:\floodml\pilot\chips"
$BBOX = "89.5,25.0,95.5,27.5"

# 1) imagery (one scene per pilot date) ~1.3 GB/scene VV+VH
foreach ($d in "2025-08-04","2025-08-06","2025-08-16") {
  python ml/sar/build_india_2025_2026.py download-sar-mpc --out $SAR `
    --bbox $BBOX --start "${d}T00:00:00Z" --end "${d}T23:59:59Z" --max-scenes 1
}

# 2) GFM labels aligned to each scene grid (a few MB)
python ml/sar/build_india_2025_2026.py gfm-labels --sar-dir $SAR `
  --out $LBL --cache-dir $GFMC --mode flood

# 3) chips (GFM labels preferred; Otsu fallback where a label is absent)
python ml/sar/build_india_2025_2026.py chips --sar-dir $SAR --dem-dir $DEM `
  --label-dir $LBL --out $CHIP

# 4) 3-epoch CPU smoke train -> a NEW artifact dir (live model untouched)
python ml/sar/build_india_2025_2026.py train --data-dir $CHIP `
  --out ml/artifacts/sar_unet_pilot --epochs 3
```

## Expected footprint
| item | size |
|---|---|
| 3 × Sentinel-1 scenes (VV+VH measurement + calibration XML) | ~4 GB |
| GFM label tiles (5 layers/tile, cached) | < 100 MB |
| chips | tens of MB |
| **total** | **~4–5 GB on `F:`** |

## Definition of done for the pilot
1. Chips carry canonical `{-1,0,1}` GFM labels (assert water pixels present).
2. A 3-epoch train produces finite loss and non-zero `val_iou`.
3. **Real** IoU scored against the 7 usable ARIA expert masks
   (`F:\floodml\validation\aria_sg_extracted\`, out-of-year generalisation —
   train on 2025, test on the 2019–2023 ARIA events).
4. Only then decide whether to scale to ~24 scenes / Colab T4.

## Explicit stop points
- Stop after (1) if the labels look wrong.
- Stop after (2) if `val_iou` is ~0 (pipeline bug, not model quality).
- Do **not** run the `train` stage without `--out` (it defaults to the live
  `ml/artifacts/sar_unet`; the CLI now defaults to a separate dir to be safe).
- Promote a model to live only via `ML_SAR_DIR` + mtime hot-reload.

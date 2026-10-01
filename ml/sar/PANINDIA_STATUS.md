# Pan-India 2025-2026 SAR U-Net dataset — progress checkpoint (resume here)

Last updated: session resume point. Read this file first, then the headline
numbers in `ml/data/india_2025_2026/manifest.json` (gitignored) and the builder
`ml/sar/build_india_2025_2026.py`.

## DONE

- **Data sources verified live** (anonymous where possible):
  - Copernicus Data Space **OData browse** works anonymously → real 2025-2026
    Sentinel-1 GRD scene enumeration over any Indian bbox.
  - **Copernicus GLO-30 DEM** (AWS Open Data) downloads anonymously.
  - **CDSE anonymous *download* → HTTP 401** → SAR download requires a free
    CDSE account token (`CDSE_USER`/`CDSE_PASS`). This is the only blocker to
    full training.
- **`ml/sar/build_india_2025_2026.py`** — the real-data pan-India builder.
  Stages: `enumerate` (anon), `download-dem` (anon), `download-sar` (token),
  `chips`, `train`, `selftest`. Key fixes along the way: OData filter =
  `Collection/Name eq 'SENTINEL-1'` + `ContentDate/Start` window + footprint
  intersect (fast, ~3 s/page); `parse_scene` uses `GeoFootprint` GeoJSON +
  `ContentDate.Start`; SAR calibration is the S1 spec formula σ⁰=DN²/A²;
  chip ids strip the leading "S1" so `train_unet.py`'s label matcher pairs
  them (`chip_id_for`).
- **`ml/sar/train_unet.py`** — hardened `collect()` label candidates (added
  `name.replace("S1Hand","LabelHand")` as first candidate).
- **REAL enumeration complete** — `ml/data/india_2025_2026/manifest.json` +
  `district_coverage.csv`:
  - **2,665 real S1 scenes, acquisitions strictly 2025-01-01..2026-12-31**
    (2025: 1,474 / 2026: 1,191; platforms S1A 2,533 / S1C 65 / S1D 67).
  - **762/763 districts covered (99.87%)**; flood-prone 352/352.
  - **Only gap: Lakshadweep** (centroid 72.6358,10.5593 — a small coral
    archipelago; 12 paged query passes found 0 scene footprints containing the
    centroid, i.e. genuinely in an orbital swath gap; not flood-prone).
    Honest, documented limitation.
- **REAL DEM downloaded** — 15 Copernicus GLO-30 tiles over Assam
  (`ml/data/india_2025_2026/dem/`, 671 MB, verified: 0–2,774 m).
- **Tests** — `tests/test_panindia_dataset_builder.py` added
  (parse/filter/labels/calibration/chip-glue + on-disk manifest audit).
  13 passed (+ no-synthetic guard) / 3 skipped **before** the manifest existed
  → re-run now that the manifest is on disk; those 3 should pass and stay green.
- **Committed locally**: `d288baf` "P2 river dataset builder: load real CWC
  gauge registry, fix LSTM 3D-vs-flat split" (not yet pushed).
- **Services restarted** via `start_demo.ps1`: backend :8000 healthy
  (763 zones, 6 live sources), frontend :5173 (HTTP 200). NOTE: a later
  `/api/ai/models` and `/api/ai/classify` call **timed out** → re-verify
  (likely first-load torch warm-up or load; not yet re-checked).

## PENDING (in order)

1. Run `python ml/evidence/make_panindia_summary.py` → writes committed
   `ml/evidence/panindia_2025_2026.md` from the live manifest.
2. Re-run `python -m pytest tests/test_panindia_dataset_builder.py -v`
   (the 3 skipped manifest tests should now run).
3. Fill REAL numbers into `ALGORITHMS.md` §5.3 (currently has placeholders
   "N scenes / M of 763 (P%)") → 2,665 scenes / 762 of 763 (99.87%) / 352/352
   flood-prone / Lakshadweep note. Also add a row/note in `ml/README.md` and
   `ml/EVIDENCE_SHEET.md` documenting the 2025-2026 pan-India retraining dataset.
4. Commit the pan-India work: `ml/sar/build_india_2025_2026.py` (new),
   `ml/sar/train_unet.py` (modified), `tests/test_panindia_dataset_builder.py`
   (new), `ml/evidence/make_panindia_summary.py` + generated md (new),
   `ALGORITHMS.md` (+README/EVIDENCE_SHEET edits). Check/ignore
   `ml/sar/enumerate_all.log` before committing.
5. Re-verify demo endpoints after the commit (`/api/ai/models`,
   `/api/ai/classify`, `POST /api/ai/sar/ingest` with existing artifacts).
6. **USER DECISION NEEDED** — actually train the U-Net on the 2025-2026 data:
   real Sentinel-1 download requires a free Copernicus Data Space account.
   Pipeline is ready:
   `download-sar --scene <name> --cdse-user U --cdse-pass P` →
   `chips --sar-dir ... --dem-dir ...` → `train --data-dir .../chips`.
   Ask user for CDSE credentials (recommended) or NRSC NDEM flood-mask access
   (would upgrade weak Otsu labels to official flood maps).
7. Optional: push commits (`git push` after final commit + E2E checks).

## Useful commands

- `python ml/sar/build_india_2025_2026.py selftest` — anonymous smoke test
- `python ml/sar/build_india_2025_2026.py download-dem --out ... --bbox lon0,lat0,lon1,lat1`
- `python ml/sar/build_india_2025_2026.py enumerate --out ml/data/india_2025_2026 --step-deg 2.5` (full re-sweep ~25-40 min, quiet by default)
- `python ml/evidence/make_panindia_summary.py`
# Pan-India 2025-2026 SAR U-Net dataset — progress checkpoint (resume here)

Last updated: user will free C: disk space and return with CDSE credentials.
Read this file first, then the headline numbers in
`ml/data/india_2025_2026/manifest.json` (gitignored) and the builder
`ml/sar/build_india_2025_2026.py`.

## DONE (committed + pushed)

- **Everything up to the SAR download is committed and pushed** on `main`
  (HEAD `3dd93b4`; upstream `TharunKrishnaP/SyncShield`).
  - Builder `ml/sar/build_india_2025_2026.py`, hardened `train_unet.py`,
    tests `tests/test_panindia_dataset_builder.py` (**16/16 green** —
    includes the on-disk manifest audit, no synthetic data anywhere).
  - Evidence `ml/evidence/panindia_2025_2026.md` (committed) + real numbers
    in `ALGORITHMS.md` §5.3, `ml/README.md`, `ml/EVIDENCE_SHEET.md`.
- **REAL enumeration**: 2,665 S1 GRD scenes (2025: 1,474 / 2026: 1,191;
  S1A/S1C/S1D), **762/763 districts (99.87%)**, flood-prone **352/352**;
  only gap = Lakshadweep (swath gap, not flood-prone — documented).
- **REAL DEM**: 15 Copernicus GLO-30 tiles over Assam
  (`ml/data/india_2025_2026/dem/`, 671 MB, 0–2,774 m).
- **Live demo re-verified after restart** (backend PID
  `start_demo.ps1`, :8000 healthy zones=763 live=7; frontend :5173 200):
  `/api/ai/models` OK (text v2 + SAR U-Net resnet18 val_iou 0.2758),
  `/api/ai/classify` OK (earlier timeout was first-load),
  `/api/ai/sar/extents` OK (real ML extents in datalake).
- **Services are DOWN again** if a shell died — restart with:
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\start_demo.ps1`
  (execution policy blocks bare `.\start_demo.ps1`).

## BLOCKED (only remaining step — real SAR download + retrain)

- CDSE **anonymous download → HTTP 401**; needs a free Copernicus Data Space
  account (`CDSE_USER`/`CDSE_PASS` env or `--cdse-user/--cdse-pass` CLI).
  Never commit credentials. (`get_cdse_token` = OIDC password grant,
  `identity.dataspace.copernicus.eu`.)
- **Disk: only 6.9 GB free on C:** (the only drive) at last check. User will
  free space. Budget below assumes ~25 GB freed → ~32 GB total.

## RUN PLAN — when you return with token + free disk

1. Hand over creds (env vars: `$env:CDSE_USER=...; $env:CDSE_PASS=...`).
2. Confirm free space: `Get-PSDrive C`. Need ≥ ~20 GB for ~8-10 scenes,
   ≥ ~30 GB for the full ~12-scene basin set (see budget).
3. Pick scenes (manifest on disk): ~10 monsoon-2025 scenes, one per major
   flood basin (Brahmaputra/Assam — DEM already present; Ganga–Kosi/Bihar;
   Ganga/UP; Ganga/WB; Godavari; Krishna; Mahanadi/Odisha; Cauvery/TN;
   Kerala; Narmada) + **2 recent 2026 scenes as temporal holdout**. Use
   `ml/data/india_2025_2026/manifest.json` footprints to select scene IDs
   containing the target district HQs.
4. **Scene-by-scene to stay inside the disk budget** — for each scene:
   `download-sar --out ml/data/india_2025_2026/sar --scene <SAFE_name>`
   then **delete `sar/zips/<name>.zip` AND `sar/unzip/<name>/`** after
   calibration completes (calibrated `sar/<name>_VV.tif` / `_VH.tif` stay,
   ~2.3 GB/scene total). Steady-state ≈ 2.3 GB × n_scenes + working zip.
5. **Two-pass chips to keep the temporal holdout honest**
   (one-pass `--val-frac 0.2` would need all scenes present at once):
   - train pool (10 monsoon-2025 scenes only):
     `chips --out ml/data/india_2025_2026/chips --sar-dir .../sar --dem-dir .../dem --val-frac 0 --size 256 --stride 256`
   - val pool (the 2 recent-2026 scenes):
     `chips --out ml/data/india_2025_2026/chips --sar-dir .../sar --dem-dir .../dem --val-frac 1 --size 256 --stride 256`
   (`--val-frac 1` → cutoff at scenes[0] → everything lands in `HandLabeled/`
   = the loader's val partition; `--val-frac 0` → everything in
   `WeakLabeled/` = train. Same out dir accumulates both pools.)
   Check `chips_meta.json` stats: expect ~hundreds–thousands of water chips.
6. Retrain (does NOT clobber the live model — separate artifact dir):
   `python ml/sar/train_unet.py --data-dir ml/data/india_2025_2026/chips
   --size 256 --epochs 35 --pos-weight 8 --grad-clip 1.0
   --out ml/artifacts/sar_unet_2025_2026`
   (default `--out` is `ml/artifacts/sar_unet` = the LIVE Sen1Floods11 model
   the backend serves — keep it, only swap deliberately later).
   CPU: 35 epochs on ~1-5k chips = hours; run in background, monitor
   `ml/artifacts/sar_unet_2025_2026/meta.json` (IoU/Dice, chip count).
7. Commit: builder unchanged; new artifacts + `chips_meta.json` summary +
   updated numbers in `ALGORITHMS.md`/`EVIDENCE_SHEET.md`/`ml/README.md`.
   Consider wiring the live swap: point `backend/app/ml/sar_model.py` at the
   new `sar_unet_2025_2026` dir (config, not code, if possible).

## Budget (approx, per GRD IW scene)

| item | size |
|---|---|
| zip (deleted after unzip) | ~1.7 GB |
| unzipped SAFE (deleted after calibration) | ~4.5 GB |
| calibrated VV+VH tifs (kept until chips) | ~2.3 GB |
| GLO-30 DEM tile | ~45 MB, cached |

## Useful commands

- `python ml/sar/build_india_2025_2026.py selftest` — anonymous smoke test
- `python ml/sar/build_india_2025_2026.py download-dem --out ... --bbox lon0,lat0,lon1,lat1` (anonymous)
- `python ml/sar/build_india_2025_2026.py enumerate --out ml/data/india_2025_2026 --step-deg 2.5` (full re-sweep ~25-40 min)
- `python ml/evidence/make_panindia_summary.py`
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\start_demo.ps1` (restart services)
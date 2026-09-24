# FDR ML Workspace — Phase 1 (50%) deliverable

Trained-machine-learning layer for the Flood Disaster Response DataLake.
Phase 1 goal: **real, measured, integrated ML** for the two highest-value models,
with the third (river forecasting) scaffolded for Phase 2.

| Model | Status (Phase 1) | Artifacts | Metrics (see `artifacts/*/metrics.json`) |
|---|---|---|---|
| **D — incident text classifier** | ✅ Trained + live in backend | `artifacts/text_classifier/` | Gold (unseen hand-written set, n=59): accuracy **0.78**, macro-F1 **0.79** — see `EVIDENCE_SHEET.md` |
| **C — Sentinel-1 SAR flood U-Net** | 🔶 Pipeline complete + synthetic cert; full IoU training = Colab notebook | `artifacts/sar_unet/` (from Colab) | IoU on Sen1Floods11 held-out (reported in `meta.json`) |
| **A — river-level forecaster** | ⏳ Phase 2 (scaffold in `forecast/`) | — | NSE/MAE vs GloFAS baseline |
| **Learned fusion / calibration** | ⏳ Phase 2 (`fusion/` scaffold) | — | calibration vs. history lake |

## How each model was trained / tested (the "reviewer answers")

### 1. Incident text classifier (D)
- **Data**: weakly-supervised bilingual (English + romanized Hindi) corpus built in
  `text/build_corpus.py` from template phrasings for the 10 incident categories
  plus an `OTHER` class + a hand-written *gold* test set of realistic reports
  (never seen by training). Corpus stats: `artifacts/text_classifier/corpus_stats.json`.
- **Model**: TF-IDF (1-2 grams) → linear SVM, probability-calibrated
  (`CalibratedClassifierCV`). Trained with `python text/train_svc.py`.
- **Test**: stratified hold-out + the gold set; per-class precision/recall/F1 and
  confusion matrix in `artifacts/text_classifier/metrics.json`.
- **Upgrade path** (Phase 2): Distil-BERT / Indic-BERT fine-tune on Colab
  (`text/train_colab.ipynb`) + human-annotated corpora (CrisisMMD / humAID).
- **Integration**: `backend/app/ml/text_classifier.py` → called by
  `backend/app/ai_engine/nlp_extractor.py::extract_incident`.
  Regex extractor stays as fallback + location/severity extraction.

### 2. Sentinel-1 SAR flood U-Net (C)
- **Data**: Sen1Floods11 (cc-by-4.0) from the Hugging Face mirror
  `harshinde/sen1floods` — 4851 tiles, train/validation/test splits.
- **Model**: U-Net with a pretrained vision backbone (segmentation-models.pytorch),
  trained on the T4 (Colab notebook `sar/train_colab.ipynb`).
- **Test**: IoU on the Sen1Floods11 test split; the inference script
  `sar/infer.py` polygonises the water mask into GeoJSON extents for the map.
- **Local**: `sar/train_unet.py --mode synthetic` trains a few epochs on
  synthetic SAR-like tiles so the full train→infer→polygonise chain is certified
  on any machine (CI-safe); it is *not* a production model — the Colab notebook
  (`--mode sen1floods11`) produces the real IoU numbers.
- **Integration**: `backend/app/ml/sar_model.py` → scene ingest endpoint →
  `datalake` → `satellite_map` in the orchestrator (fills the 0.35 satellite
  weight with real ML extents instead of 0).

### 3. River forecaster (A) — Phase 2
`forecast/` scaffold: GloFAS-reanalysis-based dataset builder + LSTM/GBM
per-gauge trainer, backtest vs the live GloFAS baseline.

### 4. Learned fusion (Phase 2)
`fusion/` scaffold: fit the severity-index weights (0.35/0.20/0.20/0.15/0.10)
from history-lake outcomes instead of hand-picking; re-calibrate severity bands.

## Reproduce
```
python ml/text/build_corpus.py && python ml/text/train_svc.py   # D — reproducible in seconds
python ml/sar/train_unet.py --mode synthetic  # C — pipeline certification (no GPU)
# real U-Net: run sar/train_colab.ipynb on a free Colab T4
```
Measured results: `EVIDENCE_SHEET.md` (top of the mL workspace).
# Dashboard rebuild plan — clarity + defensibility ("worth 5 credits")

Goal: make the live system *legible* (what is real, what is trained, what is a
scaffold) and *defensible* (metrics with a real held-out test). Today the
dashboard works but its weight of evidence is unclear, and one live scoring
term is silently dead.

## What the code actually does today (audited)
- Backend: FastAPI; frontend: React/Vite.
- `backend/app/orchestrator.py` `refresh()` runs every 60 s and rebuilds the
  situation snapshot.
- Severity is a weighted sum
  (`backend/app/ai_engine/situation_scorer.py`, ~:144):
  `0.35·satellite + 0.20·rain + 0.20·river + 0.15·reports + 0.10·population`.
- Only **two** components have trained weights:
  1. SAR U-Net — `backend/app/ml/sar_model.py`, artifacts in
     `ml/artifacts/sar_unet` (trained on Sen1Floods11, `val_iou 0.2758`,
     `val_dice 0.3861`).
  2. Text classifier — `backend/app/ml/text_classifier.py` (TF-IDF + SVM,
     acc 0.9566, macro-F1 0.6042).
- Everything under `backend/app/ai_engine/*` is a deterministic heuristic — no
  learned weights.
- The U-Net is only reachable via `POST /api/ai/sar/ingest`
  (`backend/app/api/ai.py` ~:83).
- **The satellite term is dead in normal operation**: with
  `SIMULATION_ENABLED=False` and no ML extents ingested, `satellite_map` is
  empty, so `0.35` of every severity score is zero. This is the single biggest
  credibility leak.
- LSTM river forecast (`ml/artifacts/river_forecast`) and fusion
  (`ml/artifacts/fusion`) artifact dirs are absent → those are scaffolds.

## Principle
One rule drives the rebuild: **a viewer must never have to guess whether a
number is model output, an observed value, a heuristic, or simulated.** Every
term gets a provenance badge and, where a model is involved, its measured
metric.

## Concrete changes

### 1. Provenance / model-registry panel (new, always visible)
- Backend: expose a `/api/ai/provenance` payload built from each artifact's
  `meta.json` (model name, task, training dataset, trained_at, val_iou /
  val_dice, artifact path, mtime).
- Frontend: a compact panel showing each live model with a **green/amber/red**
  flag: green = trained on India 2025–2026, amber = legacy/other data, red =
  scaffold/absent (e.g. `river_forecast`, `fusion`).
- Effect: the current ambiguity — a stale Sen1Floods11 model silently serving
  the dashboard — becomes visible and, after the pilot, gets upgraded.

### 2. Fix (or honestly label) the satellite term
- Option A (preferred): wire ingested U-Net extents into the satellite term so
  `0.35` is real; show "N extents, model X, t=…".
- Option B (interim): when no extents exist, **renormalise** the remaining
  weights and display `satellite: inactive (0.35 redistributed)`.
- Either way the score stops silently understating severity by 35 %.

### 3. Visible AI trace (explainability, not a black box)
Show the chain a viewer can audit:
`report text → classifier → incident category` and
`SAR scene → U-Net → flood extent → satellite term → severity → national score`.
Each arrow displays the contributing value and its source.

### 4. Real-vs-simulated surfacing
- A first-class toggle/banner: **"Simulated"** vs **"Observed + Model"**,
  driven by `SIMULATION_ENABLED` and the count of ingested real extents.
- Per layer: observed (satellite/rain/river gauges), model (U-Net extents,
  text classes), heuristic (ai_engine), simulated.

### 5. Metrics page with a real held-out test
- Backend: `/api/ai/metrics` returning each model's `meta.json` metrics *and*
  the split used to produce them.
- The SAR model must report a **scene-level** holdout (no event in both train
  and val) — never a re-score of training data. Report IoU/Dice plus a
  confusion matrix.
- After the pilot: promote `ml/artifacts/sar_unet_2025_2026` live via
  `ML_SAR_DIR` (mtime hot-reload) and let the page show the new numbers.

## Why this is "worth 5 credits"
1. **Real, current data** — 2025–2026 India SAR extents, not simulated.
2. **Honest metrics** — a real scene-level held-out test, published on-screen.
3. **Provenance / auditability** — every number traceable to a source artifact.
4. **Correct scoring** — the dead 35 % satellite weight fixed or declared.
5. **Legibility** — trained ML vs heuristic vs scaffold is unmistakable.

## Sequencing (after the dataset is frozen)
1. `/api/ai/provenance` + `/api/ai/metrics` backend endpoints (pure reads of
   `meta.json`; zero risk to serving).
2. Frontend provenance panel + real-vs-simulated banner.
3. Satellite-term fix (Option B interim → Option A once extents flow).
4. AI-trace view.
5. Swap in the pilot/Colab model via `ML_SAR_DIR`; screenshot the new metrics.

Nothing here downloads data or trains a model; it is all wiring over existing
artifacts.

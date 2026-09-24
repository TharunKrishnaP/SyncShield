# Review 3 — Live Demo Script (15 marks)

Run once before the review; the flow below takes ~10 minutes.

## 0. Start (1 min)

```
cd backend   &&  python main.py          # → http://localhost:8000
cd frontend  &&  npm.cmd run dev         # → http://localhost:5173
```

Open `http://localhost:5173`. Backend is healthy at
`http://localhost:8000/api/health`.

## 1. The situation dashboard (3 min)

1. **Overview** — regional severity index, headline brief (plain-language AI
   output), critical/very-high zone counts.
2. **Zone scores** — click a zone: `evidence_breakdown` shows exactly how the
   0.35/0.20/0.20/0.15/0.10 weights + raw signal values produced the score
   (this *is* the explainability requirement).
3. **Map** — rain-radar overlay, live alerts (GDACS/EONET), simulated flood
   polygons in demo mode, layer toggles.
4. **Water levels** — GloFAS live discharge per river station.
5. **Priorities** — rescue-priority ranking with recommended action checklists
   (NDRF/SDRF deployment, evacuation radii, RED alerts).
6. **Conflicts panel** — data conflicts detected between independent signals.
7. **Data sources panel** — honest per-source status (LIVE / SIMULATED /
   NEEDS_KEY / UNAVAILABLE) with record counts.

## 2. Citizen report → trained ML classifier (2 min)

Submit a report in the UI (or):

```bash
curl -X POST http://localhost:8000/api/citizen/reports \
  -F "text=Ambulance stuck in water near Gandhi Ghat, Patna,
          road to the district hospital is flooded"
```

Response shows the category — and the incident stored in `/api/incidents`
carries `nlp_extracted.ml_classification` (model, method, confidence, top-3).

Then the live-model demos (backend):

```
GET  /api/ai/models     → D: available, corpus, gold acc 0.78 / macro-F1 0.79,
                          per-class F1, confusion list; C: artifacts + note
POST /api/ai/classify   → {"text": "..."} → {category, confidence, method, top3}
GET  /docs              → all endpoints, try them interactively
```

Three lines worth typing into `/api/ai/classify`:

| Text | Expected |
|---|---|
| `Ambulance stuck in water near Gandhi Ghat, Patna, road to hospital flooded` | HOSPITAL_ACCESS_BLOCKED @ ~0.99 |
| `gali me paani bhar gaya hai, gaadiyaan atki hui hain` | FLOODED_ROAD (Hinglish) |
| `Looking for a tiffin service near the office` | OTHER (non-incident) |

## 3. Routing & brief (1 min)

`/api/routing/evaluate` — flood-risk route comparison (direct vs alternative,
risk score, recommendation). `/api/brief` — AI-written national brief.

## 4. SAR U-Net — live flood-extent prediction (3 min)

Model C — trained on **real** Sen1Floods11 India data (467 weak-label train /
68 human-QC val, the dataset's own geographic split — no synthetic data).

Current artifacts (`ml/artifacts/sar_unet/meta.json`): real-data run on this
repo, **val IoU / val Dice** as measured on the 68 held-out hand-labeled chips
(see number in the models panel below).

1. **Models panel:** `GET /api/ai/models` → `sar_unet.available: true` with
   `val_iou`/`val_dice` from the real run, `mode: sen1floods11` and the
   honesty note (`ml/artifacts/sar_unet/meta.json`).
2. **Run inference:** upload the real Sentinel-1 demo scene to the trained U-Net:
   ```
   curl.exe -X POST http://localhost:8000/api/ai/sar/ingest ^
     -F "photo=@ml/data/sar_scenes/scene_india_assam.tif"
   ```
   → returns the extent record: zone **AS-Biswanath (Assam)**, `flood_area_km2`
   as predicted, `flood_status`, `confidence`, `flood_polygons`,
   `data_source: ML_SAR_UNET`.
3. **Inspected state:** `GET /api/ai/sar/extents` — count + zones + total area.
4. **On the dashboard:** the map renders the **ML prediction** for the Assam
   zone (polygon popup: *“ML U-Net Flood Extent (Sentinel-1) · Source: trained
   U-Net · confidence …”*). The orchestrator replaces the modelled/sim
   extent for covered zones with the `ML_SAR` output (sim skips those zones,
   ML extents are appended last so the frontend's per-zone dedupe keeps the
   model's result) — the zone's satellite evidence + severity reflect live
   model output, not just the scenario.
5. **Honesty slide:** the model is trained end-to-end on **real** Sentinel-1
   chips (Sen1Floods11 India event, 2016 Assam; public GCS bucket). Training
   uses the dataset's own split when the full download is present — 467
   weakly-labeled chips train + 68 hand-labeled chips (human QC) validate, so
   the reported val IoU is on labels the model never saw. On a data-cap
   constrained machine the loader falls back to a deterministic 85/15 chip-id
   hash split over the real chips on disk (the meta.json `note` records which
   split was used) — still held-out, still real data. No synthetic data is
   used anywhere. The
   demo scene is itself a real Sentinel-1 tile (`scene_india_assam.tif`,
   ~10 m/px, copied from the HandLabeled pool via `ml/sar/mk_real_scene.py`).
   Same code paths (`infer.py`, `sar_model.py`) serve it unchanged
   — the backend hot-reloads new artifacts by file mtime, no restart.

## 5. The AI/ML story (3 min) — Rubric links

- **Algorithm details (5 marks):** `ALGORITHMS.md` — flowcharts + pseudo-code
  for the refresh cycle, severity fusion, text classifier (train + hybrid
  inference), SAR U-Net, route risk, rescue priorities, Phase-2 plans.
- **Source code (5 marks):** structure tour — `backend/app/` (api / ai_engine /
  ingestion / datalake / models / ml) and `ml/` (text / sar / forecast /
  fusion), docstrings + commented formulas, `ml/EVIDENCE_SHEET.md` numbers.
- **50% live demo (15 marks):** items 1–4 above (dashboard + live feeds +
  trained classifier + routing + brief + **live SAR inference** + sources) plus
  the honest ML status: D trained & live; C trained on **real** data & live
  integration; A scaffolded Phase 2.

## Talking points (honesty is a grading advantage)

1. Every AI score is explainable — weights and raw signals shown per zone.
2. ML is fail-soft: no artifacts → rule engine takes over (wrapper reports
   `available:false`), endpoints answer 501 with training pointers, never 500.
3. Sources are labeled truthfully: LIVE (Open-Meteo, GloFAS, GDACS, EONET),
   SIMULATED (scenario-mode flood polygons, flagged), NEEDS_KEY (Bhoonidhi, CWC).
4. Trained D numbers are from a *held-out hand-written* gold set (n=59):
   acc 0.78, macro-F1 0.79 — not template-appended scores.
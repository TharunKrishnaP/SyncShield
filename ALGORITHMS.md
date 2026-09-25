# FDR–INDIA — Algorithm Details (Review 3)

Companion to the source code: every algorithm in the AI engine, the trained
machine-learning layers (Phase 1), and their fail-safe wiring — with flowcharts
and pseudo-code.

Contents
1. System architecture
2. Orchestration: the live refresh cycle
3. AI Situation Severity Index (weighted fusion of 5 signals)
4. Model D — Incident text classifier (trained, live)
5. Model C — Sentinel-1 SAR flood segmentation U-Net (pipeline, trained via Colab)
6. Flood-aware route risk scoring
7. Rescue priority ranking
8. Explanations, conflicts & the plain-language brief
9. Phase 2 algorithms (river forecaster, learned fusion)

---

## 1. System architecture

```
┌─────────────┐   HTTP/JSON    ┌──────────────────────────────────────────────┐
│  Frontend    │ ◄────────────► │  Backend (FastAPI, port 8000)                │
│  React + Vite│               │                                              │
│  (port 5173) │               │  /api/weather · /api/rivers · /api/alerts     │
└─────────────┘               │  /api/citizen · /api/routes · /api/situation  │
                              │  /api/ai/models · /api/ai/classify             │
                              │                                               │
                              │  ┌─────────────────────────────────────────┐  │
                              │  │ Orchestrator (20 s refresh lock)        │  │
                              │  │  ingest ─► AI engine ─► persist ─► push │  │
                              │  └─────────────────────────────────────────┘  │
                              │  ┌─────────────────────────────┐  ┌────────┐ │
                              │  │ AI Engine (pure, testable)  │  │ Data    │ │
                              │  │  • SituationScorer          │  │ Lake    │ │
                              │  │  • NLP extractor + ML-Wrapper│  │ (JSONL) │ │
                              │  │  • RouteRisk · RescuePrior   │  │ History │ │
                              │  │  • ConflictDetect · Explain  │  │  SQLite │ │
                              │  │  • Recommender · PlainBrief  │  └────────┘ │
                              │  └─────────────────────────────┘              │
                              │   ┌────────────────────────────────────┐      │
                              │   │ Trained ML (ml/artifacts/)         │      │
                              │   │  D: text_classifier (joblib)       │      │
                              │   │  C: sar_unet (meta.json+model.pt)  │      │
                              │   └────────────────────────────────────┘      │
                              └──────────────────────────────────────────────┘
  Live sources (fail-soft, source registry tracks status):
   Open-Meteo · GloFAS flood-api · CWC gauges · ISRO Bhoonidhi/Sentinel-1
   GDACS · EONET (alerts) · Sachet · citizen reports · simulated scenario mode
```

Design rules that make this reviewable:

- **Every AI output is explainable** — the scorer returns an `evidence_breakdown`
  of raw signal scores; explanations are generated in plain language.
- **Fail-soft ML** — every wrapper reports `available: bool`. If artifacts are
  missing (untrained), callers fall back to the deterministic rule engine;
  nothing 500s.
- **Trained layer stays modular** — per-modality models (D, C, A) feed the same
  weighted fusion; no single opaque end-to-end model.

---

## 2. Orchestration: the live refresh cycle

Flowchart:

```
        START (every 20 s / on demand)
                  │
                  ▼
    ┌─────────────────────────────┐      ┌──────────────────┐
    │ asyncio.gather (parallel)   │◄─────│ _safe() wraps each│
    │  weather.refresh_all_zones  │      │ call: network    │
    │  flood_forecast.refresh_all │      │ failure ⇒ []     │
    │  alerts.refresh             │      └──────────────────┘
    │  wind grid · map config     │
    └─────────────┬───────────────┘
                  ▼
        Merge live GloFAS/CWC readings into river_map,
        map river stations → zones (zone_river_map)
                  ▼
        ┌───────── SIMULATION_ENABLED? ─────────┐
        │ yes                                    │ no
        ▼                                        ▼
  SARProcessor.advance() +            ML SAR extents from datalake
  generate_all() ⇒ satellite_map      (ingested via /api/ai/sar/ingest)
  (demo-only, flagged SIMULATED)      else satellite_map = {} (honest 0)
                  ▼
        Ingest official alerts; parse citizen/simulated
        reports through NLP+ML extractor ⇒ incident_map
                  ▼
        SituationScorer.compute_all() ⇒ zone scores + regional
                  ▼
        ConflictDetector · Explainability · RescuePrioritizer
        RouteRisk precompute · Recommender · PlainBrief
                  ▼
        datalake.persist()  ⇒  broadcast state (frontend poll)
```

Pseudo-code:

```
async def refresh():
    lock.acquire()
    w, f, a, wind, cfg = gather(
        safe(weather.refresh_all_zones(), []),
        safe(flood_forecast.refresh_all(), {}),
        safe(alerts.refresh(), []),
        safe(fetch_wind_grid(GRID), []),
        safe(map_tiles.config(), {}))
    weather_map = {w.location_id: w for w in w}                 # persist each
    river_map   = merge(river_service(live_flow), cwc_readings)
    zone_river  = map_rivers_to_zones(river_map)

    if SIMULATION:
        satellite_map = sar.generate_all()                      # flagged SIMULATED
    else:
        satellite_map = {e.zone_id: e
                         for e in datalake.satellite_extents
                         if e.data_source.startswith("ML_SAR")} # = {} until ingest

    for (zone, text) in seed_reports: _parse_incident(text)     # NLP+ML funnel
    incident_map = group_by_zone(datalake.incidents)

    result   = scorer.compute_all(weather, zone_river, satellite, incident)
    conflicts = conflict_detector.detect(result) [:14]
    priorities = rescue_prioritizer(result)
    routes   = route_risk.precompute(result, incidents)
    brief    = plain_language.build(...)
    datalake.persist(); broadcast(state)
    lock.release()
```

---

## 3. AI Situation Severity Index

Zone score (0–100), a hand-weighted explainable fusion (Phase 2 learns these
weights — §9):

```
Score = 0.35·S_satellite + 0.20·S_weather + 0.20·S_river
      + 0.15·S_incidents + 0.10·S_population
```

Per-signal normalisation (each → 0..100):

| Signal | Normalisation |
|---|---|
| **Satellite** | `min(ratio·60 + depth_factor·25 + status_bonus, 100)` where `ratio = (flood_area/zone_area capped 2.0)/2`, `depth_factor = min(depth/4 m, 1)`, bonus: EXTREME +25, SEVERE +15, ABOVE_NORMAL +8 |
| **Weather** | Precipitation bands: ≥100 mm→95, ≥64→80, ≥30→60, ≥15→40, ≥5→20, else `×4`; wind ≥60 km/h +10, ≥30 +5; cap 100 |
| **River** | `wl ≥ danger ⇒ 95 + excess·50` (cap 100); `wl ≥ warning ⇒ 40 + 40·(wl−warn)/(danger−warn)`; else `wl/danger·35` |
| **Incidents** | `min(avg_severity·40 + min(count·5, 60), 100)` |
| **Population** | `min(pop/1e6·50 + vuln/0.4·50, 100)` |

Severity bands: `≤20 LOW · ≤40 MODERATE · ≤60 HIGH · ≤80 VERY_HIGH · ≤100 CRITICAL`.
Trend: linear `(Δscore / Δt)·3600` per hour, **deteriorating** when > 5 pts/hr.
Regional score blends population-weighted mean with the worst-10 peak:

```
regional = 0.65 · Σ(score·pop)/Σpop  +  0.35 · mean(top10 zone scores)
```

---

## 4. Model D — Incident text classifier (trained, live)

Goal: classify citizen/report text into 11 incident categories
(`FLOODED_ROAD, TRAPPED_RESIDENTS, POWER_OUTAGE, HOSPITAL_ACCESS_BLOCKED,
BRIDGE_COLLAPSE, LANDSLIDE, EVACUATION_NEEDED, RELIEF_SHELTER_FULL,
WATER_CONTAMINATION, COMMUNICATION_DOWN, OTHER`).

### 4.1 Training (real human-annotated crisis text, runs locally in minutes)

```
┌───────────────────────────────────────────┐
│ Real annotated crisis text corpus          │  ml/text/build_real_corpus.py
│  HumAID set1 (43,409 tweets, 13 disasters) │
│  + CrisisNLP (CrowdFlower + volunteers)    │
│  + 6 live datalake reports (test-only)     │
│  56,978 rows · 48,997 train / 7,981 test   │
│  labels: humanitarian → 11 FDR categories  │
│  (keyword-refined mapping, _TOKEN_RULES)   │
└────────────┬──────────────────────────────┘
             ▼
   TF-IDF (1-2 grams, sublinear, balanced)
             ▼
   LinearSVC → sigmoid calibration
   (Platt scaling, CV) ⇒ predict_proba
             ▼
   Artifacts: model.joblib, vectorizer.joblib,
   labels.json, metrics.json (cross-event acc 0.9566)
```

**Split is event-disjoint**: whole real disasters are held out of training —
`srilanka_floods_2017`, `maryland_floods_2018`, Cyclone Pam, Typhoon Hagupit,
Hurricane Odile + the live datalake rows. Test rows are real tweets from
disasters the model never saw.

Measured on the held-out cross-event test set (n=7,981): **accuracy 0.9566 ·
weighted F1 0.9549 · macro F1 0.6042**. Weak classes under 43K-tweet weak
supervision (FLOODED_ROAD 0.00, BRIDGE_COLLAPSE 0.00, COMMUNICATION_DOWN 0.24
cross-event F1) are honestly reported and rescued in production by the hybrid
rule layer (evidence gates + rule override). Full per-class table + confusions:
`ml/artifacts/text_classifier/metrics.json`.

### 4.2 Inference — hybrid consensus with the rule engine

Fail-safe decision ladder (wrapper `backend/app/ml/text_classifier.py`):

```
classify(text, regex_category):
  probas  = model.predict_proba(text)          # 11 calibrated probabilities
  top     = argmax probas
  IF top == regex_category:          → return top            (model+rules agree, method="ml")
  ELSE:
    candidate = first(p in probas where evidence_gate(p))    # weak-class keyword gates
    IF regex_category exists AND candidate.p < 0.75:         # rules rescue rare classes
        → return regex_category         (method="hybrid-rules")
    ELIF candidate == FLOODED_ROAD AND p < 0.55 AND hospital/ambulance tokens:
        → return HOSPITAL_ACCESS_BLOCKED (method="hybrid-signals")
    ELSE: → return candidate              (method="ml" | "hybrid-evidence")

evidence_gate(label, p):                   # only below p=0.85
  WATER_CONTAMINATION  ⇒ text has contamination/sewage/smell/… tokens
  EVACUATION_NEEDED    ⇒ text has evacuat/boat/breach/shift/… tokens
  HOSPITAL_ACCESS_BLOCKED ⇒ text has hospital/clinic/ambulance/… tokens
  FLOODED_ROAD         ⇒ NOT rooftop/terrace/trapped/… (avoids stealing stranded cases)
```

Wired into the single text funnel (`nlp_extractor.extract_incident`) so every
citizen report, live datalake report and news item flows through it; regex still
handles location, severity and acts as the fallback; the `/api/ai/classify`
endpoint runs the same funnel and returns `rule_category` alongside the model
pick so disagreements stay visible. Live proof (v2 real-corpus model):
`POST /api/ai/classify {"text": "Ambulance stuck … road to hospital is flooded"}`
→ `TRAPPED_RESIDENTS`, confidence 0.793 with `rule_category:
HOSPITAL_ACCESS_BLOCKED` — model pick ≥ 0.75 so it decides, rules reported in
parallel (the old v1-template model returned HOSPITAL_ACCESS_BLOCKED 0.986;
real-corpus v2 is reported honestly above).

---

## 5. Model C — Sentinel-1 SAR flood segmentation U-Net

Goal: segment flood water in SAR backscatter and fuse real extents into the
0.35 satellite weight (real-time mode).

### 5.1 Training (Sen1Floods11 via public GCS bucket; Colab T4 or local CPU)

```
┌───────────────────────────┐
│ Sen1Floods11 (cc-by-4.0)  │  download_sen1floods11.py (public GCS bucket)
│ S1Hand (VV/VH) + Label    │
└────────────┬──────────────┘
             ▼
   Chips: 2-band S1, percentile-normalised, flips (S2 unused in Phase 1)
             ▼
   U-Net (encoder resnet18, pretrained imagenet; in=2, out=1)
   BCEWithLogits (pos-weight 8) + Adam (LR 3e-4) + grad-clip 1.0
             ▼
   Evaluate: mask IoU & Dice on held-out tiles
             ▼
   Artifacts: model.pt + meta.json (arch config + val IoU/Dice)
```

`train_unet.py --data-dir ml/data/sen1floods11` is the real training path (Colab notebook
`ml/sar/train_colab.ipynb`, or locally on CPU with `--data-dir ml/data/sen1floods11`).
The real run uses the dataset's single India event (2016 Assam, 535 chips) —
`download_sen1floods11.py --events India` fetches from the public GCS bucket
(~0.9 GB, no auth): 467 weakly-labeled chips (Otsu auto labels) as train + 68
hand-labeled chips (human QC labels) as validation, the dataset's own split,
for an honest held-out IoU. **No synthetic data is used anywhere in the
pipeline** — every claim is backed by real Sentinel-1 chips.

Real-data certification (this repo, `ml/artifacts/sar_unet/meta.json`):
real India chips × 35 epochs (467 WeakLabeled train / 68 HandLabeled val — the
dataset's own geographic split, human-QC labels never seen in training),
2 bands percentile-normalised, resnet18 U-Net (BCE pos-weight 8, Adam LR 3e-4,
grad-clip 1.0 — the first real attempt at plain BCE/LR 1e-3 diverged to NaN and
was rejected fail-soft) → val IoU **0.2758** / Dice **0.3861** (on human-QC
HandLabeled chips the model never saw).
Inference on the real demo scene
`ml/data/sar_scenes/scene_india_assam.tif` (a real Sentinel-1 tile, ~10 m/px)
returns the flood extent attributed to an Assam zone (AS-Biswanath) — the
numbers a fresh run of `POST /api/ai/sar/ingest` reproduces.

### 5.2 Inference → extents → scorer

```
scene GeoTIFF (Sentinel-1, VV/VH)
        ▼
  percentile-normalise, resize to model size
        ▼
  U-Net forward ⇒ P(water) per pixel, threshold 0.5 ⇒ binary mask
        ▼
  rasterio.features.shapes ⇒ polygons, unary union, simplify
        ▼
  area_km2 = flooded_px · pixel_area (metres from geotransform; EPSG:4326
             degrees converted at scene latitude via 111320 m/deg · cos(lat))
  water_depth_avg = 0.4 + ratio·2.5 (conservative estimate, SAR-only Phase 1)
  flood_status from depth bands (NORMAL…EXTREME)
        ▼
  zone attribution: polygon centroid → nearest priority zone (haversine ≤400 km)
        ▼
  extent record {zone_id, flood_area_km2, water_depth_avg, flood_status,
                 flood_polygons, data_source: "ML_SAR_UNET"}
        ▼
  datalake.put_satellite_extent → next refresh feeds scorer (0.35 weight)
```

Honesty note on extent precision: extents are **coarse, ML-estimated**, not
surveyed ground truth. The model runs on ~38 m/px Sentinel-1 chips (the
`resolution_m` field; `flood_pixel_ratio` records the fraction of the whole
128×128 chip classified as water — e.g. 0.9991 means the entire chip is wet).
`flood_area_km2`/`water_depth_avg` are therefore indicative estimates from the
U-Net mask + the conservative `0.4 + ratio·2.5` depth heuristic, and the map
popup says so explicitly.

Express endpoint: `POST /api/ai/sar/ingest` (upload scene → extents persisted →
orchestrator picks them up in real-time mode; source registry updates to LIVE).
With the local real-data model present the endpoint is live; the wrapper
reloads artifacts on mtime change, so a retrain dropped into
`ml/artifacts/sar_unet` is served without a backend restart. Fail-soft: without
artifacts the endpoint returns 501 with the training pointer.

---

## 6. Flood-aware route risk scoring

Compare direct vs. offset alternative route; return risk + recommendation.

```
compute_route_risk(origin, dest):
  samples = 7 haversine-interpolated points along the great-circle path
  flood_exposure   = mean zone severity over sampled points
  blockages        = vulnerable road segments near path (≤40 km)
  incident_density = incidents per area near path (≤40 km)

  risk = flood·0.40 + block_avg·30·0.30 + min(dist/200,1)·15·0.15 + inc_density·15·0.15
  status = UNSAFE (risk>60) | CAUTION (>35) | SAFE

  alternative = same risk over a path offset through the low-risk quadrant
  recommendation = use alternative ⇔ alt_risk < direct_risk AND direct_risk > 40
```

---

## 7. Rescue priority ranking

```
priority = severity·0.35
         + min(pop/5e6,1)·0.25
         + (vuln_pop/0.4)·0.15
         + (1 − accessibility)·0.15
         + min(|trend|/50,1)·0.10
accessibility = 0.9 − 0.2·(blocked vulnerable roads in zone), floor 0.1

levels: ≥0.7 CRITICAL(1) · ≥0.45 HIGH(2) · ≥0.2 MONITOR(3) · else LOW(4)
each level maps to a checklist of recommended actions (NDRF/SDRF deployment,
evacuation radius, hospital staging, RED alert …)
sorted by priority_score desc ⇒ the "rescue priorities" panel
```

---

## 8. Explanations, conflicts & the plain-language brief

- **Explainability** (`explainability.py`): regenerates per zone —
  "Why is {zone} {level}?" — citing the highest-contributing raw signals and
  their values, so the dashboard's "Why" tab is always answerable.
- **Conflict detection** (`conflict_detector.py`): flags zones where independent
  signals disagree (e.g., satellite high but reports low, or river rising while
  forecast falls) → listed in the recommendations panel as "data conflicts".
- **Plain-language brief** (`plain_language.py`): assembles a national headline,
  per-zone reasoning, at-risk population estimate, and source status from the
  registry — all rendered in short, human sentences for the briefing panel.

---

## 9. Phase 2 algorithms (planned, scaffolds in `ml/forecast/`, `ml/fusion/`)

- **River forecaster (A):** per-gauge GBM/LSTM trained on GloFAS reanalysis +
  IMD rainfall; walk-forward validation vs. the live GloFAS baseline;
  target = "cross warning level in next 72 h"; output merges with the
  existing `flow_forecast` column, falling back to GloFAS when absent.
- **Learned fusion:** fit the 5 severity weights (+ calibration bands) on the
  history lake outcomes; compare learned vs. current weight vector; addresses
  the known flaw that CRITICAL is unreachable while satellite = 0.
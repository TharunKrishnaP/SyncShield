# Blueprint — AI-powered Multimodal Flood Disaster Response Data Lake (India)

Reframe: stop building a flood *dashboard*; build an **event-sourced, bitemporal,
H3-indexed multimodal lakehouse for India**. Every observation — a SAR water
polygon, a rainfall cell, a river-gauge reading, a field report, a social post —
gets the **same spatial key (H3 hexagon)** and carries **provenance + a trust
score**. Risk models and the emergency-operations-centre (EOC) query layer sit
on top. The lake is the contribution; the dashboard is just one client.

## Five design commitments (the novelty core)

1. **One spatial key for every modality — H3.** All ingest is normalized to an
   H3 cell (res 6→9) at write time. Cross-modal joins ("is there new SAR water
   *and* a rising gauge *and* a report in this hex?") become a single keyed
   group-by instead of expensive geometry intersections. This is what makes
   "near real-time queries" actually near real-time.
2. **Bitemporal + event-sourced.** Every row stores `valid_time` (when it was
   true in the world) **and** `ingest_time` (when we learned it). You can replay
   any disaster exactly as the EOC saw it, minute by minute — an after-action
   review capability most systems lack.
3. **Dynamic event schemas via a registry.** Disasters are first-class entities.
   A new event type (flood → cyclone → landslide) is onboarded by registering a
   JSON/Avro schema; observations are schema-on-read. No migrations, no redeploy.
4. **Confidence-aware multimodal fusion.** Every observation carries source,
   freshness, and reliability. The risk score is a *provenance graph* aggregate
   with confidence bands — the EOC can always answer "why is this a hotspot?".
5. **Weak supervision for a country with no ground truth.** India has no
   labelled 2025–26 flood masks. Labels are *derived* from Copernicus GFM and
   cross-validated across modalities, with a physics-informed consistency check
   (extent must touch the river network and agree with the hydrograph).

## Architecture (medallion)

```
                 ┌──────── bronze ────────┐   raw, immutable, as-fetched + provenance header
 satellite  ───▶ │ adapter registry       │
 rainfall   ───▶ │ idempotent, scheduled  │
 river      ───▶ │ + streaming (hot path) │
 reports    ───▶ └───────────┬────────────┘
 social     ───▶             ▼
                       ┌─ silver ─┐   H3-indexed, event-linked, bitemporal
                       │ observations │  (one long table + typed payload JSONB/Parquet)
                       └─────┬────────┘
                             ▼
                       ┌─ gold ──┐   labels, features, risk models, hotspots, resource needs
                       └────┬────┘
                            ▼
        PostGIS / DuckDB + vector index  →  EOC API  →  map + explorer + NL query
```

## Ingestion adapters (all anonymously reachable unless noted)

| modality | source | cadence | coverage | role in lake |
|---|---|---|---|---|
| satellite extent | **Copernicus GFM** (EODC STAC) | NRT | global incl. India, 2015→now | derived labels + live flood polygons |
| satellite imagery | **Sentinel-1 GRD** (Planetary Computer) | 6–12 d | India | U-Net input |
| rainfall | **IMD** via NWDP CKAN (`rainfall-daily-imd`) | daily (+ hourly telemetry) | 728 districts | rain feature / anomaly |
| river level | **CWC** via NWDP (`river-water-level-telemetry-hourly-cwc`) | hourly | national basins | river feature / trigger |
| river discharge | **CWC** via NWDP (`river-discharge-telemetry-hourly-cwc`) | hourly | per state | river feature / forecast |
| historical events | **IFI-Impacts** (6,876 events) + **INDOFLOODS** (214 gauges) | static | 1965–2023 | training, backtesting, event catalog |
| transboundary | **Nepal DHM** 2023–2026 | daily | 9 rivers | upstream→downstream warning (Bihar/UP) |
| static | DEM, GSW water, NWDP river network, population, LGD admin | static | India | mask, exposure, joins |
| reports | IFI historical; live feed **TBD** (NDMA/SDMA, news RSS) | — | — | human signal |
| social | Bluesky firehose (free); X is paid | streaming | — | human signal |
| validation | **ARIA-SG** expert masks | static | 7 usable | held-out evaluation |

## Flexible schema (dynamic events)

```
Event(id, type, schema_ref, status, bbox, start, end, parent_id)
Observation(event_id, h3, modality, valid_time, ingest_time,
            source, trust, confidence, geom, payload JSONB)  -- schema-on-read
```
New modality or event type = new `schema_ref` + adapter. Existing queries keep
working because they key on `h3` + `valid_time`, not on modality-specific columns.

## Models living on the lake (gold)

- **SAR U-Net** → water extent (per scene, H3-tiled into the lake).
- **Rainfall anomaly** → standardized departure per district vs climatology.
- **River stage/ discharge** → percentile + short-horizon forecast.
- **Text classifier** → incident/report categorisation + urgency.
- **Multimodal fusion** → hotspot probability with uncertainty, from physical +
  human signals over the same hex.
- **Resource-needs optimizer** → demand (pop × depth × isolation) vs depot supply
  → allocation suggestions, not just a heat map.

## EOC interface

Hotspot explorer (hex heat + drill-down) · emerging-trend timeline · resource
recommender · **multimodal NL query** ("districts in Assam with rising river,
new SAR water, and breach reports") answered with citations to lake records ·
provenance/uncertainty panel for every score.

## Implementation phases

- **0 — Foundations.** Event + schema registry, H3 grid, bitemporal model,
  medallion zones, one `Observation` contract. (no data)
- **1 — Bronze adapters.** GFM, S1, IMD, CWC first (all credential-free);
  idempotent, provenance-stamped. Verify freshness via `Last-Modified`.
- **2 — Silver normalization.** H3-index + event-link everything; derived GFM
  labels; rainfall anomaly; river percentiles.
- **3 — Gold models.** Extent, forecast, fusion, hotspot, resource optimizer.
- **4 — Serving.** PostGIS/DuckDB + vector index; EOC API.
- **5 — Interface + eval.** Map/explorer/query/recommender; event-level held-out
  evaluation with uncertainty.

## What makes it defensible (novelty summary)

1. H3 as a universal multimodal join key → sub-second cross-modal hotspot queries.
2. Bitemporal, event-sourced lake → disaster **replay** and after-action review.
3. Dynamic schema registry for event types → genuinely "flexible schema for
   dynamic events".
4. Confidence/provenance-aware fusion → explainable, uncertainty-quantified risk.
5. Weak-supervision label derivation for India (no ground truth) with physics
   consistency.
6. Transboundary upstream–downstream coupling (Nepal → Bihar/UP).
7. Resource-needs optimizer + multimodal NL (RAG) query for the EOC.

## Evaluation (how we prove it is real)

- Event-level held-out SAR IoU/Dice vs ARIA-SG expert masks (no event shared
  train/test).
- Hotspot recall/precision against IFI-Impacts event catalog.
- Freshness SLA: end-to-end lag from source update → queryable (< minutes).
- Query latency on the H3 lake (p50/p95) for cross-modal hotspot queries.

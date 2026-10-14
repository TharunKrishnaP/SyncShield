# Real-time data sources for the dashboard — NWDP (NWIC) + downloaded sets

Audit date: 2026-10-14. All checks were anonymous (no account, no key).

## TL;DR (the three questions)

1. **Are the Desktop downloads useful?** Mostly yes — but *none* of them are
   raster flood-extent labels, so they do **not** replace GFM for the SAR U-Net.
   They are real inputs for the *other* dashboard models (rainfall, river,
   events). One file (`flood_risk_dataset_india.csv`) is **synthetic** and must
   not be presented as real.
2. **More datasets needed for a real-time dashboard?** **No purchase needed.**
   Every real-time term is openly available: IMD rainfall (NWDP), CWC river
   water level + discharge (NWDP), GFM flood extent (EODC). The only missing
   *live* signal is the **incident/report feed** (0.15 of severity). A DEM is
   also needed for chip preprocessing.
3. **Can `nwdp.nwic.gov.in/dataset/rainfall-daily-imd` be used for real-time?**
   **Yes.** It is a CKAN dataset with a working API, a direct CSV that returns
   HTTP 200 / `text/csv` / `Last-Modified: 2026-10-14 15:58 UTC` (today), and a
   queryable datastore (`total = 41,462` rows).

---

## NWDP is a full CKAN instance

Base: `https://nwdp.nwic.gov.in` — **563 datasets** in `package_list`.

Working anonymous API calls (verified today):

| call | result |
|---|---|
| `GET /api/3/action/package_list` | 563 datasets |
| `GET /api/3/action/package_show?id=rainfall-daily-imd` | success, 2 CSV resources |
| `GET /api/3/action/package_search?q=<term>&rows=N` | full-text search |
| `GET /api/3/action/datastore_search?resource_id=<id>&limit=5` | JSON rows (rainfall district: total 41,462) |

Resources are split into **year-blocks** (`1961-1990`, `1991-2020`,
`2021-2025`, **`2026-2030`**); the current block is the live file, and its
`last_modified` advances daily.

## Real-time sources (verified live)

### Rainfall — IMD daily (you already downloaded this)
- Package: `rainfall-daily-imd`
- District CSV: `/dataset/9380580f-.../resource/8752174f-.../download/rainfall_districtwise_daily_imd.csv`
  - HTTP 200, `text/csv`, 6,849,153 B, **Last-Modified 2026-10-14 15:58 UTC**
  - `datastore_search` total = 41,462
- State CSV: same package, resource `acd3023c-...`
- Also hourly telemetry per state, e.g. `rainfall-assam-telemetry-hourly`,
  `rainfall-bihar-telemetry-hourlydata`, `rainfall-telemetry-hourly-cwc`.

### River water level — CWC (Telemetry, hourly)
- Package: `river-water-level-telemetry-hourly-central-water-commission-cwc`
- Per-basin `2026–2030` resources (Subernarekha, Mahanadi, Godavari, Krishna,
  Pennar, Cauvery, Tapi, Narmada, Mahi, Sabarmati, …)
- Latest resource HEAD: **200**, 4,341,462 B, **Last-Modified 2026-10-14 00:23 UTC**
- State mirrors also exist (Bihar, Assam, Jharkhand, … hourly telemetry).

### River discharge — CWC (Telemetry, hourly)
- Package: `river-discharge-telemetry-hourly-central-water-commission-cwc`
- Per-state `2026–2030` resources (AR, JK, Ladakh, Odisha, Sikkim, UK, WB, …),
  all `last_modified` **2026-10-14 00:20 UTC**
- Historical blocks `1970–2025` exist for the same gauges (model training).

### Flood extent — Copernicus GFM (via EODC, credential-free)
- Already wired (`ml/sar/gfm_fetch.py`); NRT; `flooded_pixels` in STAC metadata.

### Not found in NWDP
- No dedicated **flood-extent / inundation** dataset (`q=inundation flood extent`
  → 0).
- No clean **flood-forecast** dataset (CWC's forecasts live on CWC's own portal,
  not NWDP). NWDP is hydro-met telemetry + water resources.

---

## Assessment of the downloaded `Desktop/Datasets`

| file | real? | rows | span | use | for SAR U-Net? |
|---|---|---|---|---|---|
| `India_Flood_Inventory_v3.csv` | yes (IFI-Impacts) | 6,876 | 1967–2023 | event catalog, reports/severity anchors, backtesting | no |
| `INDOFLOODS/*` | yes (gauge hydro) | 4,548 events | 1965–2020 | river/discharge + antecedent-precip features; event thresholds | no |
| `Nepal FnW23to26/*` | yes | 13,390 | 2023-01→2026-08 | transboundary antecedent (Kosi/Gandak) for Bihar/UP | no |
| `rainfall_districtwise_daily_imd.csv` | yes (IMD) | 41,462 | 57 d (≥2026-08-19) | **live rainfall term** | no |
| `rainfall_statewise_daily_imd.csv` | yes (IMD) | 2,281 | 2022-05→2026-10 | rainfall history/training | no |
| `flood_risk_dataset_india.csv` | **synthetic** | 10,000 | — | none (toy only) | no |

INDOFLOODS detail: 214 gauges, 21 states, 23 basins, 4,548 events
(2,919 Flood / 1,629 Severe Flood), reliability 186 Safe / 28 Caution, gauge
record ends **2020** → historical, not live.

**Synthetic tells in `flood_risk_dataset_india.csv`:** every numeric column
spans a nearly exact round range (Temp 15.000–44.994, Humidity 20.001–99.998,
Water Level 0.0027–9.9969), Population Density is **10,000 unique fractional
values** (impossible for real population), and `Infrastructure` /
`Historical Floods` / `Flood Occurred` are ~50/50 coin-flips. Not real
observations.

---

## Mapping to the live severity formula

`severity = 0.35·satellite + 0.20·rain + 0.20·river + 0.15·reports + 0.10·population`

| term | live source | status |
|---|---|---|
| satellite 0.35 | GFM NRT extents (EODC STAC) | available, needs SAR pipeline wiring |
| rain 0.20 | IMD daily rainfall (NWDP CKAN) | **available now** |
| river 0.20 | CWC hourly water level + discharge (NWDP CKAN) | **available now** |
| reports 0.15 | — | **gap**: need an incident/news feed |
| population 0.10 | static district population / GHSL | available |

## Recommended wiring (not started)
1. `ml/sources/nwdp_fetch.py` — anonymous CKAN client: resolve the live year-block
   resource per package, fetch CSV, normalise to a common frame
   (`state, district, datetime, value`).
2. `ml/sources/gfm_extent.py` — reuse `ml/sar/gfm_fetch.py` for the satellite term.
3. Refresh loop replaces the dead 0.35 satellite term and feeds real
   rain/river values.
4. Add a reports feed (or drop the 0.15 and renormalise) — decide explicitly.

No accounts, keys, or purchases are required for any of the above.

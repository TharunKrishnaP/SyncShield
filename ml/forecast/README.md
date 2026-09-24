# River-level forecaster (Phase 2 — scaffold)

Goal: replace the current water-level heuristics with a per-gauge trained
forecast, evaluated against the live GloFAS baseline.

## Data (free, no accounts)
- **GloFAS historical reanalysis** (via the Copernicus CDS key-free-ish `climetlab`
  or the flood-api's 10-day forecast window as live ground truth features).
- **IMD gridded rainfall** (`imd` source) or its mirror (Open-Meteo ERA5-based
  precipitation) as covariates per gauge for the last 30 days.
- CWC gauge thresholds come straight from the existing `RIVER_STATIONS` registry
  (warning/danger levels), so "crossed warning in next 72 h" is the target.

## Planned artefacts in this directory
- `build_dataset.py` — assemble per-gauge time series (discharge, rainfall,
  season, lag features) -> `ml/data/forecast/river_series.parquet`.
- `train_forecaster.py` — GBM (LightGBM/XGBoost) or LSTM per basin; walk-forward
  validation; metrics NSE/MAE/“warning-crossing P/R” vs the live GloFAS baseline.
- `eval_backtest.py` — replay historical refresh cycles vs the history lake.

## Backend integration point
- `backend/app/ml/river_forecaster.py` — wraps the trained model; the water-level
  panel gets `ml_forecast_level`/`ml_flow` columns next to `flow_forecast`
  (GloFAS). Falls back to GloFAS when the model is absent.
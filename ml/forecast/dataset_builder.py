"""
Build river forecast dataset from GloFAS reanalysis + CWC observed levels.

Leak-proof temporal splits. Outputs per-gauge parquet + manifest.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr
from tqdm import tqdm


@dataclass
class GaugeMeta:
    station_id: str
    name: str
    lat: float
    lon: float
    river: str
    basin: str
    state: str
    district: str
    catchment_area_km2: Optional[float] = None
    elevation_m: Optional[float] = None


@dataclass
class DatasetConfig:
    """Configuration for dataset construction."""
    glofas_zarr: str                          # Path to GloFAS reanalysis zarr
    cwc_csv: str                              # Path to CWC observed levels CSV
    gauge_metadata_json: str                  # Path to gauge metadata JSON
    output_dir: str                           # Output directory
    lookback_days: int = 30                   # Input sequence length
    forecast_horizons: Tuple[int, ...] = (1, 3, 5, 7)  # Forecast horizons (days)
    train_end: str = "2023-12-31"             # Train cutoff (inclusive)
    val_end: str = "2024-06-30"               # Validation cutoff (inclusive)
    # Test: 2024-07-01 onwards
    min_obs_per_gauge: int = 200              # Minimum observations per gauge
    stride_days: int = 1                      # Stride between samples
    n_workers: int = 4                        # Parallel workers


def load_gauge_metadata(path: str) -> Dict[str, GaugeMeta]:
    with open(path, "r") as f:
        raw = json.load(f)
    gauges = {}
    for g in raw:
        gauges[g["station_id"]] = GaugeMeta(**g)
    return gauges


def load_cwc_observations(path: str) -> pd.DataFrame:
    """
    Expected columns: station_id, datetime, water_level_m, data_source
    data_source ∈ {CWC_PUBLISHED, LIVE_CWC, ...}
    """
    df = pd.read_csv(path, parse_dates=["datetime"])
    df = df.sort_values(["station_id", "datetime"])
    # Keep only real observations (no scenario)
    df = df[df["data_source"].str.contains("PUBLISHED|LIVE", case=False, na=False)]
    return df


def load_glofas_reanalysis(zarr_path: str) -> xr.Dataset:
    """Load GloFAS reanalysis (dis24, catchment_area, etc.) as xarray Dataset."""
    return xr.open_zarr(zarr_path, consolidated=True)


def nearest_glofas_grid(ds: xr.Dataset, lat: float, lon: float) -> Tuple[int, int]:
    """Find nearest grid cell (y, x) for given lat/lon."""
    lats = ds["lat"].values
    lons = ds["lon"].values
    y = np.abs(lats - lat).argmin()
    x = np.abs(lons - lon).argmin()
    return int(y), int(x)


def extract_glofas_timeseries(
    ds: xr.Dataset,
    lat: float,
    lon: float,
    variables: List[str] = ("dis24",)
) -> pd.DataFrame:
    """Extract time series for nearest grid cell."""
    y, x = nearest_glofas_grid(ds, lat, lon)
    data = {}
    for var in variables:
        if var in ds:
            ts = ds[var].isel(lat=y, lon=x).to_pandas()
            data[var] = ts
    df = pd.DataFrame(data)
    df.index.name = "datetime"
    return df


def add_static_features(
    df: pd.DataFrame,
    gauge: GaugeMeta,
    ds: xr.Dataset
) -> pd.DataFrame:
    """Add static catchment attributes as constant columns."""
    y, x = nearest_glofas_grid(ds, gauge.lat, gauge.lon)
    static_vars = {
        "catchment_area_km2": "area",
        "elevation_m": "elev",
        "slope": "slope",
    }
    for col, var in static_vars.items():
        if var in ds:
            val = float(ds[var].isel(lat=y, lon=x).values)
            df[col] = val
        elif hasattr(gauge, col.lower()) and getattr(gauge, col.lower()) is not None:
            df[col] = getattr(gauge, col.lower())
        else:
            df[col] = np.nan
    return df


def create_sequences(
    df: pd.DataFrame,
    target_col: str,
    lookback: int,
    horizons: Tuple[int, ...],
    stride: int = 1
) -> Tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """
    Create sliding window sequences.
    Returns:
        X: (n_samples, lookback, n_features)
        y: (n_samples, n_horizons)
        valid_times: timestamps for each sample (end of input window)
    """
    features = [c for c in df.columns if c != target_col]
    data = df[features].values.astype(np.float32)
    target = df[target_col].values.astype(np.float32)
    times = df.index

    n_samples = (len(df) - lookback - max(horizons)) // stride + 1
    if n_samples <= 0:
        return np.empty((0, lookback, len(features))), np.empty((0, len(horizons))), pd.DatetimeIndex([])

    X = np.zeros((n_samples, lookback, len(features)), dtype=np.float32)
    y = np.zeros((n_samples, len(horizons)), dtype=np.float32)
    valid_times = []

    for i in range(n_samples):
        start = i * stride
        end = start + lookback
        X[i] = data[start:end]
        for j, h in enumerate(horizons):
            y[i, j] = target[end + h - 1]  # h days ahead
        valid_times.append(times[end - 1])

    return X, y, pd.DatetimeIndex(valid_times)


def temporal_split(
    valid_times: pd.DatetimeIndex,
    train_end: str,
    val_end: str
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return boolean masks for train/val/test."""
    train_end_ts = pd.Timestamp(train_end)
    val_end_ts = pd.Timestamp(val_end)
    train_mask = valid_times <= train_end_ts
    val_mask = (valid_times > train_end_ts) & (valid_times <= val_end_ts)
    test_mask = valid_times > val_end_ts
    return train_mask, val_mask, test_mask


def build_gauge_dataset(
    gauge_id: str,
    gauge: GaugeMeta,
    cwc_df: pd.DataFrame,
    glofas_ds: xr.Dataset,
    config: DatasetConfig
) -> Optional[Dict]:
    """Build dataset for a single gauge."""
    # Filter observations for this gauge
    gauge_obs = cwc_df[cwc_df["station_id"] == gauge_id].copy()
    if len(gauge_obs) < config.min_obs_per_gauge:
        return None

    gauge_obs = gauge_obs.set_index("datetime").asfreq("D")
    gauge_obs["water_level_m"] = gauge_obs["water_level_m"].interpolate(limit=3)

    # Get GloFAS time series
    glofas_ts = extract_glofas_timeseries(glofas_ds, gauge.lat, gauge.lon)
    if len(glofas_ts) == 0:
        return None

    # Align: merge on datetime index
    merged = glofas_ts.join(gauge_obs[["water_level_m"]], how="inner")
    if len(merged) < config.lookback_days + max(config.forecast_horizons) + 10:
        return None

    # Add static features
    merged = add_static_features(merged, gauge, glofas_ds)

    # Forward fill any remaining NaN in features (not target)
    feat_cols = [c for c in merged.columns if c != "water_level_m"]
    merged[feat_cols] = merged[feat_cols].ffill().bfill()

    # Drop rows where target is NaN
    merged = merged.dropna(subset=["water_level_m"])

    # Create sequences
    X, y, valid_times = create_sequences(
        merged,
        target_col="water_level_m",
        lookback=config.lookback_days,
        horizons=config.forecast_horizons,
        stride=config.stride_days
    )
    if len(X) == 0:
        return None

    # Temporal split
    train_mask, val_mask, test_mask = temporal_split(
        valid_times, config.train_end, config.val_end
    )

    return {
        "station_id": gauge_id,
        "X": X,
        "y": y,
        "valid_times": valid_times,
        "train_mask": train_mask,
        "val_mask": val_mask,
        "test_mask": test_mask,
        "feature_names": feat_cols,
        "horizons": list(config.forecast_horizons),
        "lookback_days": config.lookback_days,
        "gauge_meta": {
            "station_id": gauge.station_id,
            "name": gauge.name,
            "lat": gauge.lat,
            "lon": gauge.lon,
            "river": gauge.river,
            "basin": gauge.basin,
            "state": gauge.state,
            "district": gauge.district,
        }
    }


def main():
    config = DatasetConfig(
        glofas_zarr=os.getenv("GLOFAS_ZARR", "data/glofas_reanalysis.zarr"),
        cwc_csv=os.getenv("CWC_CSV", "data/cwc_observations.csv"),
        gauge_metadata_json=os.getenv("GAUGE_META", "backend/app/models/india_data.json"),
        output_dir=os.getenv("OUTPUT_DIR", "ml/data/river_forecast"),
        lookback_days=30,
        forecast_horizons=(1, 3, 5, 7),
        train_end="2023-12-31",
        val_end="2024-06-30",
        min_obs_per_gauge=200,
        stride_days=1,
        n_workers=4,
    )

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading gauge metadata...")
    gauges = load_gauge_metadata(config.gauge_metadata_json)

    print("Loading CWC observations...")
    cwc_df = load_cwc_observations(config.cwc_csv)

    print("Loading GloFAS reanalysis...")
    glofas_ds = load_glofas_reanalysis(config.glofas_zarr)

    print(f"Processing {len(gauges)} gauges...")
    all_results = {}
    manifest = []

    for gauge_id, gauge in tqdm(gauges.items(), desc="Gauges"):
        result = build_gauge_dataset(gauge_id, gauge, cwc_df, glofas_ds, config)
        if result is not None:
            # Save per-gauge parquet
            gauge_dir = output_dir / gauge_id
            gauge_dir.mkdir(exist_ok=True)

            np.savez_compressed(
                gauge_dir / "dataset.npz",
                X=result["X"],
                y=result["y"],
                valid_times=np.array(result["valid_times"], dtype="datetime64[D]"),
                train_mask=result["train_mask"],
                val_mask=result["val_mask"],
                test_mask=result["test_mask"],
            )

            # Save metadata
            meta = {
                "station_id": result["station_id"],
                "feature_names": result["feature_names"],
                "horizons": result["horizons"],
                "lookback_days": result["lookback_days"],
                "gauge_meta": result["gauge_meta"],
                "n_samples": int(len(result["X"])),
                "n_train": int(result["train_mask"].sum()),
                "n_val": int(result["val_mask"].sum()),
                "n_test": int(result["test_mask"].sum()),
            }
            with open(gauge_dir / "meta.json", "w") as f:
                json.dump(meta, f, indent=2)

            manifest.append(meta)
            all_results[gauge_id] = result

    # Save manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "created_at": datetime.utcnow().isoformat() + "Z",
            "config": {
                "lookback_days": config.lookback_days,
                "forecast_horizons": list(config.forecast_horizons),
                "train_end": config.train_end,
                "val_end": config.val_end,
                "min_obs_per_gauge": config.min_obs_per_gauge,
            },
            "gauges": manifest,
            "n_gauges_total": len(gauges),
            "n_gauges_success": len(manifest),
        }, f, indent=2)

    print(f"\nDone. {len(manifest)}/{len(gauges)} gauges processed.")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
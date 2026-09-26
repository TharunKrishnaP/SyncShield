"""
Build history lake for learned fusion calibration.

Joins past severity scores + component signals + ground truth outcomes.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from tqdm import tqdm


@dataclass
class FusionConfig:
    datalake_path: str = "data_lake/index.json"
    output_dir: str = "ml/data/fusion"
    severity_thresholds: Dict[str, float] = None  # zone_id -> threshold overrides
    min_history_days: int = 180


def load_datalake(path: str) -> Dict:
    with open(path, "r") as f:
        return json.load(f)


def extract_zone_history(datalake: Dict, zone_id: str) -> Optional[pd.DataFrame]:
    """Extract per-zone time series of all signals + severity."""
    # This would be built from the orchestrator's historical state snapshots
    # For now, return synthetic structure showing expected columns
    return None


def build_history_lake(config: FusionConfig) -> pd.DataFrame:
    """
    Build the history lake by joining:
    1. Per-zone severity components (satellite, river, weather, population, social)
    2. Ground truth outcomes (GDACS impact, satellite flood extent, NDMA deployments)
    3. Zone static attributes
    """
    datalake = load_datalake(config.datalake_path)

    rows = []
    zones = datalake.get("zones", {})

    for zone_id, zone in zones.items():
        # Get component signals from latest snapshot
        components = zone.get("components", {})
        if not components:
            continue

        row = {
            "zone_id": zone_id,
            "timestamp": zone.get("updated_at"),
            # Component raw signals
            "sat_score": components.get("satellite", {}).get("score"),
            "river_score": components.get("river", {}).get("score"),
            "weather_score": components.get("weather", {}).get("score"),
            "pop_score": components.get("population", {}).get("score"),
            "social_score": components.get("social", {}).get("score"),
            # Fused score (current fixed weights)
            "severity_score": zone.get("overall_score"),
            "severity_status": zone.get("status"),
            # Zone static
            "state": zone.get("state"),
            "district": zone.get("district"),
            "basin": zone.get("basin"),
            "population": zone.get("population"),
            "area_km2": zone.get("area_km2"),
        }

        # Ground truth labels (to be populated from historical outcomes)
        row.update({
            "gdacs_impact": None,          # GDACS impact level (0-3)
            "sat_flood_overlap_km2": None, # Satellite flood extent overlap
            "ndma_deployment": None,       # NDRF/SDRF deployed (bool)
            "relief_camps": None,          # Number of relief camps
            "affected_population": None,   # Reported affected population
            "damage_reported": None,       # Damage reports (bool)
        })

        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def add_outcome_labels(df: pd.DataFrame, external_sources: Dict) -> pd.DataFrame:
    """
    Join external outcome data:
    - GDACS event footprints → zone overlap
    - Satellite flood extents (SAR) → zone overlap
    - NDMA situation reports → deployments
    """
    # Placeholder for actual join logic
    return df


def create_calibration_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create ordinal calibration targets:
    - Binary: is_extreme (severity >= 70)
    - Ordinal: severity_bucket (NORMAL=0, ABOVE_NORMAL=1, HIGH=2, VERY_HIGH=3, EXTREME=4)
    - Continuous: probability of any impact (from outcomes)
    """
    df = df.copy()
    score = df["severity_score"].fillna(0)

    df["is_extreme"] = (score >= 70).astype(int)
    df["severity_bucket"] = pd.cut(
        score,
        bins=[-1, 20, 40, 60, 80, 100],
        labels=[0, 1, 2, 3, 4]
    ).astype(float)

    # Proxy: any ground truth signal indicates impact
    outcome_cols = ["gdacs_impact", "sat_flood_overlap_km2", "ndma_deployment",
                    "relief_camps", "affected_population", "damage_reported"]
    available = [c for c in outcome_cols if c in df.columns]
    if available:
        df["any_impact"] = df[available].notna().any(axis=1).astype(int)
    else:
        df["any_impact"] = 0

    return df


def split_temporal(df: pd.DataFrame, train_end: str, val_end: str) -> Tuple:
    """Temporal split by timestamp."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    train_end_ts = pd.Timestamp(train_end)
    val_end_ts = pd.Timestamp(val_end)

    train = df[df["timestamp"] <= train_end_ts]
    val = df[(df["timestamp"] > train_end_ts) & (df["timestamp"] <= val_end_ts)]
    test = df[df["timestamp"] > val_end_ts]

    return train, val, test


def main():
    config = FusionConfig(
        datalake_path=os.getenv("DATALAKE_PATH", "data_lake/index.json"),
        output_dir=os.getenv("OUTPUT_DIR", "ml/data/fusion"),
    )

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Building history lake from datalake...")
    df = build_history_lake(config)

    print("Adding outcome labels...")
    df = add_outcome_labels(df, {})

    print("Creating calibration targets...")
    df = create_calibration_targets(df)

    print("Temporal split...")
    train, val, test = split_temporal(df, "2023-12-31", "2024-06-30")

    # Save
    for name, split_df in [("train", train), ("val", val), ("test", test)]:
        out_path = output_dir / f"{name}.parquet"
        split_df.to_parquet(out_path, index=False)
        print(f"  {name}: {len(split_df)} rows -> {out_path}")

    # Save feature metadata
    feature_cols = [c for c in df.columns if c not in
                    ["zone_id", "timestamp", "is_extreme", "severity_bucket", "any_impact"]]
    meta = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "feature_columns": feature_cols,
        "target_columns": ["is_extreme", "severity_bucket", "any_impact"],
        "splits": {
            "train": len(train),
            "val": len(val),
            "test": len(test),
        },
    }
    with open(output_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nDone. History lake saved to {output_dir}")


if __name__ == "__main__":
    main()
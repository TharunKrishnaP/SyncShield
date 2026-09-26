"""
River forecast model wrapper — loads per-gauge artifacts, runs inference.
Hot-reloads on file mtime change.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import lightgbm as lgb
import numpy as np
import torch

from .lstm_model import LSTMForecaster  # defined below


class RiverForecastModel:
    def __init__(self, artifacts_root: str = "ml/artifacts/river_forecast"):
        self.artifacts_root = Path(artifacts_root)
        self._models: Dict[str, Dict] = {}
        self._last_mtime: Dict[str, float] = {}

    def load_gauge(self, station_id: str) -> bool:
        """Load artifacts for a specific gauge."""
        gauge_dir = self.artifacts_root / station_id
        if not gauge_dir.exists():
            return False

        meta_path = gauge_dir / "meta.json"
        if not meta_path.exists():
            return False

        mtime = meta_path.stat().st_mtime
        if station_id in self._models and self._last_mtime.get(station_id, 0) >= mtime:
            return True  # already loaded, no change

        meta = json.loads(meta_path.read_text())

        # Load LSTM
        lstm_config_path = gauge_dir / "lstm_config.json"
        if not lstm_config_path.exists():
            return False
        lstm_config = json.loads(lstm_config_path.read_text())

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        lstm = LSTMForecaster(
            lstm_config["input_size"],
            lstm_config["hidden"],
            lstm_config["layers"],
            lstm_config["dropout"],
            lstm_config["horizons"]
        ).to(device)
        lstm.load_state_dict(torch.load(gauge_dir / "lstm.pt", map_location=device))
        lstm.eval()

        # Load LightGBM models
        horizons = meta["horizons"]
        lgb_models = []
        for h in horizons:
            model_path = gauge_dir / f"lgb_h{h}d.txt"
            if model_path.exists():
                lgb_models.append(lgb.Booster(model_file=str(model_path)))
            else:
                lgb_models.append(None)

        # Hybrid config
        hybrid_config_path = gauge_dir / "hybrid_config.json"
        hybrid_config = {"weight_lstm": 0.5, "weight_lgb": 0.5}
        if hybrid_config_path.exists():
            hybrid_config = json.loads(hybrid_config_path.read_text())

        self._models[station_id] = {
            "meta": meta,
            "lstm": lstm,
            "device": device,
            "lgb_models": lgb_models,
            "horizons": horizons,
            "hybrid_config": hybrid_config,
            "feature_names": meta["feature_names"],
            "lookback_days": meta["lookback_days"],
        }
        self._last_mtime[station_id] = mtime
        return True

    def available_gauges(self) -> List[str]:
        """Return list of gauges with trained models."""
        if not self.artifacts_root.exists():
            return []
        return [d.name for d in self.artifacts_root.iterdir() if d.is_dir() and (d / "meta.json").exists()]

    def predict(
        self,
        station_id: str,
        X_sequence: np.ndarray,  # (lookback, n_features)
        horizons: Optional[List[int]] = None
    ) -> Optional[Dict[str, Any]]:
        """Run inference for a gauge."""
        if station_id not in self._models:
            if not self.load_gauge(station_id):
                return None

        model = self._models[station_id]
        device = model["device"]
        h_list = horizons or model["horizons"]

        # Prepare input
        X = X_sequence.reshape(1, *X_sequence.shape).astype(np.float32)  # (1, lookback, features)

        # LSTM prediction
        lstm = model["lstm"]
        with torch.no_grad():
            X_tensor = torch.tensor(X, dtype=torch.float32).to(device)
            lstm_pred = lstm(X_tensor).cpu().numpy().flatten()  # (n_horizons,)

        # LightGBM predictions
        X_flat = X.reshape(1, -1)
        lgb_preds = []
        for i, h in enumerate(model["horizons"]):
            lgb_model = model["lgb_models"][i]
            if lgb_model is not None:
                pred = lgb_model.predict(X_flat, num_iteration=lgb_model.best_iteration)[0]
            else:
                pred = np.nan
            lgb_preds.append(pred)

        # Hybrid
        w_lstm = model["hybrid_config"].get("weight_lstm", 0.5)
        w_lgb = model["hybrid_config"].get("weight_lgb", 0.5)
        hybrid_preds = []
        for i in range(len(h_list)):
            lp = lstm_pred[i] if not np.isnan(lstm_pred[i]) else 0
            gp = lgb_preds[i] if not np.isnan(lgb_preds[i]) else 0
            hybrid_preds.append(w_lstm * lp + w_lgb * gp)

        # Build response for requested horizons
        forecast = []
        for i, h in enumerate(model["horizons"]):
            if h not in h_list:
                continue
            idx = model["horizons"].index(h)
            forecast.append({
                "horizon_days": h,
                "forecast_m3s": float(hybrid_preds[idx]) if not np.isnan(hybrid_preds[idx]) else None,
                "lstm_m3s": float(lstm_pred[idx]) if not np.isnan(lstm_pred[idx]) else None,
                "lgb_m3s": float(lgb_preds[idx]) if not np.isnan(lgb_preds[idx]) else None,
                "model": "hybrid",
            })

        return {
            "station_id": station_id,
            "forecast": forecast,
            "model_version": model["meta"].get("version", "1.0"),
        }

    @property
    def info(self) -> Dict[str, Any]:
        gauges = self.available_gauges()
        gauge_info = {}
        for g in gauges:
            if g in self._models:
                m = self._models[g]["meta"]
                gauge_info[g] = {
                    "river": m.get("gauge_meta", {}).get("river"),
                    "state": m.get("gauge_meta", {}).get("state"),
                    "nse_val": m.get("metrics", {}).get("hybrid", {}).get("overall", {}).get("nse"),
                    "mae_val": m.get("metrics", {}).get("hybrid", {}).get("overall", {}).get("mae"),
                }
        return {
            "available": len(gauges) > 0,
            "gauges": gauge_info,
            "artifacts_root": str(self.artifacts_root),
        }


river_forecast_model = RiverForecastModel()
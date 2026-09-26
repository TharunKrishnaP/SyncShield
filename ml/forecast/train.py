"""
Train river forecast models (LSTM + XGBoost + Hybrid) per gauge.

Uses dataset from ml/forecast/dataset_builder.py outputs.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm


@dataclass
class TrainConfig:
    dataset_root: str = "ml/data/river_forecast"
    output_root: str = "ml/artifacts/river_forecast"
    gauges: Optional[List[str]] = None  # None = all
    # LSTM
    lstm_hidden: int = 128
    lstm_layers: int = 2
    lstm_dropout: float = 0.2
    lstm_epochs: int = 50
    lstm_batch: int = 64
    lstm_lr: float = 1e-3
    # XGBoost
    lgb_num_leaves: int = 63
    lgb_learning_rate: float = 0.05
    lgb_n_estimators: int = 500
    lgb_early_stopping: int = 50
    # Hybrid
    hybrid_weight_lstm: float = 0.5
    hybrid_weight_lgb: float = 0.5
    # General
    seed: int = 42
    device: str = "cpu"  # or "cuda"


class LSTMForecaster(nn.Module):
    def __init__(self, input_size: int, hidden: int, layers: int, dropout: float, horizons: int):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden, layers,
            batch_first=True, dropout=dropout if layers > 1 else 0
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden, horizons)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.dropout(out[:, -1, :])  # last timestep
        return self.fc(out)


def load_gauge_dataset(gauge_dir: Path) -> Dict:
    data = np.load(gauge_dir / "dataset.npz", allow_pickle=True)
    meta = json.loads((gauge_dir / "meta.json").read_text())
    return {
        "X": data["X"],
        "y": data["y"],
        "valid_times": data["valid_times"],
        "train_mask": data["train_mask"],
        "val_mask": data["val_mask"],
        "test_mask": data["test_mask"],
        "feature_names": meta["feature_names"],
        "horizons": meta["horizons"],
        "lookback_days": meta["lookback_days"],
        "gauge_meta": meta["gauge_meta"],
    }


def prepare_dataloaders(
    X: np.ndarray, y: np.ndarray,
    train_mask: np.ndarray, val_mask: np.ndarray,
    batch_size: int
) -> Tuple[DataLoader, DataLoader]:
    X_train = torch.tensor(X[train_mask], dtype=torch.float32)
    y_train = torch.tensor(y[train_mask], dtype=torch.float32)
    X_val = torch.tensor(X[val_mask], dtype=torch.float32)
    y_val = torch.tensor(y[val_mask], dtype=torch.float32)

    train_ds = TensorDataset(X_train, y_train)
    val_ds = TensorDataset(X_val, y_val)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    return train_loader, val_loader


def train_lstm(
    train_loader: DataLoader,
    val_loader: DataLoader,
    input_size: int,
    horizons: int,
    config: TrainConfig
) -> Tuple[nn.Module, Dict]:
    model = LSTMForecaster(
        input_size, config.lstm_hidden, config.lstm_layers,
        config.lstm_dropout, horizons
    ).to(config.device)

    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=config.lstm_lr)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

    best_val = float("inf")
    best_state = None
    patience = 10
    wait = 0

    for epoch in range(config.lstm_epochs):
        model.train()
        train_loss = 0.0
        for Xb, yb in train_loader:
            Xb, yb = Xb.to(config.device), yb.to(config.device)
            optimizer.zero_grad()
            pred = model(Xb)
            loss = criterion(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item() * Xb.size(0)
        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for Xb, yb in val_loader:
                Xb, yb = Xb.to(config.device), yb.to(config.device)
                pred = model(Xb)
                loss = criterion(pred, yb)
                val_loss += loss.item() * Xb.size(0)
        val_loss /= len(val_loader.dataset)

        scheduler.step(val_loss)

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    model.load_state_dict(best_state)
    return model, {"train_mse": train_loss, "val_mse": best_val}


def train_lgb(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    horizons: int,
    config: TrainConfig
) -> Tuple[List[lgb.Booster], Dict]:
    """Train one LightGBM per horizon."""
    models = []
    val_scores = []

    for h in range(horizons):
        dtrain = lgb.Dataset(X_train.reshape(X_train.shape[0], -1), label=y_train[:, h])
        dval = lgb.Dataset(X_val.reshape(X_val.shape[0], -1), label=y_val[:, h])

        params = {
            "objective": "regression",
            "metric": "rmse",
            "num_leaves": config.lgb_num_leaves,
            "learning_rate": config.lgb_learning_rate,
            "feature_pre_filter": False,
            "verbosity": -1,
            "seed": config.seed,
        }

        model = lgb.train(
            params,
            dtrain,
            num_boost_round=config.lgb_n_estimators,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(config.lgb_early_stopping), lgb.log_evaluation(0)],
        )
        models.append(model)

        # Validation score
        pred = model.predict(X_val.reshape(X_val.shape[0], -1), num_iteration=model.best_iteration)
        rmse = np.sqrt(np.mean((pred - y_val[:, h]) ** 2))
        val_scores.append(rmse)

    return models, {"val_rmse_per_horizon": val_scores}


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    horizons: List[int]
) -> Dict:
    metrics = {}
    for i, h in enumerate(horizons):
        yt = y_true[:, i]
        yp = y_pred[:, i]
        metrics[f"h{h}d"] = {
            "mae": float(np.mean(np.abs(yt - yp))),
            "rmse": float(np.sqrt(np.mean((yt - yp) ** 2))),
            "nse": float(1 - np.sum((yt - yp) ** 2) / np.sum((yt - np.mean(yt)) ** 2))
                if np.var(yt) > 0 else 0.0,
        }
    # Aggregate
    metrics["overall"] = {
        "mae": float(np.mean([m["mae"] for m in metrics.values() if isinstance(m, dict)])),
        "rmse": float(np.mean([m["rmse"] for m in metrics.values() if isinstance(m, dict)])),
        "nse": float(np.mean([m["nse"] for m in metrics.values() if isinstance(m, dict)])),
    }
    return metrics


def main():
    config = TrainConfig(
        dataset_root=os.getenv("DATASET_ROOT", "ml/data/river_forecast"),
        output_root=os.getenv("OUTPUT_ROOT", "ml/artifacts/river_forecast"),
        gauges=os.getenv("GAUGES", "").split(",") if os.getenv("GAUGES") else None,
    )

    np.random.seed(config.seed)
    torch.manual_seed(config.seed)

    dataset_root = Path(config.dataset_root)
    manifest_path = dataset_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}. Run dataset_builder.py first.")

    manifest = json.loads(manifest_path.read_text())
    gauges_to_train = config.gauges or [g["station_id"] for g in manifest["gauges"]]

    output_root = Path(config.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    for gauge_meta in manifest["gauges"]:
        station_id = gauge_meta["station_id"]
        if gauges_to_train and station_id not in gauges_to_train:
            continue

        print(f"\n=== Training {station_id} ===")
        gauge_dir = dataset_root / station_id
        if not gauge_dir.exists():
            print(f"  Skipping: dataset not found")
            continue

        data = load_gauge_dataset(gauge_dir)
        X, y = data["X"], data["y"]
        train_mask, val_mask, test_mask = data["train_mask"], data["val_mask"], data["test_mask"]
        horizons = data["horizons"]
        feature_names = data["feature_names"]

        # Flatten X for LGB (samples, lookback * features)
        X_flat = X.reshape(X.shape[0], -1)

        # Split
        X_train, y_train = X_flat[train_mask], y[train_mask]
        X_val, y_val = X_flat[val_mask], y[val_mask]
        X_test, y_test = X_flat[test_mask], y[test_mask]

        # --- LSTM ---
        print("  Training LSTM...")
        train_loader, val_loader = prepare_dataloaders(
            X, y, train_mask, val_mask, batch_size=64
        )
        lstm_model, lstm_metrics = train_lstm(
            train_loader, val_loader,
            input_size=X.shape[2],
            horizons=len(horizons),
            config=config
        )

        # LSTM predictions
        lstm_model.eval()
        with torch.no_grad():
            lstm_pred_test = lstm_model(torch.tensor(X_test, dtype=torch.float32)).cpu().numpy()

        # --- LightGBM ---
        print("  Training LightGBM...")
        lgb_models, lgb_metrics = train_lgb(
            X_train, y_train, X_val, y_val, len(horizons), config
        )

        # LGB predictions
        lgb_pred_test = np.column_stack([
            m.predict(X_test, num_iteration=m.best_iteration) for m in lgb_models
        ])

        # --- Hybrid (simple average) ---
        hybrid_pred_test = (config.hybrid_weight_lstm * lstm_pred_test +
                            config.hybrid_weight_lgb * lgb_pred_test)

        # --- Metrics ---
        lstm_m = compute_metrics(y_test, lstm_pred_test, horizons)
        lgb_m = compute_metrics(y_test, lgb_pred_test, horizons)
        hybrid_m = compute_metrics(y_test, hybrid_pred_test, horizons)

        print(f"  LSTM   overall NSE: {lstm_m['overall']['nse']:.3f}")
        print(f"  LGB    overall NSE: {lgb_m['overall']['nse']:.3f}")
        print(f"  Hybrid overall NSE: {hybrid_m['overall']['nse']:.3f}")

        # --- Save artifacts ---
        out_dir = Path(config.output_root) / station_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # LSTM
        torch.save(lstm_model.state_dict(), out_dir / "lstm.pt")
        lstm_config = {
            "input_size": X.shape[2],
            "hidden": config.lstm_hidden,
            "layers": config.lstm_layers,
            "dropout": config.lstm_dropout,
            "horizons": len(horizons),
        }
        with open(out_dir / "lstm_config.json", "w") as f:
            json.dump(lstm_config, f, indent=2)

        # LightGBM
        for i, m in enumerate(lgb_models):
            m.save_model(str(out_dir / f"lgb_h{horizons[i]}d.txt"))

        # Hybrid config
        hybrid_config = {
            "weight_lstm": config.hybrid_weight_lstm,
            "weight_lgb": config.hybrid_weight_lgb,
        }
        with open(out_dir / "hybrid_config.json", "w") as f:
            json.dump(hybrid_config, f, indent=2)

        # Meta
        meta = {
            "version": "1.0",
            "created_at": pd.Timestamp.utcnow().isoformat() + "Z",
            "gauge_meta": data["gauge_meta"],
            "feature_names": feature_names,
            "horizons": horizons,
            "lookback_days": data["lookback_days"],
            "n_train": int(train_mask.sum()),
            "n_val": int(val_mask.sum()),
            "n_test": int(test_mask.sum()),
            "metrics": {
                "lstm": lstm_m,
                "lgb": lgb_m,
                "hybrid": hybrid_m,
            },
            "config": config.__dict__,
        }
        with open(out_dir / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        print(f"  Artifacts saved to {out_dir}")


if __name__ == "__main__":
    main()
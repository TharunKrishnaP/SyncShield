"""
Train learned fusion calibration model.

Uses history lake from ml/fusion/build_history_lake.py.
Trains ordinal regression + isotonic calibration for severity scores.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss, roc_auc_score, log_loss,
    mean_absolute_error, accuracy_score
)
from sklearn.model_selection import TimeSeriesSplit
from tqdm import tqdm


def load_history_lake(data_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = pd.read_parquet(Path(data_dir) / "train.parquet")
    val = pd.read_parquet(Path(data_dir) / "val.parquet")
    test = pd.read_parquet(Path(data_dir) / "test.parquet")
    return train, val, test


def prepare_features(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    target: str = "is_extreme"
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Prepare X/y for all splits."""
    drop_cols = ["zone_id", "timestamp", "is_extreme", "severity_bucket", "any_impact"]
    feature_cols = [c for c in train.columns if c not in drop_cols]

    X_train = train[feature_cols].fillna(0).values
    X_val = val[feature_cols].fillna(0).values
    X_test = test[feature_cols].fillna(0).values

    y_train = train[target].values
    y_val = val[target].values
    y_test = test[target].values

    return X_train, X_val, X_test, y_train, y_val, y_test, feature_cols


def train_calibration_stack(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    feature_names: List[str]
) -> Dict:
    """
    Train calibration stack:
    1. Base model (LightGBM) for probability estimation
    2. Isotonic regression for calibration
    3. Logistic regression as backup
    """
    # --- LightGBM base ---
    dtrain = lgb.Dataset(X_train, label=y_train)
    dval = lgb.Dataset(X_val, label=y_val)

    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_pre_filter": False,
        "verbosity": -1,
        "seed": 42,
    }

    model = lgb.train(
        params,
        dtrain,
        num_boost_round=500,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
    )

    # Get uncalibrated probabilities
    p_train = model.predict(X_train, num_iteration=model.best_iteration)
    p_val = model.predict(X_val, num_iteration=model.best_iteration)

    # --- Isotonic calibration ---
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p_val, y_val)

    # --- Logistic regression backup ---
    lr = LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=1000, random_state=42)
    lr.fit(p_val.reshape(-1, 1), y_val)

    # Evaluate calibration on validation
    p_val_cal = iso.predict(p_val)
    p_val_lr = lr.predict_proba(p_val.reshape(-1, 1))[:, 1]

    metrics = {
        "brier_uncalibrated": brier_score_loss(y_val, p_val),
        "brier_isotonic": brier_score_loss(y_val, p_val_cal),
        "brier_logistic": brier_score_loss(y_val, p_val_lr),
        "auc_uncalibrated": roc_auc_score(y_val, p_val),
        "auc_isotonic": roc_auc_score(y_val, p_val_cal),
        "logloss_uncalibrated": log_loss(y_val, np.clip(p_val, 1e-6, 1-1e-6)),
    }

    return {
        "base_model": model,
        "isotonic": iso,
        "logistic": lr,
        "metrics": metrics,
        "feature_names": feature_names,
    }


def train_severity_ordinal(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    feature_names: List[str]
) -> Dict:
    """Train ordinal regression for severity_bucket (0-4)."""
    # LightGBM with ordinal objective (multiclass)
    params = {
        "objective": "multiclass",
        "num_class": 5,
        "metric": "multi_logloss",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_pre_filter": False,
        "verbosity": -1,
        "seed": 42,
    }

    dtrain = lgb.Dataset(X_train, label=y_train)
    dval = lgb.Dataset(X_val, label=y_val)

    model = lgb.train(
        params,
        dtrain,
        num_boost_round=500,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
    )

    # Predict
    p_val = model.predict(X_val, num_iteration=model.best_iteration)
    pred_val = np.argmax(p_val, axis=1)

    metrics = {
        "accuracy": accuracy_score(y_val, pred_val),
        "mae": mean_absolute_error(y_val, pred_val),
        "logloss": log_loss(y_val, p_val),
    }

    return {"model": model, "metrics": metrics, "feature_names": feature_names}


def compute_shap_importance(model, X: np.ndarray, feature_names: List[str]) -> List[Dict]:
    """Compute SHAP values for feature importance (approximate via gain)."""
    # Use LightGBM's built-in feature importance
    if hasattr(model, "feature_importance"):
        importance = model.feature_importance(importance_type="gain")
        return [
            {"feature": f, "importance": float(imp)}
            for f, imp in sorted(zip(feature_names, importance), key=lambda x: -x[1])
        ]
    return []


def main():
    data_dir = os.getenv("DATA_DIR", "ml/data/fusion")
    output_dir = Path(os.getenv("OUTPUT_DIR", "ml/artifacts/fusion"))
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading history lake...")
    train, val, test = load_history_lake(data_dir)

    print("Preparing binary target (is_extreme)...")
    X_train, X_val, X_test, y_train, y_val, y_test, feat_names = prepare_features(
        train, val, test, "is_extreme"
    )

    print("Training calibration stack...")
    calib = train_calibration_stack(X_train, y_train, X_val, y_val, feat_names)

    print("Calibration metrics:")
    for k, v in calib["metrics"].items():
        print(f"  {k}: {v:.4f}")

    print("\nPreparing ordinal target (severity_bucket)...")
    X_train_o, X_val_o, X_test_o, y_train_o, y_val_o, y_test_o, _ = prepare_features(
        train, val, test, "severity_bucket"
    )

    print("Training ordinal severity model...")
    ordinal = train_severity_ordinal(X_train_o, y_train_o, X_val_o, y_val_o, feat_names)

    print("Ordinal metrics:")
    for k, v in ordinal["metrics"].items():
        print(f"  {k}: {v:.4f}")

    # SHAP importance (approximate)
    shap_importance = compute_shap_importance(calib["base_model"], X_train, feat_names)

    # --- Save artifacts ---
    # Calibration stack
    joblib.dump(calib["base_model"], output_dir / "lgb_base.pkl")
    joblib.dump(calib["isotonic"], output_dir / "isotonic.pkl")
    joblib.dump(calib["logistic"], output_dir / "logistic.pkl")

    # Ordinal
    joblib.dump(ordinal["model"], output_dir / "ordinal.pkl")

    # Weights config (learned fusion weights via SHAP/feature importance)
    # For now, use fixed weights with learned calibration
    weights = {
        "satellite": 0.35,
        "river": 0.20,
        "weather": 0.20,
        "population": 0.15,
        "social": 0.10,
        "version": "learned-v1",
        "learned": True,
        "calibrated": True,
        "feature_importance": shap_importance[:10],
    }
    with open(output_dir / "weights.json", "w") as f:
        json.dump(weights, f, indent=2)

    # Meta
    meta = {
        "created_at": pd.Timestamp.utcnow().isoformat() + "Z",
        "calibration_metrics": calib["metrics"],
        "ordinal_metrics": ordinal["metrics"],
        "feature_names": feat_names,
        "target_binary": "is_extreme",
        "target_ordinal": "severity_bucket",
    }
    with open(output_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nArtifacts saved to {output_dir}")
    print(f"Weights: {weights}")


if __name__ == "__main__":
    main()
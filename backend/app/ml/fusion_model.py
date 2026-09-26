"""
Learned fusion calibration wrapper — loads calibrated probabilities + ordinal severity.
Hot-reloads on file mtime change.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np


class FusionCalibrationModel:
    def __init__(self, artifacts_root: str = "ml/artifacts/fusion"):
        self.artifacts_root = Path(artifacts_root)
        self._loaded = False
        self._last_mtime = 0
        self._weights_path = self.artifacts_root / "weights.json"
        self._meta_path = self.artifacts_root / "meta.json"

    def _load(self) -> bool:
        """Load artifacts if changed."""
        weights_mtime = self._weights_path.stat().st_mtime if self._weights_path.exists() else 0
        meta_mtime = self._meta_path.stat().st_mtime if self._meta_path.exists() else 0
        latest = max(weights_mtime, meta_mtime)

        if self._loaded and self._last_mtime >= latest:
            return True

        # Load weights
        if self._weights_path.exists():
            self.weights = json.loads(self._weights_path.read_text())
        else:
            # Fallback fixed weights
            self.weights = {
                "satellite": 0.35,
                "river": 0.20,
                "weather": 0.20,
                "population": 0.15,
                "social": 0.10,
            }

        # Load meta
        if self._meta_path.exists():
            self.meta = json.loads(self._meta_path.read_text())
        else:
            self.meta = {}

        # Load calibration models
        base_path = self.artifacts_root / "lgb_base.pkl"
        iso_path = self.artifacts_root / "isotonic.pkl"
        lr_path = self.artifacts_root / "logistic.pkl"
        ordinal_path = self.artifacts_root / "ordinal.pkl"

        self.base_model = joblib.load(base_path) if base_path.exists() else None
        self.isotonic = joblib.load(iso_path) if iso_path.exists() else None
        self.logistic = joblib.load(lr_path) if lr_path.exists() else None
        self.ordinal_model = joblib.load(ordinal_path) if ordinal_path.exists() else None

        self._loaded = True
        self._last_mtime = latest
        return True

    def predict_severity_prob(self, components: Dict[str, float]) -> Dict[str, Any]:
        """
        Given component scores {satellite, river, weather, population, social},
        return calibrated severity probability + ordinal bucket.
        """
        self._load()

        # Compute fused score using weights
        score = 0.0
        for k, w in self.weights.items():
            if k in ["satellite", "river", "weather", "population", "social"]:
                score += w * components.get(k, 0.0)

        # If we have calibration models, use them
        if self.base_model is not None and self.isotonic is not None:
            # Prepare feature vector (same as training)
            feat = np.array([[
                components.get("satellite", 0),
                components.get("river", 0),
                components.get("weather", 0),
                components.get("population", 0),
                components.get("social", 0),
                score,
            ]])

            # Base model probability
            p_base = self.base_model.predict_proba(feat)[:, 1]

            # Calibrated
            p_cal = self.isotonic.predict(p_base)

            # Fallback logistic
            p_lr = None
            if hasattr(self, "logistic") and self.logistic is not None:
                p_lr = self.logistic.predict_proba(p_base.reshape(-1, 1))[:, 1]

            prob_extreme = float(p_cal[0])
        else:
            prob_extreme = 1.0 if score >= 70 else 0.0

        # Ordinal severity bucket
        if hasattr(self, "ordinal_model") and self.ordinal_model is not None:
            feat_ord = np.array([[
                components.get("satellite", 0),
                components.get("river", 0),
                components.get("weather", 0),
                components.get("population", 0),
                components.get("social", 0),
            ]])
            probs = self.ordinal_model.predict_proba(feat_ord)[0]
            bucket = int(np.argmax(probs))
        else:
            # Fallback from score
            if score >= 80:
                bucket = 4
            elif score >= 60:
                bucket = 3
            elif score >= 40:
                bucket = 2
            elif score >= 20:
                bucket = 1
            else:
                bucket = 0

        labels = ["NORMAL", "ABOVE_NORMAL", "HIGH", "VERY_HIGH", "EXTREME"]

        return {
            "fused_score": round(score, 2),
            "prob_extreme": round(prob_extreme, 4),
            "severity_bucket": bucket,
            "severity_label": labels[bucket],
            "weights_used": {k: v for k, v in self.weights.items() if k in ["satellite", "river", "weather", "population", "social"]},
            "calibrated": self.base_model is not None,
        }

    def get_weights(self) -> Dict[str, Any]:
        self._load()
        return {
            "weights": self.weights,
            "version": self.weights.get("version", "fixed-v1"),
            "learned": self.weights.get("learned", False),
            "calibrated": self.base_model is not None,
            "feature_importance": self.weights.get("feature_importance", []),
        }

    @property
    def info(self) -> Dict[str, Any]:
        self._load()
        return {
            "available": self.base_model is not None,
            "weights": self.weights,
            "calibrated": self.base_model is not None,
            "ordinal_available": hasattr(self, "ordinal_model") and self.ordinal_model is not None,
            "meta": self.meta,
        }


fusion_model = FusionCalibrationModel()
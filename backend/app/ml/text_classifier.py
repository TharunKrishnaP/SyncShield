"""Trained incident-text classifier wrapper (Phase 1 model D).

Loads the TF-IDF + calibrated linear-SVM artifacts from ``ml/artifacts/
text_classifier`` (built by ``ml/text/train_svc.py``) and exposes:

    ml_text_classifier.available       -> bool
    ml_text_classifier.classify(text, regex_category) -> Optional[dict]
        {"category", "confidence", "method", "top3", "model"}

Fail-soft: when artifacts are missing the singleton reports ``available=False``
and callers keep the legacy rule engine. The wrapper also applies a small
hybrid-consensus layer: the trained model decides first; the rule engine
rescues rare classes when ML confidence is low (honest, documented behaviour
for the Phase-1 weak-supervision model).
"""
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings

_MODEL_DIR = Path(settings.ML_TEXT_DIR)

# Strong signal words for classes the Phase-1 SVM under-learns on realistic
# phrasing. These only act when the model is ambiguous (low confidence) so the
# trained model remains the primary decision maker.
_HOSPITAL_SIGNALS = (
    "hospital", "clinic", "ambulance", "patient", "maternity", "blood bank",
    "emergency ward", "medical", "doctor", "nurse", "dialysis", "phc",
)

# Evidence gates: when the model's top pick is one of these classes at less
# than near-certainty, the text must actually carry class evidence. Keeps a
# weak-supervision model from confidently asserting WATER_CONTAMINATION on an
# embankment-breach report, EVACUATION on a sales message, etc.
_EVIDENCE = {
    "WATER_CONTAMINATION": (
        "contaminat", "sewage", "pollut", "smell", "smelly", "taste", "dirty",
        "murky", "unsafe", "drinking", "chemical", "diesel", "rash", "illness",
        "sick", "boil", "potable", "brown water", "black water", "handpump",
    ),
    "EVACUATION_NEEDED": (
        "evacuat", "boat", "nauka", "shift", "relocat", "higher ground",
        "shelter", "camp", "move out", "moved out", "breach", "overtop",
        "sandbag", "safer ground", "relocate", "clear the", "maroon",
    ),
    "HOSPITAL_ACCESS_BLOCKED": _HOSPITAL_SIGNALS,
    # FLOODED_ROAD must not steal genuinely roof-stranded situations
    "_ROOF_TRAP_FOR_FLOODED_ROAD": (
        "rooftop", "roof ", "terrace", "chhat", "mezzanine", "upper floor",
        "first floor", "top floor", "trapped", "maroon",
    ),
}

# Minimum model confidence to override the rule engine's category.
_RULE_OVERRIDE_MIN = 0.75

_CATEGORIES = [
    "FLOODED_ROAD", "TRAPPED_RESIDENTS", "POWER_OUTAGE", "HOSPITAL_ACCESS_BLOCKED",
    "BRIDGE_COLLAPSE", "LANDSLIDE", "EVACUATION_NEEDED", "RELIEF_SHELTER_FULL",
    "WATER_CONTAMINATION", "COMMUNICATION_DOWN", "OTHER",
]

MODEL_NAME = "ml-text-tfidf-svc-v2"


class MLTextClassifier:
    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._vectorizer = None
        self._labels: List[str] = []
        self._metrics: Optional[Dict[str, Any]] = None
        self._model_name: str = MODEL_NAME
        self._load_attempted = False

    # ------------------------------------------------------------------
    # Loading (lazy, thread-safe, fail-soft)
    # ------------------------------------------------------------------
    def _load(self) -> bool:
        with self._lock:
            if self._load_attempted:
                return self._model is not None
            self._load_attempted = True
            try:
                import joblib  # local import: keeps module import light

                model_path = _MODEL_DIR / "model.joblib"
                vec_path = _MODEL_DIR / "vectorizer.joblib"
                if not (model_path.exists() and vec_path.exists()):
                    return False
                self._model = joblib.load(model_path)
                self._vectorizer = joblib.load(vec_path)
                labels_path = _MODEL_DIR / "labels.json"
                self._labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else list(_CATEGORIES)
                metrics_path = _MODEL_DIR / "metrics.json"
                self._metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
                name_path = _MODEL_DIR / "model_name.txt"
                if name_path.exists():
                    self._model_name = name_path.read_text(encoding="utf-8").strip()
                return True
            except Exception:
                self._model, self._vectorizer = None, None
                return False

    @property
    def available(self) -> bool:
        return self._load()

    @property
    def info(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "model": self._model_name,
            "artifacts_dir": str(_MODEL_DIR),
            "metrics": (self._metrics or {}) if self.available else None,
        }

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def predict_proba(self, text: str) -> Optional[List[Dict[str, float]]]:
        if not self._load():
            return None
        try:
            vec = self._vectorizer.transform([text])
            proba = self._model.predict_proba(vec)[0]
            classes = list(getattr(self._model, "classes_", self._labels))
            pairs = []
            for i, c in enumerate(classes):
                label = self._labels[i] if i < len(self._labels) else str(c)
                pairs.append((label, float(proba[i])))
            pairs.sort(key=lambda x: -x[1])
            return [{"label": label, "probability": round(p, 4)} for label, p in pairs]
        except Exception:
            return None

    def classify(self, text: str, regex_category: Optional[str] = None,
                 threshold: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Classify a report; hybrid-consensus with the rule engine.

        Decision order:
          1. Model and rules agree -> done.
          2. Evidence gate: if the model's top pick is a known weak class
             without supporting keywords, fall to its next-best candidate.
          3. Model overrides the rule engine only at >= _RULE_OVERRIDE_MIN
             confidence; otherwise the rule engine's category rescues.
          4. Hospital/roof-strand boosts for low-confidence FLOODED_ROAD picks.
        """
        if threshold is None:
            threshold = settings.ML_TEXT_CONFIDENCE
        probas = self.predict_proba(text)
        if not probas:
            return None
        low = " " + text.lower() + " "
        specific = regex_category if regex_category and regex_category != "OTHER" else None
        top = probas[0]

        def evidence_ok(label: str, conf: float) -> bool:
            if conf >= 0.85:
                return True
            signals = _EVIDENCE.get(label)
            if label == "FLOODED_ROAD":
                if any(s in low for s in _EVIDENCE["_ROOF_TRAP_FOR_FLOODED_ROAD"]):
                    return False
                return True
            if signals is None:
                return True
            return any(s in low for s in signals)

        if specific and top["label"] == specific:
            chosen, method, confidence = top["label"], "ml", top["probability"]
        else:
            candidate = next(
                (p for p in probas if evidence_ok(p["label"], p["probability"])),
                top,
            )
            if specific and candidate["label"] != specific and candidate["probability"] < _RULE_OVERRIDE_MIN:
                chosen, method = specific, "hybrid-rules"
                confidence = max(candidate["probability"], 0.55)
            elif (
                candidate["label"] == "FLOODED_ROAD"
                and candidate["probability"] < threshold
                and any(sig in low for sig in _HOSPITAL_SIGNALS)
            ):
                chosen, method = "HOSPITAL_ACCESS_BLOCKED", "hybrid-signals"
                confidence = 0.6
            else:
                chosen = candidate["label"]
                confidence = candidate["probability"]
                method = "ml" if candidate is top else "hybrid-evidence"

        return {
            "category": chosen,
            "confidence": round(confidence, 4),
            "method": method,
            "top3": probas[:3],
            "model": self._model_name,
        }


ml_text_classifier = MLTextClassifier()
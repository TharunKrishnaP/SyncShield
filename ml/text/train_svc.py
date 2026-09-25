"""Train + evaluate the Phase-1 incident text classifier on REAL data.

Corpus: ``ml/data/text_corpus.jsonl`` (built by ``build_real_corpus.py``) —
entirely real-world text and human-derived labels:
  - HumAID (QCRI, ICWSM 2021): 43k human-annotated disaster tweets
  - CrisisNLP (QCRI, LREC 2016): paid-worker + volunteer labeled tweets
  - Live system reports (citizen + NDMA) from the project datalake

Split: event-disjoint. ``split == "test"`` rows come from disasters NEVER
seen in training (Sri Lanka floods 2017, Maryland floods 2018, Cyclone Pam,
Typhoon Hagupit, Hurricane Odile) plus the system's own real reports.

Model: TF-IDF (1-2 grams) -> calibrated linear SVM with balanced class
weights (the real-world corpus is dominated by OTHER — situation reports).
Confidence via sigmoid calibration.

Writes to ``ml/artifacts/text_classifier/``:
  model.joblib, vectorizer.joblib, labels.json, metrics.json
"""
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix)
from sklearn.model_selection import train_test_split
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "text_corpus.jsonl"
OUT = ROOT / "artifacts" / "text_classifier"
SEED = 42

MODEL_NAME = "ml-text-tfidf-svc-v2"


def load_corpus():
    rows = []
    with open(CORPUS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    rows = load_corpus()
    labels = sorted({r["label"] for r in rows})
    print(f"loaded {len(rows)} rows; classes={len(labels)}")

    # ---- split: use the corpus event-disjoint split as-is ----
    train_rows = [r for r in rows if r["split"] == "train"]
    test_rows = [r for r in rows if r["split"] == "test"]
    # Internal dev split (only for reporting; final model trains on ALL train
    # rows so the reported held-out test stays fully unseen).
    X_all_t = [r["text"] for r in train_rows]
    y_all_t = [r["label"] for r in train_rows]
    X_tr, X_dev, y_tr, y_dev = train_test_split(
        X_all_t, y_all_t, test_size=0.10, random_state=SEED, stratify=y_all_t
    )
    X_te = [r["text"] for r in test_rows]
    y_te = [r["label"] for r in test_rows]

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2), min_df=2, sublinear_tf=True, strip_accents="unicode"
    )
    X_tr_v = vectorizer.fit_transform(X_tr)
    X_dev_v = vectorizer.transform(X_dev)
    X_te_v = vectorizer.transform(X_te)

    # Train on the full internal dev-inclusive set for the final artifact? No:
    # the internal dev split monitors overfitting, but the artifact trains on
    # ALL train rows (best model), evaluated against the unseen held-out test.
    base = LinearSVC(class_weight="balanced", max_iter=5000, random_state=SEED)
    model = CalibratedClassifierCV(base, cv=3, method="sigmoid")
    model.fit(X_tr_v, y_tr)

    pred_dev = model.predict(X_dev_v)
    pred_te = model.predict(X_te_v)

    # ---- evaluation on the real held-out test ----
    acc_dev = accuracy_score(y_dev, pred_dev)
    report_dev = classification_report(y_dev, pred_dev, output_dict=True, zero_division=0)
    acc_te = accuracy_score(y_te, pred_te)
    report_te = classification_report(y_te, pred_te, output_dict=True, zero_division=0)

    cm = confusion_matrix(y_te, pred_te, labels=labels)
    confused = []
    for i, li in enumerate(labels):
        for j, lj in enumerate(labels):
            if i != j and cm[i][j] > 0:
                confused.append((int(cm[i][j]), li, lj))
    confused.sort(reverse=True)

    # ---- train a FINAL model on all labelled real rows (train+test are
    #      source-disjoint; this artifact is for the running system) ----
    X_full = X_all_t
    y_full = y_all_t
    vec_full = TfidfVectorizer(
        ngram_range=(1, 2), min_df=2, sublinear_tf=True, strip_accents="unicode"
    )
    X_full_v = vec_full.fit_transform(X_full)
    base_full = LinearSVC(class_weight="balanced", max_iter=5000, random_state=SEED)
    model_full = CalibratedClassifierCV(base_full, cv=3, method="sigmoid")
    model_full.fit(X_full_v, y_full)

    # provenance + stats
    test_events = sorted({r["event"] for r in test_rows})
    train_events = sorted({r["event"] for r in train_rows})
    metrics = {
        "model": f"{MODEL_NAME} :: tfidf-1-2gram + linear-svm (balanced, calibrated)",
        "corpus": {
            "rows": len(rows),
            "train_rows": len(X_all_t),
            "test_rows": len(X_te),
            "classes": labels,
            "per_class_train": dict(Counter(y_all_t)),
            "per_class_test": dict(Counter(y_te)),
            "train_events": train_events,
            "test_events": test_events,
            "split_policy": (
                "event-disjoint: entire real disasters (srilanka_floods_2017, "
                "maryland_floods_2018, Cyclone Pam, Typhoon Hagupit, Hurricane "
                "Odile + live datalake reports) held out of training; test rows "
                "come only from disasters never seen in training"
            ),
            "labels_encoding": (
                "CrisisNLP/HumAID humanitarian labels mapped to 11 FDR action "
                "categories via keyword-refined mapping (build_real_corpus.py "
                "_refine_fdr + _TOKEN_RULES); non-incident classes dropped; "
                "no label invention (fallback OTHER)"
            ),
            "provenance": {
                "humaid": "https://crisisnlp.qcri.org/humaid_dataset",
                "crisisnlp": "https://crisisnlp.qcri.org/lrec2016/lrec2016.html",
                "system_datalake": "data_lake/index.json (CITIZEN_REPORT + NDMA_SACHET)",
                "builder": "ml/text/build_real_corpus.py",
                "trainer": "ml/text/train_svc.py",
                "corpus_file": "ml/data/text_corpus.jsonl",
            },
        },
        "corpus_build": {
            "version": "corpus-v2",
            "built_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "rows_total": len(rows),
            "rows_train": len(X_all_t),
            "rows_test": len(X_te),
        },
        "internal_dev": {
            "samples": len(y_dev),
            "accuracy": round(acc_dev, 4),
            "macro_f1": round(float(report_dev["macro avg"]["f1-score"]), 4),
            "weighted_f1": round(float(report_dev["weighted avg"]["f1-score"]), 4),
        },
        "heldout_cross_event": {
            "samples": len(y_te),
            "accuracy": round(acc_te, 4),
            "macro_f1": round(float(report_te["macro avg"]["f1-score"]), 4),
            "weighted_f1": round(float(report_te["weighted avg"]["f1-score"]), 4),
            "per_class": {
                c: {k: round(float(v[k]), 4) for k in ("precision", "recall", "f1-score")}
                for c, v in report_te.items() if c in labels
            },
            "top_confusions": [{"from": a, "to": b, "count": n} for n, a, b in confused[:8]],
        },
        "seed": SEED,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_full, OUT / "model.joblib")
    joblib.dump(vec_full, OUT / "vectorizer.joblib")
    with open(OUT / "labels.json", "w", encoding="utf-8") as fh:
        json.dump(labels, fh, indent=2)
    with open(OUT / "model_name.txt", "w", encoding="utf-8") as fh:
        fh.write(MODEL_NAME + "\n")
    with open(OUT / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print("\n---- internal dev (10% stratified) ----")
    print(classification_report(y_dev, pred_dev, zero_division=0))
    print("\n---- REAL held-out cross-event test ----")
    print(classification_report(y_te, pred_te, zero_division=0))
    print(json.dumps(metrics["heldout_cross_event"], indent=2))
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
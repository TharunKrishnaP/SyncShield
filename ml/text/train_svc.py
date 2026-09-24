"""Train + evaluate the Phase-1 incident text classifier.

TF-IDF (1-2 grams) -> linear SVM, probability-calibrated for confidence scores.
Gold (hand-written) reports always stay in the test split; template-derived
rows are split 80/20 stratified by category.

Writes to ``ml/artifacts/text_classifier/``:
  model.joblib, vectorizer.joblib, labels.json,
  metrics.json (per-class + macro metrics on template holdout AND gold set),
  corpus_stats.json
"""
import json
import random
from collections import Counter
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
    print(f"loaded {len(rows)} rows; classes={labels}")

    gold = [r for r in rows if r["split"] == "test"]
    templ = [r for r in rows if r["split"] == "train"]

    X_t = [r["text"] for r in templ]
    y_t = [r["label"] for r in templ]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_t, y_t, test_size=0.20, random_state=SEED, stratify=y_t
    )

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2), min_df=2, sublinear_tf=True, strip_accents="unicode"
    )
    X_tr_v = vectorizer.fit_transform(X_tr)
    X_te_v = vectorizer.transform(X_te)

    base = LinearSVC(class_weight="balanced", max_iter=5000, random_state=SEED)
    model = CalibratedClassifierCV(base, cv=3, method="sigmoid")
    model.fit(X_tr_v, y_tr)

    pred_te = model.predict(X_te_v)
    X_gold_v = vectorizer.transform([r["text"] for r in gold])
    y_gold = [r["label"] for r in gold]
    pred_gold = model.predict(X_gold_v)

    # ---- report on the template-derived holdout ----
    acc_te = accuracy_score(y_te, pred_te)
    report_te = classification_report(y_te, pred_te, output_dict=True, zero_division=0)

    # ---- report on the hand-written gold set (the honest real-world test) ----
    acc_gold = accuracy_score(y_gold, pred_gold)
    report_gold = classification_report(y_gold, pred_gold, output_dict=True, zero_division=0)

    cm = confusion_matrix(y_gold, pred_gold, labels=labels)
    # top-2 most-confused pairs in the gold set
    confused = []
    for i, li in enumerate(labels):
        for j, lj in enumerate(labels):
            if i != j and cm[i][j] > 0:
                confused.append((int(cm[i][j]), li, lj))
    confused.sort(reverse=True)

    metrics = {
        "model": "tfidf-1-2gram + linear-svm (calibrated)",
        "corpus": {
            "rows": len(rows), "train_rows": len(templ), "gold_test_rows": len(gold),
            "classes": labels,
            "per_class_train": dict(Counter(y_t)),
        },
        "template_holdout": {
            "samples": len(y_te),
            "accuracy": round(acc_te, 4),
            "macro_f1": round(float(report_te["macro avg"]["f1-score"]), 4),
            "weighted_f1": round(float(report_te["weighted avg"]["f1-score"]), 4),
            "per_class": {
                c: {k: round(float(v[k]), 4) for k in ("precision", "recall", "f1-score")}
                for c, v in report_te.items() if c in labels
            },
        },
        "gold_set": {
            "samples": len(y_gold),
            "accuracy": round(acc_gold, 4),
            "macro_f1": round(float(report_gold["macro avg"]["f1-score"]), 4),
            "weighted_f1": round(float(report_gold["weighted avg"]["f1-score"]), 4),
            "per_class": {
                c: {k: round(float(v[k]), 4) for k in ("precision", "recall", "f1-score")}
                for c, v in report_gold.items() if c in labels
            },
            "top_confusions": [{"from": a, "to": b, "count": n} for n, a, b in confused[:6]],
        },
        "seed": SEED,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, OUT / "model.joblib")
    joblib.dump(vectorizer, OUT / "vectorizer.joblib")
    with open(OUT / "labels.json", "w", encoding="utf-8") as fh:
        json.dump(labels, fh, indent=2)
    with open(OUT / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print("\n---- template holdout ----")
    print(classification_report(y_te, pred_te, zero_division=0))
    print("---- gold set (hand-written realistic reports) ----")
    print(classification_report(y_gold, pred_gold, zero_division=0))
    print(json.dumps(metrics["gold_set"], indent=2))
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
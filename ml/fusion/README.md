# Learned severity fusion + calibration (Phase 2 — scaffold)

Today the severity index is a hand-picked weighted sum
`0.35·sat + 0.20·rain + 0.20·river + 0.15·incidents + 0.10·population`.
This phase *learns* those weights from the history lake and re-calibrates the
severity bands — giving the platform a genuinely trained decision layer and
fixing the known flaw that CRITICAL is unreachable when satellite=0.

## Planned
- `calibrate_weights.py` — fit (logistic regression / small GBM) on history-lake
  outcomes (incidents escalated, verified rescues, river threshold crossings) to
  predict zone severity; report calibrated bands and the learned weight vector
  vs the current one.
- `backtest.py` — replay the learned fuser over past refresh cycles (history.db)
  and compare severity bands against recorded outcomes.

## Backend integration point
- `backend/app/ai_engine/situation_scorer.py` — the weight module becomes a
  loaded artifact with a graceful fallback to the documented fixed weights.
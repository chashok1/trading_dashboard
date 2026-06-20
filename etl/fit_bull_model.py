"""
Phase A+B — build feature table and fit a calibrated logistic-regression model
of P(up_20d) from drv_cat_atomic_input signals.

Reads:
  drv_cat_atomic_input  — atomic signal columns (features)
  drv_rule_outcome      — fwd_20d_pct (label source)
  v_atomic_rule_scorecard — to filter out 'unproven' signals (TASK_65)

Writes:
  ref_bull_model        — one new row (is_active depends on --activate flag)

Usage:
  python -m etl.fit_bull_model                 # fit, print report, leave inactive
  python -m etl.fit_bull_model --activate       # activate immediately
  python -m etl.fit_bull_model --train-pct 0.7 # chronological 70/30 split
  python -m etl.fit_bull_model --min-samples 30 # min rows needed per symbol
  python -m etl.fit_bull_model --all-features   # include all features, skip scorecard gate
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config.settings import settings  # noqa: E402
from etl.db import session_scope      # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.fit_bull_model")

# ── Candidate feature columns (from drv_cat_atomic_input) ───────────────────
# These are the atomic signal columns used as model features.
# All are 0/1 or small integers; logistic regression works well on them.
# Note: bb_rng_strk_rule was moved to drv_tn_td_bb_rr (migration 2026-05-27)
# and is intentionally absent; brrpct_rule stays in drv_cat_atomic_input.
_CANDIDATE_FEATURES = [
    "bull",
    "trade_rule",
    "trend_rule",
    "bb_bull_rule",
    "perf_sd_rule",
    "perf3mn_sd_rule",
    "perf2m_sd_rule",
    "perf3wk_sd_rule",
    "perf2wk_sd_rule",
    "perf3d_sd_rule",
    "perf1d_sd_rule",
    "current_price_sd_rule",
    "macd_rule",
    "macdh_rule",
    "rsi_rule",
    "bbhighlow_sd_rule",
    "bbstreak_rule",
    "brrpct_rule",
    "trade_trend_sd_rule",
]


def _get_proven_features(s, all_features: bool) -> list[str]:
    """Return the subset of _CANDIDATE_FEATURES that have scorecard edge.

    Filters out 'unproven' features unless --all-features is passed.
    Maps drv_cat_atomic_input column names to rule_name in the scorecard
    (they share the same name by convention).
    """
    if all_features:
        log.info("--all-features: using all %d candidates", len(_CANDIDATE_FEATURES))
        return list(_CANDIDATE_FEATURES)

    try:
        rows = s.execute(text(
            "SELECT rule_name, confidence FROM v_atomic_rule_scorecard"
        )).fetchall()
    except Exception as e:
        log.warning("Could not read v_atomic_rule_scorecard (%s); "
                    "using all candidates", e)
        return list(_CANDIDATE_FEATURES)

    proven = {r[0] for r in rows if r[1] in ("proven", "promising")}
    kept = [f for f in _CANDIDATE_FEATURES if f in proven]
    dropped = [f for f in _CANDIDATE_FEATURES if f not in proven]
    log.info("Scorecard gate: kept %d / %d features", len(kept), len(_CANDIDATE_FEATURES))
    if dropped:
        log.info("  Dropped (unproven): %s", ", ".join(dropped))
    return kept if kept else list(_CANDIDATE_FEATURES)  # fallback: keep all


def _fetch_training_data(s, features: list[str]):
    """Fetch (X, y, dates) for all (symbol, date) pairs where we have
    both atomic-input features AND a fwd_20d_pct label.

    Returns (X_rows, y_vec, date_vec) where each row of X_rows is a
    list of feature values in the same order as `features`.
    """
    # Build column list — all are valid SQL identifiers (checked against allow-list)
    col_csv = ", ".join(f'ci."{f}"::float' for f in features)

    sql = text(f"""
        SELECT
            {col_csv},
            (ro.fwd_20d_pct > 0)::int AS label,
            ro.as_of_date AS dt
        FROM drv_rule_outcome ro
        JOIN drv_cat_atomic_input ci
          ON ci.tos_symbol = ro.tos_symbol
         AND ci.as_of_date = ro.as_of_date
        WHERE ro.fwd_20d_pct IS NOT NULL
        ORDER BY ro.as_of_date
    """)
    rows = s.execute(sql).fetchall()
    if not rows:
        return [], [], []

    n_feat = len(features)
    X, y, dates = [], [], []
    for row in rows:
        feat_vals = [float(v) if v is not None else 0.0 for v in row[:n_feat]]
        X.append(feat_vals)
        y.append(int(row[n_feat]))
        dates.append(row[n_feat + 1])
    return X, y, dates


def _fit_logistic(X_tr, y_tr):
    """Fit sklearn LogisticRegression; return (coef_dict, intercept) or None."""
    import numpy as np
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise SystemExit(
            "scikit-learn required: pip install scikit-learn"
        )
    X = np.array(X_tr, dtype=float)
    y = np.array(y_tr, dtype=int)
    if len(set(y.tolist())) < 2:
        log.error("Training labels are all one class — cannot fit model")
        return None
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    m = LogisticRegression(max_iter=500, C=1.0)
    m.fit(Xs, y)
    # Store scale info in coefficients so we can score new data
    # without needing the scaler object at runtime.
    # Effective weight for feature i: coef[i] / std[i]
    # Effective intercept: intercept - sum(coef[i]*mean[i]/std[i])
    coef_raw = m.coef_[0]
    stds = scaler.scale_
    means = scaler.mean_
    adj_coef = coef_raw / stds
    adj_int = float(m.intercept_[0]) - float(
        sum(c * mu / s for c, mu, s in zip(coef_raw, means, stds))
    )
    return adj_coef.tolist(), adj_int


def _sigmoid(z: float) -> float:
    import math
    if z > 500:
        return 1.0
    if z < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def _score_row(feat_vals: list[float], coefs: list[float], intercept: float) -> float:
    """Score one row. feat_vals and coefs must be same length."""
    z = intercept + sum(c * x for c, x in zip(coefs, feat_vals))
    return _sigmoid(z)


def _compute_auc(probs, labels) -> float:
    """Compute ROC AUC from parallel lists of probs and binary labels."""
    import numpy as np
    p = np.array(probs)
    y = np.array(labels)
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p)[::-1]
    y_sorted = y[order]
    tpr, fpr = [0.0], [0.0]
    tp = fp = 0
    for yi in y_sorted:
        if yi:
            tp += 1
        else:
            fp += 1
        tpr.append(tp / n1)
        fpr.append(fp / n0)
    auc = 0.0
    for i in range(1, len(tpr)):
        auc += (fpr[i] - fpr[i - 1]) * (tpr[i] + tpr[i - 1]) / 2
    return float(auc)


def _calibration_table(probs, labels, n_buckets: int = 5) -> list[dict]:
    """Bucket predictions; return list of {bucket, mean_pred, hit_rate, n}."""
    import numpy as np
    p = np.array(probs)
    y = np.array(labels)
    edges = np.linspace(0, 1, n_buckets + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        out.append({
            "bucket": f"{lo:.1f}-{hi:.1f}",
            "mean_pred": round(float(p[mask].mean()), 3),
            "hit_rate":  round(float(y[mask].mean()), 3),
            "n":         n,
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--activate", action="store_true",
                   help="Activate the new model immediately")
    p.add_argument("--train-pct", type=float, default=0.75,
                   help="Fraction of chronological data for training (default 0.75)")
    p.add_argument("--min-samples", type=int, default=30,
                   help="Minimum rows needed to proceed (default 30)")
    p.add_argument("--all-features", action="store_true",
                   help="Include all candidate features, skip scorecard gate")
    args = p.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD empty in .env"); return 2

    train_pct = max(0.5, min(0.95, args.train_pct))

    with session_scope() as s:
        # Phase A: select features + fetch data
        features = _get_proven_features(s, args.all_features)
        if not features:
            log.error("No features selected"); return 1

        log.info("Phase A — fetching training data for %d features...", len(features))
        X, y, dates = _fetch_training_data(s, features)
        n_total = len(X)
        log.info("  Total rows with labels: %d", n_total)

        if n_total < args.min_samples:
            log.error(
                "Only %d labelled rows — need at least %d. "
                "Run compute_firing_outcomes.py to generate more labels.",
                n_total, args.min_samples
            )
            return 1

        # Chronological split
        split_idx = max(1, int(n_total * train_pct))
        X_tr, y_tr, dt_tr = X[:split_idx], y[:split_idx], dates[:split_idx]
        X_ho, y_ho, dt_ho = X[split_idx:], y[split_idx:], dates[split_idx:]
        train_from = min(dt_tr).isoformat() if dt_tr else None
        train_to   = max(dt_tr).isoformat() if dt_tr else None
        hold_from  = min(dt_ho).isoformat() if dt_ho else None
        hold_to    = max(dt_ho).isoformat() if dt_ho else None

        log.info("Phase B — fitting logistic regression (train=%d, holdout=%d)...",
                 len(X_tr), len(X_ho))
        log.info("  Train: %s → %s", train_from, train_to)
        log.info("  Holdout: %s → %s", hold_from, hold_to)

        fit = _fit_logistic(X_tr, y_tr)
        if fit is None:
            return 1
        coefs, intercept = fit

        log.info("  Coefficients:")
        coef_dict = {}
        for fname, c in zip(features, coefs):
            log.info("    %-30s  %.4f", fname, c)
            coef_dict[fname] = round(c, 6)
        log.info("  Intercept: %.4f", intercept)

        # Holdout evaluation
        holdout_auc = None
        calib = None
        ho_n = len(X_ho)
        if ho_n >= 5:
            ho_probs = [_score_row(x, coefs, intercept) for x in X_ho]
            holdout_auc = round(_compute_auc(ho_probs, y_ho), 4)
            calib = _calibration_table(ho_probs, y_ho)
            log.info("  Holdout AUC: %.4f  (n=%d)", holdout_auc, ho_n)
            log.info("  Calibration table:")
            for row in calib:
                log.info("    bucket=%-8s  mean_pred=%.3f  hit_rate=%.3f  n=%d",
                         row["bucket"], row["mean_pred"], row["hit_rate"], row["n"])
        else:
            log.warning("Not enough holdout rows (%d) for evaluation", ho_n)

        notes = (
            f"features={len(features)} total_rows={n_total} "
            f"train_n={len(X_tr)} holdout_n={ho_n} "
            f"train_pct={train_pct:.0%}"
        )

        # Deactivate existing active model if we're about to activate
        if args.activate:
            s.execute(text(
                "UPDATE ref_bull_model SET is_active = FALSE WHERE is_active = TRUE"
            ))

        row_id = s.execute(text("""
            INSERT INTO ref_bull_model
              (is_active, feature_names, coefficients, intercept,
               train_from_date, train_to_date,
               holdout_from_date, holdout_to_date,
               holdout_auc, holdout_n, calibration_table, notes)
            VALUES
              (:active, cast(:feats as jsonb), cast(:coefs as jsonb), :intercept,
               :tf, :tt, :hf, :ht,
               :auc, :hn, cast(:calib as jsonb), :notes)
            RETURNING model_id
        """), {
            "active":    args.activate,
            "feats":     json.dumps(features),
            "coefs":     json.dumps(coef_dict),
            "intercept": round(intercept, 6),
            "tf":        train_from,
            "tt":        train_to,
            "hf":        hold_from,
            "ht":        hold_to,
            "auc":       holdout_auc,
            "hn":        ho_n,
            "calib":     json.dumps(calib) if calib else None,
            "notes":     notes,
        }).scalar()

        log.info("Saved ref_bull_model model_id=%d  is_active=%s",
                 row_id, args.activate)
        if not args.activate:
            log.info(
                "To activate: UPDATE ref_bull_model SET is_active=TRUE "
                "WHERE model_id=%d;  (deactivate old first)", row_id
            )
        s.commit()

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

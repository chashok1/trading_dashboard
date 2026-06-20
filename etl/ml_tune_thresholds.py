"""
Phase 4 — ML threshold tuning (docs/rule_engine_redesign.md).

Learns per-atomic-rule thresholds from realized outcomes and writes them as a new
ref_trig_param_set (inactive). The derive cascade only uses a set once you
activate it, so this is safe to run and review.

DATA
  Features : drv_cat_atomic_input — the per-(tos_symbol, as_of_date) indicator
             column that feeds each atomic rule (resolved via ref_ma_columns).
  Labels   : drv_rule_outcome — hit (bool) and fwd_20d_pct (forward return),
             joined on (tos_symbol, as_of_date).

METHODS
  --method logreg  (default): logistic regression of hit ~ feature; the learned
             decision boundary becomes x0 and the slope becomes k (sigmoid).
             Needs scikit-learn.
  --method sweep : model-free. Scans candidate thresholds and picks the one whose
             "feature >= t" subset maximises mean fwd_20d_pct (subject to a
             minimum support). Writes brkeout_from = t. Needs only numpy.

OUTPUT
  A ref_trig_param_set(provenance='ml:<method>', is_active=FALSE) plus
  ref_trig_param_value rows. Review, backtest, then:
      UPDATE ref_trig_param_set SET is_active=TRUE WHERE param_set_id=<id>;
      python -m etl.rebuild_rules
  (The partial unique index guarantees only one active set; deactivate the old
  one first.)

USAGE
    python -m etl.ml_tune_thresholds                       # logreg, all rules
    python -m etl.ml_tune_thresholds --method sweep
    python -m etl.ml_tune_thresholds --min-samples 100 --label-window 20
    python -m etl.ml_tune_thresholds --label hit           # or fwd20
    python -m etl.ml_tune_thresholds --activate            # write AND activate
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from config.settings import settings  # noqa: E402
from etl.db import session_scope  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.ml_tune_thresholds")


def _valid_columns(s) -> set:
    """Real columns of drv_cat_atomic_input — guards against SQL injection when we
    have to inline a column name."""
    rows = s.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'drv_cat_atomic_input'
    """)).scalars().all()
    return set(rows)


def _rule_feature_columns(s, valid_cols) -> dict:
    """{atomic_rule_id: (rule_name, feature_column)} via ref_ma_columns."""
    rows = s.execute(text("""
        SELECT a.atomic_rule_id, a.rule_name, c.column_name
        FROM ref_trig_atomic_rule a
        JOIN ref_ma_columns c
          ON c.column_name = a.rule_name AND c.drv_cat_table = 'drv_cat_atomic_input'
        WHERE a.deprecated_at IS NULL
    """)).mappings().all()
    out = {}
    for r in rows:
        col = r["column_name"]
        if col in valid_cols and r["atomic_rule_id"] not in out:
            out[r["atomic_rule_id"]] = (r["rule_name"], col)
    return out


def _fetch_xy(s, col, rule_id, label, window):
    """Return (x[], hit[], fwd[], date[]) for one rule. col is validated upstream.
    Ordered chronologically so callers can split by index (Task 6)."""
    fwd_col = "fwd_5d_pct" if window == 5 else "fwd_20d_pct"
    rows = s.execute(text(f"""
        SELECT ci."{col}"::float AS x, ro.hit::int AS hit,
               ro.{fwd_col}::float AS fwd, ro.as_of_date AS dt
        FROM drv_rule_outcome ro
        JOIN drv_cat_atomic_input ci
          ON ci.tos_symbol = ro.tos_symbol AND ci.as_of_date = ro.as_of_date
        WHERE ro.rule_kind = 'atomic' AND ro.rule_id = :rid
          AND ci."{col}" IS NOT NULL
          AND ro.{fwd_col} IS NOT NULL
        ORDER BY ro.as_of_date
    """), {"rid": str(rule_id)}).all()
    xs   = [r[0] for r in rows if r[0] is not None]
    hits = [r[1] for r in rows if r[0] is not None]
    fwds = [r[2] for r in rows if r[0] is not None]
    dts  = [r[3] for r in rows if r[0] is not None]
    return xs, hits, fwds, dts


def _fit_logreg(xs, hits):
    """Return (x0, k) from logistic regression of hit ~ x, or None."""
    import numpy as np
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        raise SystemExit("scikit-learn required for --method logreg "
                         "(pip install scikit-learn --break-system-packages), "
                         "or use --method sweep")
    X = np.array(xs, dtype=float).reshape(-1, 1)
    y = np.array(hits, dtype=int)
    if len(set(y.tolist())) < 2:
        return None
    m = LogisticRegression()
    m.fit(X, y)
    k = float(m.coef_[0][0])
    b = float(m.intercept_[0])
    if abs(k) < 1e-9:
        return None
    x0 = -b / k          # decision boundary: where P(hit)=0.5
    return x0, k


def _fit_sweep(xs, fwds, min_support):
    """Pick threshold t maximising mean fwd return of {x >= t}. Returns t or None."""
    import numpy as np
    x = np.array(xs, dtype=float)
    f = np.array(fwds, dtype=float)
    cands = np.quantile(x, np.linspace(0.1, 0.9, 17))
    best_t, best_m = None, -1e18
    for t in cands:
        sel = x >= t
        if sel.sum() < min_support:
            continue
        m = float(f[sel].mean())
        if m > best_m:
            best_m, best_t = m, float(t)
    return best_t


def _mean_edge(xs, fwds, threshold=None):
    """Mean fwd return for the subset above threshold (or whole set if threshold=None)."""
    import numpy as np
    x = np.array(xs, dtype=float)
    f = np.array(fwds, dtype=float)
    if threshold is not None:
        mask = x >= threshold
    else:
        mask = np.ones(len(x), dtype=bool)
    if mask.sum() == 0:
        return None, 0
    return float(f[mask].mean()), int(mask.sum())


# =============================================================================
# TASK_67 — Bull-gate threshold fitting
# =============================================================================

# Each entry: (rule_key, feature_col, direction)
# direction: 'ge' → feature >= threshold is the bullish/bearish arm
#            'le' → feature <= threshold (negative arm)
# feature_col: column in drv_cat_atomic_input to read
# Candidate threshold values: integer grid -5 .. 5
_BULL_GATE_RULES = [
    # Bullish arm of _bull_expr
    ("bull.pos_hi.JN", "trade_rule",          "ge"),
    ("bull.pos_hi.JQ", "trend_rule",          "ge"),
    ("bull.pos_hi.JV", "trade_trend_sd_rule", "ge"),
    ("bull.pos_lo.JN", "trade_rule",          "ge"),
    ("bull.pos_lo.JQ", "trend_rule",          "ge"),
    ("bull.pos_lo.JV", "trade_trend_sd_rule", "ge"),
    # Bearish arm (negative thresholds; for le() comparisons)
    ("bull.neg_hi.JN", "trade_rule",          "le"),
    ("bull.neg_hi.JQ", "trend_rule",          "le"),
    ("bull.neg_lo.JN", "trade_rule",          "le"),
    ("bull.neg_lo.JQ", "trend_rule",          "le"),
    # BB streak thresholds
    ("bb_bull.hi.LP",  "bbstreak_rule",       "ge"),
    ("bb_bull.hi.LS",  "bbstreak_days_rule",  "ge"),
]


def _fetch_bull_gate_xy(s, col, direction, label_window):
    """Fetch (feature[], fwd[], dates[]) for a bull-gate rule.

    For 'ge' rules we compute fwd return for rows where col IS NOT NULL.
    For 'le' rules same but on the negative tail.
    Chronologically ordered so callers can split by index.
    """
    fwd_col = "fwd_5d_pct" if label_window == 5 else "fwd_20d_pct"
    # col is validated against the allow-list _VALID_BULL_COLS upstream
    rows = s.execute(text(f"""
        SELECT ci."{col}"::float AS x,
               ro.{fwd_col}::float AS fwd,
               ro.as_of_date AS dt
        FROM drv_rule_outcome ro
        JOIN drv_cat_atomic_input ci
          ON ci.tos_symbol = ro.tos_symbol
         AND ci.as_of_date = ro.as_of_date
        WHERE ro.{fwd_col} IS NOT NULL
          AND ci."{col}" IS NOT NULL
        ORDER BY ro.as_of_date
    """)).all()
    xs   = [r[0] for r in rows]
    fwds = [r[1] for r in rows]
    dts  = [r[2] for r in rows]
    return xs, fwds, dts


def _sweep_bull_gate(xs, fwds, direction, min_support, candidates=None):
    """Sweep integer thresholds and pick the one maximising mean fwd return
    for the selected subset (>= t for 'ge', <= t for 'le').
    Returns (best_t, best_edge, n_above) or (None, None, 0).
    """
    import numpy as np
    x = np.array(xs, dtype=float)
    f = np.array(fwds, dtype=float)
    if candidates is None:
        candidates = list(range(-5, 6))  # integer grid -5..5
    best_t, best_m, best_n = None, -1e18, 0
    for t in candidates:
        if direction == "ge":
            sel = x >= t
        else:
            sel = x <= t
        if sel.sum() < min_support:
            continue
        m = float(f[sel].mean())
        if m > best_m:
            best_m, best_t, best_n = m, float(t), int(sel.sum())
    return best_t, (best_m if best_t is not None else None), best_n


def _get_proven_rule_keys(s):
    """Return set of rule_names with proven/promising confidence in v_atomic_rule_scorecard."""
    try:
        rows = s.execute(text(
            "SELECT rule_name FROM v_atomic_rule_scorecard "
            "WHERE confidence IN ('proven', 'promising')"
        )).scalars().all()
        return set(rows)
    except Exception:
        return set()   # scorecard table absent → no gating


def _valid_bull_cols(s) -> set:
    """Columns actually present in drv_cat_atomic_input."""
    try:
        rows = s.execute(text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name='drv_cat_atomic_input'"
        )).scalars().all()
        return set(rows)
    except Exception:
        return set()


def main_bull_gate(args) -> int:
    """Fit bull-gate thresholds and write to ref_threshold_override + history."""
    if not settings.pg_password:
        log.error("PG_PASSWORD empty in .env"); return 2

    train_pct = max(0.5, min(0.95, args.train_pct))
    label_window = args.label_window

    with session_scope() as s:
        proven = _get_proven_rule_keys(s)
        valid_cols = _valid_bull_cols(s)
        today_str = s.execute(text("SELECT CURRENT_DATE")).scalar().isoformat()

        results = []  # (rule_key, fitted_value, holdout_metric, n, train_start, train_end)

        for rule_key, col, direction in _BULL_GATE_RULES:
            # Gate: only fit rules whose feature column has scorecard edge
            if proven and col not in proven:
                log.info("  SKIP %s — col '%s' not proven/promising", rule_key, col)
                continue
            if col not in valid_cols:
                log.warning("  SKIP %s — col '%s' not in drv_cat_atomic_input", rule_key, col)
                continue

            xs, fwds, dts = _fetch_bull_gate_xy(s, col, direction, label_window)
            n_total = len(xs)
            if n_total < args.min_samples:
                log.info("  SKIP %s — only %d samples (need %d)", rule_key, n_total, args.min_samples)
                continue

            split_idx = max(1, int(n_total * train_pct))
            xs_tr, fwds_tr, dts_tr = xs[:split_idx], fwds[:split_idx], dts[:split_idx]
            xs_ho, fwds_ho = xs[split_idx:], fwds[split_idx:]

            train_start = min(dts_tr).isoformat() if dts_tr else None
            train_end   = max(dts_tr).isoformat() if dts_tr else None

            best_t, train_edge, n_above = _sweep_bull_gate(
                xs_tr, fwds_tr, direction, args.min_support)
            if best_t is None:
                log.info("  SKIP %s — no threshold passed min_support=%d", rule_key, args.min_support)
                continue

            # Evaluate holdout
            import numpy as np
            xh = np.array(xs_ho, dtype=float)
            fh = np.array(fwds_ho, dtype=float)
            if direction == "ge":
                hmask = xh >= best_t
            else:
                hmask = xh <= best_t
            ho_n = int(hmask.sum())
            ho_edge = float(fh[hmask].mean()) if ho_n > 0 else None

            if not args.no_holdout_gate and (ho_edge is None or ho_edge <= 0):
                log.warning("  SKIP %s — holdout edge %.3f <= 0 (overfit flag)",
                            rule_key, ho_edge or 0)
                continue

            log.info("  [%s] col=%-22s dir=%-2s fitted=%-4s "
                     "train_edge=%.3f holdout_edge=%.3f holdout_n=%d",
                     rule_key, col, direction, best_t,
                     train_edge or 0, ho_edge or 0, ho_n)
            results.append((rule_key, best_t, ho_edge, ho_n, train_start, train_end))

        if not results:
            log.warning("No bull-gate rules passed filters. Nothing written.")
            return 0

        # Write calculated_value + history rows
        for rule_key, fitted, ho_edge, ho_n, tr_start, tr_end in results:
            s.execute(text("""
                UPDATE ref_threshold_override
                   SET calculated_value = :v, updated_at = NOW()
                 WHERE rule_key = :k
            """), {"v": fitted, "k": rule_key})
            s.execute(text("""
                INSERT INTO ref_threshold_fit_history
                  (rule_key, fitted_value, fit_date,
                   train_start, train_end, holdout_metric, n,
                   notes)
                VALUES (:k, :v, :fd, :ts, :te, :hm, :n, :notes)
            """), {
                "k":     rule_key,
                "v":     fitted,
                "fd":    today_str,
                "ts":    tr_start,
                "te":    tr_end,
                "hm":    ho_edge,
                "n":     ho_n,
                "notes": (f"method=sweep label_window={label_window}d "
                          f"train_pct={train_pct:.0%}"),
            })

        s.commit()
        log.info("=== Bull-gate fitting done: %d rules updated ===", len(results))
        log.info("  calculated_value written to ref_threshold_override "
                 "(active_source still 'original').")
        log.info("  To activate: UPDATE ref_threshold_override "
                 "SET active_source='calculated' WHERE rule_key IN (%s);",
                 ", ".join(f"'{r[0]}'" for r in results))
        log.info("  Then re-derive to apply new thresholds.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", choices=["param-set", "bull-gate"], default="param-set",
                   help="param-set (default): tune ref_trig_param_set thresholds; "
                        "bull-gate: fit revertible bull-gate cutoffs (TASK_67)")
    p.add_argument("--method", choices=["logreg", "sweep"], default="logreg")
    p.add_argument("--label", choices=["hit", "fwd20"], default="hit",
                   help="logreg uses hit; sweep uses forward return")
    p.add_argument("--label-window", type=int, choices=[5, 20], default=20)
    p.add_argument("--min-samples", type=int, default=50)
    p.add_argument("--min-support", type=int, default=20,
                   help="sweep: min observations above the threshold")
    p.add_argument("--label-set", default=None, help="Param-set label (default auto)")
    p.add_argument("--activate", action="store_true",
                   help="Activate the new set (deactivates any current active set)")
    p.add_argument("--train-pct", type=float, default=0.70,
                   help="Fraction of chronological data used for training (default 0.70)")
    p.add_argument("--no-holdout-gate", action="store_true",
                   help="Skip the hold-out guard (allow saving even with negative holdout edge)")
    args = p.parse_args()

    # TASK_67: dispatch to bull-gate fitter when --target bull-gate
    if args.target == "bull-gate":
        return main_bull_gate(args)

    if not settings.pg_password:
        log.error("PG_PASSWORD empty in .env"); return 2

    train_pct = max(0.5, min(0.95, args.train_pct))  # clamp to sane range
    label = args.label_set or f"ml-{args.method}-{args.label_window}d"

    with session_scope() as s:
        valid_cols = _valid_columns(s)
        feats = _rule_feature_columns(s, valid_cols)
        if not feats:
            log.error("No atomic rules resolved to a drv_cat_atomic_input column "
                      "(check ref_ma_columns). Nothing to tune."); return 1
        log.info("Resolved %d atomic rules to feature columns. Method=%s train_pct=%.0f%%",
                 len(feats), args.method, train_pct * 100)

        results = []      # (rule_id, rule_name, params{}, train_edge, holdout_edge, holdout_n)
        skipped_holdout = 0
        for rid, (rname, col) in sorted(feats.items()):
            xs, hits, fwds, _dts = _fetch_xy(s, col, rid, args.label, args.label_window)
            n_total = len(xs)
            if n_total < args.min_samples:
                continue

            # Chronological split: first train_pct rows = train, remainder = hold-out.
            split_idx = max(1, int(n_total * train_pct))
            xs_tr,   hits_tr,   fwds_tr   = xs[:split_idx],   hits[:split_idx],   fwds[:split_idx]
            xs_hold, hits_hold, fwds_hold = xs[split_idx:], hits[split_idx:], fwds[split_idx:]

            if args.method == "logreg":
                fit = _fit_logreg(xs_tr, hits_tr)
                if not fit:
                    continue
                x0, k = fit
                threshold = x0  # decision boundary for edge calc
                params = {"x0": round(x0, 6), "k": round(k, 6)}
            else:
                t = _fit_sweep(xs_tr, fwds_tr, args.min_support)
                if t is None:
                    continue
                threshold = t
                params = {"brkeout_from": round(t, 6)}

            # Evaluate both splits
            te, _ = _mean_edge(xs_tr, fwds_tr, threshold)
            he, hn = _mean_edge(xs_hold, fwds_hold, threshold)

            if te is not None and he is not None:
                log.info("  [%s] %-26s train=%.3f holdout=%.3f (n=%d/%d=%d) %s",
                         rid, (rname or "")[:26], te, he, split_idx, n_total - split_idx,
                         params)
                if not args.no_holdout_gate:
                    if he <= 0:
                        log.warning("    SKIPPED (holdout edge %.3f <= 0 — overfit flag)", he)
                        skipped_holdout += 1
                        continue
                    if te > 0 and he < te * 0.5:
                        log.warning("    SKIPPED (holdout %.3f < half of train %.3f — "
                                    "possible overfit)", he, te)
                        skipped_holdout += 1
                        continue
            results.append((rid, rname, params, te, he, hn))

        if not results:
            log.warning("No rules passed filters (min-samples=%d, holdout gate=%s). "
                        "%d rules skipped by holdout gate.",
                        args.min_samples, not args.no_holdout_gate, skipped_holdout)
            return 0

        # Aggregate train/holdout edges across all rules
        all_te = [r[3] for r in results if r[3] is not None]
        all_he = [r[4] for r in results if r[4] is not None]
        agg_te = round(sum(all_te) / len(all_te), 4) if all_te else None
        agg_he = round(sum(all_he) / len(all_he), 4) if all_he else None
        total_hn = sum(r[5] or 0 for r in results)

        log.info("=== Tuned %d rules (skipped %d by holdout gate) ===",
                 len(results), skipped_holdout)
        log.info("    Aggregate train_edge=%.4f  holdout_edge=%.4f  holdout_n=%d",
                 agg_te or 0, agg_he or 0, total_hn)
        for rid, rname, params, te, he, hn in results:
            log.info("  [%s] %-28s %s  te=%.3f he=%.3f",
                     rid, (rname or "")[:28], json.dumps(params),
                     te or 0, he or 0)

        notes = (f"method={args.method} label={args.label} window={args.label_window}d "
                 f"min_samples={args.min_samples} train_pct={train_pct:.0%}; "
                 f"{len(results)} rules tuned; "
                 f"agg_train_edge={agg_te} agg_holdout_edge={agg_he}")

        # Write the param set
        pid = s.execute(text("""
            INSERT INTO ref_trig_param_set
              (label, provenance, is_active, notes,
               train_edge, holdout_edge, holdout_n, validated)
            VALUES (:label, :prov, FALSE, :notes,
                    :te, :he, :hn, TRUE)
            RETURNING param_set_id
        """), {"label": label, "prov": f"ml:{args.method}",
               "notes": notes,
               "te": agg_te, "he": agg_he, "hn": total_hn}).scalar()
        for rid, _rname, params, _te, _he, _hn in results:
            for pname, pval in params.items():
                s.execute(text("""
                    INSERT INTO ref_trig_param_value
                      (param_set_id, target_kind, target_id, param_name, param_value)
                    VALUES (:pid, 'atomic', :tid, :pname, :pval)
                    ON CONFLICT (param_set_id, target_kind, target_id, param_name)
                    DO UPDATE SET param_value = EXCLUDED.param_value
                """), {"pid": pid, "tid": str(rid), "pname": pname, "pval": pval})

        if args.activate:
            s.execute(text("UPDATE ref_trig_param_set SET is_active = FALSE WHERE is_active = TRUE"))
            s.execute(text("UPDATE ref_trig_param_set SET is_active = TRUE WHERE param_set_id = :pid"),
                      {"pid": pid})
            log.info("Param set %s ACTIVATED. Run `python -m etl.rebuild_rules` to apply.", pid)
        else:
            log.info("Param set %s written (INACTIVE). Backtest, then activate:", pid)
            log.info("  UPDATE ref_trig_param_set SET is_active=TRUE WHERE param_set_id=%s;", pid)
        s.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

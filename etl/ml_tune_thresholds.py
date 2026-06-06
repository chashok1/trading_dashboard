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
    """Return (x[], hit[], fwd[]) for one rule. col is validated upstream."""
    fwd_col = "fwd_5d_pct" if window == 5 else "fwd_20d_pct"
    rows = s.execute(text(f"""
        SELECT ci."{col}"::float AS x, ro.hit::int AS hit, ro.{fwd_col}::float AS fwd
        FROM drv_rule_outcome ro
        JOIN drv_cat_atomic_input ci
          ON ci.tos_symbol = ro.tos_symbol AND ci.as_of_date = ro.as_of_date
        WHERE ro.rule_kind = 'atomic' AND ro.rule_id = :rid
          AND ci."{col}" IS NOT NULL
          AND ro.{fwd_col} IS NOT NULL
    """), {"rid": str(rule_id)}).all()
    xs = [r[0] for r in rows if r[0] is not None]
    hits = [r[1] for r in rows if r[0] is not None]
    fwds = [r[2] for r in rows if r[0] is not None]
    return xs, hits, fwds


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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
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
    args = p.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD empty in .env"); return 2

    label = args.label_set or f"ml-{args.method}-{args.label_window}d"

    with session_scope() as s:
        valid_cols = _valid_columns(s)
        feats = _rule_feature_columns(s, valid_cols)
        if not feats:
            log.error("No atomic rules resolved to a drv_cat_atomic_input column "
                      "(check ref_ma_columns). Nothing to tune."); return 1
        log.info("Resolved %d atomic rules to feature columns. Method=%s",
                 len(feats), args.method)

        results = []   # (rule_id, rule_name, params{})
        for rid, (rname, col) in sorted(feats.items()):
            xs, hits, fwds = _fetch_xy(s, col, rid, args.label, args.label_window)
            if len(xs) < args.min_samples:
                continue
            if args.method == "logreg":
                fit = _fit_logreg(xs, hits)
                if not fit:
                    continue
                x0, k = fit
                results.append((rid, rname, {"x0": round(x0, 6), "k": round(k, 6)}))
            else:
                t = _fit_sweep(xs, fwds, args.min_support)
                if t is None:
                    continue
                results.append((rid, rname, {"brkeout_from": round(t, 6)}))

        if not results:
            log.warning("No rules had enough data (min-samples=%d). "
                        "Are user_action_log / drv_rule_outcome populated?", args.min_samples)
            return 0

        log.info("=== Tuned %d rules ===", len(results))
        for rid, rname, params in results:
            log.info("  [%s] %-28s %s", rid, (rname or "")[:28], json.dumps(params))

        # Write the param set
        pid = s.execute(text("""
            INSERT INTO ref_trig_param_set (label, provenance, is_active, notes)
            VALUES (:label, :prov, FALSE, :notes)
            RETURNING param_set_id
        """), {"label": label, "prov": f"ml:{args.method}",
               "notes": f"method={args.method} label={args.label} window={args.label_window}d "
                        f"min_samples={args.min_samples}; {len(results)} rules tuned"}).scalar()
        for rid, _rname, params in results:
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

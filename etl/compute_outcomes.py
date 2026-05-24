"""
Outcome ETL — Compute hit/miss rates for logged user actions.

Reads user_action_log entries older than 5 trading days,
computes forward returns, and populates drv_rule_outcome.
"""
import ast
import json
from datetime import date, timedelta
from sqlalchemy import text
from etl.db import session_scope
import logging

logger = logging.getLogger(__name__)


def get_trading_days_offset(start_date: date, num_days: int) -> date:
    """Find the date N trading days after start_date."""
    with session_scope() as s:
        result = s.execute(text("""
            SELECT MAX(snapshot_date) FROM drv_ma
            WHERE snapshot_date > :start
            ORDER BY snapshot_date
            LIMIT :days
        """), {
            "start": start_date,
            "days": num_days,
        }).scalar()
    return result or start_date


def compute_outcomes(dry_run: bool = True) -> dict:
    """
    Compute rule outcomes from user actions.

    Returns: {"processed": N, "errors": M}
    """
    with session_scope() as s:
        settings = _load_settings(s)

        # Find unprocessed actions older than 5 trading days
        sql = """
            SELECT id, as_of_date, symbol, action_code, triggered_rules
            FROM user_action_log
            WHERE as_of_date <= CURRENT_DATE - INTERVAL '5 days'
            AND id NOT IN (SELECT DISTINCT id FROM drv_rule_outcome
                          WHERE rule_id IS NOT NULL)
            LIMIT 1000
        """

        actions = s.execute(text(sql)).mappings().all()
        processed = 0
        errors = 0

        for action in actions:
            try:
                # Get forward returns
                fwd_5d_pct = _get_forward_return(s, action["symbol"], action["as_of_date"], 5)
                fwd_20d_pct = _get_forward_return(s, action["symbol"], action["as_of_date"], 20)

                # Determine hit
                hit = _determine_hit(action["action_code"], fwd_5d_pct, settings)

                # Parse triggered rules
                triggered_raw = action["triggered_rules"]
                if triggered_raw:
                    if isinstance(triggered_raw, list):
                        triggered = triggered_raw
                    else:
                        try:
                            triggered = json.loads(triggered_raw)
                        except (json.JSONDecodeError, ValueError):
                            try:
                                triggered = ast.literal_eval(triggered_raw)
                            except Exception:
                                triggered = []
                else:
                    triggered = []

                # Write outcome for each rule
                for rule in triggered:
                    rule_id = rule.get("rule_id", rule.get("id", "unknown"))
                    rule_kind = rule.get("kind", "unknown")

                    insert_sql = """
                        INSERT INTO drv_rule_outcome
                          (rule_id, rule_kind, as_of_date, symbol, action_code,
                           fwd_5d_pct, fwd_20d_pct, hit)
                        VALUES
                          (:rid, :kind, :d, :sym, :code, :f5, :f20, :hit)
                        ON CONFLICT (rule_id, as_of_date, symbol) DO UPDATE SET
                          fwd_5d_pct = :f5,
                          fwd_20d_pct = :f20,
                          hit = :hit
                    """
                    if not dry_run:
                        s.execute(text(insert_sql), {
                            "rid": rule_id,
                            "kind": rule_kind,
                            "d": action["as_of_date"],
                            "sym": action["symbol"],
                            "code": action["action_code"],
                            "f5": fwd_5d_pct,
                            "f20": fwd_20d_pct,
                            "hit": hit,
                        })

                processed += 1

            except Exception as e:
                logger.error(f"Error processing action {action['id']}: {e}")
                errors += 1

        if not dry_run:
            s.commit()

        return {"processed": processed, "errors": errors}


def _get_forward_return(session, symbol: str, as_of_date: date, days: int) -> float:
    """Get forward return N days later."""
    start_price = session.execute(text("""
        SELECT last_price FROM drv_ma
        WHERE symbol = :sym AND as_of_date = :d
        LIMIT 1
    """), {"sym": symbol, "d": as_of_date}).scalar()

    if not start_price:
        return None

    fwd_date = get_trading_days_offset(as_of_date, days)

    end_price = session.execute(text("""
        SELECT last_price FROM drv_ma
        WHERE symbol = :sym AND as_of_date = :d
        LIMIT 1
    """), {"sym": symbol, "d": fwd_date}).scalar()

    if not end_price or start_price == 0:
        return None

    return ((end_price - start_price) / start_price) * 100


def _load_settings(session) -> dict:
    """Load ref_settings into a dict for use by _determine_hit."""
    rows = session.execute(text(
        "SELECT setting_name, setting_value FROM ref_settings"
    )).fetchall()
    return {name: value for name, value in rows}


def _determine_hit(action_code: str, fwd_return: float, settings: dict = None) -> bool:
    """Determine if rule "hit" based on action and forward return.

    Code groups (compared against forward return; settings drive thresholds):
      sell-direction  SA, STM, SS, REMOVE, REDUCE        → hit when return ≤ sell threshold
      buy-direction   BM, ADD, INCREASE                  → hit when return ≥ buy  threshold
      neutral         HOLD, SKIP                         → hit when |return| < hold threshold
      meta            ACTED (system rec not resolvable)  → hit when |return| ≥ |sell| or ≥ buy

    `ACTED` is the Cockpit meta-code that should normally be resolved upstream
    (in `POST /api/actions`) to the system's recommended action. If it slipped
    through unresolved, we score it as "the symbol moved meaningfully" — a
    weaker but non-zero signal so the row still contributes to drv_rule_outcome.
    """
    if fwd_return is None:
        return False
    cfg = settings or {}
    def _f(key, default):
        try:
            return float(cfg.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    code = (action_code or "").upper().strip()
    if code in ("SA", "STM", "SS", "REMOVE", "REDUCE"):
        threshold = _f("outcome_hit_threshold_sell", -0.5)
        return fwd_return <= threshold
    elif code in ("BM", "ADD", "INCREASE"):
        threshold = _f("outcome_hit_threshold_buy", 0.5)
        return fwd_return >= threshold
    elif code in ("HOLD", "SKIP"):
        threshold = _f("outcome_hold_threshold", 1.0)
        return abs(fwd_return) < threshold
    elif code == "ACTED":
        # Unresolved meta-code: count it as a hit if the symbol moved
        # meaningfully in either direction.
        sell_th = abs(_f("outcome_hit_threshold_sell", -0.5))
        buy_th  = _f("outcome_hit_threshold_buy", 0.5)
        return abs(fwd_return) >= min(sell_th, buy_th)
    return False


if __name__ == "__main__":
    from etl._logging import setup_logging
    setup_logging()
    result = compute_outcomes(dry_run=False)
    print(f"Processed: {result['processed']}, Errors: {result['errors']}")
